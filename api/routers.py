from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.db import get_db
from api.models import EnterpriseDetail, SearchResult
from api.scrapers.kbopub import scrape_officers
from api.scrapers.notaire_stream import stream_statutes
from filters.hotel import hotel_query_silver

router = APIRouter()


def _display_name(silver: dict) -> str | None:
    for d in silver.get("denominations", []):
        if d.get("Denomination"):
            return d["Denomination"]
    return silver.get("name")


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
