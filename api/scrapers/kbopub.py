"""
kbopub.py — scrape dirigeants depuis kbopub.economie.fgov.be
"""

from __future__ import annotations

import re
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html"

EXCLUSIONS = {
    "Numéro d'entreprise", "Statut", "Adresse du siège",
    "Date de début", "Dénomination", "Forme juridique",
}


def scrape_officers(enterprise_number: str) -> list[dict]:
    num = enterprise_number.replace(".", "")
    url = f"{BASE_URL}?ondernemingsnummer={num}&lang=fr"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    dirigeants_raw: list[dict] = []

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        role = tds[0].get_text(strip=True).rstrip(":")
        nom = re.sub(r"\s*Depuis.*", "", tds[1].get_text(strip=True)).strip()
        if role and nom:
            dirigeants_raw.append({"nom": nom, "qualite": role})

    par_nom: dict[str, list[str]] = defaultdict(list)
    for d in dirigeants_raw:
        if d["qualite"] not in EXCLUSIONS and d["nom"] not in EXCLUSIONS:
            par_nom[d["nom"]].append(d["qualite"])

    return [{"nom": nom, "qualites": qualites} for nom, qualites in par_nom.items()]
