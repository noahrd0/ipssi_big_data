import { useCallback, useEffect, useState } from "react";
import {
  DashboardStats,
  EnterpriseListItem,
  getDashboardStats,
  listEnterprises,
} from "../api";
import EnterpriseTable from "../components/EnterpriseTable";
import KpiCards from "../components/KpiCards";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [items, setItems] = useState<EnterpriseListItem[]>([]);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [hasGold, setHasGold] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, list] = await Promise.all([
        getDashboardStats(),
        listEnterprises({ q: query, page, page_size: 50, has_gold: hasGold }),
      ]);
      setStats(s);
      setItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [query, page, hasGold]);

  useEffect(() => {
    const t = setTimeout(load, query ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, query]);

  return (
    <div className="dashboard-page">
      <KpiCards stats={stats} loading={loading && !stats} />

      <div className="toolbar">
        <div className="search-wrap">
          <span className="search-icon">⌕</span>
          <input
            className="search-input"
            placeholder="Rechercher par nom, BCE ou ville..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1); }}
          />
        </div>
        <label className="filter-toggle">
          <input
            type="checkbox"
            checked={hasGold}
            onChange={(e) => { setHasGold(e.target.checked); setPage(1); }}
          />
          Avec ratios Gold uniquement
        </label>
      </div>

      {error && <div className="alert error">{error}</div>}

      <EnterpriseTable items={items} loading={loading} />

      <div className="pagination">
        <button disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
          ← Précédent
        </button>
        <span>Page {page}</span>
        <button
          disabled={items.length < 50 || loading}
          onClick={() => setPage((p) => p + 1)}
        >
          Suivant →
        </button>
      </div>
    </div>
  );
}
