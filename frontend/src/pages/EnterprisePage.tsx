import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  EnterpriseDetail,
  getDirigeants,
  getEnterprise,
  streamStatuts,
  YearData,
} from "../api";
import RatiosTable from "../components/RatiosTable";
import SankeyChart from "../components/SankeyChart";

export default function EnterprisePage() {
  const { bce } = useParams<{ bce: string }>();
  const [data, setData] = useState<EnterpriseDetail | null>(null);
  const [officers, setOfficers] = useState<Array<{ nom: string; qualites: string[] }>>([]);
  const [statuts, setStatuts] = useState<Record<string, unknown>[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!bce) return;
    getEnterprise(bce)
      .then((d) => {
        setData(d);
        const years = d.gold?.years || [];
        if (years.length) setSelectedYear(years[years.length - 1].year);
      })
      .catch((e) => setError(e.message));

    getDirigeants(bce)
      .then((d) => setOfficers(d.officers || []))
      .catch(() => {});
  }, [bce]);

  const loadStatuts = () => {
    if (!bce) return;
    setStreaming(true);
    setStatuts([]);
    streamStatuts(
      bce,
      (doc) => setStatuts((prev) => [...prev, doc]),
      () => setStreaming(false),
      (msg) => {
        setError(msg);
        setStreaming(false);
      },
    );
  };

  if (!bce) return null;
  if (error && !data) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Chargement...</p>;

  const silver = data.silver;
  const years: YearData[] = data.gold?.years || [];
  const yearData = years.find((y) => y.year === selectedYear);

  const name =
    (silver.denominations as Array<{ Denomination?: string }>)?.[0]?.Denomination ||
    (silver.name as string) ||
    bce;

  return (
    <div className="page">
      <Link to="/" className="back">← Retour</Link>
      <h1>{name}</h1>
      <p className="muted">{bce} — {silver.JuridicalFormLabel as string} — {silver.StatusLabel as string}</p>

      {silver.address && (
        <p>
          {(silver.address as { Street?: string; Zipcode?: string; City?: string }).Street}{" "}
          {(silver.address as { Zipcode?: string }).Zipcode}{" "}
          {(silver.address as { City?: string }).City}
        </p>
      )}

      <section>
        <h2>Activités NACE</h2>
        <ul>
          {(silver.activities as Array<{ NaceCode?: string; NaceLabel?: string }>)?.map((a, i) => (
            <li key={i}>{a.NaceCode} — {a.NaceLabel}</li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Dirigeants</h2>
        {officers.length === 0 ? (
          <p className="muted">Aucun dirigeant</p>
        ) : (
          <ul>
            {officers.map((o) => (
              <li key={o.nom}>{o.nom} — {o.qualites.join(", ")}</li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Ratios financiers</h2>
        {years.length > 0 && (
          <div className="year-select">
            <label>Exercice : </label>
            <select
              value={selectedYear ?? ""}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
            >
              {years.map((y) => (
                <option key={y.year} value={y.year}>{y.year}</option>
              ))}
            </select>
          </div>
        )}
        {yearData && <SankeyChart year={yearData} />}
        <RatiosTable years={years} />
      </section>

      <section>
        <h2>Statuts notaire</h2>
        <button onClick={loadStatuts} disabled={streaming}>
          {streaming ? "Chargement..." : "Charger les statuts"}
        </button>
        {streaming && <div className="spinner" />}
        <ul className="statuts">
          {statuts.map((s, i) => (
            <li key={i}>
              {(s.deed_date as string) || "—"} — {(s.document_id as string)}
              {s.hdfs_path && <span className="muted"> ({s.hdfs_path as string})</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
