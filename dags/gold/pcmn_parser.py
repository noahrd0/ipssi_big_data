"""
pcmn_parser.py — parse les CSV NBB (codes PCMN + montants).
Format réel : CSV comma-separated, métadonnées en tête puis paires code/valeur.
Ex. "9904","56257.38"
"""

from __future__ import annotations

import csv
import io
import re


def _norm_code(raw: str) -> str:
    return str(raw).strip().strip('"')


def _to_float(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip().strip('"').replace(",", ".")
    if not s or s in ("-", "nan", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


_PCMN_RE = re.compile(
    r"^(\d{1,4}([/]\d{1,4})*([A-Z]P?)?|\d{2,4}[A-Z]?P?)$"
)


def _is_pcmn_code(key: str) -> bool:
    if not key or " " in key:
        return False
    if key.lower().startswith("entity") or key.lower().startswith("accounting"):
        return False
    return bool(_PCMN_RE.match(key)) or key.replace("/", "").replace("P", "").isdigit()


def parse_pcmn_csv(content: str | bytes) -> dict[str, float]:
    """
    Lit un CSV NBB et retourne {code_pcmn: montant}.
    Ignore les lignes de métadonnées (libellés avec espaces).
    """
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content

    codes: dict[str, float] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        key = _norm_code(row[0])
        if not _is_pcmn_code(key):
            continue
        codes[key] = _to_float(row[1])
    return codes


def _sum_codes(codes: dict[str, float], keys: list[str]) -> float:
    return sum(codes.get(k, 0.0) for k in keys)


def _sum_range(codes: dict[str, float], start: int, end: int) -> float:
    return sum(codes.get(str(i), 0.0) for i in range(start, end + 1))


def _sum_slash_code(codes: dict[str, float], slash_key: str) -> float:
    if slash_key in codes:
        return codes[slash_key]
    m = re.match(r"^(\d+)/(\d+)$", slash_key)
    if not m:
        return codes.get(slash_key, 0.0)
    a, b = int(m.group(1)), int(m.group(2))
    return _sum_range(codes, a, b)


def extract_fields(codes: dict[str, float]) -> dict:
    """Extrait les champs métier depuis les codes PCMN."""
    ca = codes.get("70", 0.0)
    achats = codes.get("60", 0.0)
    variation = codes.get("71", 0.0)
    ebit = codes.get("9901", 0.0)
    resultat_net = codes.get("9904", 0.0)

    tresorerie = (
        _sum_codes(codes, ["54", "55"])
        or _sum_slash_code(codes, "54/58")
        or codes.get("54/55", 0.0)
    )
    dettes = _sum_codes(codes, ["17", "43"]) or _sum_slash_code(codes, "17/49")
    fonds_propres = (
        _sum_range(codes, 10, 15)
        or _sum_slash_code(codes, "10/15")
        or _sum_slash_code(codes, "10/49")
    )
    capital = codes.get("100", 0.0)

    return {
        "ca": ca,
        "achats": achats,
        "variation_stocks": variation,
        "ebit": ebit,
        "resultat_net": resultat_net,
        "tresorerie": tresorerie,
        "dettes_financieres": dettes,
        "fonds_propres": fonds_propres,
        "capital_souscrit": capital,
    }


def detect_schema_type(codes: dict[str, float]) -> str:
    """Déduit full / abrege / micro selon la richesse des codes."""
    key_codes = {"70", "60", "9901", "9904", "100"}
    present = sum(1 for k in key_codes if k in codes and codes[k] != 0)
    total_lines = len([v for v in codes.values() if v != 0])
    if total_lines <= 8 or present <= 1:
        return "micro"
    if present >= 4 and total_lines >= 15:
        return "full"
    return "abrege"
