import { DashboardStats } from "../api";

interface Props {
  stats: DashboardStats | null;
  loading: boolean;
}

function fmt(n: number | null | undefined, suffix = "") {
  if (n == null) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M${suffix}`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)} k${suffix}`;
  return `${n.toLocaleString("fr-BE", { maximumFractionDigits: 0 })}${suffix}`;
}

export default function KpiCards({ stats, loading }: Props) {
  if (loading || !stats) {
    return (
      <div className="kpi-grid">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="kpi-card skeleton" />
        ))}
      </div>
    );
  }

  const coverage = stats.total_hotels
    ? Math.round((stats.total_gold / stats.total_hotels) * 100)
    : 0;

  return (
    <div className="kpi-grid">
      <div className="kpi-card">
        <span className="kpi-label">Hôtels actifs</span>
        <span className="kpi-value">{stats.total_hotels.toLocaleString("fr-BE")}</span>
        <span className="kpi-hint">Filtre NACE hôtellerie</span>
      </div>
      <div className="kpi-card accent-blue">
        <span className="kpi-label">Couche Gold</span>
        <span className="kpi-value">{stats.total_gold.toLocaleString("fr-BE")}</span>
        <span className="kpi-hint">{coverage}% couverture ratios</span>
      </div>
      <div className="kpi-card accent-green">
        <span className="kpi-label">CA moyen (dernier ex.)</span>
        <span className="kpi-value">{fmt(stats.avg_ca, " €")}</span>
        <span className="kpi-hint">Code PCMN 70</span>
      </div>
      <div className="kpi-card accent-purple">
        <span className="kpi-label">Résultat net moyen</span>
        <span className="kpi-value">{fmt(stats.avg_resultat_net, " €")}</span>
        <span className="kpi-hint">
          full {stats.schema_breakdown.full || 0} · abrégé {stats.schema_breakdown.abrege || 0} · micro {stats.schema_breakdown.micro || 0}
        </span>
      </div>
    </div>
  );
}
