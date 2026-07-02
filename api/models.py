from pydantic import BaseModel


class SearchResult(BaseModel):
    enterprise_number: str
    name: str | None = None
    status: str | None = None
    juridical_form_label: str | None = None
    city: str | None = None
    nace_label: str | None = None


class EnterpriseListItem(BaseModel):
    enterprise_number: str
    name: str | None = None
    status: str | None = None
    juridical_form_label: str | None = None
    city: str | None = None
    nace_label: str | None = None
    schema_type: str | None = None
    latest_year: int | None = None
    ca: float | None = None
    resultat_net: float | None = None
    roe_pct: float | None = None
    marge_nette_pct: float | None = None
    filings_count: int = 0


class DashboardStats(BaseModel):
    total_hotels: int
    total_gold: int
    avg_ca: float | None = None
    avg_resultat_net: float | None = None
    schema_breakdown: dict[str, int]


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
