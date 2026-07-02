import { YearData } from "../api";

interface Props {
  years: YearData[];
}

function fmt(v: number | undefined | null) {
  if (v == null) return "—";
  return v.toLocaleString("fr-BE", { maximumFractionDigits: 2 });
}

export default function RatiosTable({ years }: Props) {
  if (!years.length) return <p className="muted">Aucun ratio disponible</p>;

  return (
    <table className="ratios-table">
      <thead>
        <tr>
          <th>Année</th>
          <th>CA</th>
          <th>Marge brute</th>
          <th>EBIT</th>
          <th>Résultat net</th>
          <th>Marge nette %</th>
          <th>ROE %</th>
          <th>Liquidité</th>
          <th>Endettement %</th>
        </tr>
      </thead>
      <tbody>
        {years.map((y) => (
          <tr key={y.year}>
            <td>{y.year}</td>
            <td>{fmt(y.ca)}</td>
            <td>{fmt(y.marge_brute)}</td>
            <td>{fmt(y.ebit)}</td>
            <td>{fmt(y.resultat_net)}</td>
            <td>{fmt(y.ratios?.marge_nette_pct)}</td>
            <td>{fmt(y.ratios?.roe_pct)}</td>
            <td>{fmt(y.ratios?.ratio_liquidite)}</td>
            <td>{fmt(y.ratios?.taux_endettement_pct)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
