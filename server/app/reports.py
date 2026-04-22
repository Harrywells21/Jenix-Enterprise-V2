"""
JENIX Enterprise v3.0 — Professional PDF Report Generator
Multi-page signed security reports using ReportLab.
Executive summary · CVE table · Compliance findings · Recommendations.
"""

import hashlib
import io
from datetime import datetime
from typing import List, Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable,
        PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    HAS_RL = True
except ImportError:
    HAS_RL = False

# ── Palette ───────────────────────────────────────────────────────────────────
if HAS_RL:
    C_ACCENT = colors.HexColor("#3b82f6")
    C_DARK   = colors.HexColor("#070b14")
    C_GREEN  = colors.HexColor("#10b981")
    C_RED    = colors.HexColor("#ef4444")
    C_AMBER  = colors.HexColor("#f59e0b")
    C_BLUE   = colors.HexColor("#38bdf8")
    C_MUTED  = colors.HexColor("#8899bb")
    C_BORDER = colors.HexColor("#e2e8f0")
    C_BG     = colors.HexColor("#f8fafc")
    C_WHITE  = colors.white

def _sclr(sev: str):
    if not HAS_RL: return None
    return {"CRITICAL": C_RED, "HIGH": C_AMBER, "MEDIUM": C_BLUE,
            "LOW": C_GREEN, "critical": C_RED, "high": C_AMBER,
            "medium": C_BLUE, "low": C_GREEN}.get(sev, C_MUTED)

def _hclr(score: int):
    if not HAS_RL: return None
    return C_GREEN if score >= 85 else C_AMBER if score >= 65 else C_RED


