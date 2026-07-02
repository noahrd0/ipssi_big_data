import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { AppDispatch, RootState } from "../store";
import { fetchSearch, setQuery } from "../store/searchSlice";

export default function SearchPage() {
  const dispatch = useDispatch<AppDispatch>();
  const { query, results, loading, error } = useSelector((s: RootState) => s.search);
  const [input, setInput] = useState(query);

  useEffect(() => {
    if (input.length < 2) return;
    const t = setTimeout(() => {
      dispatch(setQuery(input));
      dispatch(fetchSearch(input));
    }, 300);
    return () => clearTimeout(t);
  }, [input, dispatch]);

  return (
    <div className="page">
      <h1>Recherche hôtellerie</h1>
      <input
        className="search-input"
        placeholder="Nom ou numéro BCE..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      {loading && <p className="muted">Recherche...</p>}
      {error && <p className="error">{error}</p>}
      <ul className="results">
        {results.map((r) => (
          <li key={r.enterprise_number}>
            <Link to={`/enterprise/${r.enterprise_number}`}>
              <strong>{r.name || r.enterprise_number}</strong>
              <span>{r.enterprise_number}</span>
              <span className="muted">{r.juridical_form_label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
