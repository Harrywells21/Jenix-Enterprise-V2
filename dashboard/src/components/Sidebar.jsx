import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { path:"/",         label:"Fleet Command",  icon:"🚀", divider:false },
  { path:"/overview", label:"All Machines",   icon:"🖥", divider:false },
  { path:"/reports",  label:"Reports",        icon:"📄", divider:false },
  { path:"/audit",    label:"Audit Log",      icon:"🔐", divider:false },
  { path:"/users",    label:"Users",          icon:"👥", divider:true  },
  { path:"/settings", label:"Settings",       icon:"⚙",  divider:false },
];

export default function Sidebar() {
  const { pathname }     = useLocation();
  const { user, logout } = useAuth();

  return (
    <aside style={{
      width:"220px", minWidth:"220px",
      background:"#0d0d1a",
      borderRight:"1px solid #1a1a2e",
      display:"flex", flexDirection:"column",
      padding:"0"
    }}>
      {/* Logo */}
      <div style={{
        padding:"24px",
        borderBottom:"1px solid #1a1a2e"
      }}>
        <div style={{ color:"#00bcd4", fontSize:"20px",
                      fontWeight:900, letterSpacing:"3px" }}>
          JENIX
        </div>
        <div style={{ color:"#333", fontSize:"10px",
                      marginTop:"2px", letterSpacing:"1px" }}>
          ENTERPRISE v2.0
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex:1, padding:"12px 0", overflowY:"auto" }}>
        {NAV.map(({ path, label, icon, divider }) => {
          const active = pathname === path;
          return (
            <div key={path}>
              {divider && (
                <div style={{
                  height:"1px", background:"#1a1a2e",
                  margin:"8px 20px"
                }}/>
              )}
              <Link to={path} style={{
                display:"flex", alignItems:"center", gap:"10px",
                padding:"9px 24px", textDecoration:"none",
                color:      active ? "#00bcd4" : "#555",
                background: active ? "#0a1628" : "transparent",
                borderLeft: active
                  ? "3px solid #00bcd4"
                  : "3px solid transparent",
                fontSize:"13px",
                fontWeight: active ? 600 : 400,
                transition:"all 0.15s"
              }}>
                <span style={{ fontSize:"15px" }}>{icon}</span>
                <span>{label}</span>
                {path==="/" && (
                  <span style={{
                    marginLeft:"auto", background:"#f44336",
                    color:"#fff", borderRadius:"10px",
                    fontSize:"9px", padding:"1px 6px",
                    fontWeight:700, display:"none"
                  }} className="alert-badge">
                    !
                  </span>
                )}
              </Link>
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div style={{
        padding:"16px 20px",
        borderTop:"1px solid #1a1a2e"
      }}>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"10px", marginBottom:"12px" }}>
          <div style={{
            width:"32px", height:"32px", borderRadius:"50%",
            background:"#0a2a2a", border:"1px solid #00bcd4",
            display:"flex", alignItems:"center",
            justifyContent:"center",
            color:"#00bcd4", fontSize:"13px", fontWeight:700,
            flexShrink:0
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
        <button onClick={logout} style={{
          width:"100%", padding:"6px",
          background:"transparent", color:"#333",
          border:"1px solid #1a1a2e", borderRadius:"6px",
          cursor:"pointer", fontSize:"11px",
          transition:"all 0.15s"
        }}
        onMouseOver={e => {
          e.target.style.color="#f44336";
          e.target.style.borderColor="#f44336";
        }}
        onMouseOut={e => {
          e.target.style.color="#333";
          e.target.style.borderColor="#1a1a2e";
        }}>
          Sign Out
        </button>
      </div>
    </aside>
  );
}
