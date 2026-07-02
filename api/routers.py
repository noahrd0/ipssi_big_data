from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.db import get_db
from api.models import DashboardStats, EnterpriseDetail, EnterpriseListItem, SearchResult
from api.scrapers.kbopub import scrape_officers
from api.scrapers.notaire_stream import stream_statutes
from filters.hotel import hotel_query_silver

router = APIRouter()


def _display_name(silver: dict) -> str | None:
    for d in silver.get("denominations", []):
        if d.get("Denomination"):
            return d["Denomination"]
    return silver.get("name")


def _city(silver: dict) -> str | None:
    addr = silver.get("address") or {}
    return addr.get("City") or addr.get("city")


def _main_nace(silver: dict) -> str | None:
    for act in silver.get("activities", []):
        if act.get("NaceLabel"):
            return f"{act.get('NaceCode', '')} — {act['NaceLabel']}"
    return None


def _latest_gold_metrics(gold: dict | None) -> dict:
    if not gold or not gold.get("years"):
        return {}
    latest = max(gold["years"], key=lambda y: y.get("year", 0))
    ratios = latest.get("ratios") or {}
    return {
        "latest_year": latest.get("year"),
        "ca": latest.get("ca"),
        "resultat_net": latest.get("resultat_net"),
        "roe_pct": ratios.get("roe_pct"),
        "marge_nette_pct": ratios.get("marge_nette_pct"),
        "filings_count": len(gold["years"]),
        "schema_type": gold.get("schema_type"),
    }


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats():
    db = get_db()
    hotel_q = hotel_query_silver()
    total_hotels = db.enterprise_silver.count_documents(hotel_q)
    total_gold = db.hotel_gold.count_documents({})

    schema_breakdown: dict[str, int] = {"full": 0, "abrege": 0, "micro": 0}
    cas, nets = [], []
    for doc in db.hotel_gold.find({}, {"years": 1, "schema_type": 1}):
        st = doc.get("schema_type") or "abrege"
        schema_breakdown[st] = schema_breakdown.get(st, 0) + 1
        if not doc.get("years"):
            continue
        latest = max(doc["years"], key=lambda y: y.get("year", 0))
        if latest.get("ca"):
            cas.append(latest["ca"])
        if latest.get("resultat_net") is not None:
            nets.append(latest["resultat_net"])

    def _avg(vals: list) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    return DashboardStats(
        total_hotels=total_hotels,
        total_gold=total_gold,
        avg_ca=_avg(cas),
        avg_resultat_net=_avg(nets),
        schema_breakdown=schema_breakdown,
    )


@router.get("/enterprises", response_model=list[EnterpriseListItem])
def list_enterprises(
    q: str = Query("", min_length=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    has_gold: bool = Query(False),
):
    db = get_db()
    match = hotel_query_silver()
    if q and len(q) >= 2:
        regex = {"$regex": q, "$options": "i"}
        match["$or"] = [
            {"EnterpriseNumber": regex},
            {"denominations.Denomination": regex},
            {"name": regex},
            {"address.City": regex},
        ]

    pipeline: list[dict] = [
        {"$match": match},
        {"$lookup": {
            "from": "hotel_gold",
            "localField": "EnterpriseNumber",
            "foreignField": "enterprise_number",
            "as": "_gold",
        }},
        {"$addFields": {"_gold": {"$arrayElemAt": ["$_gold", 0]}}},
    ]
    if has_gold:
        pipeline.append({"$match": {"_gold": {"$ne": None}}})

    pipeline += [
        {"$sort": {"denominations.Denomination": 1, "EnterpriseNumber": 1}},
        {"$skip": (page - 1) * page_size},
        {"$limit": page_size},
    ]

    items = []
    for doc in db.enterprise_silver.aggregate(pipeline):
        gold = doc.get("_gold")
        metrics = _latest_gold_metrics(gold)
        items.append(EnterpriseListItem(
            enterprise_number=doc.get("EnterpriseNumber", ""),
            name=_display_name(doc),
            status=doc.get("StatusLabel") or doc.get("Status"),
            juridical_form_label=doc.get("JuridicalFormLabel"),
            city=_city(doc),
            nace_label=_main_nace(doc),
            schema_type=metrics.get("schema_type"),
            latest_year=metrics.get("latest_year"),
            ca=metrics.get("ca"),
            resultat_net=metrics.get("resultat_net"),
            roe_pct=metrics.get("roe_pct"),
            marge_nette_pct=metrics.get("marge_nette_pct"),
            filings_count=metrics.get("filings_count", 0),
        ))
    return items


@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query(..., min_length=2), limit: int = Query(20, le=50)):
    db = get_db()
    query = hotel_query_silver()
    regex = {"$regex": q, "$options": "i"}

    or_clauses = [
        {"EnterpriseNumber": regex},
        {"denominations.Denomination": regex},
        {"name": regex},
    ]
    q_clean = q.replace(".", "").strip()
    if q_clean.isdigit():
        or_clauses.append({"EnterpriseNumber": {"$regex": q_clean}})

    query["$or"] = or_clauses

    results = []
    for doc in db.enterprise_silver.find(query, limit=limit):
        results.append(SearchResult(
            enterprise_number=doc.get("EnterpriseNumber", ""),
            name=_display_name(doc),
            status=doc.get("StatusLabel") or doc.get("Status"),
            juridical_form_label=doc.get("JuridicalFormLabel"),
            city=_city(doc),
            nace_label=_main_nace(doc),
        ))
    return results


@router.get("/enterprise/{enterprise_number}", response_model=EnterpriseDetail)
def get_enterprise(enterprise_number: str):
    db = get_db()
    silver = db.enterprise_silver.find_one(
        {"EnterpriseNumber": enterprise_number},
        {"_id": 0},
    )
    if not silver:
        raise HTTPException(404, "Entreprise introuvable")

    gold = db.hotel_gold.find_one(
        {"enterprise_number": enterprise_number},
        {"_id": 0},
    )
    return EnterpriseDetail(
        enterprise_number=enterprise_number,
        silver=silver,
        gold=gold,
    )


@router.get("/enterprise/{enterprise_number}/dirigeants")
def get_dirigeants(enterprise_number: str):
    db = get_db()
    cached = db.enterprise_officers.find_one(
        {"enterprise_number": enterprise_number},
        {"_id": 0, "officers": 1},
    )
    if cached:
        return {"enterprise_number": enterprise_number, "officers": cached["officers"], "cached": True}

    try:
        officers = scrape_officers(enterprise_number)
    except Exception as exc:
        raise HTTPException(502, f"Scrape kbopub échoué : {exc}") from exc

    db.enterprise_officers.update_one(
        {"enterprise_number": enterprise_number},
        {"$set": {
            "enterprise_number": enterprise_number,
            "officers": officers,
        }},
        upsert=True,
    )
    return {"enterprise_number": enterprise_number, "officers": officers, "cached": False}


@router.get("/enterprise/{enterprise_number}/statuts")
def list_statuts(enterprise_number: str):
    db = get_db()
    docs = list(db.notaire_statutes.find(
        {"enterprise_number": enterprise_number},
        {"_id": 0},
    ))
    return {"enterprise_number": enterprise_number, "statutes": docs, "count": len(docs)}


@router.get("/enterprise/{enterprise_number}/statuts/stream")
async def stream_statuts_endpoint(enterprise_number: str):
    return StreamingResponse(
        stream_statutes(enterprise_number),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
