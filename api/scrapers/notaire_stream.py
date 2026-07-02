"""
notaire_stream.py — streaming SSE des statuts notaire.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hdfs import InsecureClient  # noqa: E402

import stapor_scraper  # noqa: E402
from api.config import HDFS_URL, HDFS_USER  # noqa: E402
from api.db import get_db  # noqa: E402

log = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _persist_statute(enterprise_number: str, statute: dict, hdfs_path: str | None) -> None:
    db = get_db()
    doc_id = statute.get("documentId", "")
    db.notaire_statutes.update_one(
        {"enterprise_number": enterprise_number, "document_id": doc_id},
        {"$set": {
            "enterprise_number": enterprise_number,
            "document_id": doc_id,
            "deed_date": statute.get("deedDate"),
            "document_status": statute.get("documentStatus"),
            "hdfs_path": hdfs_path,
            "raw": statute,
            "scraped_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


async def stream_statutes(enterprise_number: str) -> AsyncIterator[str]:
    """Générateur SSE — émet chaque statut au fur et à mesure."""
    db = get_db()
    cached = list(db.notaire_statutes.find(
        {"enterprise_number": enterprise_number},
        {"_id": 0},
    ))
    if cached:
        for doc in cached:
            yield _sse("statute", doc)
        yield _sse("done", {"count": len(cached), "cached": True})
        return

    num = enterprise_number.replace(".", "")
    try:
        session = stapor_scraper.get_session(seed_bce=num)
        session, statutes = stapor_scraper.get_statutes(session, enterprise_number)
        hdfs = InsecureClient(HDFS_URL, user=HDFS_USER)

        count = 0
        for statute in statutes:
            hdfs_path = stapor_scraper.download_statute_pdf(
                session, enterprise_number, statute, hdfs
            )
            doc = {
                "enterprise_number": enterprise_number,
                "document_id": statute.get("documentId"),
                "deed_date": statute.get("deedDate"),
                "document_status": statute.get("documentStatus"),
                "hdfs_path": hdfs_path,
                "raw": statute,
            }
            _persist_statute(enterprise_number, statute, hdfs_path)
            count += 1
            yield _sse("statute", doc)

        yield _sse("done", {"count": count, "cached": False})

    except Exception as exc:
        log.exception("Erreur SSE notaire %s", enterprise_number)
        yield _sse("error", {"message": str(exc)})
