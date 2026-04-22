import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrandProvider }         from "./context/BrandContext";
import ErrorBoundary    from "./components/ErrorBoundary";
import MobileSidebar    from "./components/MobileSidebar";
import Landing    from "./pages/Landing";
import Login      from "./pages/Login";
import Fleet      from "./pages/Fleet";
import Overview   from "./pages/Overview";
import Machine    from "./pages/Machine";
import Reports    from "./pages/Reports";
import Users      from "./pages/Users";
import Settings   from "./pages/Settings";
import AuditPage  from "./pages/AuditPage";
import CVEScanner from "./pages/CVEScanner";
import Uptime     from "./pages/Uptime";
import WhiteLabel from "./pages/WhiteLabel";
import DemoScript from "./pages/DemoScript";
import Sidebar    from "./components/Sidebar";

function Protected({ children }) {
  const { token } = useAuth();
  return token ? children : <Navigate to="/login" replace />;
}

function Layout({ children }) {
  return (
    <div style={{
      display: "flex",
      height: "100vh",
      overflow: "hidden",
      background: "#060812",
      fontFamily: "'Cabinet Grotesk', sans-serif",
    }}>
      {/* Desktop sidebar */}
      <div className="desktop-sidebar">
        <Sidebar />
      </div>
      {/* Mobile sidebar */}
      <MobileSidebar />

      {/* Main content */}
      <main
        className="main-content"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "28px 32px",
          background: "#060812",
          /* Subtle grid pattern */
          backgroundImage: `
            linear-gradient(rgba(56,189,248,0.015) 1px, transparent 1px),
            linear-gradient(90deg, rgba(56,189,248,0.015) 1px, transparent 1px)
          `,
          backgroundSize: "80px 80px",
        }}
      >
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </main>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500;600&family=Cabinet+Grotesk:wght@300;400;500;600;700;800&display=swap');

        * { box-sizing: border-box; }

        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(56,189,248,0.15); border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(56,189,248,0.3); }

        ::selection { background: rgba(56,189,248,0.2); }

        @keyframes fadeIn  { from { opacity: 0; } to { opacity: 1; } }
        @keyframes fadeUp  { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse   { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes shimmer {
          0%   { background-position: -200% 0; }
          100% { background-position:  200% 0; }
        }

        @media (max-width: 800px) {
          .desktop-sidebar { display: none !important; }
          .main-content { padding: 16px !important; padding-top: 64px !important; }
        }
      `}</style>
    </div>
  );
}

export default function App() {
  return (
    <BrandProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/welcome" element={<Landing />} />
            <Route path="/login"   element={<Login />} />
            <Route path="/" element={
              <Protected><Layout><Fleet /></Layout></Protected>
            }/>
            <Route path="/overview" element={
              <Protected><Layout><Overview /></Layout></Protected>
            }/>
            <Route path="/machines/:id" element={
              <Protected><Layout><Machine /></Layout></Protected>
            }/>
            <Route path="/reports" element={
              <Protected><Layout><Reports /></Layout></Protected>
            }/>
            <Route path="/audit" element={
              <Protected><Layout><AuditPage /></Layout></Protected>
            }/>
            <Route path="/cve" element={
              <Protected><Layout><CVEScanner /></Layout></Protected>
            }/>
            <Route path="/uptime" element={
              <Protected><Layout><Uptime /></Layout></Protected>
            }/>
            <Route path="/whitelabel" element={
              <Protected><Layout><WhiteLabel /></Layout></Protected>
            }/>
            <Route path="/demo" element={
              <Protected><Layout><DemoScript /></Layout></Protected>
            }/>
            <Route path="/users" element={
              <Protected><Layout><Users /></Layout></Protected>
            }/>
            <Route path="/settings" element={
              <Protected><Layout><Settings /></Layout></Protected>
            }/>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </BrandProvider>
  );
}
