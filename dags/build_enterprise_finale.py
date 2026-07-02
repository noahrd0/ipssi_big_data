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
    _load_csv_filtered,
    _load_csv_full,
    format_num_vec,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _records_from_df(df: pd.DataFrame, entity_col: str = "EntityNumber") -> dict[str, list]:
    """Groupe les lignes CSV par numéro d'entreprise formaté."""
    if df.empty:
        return {}
    col = "enterprise_number" if "enterprise_number" in df.columns else entity_col
    if col != "enterprise_number":
        df = df.copy()
        df["enterprise_number"] = format_num_vec(df[entity_col])
    grouped: dict[str, list] = {}
    for num, grp in df.groupby("enterprise_number"):
        grouped[num] = grp.drop(columns=["enterprise_number"], errors="ignore").to_dict("records")
    return grouped


def build_enterprise_finale(kbo_path: str = DEFAULT_KBO_PATH, limit: int | None = None) -> int:
    p = Path(kbo_path)
    log.info(f"Construction enterprise_finale depuis {p}")

    df_ent = _load_csv_full(p / "enterprise.csv")
    if df_ent.empty:
        raise FileNotFoundError(f"enterprise.csv introuvable dans {p}")

    df_ent["enterprise_number"] = format_num_vec(df_ent["EnterpriseNumber"])
    known_nums = set(df_ent["enterprise_number"])
    if limit:
        known_nums = set(list(known_nums)[:limit])
        df_ent = df_ent[df_ent["enterprise_number"].isin(known_nums)]

    denoms  = _records_from_df(_load_csv_filtered(p / "denomination.csv", "EntityNumber", known_nums))
    addrs   = _records_from_df(_load_csv_filtered(p / "address.csv", "EntityNumber", known_nums))
    acts    = _records_from_df(_load_csv_filtered(p / "activity.csv", "EntityNumber", known_nums))
    contacts = _records_from_df(_load_csv_filtered(p / "contact.csv", "EntityNumber", known_nums))

    df_est = _load_csv_filtered(p / "establishment.csv", "EnterpriseNumber", known_nums)
    if not df_est.empty:
        df_est = df_est.rename(columns={"EstablishmentNumber": "EstablishmentNumber"})
        df_est["EstablishmentNumber"] = format_num_vec(df_est["EstablishmentNumber"])
    ests = _records_from_df(df_est, "EnterpriseNumber") if not df_est.empty else {}

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
