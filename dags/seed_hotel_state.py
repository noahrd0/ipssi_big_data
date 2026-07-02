"""
seed_hotel_state.py
-------------------
Charge les entreprises hôtellerie en StateDB (status=pending).
"""

from __future__ import annotations

import argparse
import logging

from db.mongo_client import get_db, init_silver_indexes
from db.state_db import ENTERPRISE_META_DEPOSIT, bulk_mark_pending
from filters.hotel import get_hotel_enterprises

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def seed(collection: str = "auto", limit: int | None = None) -> int:
    db = get_db()
    init_silver_indexes()

    nums = get_hotel_enterprises(db, collection=collection)
    if limit:
        nums = nums[:limit]

    log.info(f"Entreprises hôtellerie identifiées : {len(nums):,}")

    records = [
        {
            "enterprise_number": num,
            "source":            "cbso",
            "deposit_id":        ENTERPRISE_META_DEPOSIT,
            "file_type":         "meta",
        }
        for num in nums
    ]
    inserted = bulk_mark_pending(records, db=db)
    log.info(f"StateDB : {inserted:,} nouvelles entrées pending (meta)")
    return len(nums)


def run(collection: str = "auto", limit: int | None = None) -> None:
    log.info("=" * 60)
    log.info("SEED HOTEL — StateDB pending")
    log.info("=" * 60)
    count = seed(collection=collection, limit=limit)
    log.info(f"✓ {count:,} entreprises hôtellerie enregistrées")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialiser StateDB pour hôtellerie")
    parser.add_argument("--collection", default="auto",
                        choices=["auto", "enterprise_finale", "enterprise_silver", "enterprises"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(collection=args.collection, limit=args.limit)
