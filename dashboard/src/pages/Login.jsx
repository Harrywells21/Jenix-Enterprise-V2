import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [email,    setEmail]    = useState("admin@jenix.io");
  const [password, setPassword] = useState("admin123");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const { loginSuccess } = useAuth();
  const navigate         = useNavigate();

  const handleLogin = async () => {
    setLoading(true); setError("");
    try {
      const res = await login(email, password);
      loginSuccess(res.data.access_token, {
        name: res.data.name, role: res.data.role
      });
      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight:"100vh", background:"#0d0d1a",
      display:"flex", alignItems:"center", justifyContent:"center"
    }}>
      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"12px", padding:"40px", width:"380px"
      }}>
        <div style={{ textAlign:"center", marginBottom:"32px" }}>
          <div style={{ color:"#00bcd4", fontSize:"32px",
                        fontWeight:800, letterSpacing:"2px" }}>JENIX</div>
          <div style={{ color:"#666", fontSize:"13px", marginTop:"4px" }}>
            Enterprise Management Platform
          </div>
        </div>

        {[
          { label:"Email",    value:email,    set:setEmail,    type:"email"    },
          { label:"Password", value:password, set:setPassword, type:"password" },
        ].map(({ label, value, set, type }) => (
          <div key={label} style={{ marginBottom:"16px" }}>
            <label style={{ color:"#aaa", fontSize:"12px",
                            display:"block", marginBottom:"6px" }}>
              {label}
            </label>
            <input type={type} value={value}
              onChange={e => set(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleLogin()}
              style={{
                width:"100%", padding:"10px 14px",
                background:"#1a1a2e", border:"1px solid #2a2a3e",
                borderRadius:"8px", color:"#e0e0e0",
                fontSize:"14px", outline:"none"
              }}
            />
          </div>
        ))}

        {error && (
          <div style={{ color:"#f44336", fontSize:"13px",
                        marginBottom:"12px", textAlign:"center" }}>
            {error}
          </div>
        )}

        <button onClick={handleLogin} disabled={loading} style={{
          width:"100%", padding:"12px",
          background: loading ? "#1a1a2e" : "#00bcd4",
          color:      loading ? "#666"    : "#000",
          border:"none", borderRadius:"8px",
          fontWeight:700, fontSize:"15px",
          cursor: loading ? "not-allowed" : "pointer"
        }}>
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </div>
    </div>
  );
}
