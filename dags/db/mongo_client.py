"""
mongo_client.py
---------------
Connexion MongoDB partagée pour tous les DAGs et scrapers.

Utilisation :
    from db.mongo_client import get_db
    db = get_db()
    db.enterprises.find_one({"enterprise_number": "0878.065.378"})

Collections :
    enterprises          — entreprises belges (source : KBO CSV, aplati)
    enterprise_finale    — couche Bronze nested (KBO brut agrégé)
    enterprise_silver    — couche Silver (nettoyée / enrichie)
    download_state       — état de chaque fichier téléchargé (State DB)
"""

import os
from functools import lru_cache

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "belgique")


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


def get_db() -> Database:
    return get_client()[MONGO_DB]


def init_indexes() -> None:
    """
    Crée les index nécessaires (idempotent — safe à appeler plusieurs fois).
    À appeler une seule fois au démarrage (via init_mongodb.py).
    """
    db = get_db()

    # ── enterprises ──────────────────────────────────────────────────────────
    db.enterprises.create_index(
        [("enterprise_number", ASCENDING)], unique=True, name="idx_enterprise_number"
    )
    db.enterprises.create_index(
        [("status", ASCENDING)], name="idx_status"
    )
    db.enterprises.create_index(
        [("legal_form", ASCENDING)], name="idx_legal_form"
    )

    # ── download_state ────────────────────────────────────────────────────────
    # Index composite unique : (entreprise, source, deposit_id, file_type)
    db.download_state.create_index(
        [
            ("enterprise_number", ASCENDING),
            ("source",            ASCENDING),
            ("deposit_id",        ASCENDING),
            ("file_type",         ASCENDING),
        ],
        unique=True,
        name="idx_state_unique",
    )
    db.download_state.create_index(
        [("status", ASCENDING)], name="idx_state_status"
    )
    db.download_state.create_index(
        [("enterprise_number", ASCENDING), ("source", ASCENDING)],
        name="idx_state_enterprise_source",
    )
    db.download_state.create_index(
        [("downloaded_at", DESCENDING)], name="idx_state_date"
    )

    print("✓ Index MongoDB créés")


def init_silver_indexes() -> None:
    """Index pour enterprise_finale et enterprise_silver."""
    db = get_db()

    db.enterprise_finale.create_index(
        [("EnterpriseNumber", ASCENDING)], unique=True, name="idx_finale_number"
    )
    db.enterprise_finale.create_index(
        [("Status", ASCENDING)], name="idx_finale_status"
    )
    db.enterprise_finale.create_index(
        [("activities.NaceCode", ASCENDING)], name="idx_finale_nace"
    )

    db.enterprise_silver.create_index(
        [("EnterpriseNumber", ASCENDING)], unique=True, name="idx_silver_number"
    )
    db.enterprise_silver.create_index(
        [("Status", ASCENDING)], name="idx_silver_status"
    )
    db.enterprise_silver.create_index(
        [("JuridicalForm", ASCENDING)], name="idx_silver_juridical"
    )
    db.enterprise_silver.create_index(
        [("activities.NaceCode", ASCENDING)], name="idx_silver_nace"
    )

    print("✓ Index Silver créés")