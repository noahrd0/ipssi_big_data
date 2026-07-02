"""
ingestion_dag.py
----------------
DAG Airflow — couche d'ingestion Bronze.

Flux :
  MongoDB → HDFS Bronze

Sources :
  - CBSO/NBB  : PDFs et CSVs des comptes annuels
  - eJustice  : publications (JSON)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models.param import Param

log = logging.getLogger(__name__)

HDFS_URL    = "http://namenode:9870"
HDFS_USER   = "airflow"
HDFS_BRONZE = "/data/bronze"


@dag(
    dag_id="enterprise_ingestion",
    description="Ingestion Bronze — CBSO / eJustice → HDFS",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=10,
    default_args={
        "retries":                   2,
        "retry_delay":               timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    tags=["ingestion", "bronze", "layer-1"],
    params={
        "enterprise_number": Param(
            default="",
            type="string",
            description="Numéro BCE ciblé (vide = batch MongoDB)",
        ),
        "sector": Param(
            default="",
            type="string",
            description="Secteur ciblé : 'hotel' ou vide (toutes actives)",
        ),
        "start_year": Param(default=2020, type="integer", description="Année min PDF (legacy)"),
        "pdf_start_year": Param(default=2000, type="integer"),
        "csv_start_year": Param(default=2021, type="integer"),
        "sources": Param(
            default=["cbso", "ejustice"],
            type="array",
            description="Sources à ingérer",
        ),
        "batch_size": Param(
            default=500,
            type="integer",
            description="Entreprises traitées par batch MongoDB",
        ),
        "mongo_skip": Param(
            default=0,
            type="integer",
            description="Offset MongoDB pour distribuer les runs parallèles",
        ),
    },
)
def enterprise_ingestion():

    @task(task_id="resolve_enterprises")
    def resolve_enterprises(**context) -> list[str]:
        from db.mongo_client import get_db
        from filters.hotel import get_hotel_enterprises

        params = context["params"]
        num    = params.get("enterprise_number", "").strip()
        sector = params.get("sector", "").strip().lower()

        if num:
            log.info(f"Mode ciblé : {num}")
            return [num]

        if sector == "hotel":
            db = get_db()
            nums = get_hotel_enterprises(db)
            batch = params["batch_size"]
            skip  = params.get("mongo_skip", 0)
            nums  = nums[skip: skip + batch]
            log.info(f"Mode hôtellerie : {len(nums)} entreprises")
            return nums

        db    = get_db()
        batch = params["batch_size"]
        skip  = params.get("mongo_skip", 0)
        nums  = [
            doc["enterprise_number"]
            for doc in db.enterprises.find(
                {"status": "AC"},
                {"enterprise_number": 1},
                skip=skip,
                limit=batch,
            )
        ]
        log.info(f"Mode bulk : {len(nums)} entreprises actives depuis MongoDB")
        return nums

    @task(task_id="ingest_cbso")
    def ingest_cbso(enterprise_numbers: list[str], **context) -> dict:
        import time
        from hdfs import InsecureClient
        from db.state_db import is_done, mark_done, mark_error, mark_in_progress, mark_enterprise_done, count_done_filings
        from scrapers.cbso_scraper import (
            fetch_deposit_list, filter_deposits,
            CBSO_DOC_BASE,
        )
        from scrapers.tor_session import get_with_rotation

        if "cbso" not in context["params"]["sources"]:
            log.info("[CBSO] Source désactivée — skip")
            return {}

        hdfs           = InsecureClient(HDFS_URL, user=HDFS_USER)
        params         = context["params"]
        pdf_start_year = params.get("pdf_start_year") or params.get("start_year", 2000)
        csv_start_year = params.get("csv_start_year", 2021)
        results        = {"done": 0, "error": 0, "skipped": 0}

        for num in enterprise_numbers:
            log.info(f"\n[CBSO] {num}")
            mark_in_progress(num, "cbso")
            try:
                deposits  = fetch_deposit_list(num)
                par_annee = filter_deposits(deposits)
            except Exception as exc:
                log.error(f"[CBSO] {num} : fetch échoué — {exc}")
                continue

            for annee, depot in sorted(par_annee.items()):
                an  = int(annee) if annee.isdigit() else 0
                did = depot["id"]
                ref = depot.get("reference", did[:8])

                for file_type, min_year, url_fn in [
                    ("pdf", pdf_start_year, lambda d: f"{CBSO_DOC_BASE}/pdf/{d}"),
                    ("csv", csv_start_year, lambda d: f"{CBSO_DOC_BASE}/consult/csv/{d}"),
                ]:
                    if an < min_year:
                        continue
                    if file_type == "csv" and depot.get("migration"):
                        continue

                    if is_done(num, "cbso", did, file_type):
                        results["skipped"] += 1
                        continue

                    ext = "pdf" if file_type == "pdf" else "csv"
                    if file_type == "csv":
                        hdfs_path = f"{HDFS_BRONZE}/{num}/nbb/{annee}/{ref}.csv"
                    else:
                        hdfs_path = f"{HDFS_BRONZE}/{num}/cbso/{file_type}s/{annee}.{ext}"
                    time.sleep(1)

                    try:
                        extra = {"Accept": "text/csv,application/octet-stream,*/*"} if file_type == "csv" else {}
                        resp = get_with_rotation(url_fn(did), timeout=60, extra_headers=extra)

                        if resp.status_code == 200 and len(resp.content) > 500:
                            parent = hdfs_path.rsplit("/", 1)[0]
                            hdfs.makedirs(parent)
                            with hdfs.write(hdfs_path, overwrite=True) as f:
                                f.write(resp.content)
                            mark_done(num, "cbso", did, file_type, hdfs_path, len(resp.content), year=an)
                            results["done"] += 1
                        else:
                            mark_error(num, "cbso", did, file_type,
                                       f"HTTP {resp.status_code} / taille {len(resp.content)}")
                            results["error"] += 1

                    except Exception as exc:
                        mark_error(num, "cbso", did, file_type, str(exc))
                        results["error"] += 1

            mark_enterprise_done(num, "cbso", count_done_filings(num, "cbso"))
            time.sleep(1)

        log.info(f"[CBSO] Résultat : {results}")
        return results

    @task(task_id="ingest_ejustice")
    def ingest_ejustice(enterprise_numbers: list[str], **context) -> dict:
        import json, time
        from hdfs import InsecureClient
        from db.state_db import is_done, mark_done, mark_error
        from scrapers.ejustice_scraper import fetch_publications

        if "ejustice" not in context["params"]["sources"]:
            log.info("[eJustice] Source désactivée — skip")
            return {}

        hdfs    = InsecureClient(HDFS_URL, user=HDFS_USER)
        results = {"done": 0, "skipped": 0, "error": 0}

        for num in enterprise_numbers:
            log.info(f"\n[eJustice] {num}")
            deposit_id = f"ejustice_{num}"

            if is_done(num, "ejustice", deposit_id, "json"):
                log.info("  Déjà ingéré — skip")
                results["skipped"] += 1
                continue

            try:
                pubs      = fetch_publications(num, lang="fr")
                payload   = json.dumps(pubs, ensure_ascii=False, indent=2).encode()
                hdfs_path = f"{HDFS_BRONZE}/{num}/ejustice/publications.json"

                hdfs.makedirs(f"{HDFS_BRONZE}/{num}/ejustice")
                with hdfs.write(hdfs_path, overwrite=True) as f:
                    f.write(payload)

                mark_done(num, "ejustice", deposit_id, "json", hdfs_path, len(payload))
                results["done"] += 1

            except Exception as exc:
                mark_error(num, "ejustice", deposit_id, "json", str(exc))
                results["error"] += 1

            time.sleep(1)

        log.info(f"[eJustice] Résultat : {results}")
        return results

    @task(task_id="ingestion_report")
    def ingestion_report(
        enterprise_numbers: list[str],
        cbso_result: dict,
        ejustice_result: dict,
    ) -> dict:
        from db.state_db import get_stats

        log.info("\n" + "=" * 60)
        log.info("RAPPORT INGESTION BRONZE")
        log.info(f"  Entreprises traitées : {len(enterprise_numbers)}")
        log.info(f"  CBSO     : {cbso_result}")
        log.info(f"  eJustice : {ejustice_result}")

        if enterprise_numbers:
            stats = get_stats(enterprise_numbers[0])
            log.info(f"\n  State DB ({enterprise_numbers[0]}) : {stats}")

        log.info("=" * 60)

        return {
            "enterprises": len(enterprise_numbers),
            "cbso":        cbso_result,
            "ejustice":    ejustice_result,
        }

    nums = resolve_enterprises()
    cbso = ingest_cbso(nums)
    ej   = ingest_ejustice(nums)
    ingestion_report(nums, cbso, ej)


enterprise_ingestion()
