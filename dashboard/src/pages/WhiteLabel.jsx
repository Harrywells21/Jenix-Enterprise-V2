import { useState, useEffect } from "react";
import api from "../api";
import { useBrand } from "../context/BrandContext";

const PRESETS = [
  { name:"JENIX Default",   primary:"#00bcd4", sidebar:"#0d0d1a" },
  { name:"Purple Storm",    primary:"#9c27b0", sidebar:"#0d0a14" },
  { name:"Green Matrix",    primary:"#4caf50", sidebar:"#0a140a" },
  { name:"Red Alert",       primary:"#f44336", sidebar:"#140a0a" },
  { name:"Gold Enterprise", primary:"#ffb300", sidebar:"#141008" },
  { name:"Ocean Blue",      primary:"#2196f3", sidebar:"#0a0d14" },
];

export default function WhiteLabel() {
  const { brand, setBrand } = useBrand();
  const [form,  setForm]   = useState(brand);
  const [toast, setToast]  = useState("");
  const [saved, setSaved]  = useState(false);

  const showToast = (msg) => {
    setToast(msg); setTimeout(() => setToast(""), 3000);
  };

  useEffect(() => {
    api.get("/whitelabel").then(r => {
      setForm(r.data);
    }).catch(() => {});
  }, []);

  const save = async () => {
    try {
      await api.post("/whitelabel", form);
      setBrand(form);
      setSaved(true);
      showToast("✅ Branding saved — refresh to see changes");
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      showToast(`❌ ${e.response?.data?.detail || e.message}`);
    }
  };

  const reset = async () => {
    try {
      const r = await api.post("/whitelabel/reset");
      setForm(r.data.config);
      setBrand(r.data.config);
      showToast("✅ Reset to defaults");
    } catch (e) {
      showToast(`❌ ${e.message}`);
    }
  };

  const applyPreset = (preset) => {
    setForm(p => ({
      ...p,
      primary_color: preset.primary,
      sidebar_bg:    preset.sidebar,
      main_bg:       preset.sidebar,
    }));
  };

  const inputStyle = {
    padding:"8px 12px", background:"#1a1a2e",
    border:"1px solid #2a2a3e", borderRadius:"8px",
    color:"#e0e0e0", fontSize:"13px",
    outline:"none", width:"100%"
  };

  const box = {
    background:"#13131f", border:"1px solid #2a2a3e",
    borderRadius:"10px", padding:"20px", marginBottom:"16px"
  };

  return (
    <div>
      {toast && (
        <div style={{
          position:"fixed", top:"20px", right:"20px",
          background:"#1a1a2e", border:"1px solid #2a2a3e",
          borderRadius:"8px", padding:"12px 20px",
          color:"#e0e0e0", fontSize:"13px", zIndex:1000
        }}>{toast}</div>
      )}

      <div style={{ display:"flex", justifyContent:"space-between",
                    alignItems:"flex-start", marginBottom:"24px" }}>
        <div>
          <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                       fontWeight:700, marginBottom:"4px" }}>
            White Label Branding
          </h1>
          <div style={{ color:"#666", fontSize:"13px" }}>
            Customize JENIX with your company's brand
          </div>
        </div>
        <div style={{ display:"flex", gap:"8px" }}>
          <button onClick={reset} style={{
            padding:"8px 16px", background:"transparent",
            color:"#666", border:"1px solid #2a2a3e",
            borderRadius:"8px", cursor:"pointer",
            fontSize:"13px"
          }}>Reset</button>
          <button onClick={save} style={{
            padding:"8px 24px",
            background: saved ? "#4caf50" : form.primary_color,
            color:"#000", border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px", cursor:"pointer"
          }}>
            {saved ? "✅ Saved!" : "Save Branding"}
          </button>
        </div>
      </div>

      {/* Live Preview */}
      <div style={box}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          LIVE PREVIEW
        </div>
        <div style={{
          background: form.sidebar_bg,
          borderRadius:"10px", padding:"16px",
          display:"flex", gap:"16px",
          alignItems:"center",
          border:"1px solid #2a2a3e"
        }}>
          <div style={{
            padding:"12px 20px",
            background: form.sidebar_bg,
            borderRight:"1px solid #1a1a2e",
            minWidth:"120px"
          }}>
            <div style={{ color:form.primary_color,
                          fontSize:"16px", fontWeight:900,
                          letterSpacing:"2px" }}>
              {form.logo_text}
            </div>
            <div style={{ color:"#333", fontSize:"9px",
                          marginTop:"2px" }}>
              {form.logo_subtext}
            </div>
          </div>
          <div style={{ flex:1 }}>
            <div style={{ color:"#e0e0e0", fontSize:"14px",
                          fontWeight:700 }}>
              {form.dashboard_title}
            </div>
            <div style={{ color:"#666", fontSize:"11px" }}>
              {form.company_name}
            </div>
            <div style={{ marginTop:"8px", display:"flex",
                          gap:"8px" }}>
              <div style={{
                padding:"4px 12px", borderRadius:"6px",
                background: form.primary_color,
                color:"#000", fontSize:"11px", fontWeight:700
              }}>
                Primary Button
              </div>
              <div style={{
                padding:"4px 12px", borderRadius:"6px",
                background: form.card_bg,
                border:`1px solid ${form.primary_color}`,
                color: form.primary_color,
                fontSize:"11px", fontWeight:700
              }}>
                Secondary
              </div>
            </div>
          </div>
          {form.powered_by && (
            <div style={{ color:"#333", fontSize:"10px" }}>
              Powered by JENIX
            </div>
          )}
        </div>
      </div>

      {/* Color Presets */}
      <div style={box}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          COLOR PRESETS
        </div>
        <div style={{ display:"flex", gap:"8px", flexWrap:"wrap" }}>
          {PRESETS.map(preset => (
            <button key={preset.name}
              onClick={() => applyPreset(preset)}
              style={{
                padding:"8px 16px",
                background:"#1a1a2e",
                border:`2px solid ${preset.primary}`,
                borderRadius:"8px", cursor:"pointer",
                color: preset.primary,
                fontSize:"12px", fontWeight:600
              }}>
              {preset.name}
            </button>
          ))}
        </div>
      </div>

      {/* Branding Fields */}
      <div style={box}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"16px" }}>
          BRANDING
        </div>
        <div style={{ display:"grid",
                      gridTemplateColumns:"1fr 1fr",
                      gap:"12px" }}>
          {[
            { key:"company_name",   label:"Company Name"      },
            { key:"logo_text",      label:"Logo Text"         },
            { key:"logo_subtext",   label:"Logo Subtext"      },
            { key:"dashboard_title",label:"Dashboard Title"   },
            { key:"support_email",  label:"Support Email"     },
            { key:"support_url",    label:"Support URL"       },
            { key:"favicon_emoji",  label:"Favicon Emoji"     },
          ].map(({ key, label }) => (
            <div key={key}>
              <div style={{ color:"#666", fontSize:"11px",
                            marginBottom:"4px" }}>
                {label}
              </div>
              <input style={inputStyle}
                value={form[key] || ""}
                onChange={e => setForm(p=>({...p,[key]:e.target.value}))}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Colors */}
      <div style={box}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"16px" }}>
          COLORS
        </div>
        <div style={{ display:"grid",
                      gridTemplateColumns:"repeat(3,1fr)",
                      gap:"12px" }}>
          {[
            { key:"primary_color", label:"Primary Color"  },
            { key:"accent_color",  label:"Accent Color"   },
            { key:"sidebar_bg",    label:"Sidebar Background" },
            { key:"main_bg",       label:"Main Background"   },
            { key:"card_bg",       label:"Card Background"   },
          ].map(({ key, label }) => (
            <div key={key}>
              <div style={{ color:"#666", fontSize:"11px",
                            marginBottom:"4px" }}>
                {label}
              </div>
              <div style={{ display:"flex", gap:"8px",
                            alignItems:"center" }}>
                <input type="color"
                  value={form[key] || "#000000"}
                  onChange={e => setForm(p=>({...p,[key]:e.target.value}))}
                  style={{ width:"36px", height:"36px",
                           borderRadius:"6px", border:"none",
                           cursor:"pointer", background:"none" }}
                />
                <input style={{...inputStyle, flex:1}}
                  value={form[key] || ""}
                  onChange={e => setForm(p=>({...p,[key]:e.target.value}))}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Toggles */}
      <div style={box}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"16px" }}>
          OPTIONS
        </div>
        <div style={{ display:"flex", alignItems:"center",
                      gap:"12px" }}>
          <div style={{
            width:"40px", height:"22px", borderRadius:"11px",
            background: form.powered_by ? "#00bcd4" : "#2a2a3e",
            cursor:"pointer", position:"relative",
            transition:"background 0.2s"
          }} onClick={() => setForm(p=>({...p,powered_by:!p.powered_by}))}>
            <div style={{
              width:"18px", height:"18px", borderRadius:"50%",
              background:"#fff", position:"absolute",
              top:"2px",
              left: form.powered_by ? "20px" : "2px",
              transition:"left 0.2s"
            }}/>
          </div>
          <span style={{ color:"#aaa", fontSize:"13px" }}>
            Show "Powered by JENIX" footer
          </span>
        </div>
      </div>
    </div>
  );
}
