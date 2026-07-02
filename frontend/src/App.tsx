import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import EnterprisePage from "./pages/EnterprisePage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/enterprise/:bce" element={<EnterprisePage />} />
      </Routes>
    </Layout>
  );
}
