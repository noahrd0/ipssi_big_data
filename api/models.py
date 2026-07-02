from pydantic import BaseModel


class SearchResult(BaseModel):
    enterprise_number: str
    name: str | None = None
    status: str | None = None
    juridical_form_label: str | None = None


class Officer(BaseModel):
    nom: str
    qualites: list[str]


class YearRatios(BaseModel):
    marge_nette_pct: float | None = None
    roe_pct: float | None = None
    ratio_liquidite: float | None = None
    taux_endettement_pct: float | None = None


class YearData(BaseModel):
    year: int
    ca: float | None = None
    marge_brute: float | None = None
    ebit: float | None = None
    resultat_net: float | None = None
    tresorerie: float | None = None
    dettes_financieres: float | None = None
    fonds_propres: float | None = None
    capital_souscrit: float | None = None
    ratios: YearRatios | None = None


class EnterpriseDetail(BaseModel):
    enterprise_number: str
    silver: dict
    gold: dict | None = None


class StatuteDoc(BaseModel):
    document_id: str
    deed_date: str | None = None
    document_status: str | None = None
    hdfs_path: str | None = None
    raw: dict | None = None
