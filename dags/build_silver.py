"""
build_silver.py
---------------
Lit enterprise_finale (ou enterprises en fallback) et écrit enterprise_silver.
"""

from __future__ import annotations

import argparse
import logging
import os

from pymongo import UpdateOne

from db.mongo_client import get_db, init_silver_indexes
from init_mongodb import DEFAULT_KBO_PATH
from silver.transform import bronze_to_silver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BATCH_SIZE = 5_000


def _source_collection(db, source: str):
    if source == "auto":
        if db.enterprise_finale.count_documents({}) > 0:
            return db.enterprise_finale, "EnterpriseNumber"
        log.warning("enterprise_finale vide — fallback sur enterprises")
        return db.enterprises, "enterprise_number"
    if source == "enterprise_finale":
        return db.enterprise_finale, "EnterpriseNumber"
    return db.enterprises, "enterprise_number"


def build_silver(
    source: str = "auto",
    kbo_path: str = DEFAULT_KBO_PATH,
    limit: int | None = None,
) -> dict:
    db = get_db()
    init_silver_indexes()

    coll, id_field = _source_collection(db, source)
    total_src = coll.count_documents({})
    log.info(f"Source : {coll.name} ({total_src:,} documents)")

    ops: list[UpdateOne] = []
    processed = upserted = 0

    cursor = coll.find({})
    if limit:
        cursor = cursor.limit(limit)

    for doc in cursor:
        silver = bronze_to_silver(doc, kbo_path=kbo_path)
        key = silver.get("EnterpriseNumber") or doc.get(id_field)
        ops.append(UpdateOne(
            {"EnterpriseNumber": key},
            {"$set": silver},
            upsert=True,
        ))
        processed += 1

        if len(ops) >= BATCH_SIZE:
            result = db.enterprise_silver.bulk_write(ops, ordered=False)
            upserted += result.upserted_count + result.modified_count
            log.info(f"  {processed:,} documents transformés")
            ops = []

    if ops:
        result = db.enterprise_silver.bulk_write(ops, ordered=False)
        upserted += result.upserted_count + result.modified_count

    total_silver = db.enterprise_silver.count_documents({})
    log.info(f"✓ enterprise_silver : {total_silver:,} documents ({processed:,} traités)")
    return {"source": coll.name, "processed": processed, "total_silver": total_silver}


def run(source: str = "auto", kbo_path: str = DEFAULT_KBO_PATH, limit: int | None = None) -> None:
    log.info("=" * 60)
    log.info("BUILD SILVER — enterprise_finale → enterprise_silver")
    log.info("=" * 60)
    stats = build_silver(source=source, kbo_path=kbo_path, limit=limit)
    log.info(f"  Source traitée : {stats['source']}")
    log.info(f"  Documents Silver : {stats['total_silver']:,}")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MongoDB enterprise_silver")
    parser.add_argument("--source", default="auto", choices=["auto", "enterprise_finale", "enterprises"])
    parser.add_argument("--kbo-path", default=DEFAULT_KBO_PATH)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(source=args.source, kbo_path=args.kbo_path, limit=args.limit)
