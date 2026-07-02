"""
scrape_hotel_cbso.py
--------------------
Scraping CBSO ciblé hôtellerie — dépôts CSV 2021 à 2025.
Reprise via StateDB (pending / error / is_done par dépôt).
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from hdfs import InsecureClient

from db.mongo_client import get_db
from db.state_db import (
    count_done_filings,
    get_pending_enterprises,
    is_done,
    mark_done,
    mark_enterprise_done,
    mark_error,
    mark_in_progress,
)
from filters.hotel import get_hotel_enterprises
from scrapers.cbso_scraper import CBSO_DOC_BASE, fetch_deposit_list, filter_deposits
from scrapers.tor_session import get_with_rotation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HDFS_URL    = os.getenv("HDFS_URL", "http://localhost:9870")
HDFS_USER   = os.getenv("HDFS_USER", "root")
HDFS_BRONZE = "/data/bronze"
CSV_START_YEAR = 2021


def scrape_enterprise(
    num: str,
    hdfs: InsecureClient,
    csv_start_year: int = CSV_START_YEAR,
    sleep_sec: float = 1.5,
) -> dict:
    """Scrape les CSV CBSO d'une entreprise. Retourne stats {done, error, skipped}."""
    results = {"done": 0, "error": 0, "skipped": 0}
    mark_in_progress(num, "cbso")

    try:
        deposits  = fetch_deposit_list(num)
        par_annee = filter_deposits(deposits)
    except Exception as exc:
        log.error(f"[CBSO] {num} : liste dépôts échouée — {exc}")
        mark_error(num, "cbso", "_fetch", "meta", str(exc))
        return results

    for annee, depot in sorted(par_annee.items()):
        an = int(annee) if str(annee).isdigit() else 0
        if an < csv_start_year:
            continue

        if depot.get("migration"):
            log.info(f"  {num} {annee} : skip CSV (migration)")
            continue

        did = depot["id"]
        ref = depot.get("reference", did[:8])

        if is_done(num, "cbso", did, "csv"):
            results["skipped"] += 1
            continue

        hdfs_path = f"{HDFS_BRONZE}/{num}/nbb/{annee}/{ref}.csv"
        csv_url   = f"{CBSO_DOC_BASE}/consult/csv/{did}"
        time.sleep(sleep_sec)

        try:
            resp = get_with_rotation(
                csv_url,
                extra_headers={"Accept": "text/csv,application/octet-stream,*/*"},
                timeout=60,
            )

            if resp.status_code == 429:
                log.warning(f"[CBSO] 429 rate limit sur {num} — arrêt propre")
                mark_error(num, "cbso", did, "csv", "HTTP 429 Too Many Requests")
                results["error"] += 1
                return results

            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "problem+json" not in content_type and len(resp.content) > 100:
                hdfs.makedirs(f"{HDFS_BRONZE}/{num}/nbb/{annee}")
                with hdfs.write(hdfs_path, overwrite=True) as f:
                    f.write(resp.content)
                mark_done(num, "cbso", did, "csv", hdfs_path, len(resp.content), year=an)
                results["done"] += 1
                log.info(f"  ✓ {num} {annee} → {hdfs_path}")
            else:
                mark_error(num, "cbso", did, "csv",
                           f"HTTP {resp.status_code} / {content_type[:40]}")
                results["error"] += 1

        except Exception as exc:
            mark_error(num, "cbso", did, "csv", str(exc))
            results["error"] += 1

    filings = count_done_filings(num, "cbso")
    mark_enterprise_done(num, "cbso", filings)
    return results


def run_scrape(
    collection: str = "auto",
    limit: int | None = None,
    resume: bool = False,
    enterprise: str | None = None,
    csv_start_year: int = CSV_START_YEAR,
) -> dict:
    db = get_db()
    hdfs = InsecureClient(HDFS_URL, user=HDFS_USER)

    if enterprise:
        nums = [enterprise.strip()]
    elif resume:
        nums = get_pending_enterprises("cbso")
        log.info(f"Reprise StateDB : {len(nums):,} entreprises pending/error")
    else:
        nums = get_hotel_enterprises(db, collection=collection)
        log.info(f"Hôtellerie : {len(nums):,} entreprises")

    if limit:
        nums = nums[:limit]

    totals = {"done": 0, "error": 0, "skipped": 0, "enterprises": len(nums)}

    for i, num in enumerate(nums, 1):
        log.info(f"\n[{i}/{len(nums)}] {num}")
        stats = scrape_enterprise(num, hdfs, csv_start_year=csv_start_year)
        for k in ("done", "error", "skipped"):
            totals[k] += stats[k]
        time.sleep(2)

    log.info(f"\nRésultat global : {totals}")
    return totals


def run(
    collection: str = "auto",
    limit: int | None = None,
    resume: bool = False,
    enterprise: str | None = None,
    csv_start_year: int = CSV_START_YEAR,
) -> None:
    log.info("=" * 60)
    log.info("SCRAPE HOTEL CBSO — CSV 2021+")
    log.info("=" * 60)
    run_scrape(
        collection=collection,
        limit=limit,
        resume=resume,
        enterprise=enterprise,
        csv_start_year=csv_start_year,
    )
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraping CBSO hôtellerie 2021+")
    parser.add_argument("--collection", default="auto",
                        choices=["auto", "enterprise_finale", "enterprise_silver", "enterprises"])
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nombre d'entreprises")
    parser.add_argument("--resume", action="store_true", help="Reprendre depuis StateDB pending")
    parser.add_argument("--enterprise", default=None, help="Une seule entreprise BCE")
    parser.add_argument("--csv-start-year", type=int, default=CSV_START_YEAR)
    args = parser.parse_args()
    run(
        collection=args.collection,
        limit=args.limit,
        resume=args.resume,
        enterprise=args.enterprise,
        csv_start_year=args.csv_start_year,
    )