def generate_report(
    node: dict,
    metrics: dict,
    scan:   Optional[dict],
    comp:   Optional[dict],
    anomaly:Optional[dict],
    company: str = "JENIX Enterprise",
    output_path: Optional[str] = None,
) -> bytes:
    if not HAS_RL:
        return b"%PDF-1.4 % ReportLab not installed - pip install reportlab\n"

    buf    = io.BytesIO()
    PW, PH = letter

    # ── Styles ────────────────────────────────────────────────────────────────
    def sty(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=15)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    S = {
        "title":  sty("title",  fontName="Helvetica-Bold", fontSize=26, textColor=C_DARK, spaceAfter=4),
        "h1":     sty("h1",     fontName="Helvetica-Bold", fontSize=15, textColor=C_ACCENT, spaceAfter=6, spaceBefore=14),
        "h2":     sty("h2",     fontName="Helvetica-Bold", fontSize=12, spaceAfter=5, spaceBefore=10),
        "body":   sty("body",   spaceAfter=4),
        "mono":   sty("mono",   fontName="Courier",        fontSize=8,  textColor=colors.HexColor("#334155"), leading=12),
        "small":  sty("small",  fontSize=8,                textColor=C_MUTED, leading=11),
        "center": sty("center", alignment=1),
        "badge":  sty("badge",  fontName="Helvetica-Bold", fontSize=8,  textColor=C_WHITE, alignment=1),
    }

    # ── Header/footer ─────────────────────────────────────────────────────────
    def hf(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, PH - 26*mm, PW, 26*mm, fill=1, stroke=0)
        canvas.setFillColor(C_WHITE)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(18*mm, PH - 16*mm, company)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(PW - 18*mm, PH - 16*mm, "Security & Compliance Report")
        canvas.setFillColor(C_BG)
        canvas.rect(0, 0, PW, 16*mm, fill=1, stroke=0)
        canvas.setFillColor(C_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(18*mm, 7*mm, f"Generated: {datetime.utcnow():%Y-%m-%d %H:%M UTC} · JENIX Enterprise v3.0")
        canvas.drawRightString(PW - 18*mm, 7*mm, f"Page {doc.page}")
        canvas.setStrokeColor(C_ACCENT)
        canvas.setLineWidth(0.4)
        canvas.line(18*mm, 17*mm, PW - 18*mm, 17*mm)
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=letter,
                          leftMargin=18*mm, rightMargin=18*mm,
                          topMargin=32*mm, bottomMargin=22*mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=hf)])

    story = []
    W     = doc.width

    def table(data, col_widths, style_extras=None):
        base = [
            ("BACKGROUND",   (0,0), (-1,0), C_ACCENT),
            ("TEXTCOLOR",    (0,0), (-1,0), C_WHITE),
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[C_WHITE, C_BG]),
            ("GRID",         (0,0), (-1,-1), 0.3, C_BORDER),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("LEFTPADDING",  (0,0), (-1,-1), 7),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ]
        if style_extras:
            base.extend(style_extras)
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle(base))
        return t

    # ── Cover ─────────────────────────────────────────────────────────────────
    node_name = node.get("name", "Unknown")
    os_pretty = node.get("os_pretty", node.get("os_type", "Linux"))
    ip        = node.get("ip_address", "—")
    health    = node.get("health_score", 0)
    status    = "ONLINE" if node.get("is_online") else "OFFLINE"

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Security Report", S["title"]))
    story.append(Paragraph(node_name, ParagraphStyle("nn", fontName="Helvetica-Bold",
                 fontSize=20, textColor=C_ACCENT, spaceAfter=3)))
    story.append(Paragraph(f"{os_pretty}  ·  {ip}  ·  {status}", S["body"]))
    story.append(Paragraph(f"Report date: {datetime.utcnow():%B %d, %Y at %H:%M UTC}", S["small"]))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 5*mm))

    # ── Executive summary ─────────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", S["h1"]))

    scan_score = scan.get("score", "—") if scan else "—"
    comp_score = comp.get("score", "—") if comp else "—"

    summary = [
        ["Metric",           "Value",            "Status"],
        ["Health Score",     f"{health}/100",     "GOOD" if health > 80 else "AT RISK" if health > 60 else "CRITICAL"],
        ["CVE Risk Score",   str(scan_score),     "GOOD" if scan_score != "—" and int(scan_score) > 80 else "REVIEW"],
        ["Compliance Score", f"{comp_score}%",    "COMPLIANT" if comp_score != "—" and int(comp_score) >= 80 else "REVIEW"],
        ["Node Status",      status,              "✓" if status == "ONLINE" else "⚠ OFFLINE"],
        ["OS Platform",      node.get("os_type","Linux"), "✓ Supported"],
    ]
    story.append(table(summary, [W*0.4, W*0.3, W*0.3]))
    story.append(Spacer(1, 5*mm))

    # ── System info ───────────────────────────────────────────────────────────
    story.append(Paragraph("System Information", S["h1"]))
    cpu = metrics.get("cpu", {})
    mem = metrics.get("memory", {})
    def fb(b): return f"{b/1073741824:.1f} GB" if b else "—"

    sysinfo = [
        ["Property",           "Value"],
        ["Hostname",           node.get("hostname", "—")],
        ["IP Address",         ip],
        ["Operating System",   os_pretty],
        ["Architecture",       metrics.get("os_info", {}).get("arch", "x86_64")],
        ["CPU Cores (logical)",str(cpu.get("cpu_count", "—"))],
        ["CPU Cores (physical)",str(cpu.get("cpu_count_phys", "—"))],
        ["Total RAM",          fb(mem.get("ram_total"))],
        ["RAM Usage",          f"{mem.get('ram_percent',0):.1f}%"],
        ["Swap Usage",         f"{mem.get('swap_percent',0):.1f}%"],
    ]
    story.append(table(sysinfo, [W*0.45, W*0.55]))
    story.append(Spacer(1, 5*mm))

    # ── CVE findings ──────────────────────────────────────────────────────────
    if scan and scan.get("cve_findings"):
        story.append(PageBreak())
        story.append(Paragraph("CVE Vulnerability Findings", S["h1"]))
        s = scan.get("summary", {})
        story.append(Paragraph(
            f"Critical: {s.get('critical',0)}  ·  High: {s.get('high',0)}  ·  "
            f"Medium: {s.get('medium',0)}  ·  Low: {s.get('low',0)}",
            S["body"]
        ))
        story.append(Spacer(1, 3*mm))

        cve_rows = [["CVE ID", "Package", "Version", "Severity", "Summary"]]
        for f in sorted(scan["cve_findings"],
                        key=lambda x: {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}.get(x.get("severity","LOW"),3))[:25]:
            cve_rows.append([
                f.get("cve_id","—"), f.get("package","—"), f.get("version","—"),
                f.get("severity","—"),
                Paragraph(f.get("summary","")[:80], S["small"]),
            ])
        story.append(table(cve_rows, [W*0.17, W*0.13, W*0.09, W*0.10, W*0.51]))

    # ── Compliance findings ───────────────────────────────────────────────────
    if comp and comp.get("failed_findings"):
        story.append(PageBreak())
        fw = comp.get("framework", "CIS")
        story.append(Paragraph(f"{fw} Compliance Findings", S["h1"]))
        story.append(Paragraph(
            f"Score: {comp.get('score',0)}%  ·  "
            f"Passed: {comp.get('passed',0)}  ·  Failed: {comp.get('failed',0)}  ·  "
            f"Risk: {comp.get('risk_level','—').upper()}",
            S["body"]
        ))
        story.append(Spacer(1, 3*mm))
        comp_rows = [["Check ID", "Category", "Check Name", "Severity"]]
        for f in comp["failed_findings"][:30]:
            comp_rows.append([
                f.get("id","—"), f.get("category","—"),
                Paragraph(f.get("name","—"), S["small"]),
                f.get("severity","—").upper(),
            ])
        story.append(table(comp_rows, [W*0.16, W*0.16, W*0.50, W*0.18]))

    # ── Recommendations ───────────────────────────────────────────────────────
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("Prioritised Recommendations", S["h1"]))
    recs = []
    if scan:
        ss = scan.get("summary", {})
        if ss.get("critical", 0) > 0:
            recs.append(("CRITICAL", f"Patch {ss['critical']} critical CVE(s) immediately — active exploitation risk"))
        if ss.get("high", 0) > 0:
            recs.append(("HIGH", f"Patch {ss['high']} high-severity CVE(s) within 72 hours"))
    if comp and comp.get("score", 100) < 70:
        recs.append(("HIGH", f"Compliance {comp.get('score')}% below 70% — run security hardening playbook"))
    if health < 70:
        recs.append(("MEDIUM", f"Health score {health}/100 below threshold — investigate resource utilization"))
    if not recs:
        recs.append(("LOW", "No critical recommendations — maintain regular scan schedule"))

    rec_rows = [["Priority", "Recommendation"]]
    rec_rows.extend(recs)
    story.append(table(rec_rows, [W*0.14, W*0.86]))

    # ── Signature ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.4, color=C_BORDER))
    story.append(Spacer(1, 3*mm))
    sig_data = f"{node_name}:{datetime.utcnow().isoformat()}:{health}"
    sig      = hashlib.sha256(sig_data.encode()).hexdigest()
    story.append(Paragraph(f"Report signature (SHA-256): {sig[:32]}…{sig[-8:]}", S["small"]))
    story.append(Paragraph(
        "This report was generated automatically by JENIX Enterprise v3.0. "
        "All findings should be verified by a qualified security professional.",
        S["small"]
    ))

    doc.build(story)
    pdf = buf.getvalue()
    if output_path:
        with open(output_path, "wb") as fh:
            fh.write(pdf)
    return pdf
