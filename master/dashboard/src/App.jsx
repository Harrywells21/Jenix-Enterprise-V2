import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import { ToastProvider } from "./components/Toast";
import Dashboard from "./pages/Dashboard";
import Automation from "./pages/Automation";
import Reports from "./pages/Reports";
import AuditLogs from "./pages/AuditLogs";
import Floors from "./pages/Floors";
import SystemHealth from "./pages/SystemHealth";
import Monitoring from "./pages/Monitoring";
import Signals from "./pages/Signals";
import Security from "./pages/Security";
import Settings from "./pages/Settings";
import "./theme/tokens.css";

function Layout({ children }) {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--bg-void)" }}>
      <Sidebar />
      <main style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/security" element={<Security />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/health" element={<SystemHealth />} />
            <Route path="/automation" element={<Automation />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/audit" element={<AuditLogs />} />
            <Route path="/floors" element={<Floors />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </ToastProvider>
  );
}
