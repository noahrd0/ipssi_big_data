import { Link, useLocation } from "react-router-dom";

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const isHome = pathname === "/";

  return (
    <div className="dashboard">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-icon">◆</span>
          <div>
            <strong>BCE Analytics</strong>
            <small>Secteur Hôtellerie</small>
          </div>
        </div>
        <nav className="sidebar-nav">
          <Link to="/" className={isHome ? "active" : ""}>
            <span className="nav-icon">▣</span> Dashboard
          </Link>
        </nav>
        <div className="sidebar-footer">
          <small>Gold Layer · MongoDB + HDFS</small>
        </div>
      </aside>
      <div className="main-area">
        {isHome && (
          <header className="topbar">
            <div>
              <h1>Tableau de bord</h1>
              <p className="topbar-sub">Analyse financière des établissements hôteliers belges</p>
            </div>
          </header>
        )}
        <main className={`content ${isHome ? "" : "content-flush"}`}>{children}</main>
      </div>
    </div>
  );
}
