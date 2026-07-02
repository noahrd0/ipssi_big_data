"""
kbo_codes.py — référentiel de traduction des codes KBO (code.csv).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

_DEFAULT_KBO = Path(__file__).resolve().parent.parent.parent / "data" / "kbo"
DEFAULT_KBO_PATH = os.getenv("KBO_PATH", str(_DEFAULT_KBO))


def fmt_code(val, width: int = 3) -> str:
    """Normalise un code KBO (14.0 → '014')."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        return str(int(float(val))).zfill(width) if width else str(int(float(val)))
    except (ValueError, TypeError):
        return str(val).strip()


@lru_cache(maxsize=1)
def _load_codes(kbo_path: str) -> pd.DataFrame:
    path = Path(kbo_path) / "code.csv"
    if not path.exists():
        return pd.DataFrame(columns=["Category", "Code", "Language", "Description"])
    return pd.read_csv(path, dtype=str, low_memory=False)


def lookup(category: str, code_val: str, lang: str = "FR", kbo_path: str = DEFAULT_KBO_PATH) -> str:
    """Traduit un code KBO en libellé lisible."""
    if not code_val or code_val == "N/A":
        return str(code_val)

    df = _load_codes(kbo_path)
    if df.empty:
        return str(code_val)

    code_str = fmt_code(code_val, 0) if category.startswith("Nace") else fmt_code(code_val, 3)
    if category.startswith("Nace"):
        code_str = str(code_val).strip()

    for try_lang in (lang, "FR", "1"):
        res = df[
            (df["Category"] == category)
            & (df["Code"].astype(str).str.strip() == code_str)
            & (df["Language"].astype(str).str.strip().isin([try_lang, fmt_code(try_lang, 0)]))
        ]
        if not res.empty:
            return res.iloc[0]["Description"]

    return str(code_val)


def nace_category(version: str | float) -> str:
    """'2025.0' → 'Nace2025'."""
    try:
        return f"Nace{int(float(version))}"
    except (ValueError, TypeError):
        return "Nace2008"
