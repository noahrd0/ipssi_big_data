"""
scrape_hotel_cbso.py
--------------------
Scraping CBSO ciblé hôtellerie — dépôts CSV 2021 à 2025.
Reprise via StateDB (pending / error / is_done par dépôt).

Optimisations :
  - skip entreprises déjà meta=done
  - 1 requête StateDB / entreprise (done deposit_ids en batch)
  - parallélisme (--workers) avec 1 proxy Tor par worker
  - Tor obligatoire (pas de fallback direct → évite les 429)
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from hdfs import InsecureClient

from db.mongo_client import get_db
from db.state_db import (
    ENTERPRISE_META_DEPOSIT,
    count_done_filings,
    get_done_deposit_ids,
    get_done_enterprises,
    get_pending_enterprises,
    mark_done,
    mark_enterprise_done,
    mark_error,
    mark_in_progress,
)
from filters.hotel import get_hotel_enterprises
from scrapers.cbso_scraper import (
    CBSO_DOC_BASE,
    CbsoFetchError,
    CbsoRateLimitError,
    fetch_deposit_list,
    filter_deposits,
)
from scrapers.tor_session import bind_worker_proxy, get_with_rotation

# Tor obligatoire pour le scraping hôtellerie
os.environ["CBSO_USE_DIRECT"] = "0"
os.environ.setdefault("CBSO_USE_TOR", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HDFS_URL       = os.getenv("HDFS_URL", "http://localhost:9870")
HDFS_USER      = os.getenv("HDFS_USER", "root")
HDFS_BRONZE    = "/data/bronze"
CSV_START_YEAR = 2021


def scrape_enterprise(
    num: str,
    hdfs: InsecureClient,
    csv_start_year: int = CSV_START_YEAR,
    sleep_csv: float = 0.3,
    done_ids: set[str] | None = None,
) -> dict:
    """Scrape les CSV CBSO d'une entreprise. Retourne stats {done, error, skipped}."""
    results = {"done": 0, "error": 0, "skipped": 0, "enterprise": num}
    mark_in_progress(num, "cbso")

    if done_ids is None:
        done_ids = get_done_deposit_ids(num, "cbso", "csv")

    try:
        deposits  = fetch_deposit_list(num)
        par_annee = filter_deposits(deposits)
    except CbsoRateLimitError as exc:
        log.error(f"[CBSO] {num} : rate-limit listing — {exc}")
        mark_error(num, "cbso", ENTERPRISE_META_DEPOSIT, "meta", str(exc))
        return results
    except (CbsoFetchError, Exception) as exc:
        log.error(f"[CBSO] {num} : liste dépôts échouée — {exc}")
        mark_error(num, "cbso", ENTERPRISE_META_DEPOSIT, "meta", str(exc))
        return results

    for annee, depot in sorted(par_annee.items()):
        an = int(annee) if str(annee).isdigit() else 0
        if an < csv_start_year:
            continue

        if depot.get("migration"):
            continue

        did = depot["id"]
        ref = depot.get("reference", did[:8])

        if did in done_ids:
            results["skipped"] += 1
            continue

        hdfs_path = f"{HDFS_BRONZE}/{num}/nbb/{annee}/{ref}.csv"
        csv_url   = f"{CBSO_DOC_BASE}/consult/csv/{did}"

        if sleep_csv > 0:
            time.sleep(sleep_csv)

        try:
            resp = get_with_rotation(
                csv_url,
                extra_headers={"Accept": "text/csv,application/octet-stream,*/*"},
                timeout=60,
            )

            if resp.status_code == 429:
                mark_error(num, "cbso", did, "csv", "HTTP 429 Too Many Requests")
                results["error"] += 1
                time.sleep(5)
                continue

            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "problem+json" not in content_type and len(resp.content) > 100:
                hdfs.makedirs(f"{HDFS_BRONZE}/{num}/nbb/{annee}")
                with hdfs.write(hdfs_path, overwrite=True) as f:
                    f.write(resp.content)
                mark_done(num, "cbso", did, "csv", hdfs_path, len(resp.content), year=an)
                done_ids.add(did)
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


_worker_counter = 0
_worker_lock = threading.Lock()


def _init_worker() -> None:
    """Assigne un proxy Tor distinct à chaque thread du pool."""
    global _worker_counter
    with _worker_lock:
        wid = _worker_counter
        _worker_counter += 1
    bind_worker_proxy(wid)

