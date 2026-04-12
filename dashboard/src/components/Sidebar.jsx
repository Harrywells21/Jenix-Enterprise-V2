import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBrand } from "../context/BrandContext";

const NAV = [
  { path:"/",           label:"Fleet Command",  icon:"🚀" },
  { path:"/overview",   label:"All Machines",   icon:"🖥" },
  { path:"/uptime",     label:"Uptime Monitor", icon:"📡" },
  { path:"/cve",        label:"CVE Scanner",    icon:"🛡" },
  { path:"/reports",    label:"Reports",        icon:"📄" },
  { path:"/audit",      label:"Audit Log",      icon:"🔐", divider:false },
  { path:"/users",      label:"Users",          icon:"👥", divider:true  },
  { path:"/whitelabel", label:"Branding",       icon:"🎨" },
  { path:"/settings",   label:"Settings",       icon:"⚙"  },
];

export default function Sidebar() {
  const { pathname }     = useLocation();
  const { user, logout } = useAuth();
  const { brand }        = useBrand();

  return (
    <aside style={{
      width:"220px", minWidth:"220px",
      background: brand.sidebar_bg || "#0d0d1a",
      borderRight:"1px solid #1a1a2e",
      display:"flex", flexDirection:"column"
    }}>
      {/* Logo */}
      <div style={{ padding:"22px 24px",
                    borderBottom:"1px solid #1a1a2e" }}>
        <div style={{
          color:      brand.primary_color || "#00bcd4",
          fontSize:   "20px",
          fontWeight: 900,
          letterSpacing:"3px"
        }}>
          {brand.logo_text || "JENIX"}
        </div>
        <div style={{ color:"#333", fontSize:"10px",
                      marginTop:"2px", letterSpacing:"1px" }}>
          {brand.logo_subtext || "ENTERPRISE v2.0"}
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex:1, padding:"10px 0", overflowY:"auto" }}>
        {NAV.map(({ path, label, icon, divider }) => {
          const active = pathname === path;
          const primary = brand.primary_color || "#00bcd4";
          return (
            <div key={path}>
              {divider && (
                <div style={{ height:"1px", background:"#1a1a2e",
                              margin:"6px 20px" }}/>
              )}
              <Link to={path} style={{
                display:"flex", alignItems:"center", gap:"10px",
                padding:"8px 24px", textDecoration:"none",
                color:      active ? primary : "#555",
                background: active ? primary + "15" : "transparent",
                borderLeft: active
                  ? `3px solid ${primary}`
                  : "3px solid transparent",
                fontSize:"13px",
                fontWeight: active ? 600 : 400,
                transition:"all 0.15s"
              }}>
                <span style={{ fontSize:"14px" }}>{icon}</span>
                <span>{label}</span>
              </Link>
            </div>
          );
        })}
      </nav>

      {/* User + footer */}
      <div style={{ borderTop:"1px solid #1a1a2e" }}>
        <div style={{ padding:"14px 20px" }}>
          <div style={{ display:"flex", alignItems:"center",
                        gap:"10px", marginBottom:"10px" }}>
            <div style={{
              width:"30px", height:"30px", borderRadius:"50%",
              background:"#0a2a2a",
              border:`1px solid ${brand.primary_color || "#00bcd4"}`,
              display:"flex", alignItems:"center",
              justifyContent:"center",
              color: brand.primary_color || "#00bcd4",
              fontSize:"12px", fontWeight:700, flexShrink:0
            }}>
              {user?.name?.[0]?.toUpperCase() || "A"}
            </div>
            <div style={{ minWidth:0 }}>
              <div style={{ color:"#e0e0e0", fontSize:"12px",
                            fontWeight:600, overflow:"hidden",
                            textOverflow:"ellipsis",
                            whiteSpace:"nowrap" }}>
                {user?.name}
              </div>
              <div style={{ color:"#444", fontSize:"10px",
                            textTransform:"capitalize" }}>
                {user?.role}
              </div>
            </div>
          </div>
          <button onClick={logout}
            onMouseOver={e => {
              e.target.style.color="#f44336";
              e.target.style.borderColor="#f44336";
            }}
            onMouseOut={e => {
              e.target.style.color="#333";
              e.target.style.borderColor="#1a1a2e";
            }}
            style={{
              width:"100%", padding:"6px",
              background:"transparent", color:"#333",
              border:"1px solid #1a1a2e", borderRadius:"6px",
              cursor:"pointer", fontSize:"11px",
              transition:"all 0.15s"
            }}>
            Sign Out
          </button>
        </div>
        {brand.powered_by && (
          <div style={{ textAlign:"center", padding:"8px",
                        color:"#222", fontSize:"10px",
                        borderTop:"1px solid #1a1a2e" }}>
            Powered by JENIX
          </div>
        )}
      </div>
    </aside>
  );
}
