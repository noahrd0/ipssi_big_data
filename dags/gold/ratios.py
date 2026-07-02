"""
ratios.py — calcul des ratios financiers par exercice.
"""

from __future__ import annotations


def _pct(num: float, denom: float) -> float | None:
    if not denom:
        return None
    return round(num / denom * 100, 2)


def compute_ratios(fields: dict) -> dict:
    ca = fields.get("ca") or 0.0
    achats = fields.get("achats") or 0.0
    variation = fields.get("variation_stocks") or 0.0
    resultat_net = fields.get("resultat_net") or 0.0
    fonds_propres = fields.get("fonds_propres") or 0.0
    tresorerie = fields.get("tresorerie") or 0.0
    dettes = fields.get("dettes_financieres") or 0.0

    marge_brute = ca - achats + variation

    return {
        "marge_brute": round(marge_brute, 2),
        "marge_nette_pct": _pct(resultat_net, ca),
        "roe_pct": _pct(resultat_net, fonds_propres),
        "ratio_liquidite": round(tresorerie / dettes, 4) if dettes else None,
        "taux_endettement_pct": _pct(dettes, fonds_propres),
    }


def build_year_record(year: int, fields: dict, schema_type: str) -> dict:
    ratios = compute_ratios(fields)
    return {
        "year": year,
        "ca": fields.get("ca"),
        "achats": fields.get("achats"),
        "variation_stocks": fields.get("variation_stocks"),
        "marge_brute": ratios["marge_brute"],
        "ebit": fields.get("ebit"),
        "resultat_net": fields.get("resultat_net"),
        "tresorerie": fields.get("tresorerie"),
        "dettes_financieres": fields.get("dettes_financieres"),
        "fonds_propres": fields.get("fonds_propres"),
        "capital_souscrit": fields.get("capital_souscrit"),
        "schema_type": schema_type,
        "ratios": {
            "marge_nette_pct": ratios["marge_nette_pct"],
            "roe_pct": ratios["roe_pct"],
            "ratio_liquidite": ratios["ratio_liquidite"],
            "taux_endettement_pct": ratios["taux_endettement_pct"],
        },
    }