def _resolve_enterprises(
    db,
    collection: str,
    resume: bool,
    enterprise: str | None,
    skip_done: bool,
) -> list[str]:
    if enterprise:
        return [enterprise.strip()]

    if resume:
        nums = get_pending_enterprises("cbso")
        log.info(f"Reprise StateDB : {len(nums):,} entreprises pending/error")
        return nums

    nums = get_hotel_enterprises(db, collection=collection)
    log.info(f"Hôtellerie : {len(nums):,} entreprises")

    if skip_done:
        done = get_done_enterprises("cbso")
        nums = [n for n in nums if n not in done]
        log.info(f"  Skip {len(done):,} déjà terminées — {len(nums):,} à traiter")

    return nums


def _scrape_one(
    num: str,
    csv_start_year: int,
    sleep_csv: float,
) -> dict:
    hdfs = InsecureClient(HDFS_URL, user=HDFS_USER)
    done_ids = get_done_deposit_ids(num, "cbso", "csv")
    return scrape_enterprise(num, hdfs, csv_start_year, sleep_csv, done_ids)


def run_scrape(
    collection: str = "auto",
    limit: int | None = None,
    resume: bool = False,
    enterprise: str | None = None,
    csv_start_year: int = CSV_START_YEAR,
    workers: int = 3,
    sleep_csv: float = 0.3,
    skip_done: bool = True,
) -> dict:
    db = get_db()
    nums = _resolve_enterprises(db, collection, resume, enterprise, skip_done)

    if limit:
        nums = nums[:limit]

    totals = {"done": 0, "error": 0, "skipped": 0, "enterprises": len(nums)}
    if not nums:
        log.info("Rien à traiter.")
        return totals

    log.info(f"Workers : {workers} | sleep CSV : {sleep_csv}s | Tor : {os.getenv('CBSO_USE_TOR', '1')}")
    t0 = time.time()
    completed = 0

    if workers <= 1:
        bind_worker_proxy(0)
        hdfs = InsecureClient(HDFS_URL, user=HDFS_USER)
        for i, num in enumerate(nums, 1):
            log.info(f"[{i}/{len(nums)}] {num}")
            stats = scrape_enterprise(num, hdfs, csv_start_year, sleep_csv)
            for k in ("done", "error", "skipped"):
                totals[k] += stats[k]
    else:
        with ThreadPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
            futures = {
                pool.submit(_scrape_one, num, csv_start_year, sleep_csv): num
                for num in nums
            }
            for fut in as_completed(futures):
                num = futures[fut]
                completed += 1
                try:
                    stats = fut.result()
                    for k in ("done", "error", "skipped"):
                        totals[k] += stats[k]
                    if completed % 50 == 0 or completed == len(nums):
                        elapsed = time.time() - t0
                        rate = completed / elapsed * 60 if elapsed else 0
                        log.info(
                            f"  Progression {completed}/{len(nums)} "
                            f"({rate:.0f} ent/min) — dernier : {num}"
                        )
                except Exception as exc:
                    log.error(f"[CBSO] {num} : échec worker — {exc}")

    elapsed = time.time() - t0
    log.info(f"\nRésultat global : {totals} — {elapsed/60:.1f} min")
    return totals


def run(
    collection: str = "auto",
    limit: int | None = None,
    resume: bool = False,
    enterprise: str | None = None,
    csv_start_year: int = CSV_START_YEAR,
    workers: int = 3,
    sleep_csv: float = 0.3,
    skip_done: bool = True,
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
        workers=workers,
        sleep_csv=sleep_csv,
        skip_done=skip_done,
    )
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraping CBSO hôtellerie 2021+")
    parser.add_argument("--collection", default="auto",
                        choices=["auto", "enterprise_finale", "enterprise_silver", "enterprises"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--enterprise", default=None)
    parser.add_argument("--csv-start-year", type=int, default=CSV_START_YEAR)
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallélisme (défaut 3 = 3 proxies Tor)")
    parser.add_argument("--sleep-csv", type=float, default=0.3,
                        help="Pause entre CSV (défaut 0.3s)")
    parser.add_argument("--no-skip-done", action="store_true",
                        help="Retraiter les entreprises déjà meta=done")
    args = parser.parse_args()
    run(
        collection=args.collection,
        limit=args.limit,
        resume=args.resume,
        enterprise=args.enterprise,
        csv_start_year=args.csv_start_year,
        workers=args.workers,
        sleep_csv=args.sleep_csv,
        skip_done=not args.no_skip_done,
    )
