"""
JENIX Enterprise — Report A: AUDIT TRAIL REPORT (PDF) + CSV export.

Drop-in module for server/routes/reports.py. Implements JENIX_Report_Template_Prompt.md
section 2 (Report Type A) exactly: section order, table columns, sort rules, wording,
and computed-field logic. Also carries the 5-tier _risk_band() helper (spec section 3.2)
meant to REPLACE the currently-deployed 3-tier version so Report A and Report B agree on
the same bands (see note at bottom of file for the Report B patch).

WIRING THIS UP FOR REAL (the only things to change):
  1. Replace `get_events_from_db(...)` below with a real query against AuditLog
     (id, machine_id -> hostname, action, detail, status, timestamp, content_hash-as-fingerprint).
     Everything else (grouping, narrative, PDF, CSV) operates on the plain dict shape
     produced there and needs no changes.
  2. Add the two route stubs at the bottom to reports.py under the existing /api/reports
     prefix (POST /api/reports/audit already exists per the real registered routes list —
     point it at build_audit_trail_pdf() below; GET /api/reports/audit/csv is new).
  3. py_compile -> real import test -> live restart -> generate a real report -> read the
     real output, per standing verification discipline. Do not skip the last step.
"""
import csv
import hashlib
from collections import OrderedDict, defaultdict

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
    CondPageBreak, HRFlowable,
)
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.graphics.shapes import Drawing, Rect

# ---------------------------------------------------------------------------
# 5-tier risk band (spec section 3.2 "Risk score / label bands (keep consistent
# across reports)"). Report A itself never displays a risk score (it uses
# integrity-status counters instead — see build_executive_summary below), but
# this is the shared helper meant to replace the currently-deployed 3-tier
# _risk_band() in reports.py's Report B (_generate_pdf) so both report types
# agree on the same bands.
# ---------------------------------------------------------------------------
_RISK_BANDS = [
    (0, 24, "LOW RISK", "#2e7d32"),        # green
    (25, 49, "MODERATE RISK", "#c9a227"),  # amber/gold
    (50, 74, "ELEVATED RISK", "#e07b1a"),  # orange
    (75, 89, "HIGH RISK", "#d1421a"),      # red-orange
    (90, 100, "CRITICAL RISK", "#a3121a"), # dark red
]


def risk_band(score):
    """5-tier band per spec. Returns (label, hex_color)."""
    score = max(0, min(100, score))
    for lo, hi, label, color in _RISK_BANDS:
        if lo <= score <= hi:
            return label, color
    return "LOW RISK", "#2e7d32"  # unreachable, safe fallback


# ---------------------------------------------------------------------------
# Scope classification (spec 3.6, reused for Report A per the note "Same
# formatting rules as section 2.7"). Matches the real scope_of() helper
# already deployed in reports.py for the per-machine report.
# ---------------------------------------------------------------------------
_SYSTEM_ACTIONS = {"node_approved", "node_rejected", "node_redirect_pending", "registered", "passphrase_reset"}


def scope_of(action):
    if action.startswith("fleet"):
        return "Fleet"
    if action in _SYSTEM_ACTIONS:
        return "System"
    return "Machine"


# ---------------------------------------------------------------------------
# 2.1 Machines/Period summary line
# ---------------------------------------------------------------------------
def machines_period_summary(events):
    machines = sorted({e["machine"] for e in events})
    start = min(e["timestamp"] for e in events)[:10]
    end = max(e["timestamp"] for e in events)[:10]
    return {
        "machines_covered": ", ".join(machines),
        "event_count": len(events),
        "period_start": start,
        "period_end": end,
    }


# ---------------------------------------------------------------------------
# 2.2 EXECUTIVE SUMMARY — critical/warning/ok counters + narrative
# ---------------------------------------------------------------------------
def _window_and_date(rows):
    """Shared time-window formatting, reused so the executive summary reflects ALL
    critical events, not just the lead group's own window."""
    rows_sorted = sorted(rows, key=lambda r: r["timestamp"])
    earliest = rows_sorted[0]["timestamp"]
    latest = rows_sorted[-1]["timestamp"]
    same_day = earliest[:10] == latest[:10]
    if same_day:
        window = f"{earliest[11:]}-{latest[11:]}" if earliest != latest else earliest[11:]
    else:
        window = f"{earliest} - {latest}"
    return window, earliest[:10]


