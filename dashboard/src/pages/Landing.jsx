import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

const FONT = "'Cabinet Grotesk', sans-serif";
const MONO = "'JetBrains Mono', monospace";
const DISP = "'Syne', sans-serif";

function useCountUp(target, duration = 2000, start = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!start) return;
    let startTime = null;
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setVal(Math.floor(eased * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, start]);
  return val;
}

function ParticleField() {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    const particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.4 + 0.1,
    }));
    let animId;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(56,189,248,${p.opacity})`;
        ctx.fill();
      });
      // Draw connections
      particles.forEach((a, i) => {
        particles.slice(i + 1).forEach(b => {
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(56,189,248,${0.06 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        });
      });
      animId = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(animId);
  }, []);
  return <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />;
}

function StatCounter({ value, suffix = "", label, start }) {
  const count = useCountUp(value, 1800, start);
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontFamily: DISP, fontSize: "48px", fontWeight: 800, color: "#38bdf8", lineHeight: 1, letterSpacing: "-0.03em" }}>
        {count}{suffix}
      </div>
      <div style={{ fontSize: "13px", color: "rgba(122,143,166,0.7)", fontFamily: MONO, marginTop: "6px", letterSpacing: "0.08em" }}>
        {label}
      </div>
    </div>
  );
}

const FEATURES = [
  {
    icon: "⬡",
    title: "Fleet Intelligence",
    desc: "Real-time monitoring of unlimited Linux, macOS and Windows nodes with sub-second WebSocket telemetry.",
    accent: "#38bdf8",
    delay: 0,
  },
  {
    icon: "🛡",
    title: "CVE Threat Detection",
    desc: "Continuous vulnerability scanning against the OSV.dev database. Catch critical CVEs before they become breaches.",
    accent: "#f43f5e",
    delay: 100,
  },
  {
    icon: "⚡",
    title: "Fleet Automation",
    desc: "Execute commands across thousands of nodes simultaneously. Patch, scan, clean and boost with one click.",
    accent: "#10b981",
    delay: 200,
  },
  {
    icon: "◱",
    title: "Tamper-Proof Audit",
    desc: "SHA-256 hashed audit trail for every action. Meet SOC 2, HIPAA and ISO 27001 compliance requirements.",
    accent: "#8b5cf6",
    delay: 300,
  },
  {
    icon: "◎",
    title: "Uptime Intelligence",
    desc: "99.9% SLA monitoring with instant alerting. Know about downtime before your customers do.",
    accent: "#f59e0b",
    delay: 400,
  },
  {
    icon: "◈",
    title: "Executive ROI",
    desc: "Real-time savings calculator. Show stakeholders exactly how JENIX pays for itself within 30 days.",
    accent: "#38bdf8",
    delay: 500,
  },
];

const TESTIMONIALS = [
  { quote: "JENIX reduced our incident response time by 94%. What used to take our team 4 hours now takes 14 minutes.", name: "Sarah Chen", title: "VP Engineering, FinStack" },
  { quote: "The CVE scanner caught a Log4Shell variant we had missed for 3 weeks. JENIX paid for itself in the first 48 hours.", name: "Marcus Webb", title: "CISO, DataVault Inc" },
  { quote: "Managing 2,400 nodes used to require a 6-person ops team. With JENIX, two engineers handle it effortlessly.", name: "Priya Sharma", title: "Head of Infrastructure, ScaleAI" },
];

export default function Landing() {
  const navigate = useNavigate();
  const [statsVisible, setStatsVisible] = useState(false);
  const [visibleFeatures, setVisibleFeatures] = useState([]);
  const [activeTestimonial, setActiveTestimonial] = useState(0);
  const statsRef = useRef(null);
  const featRef = useRef(null);

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true); }, { threshold: 0.3 });
    if (statsRef.current) obs.observe(statsRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        FEATURES.forEach((_, i) => setTimeout(() => setVisibleFeatures(p => [...p, i]), i * 80));
      }
    }, { threshold: 0.1 });
    if (featRef.current) obs.observe(featRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const iv = setInterval(() => setActiveTestimonial(p => (p + 1) % TESTIMONIALS.length), 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div style={{ fontFamily: FONT, background: "#040810", color: "#e8f0fe", overflowX: "hidden" }}>

      {/* Nav */}
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        padding: "0 48px",
        height: "64px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "rgba(4,8,16,0.85)",
        backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(56,189,248,0.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "30px", height: "30px",
            background: "linear-gradient(135deg, #38bdf8, #8b5cf6)",
            clipPath: "polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ color: "#000", fontSize: "10px", fontWeight: 800, fontFamily: DISP }}>J</span>
          </div>
          <span style={{ fontFamily: DISP, fontWeight: 800, fontSize: "16px", letterSpacing: "0.1em", background: "linear-gradient(135deg, #38bdf8, #e8f0fe)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>JENIX</span>
        </div>
        <div style={{ display: "flex", gap: "32px" }}>
          {["Features", "Pricing", "Docs", "Blog"].map(item => (
            <a key={item} href="#" style={{ color: "rgba(122,143,166,0.6)", fontSize: "13px", textDecoration: "none", transition: "color 0.2s", fontWeight: 500 }}
              onMouseOver={e => e.target.style.color = "#e8f0fe"}
              onMouseOut={e => e.target.style.color = "rgba(122,143,166,0.6)"}
            >{item}</a>
          ))}
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button onClick={() => navigate("/login")} style={{
            padding: "8px 18px", background: "transparent",
            border: "1px solid rgba(56,189,248,0.2)", borderRadius: "8px",
            color: "#38bdf8", fontSize: "13px", fontWeight: 600,
            cursor: "pointer", fontFamily: FONT, transition: "all 0.2s",
          }}
            onMouseOver={e => { e.currentTarget.style.background = "rgba(56,189,248,0.08)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "transparent"; }}
          >Sign In</button>
          <button onClick={() => navigate("/login")} style={{
            padding: "8px 18px",
            background: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
            border: "none", borderRadius: "8px",
            color: "#000", fontSize: "13px", fontWeight: 700,
            cursor: "pointer", fontFamily: FONT,
            boxShadow: "0 4px 16px rgba(56,189,248,0.3)",
            transition: "all 0.2s",
          }}
            onMouseOver={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(56,189,248,0.4)"; }}
            onMouseOut={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 4px 16px rgba(56,189,248,0.3)"; }}
          >Get Started →</button>
        </div>
      </nav>

      {/* Hero */}
      <section style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        position: "relative", overflow: "hidden", paddingTop: "64px",
      }}>
        <ParticleField />

        {/* Grid overlay */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "linear-gradient(rgba(56,189,248,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.025) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black, transparent)",
        }}/>

        {/* Glow orbs */}
        <div style={{ position: "absolute", top: "20%", left: "10%", width: "600px", height: "600px", borderRadius: "50%", background: "radial-gradient(circle, rgba(56,189,248,0.05) 0%, transparent 70%)", pointerEvents: "none" }}/>
        <div style={{ position: "absolute", bottom: "10%", right: "5%", width: "500px", height: "500px", borderRadius: "50%", background: "radial-gradient(circle, rgba(139,92,246,0.04) 0%, transparent 70%)", pointerEvents: "none" }}/>

        <div style={{ position: "relative", zIndex: 1, textAlign: "center", maxWidth: "900px", padding: "0 24px" }}>
          {/* Badge */}
          <div style={{
            display: "inline-flex", alignItems: "center", gap: "8px",
            padding: "6px 16px", marginBottom: "32px",
            background: "rgba(56,189,248,0.06)",
            border: "1px solid rgba(56,189,248,0.15)",
            borderRadius: "20px",
            animation: "fadeUp 0.6s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#10b981", boxShadow: "0 0 6px #10b981", animation: "pulse 2s infinite" }}/>
            <span style={{ fontSize: "12px", color: "#38bdf8", fontFamily: MONO, letterSpacing: "0.1em" }}>
              ENTERPRISE FLEET INTELLIGENCE PLATFORM
            </span>
          </div>

          {/* Headline */}
          <h1 style={{
            fontFamily: DISP, fontSize: "clamp(48px, 7vw, 84px)",
            fontWeight: 800, lineHeight: 1.05, letterSpacing: "-0.03em",
            marginBottom: "24px",
            animation: "fadeUp 0.7s 0.1s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            <span style={{ color: "#e8f0fe" }}>Your infrastructure.</span>
            <br/>
            <span style={{
              background: "linear-gradient(135deg, #38bdf8 0%, #8b5cf6 50%, #10b981 100%)",
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
              backgroundSize: "200% 200%",
              animation: "gradientShift 4s ease infinite",
            }}>Fully automated.</span>
          </h1>

          <p style={{
            fontSize: "clamp(16px, 2vw, 20px)", color: "rgba(122,143,166,0.8)",
            maxWidth: "600px", margin: "0 auto 40px",
            lineHeight: 1.7,
            animation: "fadeUp 0.7s 0.2s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            JENIX monitors, secures, and automates your entire Linux fleet in real-time. One platform. Zero blind spots. Infinite scale.
          </p>

          <div style={{
            display: "flex", gap: "12px", justifyContent: "center", flexWrap: "wrap",
            animation: "fadeUp 0.7s 0.3s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            <button onClick={() => navigate("/login")} style={{
              padding: "14px 32px",
              background: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
              border: "none", borderRadius: "12px",
              color: "#000", fontSize: "15px", fontWeight: 800,
              cursor: "pointer", fontFamily: DISP, letterSpacing: "0.04em",
              boxShadow: "0 8px 32px rgba(56,189,248,0.35)",
              transition: "all 0.25s cubic-bezier(0.16,1,0.3,1)",
            }}
              onMouseOver={e => { e.currentTarget.style.transform = "translateY(-3px) scale(1.02)"; e.currentTarget.style.boxShadow = "0 16px 48px rgba(56,189,248,0.45)"; }}
              onMouseOut={e => { e.currentTarget.style.transform = "translateY(0) scale(1)"; e.currentTarget.style.boxShadow = "0 8px 32px rgba(56,189,248,0.35)"; }}
            >Start Free Trial →</button>
            <button onClick={() => navigate("/login")} style={{
              padding: "14px 32px",
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px",
              color: "#e8f0fe", fontSize: "15px", fontWeight: 600,
              cursor: "pointer", fontFamily: FONT,
              transition: "all 0.2s",
            }}
              onMouseOver={e => { e.currentTarget.style.background = "rgba(255,255,255,0.06)"; e.currentTarget.style.borderColor = "rgba(56,189,248,0.3)"; }}
              onMouseOut={e => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}
            >▷ Watch Demo</button>
          </div>

          {/* Trust badges */}
          <div style={{
            display: "flex", gap: "24px", justifyContent: "center", marginTop: "48px",
            flexWrap: "wrap",
            animation: "fadeUp 0.7s 0.4s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            {["SOC 2 Compliant", "HIPAA Ready", "ISO 27001", "GDPR Compliant"].map(badge => (
              <div key={badge} style={{
                display: "flex", alignItems: "center", gap: "6px",
                fontSize: "11px", color: "rgba(122,143,166,0.5)",
                fontFamily: MONO, letterSpacing: "0.06em",
              }}>
                <span style={{ color: "#10b981" }}>✓</span> {badge}
              </div>
            ))}
          </div>
        </div>

        {/* Scroll indicator */}
        <div style={{
          position: "absolute", bottom: "32px", left: "50%", transform: "translateX(-50%)",
          display: "flex", flexDirection: "column", alignItems: "center", gap: "8px",
          animation: "fadeIn 1s 1s both",
        }}>
          <span style={{ fontSize: "10px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.12em" }}>SCROLL</span>
          <div style={{ width: "1px", height: "40px", background: "linear-gradient(180deg, rgba(56,189,248,0.4), transparent)", animation: "scrollPulse 2s infinite" }}/>
        </div>
      </section>

      {/* Stats */}
      <section ref={statsRef} style={{
        padding: "80px 48px",
        background: "rgba(12,18,32,0.6)",
        borderTop: "1px solid rgba(255,255,255,0.04)",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
      }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "40px" }}>
          <StatCounter value={10000} suffix="+" label="Nodes Monitored" start={statsVisible} />
          <StatCounter value={99} suffix=".9%" label="Fleet Uptime SLA" start={statsVisible} />
          <StatCounter value={94} suffix="%" label="Faster Incident Response" start={statsVisible} />
          <StatCounter value={2400} suffix="+" label="Enterprise Customers" start={statsVisible} />
        </div>
      </section>

      {/* Features */}
      <section ref={featRef} style={{ padding: "100px 48px", maxWidth: "1200px", margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: "64px" }}>
          <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "12px" }}>Platform Capabilities</div>
          <h2 style={{ fontFamily: DISP, fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 800, letterSpacing: "-0.02em", color: "#e8f0fe" }}>
            Everything your ops team needs
          </h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "16px" }}>
          {FEATURES.map((f, i) => (
            <div key={i} style={{
              padding: "28px", borderRadius: "16px",
              background: "#0c1220",
              border: "1px solid rgba(255,255,255,0.06)",
              opacity: visibleFeatures.includes(i) ? 1 : 0,
              transform: visibleFeatures.includes(i) ? "translateY(0)" : "translateY(24px)",
              transition: `opacity 0.5s ${f.delay}ms cubic-bezier(0.16,1,0.3,1), transform 0.5s ${f.delay}ms cubic-bezier(0.16,1,0.3,1), border-color 0.2s`,
              cursor: "default",
            }}
              onMouseOver={e => { e.currentTarget.style.borderColor = `${f.accent}30`; e.currentTarget.style.boxShadow = `0 0 30px ${f.accent}08`; }}
              onMouseOut={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; e.currentTarget.style.boxShadow = "none"; }}
            >
              <div style={{
                width: "44px", height: "44px", borderRadius: "12px",
                background: `${f.accent}12`, border: `1px solid ${f.accent}20`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "20px", marginBottom: "16px",
                color: f.accent,
              }}>{f.icon}</div>
              <h3 style={{ fontFamily: DISP, fontSize: "18px", fontWeight: 700, color: "#e8f0fe", marginBottom: "8px" }}>{f.title}</h3>
              <p style={{ fontSize: "14px", color: "rgba(122,143,166,0.7)", lineHeight: 1.65 }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Dashboard preview */}
      <section style={{
        padding: "60px 48px 100px",
        background: "rgba(8,13,26,0.8)",
        borderTop: "1px solid rgba(255,255,255,0.04)",
      }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "48px" }}>
            <h2 style={{ fontFamily: DISP, fontSize: "36px", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "12px" }}>
              Built for the modern ops team
            </h2>
            <p style={{ color: "rgba(122,143,166,0.6)", fontSize: "15px" }}>
              A command center that turns infrastructure chaos into clarity
            </p>
          </div>

          {/* Fake terminal / dashboard preview */}
          <div style={{
            background: "#080d1a", border: "1px solid rgba(56,189,248,0.12)",
            borderRadius: "16px", overflow: "hidden",
            boxShadow: "0 40px 120px rgba(0,0,0,0.6), 0 0 60px rgba(56,189,248,0.05)",
          }}>
            {/* Window chrome */}
            <div style={{ padding: "12px 16px", background: "#0c1220", borderBottom: "1px solid rgba(255,255,255,0.04)", display: "flex", alignItems: "center", gap: "8px" }}>
              {["#f43f5e", "#f59e0b", "#10b981"].map(c => (
                <div key={c} style={{ width: "10px", height: "10px", borderRadius: "50%", background: c, opacity: 0.7 }}/>
              ))}
              <div style={{ marginLeft: "12px", fontSize: "11px", color: "rgba(122,143,166,0.4)", fontFamily: MONO }}>jenix-enterprise · fleet-command</div>
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "6px" }}>
                <div style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#10b981", boxShadow: "0 0 5px #10b981" }}/>
                <span style={{ fontSize: "10px", color: "#10b981", fontFamily: MONO }}>LIVE</span>
              </div>
            </div>

            {/* Dashboard mockup */}
            <div style={{ padding: "24px", display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "12px" }}>
              {[
                { label: "TOTAL NODES", value: "1,247", color: "#38bdf8" },
                { label: "FLEET CPU", value: "34.2%", color: "#10b981" },
                { label: "FLEET RAM", value: "67.8%", color: "#8b5cf6" },
                { label: "CRITICAL ALERTS", value: "3", color: "#f43f5e" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: "#0c1220", border: "1px solid rgba(255,255,255,0.05)",
                  borderRadius: "10px", padding: "16px",
                }}>
                  <div style={{ fontSize: "8px", color: "rgba(122,143,166,0.4)", fontFamily: MONO, letterSpacing: "0.18em", marginBottom: "8px" }}>{label}</div>
                  <div style={{ fontFamily: DISP, fontSize: "24px", fontWeight: 800, color }}>{value}</div>
                  <div style={{ height: "2px", background: "rgba(255,255,255,0.04)", borderRadius: "1px", marginTop: "10px", overflow: "hidden" }}>
                    <div style={{ width: `${Math.random() * 60 + 30}%`, height: "100%", background: color, opacity: 0.6, borderRadius: "1px" }}/>
                  </div>
                </div>
              ))}
            </div>

            {/* Animated terminal lines */}
            <div style={{ padding: "0 24px 24px" }}>
              <div style={{ background: "#040810", borderRadius: "10px", padding: "14px 16px", fontFamily: MONO, fontSize: "11px" }}>
                {[
                  { t: "10:42:01", msg: "Fleet scan complete — 1,247 nodes checked", c: "#10b981" },
                  { t: "10:42:14", msg: "CVE-2024-3094 detected on node prod-web-07", c: "#f43f5e" },
                  { t: "10:42:15", msg: "Auto-remediation triggered — patching in progress", c: "#f59e0b" },
                  { t: "10:42:31", msg: "Patch applied successfully — node status: healthy", c: "#10b981" },
                  { t: "10:42:45", msg: "Compliance report generated — SOC 2: 91%", c: "#38bdf8" },
                ].map((line, i) => (
                  <div key={i} style={{ display: "flex", gap: "12px", marginBottom: "5px", animation: `fadeIn 0.4s ${i * 0.15}s both` }}>
                    <span style={{ color: "rgba(122,143,166,0.3)" }}>{line.t}</span>
                    <span style={{ color: line.c }}>›</span>
                    <span style={{ color: "rgba(122,143,166,0.7)" }}>{line.msg}</span>
                  </div>
                ))}
                <div style={{ display: "flex", gap: "4px", marginTop: "8px" }}>
                  <span style={{ color: "#38bdf8" }}>jenix@fleet:~$</span>
                  <span style={{ color: "rgba(56,189,248,0.6)", animation: "blink 1s step-end infinite" }}>▊</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section style={{ padding: "100px 48px", maxWidth: "800px", margin: "0 auto", textAlign: "center" }}>
        <div style={{ fontSize: "10px", color: "rgba(56,189,248,0.6)", fontFamily: MONO, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: "48px" }}>
          Trusted by Engineering Teams Worldwide
        </div>
        <div style={{ position: "relative", minHeight: "160px" }}>
          {TESTIMONIALS.map((t, i) => (
            <div key={i} style={{
              position: "absolute", inset: 0,
              opacity: i === activeTestimonial ? 1 : 0,
              transform: i === activeTestimonial ? "translateY(0)" : "translateY(10px)",
              transition: "opacity 0.5s, transform 0.5s",
              pointerEvents: i === activeTestimonial ? "auto" : "none",
            }}>
              <p style={{ fontSize: "clamp(18px, 2.5vw, 24px)", color: "#e8f0fe", lineHeight: 1.6, fontWeight: 500, marginBottom: "24px", fontStyle: "italic" }}>
                "{t.quote}"
              </p>
              <div style={{ fontSize: "13px", color: "#38bdf8", fontWeight: 700 }}>{t.name}</div>
              <div style={{ fontSize: "12px", color: "rgba(122,143,166,0.5)", fontFamily: MONO, marginTop: "3px" }}>{t.title}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: "6px", justifyContent: "center", marginTop: "32px" }}>
          {TESTIMONIALS.map((_, i) => (
            <button key={i} onClick={() => setActiveTestimonial(i)} style={{
              width: i === activeTestimonial ? "24px" : "6px", height: "6px",
              borderRadius: "3px", border: "none",
              background: i === activeTestimonial ? "#38bdf8" : "rgba(56,189,248,0.2)",
              cursor: "pointer", padding: 0,
              transition: "all 0.3s cubic-bezier(0.16,1,0.3,1)",
            }}/>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{
        padding: "100px 48px",
        background: "rgba(12,18,32,0.6)",
        borderTop: "1px solid rgba(255,255,255,0.04)",
        textAlign: "center",
        position: "relative", overflow: "hidden",
      }}>
        <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: "600px", height: "600px", borderRadius: "50%", background: "radial-gradient(circle, rgba(56,189,248,0.04) 0%, transparent 70%)", pointerEvents: "none" }}/>
        <div style={{ position: "relative", zIndex: 1 }}>
          <h2 style={{ fontFamily: DISP, fontSize: "clamp(32px, 4vw, 52px)", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "16px" }}>
            Ready to take control<br/>of your fleet?
          </h2>
          <p style={{ color: "rgba(122,143,166,0.7)", fontSize: "16px", marginBottom: "40px" }}>
            Join 2,400+ engineering teams running JENIX in production.
          </p>
          <button onClick={() => navigate("/login")} style={{
            padding: "16px 48px",
            background: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
            border: "none", borderRadius: "14px",
            color: "#000", fontSize: "16px", fontWeight: 800,
            cursor: "pointer", fontFamily: DISP, letterSpacing: "0.04em",
            boxShadow: "0 8px 40px rgba(56,189,248,0.4)",
            transition: "all 0.25s cubic-bezier(0.16,1,0.3,1)",
          }}
            onMouseOver={e => { e.currentTarget.style.transform = "translateY(-3px) scale(1.02)"; e.currentTarget.style.boxShadow = "0 16px 60px rgba(56,189,248,0.5)"; }}
            onMouseOut={e => { e.currentTarget.style.transform = "translateY(0) scale(1)"; e.currentTarget.style.boxShadow = "0 8px 40px rgba(56,189,248,0.4)"; }}
          >Start Free — No Credit Card →</button>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ padding: "32px 48px", borderTop: "1px solid rgba(255,255,255,0.04)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ width: "22px", height: "22px", background: "linear-gradient(135deg, #38bdf8, #8b5cf6)", clipPath: "polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)" }}/>
          <span style={{ fontFamily: DISP, fontWeight: 800, fontSize: "13px", letterSpacing: "0.1em", color: "rgba(122,143,166,0.5)" }}>JENIX</span>
        </div>
        <div style={{ fontSize: "12px", color: "rgba(61,80,104,0.6)", fontFamily: MONO }}>
          © 2026 JENIX Enterprise. All rights reserved.
        </div>
        <div style={{ display: "flex", gap: "20px" }}>
          {["Privacy", "Terms", "Security", "Status"].map(item => (
            <a key={item} href="#" style={{ fontSize: "12px", color: "rgba(61,80,104,0.6)", textDecoration: "none", fontFamily: MONO, transition: "color 0.2s" }}
              onMouseOver={e => e.target.style.color = "#38bdf8"}
              onMouseOut={e => e.target.style.color = "rgba(61,80,104,0.6)"}
            >{item}</a>
          ))}
        </div>
      </footer>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&family=Cabinet+Grotesk:wght@300;400;500;600;700;800&display=swap');
        @keyframes fadeUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @keyframes gradientShift { 0%,100% { background-position:0% 50%; } 50% { background-position:100% 50%; } }
        @keyframes scrollPulse { 0%,100% { opacity:0.4; transform:scaleY(1); } 50% { opacity:0.8; transform:scaleY(1.1); } }
        @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0; } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width:4px; } ::-webkit-scrollbar-thumb { background:rgba(56,189,248,0.2); border-radius:2px; }
      `}</style>
    </div>
  );
}
