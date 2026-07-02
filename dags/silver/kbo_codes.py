"""
kbo_codes.py — référentiel de traduction des codes KBO (code.csv).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_DEFAULT_KBO = Path(__file__).resolve().parent.parent.parent / "data" / "kbo"
DEFAULT_KBO_PATH = os.getenv("KBO_PATH", str(_DEFAULT_KBO))

# (category, code, language) → description
LookupKey = tuple[str, str, str]


def fmt_code(val, width: int = 3) -> str:
    """Normalise un code KBO (14.0 → '014')."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        return str(int(float(val))).zfill(width) if width else str(int(float(val)))
    except (ValueError, TypeError):
        return str(val).strip()


@lru_cache(maxsize=4)
def _load_codes(kbo_path: str) -> pd.DataFrame:
    path = Path(kbo_path) / "code.csv"
    if not path.exists():
        return pd.DataFrame(columns=["Category", "Code", "Language", "Description"])
    return pd.read_csv(path, dtype=str, low_memory=False)


@lru_cache(maxsize=4)
def _lookup_cache(kbo_path: str) -> dict[LookupKey, str]:
    """Construit un index O(1) une seule fois par chemin KBO."""
    df = _load_codes(kbo_path)
    cache: dict[LookupKey, str] = {}
    if df.empty:
        return cache

    for _, row in df.iterrows():
        cat  = str(row.get("Category", "")).strip()
        code = str(row.get("Code", "")).strip()
        lang = str(row.get("Language", "")).strip()
        desc = row.get("Description", "")
        if not cat or not code:
            continue

        cache[(cat, code, lang)] = desc

        if not cat.startswith("Nace"):
            padded = fmt_code(code, 3)
            cache[(cat, padded, lang)] = desc

        lang_padded = fmt_code(lang, 0) if lang.isdigit() or lang.replace(".", "").isdigit() else lang
        cache[(cat, code, lang_padded)] = desc
        if not cat.startswith("Nace"):
            cache[(cat, fmt_code(code, 3), lang_padded)] = desc

    return cache


def warm_cache(kbo_path: str = DEFAULT_KBO_PATH) -> int:
    """Précharge code.csv en mémoire. Retourne le nombre d'entrées."""
    cache = _lookup_cache(kbo_path)
    log.info(f"Cache code.csv : {len(cache):,} entrées")
    return len(cache)


def lookup(category: str, code_val: str, lang: str = "FR", kbo_path: str = DEFAULT_KBO_PATH) -> str:
    """Traduit un code KBO en libellé lisible (lookup O(1))."""
    if not code_val or code_val == "N/A":
        return str(code_val)

    cache = _lookup_cache(kbo_path)
    if not cache:
        return str(code_val)

    if category.startswith("Nace"):
        code_str = str(code_val).strip()
    else:
        code_str = fmt_code(code_val, 3)

    for try_lang in (lang, "FR", "1", fmt_code(lang, 0) if lang else "FR"):
        try_lang = str(try_lang).strip()
        hit = cache.get((category, code_str, try_lang))
        if hit:
            return hit
        if not category.startswith("Nace"):
            hit = cache.get((category, str(code_val).strip(), try_lang))
            if hit:
                return hit

    return str(code_val)


def nace_category(version: str | float) -> str:
    """'2025.0' → 'Nace2025'."""
    try:
        return f"Nace{int(float(version))}"
    except (ValueError, TypeError):
        return "Nace2008"