def build_executive_summary(events, notable_groups):
    critical = sum(1 for e in events if e["status"] == "critical")
    warning = sum(1 for e in events if e["status"] == "warning")
    ok = sum(1 for e in events if e["status"] == "ok")

    if notable_groups:
        # Fixed Sept 4 2026: window/date/machines/pattern now computed across ALL
        # critical events, not just the lead group - the old version could understate
        # the true time span and falsely imply every critical event shared one pattern.
        lead = notable_groups[0]
        crit_events = [e for e in events if e["status"] == "critical"]
        crit_window, crit_date = _window_and_date(crit_events) if crit_events else (lead["window"], lead["date"])
        machines_in_group = ", ".join(sorted({e["machine"] for e in crit_events})) or lead["machine"]
        actions_in_group = sorted({e["action"] for e in crit_events})
        if len(actions_in_group) == 1:
            pattern_desc = _describe_pattern(actions_in_group[0])
        else:
            pattern_desc = "multiple denied-action patterns (" + ", ".join(
                a.replace("_denied", "").replace("_", "-") for a in actions_in_group) + ")"
        narrative = (
            f"{critical} critical events were recorded, all reflecting {pattern_desc} "
            f"against {machines_in_group}, clustered within a window of {crit_window} on "
            f"{crit_date}. This pattern is consistent with {_interpretation(lead['action'])} "
            f"and warrants {_recommended_followup(lead['action'])}."
        )
    else:
        narrative = (
            "No critical audit events were recorded in this period. Activity across the "
            "covered machines remained within normal operational patterns."
        )

    return {
        "critical_count": critical,
        "warning_count": warning,
        "ok_count": ok,
        "narrative": narrative,
    }


def _describe_pattern(action):
    mapping = {
        "fleet_boost_denied": "repeated denied fleet-boost authorization attempts",
        "rollback_denied": "denied rollback attempts due to insufficient permissions",
        "fix_denied": "denied fix commands against an unreachable target service",
        "clean_denied": "denied clean commands while the target disk was busy",
    }
    return mapping.get(action, f"repeated '{action}' denial events")


def _interpretation(action):
    if action.endswith("_denied"):
        return "an authorization or permissions gap rather than a confirmed intrusion"
    return "an anomaly worth reviewing"


def _recommended_followup(action):
    if action == "fleet_boost_denied":
        return "confirming the passphrase reset that followed was performed by an authorized admin"
    if action.endswith("_denied"):
        return "reviewing the responsible user's permissions and confirming the denial was not an active intrusion attempt"
    return "a manual review"


# ---------------------------------------------------------------------------
# 2.3 EVENT BREAKDOWN BY STATUS
# ---------------------------------------------------------------------------
def event_breakdown_by_status(events):
    total = len(events)
    counts = OrderedDict([("critical", 0), ("warning", 0), ("ok", 0)])
    for e in events:
        counts[e["status"]] += 1
    rows = []
    for status in ("critical", "warning", "ok"):
        c = counts[status]
        share = (c / total * 100) if total else 0.0
        rows.append({"status": status, "count": c, "share": share})
    return rows


