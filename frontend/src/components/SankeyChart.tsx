import { YearData } from "../api";

interface Props {
  year: YearData;
}

export default function SankeyChart({ year }: Props) {
  const ca = year.ca || 0;
  const marge = year.marge_brute || 0;
  const net = year.resultat_net || 0;
  const max = Math.max(ca, 1);

  const h1 = Math.max((ca / max) * 120, 8);
  const h2 = Math.max((marge / max) * 120, 8);
  const h3 = Math.max((Math.abs(net) / max) * 120, 8);

  return (
    <div className="sankey">
      <h3>Sankey compte de résultats — {year.year}</h3>
      <svg viewBox="0 0 520 160" className="sankey-svg">
        <rect x="20" y={80 - h1 / 2} width="80" height={h1} fill="#4f86f7" rx="4" />
        <text x="60" y="150" textAnchor="middle" fontSize="11">CA</text>
        <text x="60" y={75 - h1 / 2} textAnchor="middle" fontSize="10">{ca.toLocaleString("fr-BE")}</text>

        <path d={`M 100 ${80} C 160 ${80}, 160 ${80 - h2 / 2 + h2 / 2}, 220 ${80}`} fill="none" stroke="#94a3b8" strokeWidth={Math.max(h1 * 0.4, 4)} opacity="0.5" />
        <rect x="220" y={80 - h2 / 2} width="80" height={h2} fill="#22c55e" rx="4" />
        <text x="260" y="150" textAnchor="middle" fontSize="11">Marge brute</text>
        <text x="260" y={75 - h2 / 2} textAnchor="middle" fontSize="10">{marge.toLocaleString("fr-BE")}</text>

        <path d={`M 300 ${80} C 360 ${80}, 360 ${80 - h3 / 2 + h3 / 2}, 420 ${80}`} fill="none" stroke="#94a3b8" strokeWidth={Math.max(h2 * 0.4, 4)} opacity="0.5" />
        <rect x="420" y={80 - h3 / 2} width="80" height={h3} fill={net >= 0 ? "#a855f7" : "#ef4444"} rx="4" />
        <text x="460" y="150" textAnchor="middle" fontSize="11">Résultat net</text>
        <text x="460" y={75 - h3 / 2} textAnchor="middle" fontSize="10">{net.toLocaleString("fr-BE")}</text>
      </svg>
    </div>
  );
}
