from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db import get_db, Machine, Report, Metric, AuditLog, Alert
from auth import get_current_user, require_operator, User
from datetime import datetime
import os, textwrap, jwt, csv, re
from routes.audit_trail_report import get_events_from_db, build_audit_trail_pdf, write_audit_csv, risk_band as _shared_risk_band

router = APIRouter(prefix="/reports", tags=["reports"])
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Spec section 3.3 SYSTEM HEALTH default thresholds (also matches the CPU chart's
# own "Threshold reference: warning at 85%, critical at 95%" caption elsewhere in
# this file). Added Sept 5 2026 to fix the previously binary High/OK status column,
# which used different, non-spec per-metric thresholds (80/85/90).
HEALTH_WARNING_THRESHOLD = 85
HEALTH_CRITICAL_THRESHOLD = 95

def _compute_risk_score(metrics: list, critical_count: int, warning_count: int) -> int:
    """
    Weighted risk score. Each of CPU/RAM/Disk contributes up to 30 points,
    ramping from 0 at half its own "High" threshold (80% CPU, 85% RAM, 90%
    Disk) up to the full 30 points at that threshold -- so usage comfortably
    below "High" contributes ~nothing, and a single maxed-out metric alone
    cannot reach 100. This replaces the previous count-only formula
    (critical*20 + warning*5), which let a handful of alerts saturate the
    score regardless of actual system health. Alerts contribute up to the
    remaining 10 points of headroom.
    """
    if metrics:
        avg_cpu  = sum(m["cpu"]  for m in metrics) / len(metrics)
        avg_ram  = sum(m["ram"]  for m in metrics) / len(metrics)
        avg_disk = sum(m["disk"] for m in metrics) / len(metrics)
    else:
        avg_cpu = avg_ram = avg_disk = 0

    def _metric_pts(value, high_threshold):
        half = high_threshold / 2
        return min(30, max(0, (value - half) / half * 30))

    cpu_pts   = _metric_pts(avg_cpu, 80)
    ram_pts   = _metric_pts(avg_ram, 85)
    disk_pts  = _metric_pts(avg_disk, 90)
    alert_pts = min(10, critical_count * 4 + warning_count * 1)

    return round(min(100, cpu_pts + ram_pts + disk_pts + alert_pts))


def _generate_pdf(machine: Machine, metrics: list, logs: list,
                  alerts: list) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable)
    from reportlab.lib.units import cm

    fname    = f"jenix_report_{machine.hostname}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath    = os.path.join(REPORTS_DIR, fname)
    doc      = SimpleDocTemplate(fpath, pagesize=A4,
                                 leftMargin=2*cm, rightMargin=2*cm,
                                 topMargin=2*cm,  bottomMargin=2*cm)
    styles   = getSampleStyleSheet()
    story    = []

    # Styles
    title_style = ParagraphStyle("title", fontSize=24, textColor=colors.HexColor("#00bcd4"),
                                  spaceAfter=6, fontName="Helvetica-Bold")
    h2_style    = ParagraphStyle("h2", fontSize=14, textColor=colors.HexColor("#00bcd4"),
                                  spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold")
    body_style  = styles["BodyText"]
    warn_style  = ParagraphStyle("warn", fontSize=10, textColor=colors.HexColor("#ff9800"),
                                  fontName="Helvetica-Bold")
    crit_style  = ParagraphStyle("crit", fontSize=10, textColor=colors.HexColor("#f44336"),
                                  fontName="Helvetica-Bold")
    small_style = ParagraphStyle("small", fontSize=8, textColor=colors.HexColor("#999999"),
                                  fontName="Helvetica")
    h3_style    = ParagraphStyle("h3", fontSize=11, textColor=colors.HexColor("#ffffff"),
                                  spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold")

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("JENIX Enterprise", title_style))
    story.append(Paragraph("Security & Compliance Report", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#00bcd4")))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"<b>Machine:</b> {machine.hostname} ({machine.ip})", body_style))
    story.append(Paragraph(f"<b>OS:</b> {machine.os_name}", body_style))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", body_style))
    story.append(Spacer(1, 1*cm))

    # ── Executive Summary ──────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    critical_count = sum(1 for a in alerts if a["level"] == "critical")
    warning_count  = sum(1 for a in alerts if a["level"] == "warning")
    risk_score     = _compute_risk_score(metrics, critical_count, warning_count)

    risk_band, risk_color = _shared_risk_band(risk_score)
    story.append(Paragraph(
        f'Overall Risk Score: <font color="{risk_color}"><b>{risk_score}/100 — {risk_band}</b></font>', body_style))
    story.append(Paragraph(f"Critical Alerts: {critical_count}", body_style))
    story.append(Paragraph(f"Warning Alerts:  {warning_count}", body_style))
    if risk_band == "CRITICAL RISK":
        band_sentence = ("Immediate action is required. The system shows severe, sustained resource "
                          "exhaustion and/or a high volume of critical alerts, indicating a high "
                          "likelihood of imminent service degradation or an unplanned outage.")
    elif risk_band == "HIGH RISK":
        band_sentence = ("Immediate action is recommended. Multiple critical alerts and/or "
                          "sustained resource exhaustion indicate a high likelihood of service "
                          "degradation or an unplanned outage if left unaddressed.")
    elif risk_band == "ELEVATED RISK":
        band_sentence = ("The system has active critical alerts that require prompt "
                          "investigation. Sustained resource exhaustion increases the likelihood "
                          "of service degradation or an unplanned outage if left unaddressed.")
    elif risk_band == "MODERATE RISK":
        band_sentence = ("The system shows early signs of elevated resource usage and/or a small "
                          "number of alerts. No immediate action is required, but continued "
                          "monitoring is recommended.")
    else:
        band_sentence = "The system appears to be in acceptable health. Continue regular scheduled scans."

    summary = (
        f"This report was automatically generated by JENIX Enterprise for {machine.hostname}. "
        f"The system scored {risk_score}/100 on the risk scale ({risk_band}). {band_sentence}"
    )
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(summary, body_style))
    story.append(Spacer(1, 0.5*cm))

    # ── System Health ──────────────────────────────────────────────────────
    story.append(Paragraph("System Health", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    def _trend(metric_list, key):
        if len(metric_list) < 4:
            return "→ flat"
        half = len(metric_list) // 2
        avg_recent = sum(m[key] for m in metric_list[:half]) / half
        avg_older  = sum(m[key] for m in metric_list[half:]) / (len(metric_list) - half)
        delta = avg_recent - avg_older
        if delta > 5:
            return "↑ rising"
        if delta < -5:
            return "↓ falling"
        return "→ stable"

    if metrics:
        avg_cpu  = sum(m["cpu"]  for m in metrics) / len(metrics)
        avg_ram  = sum(m["ram"]  for m in metrics) / len(metrics)
        avg_disk = sum(m["disk"] for m in metrics) / len(metrics)

        def _health_status(value):
            if value >= HEALTH_CRITICAL_THRESHOLD:
                return "⛔ CRITICAL"
            if value >= HEALTH_WARNING_THRESHOLD:
                return "⚠ WATCH"
            return "✓ OK"

        health_data = [
            ["Metric", "Average", "Trend", "Status"],
            ["CPU Usage",  f"{avg_cpu:.1f}%",  _trend(metrics, "cpu"),  _health_status(avg_cpu)],
            ["RAM Usage",  f"{avg_ram:.1f}%",  _trend(metrics, "ram"),  _health_status(avg_ram)],
            ["Disk Usage", f"{avg_disk:.1f}%", _trend(metrics, "disk"), _health_status(avg_disk)],
        ]
        t = Table(health_data, colWidths=[5*cm, 3*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e1e2e")),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.HexColor("#00bcd4")),
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),
             [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
            ("TEXTCOLOR",    (0,1), (-1,-1), colors.white),
            ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
            ("ALIGN",        (0,0), (-1,-1), "CENTER"),
            ("PADDING",      (0,0), (-1,-1), 6),
        ]))
        story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # ── Alerts (grouped & deduplicated) ───────────────────────────────────
    import re as _re
    from reportlab.graphics.shapes import Drawing, Line
    from reportlab.graphics.charts.lineplots import LinePlot

    def _extract_pct(message):
        m = _re.search(r"(\d+\.?\d*)\s*%", message)
        return float(m.group(1)) if m else None

    def _recommended_action(atype, level, occurrences, pct_min, pct_max):
        if atype == "cpu":
            if level == "critical":
                return (f"CPU utilization reached {pct_max:.1f}% on {occurrences} separate "
                        f"occasion(s) (peak {pct_max:.1f}%). Identify the responsible process "
                        f"(top/htop, or a scheduled profiling capture), evaluate whether this "
                        f"reflects legitimate load vs. a runaway/looping process, and consider "
                        f"CPU limits or autoscaling if this is expected peak load.")
            return (f"CPU trended into warning range {occurrences} time(s) "
                    f"({pct_min:.1f}-{pct_max:.1f}%). Monitor for escalation into critical "
                    f"territory; no immediate action required if isolated.")
        if atype == "ram":
            if level == "critical":
                return (f"RAM usage reached {pct_max:.1f}% on {occurrences} occasion(s). Check "
                        f"for memory leaks, restart the offending service, or increase available RAM.")
            return (f"RAM trended into warning range {occurrences} time(s) "
                    f"({pct_min:.1f}-{pct_max:.1f}%). Monitor for escalation.")
        if atype == "disk":
            if level == "critical":
                return (f"Disk usage reached {pct_max:.1f}%, above the critical threshold. Free "
                        f"space urgently, review log rotation and snapshot retention, and set an "
                        f"automated cleanup policy before available headroom is exhausted.")
            return (f"Disk trended into warning range {occurrences} time(s) "
                    f"({pct_min:.1f}-{pct_max:.1f}%). Monitor for escalation.")
        if atype == "offline":
            return (f"Machine went offline {occurrences} time(s). Confirm this reflects expected "
                    f"maintenance/reboots vs. an unplanned outage or connectivity issue.")
        return f"{occurrences} {level} {atype} alert(s) recorded. Review for pattern."

    story.append(Paragraph("SECURITY ALERTS (grouped & deduplicated)", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))

    if alerts:
        groups = {}
        for a in alerts:
            groups.setdefault((a["level"], a["type"]), []).append(a)

        group_rows = []
        for (level, atype), items in groups.items():
            pcts = [p for p in (_extract_pct(x["message"]) for x in items) if p is not None]
            pct_min, pct_max = (min(pcts), max(pcts)) if pcts else (None, None)
            rng = f"{pct_min:.1f}% - {pct_max:.1f}%" if pcts else "—"
            action_text = _recommended_action(atype, level, len(items), pct_min, pct_max)
            group_rows.append((level, atype, len(items), rng, action_text))

        sev_order = {"critical": 0, "warning": 1}
        group_rows.sort(key=lambda r: (sev_order.get(r[0], 2), -r[2]))

        alert_body_style = ParagraphStyle("alertbody", parent=body_style,
                                           textColor=colors.white, fontSize=8, leading=10)
        alert_data = [["Severity", "Category", "Occurrences", "Range", "Recommended Action"]]
        for level, atype, count, rng, action_text in group_rows:
            alert_data.append([level.upper(), atype.upper(), f"{count}x", rng,
                                Paragraph(action_text, alert_body_style)])

        t_alerts = Table(alert_data, colWidths=[2.2*cm, 2.2*cm, 2.2*cm, 2.8*cm, 6.6*cm])
        t_alerts.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1), (-1,-1),
             [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
            ("TEXTCOLOR",     (0,1), (-1,-1), colors.white),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("PADDING",       (0,0), (-1,-1), 5),
        ]))
        story.append(t_alerts)
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            f"{len(alerts)} raw events condensed into {len(group_rows)} categories for "
            f"readability. Full uncollapsed event list available in the CSV export.", small_style))
        story.append(Spacer(1, 0.4*cm))

        cpu_series = [p for p in (_extract_pct(x["message"]) for x in reversed(alerts)
                                   if x["type"] == "cpu") if p is not None]
        if cpu_series:
            story.append(Paragraph("CPU reading at each alert event (chronological)", h3_style))
            drawing = Drawing(430, 160)
            plot = LinePlot()
            plot.x, plot.y = 40, 20
            plot.height, plot.width = 120, 350
            plot.data = [list(enumerate(cpu_series))]
            plot.lines[0].strokeColor = colors.HexColor("#00bcd4")
            plot.lines[0].strokeWidth = 1.5
            plot.xValueAxis.valueMin = 0
            plot.xValueAxis.valueMax = max(len(cpu_series) - 1, 1)
            plot.yValueAxis.valueMin = 0
            plot.yValueAxis.valueMax = 100
            drawing.add(plot)
            warn_y = plot.y + (85/100)*plot.height
            crit_y = plot.y + (95/100)*plot.height
            drawing.add(Line(plot.x, warn_y, plot.x+plot.width, warn_y,
                              strokeColor=colors.HexColor("#ff9800"), strokeDashArray=[3,2]))
            drawing.add(Line(plot.x, crit_y, plot.x+plot.width, crit_y,
                              strokeColor=colors.HexColor("#f44336"), strokeDashArray=[3,2]))
            story.append(drawing)
            story.append(Paragraph("Threshold reference: warning at 85%, critical at 95%.", small_style))
            story.append(Spacer(1, 0.4*cm))
    else:
        story.append(Paragraph("No alerts recorded.", body_style))
    story.append(Spacer(1, 0.3*cm))

    # ── Audit Trail ────────────────────────────────────────────────────────
    story.append(Paragraph("Audit Trail (integrity-fingerprinted)", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    def _scope_of(action):
        if action.startswith("fleet_"):
            return "Fleet"
        if action in ("node_approved", "node_rejected", "node_redirect_pending", "registered"):
            return "System"
        return "Machine"

    if logs:
        cell_wrap_style = ParagraphStyle("logcell", fontSize=8, leading=10,
                                          textColor=colors.white, fontName="Helvetica")
        log_data = [["Timestamp", "Action", "Scope", "Detail", "Status", "Fingerprint"]]
        for l in logs[:15]:
            log_data.append([
                Paragraph(l["timestamp"][:16], cell_wrap_style),
                Paragraph(l["action"], cell_wrap_style),
                Paragraph(_scope_of(l["action"]), cell_wrap_style),
                Paragraph(textwrap.shorten(l["detail"], 30), cell_wrap_style),
                Paragraph(l["status"], cell_wrap_style),
                Paragraph((l.get("content_hash") or "")[:8], cell_wrap_style),
            ])
        t2 = Table(log_data, colWidths=[3*cm, 3.4*cm, 1.6*cm, 5*cm, 1.6*cm, 2.4*cm])
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1), (-1,-1),
             [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("PADDING",       (0,0), (-1,-1), 5),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("No audit entries found.", body_style))

    doc.build(story)
    return fname, fpath

# ── Generate report ────────────────────────────────────────────────────────
def _generate_fleet_pdf(machines_data: list) -> tuple:
    """
    machines_data: list of dicts, each shaped like:
      {"machine": Machine, "metrics": [...], "logs": [...], "alerts": [...]}
    Produces one multi-page PDF covering the whole fleet: an executive
    summary rollup, then a per-machine section for each machine.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, PageBreak)
    from reportlab.lib.units import cm

    fname = f"jenix_fleet_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath = os.path.join(REPORTS_DIR, fname)
    doc   = SimpleDocTemplate(fpath, pagesize=A4,
                              leftMargin=2*cm, rightMargin=2*cm,
                              topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    title_style = ParagraphStyle("title", fontSize=24, textColor=colors.HexColor("#00bcd4"),
                                  spaceAfter=6, fontName="Helvetica-Bold")
    h2_style    = ParagraphStyle("h2", fontSize=14, textColor=colors.HexColor("#00bcd4"),
                                  spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold")
    h3_style    = ParagraphStyle("h3", fontSize=12, textColor=colors.HexColor("#ffffff"),
                                  spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
    body_style  = styles["BodyText"]
    warn_style  = ParagraphStyle("warn", fontSize=10, textColor=colors.HexColor("#ff9800"),
                                  fontName="Helvetica-Bold")
    crit_style  = ParagraphStyle("crit", fontSize=10, textColor=colors.HexColor("#f44336"),
                                  fontName="Helvetica-Bold")

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("JENIX Enterprise", title_style))
    story.append(Paragraph("Fleet-Wide Security & Compliance Report", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#00bcd4")))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"<b>Machines Covered:</b> {len(machines_data)}", body_style))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", body_style))
    story.append(Spacer(1, 1*cm))

    # ── Fleet Executive Summary ───────────────────────────────────────────
    story.append(Paragraph("Fleet Executive Summary", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))

    total_critical = 0
    total_warning  = 0
    per_machine_scores = []
    for md in machines_data:
        m, alerts = md["machine"], md["alerts"]
        c = sum(1 for a in alerts if a["level"] == "critical")
        w = sum(1 for a in alerts if a["level"] == "warning")
        total_critical += c
        total_warning  += w
        score = _compute_risk_score(md["metrics"], c, w)
        per_machine_scores.append((m.hostname, score, c, w))

    fleet_avg_score = (sum(s for _, s, _, _ in per_machine_scores) / len(per_machine_scores)) if per_machine_scores else 0
    fleet_risk_color = "#f44336" if fleet_avg_score > 60 else "#ff9800" if fleet_avg_score > 20 else "#4caf50"

    story.append(Paragraph(
        f'Fleet Average Risk Score: <font color="{fleet_risk_color}"><b>{fleet_avg_score:.0f}/100</b></font>', body_style))
    story.append(Paragraph(f"Total Critical Alerts Across Fleet: {total_critical}", body_style))
    story.append(Paragraph(f"Total Warning Alerts Across Fleet: {total_warning}", body_style))
    story.append(Spacer(1, 0.3*cm))

    summary = (
        f"This report was automatically generated by JENIX Enterprise covering {len(machines_data)} "
        f"machine(s) across the fleet. The fleet-wide average risk score is {fleet_avg_score:.0f}/100. "
        f"{'Immediate action is recommended on one or more machines.' if fleet_avg_score > 60 else 'The fleet appears to be in acceptable health overall.'}"
    )
    story.append(Paragraph(summary, body_style))
    story.append(Spacer(1, 0.5*cm))

    # ── Per-Machine Risk Rollup Table ─────────────────────────────────────
    story.append(Paragraph("Per-Machine Risk Overview", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    if per_machine_scores:
        rollup_data = [["Machine", "Risk Score", "Critical", "Warning"]]
        for hostname, score, c, w in per_machine_scores:
            rollup_data.append([hostname, f"{score}/100", str(c), str(w)])
        t = Table(rollup_data, colWidths=[6*cm, 4*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e1e2e")),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.HexColor("#00bcd4")),
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),
             [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
            ("TEXTCOLOR",    (0,1), (-1,-1), colors.white),
            ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
            ("ALIGN",        (0,0), (-1,-1), "CENTER"),
            ("PADDING",      (0,0), (-1,-1), 6),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No machines included in this report.", body_style))

    # ── Per-Machine Detail Sections ────────────────────────────────────────
    for md in machines_data:
        m, metrics, logs, alerts = md["machine"], md["metrics"], md["logs"], md["alerts"]
        story.append(PageBreak())
        story.append(Paragraph(f"Machine Detail: {m.hostname}", h2_style))
        story.append(HRFlowable(width="100%", color=colors.HexColor("#00bcd4")))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"<b>Machine:</b> {m.hostname} ({m.ip})", body_style))
        story.append(Paragraph(f"<b>OS:</b> {m.os_name}", body_style))
        story.append(Spacer(1, 0.4*cm))

        # System health
        story.append(Paragraph("System Health", h3_style))
        if metrics:
            avg_cpu  = sum(x["cpu"]  for x in metrics) / len(metrics)
            avg_ram  = sum(x["ram"]  for x in metrics) / len(metrics)
            avg_disk = sum(x["disk"] for x in metrics) / len(metrics)
            health_data = [
                ["Metric", "Average", "Status"],
                ["CPU Usage",  f"{avg_cpu:.1f}%",  "High" if avg_cpu > 80  else "OK"],
                ["RAM Usage",  f"{avg_ram:.1f}%",  "High" if avg_ram > 85  else "OK"],
                ["Disk Usage", f"{avg_disk:.1f}%", "High" if avg_disk > 90 else "OK"],
            ]
            t2 = Table(health_data, colWidths=[6*cm, 4*cm, 4*cm])
            t2.setStyle(TableStyle([
                ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e1e2e")),
                ("TEXTCOLOR",    (0,0), (-1,0), colors.HexColor("#00bcd4")),
                ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),
                 [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
                ("TEXTCOLOR",    (0,1), (-1,-1), colors.white),
                ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
                ("ALIGN",        (0,0), (-1,-1), "CENTER"),
                ("PADDING",      (0,0), (-1,-1), 6),
            ]))
            story.append(t2)
        else:
            story.append(Paragraph("No metrics recorded for this machine.", body_style))
        story.append(Spacer(1, 0.4*cm))

        # Alerts
        story.append(Paragraph("Security Alerts", h3_style))
        if alerts:
            for a in alerts:
                style = crit_style if a["level"] == "critical" else warn_style
                story.append(Paragraph(
                    f"[{a['level'].upper()}] {a['type'].upper()} — {a['message']}", style))
        else:
            story.append(Paragraph("No alerts recorded.", body_style))
        story.append(Spacer(1, 0.4*cm))

        # Recent audit trail (shorter than single-machine report to keep fleet PDF manageable)
        story.append(Paragraph("Recent Audit Trail", h3_style))
        if logs:
            log_data = [["Timestamp", "Action", "Detail", "Status"]]
            for l in logs[:8]:
                log_data.append([
                    l["timestamp"][:16],
                    l["action"],
                    textwrap.shorten(l["detail"], 35),
                    l["status"]
                ])
            t3 = Table(log_data, colWidths=[4*cm, 3*cm, 6.5*cm, 3*cm])
            t3.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
                ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS",(0,1), (-1,-1),
                 [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
                ("TEXTCOLOR",     (0,1), (-1,-1), colors.white),
                ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
                ("FONTSIZE",      (0,0), (-1,-1), 8),
                ("PADDING",       (0,0), (-1,-1), 5),
            ]))
            story.append(t3)
        else:
            story.append(Paragraph("No audit entries found for this machine.", body_style))

    doc.build(story)
    return fname, fpath


# ── Generate fleet-wide report ──────────────────────────────────────────────
class FleetReportRequest(BaseModel):
    machine_ids: list[int] = []  # empty/omitted = all machines

@router.post("/fleet")
def generate_fleet_report(body: FleetReportRequest = FleetReportRequest(),
                          db: Session = Depends(get_db),
                          current_user: User = Depends(require_operator)):
    machine_ids = body.machine_ids
    """
    Generate one bulk PDF covering multiple machines.
    If machine_ids is omitted or empty, includes ALL machines in the fleet.
    """
    query = db.query(Machine)
    if machine_ids:
        query = query.filter(Machine.id.in_(machine_ids))
    machines = query.all()

    if not machines:
        raise HTTPException(status_code=404, detail="No machines found for the given criteria")

    machines_data = []
    for m in machines:
        metrics = db.query(Metric)\
                    .filter(Metric.machine_id == m.id)\
                    .order_by(Metric.timestamp.desc())\
                    .limit(100).all()
        metrics_list = [{"cpu": x.cpu, "ram": x.ram, "disk": x.disk} for x in metrics]

        logs = db.query(AuditLog)\
                 .filter(AuditLog.machine_id == m.id)\
                 .order_by(AuditLog.timestamp.desc())\
                 .limit(20).all()
        logs_list = [{"action": l.action, "detail": l.detail,
                      "status": l.status, "timestamp": l.timestamp.isoformat()} for l in logs]

        alerts = db.query(Alert)\
                   .filter(Alert.machine_id == m.id)\
                   .order_by(Alert.timestamp.desc())\
                   .limit(20).all()
        alerts_list = [{"level": a.level, "type": a.type,
                        "message": a.message} for a in alerts]

        machines_data.append({
            "machine": m, "metrics": metrics_list,
            "logs": logs_list, "alerts": alerts_list
        })

    fname, fpath = _generate_fleet_pdf(machines_data)
    size_kb = os.path.getsize(fpath) / 1024

    report = Report(
        machine_id  = 0,  # sentinel: fleet-wide report, not tied to a single machine
        machine_ids = ",".join(str(m.id) for m in machines),
        report_type = "fleet",
        filename    = fname,
        filepath    = fpath,
        size_kb     = round(size_kb, 1)
    )
    db.add(report); db.commit(); db.refresh(report)

    return {
        "report_id": report.id,
        "filename": fname,
        "size_kb": report.size_kb,
        "machines_included": [m.hostname for m in machines]
    }


def _generate_audit_pdf(logs: list, machines: dict, users: dict) -> tuple:
    import hashlib, json
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, PageBreak)
    from reportlab.lib.units import cm

    fname = f"jenix_audit_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath = os.path.join(REPORTS_DIR, fname)
    doc = SimpleDocTemplate(fpath, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", fontSize=24, textColor=colors.HexColor("#00bcd4"),
                                 spaceAfter=6, fontName="Helvetica-Bold")
    h2_style = ParagraphStyle("h2", fontSize=14, textColor=colors.HexColor("#00bcd4"),
                              spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold")
    body_style = styles["BodyText"]
    small_style = ParagraphStyle("small", fontSize=8, textColor=colors.HexColor("#999999"),
                                 fontName="Helvetica")

    def _fingerprint(l):
        data = {
            "id": l.id, "machine_id": l.machine_id, "user_id": l.user_id,
            "action": l.action, "detail": l.detail, "status": l.status,
            "timestamp": l.timestamp.isoformat(),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("JENIX Enterprise", title_style))
    story.append(Paragraph("Audit Trail Report", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#00bcd4")))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("<b>Scope:</b> All machines, full audit history", body_style))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", body_style))
    story.append(Spacer(1, 1*cm))

    story.append(Paragraph("Executive Summary", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))

    total = len(logs)
    ok_count   = sum(1 for l in logs if l.status == "ok")
    warn_count = sum(1 for l in logs if l.status == "warning")
    crit_count = sum(1 for l in logs if l.status == "critical")
    first_ts = min((l.timestamp for l in logs), default=None)
    last_ts  = max((l.timestamp for l in logs), default=None)

    story.append(Paragraph(f"Total Log Entries: {total}", body_style))
    story.append(Paragraph(
        f"Date Range: {first_ts.strftime('%Y-%m-%d %H:%M') if first_ts else 'N/A'} "
        f"to {last_ts.strftime('%Y-%m-%d %H:%M') if last_ts else 'N/A'}", body_style))
    story.append(Paragraph(f"OK: {ok_count}   Warning: {warn_count}   Critical: {crit_count}", body_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "Each entry below includes a SHA256 content fingerprint computed from its recorded "
        "fields (ID, machine, user, action, detail, status, timestamp). Recomputing this hash "
        "from an exported entry and comparing it to the value shown confirms the entry's content "
        "has not changed since export. It is a per-entry content fingerprint, not a cryptographic "
        "chain linking entries together.", small_style))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Activity Breakdown by Action Type", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    action_counts = {}
    for l in logs:
        action_counts[l.action] = action_counts.get(l.action, 0) + 1
    action_data = [["Action Type", "Count"]] + [
        [a, c] for a, c in sorted(action_counts.items(), key=lambda x: -x[1])
    ]
    t_actions = Table(action_data, colWidths=[10*cm, 4*cm])
    t_actions.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),
         [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
        ("TEXTCOLOR",     (0,1), (-1,-1), colors.white),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("PADDING",       (0,0), (-1,-1), 6),
    ]))
    story.append(t_actions)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Activity Breakdown by Status", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    status_data = [["Status", "Count"], ["ok", ok_count], ["warning", warn_count], ["critical", crit_count]]
    t_status = Table(status_data, colWidths=[10*cm, 4*cm])
    t_status.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),
         [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
        ("TEXTCOLOR",     (0,1), (-1,-1), colors.white),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("PADDING",       (0,0), (-1,-1), 6),
    ]))
    story.append(t_status)

    story.append(PageBreak())
    story.append(Paragraph("Full Audit Log", h2_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#333333")))
    story.append(Spacer(1, 0.3*cm))
    if logs:
        log_data = [["Timestamp", "Machine", "User", "Action", "Detail", "Status", "Fingerprint"]]
        for l in logs:
            log_data.append([
                l.timestamp.strftime("%Y-%m-%d %H:%M"),
                machines.get(l.machine_id, "System"),
                users.get(l.user_id, "System"),
                l.action,
                textwrap.shorten(l.detail, 35),
                l.status,
                _fingerprint(l)[:12] + "...",
            ])
        t_log = Table(log_data, colWidths=[2.6*cm, 2.4*cm, 2*cm, 2.6*cm, 4.5*cm, 1.8*cm, 2.6*cm],
                     repeatRows=1)
        t_log.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#1e1e2e")),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.HexColor("#00bcd4")),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1), (-1,-1),
             [colors.HexColor("#2a2a3e"), colors.HexColor("#1e1e2e")]),
            ("TEXTCOLOR",     (0,1), (-1,-1), colors.white),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
            ("FONTSIZE",      (0,0), (-1,-1), 7),
            ("PADDING",       (0,0), (-1,-1), 4),
        ]))
        story.append(t_log)
    else:
        story.append(Paragraph("No audit entries found.", body_style))

    doc.build(story)
    return fname, fpath


@router.post("/audit")
def generate_audit_report(db: Session = Depends(get_db),
                          current_user: User = Depends(require_operator)):
    events = get_events_from_db(db)
    report_id = f"JX-{datetime.utcnow():%Y%m%d-%H%M%S}"
    generated_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    fname = f"jenix_audit_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    fpath = os.path.join(REPORTS_DIR, fname)
    build_audit_trail_pdf(events, report_id, generated_utc, fpath)
    size_kb = os.path.getsize(fpath) / 1024
    report  = Report(machine_id=0, report_type="audit",
                     filename=fname, filepath=fpath, size_kb=round(size_kb, 1))
    db.add(report); db.commit(); db.refresh(report)
    return {"report_id": report.id, "filename": fname,
            "size_kb": report.size_kb, "total_entries": len(events)}


@router.get("/audit/csv")
def export_audit_csv(machine_ids: str = Query(None), start: str = Query(None),
                     end: str = Query(None), db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    ids = [int(x) for x in machine_ids.split(",")] if machine_ids else None
    events = get_events_from_db(db, ids, start, end)
    fname = f"jenix_audit_export_{datetime.utcnow():%Y%m%d_%H%M%S}.csv"
    fpath = os.path.join(REPORTS_DIR, fname)
    write_audit_csv(events, fpath)
    return FileResponse(fpath, media_type="text/csv", filename="jenix_audit_trail_export.csv")


# ---------------------------------------------------------------------------
# Report B CSV export — full uncollapsed raw alert events (spec 3.5: "Full
# uncollapsed event list available in the CSV export"). Distinct from the
# grouped/deduplicated SECURITY ALERTS table shown in the PDF itself.
# ---------------------------------------------------------------------------
ALERTS_CSV_FIELDS = ["id", "timestamp", "machine", "severity", "category", "value_pct", "message"]


def _alert_pct(message):
    m = re.search(r"(\d+\.?\d*)\s*%", message)
    return f"{float(m.group(1)):.1f}" if m else ""


def write_alerts_csv(alerts, machine_hostname, out_path):
    rows = sorted(alerts, key=lambda a: a.timestamp, reverse=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALERTS_CSV_FIELDS)
        writer.writeheader()
        for a in rows:
            writer.writerow({
                "id": a.id,
                "timestamp": a.timestamp.strftime("%Y-%m-%d %H:%M") if a.timestamp else "",
                "machine": machine_hostname,
                "severity": a.level or "warning",
                "category": a.type,
                "value_pct": _alert_pct(a.message),
                "message": a.message,
            })
    return out_path


@router.get("/{machine_id}/alerts/csv")
def export_alerts_csv(machine_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    alerts = db.query(Alert).filter(Alert.machine_id == machine_id)\
               .order_by(Alert.timestamp.desc()).all()
    fname = f"jenix_alerts_export_{m.hostname}_{datetime.utcnow():%Y%m%d_%H%M%S}.csv"
    fpath = os.path.join(REPORTS_DIR, fname)
    write_alerts_csv(alerts, m.hostname, fpath)
    return FileResponse(fpath, media_type="text/csv", filename="jenix_alerts_export.csv")




@router.post("/{machine_id}")
def generate_report(machine_id: int,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_operator)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    metrics = db.query(Metric)\
                .filter(Metric.machine_id == machine_id)\
                .order_by(Metric.timestamp.desc())\
                .limit(100).all()
    metrics_list = [{"cpu": x.cpu, "ram": x.ram, "disk": x.disk} for x in metrics]
    logs    = db.query(AuditLog)\
                .filter(AuditLog.machine_id == machine_id)\
                .order_by(AuditLog.timestamp.desc())\
                .limit(20).all()
    logs_list = [{"id": l.id, "machine_id": l.machine_id, "user_id": l.user_id,
                  "action": l.action, "detail": l.detail, "status": l.status,
                  "timestamp": l.timestamp.isoformat(),
                  "content_hash": getattr(l, "content_hash", None)} for l in logs]
    alerts  = db.query(Alert)\
                .filter(Alert.machine_id == machine_id)\
                .order_by(Alert.timestamp.desc())\
                .limit(20).all()
    alerts_list = [{"level": a.level, "type": a.type,
                    "message": a.message} for a in alerts]
    fname, fpath = _generate_pdf(m, metrics_list, logs_list, alerts_list)
    size_kb = os.path.getsize(fpath) / 1024
    report  = Report(machine_id=machine_id, filename=fname,
                     filepath=fpath, size_kb=round(size_kb, 1))
    db.add(report); db.commit(); db.refresh(report)
    return {"report_id": report.id, "filename": fname,
            "size_kb": report.size_kb}

# ── List reports ───────────────────────────────────────────────────────────
@router.get("")
def list_reports(db: Session = Depends(get_db),
                 _:  User    = Depends(get_current_user)):
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return [{"id": r.id, "machine_id": r.machine_id,
             "filename": r.filename, "size_kb": r.size_kb,
             "created_at": r.created_at.isoformat()} for r in reports]

# ── Download report ────────────────────────────────────────────────────────
@router.get("/{report_id}/download")
def download_report(report_id: int,
                    request: Request,
                    token: str = Query(None),
                    db: Session = Depends(get_db)):
    """Accepts EITHER a normal Authorization header (used automatically by
    axios/fetch calls that already attach one) OR a ?token= query param
    (needed for plain <a href> browser download links, which cannot carry
    custom headers). Both paths validate through the same decode_token()
    logic every other authenticated route uses."""
    from auth import decode_token

    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header[7:]

    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(raw_token)
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    r = db.query(Report).filter(Report.id == report_id).first()
    if not r or not os.path.exists(r.filepath):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(r.filepath, media_type="application/pdf",
                        filename=r.filename)

# ── Delete report ──────────────────────────────────────────────────────────
@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db),
                  _: User = Depends(require_operator)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    if os.path.exists(r.filepath):
        os.remove(r.filepath)
    db.delete(r); db.commit()
    return {"ok": True}
