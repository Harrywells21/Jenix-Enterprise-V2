import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
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
import Sidebar    from "./components/Sidebar";

function Protected({ children }) {
  const { token } = useAuth();
  return token ? children : <Navigate to="/login" replace />;
}

function Layout({ children }) {
  return (
    <div style={{ display:"flex", height:"100vh",
                  overflow:"hidden", background:"#0d0d1a" }}>
      <Sidebar />
      <main style={{ flex:1, overflowY:"auto", padding:"28px" }}>
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/welcome"  element={<Landing />} />
          <Route path="/login"    element={<Login />} />
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
  );
}
