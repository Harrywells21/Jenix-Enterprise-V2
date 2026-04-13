import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useBrand } from "../context/BrandContext";

const NAV_ALL = [
  { path:"/",           label:"Fleet Command",  icon:"🚀", role:"all"   },
  { path:"/overview",   label:"All Machines",   icon:"🖥", role:"all"   },
  { path:"/uptime",     label:"Uptime Monitor", icon:"📡", role:"all"   },
  { path:"/cve",        label:"CVE Scanner",    icon:"🛡", role:"all"   },
  { path:"/reports",    label:"Reports",        icon:"📄", role:"all"   },
  { path:"/audit",      label:"Audit Log",      icon:"🔐", role:"all"   },
  { path:"/users",      label:"Users",          icon:"👥", role:"admin", divider:true },
  { path:"/whitelabel", label:"Branding",       icon:"🎨", role:"admin" },
  { path:"/settings",   label:"Settings",       icon:"⚙",  role:"admin" },
  { path:"/demo",       label:"Demo Script",    icon:"🎬", role:"admin", divider:true },
];

export default function MobileSidebar() {
  const [open, setOpen]      = useState(false);
  const { pathname }         = useLocation();
  const { user, logout }     = useAuth();
  const { brand }            = useBrand();
  const primary              = brand?.primary_color || "#00bcd4";
  const role                 = user?.role || "viewer";

  const visibleNav = NAV_ALL.filter(item =>
    item.role === "all" || role === "admin"
  );

  return (
    <>
      {/* Hamburger button */}
      <button
        onClick={() => setOpen(true)}
        style={{
          position:"fixed", top:"16px", left:"16px",
          zIndex:200, background:"#13131f",
          border:"1px solid #2a2a3e", borderRadius:"8px",
          padding:"8px 10px", cursor:"pointer",
          color:"#e0e0e0", fontSize:"18px",
          display:"none"
        }}
        className="hamburger"
      >
        ☰
      </button>

      {/* Overlay */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position:"fixed", inset:0,
            background:"rgba(0,0,0,0.7)",
            zIndex:300
          }}
        />
      )}

      {/* Drawer */}
      <div style={{
        position:"fixed", top:0, left:0, bottom:0,
        width:"240px", background:"#0d0d1a",
        borderRight:"1px solid #1a1a2e",
        zIndex:400, transform: open
          ? "translateX(0)" : "translateX(-100%)",
        transition:"transform 0.25s ease",
        display:"flex", flexDirection:"column"
      }}>
        <div style={{ display:"flex", justifyContent:"space-between",
                      alignItems:"center", padding:"20px 24px",
                      borderBottom:"1px solid #1a1a2e" }}>
          <div style={{ color:primary, fontSize:"20px",
                        fontWeight:900, letterSpacing:"3px" }}>
            {brand?.logo_text || "JENIX"}
          </div>
          <button onClick={() => setOpen(false)} style={{
            background:"none", border:"none",
            color:"#666", fontSize:"18px", cursor:"pointer"
          }}>✕</button>
        </div>

        <nav style={{ flex:1, overflowY:"auto", padding:"10px 0" }}>
          {visibleNav.map(({ path, label, icon, divider }) => {
            const active = pathname === path;
            return (
              <div key={path}>
                {divider && (
                  <div style={{ height:"1px", background:"#1a1a2e",
                                margin:"6px 20px" }}/>
                )}
                <Link to={path}
                  onClick={() => setOpen(false)}
                  style={{
                    display:"flex", alignItems:"center", gap:"10px",
                    padding:"10px 24px", textDecoration:"none",
                    color:      active ? primary : "#555",
                    background: active ? primary + "15" : "transparent",
                    borderLeft: active
                      ? `3px solid ${primary}`
                      : "3px solid transparent",
                    fontSize:"13px",
                    fontWeight: active ? 600 : 400,
                  }}>
                  <span>{icon}</span><span>{label}</span>
                </Link>
              </div>
            );
          })}
        </nav>

        <div style={{ padding:"16px 24px",
                      borderTop:"1px solid #1a1a2e" }}>
          <div style={{ color:"#aaa", fontSize:"12px",
                        marginBottom:"4px" }}>
            {user?.name}
          </div>
          <button onClick={() => { logout(); setOpen(false); }}
            style={{
              width:"100%", padding:"8px",
              background:"transparent", color:"#f44336",
              border:"1px solid #f44336", borderRadius:"6px",
              cursor:"pointer", fontSize:"12px"
            }}>
            Sign Out
          </button>
        </div>
      </div>

      <style>{`
        @media (max-width: 800px) {
          .hamburger { display: block !important; }
        }
      `}</style>
    </>
  );
}
