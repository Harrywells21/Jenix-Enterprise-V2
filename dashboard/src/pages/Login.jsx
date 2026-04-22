import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [email,    setEmail]    = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [mounted,  setMounted]  = useState(false);
  const { loginSuccess } = useAuth();
  const navigate = useNavigate();

  useEffect(() => { setMounted(true); }, []);

  const handleLogin = async () => {
    setLoading(true); setError("");
    try {
      const res = await login(email, password);
      loginSuccess(res.data.token, { name: res.data.username, role: res.data.role });
      navigate("/");
    } catch {
      setError("Invalid credentials. Please try again.");
    } finally { setLoading(false); }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "#060812",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "'Cabinet Grotesk', sans-serif",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Animated grid background */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `
          linear-gradient(rgba(56,189,248,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(56,189,248,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "60px 60px",
        maskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black, transparent)",
      }}/>

      {/* Glow orbs */}
      <div style={{
        position: "absolute", top: "20%", left: "15%",
        width: "500px", height: "500px", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(56,189,248,0.06) 0%, transparent 70%)",
        pointerEvents: "none",
      }}/>
      <div style={{
        position: "absolute", bottom: "10%", right: "10%",
        width: "400px", height: "400px", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(139,92,246,0.05) 0%, transparent 70%)",
        pointerEvents: "none",
      }}/>

      {/* Scanline effect */}
      <div style={{
        position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none",
      }}>
        <div style={{
          position: "absolute", left: 0, right: 0, height: "2px",
          background: "linear-gradient(90deg, transparent, rgba(56,189,248,0.3), transparent)",
          animation: "scanline 8s linear infinite",
        }}/>
      </div>

      {/* Login card */}
      <div style={{
        width: "420px",
        background: "rgba(11, 18, 32, 0.9)",
        border: "1px solid rgba(56,189,248,0.15)",
        borderRadius: "20px",
        padding: "48px",
        boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 60px rgba(56,189,248,0.05), inset 0 1px 0 rgba(255,255,255,0.05)",
        backdropFilter: "blur(20px)",
        opacity: mounted ? 1 : 0,
        transform: mounted ? "translateY(0)" : "translateY(24px)",
        transition: "opacity 0.6s cubic-bezier(0.16,1,0.3,1), transform 0.6s cubic-bezier(0.16,1,0.3,1)",
        position: "relative",
      }}>
        {/* Top accent line */}
        <div style={{
          position: "absolute", top: 0, left: "40px", right: "40px", height: "1px",
          background: "linear-gradient(90deg, transparent, rgba(56,189,248,0.6), transparent)",
        }}/>

        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "12px", marginBottom: "8px" }}>
            {/* Hexagon logo mark */}
            <div style={{
              width: "40px", height: "40px",
              background: "linear-gradient(135deg, #38bdf8, #8b5cf6)",
              clipPath: "polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <span style={{ color: "#000", fontSize: "14px", fontWeight: 800, fontFamily: "'Syne', sans-serif" }}>J</span>
            </div>
            <span style={{
              fontFamily: "'Syne', sans-serif",
              fontSize: "28px", fontWeight: 800,
              letterSpacing: "0.08em",
              background: "linear-gradient(135deg, #38bdf8 0%, #e8f0fe 60%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}>JENIX</span>
          </div>
          <div style={{
            color: "rgba(122,143,166,0.8)", fontSize: "11px",
            letterSpacing: "0.2em", textTransform: "uppercase",
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            Enterprise Intelligence Platform
          </div>
        </div>

        {/* Form */}
        <div style={{ marginBottom: "16px" }}>
          <label style={{
            display: "block", fontSize: "11px", fontWeight: 600,
            color: "rgba(122,143,166,0.8)", letterSpacing: "0.12em",
            textTransform: "uppercase", marginBottom: "8px",
            fontFamily: "'JetBrains Mono', monospace",
          }}>Email</label>
          <input
            type="text" value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleLogin()}
            style={{
              width: "100%", padding: "12px 16px",
              background: "rgba(14,25,41,0.8)",
              border: "1px solid rgba(56,189,248,0.15)",
              borderRadius: "10px", color: "#e8f0fe",
              fontSize: "14px", outline: "none",
              fontFamily: "'Cabinet Grotesk', sans-serif",
              transition: "border-color 0.2s, box-shadow 0.2s",
            }}
            onFocus={e => {
              e.target.style.borderColor = "rgba(56,189,248,0.5)";
              e.target.style.boxShadow = "0 0 0 3px rgba(56,189,248,0.08)";
            }}
            onBlur={e => {
              e.target.style.borderColor = "rgba(56,189,248,0.15)";
              e.target.style.boxShadow = "none";
            }}
          />
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label style={{
            display: "block", fontSize: "11px", fontWeight: 600,
            color: "rgba(122,143,166,0.8)", letterSpacing: "0.12em",
            textTransform: "uppercase", marginBottom: "8px",
            fontFamily: "'JetBrains Mono', monospace",
          }}>Password</label>
          <input
            type="password" value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleLogin()}
            style={{
              width: "100%", padding: "12px 16px",
              background: "rgba(14,25,41,0.8)",
              border: "1px solid rgba(56,189,248,0.15)",
              borderRadius: "10px", color: "#e8f0fe",
              fontSize: "14px", outline: "none",
              fontFamily: "'Cabinet Grotesk', sans-serif",
              transition: "border-color 0.2s, box-shadow 0.2s",
            }}
            onFocus={e => {
              e.target.style.borderColor = "rgba(56,189,248,0.5)";
              e.target.style.boxShadow = "0 0 0 3px rgba(56,189,248,0.08)";
            }}
            onBlur={e => {
              e.target.style.borderColor = "rgba(56,189,248,0.15)";
              e.target.style.boxShadow = "none";
            }}
          />
        </div>

        {error && (
          <div style={{
            padding: "10px 14px", marginBottom: "16px",
            background: "rgba(244,63,94,0.08)", border: "1px solid rgba(244,63,94,0.2)",
            borderRadius: "8px", color: "#f43f5e", fontSize: "13px",
            display: "flex", alignItems: "center", gap: "8px",
          }}>
            <span>⚠</span> {error}
          </div>
        )}

        <button
          onClick={handleLogin} disabled={loading}
          style={{
            width: "100%", padding: "13px",
            background: loading
              ? "rgba(56,189,248,0.1)"
              : "linear-gradient(135deg, #38bdf8, #0ea5e9)",
            color: loading ? "rgba(56,189,248,0.5)" : "#000",
            border: "none", borderRadius: "10px",
            fontWeight: 700, fontSize: "14px",
            letterSpacing: "0.04em",
            cursor: loading ? "not-allowed" : "pointer",
            fontFamily: "'Syne', sans-serif",
            transition: "all 0.2s",
            boxShadow: loading ? "none" : "0 4px 20px rgba(56,189,248,0.3)",
          }}
          onMouseOver={e => { if (!loading) e.currentTarget.style.transform = "translateY(-1px)"; }}
          onMouseOut={e => { e.currentTarget.style.transform = "translateY(0)"; }}
        >
          {loading ? (
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
              <span style={{
                width: "14px", height: "14px", border: "2px solid rgba(56,189,248,0.3)",
                borderTopColor: "#38bdf8", borderRadius: "50%",
                animation: "spin 0.7s linear infinite", display: "inline-block",
              }}/>
              Authenticating...
            </span>
          ) : "Access Platform →"}
        </button>

        <div style={{
          textAlign: "center", marginTop: "24px",
          color: "rgba(61,80,104,0.8)", fontSize: "11px",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          JENIX ENTERPRISE · SECURE ACCESS PORTAL
        </div>
      </div>

      <style>{`
        @keyframes scanline {
          0%   { transform: translateY(-100%); opacity: 0; }
          10%  { opacity: 0.6; }
          90%  { opacity: 0.6; }
          100% { transform: translateY(3000%); opacity: 0; }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
