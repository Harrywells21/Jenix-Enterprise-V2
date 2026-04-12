import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { path:"/",         label:"Overview",  icon:"🖥" },
  { path:"/reports",  label:"Reports",   icon:"📄" },
  { path:"/users",    label:"Users",     icon:"👥" },
  { path:"/settings", label:"Settings",  icon:"⚙" },
];

export default function Sidebar() {
  const { pathname }     = useLocation();
  const { user, logout } = useAuth();

  return (
    <aside style={{
      width:"220px", minWidth:"220px",
      background:"#13131f",
      borderRight:"1px solid #2a2a3e",
      display:"flex", flexDirection:"column",
      padding:"24px 0"
    }}>
      <div style={{ padding:"0 24px 24px",
                    borderBottom:"1px solid #2a2a3e" }}>
        <div style={{ color:"#00bcd4", fontSize:"22px", fontWeight:700 }}>
          JENIX
        </div>
        <div style={{ color:"#666", fontSize:"11px", marginTop:"2px" }}>
          Enterprise v1.0
        </div>
      </div>

      <nav style={{ flex:1, padding:"16px 0" }}>
        {NAV.map(({ path, label, icon }) => {
          const active = pathname === path;
          return (
            <Link key={path} to={path} style={{
              display:"flex", alignItems:"center", gap:"10px",
              padding:"10px 24px", textDecoration:"none",
              color:      active ? "#00bcd4" : "#aaa",
              background: active ? "#1a1a2e" : "transparent",
              borderLeft: active ? "3px solid #00bcd4"
                                 : "3px solid transparent",
              fontSize:"14px", fontWeight: active ? 600 : 400,
              transition:"all 0.15s"
            }}>
              <span>{icon}</span><span>{label}</span>
            </Link>
          );
        })}
      </nav>

      <div style={{ padding:"16px 24px",
                    borderTop:"1px solid #2a2a3e" }}>
        <div style={{ color:"#aaa", fontSize:"12px" }}>Logged in as</div>
        <div style={{ color:"#e0e0e0", fontSize:"13px",
                      fontWeight:600, marginBottom:"10px" }}>
          {user?.name} ({user?.role})
        </div>
        <button onClick={logout} style={{
          width:"100%", padding:"7px",
          background:"#1a1a2e", color:"#f44336",
          border:"1px solid #f44336", borderRadius:"6px",
          cursor:"pointer", fontSize:"12px"
        }}>Logout</button>
      </div>
    </aside>
  );
}
