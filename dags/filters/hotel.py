"""
hotel.py — filtre secteur hôtellerie sur enterprise_finale / enterprise_silver.
"""

from __future__ import annotations

from silver.kbo_codes import fmt_code

HOTEL_NACE_CODES = frozenset({
    "55100", "55201", "55202", "55203", "55204",
    "55209", "55300", "55400", "55900",
})

EXCLUDED_JURIDICAL_FORMS = frozenset({
    fmt_code(c, 3) for c in (
        "110", "114", "116", "117",
        "301", "302", "303",
        "310", "320", "330", "340", "350",
        "400", "411", "412", "413", "414", "415", "416", "417", "418", "419", "420",
    )
})

MAIN_CLASSIFICATIONS = frozenset({"MAIN", "001", "1"})


def _activity_nace(act: dict) -> str:
    return str(act.get("NaceCode") or act.get("nace_code") or "").strip()


def _activity_classif(act: dict) -> str:
    return str(act.get("Classification") or act.get("classification") or "").strip().upper()


def _is_main_activity(act: dict) -> bool:
    c = _activity_classif(act)
    return c in MAIN_CLASSIFICATIONS or fmt_code(c, 3) == "001"


def _has_hotel_main_activity(doc: dict) -> bool:
    for act in doc.get("activities", []):
        if _is_main_activity(act) and _activity_nace(act) in HOTEL_NACE_CODES:
            return True
    return False


def hotel_query() -> dict:
    """Requête MongoDB pour le secteur hôtellerie (enterprise_finale)."""
    return {
        "Status": "AC",
        "TypeOfEnterprise": {"$in": ["2", "002", 2]},
        "JuridicalForm": {"$nin": list(EXCLUDED_JURIDICAL_FORMS)},
        "activities": {
            "$elemMatch": {
                "Classification": {"$in": list(MAIN_CLASSIFICATIONS | {"001"})},
                "NaceCode": {"$in": list(HOTEL_NACE_CODES)},
            }
        },
    }


def hotel_query_silver() -> dict:
    """Requête MongoDB sur enterprise_silver."""
    return {
        "Status": "AC",
        "TypeOfEnterprise": {"$in": ["2", "002", "2"]},
        "JuridicalForm": {"$nin": list(EXCLUDED_JURIDICAL_FORMS)},
        "activities": {
            "$elemMatch": {
                "Classification": {"$in": list(MAIN_CLASSIFICATIONS | {"001"})},
                "NaceCode": {"$in": list(HOTEL_NACE_CODES)},
            }
        },
    }


def get_hotel_enterprises(db, collection: str = "auto") -> list[str]:
    """
    Retourne la liste des numéros BCE hôtellerie actifs (PM privées).
    """
    if collection == "auto":
        if db.enterprise_finale.count_documents({}) > 0:
            coll, field, query = db.enterprise_finale, "EnterpriseNumber", hotel_query()
        elif db.enterprise_silver.count_documents({}) > 0:
            coll, field, query = db.enterprise_silver, "EnterpriseNumber", hotel_query_silver()
        else:
            coll, field, query = db.enterprises, "enterprise_number", _enterprises_hotel_query()
    elif collection == "enterprise_finale":
        coll, field, query = db.enterprise_finale, "EnterpriseNumber", hotel_query()
    elif collection == "enterprise_silver":
        coll, field, query = db.enterprise_silver, "EnterpriseNumber", hotel_query_silver()
    else:
        coll, field, query = db.enterprises, "enterprise_number", _enterprises_hotel_query()

    if coll.name == "enterprises":
        nums = [
            doc["enterprise_number"]
            for doc in coll.find(
                {"status": "AC"},
                {"enterprise_number": 1, "activities": 1, "legal_form": 1, "type_of_enterprise": 1},
            )
            if _matches_hotel_flat(doc)
        ]
    else:
        nums = [doc[field] for doc in coll.find(query, {field: 1})]

    return sorted(set(nums))


def _enterprises_hotel_query() -> dict:
    return {"status": "AC"}


def _matches_hotel_flat(doc: dict) -> bool:
    jf = fmt_code(doc.get("legal_form", ""), 3)
    if jf in EXCLUDED_JURIDICAL_FORMS:
        return False
    type_ent = str(doc.get("type_of_enterprise", doc.get("TypeOfEnterprise", "2"))).strip()
    if type_ent not in ("2", "002", ""):
        return False
    return _has_hotel_main_activity(doc)
