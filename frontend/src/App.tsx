import { Route, Routes } from "react-router-dom";
import EnterprisePage from "./pages/EnterprisePage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  return (
    <div className="app">
      <header>
        <h2>BCE Hôtellerie — Gold Layer</h2>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/enterprise/:bce" element={<EnterprisePage />} />
        </Routes>
      </main>
    </div>
  );
}
