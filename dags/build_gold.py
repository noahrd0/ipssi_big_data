"""
build_gold.py
-------------
Lit les CSV PCMN depuis HDFS (/data/bronze/{bce}/nbb/{year}/),
calcule les ratios et upsert dans MongoDB hotel_gold.

Usage :
    python build_gold.py
    python build_gold.py --limit 10
    python build_gold.py --enterprise 0434.409.550
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import datetime, timezone

from hdfs import InsecureClient
from pymongo import UpdateOne

from db.mongo_client import get_db
from db.state_db import get_done_enterprises
from filters.hotel import get_hotel_enterprises
from gold.pcmn_parser import detect_schema_type, extract_fields, parse_pcmn_csv
from gold.ratios import build_year_record

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HDFS_URL = os.getenv("HDFS_URL", "http://localhost:9870")
HDFS_USER = os.getenv("HDFS_USER", "root")
HDFS_BRONZE = os.getenv("HDFS_BRONZE", "/data/bronze")
COLLECTION_GOLD = "hotel_gold"

_YEAR_RE = re.compile(r"/nbb/(\d{4})/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_year(hdfs_path: str) -> int | None:
    m = _YEAR_RE.search(hdfs_path.replace("\\", "/"))
    return int(m.group(1)) if m else None


def _list_csv_paths(hdfs: InsecureClient, enterprise_number: str) -> list[tuple[int, str]]:
    """Retourne [(year, hdfs_path), ...] pour une entreprise."""
    base = f"{HDFS_BRONZE}/{enterprise_number}/nbb"
    results: list[tuple[int, str]] = []
    try:
        years = hdfs.list(base)
    except Exception:
        return results

    for year_name in years:
        if not str(year_name).isdigit():
            continue
        year_dir = f"{base}/{year_name}"
        try:
            files = hdfs.list(year_dir)
        except Exception:
            continue
        for fname in files:
            if not str(fname).lower().endswith(".csv"):
                continue
            path = f"{year_dir}/{fname}"
            year = int(year_name)
            results.append((year, path))
    return sorted(results, key=lambda x: x[0])


def _process_enterprise(hdfs: InsecureClient, enterprise_number: str) -> dict | None:
    csv_paths = _list_csv_paths(hdfs, enterprise_number)
    if not csv_paths:
        return None

    years_data: dict[int, dict] = {}
    schema_types: list[str] = []

    for year, path in csv_paths:
        try:
            with hdfs.read(path) as reader:
                content = reader.read()
        except Exception as exc:
            log.warning(f"  {enterprise_number} {path} : lecture échouée — {exc}")
            continue

        codes = parse_pcmn_csv(content)
        if not codes:
            continue

        schema = detect_schema_type(codes)
        schema_types.append(schema)
        fields = extract_fields(codes)
        years_data[year] = build_year_record(year, fields, schema)

    if not years_data:
        return None

    dominant_schema = max(set(schema_types), key=schema_types.count) if schema_types else "abrege"

    return {
        "enterprise_number": enterprise_number,
        "schema_type": dominant_schema,
        "last_updated": _now(),
        "years": sorted(years_data.values(), key=lambda y: y["year"]),
    }


def init_gold_indexes(db) -> None:
    db[COLLECTION_GOLD].create_index(
        [("enterprise_number", 1)], unique=True, name="idx_gold_number"
    )


def build_gold(
    limit: int | None = None,
    enterprise: str | None = None,
    only_done: bool = True,
) -> dict:
    db = get_db()
    init_gold_indexes(db)
    hdfs = InsecureClient(HDFS_URL, user=HDFS_USER)

    if enterprise:
        nums = [enterprise.strip()]
    elif only_done:
        done = get_done_enterprises("cbso")
        hotel = set(get_hotel_enterprises(db))
        nums = sorted(done & hotel)
        log.info(f"Entreprises hôtellerie done CBSO : {len(nums):,}")
    else:
        nums = get_hotel_enterprises(db)

    if limit:
        nums = nums[:limit]

    ops: list[UpdateOne] = []
    processed = 0
    empty = 0

    for i, num in enumerate(nums, 1):
        doc = _process_enterprise(hdfs, num)
        if not doc:
            empty += 1
            continue

        ops.append(
            UpdateOne(
                {"enterprise_number": num},
                {"$set": doc},
                upsert=True,
            )
        )
        processed += 1

        if len(ops) >= 200:
            db[COLLECTION_GOLD].bulk_write(ops, ordered=False)
            ops.clear()

        if i % 100 == 0 or i == len(nums):
            log.info(f"  Progression {i}/{len(nums)} — {processed} Gold docs")

    if ops:
        db[COLLECTION_GOLD].bulk_write(ops, ordered=False)

    total = db[COLLECTION_GOLD].count_documents({})
    stats = {
        "enterprises_scanned": len(nums),
        "gold_upserted": processed,
        "no_csv": empty,
        "hotel_gold_total": total,
    }
    log.info(f"Résultat Gold : {stats}")
    return stats


def run(
    limit: int | None = None,
    enterprise: str | None = None,
    only_done: bool = True,
) -> None:
    log.info("=" * 60)
    log.info("BUILD GOLD — hotel_gold")
    log.info("=" * 60)
    build_gold(limit=limit, enterprise=enterprise, only_done=only_done)
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construire la couche Gold hotel_gold")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--enterprise", default=None)
    parser.add_argument("--all-hotel", action="store_true", help="Toutes les hôtels, pas seulement done CBSO")
    args = parser.parse_args()
    run(limit=args.limit, enterprise=args.enterprise, only_done=not args.all_hotel)
