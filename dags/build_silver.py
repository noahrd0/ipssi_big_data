"""
build_silver.py
---------------
Lit enterprise_finale (ou enterprises en fallback) et écrit enterprise_silver.
"""

from __future__ import annotations

import argparse
import logging

from pymongo import UpdateOne

from db.mongo_client import get_db, init_silver_indexes
from init_mongodb import DEFAULT_KBO_PATH
from silver.kbo_codes import warm_cache
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


def _load_done_numbers(db) -> set[str]:
    """Charge les EnterpriseNumber déjà présents en Silver."""
    log.info("Chargement des numéros déjà en Silver...")
    done = set(db.enterprise_silver.distinct("EnterpriseNumber"))
    log.info(f"  {len(done):,} documents déjà en enterprise_silver")
    return done


def _iter_pending(coll, id_field: str, done: set[str], limit: int | None):
    """
    Itère sur les documents Bronze pas encore en Silver.
    Utilise $nin MongoDB pour ne pas relire l'existant (reprise rapide).
    """
    if not done:
        cursor = coll.find({})
        if limit:
            cursor = cursor.limit(limit)
        yield from cursor
        return

    log.info(f"  Reprise : {len(done):,} exclus via $nin")
    cursor = coll.find({id_field: {"$nin": list(done)}})
    if limit:
        count = 0
        for doc in cursor:
            yield doc
            count += 1
            if count >= limit:
                return
        return

    yield from cursor


def build_silver(
    source: str = "auto",
    kbo_path: str = DEFAULT_KBO_PATH,
    limit: int | None = None,
    skip_existing: bool = True,
) -> dict:
    db = get_db()
    init_silver_indexes()
    warm_cache(kbo_path)

    coll, id_field = _source_collection(db, source)
    total_src = coll.count_documents({})
    log.info(f"Source : {coll.name} ({total_src:,} documents)")

    done: set[str] = set()
    if skip_existing and not limit:
        done = _load_done_numbers(db)
        remaining = total_src - len(done)
        log.info(f"  À traiter : ~{remaining:,} documents")
    elif skip_existing and limit:
        done = _load_done_numbers(db)

    ops: list[UpdateOne] = []
    processed = written = 0

    for doc in _iter_pending(coll, id_field, done, limit):
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
            written += result.upserted_count + result.modified_count
            log.info(f"  {processed:,} documents transformés ({written:,} écrits)")
            ops = []

    if ops:
        result = db.enterprise_silver.bulk_write(ops, ordered=False)
        written += result.upserted_count + result.modified_count

    total_silver = db.enterprise_silver.count_documents({})
    skipped = len(done) if skip_existing else 0
    log.info(
        f"✓ enterprise_silver : {total_silver:,} documents "
        f"({processed:,} transformés, ~{skipped:,} ignorés)"
    )
    return {
        "source":       coll.name,
        "processed":    processed,
        "skipped":      skipped,
        "total_silver": total_silver,
    }


def run(
    source: str = "auto",
    kbo_path: str = DEFAULT_KBO_PATH,
    limit: int | None = None,
    skip_existing: bool = True,
) -> None:
    log.info("=" * 60)
    log.info("BUILD SILVER — enterprise_finale → enterprise_silver")
    log.info("=" * 60)
    stats = build_silver(
        source=source,
        kbo_path=kbo_path,
        limit=limit,
        skip_existing=skip_existing,
    )
    log.info(f"  Source traitée : {stats['source']}")
    log.info(f"  Transformés    : {stats['processed']:,}")
    log.info(f"  Ignorés        : ~{stats['skipped']:,}")
    log.info(f"  Total Silver   : {stats['total_silver']:,}")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MongoDB enterprise_silver")
    parser.add_argument("--source", default="auto", choices=["auto", "enterprise_finale", "enterprises"])
    parser.add_argument("--kbo-path", default=DEFAULT_KBO_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retraiter toutes les entreprises (désactive la reprise)",
    )
    args = parser.parse_args()
    run(
        source=args.source,
        kbo_path=args.kbo_path,
        limit=args.limit,
        skip_existing=not args.force,
    )