# ---------------------------------------------------------------------------
# 2.4 NOTABLE SECURITY EVENTS (critical, grouped by (action, machine))
# ---------------------------------------------------------------------------
def notable_security_events(events):
    groups = defaultdict(list)
    for e in events:
        if e["status"] == "critical":
            groups[(e["action"], e["machine"])].append(e)

    result = []
    for (action, machine), rows in groups.items():
        rows_sorted = sorted(rows, key=lambda r: r["timestamp"])
        earliest = rows_sorted[0]["timestamp"]
        latest = rows_sorted[-1]["timestamp"]
        same_day = earliest[:10] == latest[:10]
        if same_day:
            window = f"{earliest[11:]}-{latest[11:]}" if earliest != latest else earliest[11:]
        else:
            window = f"{earliest} - {latest}"
        result.append({
            "action": action,
            "machine": machine,
            "occurrences": len(rows),
            "window": window,
            "date": earliest[:10],
            "detail": rows_sorted[0]["detail"],
            "_earliest": earliest,
        })

    # "Sort groups by earliest occurrence, most recent first"
    result.sort(key=lambda g: g["_earliest"], reverse=True)
    for g in result:
        del g["_earliest"]
    return result


def denied_reset_retry_note(events, notable_groups):
    """Only include this note when the data actually shows a fail->reset->retry
    pattern (spec 2.4) — never fabricate it otherwise."""
    denied_groups = [g for g in notable_groups if g["action"].endswith("_denied")]
    if not denied_groups:
        return None
    lead = denied_groups[0]
    machine_events = sorted(
        [e for e in events if e["machine"] == lead["machine"]],
        key=lambda e: e["timestamp"],
    )
    # look for a reset/re-auth event immediately after the denied cluster on the same machine
    denied_ts = sorted(e["timestamp"] for e in events
                        if e["action"] == lead["action"] and e["machine"] == lead["machine"])
    last_denied = denied_ts[-1]
    follow_ups = [e for e in machine_events if e["timestamp"] > last_denied]
    reset_evt = next((e for e in follow_ups if "reset" in e["action"] or "reauthoriz" in e["detail"].lower()), None)
    retry_evt = next((e for e in follow_ups if e["action"] == lead["action"].replace("_denied", "") and e["status"] == "ok"), None)
    if reset_evt and retry_evt:
        return (
            f"All {lead['occurrences']} denied-action pairs occurred back-to-back on {lead['machine']} "
            f"during the same session, immediately followed by a successful passphrase reset and "
            f"re-authorization of each action. Recommend confirming this matches an expected admin workflow."
        )
    return None


# ---------------------------------------------------------------------------
# 2.5 TOP ACTIONS
# ---------------------------------------------------------------------------
def top_actions(events, limit=10):
    total = len(events)
    counts = defaultdict(int)
    for e in events:
        counts[e["action"]] += 1
    rows = [
        {"action": a, "occurrences": c, "share": c / total * 100}
        for a, c in counts.items()
    ]
    rows.sort(key=lambda r: r["occurrences"], reverse=True)
    return rows[:limit]


