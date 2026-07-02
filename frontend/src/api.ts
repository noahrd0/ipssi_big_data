const API_BASE = import.meta.env.VITE_API_URL || "";

export interface SearchResult {
  enterprise_number: string;
  name?: string;
  status?: string;
  juridical_form_label?: string;
  city?: string;
  nace_label?: string;
}

export interface DashboardStats {
  total_hotels: number;
  total_gold: number;
  avg_ca: number | null;
  avg_resultat_net: number | null;
  schema_breakdown: Record<string, number>;
}

export interface EnterpriseListItem {
  enterprise_number: string;
  name?: string;
  status?: string;
  juridical_form_label?: string;
  city?: string;
  nace_label?: string;
  schema_type?: string;
  latest_year?: number;
  ca?: number;
  resultat_net?: number;
  roe_pct?: number;
  marge_nette_pct?: number;
  filings_count: number;
}

export interface YearData {
  year: number;
  ca?: number;
  marge_brute?: number;
  ebit?: number;
  resultat_net?: number;
  tresorerie?: number;
  dettes_financieres?: number;
  fonds_propres?: number;
  capital_souscrit?: number;
  ratios?: {
    marge_nette_pct?: number;
    roe_pct?: number;
    ratio_liquidite?: number;
    taux_endettement_pct?: number;
  };
}

export interface EnterpriseDetail {
  enterprise_number: string;
  silver: Record<string, unknown>;
  gold?: {
    years: YearData[];
    schema_type?: string;
  };
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const res = await fetch(`${API_BASE}/api/dashboard/stats`);
  if (!res.ok) throw new Error("Stats indisponibles");
  return res.json();
}

export async function listEnterprises(opts: {
  q?: string;
  page?: number;
  page_size?: number;
  has_gold?: boolean;
}): Promise<EnterpriseListItem[]> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.page) params.set("page", String(opts.page));
  if (opts.page_size) params.set("page_size", String(opts.page_size));
  if (opts.has_gold) params.set("has_gold", "true");
  const res = await fetch(`${API_BASE}/api/enterprises?${params}`);
  if (!res.ok) throw new Error("Liste entreprises échouée");
  return res.json();
}

export async function searchEnterprises(q: string): Promise<SearchResult[]> {
  const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error("Recherche échouée");
  return res.json();
}

export async function getEnterprise(bce: string): Promise<EnterpriseDetail> {
  const res = await fetch(`${API_BASE}/api/enterprise/${encodeURIComponent(bce)}`);
  if (!res.ok) throw new Error("Entreprise introuvable");
  return res.json();
}

export async function getDirigeants(bce: string) {
  const res = await fetch(`${API_BASE}/api/enterprise/${encodeURIComponent(bce)}/dirigeants`);
  if (!res.ok) throw new Error("Dirigeants indisponibles");
  return res.json();
}

export function streamStatuts(
  bce: string,
  onStatute: (doc: Record<string, unknown>) => void,
  onDone: (info: Record<string, unknown>) => void,
  onError: (msg: string) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/api/enterprise/${encodeURIComponent(bce)}/statuts/stream`);

  es.addEventListener("statute", (e) => {
    onStatute(JSON.parse(e.data));
  });
  es.addEventListener("done", (e) => {
    onDone(JSON.parse(e.data));
    es.close();
  });
  es.addEventListener("error", (e) => {
    if (e instanceof MessageEvent && e.data) {
      const data = JSON.parse(e.data);
      onError(data.message || "Erreur SSE");
    }
    es.close();
  });
  es.onerror = () => {
    onError("Connexion SSE interrompue");
    es.close();
  };

  return () => es.close();
}
