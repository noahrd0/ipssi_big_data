import { Link } from "react-router-dom";
import { EnterpriseListItem } from "../api";

interface Props {
  items: EnterpriseListItem[];
  loading: boolean;
}

function fmtEuro(v: number | null | undefined) {
  if (v == null || v === 0) return "—";
  return v.toLocaleString("fr-BE", { maximumFractionDigits: 0 }) + " €";
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v.toFixed(1)} %`;
}

export default function EnterpriseTable({ items, loading }: Props) {
  if (loading) {
    return <div className="table-card skeleton" style={{ height: 400 }} />;
  }

  return (
    <div className="table-card">
      <div className="table-header">
        <h2>Entreprises</h2>
        <span className="badge">{items.length} affichées</span>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Entreprise</th>
              <th>BCE</th>
              <th>Ville</th>
              <th>Forme</th>
              <th>Exercice</th>
              <th>CA</th>
              <th>Résultat net</th>
              <th>ROE</th>
              <th>Marge nette</th>
              <th>Schéma</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={10} className="empty-row">Aucune entreprise trouvée</td>
              </tr>
            ) : (
              items.map((e) => (
                <tr key={e.enterprise_number}>
                  <td>
                    <Link to={`/enterprise/${e.enterprise_number}`} className="ent-link">
                      <strong>{e.name || "—"}</strong>
                      {e.nace_label && <small>{e.nace_label.split("—")[0]?.trim()}</small>}
                    </Link>
                  </td>
                  <td className="mono">{e.enterprise_number}</td>
                  <td>{e.city || "—"}</td>
                  <td><span className="tag">{e.juridical_form_label || "—"}</span></td>
                  <td>{e.latest_year || "—"}</td>
                  <td className="num">{fmtEuro(e.ca)}</td>
                  <td className={`num ${(e.resultat_net ?? 0) < 0 ? "neg" : "pos"}`}>
                    {fmtEuro(e.resultat_net)}
                  </td>
                  <td className="num">{fmtPct(e.roe_pct)}</td>
                  <td className="num">{fmtPct(e.marge_nette_pct)}</td>
                  <td>
                    {e.schema_type ? (
                      <span className={`schema schema-${e.schema_type}`}>{e.schema_type}</span>
                    ) : (
                      <span className="schema schema-none">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