# ---------------------------------------------------------------------------
# 2.6 MACHINE ACTIVITY
# ---------------------------------------------------------------------------
def machine_activity(events):
    total = len(events)
    counts = defaultdict(int)
    for e in events:
        counts[e["machine"]] += 1
    rows = [
        {"machine": m, "events": c, "share": c / total * 100}
        for m, c in counts.items()
    ]
    rows.sort(key=lambda r: r["events"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# 2.7 FULL AUDIT TRAIL (every raw row, newest first, no grouping)
# ---------------------------------------------------------------------------
def full_audit_trail(events):
    # Fixed Sept 4 2026: PDF table's Fingerprint column is 68pt wide, sized for a short
    # display string, but real content_hash is a full 64-char SHA256 hex string - this
    # was wrapping across ~6 lines per row and bloating the report to 9 pages for 72
    # events. Truncated to 12 chars for THIS table only; write_audit_csv() builds its
    # own rows independently and is untouched, so the CSV still exports the full hash.
    rows = []
    for e in events:
        rows.append({
            "timestamp": e["timestamp"],
            "machine": e["machine"],
            "action": e["action"],
            "detail": e["detail"],
            "status": e["status"],
            "fingerprint": (e["fingerprint"] or "")[:12],
        })
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    return rows


PAGE_W, PAGE_H = letter
MARGIN_L = 40
MARGIN_R = 40
MARGIN_T = 46
MARGIN_B = 66
USABLE_W = PAGE_W - MARGIN_L - MARGIN_R  # 532pt

BRAND = colors.HexColor("#1a2b4c")
ORANGE = colors.HexColor("#e07b1a")
RED = colors.HexColor("#a3121a")
GREEN = colors.HexColor("#2e7d32")
GREY = colors.HexColor("#666666")
LIGHT_GREY = colors.HexColor("#f2f2f2")
RULE_GREY = colors.HexColor("#cccccc")

STATUS_COLOR = {"critical": RED, "warning": ORANGE, "ok": GREEN}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Brand", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=10, textColor=BRAND, leading=12))
    ss.add(ParagraphStyle("ReportTitle", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=18, textColor=colors.black, leading=22, spaceAfter=2))
    ss.add(ParagraphStyle("MetaLine", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=8.5, textColor=GREY, leading=11))
    ss.add(ParagraphStyle("SectionHeading", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=11, textColor=BRAND, leading=14, spaceBefore=4, spaceAfter=6))
    ss.add(ParagraphStyle("Narrative", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=9.5, leading=13.5, spaceAfter=4))
    ss.add(ParagraphStyle("Note", parent=ss["Normal"], fontName="Helvetica-Oblique",
                           fontSize=8.5, textColor=GREY, leading=11.5, spaceBefore=3))
    ss.add(ParagraphStyle("CellSmall", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=8, leading=10))
    ss.add(ParagraphStyle("CellMono", parent=ss["Normal"], fontName="Courier",
                           fontSize=7.5, leading=9.5))
    ss.add(ParagraphStyle("CellHeader", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=8, leading=10, textColor=colors.white))
    ss.add(ParagraphStyle("BigNum", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=26, alignment=TA_CENTER, leading=30))
    ss.add(ParagraphStyle("BigLabel", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=9, alignment=TA_CENTER, textColor=GREY, leading=11))
    ss.add(ParagraphStyle("TinyTag", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=7, alignment=TA_CENTER, textColor=RED, leading=8))
    ss.add(ParagraphStyle("GroupCaption", parent=ss["Normal"], fontName="Helvetica-Bold",
                           fontSize=8.5, alignment=TA_CENTER, textColor=BRAND, leading=10,
                           spaceBefore=4))
    return ss


def _distribution_bar(share_pct, width=180, height=8, color=ORANGE):
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=LIGHT_GREY, strokeColor=RULE_GREY, strokeWidth=0.5))
    filled = max(0, min(width, width * share_pct / 100.0))
    if filled > 0:
        d.add(Rect(0, 0, filled, height, fillColor=color, strokeColor=None))
    return d


def _table(data, col_widths, header_bg=BRAND, align_right_cols=None, small_font=8):
    align_right_cols = align_right_cols or []
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), small_font),
        ("FONTSIZE", (0, 1), (-1, -1), small_font),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for c in align_right_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


class NumberedCanvas(pdfcanvas.Canvas):
    """Draws the spec's footer block (fingerprint disclaimer + branding + Page X of Y)
    on every page, resolving the real total page count with a second pass."""

    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(self._pageNumber, total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, page_num, total):
        self.saveState()
        self.setStrokeColor(RULE_GREY)
        self.setLineWidth(0.5)
        y = MARGIN_B - 20
        self.line(MARGIN_L, y + 22, PAGE_W - MARGIN_R, y + 22)
        self.setFont("Helvetica-Oblique", 6.8)
        self.setFillColor(GREY)
        self.drawString(MARGIN_L, y + 12,
            "Fingerprint is a SHA-256 content hash of each entry, used to detect post-hoc "
            "tampering. It is not a hash-chain / blockchain-style sequence guarantee.")
        self.setFont("Helvetica", 7)
        self.drawString(MARGIN_L, y,
            "JENIX Enterprise \u2014 Self-Hosted Fleet Monitoring & Endpoint Management | "
            "This report is system-generated and intended for internal security review.")
        self.drawRightString(PAGE_W - MARGIN_R, y, f"Page {page_num} of {total}")
        self.restoreState()


