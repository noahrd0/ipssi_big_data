"""
transform.py — Bronze (enterprise_finale) → Silver (enterprise_silver).
"""

from __future__ import annotations

from datetime import datetime, timezone

from silver.kbo_codes import DEFAULT_KBO_PATH, fmt_code, lookup, nace_category


def normalize_date(date_str: str | None) -> str | None:
    """DD-MM-YYYY → YYYY-MM-DD."""
    if not date_str or date_str in ("N/A", "nan", "None"):
        return None
    date_str = str(date_str).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _is_rego_address(addr: dict) -> bool:
    val = str(addr.get("TypeOfAddress", "")).strip().upper()
    code = fmt_code(addr.get("TypeOfAddress", ""), 3)
    return val in ("REGO", "001", "1") or code == "001"


def _dedupe_activities(activities: list[dict], kbo_path: str) -> list[dict]:
    seen: set[tuple] = set()
    result = []
    for act in activities:
        nace = str(act.get("NaceCode") or act.get("nace_code") or "").strip()
        classif = str(act.get("Classification") or act.get("classification") or "").strip()
        key = (nace, classif)
        if key in seen:
            continue
        seen.add(key)

        version = act.get("NaceVersion") or act.get("nace_version") or ""
        nace_cat = nace_category(version)
        silver_act = {
            "NaceCode":       nace,
            "NaceVersion":    str(version),
            "Classification": classif,
            "ActivityGroup":  fmt_code(act.get("ActivityGroup") or act.get("activity_group_code", ""), 3),
            "NaceLabel":      lookup(nace_cat, nace, kbo_path=kbo_path),
        }
        if act.get("activity_group_label"):
            silver_act["ActivityGroupLabel"] = act["activity_group_label"]
        else:
            silver_act["ActivityGroupLabel"] = lookup(
                "ActivityGroup", silver_act["ActivityGroup"], kbo_path=kbo_path
            )
        result.append(silver_act)
    return result


def _sort_denominations(denoms: list[dict]) -> list[dict]:
    def sort_key(d: dict) -> tuple:
        type_code = fmt_code(d.get("TypeOfDenomination", ""), 3)
        lang = str(d.get("Language", "")).strip()
        is_official = 0 if type_code == "001" else 1
        is_fr = 0 if lang in ("1", "001", "FR") else 1
        return (is_official, is_fr)

    return sorted(denoms, key=sort_key)


def _flat_to_nested(doc: dict) -> dict:
    """Convertit un document 'enterprises' aplati en structure nested."""
    num = doc.get("enterprise_number") or doc.get("EnterpriseNumber")
    nested = {
        "EnterpriseNumber":   num,
        "Status":             doc.get("status") or doc.get("Status"),
        "JuridicalForm":      doc.get("legal_form") or doc.get("JuridicalForm"),
        "StartDate":          doc.get("start_date") or doc.get("StartDate"),
        "TypeOfEnterprise":   doc.get("type_of_enterprise") or doc.get("TypeOfEnterprise"),
        "JuridicalSituation": doc.get("juridical_situation") or doc.get("JuridicalSituation"),
    }
    if doc.get("name"):
        nested["denominations"] = [{
            "Denomination":       doc["name"],
            "TypeOfDenomination": "001",
            "Language":           "1",
        }]
    else:
        nested["denominations"] = doc.get("denominations", [])

    if any(doc.get(k) for k in ("zip", "street_fr", "city_fr")):
        nested["addresses"] = [{
            "TypeOfAddress":  "001",
            "Zipcode":        doc.get("zip"),
            "StreetFR":       doc.get("street_fr"),
            "StreetNL":       doc.get("street_nl"),
            "MunicipalityFR": doc.get("city_fr"),
            "MunicipalityNL": doc.get("city_nl"),
            "HouseNumber":    doc.get("house_number"),
        }]
    else:
        nested["addresses"] = doc.get("addresses", [])

    acts = doc.get("activities", [])
    nested["activities"] = [
        {
            "NaceCode":       a.get("nace_code") or a.get("NaceCode"),
            "NaceVersion":    a.get("nace_version") or a.get("NaceVersion"),
            "Classification": a.get("classification") or a.get("Classification"),
            "ActivityGroup":  a.get("activity_group_code") or a.get("ActivityGroup"),
        }
        for a in acts
    ]
    nested["contacts"] = doc.get("contacts", [])
    nested["establishments"] = doc.get("establishments", [])
    return nested


def bronze_to_silver(doc: dict, kbo_path: str = DEFAULT_KBO_PATH) -> dict:
    """
    Transforme un document Bronze en document Silver.
    Ne modifie pas le document source.
    """
    if "EnterpriseNumber" not in doc and "enterprise_number" in doc:
        src = _flat_to_nested(doc)
    else:
        src = doc

    num = src.get("EnterpriseNumber") or src.get("enterprise_number")
    jf = fmt_code(src.get("JuridicalForm", ""), 3)
    status = str(src.get("Status", "")).strip()

    silver: dict = {
        "EnterpriseNumber":   num,
        "Status":             status,
        "StatusLabel":        lookup("Status", status, kbo_path=kbo_path),
        "JuridicalForm":      jf,
        "JuridicalFormLabel": lookup("JuridicalForm", jf, kbo_path=kbo_path),
        "TypeOfEnterprise":   str(src.get("TypeOfEnterprise", "")).strip(),
        "JuridicalSituation": fmt_code(src.get("JuridicalSituation", ""), 3),
        "StartDate":          normalize_date(src.get("StartDate")),
        "StartDate_raw":      src.get("StartDate"),
        "updated_at_silver":  datetime.now(timezone.utc).isoformat(),
    }

    addrs = src.get("addresses", [])
    rego = [a for a in addrs if _is_rego_address(a)]
    silver["address"] = rego[0] if rego else (addrs[0] if addrs else None)

    denoms = src.get("denominations", [])
    silver["denominations"] = _sort_denominations(denoms) if denoms else []

    silver["activities"] = _dedupe_activities(src.get("activities", []), kbo_path)

    ests = src.get("establishments", [])
    silver["establishments"] = [
        {**e, "start_date": normalize_date(e.get("start_date") or e.get("StartDate"))}
        for e in ests
    ]

    for field in ("telephone", "email", "website", "name"):
        if src.get(field):
            silver[field] = src[field]

    silver["contacts"] = src.get("contacts", [])
    return silver
