const API_BASE = import.meta.env.VITE_API_URL || "";

export interface SearchResult {
  enterprise_number: string;
  name?: string;
  status?: string;
  juridical_form_label?: string;
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