def build_audit_trail_pdf(events, report_id, generated_utc, out_path):
    ss = _styles()
    story = []

    # ---- Header block (top of page 1) ----
    story.append(Paragraph("JENIX ENTERPRISE", ss["Brand"]))
    story.append(Paragraph("AUDIT TRAIL REPORT", ss["ReportTitle"]))
    story.append(Paragraph(f"Report ID: {report_id}", ss["MetaLine"]))
    story.append(Paragraph(f"Generated: {generated_utc} UTC", ss["MetaLine"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width=USABLE_W, thickness=1.4, color=BRAND))
    story.append(Spacer(1, 10))

    # ---- 2.1 Machines/Period summary line ----
    summary = machines_period_summary(events)
    meta_tbl = _table(
        [
            [Paragraph("MACHINES COVERED", ss["CellHeader"]),
             Paragraph("EVENT COUNT", ss["CellHeader"]),
             Paragraph("PERIOD", ss["CellHeader"])],
            [Paragraph(summary["machines_covered"], ss["CellSmall"]),
             Paragraph(f"{summary['event_count']} events", ss["CellSmall"]),
             Paragraph(f"{summary['period_start']} to {summary['period_end']}", ss["CellSmall"])],
        ],
        col_widths=[USABLE_W * 0.42, USABLE_W * 0.18, USABLE_W * 0.40],
        header_bg=colors.HexColor("#3a4a68"),
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 14))

    # ---- 2.2 EXECUTIVE SUMMARY ----
    notable = notable_security_events(events)
    exec_sum = build_executive_summary(events, notable)
    story.append(Paragraph("EXECUTIVE SUMMARY", ss["SectionHeading"]))

    tag_row = ["", "", ""]
    if exec_sum["critical_count"] > 0:
        tag_row = [Paragraph("REVIEW<br/>RECOMMENDED", ss["TinyTag"]), "", ""]
    counters_tbl = Table(
        [
            tag_row,
            [Paragraph(str(exec_sum["critical_count"]), ss["BigNum"]),
             Paragraph(str(exec_sum["warning_count"]), ss["BigNum"]),
             Paragraph(str(exec_sum["ok_count"]), ss["BigNum"])],
            [Paragraph("CRITICAL", ss["BigLabel"]),
             Paragraph("WARNING", ss["BigLabel"]),
             Paragraph("OK", ss["BigLabel"])],
        ],
        colWidths=[USABLE_W / 3.0] * 3,
    )
    counters_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TEXTCOLOR", (0, 1), (0, 1), RED if exec_sum["critical_count"] else colors.black),
        ("TEXTCOLOR", (1, 1), (1, 1), ORANGE if exec_sum["warning_count"] else colors.black),
        ("TEXTCOLOR", (2, 1), (2, 1), GREEN),
    ]))
    story.append(counters_tbl)
    story.append(Paragraph("INTEGRITY STATUS", ss["GroupCaption"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(exec_sum["narrative"], ss["Narrative"]))
    story.append(Spacer(1, 12))

    # ---- 2.3 EVENT BREAKDOWN BY STATUS ----
    story.append(CondPageBreak(110))
    breakdown_block = [Paragraph("EVENT BREAKDOWN BY STATUS", ss["SectionHeading"])]
    rows = [[Paragraph("Status", ss["CellHeader"]), Paragraph("Count", ss["CellHeader"]),
              Paragraph("Share", ss["CellHeader"]), Paragraph("Distribution", ss["CellHeader"])]]
    for r in event_breakdown_by_status(events):
        bar_color = STATUS_COLOR[r["status"]]
        rows.append([
            Paragraph(r["status"], ss["CellSmall"]),
            Paragraph(str(r["count"]), ss["CellSmall"]),
            Paragraph(f"{r['share']:.1f}%", ss["CellSmall"]),
            _distribution_bar(r["share"], width=250, color=bar_color),
        ])
    breakdown_block.append(_table(rows, col_widths=[90, 80, 80, 282], align_right_cols=[1, 2]))
    story.append(KeepTogether(breakdown_block))
    story.append(Spacer(1, 14))

    # ---- 2.4 NOTABLE SECURITY EVENTS (critical, grouped) ----
    story.append(CondPageBreak(120))
    notable_block = [Paragraph("NOTABLE SECURITY EVENTS (critical, grouped)", ss["SectionHeading"])]
    if notable:
        nrows = [[Paragraph("Action", ss["CellHeader"]), Paragraph("Machine", ss["CellHeader"]),
                   Paragraph("Occurrences", ss["CellHeader"]), Paragraph("Window", ss["CellHeader"]),
                   Paragraph("Detail", ss["CellHeader"])]]
        for g in notable:
            nrows.append([
                Paragraph(g["action"], ss["CellSmall"]),
                Paragraph(g["machine"], ss["CellSmall"]),
                Paragraph(f"{g['occurrences']}x", ss["CellSmall"]),
                Paragraph(g["window"], ss["CellSmall"]),
                Paragraph(g["detail"], ss["CellSmall"]),
            ])
        notable_block.append(_table(nrows, col_widths=[100, 75, 60, 100, 197]))
        note = denied_reset_retry_note(events, notable)
        if note:
            notable_block.append(Paragraph(note, ss["Note"]))
    else:
        notable_block.append(Paragraph(
            "No critical-status events were recorded in this period.", ss["Narrative"]))
    story.append(KeepTogether(notable_block))
    story.append(Spacer(1, 14))

    # ---- 2.5 TOP ACTIONS ----
    story.append(CondPageBreak(110))
    top_block = [Paragraph("TOP ACTIONS", ss["SectionHeading"])]
    trows = [[Paragraph("Action", ss["CellHeader"]), Paragraph("Occurrences", ss["CellHeader"]),
               Paragraph("Share of Total", ss["CellHeader"])]]
    for r in top_actions(events):
        trows.append([
            Paragraph(r["action"], ss["CellSmall"]),
            Paragraph(f"{r['occurrences']}x", ss["CellSmall"]),
            Paragraph(f"{r['share']:.1f}%", ss["CellSmall"]),
        ])
    top_block.append(_table(trows, col_widths=[260, 130, 142], align_right_cols=[1, 2]))
    story.append(KeepTogether(top_block))
    story.append(Spacer(1, 14))

    # ---- 2.6 MACHINE ACTIVITY ----
    story.append(CondPageBreak(110))
    mach_block = [Paragraph("MACHINE ACTIVITY", ss["SectionHeading"])]
    mrows = [[Paragraph("Machine", ss["CellHeader"]), Paragraph("Events", ss["CellHeader"]),
               Paragraph("Share of Total", ss["CellHeader"])]]
    for r in machine_activity(events):
        mrows.append([
            Paragraph(r["machine"], ss["CellSmall"]),
            Paragraph(f"{r['events']}x", ss["CellSmall"]),
            Paragraph(f"{r['share']:.1f}%", ss["CellSmall"]),
        ])
    mach_block.append(_table(mrows, col_widths=[220, 150, 162], align_right_cols=[1, 2]))
    story.append(KeepTogether(mach_block))
    story.append(Spacer(1, 14))

    # ---- 2.7 FULL AUDIT TRAIL ----
    story.append(CondPageBreak(140))
    trail = full_audit_trail(events)
    story.append(Paragraph(
        f"FULL AUDIT TRAIL ({len(trail)} events, integrity-fingerprinted, newest first)",
        ss["SectionHeading"]))
    frows = [[Paragraph("Timestamp", ss["CellHeader"]), Paragraph("Machine", ss["CellHeader"]),
               Paragraph("Action", ss["CellHeader"]), Paragraph("Detail", ss["CellHeader"]),
               Paragraph("Status", ss["CellHeader"]), Paragraph("Fingerprint", ss["CellHeader"])]]
    for r in trail:
        frows.append([
            Paragraph(r["timestamp"], ss["CellSmall"]),
            Paragraph(r["machine"], ss["CellSmall"]),
            Paragraph(r["action"], ss["CellSmall"]),
            Paragraph(r["detail"], ss["CellSmall"]),
            Paragraph(r["status"], ss["CellSmall"]),
            Paragraph(r["fingerprint"], ss["CellMono"]),
        ])
    story.append(_table(frows, col_widths=[76, 74, 92, 178, 44, 68]))

    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="JENIX Audit Trail Report",
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    return out_path



# ---------------------------------------------------------------------------
# CSV export — full uncollapsed raw event list, same source/sort as Full Audit Trail
# ---------------------------------------------------------------------------
CSV_FIELDS = ["id", "timestamp", "machine", "action", "scope", "detail", "status", "fingerprint"]


def write_audit_csv(events, out_path):
    rows = sorted(events, key=lambda e: e["timestamp"], reverse=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for e in rows:
            writer.writerow({
                "id": e["id"],
                "timestamp": e["timestamp"],
                "machine": e["machine"],
                "action": e["action"],
                "scope": scope_of(e["action"]),
                "detail": e["detail"],
                "status": e["status"],
                "fingerprint": e["fingerprint"],
            })
    return out_path


# ---------------------------------------------------------------------------
# Real-data hook — REPLACE THIS with a real AuditLog query. Left as a clearly-marked
# stub rather than guessed, per standing instruction: never guess a live DB schema.
# ---------------------------------------------------------------------------
def get_events_from_db(db_session, machine_ids=None, start=None, end=None):
    """
    Real AuditLog query, wired Sept 4 2026 against the confirmed live schema:
    audit_logs(id, machine_id, user_id, action, detail, status, timestamp, content_hash),
    LEFT JOIN machines(id, hostname). machine_id is nullable for system-level events
    (e.g. node_redirect_pending) - labeled "system" to match scope_of()'s existing
    System-scope action list in report_logic.py.
    """
    from db import AuditLog, Machine
    query = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if machine_ids:
        query = query.filter(AuditLog.machine_id.in_(machine_ids))
    if start:
        query = query.filter(AuditLog.timestamp >= start)
    if end:
        query = query.filter(AuditLog.timestamp <= end)
    logs = query.limit(1000).all()
    machines = {m.id: m.hostname for m in db_session.query(Machine).all()}
    events = []
    for l in logs:
        events.append({
            "id": l.id,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M") if l.timestamp else "",
            "machine": machines.get(l.machine_id, "unknown") if l.machine_id is not None else "system",
            "action": l.action,
            "detail": l.detail or "",
            "status": l.status or "ok",
            "fingerprint": l.content_hash or "",
        })
    return events


# ---------------------------------------------------------------------------
# FastAPI route stubs — match the existing /api/reports prefix and auth pattern.
# ---------------------------------------------------------------------------
"""
# In reports.py, replace the existing audit-report branch of POST /api/reports/audit with:

@router.post("/audit")
def generate_audit_report(payload: AuditReportRequest, db: Session = Depends(get_db),
                           user=Depends(get_current_user)):
    events = get_events_from_db(db, payload.machine_ids, payload.start, payload.end)
    report_id = _next_report_id(db)  # reuse whatever real JX-YYYYMMDD-XXXX sequence helper exists
    generated_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    out_path = f"{REPORTS_DIR}/jenix_audit_trail_{report_id}.pdf"
    build_audit_trail_pdf(events, report_id, generated_utc, out_path)
    # ... existing Report row insert / FileResponse handoff pattern goes here ...


# New CSV export route (none exists yet — confirmed via grep this session):

@router.get("/audit/csv")
def export_audit_csv(machine_ids: str = Query(None), start: str = Query(None),
                      end: str = Query(None), db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    events = get_events_from_db(db, machine_ids.split(",") if machine_ids else None, start, end)
    out_path = f"{REPORTS_DIR}/jenix_audit_export_{datetime.utcnow():%Y%m%d_%H%M%S}.csv"
    write_audit_csv(events, out_path)
    return FileResponse(out_path, media_type="text/csv", filename="jenix_audit_trail_export.csv")
"""
