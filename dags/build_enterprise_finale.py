"""
build_enterprise_finale.py
--------------------------
Peuple la collection enterprise_finale (Bronze nested) depuis les CSV KBO.
Ne modifie pas enterprise_finale existante en cas de re-run : upsert par EnterpriseNumber.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo import UpdateOne

from db.mongo_client import get_db, init_silver_indexes
from init_mongodb import (
    BATCH_SIZE,
    CHUNK_SIZE,
    DEFAULT_KBO_PATH,
    _load_csv_full,
    format_num_vec,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _records_from_df(df: pd.DataFrame, entity_col: str = "EntityNumber", label: str = "") -> dict[str, list]:
    """Groupe les lignes CSV par numéro d'entreprise formaté."""
    if df.empty:
        log.info(f"  {label or 'CSV'} : vide — skip")
        return {}
    col = "enterprise_number" if "enterprise_number" in df.columns else entity_col
    if col != "enterprise_number":
        df = df.copy()
        df["enterprise_number"] = format_num_vec(df[entity_col])
    log.info(f"  {label or 'CSV'} : {len(df):,} lignes — groupement par entreprise...")
    grouped: dict[str, list] = {}
    for num, grp in df.groupby("enterprise_number"):
        grouped[num] = grp.drop(columns=["enterprise_number"], errors="ignore").to_dict("records")
    log.info(f"  {label or 'CSV'} : {len(grouped):,} entreprises")
    return grouped


def _load_csv_filtered_verbose(
    path: Path,
    entity_col: str,
    known_nums: set,
    label: str,
) -> pd.DataFrame:
    """Lit un CSV en chunks avec logs de progression."""
    chunks = []
    chunk_no = 0
    rows_kept = 0
    try:
        for chunk in pd.read_csv(path, dtype=str, chunksize=CHUNK_SIZE):
            chunk_no += 1
            chunk["enterprise_number"] = format_num_vec(chunk[entity_col])
            filtered = chunk[chunk["enterprise_number"].isin(known_nums)]
            if not filtered.empty:
                chunks.append(filtered)
                rows_kept += len(filtered)
            if chunk_no % 5 == 0:
                log.info(f"  {label} : chunk {chunk_no} lu ({rows_kept:,} lignes gardées)")
    except FileNotFoundError:
        log.warning(f"  Fichier introuvable : {path.name}")
        return pd.DataFrame()

    log.info(f"  {label} : terminé — {chunk_no} chunks, {rows_kept:,} lignes")
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def _load_and_group(path: Path, entity_col: str, known_nums: set, label: str) -> dict[str, list]:
    log.info(f"Chargement {label} ({path.name})...")
    df = _load_csv_filtered_verbose(path, entity_col, known_nums, label)
    return _records_from_df(df, entity_col, label=label)


def build_enterprise_finale(kbo_path: str = DEFAULT_KBO_PATH, limit: int | None = None) -> int:
    p = Path(kbo_path)
    log.info(f"Construction enterprise_finale depuis {p}")

    log.info("Chargement enterprise.csv...")
    df_ent = _load_csv_full(p / "enterprise.csv")
    if df_ent.empty:
        raise FileNotFoundError(f"enterprise.csv introuvable dans {p}")

    df_ent["enterprise_number"] = format_num_vec(df_ent["EnterpriseNumber"])
    known_nums = set(df_ent["enterprise_number"])
    log.info(f"  enterprise.csv : {len(df_ent):,} entreprises")
    if limit:
        known_nums = set(list(known_nums)[:limit])
        df_ent = df_ent[df_ent["enterprise_number"].isin(known_nums)]
        log.info(f"  Mode test : limité à {len(known_nums):,} entreprises")

    denoms   = _load_and_group(p / "denomination.csv", "EntityNumber", known_nums, "denomination")
    addrs    = _load_and_group(p / "address.csv", "EntityNumber", known_nums, "address")
    acts     = _load_and_group(p / "activity.csv", "EntityNumber", known_nums, "activity")
    contacts = _load_and_group(p / "contact.csv", "EntityNumber", known_nums, "contact")

    log.info("Chargement establishment.csv...")
    df_est = _load_csv_filtered_verbose(p / "establishment.csv", "EnterpriseNumber", known_nums, "establishment")
    if not df_est.empty:
        df_est = df_est.rename(columns={"EstablishmentNumber": "EstablishmentNumber"})
        df_est["EstablishmentNumber"] = format_num_vec(df_est["EstablishmentNumber"])
    ests = _records_from_df(df_est, "EnterpriseNumber", label="establishment") if not df_est.empty else {}

    log.info(f"Écriture MongoDB ({len(df_ent):,} documents nested)...")
    db = get_db()
    now = datetime.now(timezone.utc)
    ops: list[UpdateOne] = []
    count = 0

    for _, row in df_ent.iterrows():
        num = row["enterprise_number"]
        doc = {
            "EnterpriseNumber":   num,
            "Status":             row.get("Status"),
            "JuridicalForm":      row.get("JuridicalForm"),
            "JuridicalSituation": row.get("JuridicalSituation"),
            "TypeOfEnterprise":   row.get("TypeOfEnterprise"),
            "StartDate":          row.get("StartDate"),
            "denominations":      denoms.get(num, []),
            "addresses":          addrs.get(num, []),
            "activities":         acts.get(num, []),
            "contacts":           contacts.get(num, []),
            "establishments":     ests.get(num, []),
            "updated_at":         now,
        }
        ops.append(UpdateOne(
            {"EnterpriseNumber": num},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
        count += 1

        if len(ops) >= BATCH_SIZE:
            db.enterprise_finale.bulk_write(ops, ordered=False)
            log.info(f"  {count:,} entreprises traitées")
            ops = []

    if ops:
        db.enterprise_finale.bulk_write(ops, ordered=False)

    total = db.enterprise_finale.count_documents({})
    log.info(f"✓ enterprise_finale : {total:,} documents")
    return total


def run(kbo_path: str = DEFAULT_KBO_PATH, limit: int | None = None) -> None:
    init_silver_indexes()
    build_enterprise_finale(kbo_path, limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MongoDB enterprise_finale (Bronze nested)")
    parser.add_argument("--kbo-path", default=DEFAULT_KBO_PATH)
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nombre d'entreprises (test)")
    args = parser.parse_args()
    run(args.kbo_path, limit=args.limit)
