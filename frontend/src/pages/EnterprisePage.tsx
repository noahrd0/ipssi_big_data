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
  if (error && !data) return <div className="alert error">{error}</div>;
  if (!data) return <div className="loading-state">Chargement de la fiche...</div>;

  const silver = data.silver;
  const years: YearData[] = data.gold?.years || [];
  const yearData = years.find((y) => y.year === selectedYear);
  const addr = silver.address as { Street?: string; Zipcode?: string; City?: string } | undefined;

  const name =
    (silver.denominations as Array<{ Denomination?: string }>)?.[0]?.Denomination ||
    (silver.name as string) ||
    bce;

  return (
    <div className="detail-page">
      <Link to="/" className="back-link">← Retour au dashboard</Link>

      <div className="detail-hero">
        <div>
          <h2>{name}</h2>
          <p className="hero-meta">
            <span className="mono">{bce}</span>
            <span className="dot">·</span>
            {silver.JuridicalFormLabel as string}
            <span className="dot">·</span>
            <span className="status-badge">{silver.StatusLabel as string}</span>
          </p>
          {addr && (
            <p className="hero-address">
              {addr.Street}, {addr.Zipcode} {addr.City}
            </p>
          )}
        </div>
        {data.gold?.schema_type && (
          <span className={`schema schema-${data.gold.schema_type}`}>
            {data.gold.schema_type}
          </span>
        )}
      </div>

      <div className="detail-grid">
        <div className="card">
          <h3>Activités NACE</h3>
          <ul className="info-list">
            {(silver.activities as Array<{ NaceCode?: string; NaceLabel?: string }>)?.map((a, i) => (
              <li key={i}>
                <span className="tag">{a.NaceCode}</span>
                {a.NaceLabel}
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h3>Dirigeants</h3>
          {officers.length === 0 ? (
            <p className="muted">Aucun dirigeant enregistré</p>
          ) : (
            <ul className="info-list">
              {officers.map((o) => (
                <li key={o.nom}>
                  <strong>{o.nom}</strong>
                  <small>{o.qualites.join(", ")}</small>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card card-wide">
        <div className="card-header">
          <h3>Ratios financiers</h3>
          {years.length > 0 && (
            <select
              className="year-select-input"
              value={selectedYear ?? ""}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
            >
              {years.map((y) => (
                <option key={y.year} value={y.year}>Exercice {y.year}</option>
              ))}
            </select>
          )}
        </div>
        {yearData ? (
          <SankeyChart year={yearData} />
        ) : (
          <p className="muted">Aucune donnée Gold — lancez build_gold.py</p>
        )}
        <RatiosTable years={years} />
      </div>

      <div className="card card-wide">
        <div className="card-header">
          <h3>Statuts notaire</h3>
          <button className="btn-primary" onClick={loadStatuts} disabled={streaming}>
            {streaming ? "Streaming..." : "Charger via SSE"}
          </button>
        </div>
        {streaming && <div className="spinner" />}
        <ul className="statuts-list">
          {statuts.map((s, i) => (
            <li key={i} className="statut-item">
              <span className="statut-date">{(s.deed_date as string) || "—"}</span>
              <span className="mono">{(s.document_id as string)?.slice(0, 12)}…</span>
              {s.hdfs_path && <span className="muted">PDF stocké</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
