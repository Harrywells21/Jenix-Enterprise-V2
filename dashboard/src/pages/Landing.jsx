import { useNavigate } from "react-router-dom";

const FEATURES = [
  { icon:"🖥", title:"Multi-Node Management",
    desc:"Manage unlimited Linux servers from one dashboard. No SSH juggling." },
  { icon:"⚡", title:"One-Click Fleet Operations",
    desc:"Scan, boost, clean or fix your entire fleet simultaneously." },
  { icon:"📊", title:"Real-Time Analytics",
    desc:"Live CPU, RAM, disk and network metrics with health scoring." },
  { icon:"🔐", title:"Tamper-Proof Audit Logs",
    desc:"Every action cryptographically signed with SHA-256." },
  { icon:"🤖", title:"Automated Scheduled Scans",
    desc:"Set it and forget it. JENIX watches your fleet 24/7." },
  { icon:"📄", title:"Compliance PDF Reports",
    desc:"Professional security reports ready for auditors in one click." },
  { icon:"🚨", title:"Instant Alerts",
    desc:"Slack and Teams notifications when something needs attention." },
  { icon:"↩", title:"Safe Rollback",
    desc:"Every change is reversible. Never fear a fix again." },
];

const STATS = [
  { value:"∞", label:"Servers Managed" },
  { value:"60%", label:"Less Manual Work" },
  { value:"1-Click", label:"Fleet Operations" },
  { value:"SHA-256", label:"Audit Security" },
];

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight:"100vh", background:"#0d0d1a",
                  fontFamily:"Inter, Segoe UI, sans-serif" }}>

      {/* Nav */}
      <nav style={{
        display:"flex", justifyContent:"space-between",
        alignItems:"center", padding:"20px 60px",
        borderBottom:"1px solid #1a1a2e",
        position:"sticky", top:0, zIndex:100,
        background:"rgba(13,13,26,0.95)",
        backdropFilter:"blur(10px)"
      }}>
        <div style={{ color:"#00bcd4", fontSize:"22px",
                      fontWeight:800, letterSpacing:"2px" }}>
          JENIX
        </div>
        <div style={{ display:"flex", gap:"12px" }}>
          <button onClick={() => navigate("/login")} style={{
            padding:"8px 24px", background:"transparent",
            color:"#aaa", border:"1px solid #2a2a3e",
            borderRadius:"8px", cursor:"pointer",
            fontSize:"14px", fontWeight:600
          }}>
            Sign In
          </button>
          <button onClick={() => navigate("/login")} style={{
            padding:"8px 24px", background:"#00bcd4",
            color:"#000", border:"none",
            borderRadius:"8px", cursor:"pointer",
            fontSize:"14px", fontWeight:700
          }}>
            Get Started
          </button>
        </div>
      </nav>

      {/* Hero */}
      <div style={{
        textAlign:"center", padding:"100px 60px 80px",
        maxWidth:"900px", margin:"0 auto"
      }}>
        <div style={{
          display:"inline-block",
          padding:"4px 16px", borderRadius:"20px",
          background:"#0a2a2a", border:"1px solid #00bcd4",
          color:"#00bcd4", fontSize:"12px", fontWeight:600,
          marginBottom:"24px", letterSpacing:"1px"
        }}>
          ENTERPRISE LINUX MANAGEMENT PLATFORM
        </div>

        <h1 style={{
          fontSize:"56px", fontWeight:900, lineHeight:1.1,
          marginBottom:"20px", color:"#ffffff"
        }}>
          One Dashboard.<br/>
          <span style={{ color:"#00bcd4" }}>
            Infinite Linux Servers.
          </span>
        </h1>

        <p style={{
          fontSize:"18px", color:"#aaa", lineHeight:1.7,
          marginBottom:"40px", maxWidth:"600px", margin:"0 auto 40px"
        }}>
          JENIX replaces hours of manual sysadmin work with intelligent
          automation. Scan, fix, secure and monitor your entire Linux
          fleet — from one screen.
        </p>

        <div style={{ display:"flex", gap:"12px",
                      justifyContent:"center", marginBottom:"60px" }}>
          <button onClick={() => navigate("/login")} style={{
            padding:"14px 36px", background:"#00bcd4",
            color:"#000", border:"none", borderRadius:"10px",
            fontSize:"16px", fontWeight:700, cursor:"pointer"
          }}>
            Open Dashboard →
          </button>
          <button style={{
            padding:"14px 36px", background:"transparent",
            color:"#aaa", border:"1px solid #2a2a3e",
            borderRadius:"10px", fontSize:"16px",
            fontWeight:600, cursor:"pointer"
          }}>
            View Docs
          </button>
        </div>

        {/* Stats */}
        <div style={{
          display:"grid", gridTemplateColumns:"repeat(4,1fr)",
          gap:"20px", maxWidth:"700px", margin:"0 auto"
        }}>
          {STATS.map(({ value, label }) => (
            <div key={label} style={{
              background:"#13131f", border:"1px solid #2a2a3e",
              borderRadius:"10px", padding:"20px"
            }}>
              <div style={{ color:"#00bcd4", fontSize:"24px",
                            fontWeight:800 }}>
                {value}
              </div>
              <div style={{ color:"#666", fontSize:"12px",
                            marginTop:"4px" }}>
                {label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Features */}
      <div style={{ padding:"60px", background:"#0a0a14" }}>
        <h2 style={{ textAlign:"center", color:"#e0e0e0",
                     fontSize:"32px", fontWeight:800,
                     marginBottom:"8px" }}>
          Everything your team needs
        </h2>
        <p style={{ textAlign:"center", color:"#666",
                    marginBottom:"48px", fontSize:"15px" }}>
          Built for sysadmins. Designed for executives.
        </p>
        <div style={{
          display:"grid",
          gridTemplateColumns:"repeat(4,1fr)",
          gap:"16px", maxWidth:"1100px", margin:"0 auto"
        }}>
          {FEATURES.map(({ icon, title, desc }) => (
            <div key={title} style={{
              background:"#13131f", border:"1px solid #2a2a3e",
              borderRadius:"12px", padding:"24px"
            }}>
              <div style={{ fontSize:"28px", marginBottom:"12px" }}>
                {icon}
              </div>
              <div style={{ color:"#e0e0e0", fontWeight:700,
                            fontSize:"14px", marginBottom:"8px" }}>
                {title}
              </div>
              <div style={{ color:"#666", fontSize:"13px",
                            lineHeight:1.6 }}>
                {desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div style={{
        textAlign:"center", padding:"80px 60px",
        background:"linear-gradient(135deg, #0a1628 0%, #0d0d1a 100%)"
      }}>
        <h2 style={{ color:"#e0e0e0", fontSize:"36px",
                     fontWeight:800, marginBottom:"16px" }}>
          Ready to take control of your infrastructure?
        </h2>
        <p style={{ color:"#666", fontSize:"15px",
                    marginBottom:"32px" }}>
          One-time license. Unlimited servers. Perpetual use.
        </p>
        <button onClick={() => navigate("/login")} style={{
          padding:"16px 48px", background:"#00bcd4",
          color:"#000", border:"none", borderRadius:"10px",
          fontSize:"18px", fontWeight:800, cursor:"pointer"
        }}>
          Open JENIX Dashboard →
        </button>
      </div>

      {/* Footer */}
      <div style={{
        textAlign:"center", padding:"24px",
        borderTop:"1px solid #1a1a2e",
        color:"#444", fontSize:"12px"
      }}>
        JENIX Enterprise v2.0 · Linux Management Platform ·
        Perpetual License
      </div>
    </div>
  );
}
