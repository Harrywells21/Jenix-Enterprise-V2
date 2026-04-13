export default function DemoScript() {
  const SCRIPT = [
    {
      time: "0:00 – 0:20",
      section: "OPENING",
      color: "#00bcd4",
      lines: [
        "\"Good [morning/afternoon]. Today I'm going to show you JENIX Enterprise — a Linux infrastructure management platform I built from scratch.\"",
        "\"Over 90% of the world's servers run Linux. And most teams manage them the old way — SSH sessions, manual commands, scattered scripts. JENIX replaces all of that.\"",
        "\"One dashboard. Every server. Let's go.\"",
      ]
    },
    {
      time: "0:20 – 0:50",
      section: "FLEET COMMAND CENTER",
      color: "#ffb300",
      lines: [
        "\"This is the Fleet Command Center. Every machine in your infrastructure, scored by health from 0 to 100, updating live.\"",
        "\"Green means healthy. Amber means attention needed. Red means critical — and as you can see, it tells you exactly why.\"",
        "\"The ROI calculator at the bottom is pulling real data from this deployment. It's showing you exactly how much JENIX has saved in manual work — in dollars, not hours.\"",
        "\"This is the first screen your management team sees. They don't need to be technical to understand it.\"",
      ]
    },
    {
      time: "0:50 – 1:20",
      section: "ONE-CLICK FLEET OPERATIONS",
      color: "#4caf50",
      lines: [
        "\"Now watch this. I'm going to run a security scan across every single online machine simultaneously. One click.\"",
        "[Click SCAN ALL — pause 3 seconds]",
        "\"Done. That command just went to every agent simultaneously over WebSocket. No SSH. No scripts. No waiting.\"",
        "\"I can do the same for performance boost, deep clean, or security fixes. All with rollback — so if anything goes wrong, one click puts everything back.\"",
      ]
    },
    {
      time: "1:20 – 1:45",
      section: "CVE THREAT INTELLIGENCE",
      color: "#f44336",
      lines: [
        "\"This is where security teams pay attention. JENIX scans every installed package against the OSV.dev vulnerability database in real time.\"",
        "[Navigate to CVE Scanner, run scan]",
        "\"It found [X] vulnerabilities — with severity levels, CVE IDs, and direct links to the full details. This took 20 seconds. Manually, this would take a security engineer half a day per server.\"",
      ]
    },
    {
      time: "1:45 – 2:05",
      section: "TAMPER-PROOF AUDIT LOG",
      color: "#9c27b0",
      lines: [
        "\"For compliance teams — every single action in JENIX is cryptographically hashed with SHA-256.\"",
        "[Navigate to Audit Log, click Verify on an entry]",
        "\"That hash was computed when the log was created. Clicking Verify recomputes it now and confirms it matches. This log has not been touched since it was written.\"",
        "\"Export the full audit trail as a signed CSV — hand it to your auditor. Done.\"",
      ]
    },
    {
      time: "2:05 – 2:25",
      section: "COMPLIANCE PDF REPORT",
      color: "#00bcd4",
      lines: [
        "\"One more thing compliance teams love. I can generate a full security report for any machine in one click.\"",
        "[Navigate to Reports, generate PDF, open it]",
        "\"Executive summary, risk score, open ports, SSH configuration, SUID files, recommendations — all formatted for an auditor. Most companies pay consultants thousands to produce this manually.\"",
      ]
    },
    {
      time: "2:25 – 2:45",
      section: "UPTIME + SLA",
      color: "#4caf50",
      lines: [
        "\"The Uptime Monitor tracks every machine over 30 days. Green blocks are operational days, red are incidents.\"",
        "\"Each machine gets an SLA compliance rating against a 99% uptime target. This view alone can replace dedicated monitoring tools your team might be paying for monthly.\"",
      ]
    },
    {
      time: "2:45 – 3:00",
      section: "CLOSING",
      color: "#ffb300",
      lines: [
        "\"JENIX is a one-time buyout. Unlimited servers. Perpetual license. Deploy on your own infrastructure — no cloud, no subscription, no calling home.\"",
        "\"One sysadmin costs $60,000 to $80,000 per year. JENIX costs $65,000 once, and pays for itself in the first 12 months.\"",
        "\"I'm Aaditya Singh — I built every line of this. If you want a pilot deployment on your infrastructure this week, let's talk.\"",
        "\"aadisingh0121@gmail.com\"",
      ]
    },
  ];

  return (
    <div>
      <div style={{ marginBottom:"24px" }}>
        <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                     fontWeight:700, marginBottom:"4px" }}>
          Demo Video Script
        </h1>
        <div style={{ color:"#666", fontSize:"13px" }}>
          3-minute enterprise demo · Read at natural pace
        </div>
      </div>

      {/* Tips */}
      <div style={{
        background:"#0a1628", border:"1px solid #00bcd4",
        borderRadius:"10px", padding:"16px",
        marginBottom:"20px"
      }}>
        <div style={{ color:"#00bcd4", fontSize:"12px",
                      fontWeight:700, marginBottom:"8px" }}>
          📋 DEMO TIPS
        </div>
        <div style={{ display:"grid",
                      gridTemplateColumns:"1fr 1fr",
                      gap:"6px" }}>
          {[
            "Open Fleet Command Center first — that's the wow moment",
            "Have the agent running and sending live metrics before you start",
            "Run the CVE scan BEFORE the demo so results are ready",
            "Generate a PDF report in advance — show the download",
            "Keep browser zoom at 90% so everything fits cleanly",
            "Use a dark room if presenting — the UI pops on projector",
            "Pause after 'One click' moments — let silence do the selling",
            "End with your email on screen while saying it out loud",
          ].map((tip, i) => (
            <div key={i} style={{ display:"flex", gap:"8px",
                                   alignItems:"flex-start" }}>
              <span style={{ color:"#00bcd4", fontSize:"11px",
                             flexShrink:0 }}>→</span>
              <span style={{ color:"#aaa", fontSize:"12px" }}>{tip}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Script blocks */}
      {SCRIPT.map((block, i) => (
        <div key={i} style={{
          background:"#13131f",
          border:`1px solid ${block.color}33`,
          borderLeft:`4px solid ${block.color}`,
          borderRadius:"10px", padding:"20px",
          marginBottom:"12px"
        }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"center", marginBottom:"12px" }}>
            <div style={{ color:block.color, fontSize:"13px",
                          fontWeight:700 }}>
              {block.section}
            </div>
            <div style={{
              background: block.color + "22",
              color: block.color,
              padding:"3px 10px", borderRadius:"20px",
              fontSize:"11px", fontWeight:600
            }}>
              {block.time}
            </div>
          </div>
          {block.lines.map((line, j) => (
            <div key={j} style={{
              padding:"8px 12px", marginBottom:"6px",
              background: line.startsWith("[")
                ? "#0d0d1a" : "#0a0a12",
              borderRadius:"6px",
              border: line.startsWith("[")
                ? "1px dashed #2a2a3e" : "none"
            }}>
              <span style={{
                color: line.startsWith("[") ? "#ffb300" : "#e0e0e0",
                fontSize:"13px", lineHeight:"1.6",
                fontStyle: line.startsWith("[") ? "italic" : "normal"
              }}>
                {line}
              </span>
            </div>
          ))}
        </div>
      ))}

      {/* Contact block */}
      <div style={{
        background:"linear-gradient(135deg, #0a1628, #0d0d1a)",
        border:"1px solid #00bcd4", borderRadius:"12px",
        padding:"24px", textAlign:"center", marginTop:"8px"
      }}>
        <div style={{ color:"#00bcd4", fontSize:"18px",
                      fontWeight:800, marginBottom:"8px" }}>
          Aaditya Singh
        </div>
        <div style={{ color:"#666", fontSize:"13px",
                      marginBottom:"4px" }}>
          Freelance Developer · JENIX Enterprise Creator
        </div>
        <div style={{ color:"#00bcd4", fontSize:"14px",
                      fontWeight:600 }}>
          aadisingh0121@gmail.com
        </div>
      </div>
    </div>
  );
}
