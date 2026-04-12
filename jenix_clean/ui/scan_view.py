"""
jenix_scan_view.py
══════════════════
JENIX v4.1 — Production-Grade ScanView (UPGRADED)

Changes vs v4.0:
  ✦ Health banner shows Status label (Excellent/Good/Warning/Critical)
  ✦ Component score breakdown bar-chart (CPU/RAM/Disk/Processes/Security)
  ✦ Insight panel — system summary, performance verdict, risk summary
  ✦ Rich recommendations rendered with group headers, impact badge, command block
  ✦ Stat card shows Grade + Status text instead of plain grade
  ✦ All colours / tokens match gui.py exactly — drop-in compatible
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from jenix_scan_engine import (
    ScanEngine,
    ScanResult,
    ReportGenerator,
    WeightedHealthScorer,
    Recommendation,
)

# ── Design tokens (mirrors gui.py exactly) ────────────────────────────────────
BG1 = "#0A0E1A"; BG2 = "#111827"; BG3 = "#1A2235"; BG4 = "#1f2d42"
CYAN = "#00E5FF"; CYANL = "#00b0c8"
GREEN = "#39FF14"; AMBER = "#FFB800"; RED = "#FF4444"
T1 = "#E8EAF0"; T2 = "#7B8BA0"; BORDER = "#1e2d45"
CYAN_BORDER  = "#007a8a"; GREEN_BORDER = "#1a6b0a"
AMBER_BORDER = "#7a5800"; RED_BORDER   = "#8a1a1a"

F_MONO    = ("Courier New", 11)
F_MONO_SM = ("Courier New", 10)
F_MONO_XS = ("Courier New", 9)
F_LABEL   = ("Helvetica", 10, "bold")
F_TITLE   = ("Helvetica", 13, "bold")
F_BIG     = ("Courier New", 20, "bold")
F_MED     = ("Courier New", 14, "bold")

SEV_COLORS = {
    "CRITICAL": (RED,   "#2a0808", RED_BORDER),
    "HIGH":     (AMBER, "#1f1600", AMBER_BORDER),
    "MEDIUM":   (CYAN,  "#001e26", CYAN_BORDER),
    "LOW":      (GREEN, "#0a1f06", GREEN_BORDER),
}
SEV_ICONS = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

RISK_COLORS = {
    "red":   (RED,   "#2a0808", RED_BORDER),
    "amber": (AMBER, "#1f1600", AMBER_BORDER),
    "green": (GREEN, "#0a1f06", GREEN_BORDER),
}

STATUS_COLORS = {
    "Excellent": GREEN,
    "Good":      CYAN,
    "Warning":   AMBER,
    "Critical":  RED,
}

GROUP_ICONS = {
    "Performance":   "⚡",
    "Security":      "🔒",
    "System Cleanup":"◻",
}

IMPACT_COLORS = {"high": RED, "medium": AMBER, "low": GREEN}

LOG_DIR    = Path.home() / ".jenix"
LOG_DIR.mkdir(exist_ok=True)
REPORT_DIR = LOG_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ── Widget helpers ────────────────────────────────────────────────────────────

def _divider(parent):
    ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x")

def _card(parent, **kw):
    return ctk.CTkFrame(
        parent, fg_color=BG2, corner_radius=8,
        border_width=1, border_color=BORDER, **kw
    )

def _card_header(card, title: str, badge_text: str, badge_color: str):
    bg_map = {CYAN: "#001e26", GREEN: "#0a1f06", AMBER: "#1f1600", RED: "#2a0808"}
    bd_map = {CYAN: CYAN_BORDER, GREEN: GREEN_BORDER, AMBER: AMBER_BORDER, RED: RED_BORDER}
    bg = bg_map.get(badge_color, BG3)
    bd = bd_map.get(badge_color, BORDER)
    h = ctk.CTkFrame(card, fg_color="transparent", height=36)
    h.pack(fill="x", padx=14, pady=(10, 0))
    h.pack_propagate(False)
    ctk.CTkLabel(h, text=title, font=F_LABEL, text_color=T1).pack(side="left")
    f = ctk.CTkFrame(h, fg_color=bg, corner_radius=4, border_width=1, border_color=bd)
    ctk.CTkLabel(f, text=badge_text, font=F_MONO_XS,
                 text_color=badge_color, padx=6, pady=2).pack()
    f.pack(side="right")
    _divider(card)


def _score_color(score: int) -> str:
    if score >= 90: return GREEN
    if score >= 75: return CYAN
    if score >= 60: return AMBER
    return RED


def _mini_bar(parent, value: float, color: str, width: int = 120):
    """Horizontal mini progress bar for component breakdown."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    bar = ctk.CTkProgressBar(frame, width=width, height=6, corner_radius=3,
                             fg_color=BG3, progress_color=color)
    bar.set(max(0.0, min(1.0, value / 100)))
    bar.pack(side="left")
    ctk.CTkLabel(frame, text=f"{value:.0f}", font=F_MONO_XS,
                 text_color=color, width=30).pack(side="left", padx=(4, 0))
    return frame


# ══════════════════════════════════════════════════════════════════════════════
# LOG BOX
# ══════════════════════════════════════════════════════════════════════════════

class _LogBox(ctk.CTkFrame):
    def __init__(self, parent, height: int = 150):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        h = ctk.CTkFrame(self, fg_color="transparent", height=28)
        h.pack(fill="x", padx=12, pady=(8, 0))
        h.pack_propagate(False)
        ctk.CTkLabel(h, text="›  Output Log", font=F_MONO_SM,
                     text_color=T1).pack(side="left")
        ctk.CTkLabel(h, text="LIVE", font=F_MONO_XS, text_color=CYAN).pack(side="right")
        _divider(self)
        self._box = ctk.CTkTextbox(
            self, font=F_MONO_XS, fg_color=BG1, text_color=T2,
            wrap="none", height=height,
        )
        self._box.pack(fill="both", expand=True, padx=2, pady=2)
        self._box.configure(state="disabled")

    def write(self, level: str, msg: str):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"  {ts}  [{level:4s}]  {msg}\n"
        self._box.configure(state="normal")
        self._box.insert("end", line)
        self._box.configure(state="disabled")
        self._box.see("end")


# ══════════════════════════════════════════════════════════════════════════════
# STAT CARD
# ══════════════════════════════════════════════════════════════════════════════

class _StatCard(ctk.CTkFrame):
    def __init__(self, parent, label: str, value: str,
                 unit: str = "", sub: str = "", color: str = CYAN):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        ctk.CTkLabel(self, text=label, font=F_MONO_XS,
                     text_color=T2).pack(anchor="w", padx=12, pady=(10, 0))
        r = ctk.CTkFrame(self, fg_color="transparent")
        r.pack(anchor="w", padx=12)
        self._v = ctk.CTkLabel(r, text=value, font=F_BIG, text_color=color)
        self._v.pack(side="left")
        self._c = color
        ctk.CTkLabel(r, text=unit, font=F_MONO_SM,
                     text_color=T2).pack(side="left", pady=(8, 0))
        self._sub = ctk.CTkLabel(self, text=sub, font=F_MONO_XS, text_color=T2)
        self._sub.pack(anchor="w", padx=12, pady=(0, 10))

    def update(self, value: str, color: Optional[str] = None,
               sub: Optional[str] = None):
        self._v.configure(text=value, text_color=color or self._c)
        if sub is not None:
            self._sub.configure(text=sub)


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTION SCAN VIEW  (v4.1)
# ══════════════════════════════════════════════════════════════════════════════

class ProductionScanView(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._engine   = ScanEngine()
        self._scorer   = WeightedHealthScorer()
        self._result:  Optional[ScanResult] = None
        self._scanning = False
        self._stat_cards: dict = {}
        self._build()

    # ─────────────────────────────────────────────────────────────────────────
    # BUILD
    # ─────────────────────────────────────────────────────────────────────────

    def _build(self):
        # Top bar
        top_bar = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=52)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        tb = ctk.CTkFrame(top_bar, fg_color="transparent")
        tb.pack(fill="both", expand=True, padx=14)

        self._scan_btn = ctk.CTkButton(
            tb, text="▶  DEEP SCAN", width=148, height=34,
            font=("Courier New", 10, "bold"),
            fg_color=CYAN, hover_color=CYANL, text_color=BG1,
            corner_radius=6, command=self._start_scan,
        )
        self._scan_btn.pack(side="left", pady=9, padx=(0, 12))

        self._save_btn = ctk.CTkButton(
            tb, text="💾  SAVE REPORTS", width=148, height=34,
            font=("Courier New", 10, "bold"),
            fg_color=BG3, hover_color=BG4, text_color=T2,
            corner_radius=6, border_width=1, border_color=BORDER,
            state="disabled", command=self._save_reports,
        )
        self._save_btn.pack(side="left", pady=9, padx=(0, 12))

        self._prog_lbl = ctk.CTkLabel(
            tb, text="Ready — click ▶ DEEP SCAN",
            font=F_MONO_XS, text_color=T2,
        )
        self._prog_lbl.pack(side="left")

        self._ts_lbl = ctk.CTkLabel(tb, text="", font=F_MONO_XS, text_color=T2)
        self._ts_lbl.pack(side="right", padx=(0, 4))

        # Progress bar
        self._prog = ctk.CTkProgressBar(
            self, height=3, corner_radius=0,
            fg_color=BG3, progress_color=CYAN,
        )
        self._prog.set(0)
        self._prog.pack(fill="x")

        # Scrollable body
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BG3,
            scrollbar_button_hover_color=BG4,
        )
        self._scroll.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        self._build_stat_row()
        self._build_body_placeholder()
        self._build_log()

    def _build_stat_row(self):
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        for i in range(6):
            row.columnconfigure(i, weight=1, uniform="sc")

        defs = [
            ("health",  "HEALTH",  "—", "/100",  "Grade — · Awaiting scan",    GREEN),
            ("status",  "STATUS",  "—", "",       "Awaiting scan",              CYAN),
            ("cpu",     "CPU",     "—", "%",      "Awaiting scan",              CYAN),
            ("ram",     "RAM",     "—", "%",      "Awaiting scan",              AMBER),
            ("issues",  "ISSUES",  "—", "",       "Awaiting scan",              AMBER),
            ("ports",   "PORTS",   "—", "",       "Awaiting scan",              CYAN),
        ]
        for i, (key, label, val, unit, sub, color) in enumerate(defs):
            card = _StatCard(row, label, val, unit, sub, color)
            card.grid(row=0, column=i, padx=(0, 6 if i < 5 else 0), sticky="nsew")
            self._stat_cards[key] = card

    def _build_body_placeholder(self):
        self._body = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._body.pack(fill="x", pady=(0, 10))
        ph = ctk.CTkFrame(self._body, fg_color=BG2, corner_radius=8,
                          border_width=1, border_color=BORDER)
        ph.pack(fill="x")
        ctk.CTkLabel(
            ph,
            text="◈  Run a Deep Scan to see weighted health score, AI-powered insights, process table, port audit and issue report.",
            font=F_MONO_SM, text_color=T2,
        ).pack(pady=28)

    def _build_log(self):
        self._log = _LogBox(self._scroll, height=130)
        self._log.pack(fill="x")
        self._log.write("INFO", "JENIX v4.1 Intelligent Scan Engine ready")
        self._log.write("INFO", f"Reports saved to: {REPORT_DIR}")
        self._log.write("INFO", "Click ▶ DEEP SCAN to begin full analysis")

    # ─────────────────────────────────────────────────────────────────────────
    # SCAN
    # ─────────────────────────────────────────────────────────────────────────

    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._scan_btn.configure(state="disabled", text="⏳  SCANNING…")
        self._save_btn.configure(state="disabled")
        self._prog.set(0)
        self._log.write("INFO", "═" * 50)
        self._log.write("RUN", "Deep Scan initiated — v4.1 weighted engine")
        for w in self._body.winfo_children():
            w.destroy()
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        def cb(pct: int, msg: str):
            self.after(0, lambda p=pct, m=msg: self._on_progress(p, m))
        try:
            result = self._engine.run_full_scan(progress_cb=cb)
            self.after(0, lambda r=result: self._render_result(r))
        except Exception as exc:
            self.after(0, lambda e=str(exc): self._scan_error(e))

    def _on_progress(self, pct: int, msg: str):
        self._prog.set(pct / 100)
        self._prog_lbl.configure(text=msg, text_color=CYAN)
        self._log.write("INFO", msg)

    def _scan_error(self, msg: str):
        self._scanning = False
        self._scan_btn.configure(state="normal", text="▶  DEEP SCAN")
        self._log.write("ERR", f"Scan failed: {msg}")
        self._prog.set(0)

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER RESULTS
    # ─────────────────────────────────────────────────────────────────────────

    def _render_result(self, result: ScanResult):
        self._result   = result
        self._scanning = False
        self._prog.set(1.0)
        self.after(600, lambda: self._prog.set(0))

        self._scan_btn.configure(state="normal", text="▶  DEEP SCAN")
        self._save_btn.configure(
            state="normal", fg_color=GREEN,
            hover_color="#2acc0e", text_color=BG1,
        )
        self._ts_lbl.configure(
            text=f"Last scan: {result.timestamp}  ·  {result.duration_s}s",
            text_color=T2,
        )
        sc = _score_color(result.health_score)
        self._prog_lbl.configure(
            text=(f"Score {result.health_score}/100  ·  Grade {result.health_grade}"
                  f"  ·  {result.health_status}  ·  {len(result.issues)} issue(s)"),
            text_color=sc,
        )
        self._log.write("OK", (
            f"Score: {result.health_score}/100  Grade: {result.health_grade}"
            f"  Status: {result.health_status}"
        ))
        self._log.write("OK", (
            f"Issues: {len(result.issues)}  "
            f"Ports: {len(result.open_ports)}  "
            f"Suspicious: {len(result.suspicious_procs)}"
        ))
        self._log.write("INFO", f"Insight: {result.insight.system_summary[:80]}…")

        self._update_stat_cards(result)
        self._render_body(result)

    def _update_stat_cards(self, r: ScanResult):
        sc = _score_color(r.health_score)
        self._stat_cards["health"].update(
            str(r.health_score), sc,
            f"Grade {r.health_grade}"
        )

        status_c = STATUS_COLORS.get(r.health_status, CYAN)
        self._stat_cards["status"].update(
            r.health_status[:6] if len(r.health_status) > 6 else r.health_status,
            status_c,
            r.health_status,
        )

        cpu_c = RED if r.performance.cpu_percent >= 80 else \
                AMBER if r.performance.cpu_percent >= 50 else GREEN
        self._stat_cards["cpu"].update(
            f"{r.performance.cpu_percent:.0f}", cpu_c,
            f"Load {r.performance.load_avg_1:.2f}/{r.performance.load_avg_5:.2f}"
        )

        ram_c = RED if r.performance.ram_percent >= 85 else \
                AMBER if r.performance.ram_percent >= 65 else GREEN
        self._stat_cards["ram"].update(
            f"{r.performance.ram_percent:.0f}", ram_c,
            f"{r.performance.ram_used_gb:.1f}/{r.performance.ram_total_gb:.1f}GB"
        )

        crit = sum(1 for i in r.issues if i.severity == "CRITICAL")
        high = sum(1 for i in r.issues if i.severity == "HIGH")
        issue_c = RED if crit else AMBER if high else GREEN
        self._stat_cards["issues"].update(
            str(len(r.issues)), issue_c,
            f"{crit} critical · {high} high"
        )

        red_p = sum(1 for p in r.open_ports if p.risk == "red")
        port_c = RED if red_p else AMBER if r.open_ports else GREEN
        self._stat_cards["ports"].update(
            str(len(r.open_ports)), port_c,
            f"{red_p} high-risk"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BODY PANELS
    # ─────────────────────────────────────────────────────────────────────────

    def _render_body(self, r: ScanResult):
        for w in self._body.winfo_children():
            w.destroy()
        self._render_health_banner(r)
        self._render_insight_panel(r)          # NEW
        self._render_score_breakdown(r)        # NEW
        self._render_system_info(r)
        self._render_performance(r)
        self._render_processes(r)
        self._render_ports(r)
        self._render_issues(r)
        self._render_recommendations(r)        # UPGRADED

    # ── Health banner ─────────────────────────────────────────────────────────

    def _render_health_banner(self, r: ScanResult):
        sc  = _score_color(r.health_score)
        stc = STATUS_COLORS.get(r.health_status, sc)
        bg_map = {GREEN: "#0a1f06", CYAN: "#001e26", AMBER: "#1f1600", RED: "#2a0808"}
        bd_map = {GREEN: GREEN_BORDER, CYAN: CYAN_BORDER, AMBER: AMBER_BORDER, RED: RED_BORDER}
        bg = bg_map.get(sc, BG3)
        bd = bd_map.get(sc, BORDER)

        card = ctk.CTkFrame(self._body, fg_color=bg, corner_radius=8,
                            border_width=1, border_color=bd)
        card.pack(fill="x", pady=(0, 8))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=12)

        # Large score
        ctk.CTkLabel(inner, text=str(r.health_score),
                     font=("Courier New", 38, "bold"), text_color=sc).pack(side="left", padx=(0, 14))

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(right,
                     text=f"Health Score  ·  Grade {r.health_grade}  ·  {r.health_status}",
                     font=("Courier New", 14, "bold"), text_color=sc).pack(anchor="w")

        bar_frame = ctk.CTkFrame(right, fg_color="transparent")
        bar_frame.pack(anchor="w", fill="x", pady=(4, 2))
        ctk.CTkProgressBar(bar_frame, height=8, corner_radius=4,
                           fg_color=BG3, progress_color=sc, width=400
                           ).pack(side="left").set(r.health_score / 100)

        ctk.CTkLabel(right,
                     text=f"Scan: {r.duration_s}s  ·  {r.timestamp}  ·  {len(r.issues)} issue(s)",
                     font=F_MONO_XS, text_color=T2).pack(anchor="w")

        # Severity badges
        badges = ctk.CTkFrame(inner, fg_color="transparent")
        badges.pack(side="right")
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            count = sum(1 for i in r.issues if i.severity == sev)
            if not count:
                continue
            fg2, bg2, bd2 = SEV_COLORS[sev]
            f = ctk.CTkFrame(badges, fg_color=bg2, corner_radius=4,
                             border_width=1, border_color=bd2)
            f.pack(side="left", padx=3)
            ctk.CTkLabel(f, text=f"{SEV_ICONS[sev]} {count} {sev}",
                         font=F_MONO_XS, text_color=fg2, padx=8, pady=4).pack()

    # ── Insight panel (NEW) ────────────────────────────────────────────────────

    def _render_insight_panel(self, r: ScanResult):
        ins = r.insight
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        _card_header(card, "◈  System Intelligence",
                     ins.status_label, STATUS_COLORS.get(ins.status_label, CYAN))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(10, 12))
        grid.columnconfigure((0, 1, 2), weight=1, uniform="ins")

        blocks = [
            ("System Summary",      ins.system_summary,      CYAN),
            ("Performance Verdict", ins.performance_verdict,  AMBER),
            ("Security Overview",   ins.risk_summary,         RED if "risk" in ins.risk_summary.lower() or "no firewall" in ins.risk_summary.lower() else GREEN),
        ]
        for col, (title, text, color) in enumerate(blocks):
            cell = ctk.CTkFrame(grid, fg_color=BG3, corner_radius=6)
            cell.grid(row=0, column=col, padx=(0, 6 if col < 2 else 0), sticky="nsew")
            ctk.CTkLabel(cell, text=title, font=("Courier New", 8, "bold"),
                         text_color=color).pack(anchor="w", padx=10, pady=(8, 2))
            ctk.CTkLabel(cell, text=text,
                         font=F_MONO_XS, text_color=T1,
                         wraplength=200, justify="left", anchor="w"
                         ).pack(anchor="w", padx=10, pady=(0, 10), fill="x")

    # ── Score breakdown (NEW) ──────────────────────────────────────────────────

    def _render_score_breakdown(self, r: ScanResult):
        breakdown = self._scorer.component_breakdown(
            r.performance, r.open_ports, r.suspicious_procs
        )
        weights = {"cpu": 30, "ram": 25, "disk": 20, "processes": 15, "security": 10}
        labels  = {"cpu": "CPU", "ram": "RAM", "disk": "Disk",
                   "processes": "Processes", "security": "Security"}

        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        _card_header(card, "▦  Score Breakdown  (Weighted Components)",
                     "CPU 30% · RAM 25% · Disk 20% · Proc 15% · Sec 10%", CYAN)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 12))
        for i in range(5):
            row.columnconfigure(i, weight=1, uniform="sb")

        component_order = ["cpu", "ram", "disk", "processes", "security"]
        for i, key in enumerate(component_order):
            val = breakdown[key]
            w   = weights[key]
            color = RED if val < 40 else AMBER if val < 70 else GREEN

            cell = ctk.CTkFrame(row, fg_color=BG3, corner_radius=6)
            cell.grid(row=0, column=i, padx=(0, 6 if i < 4 else 0), sticky="nsew")

            ctk.CTkLabel(cell, text=f"{labels[key]} ({w}%)",
                         font=("Courier New", 8, "bold"),
                         text_color=T2).pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(cell, text=f"{val:.0f}",
                         font=("Courier New", 18, "bold"),
                         text_color=color).pack(anchor="w", padx=10)

            bar = ctk.CTkProgressBar(cell, height=5, corner_radius=2,
                                     fg_color=BG2, progress_color=color)
            bar.set(val / 100)
            bar.pack(fill="x", padx=10, pady=(2, 8))

    # ── System info ───────────────────────────────────────────────────────────

    def _render_system_info(self, r: ScanResult):
        si = r.system_info
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        _card_header(card, "◈  System Information", "SYSTEM", CYAN)
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(8, 12))
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="si")
        fields = [
            ("Hostname",     si.hostname),
            ("OS",           si.os_name.split("(")[0].strip()),
            ("Kernel",       si.kernel_version),
            ("Architecture", si.architecture),
            ("Boot Time",    si.boot_time or "—"),
            ("Uptime",       si.uptime_str or "—"),
            ("CPU Model",    si.cpu_model[:35] + "…" if len(si.cpu_model) > 35 else si.cpu_model),
            ("CPU",          f"{si.cpu_cores} cores / {si.cpu_threads} threads"),
            ("Total RAM",    f"{si.total_ram_gb} GB"),
            ("Python",       si.python_version),
        ]
        for i, (label, value) in enumerate(fields):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=i // 4, column=i % 4, padx=6, pady=4, sticky="w")
            ctk.CTkLabel(cell, text=label, font=F_MONO_XS, text_color=T2).pack(anchor="w")
            ctk.CTkLabel(cell, text=value, font=F_LABEL, text_color=T1).pack(anchor="w")

    # ── Performance ───────────────────────────────────────────────────────────

    def _render_performance(self, r: ScanResult):
        p = r.performance
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        cpu_c = RED if p.cpu_percent >= 80 else AMBER if p.cpu_percent >= 50 else GREEN
        _card_header(card, "⚡  Performance", f"CPU {p.cpu_percent:.0f}%", cpu_c)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 12))
        row.columnconfigure((0, 1, 2), weight=1, uniform="pf")

        # CPU column
        cpu_col = ctk.CTkFrame(row, fg_color=BG3, corner_radius=6)
        cpu_col.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        ctk.CTkLabel(cpu_col, text="CPU", font=F_LABEL, text_color=T2
                     ).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(cpu_col, text=f"{p.cpu_percent:.1f}%",
                     font=F_MED, text_color=cpu_c).pack(anchor="w", padx=10)
        ctk.CTkLabel(cpu_col, text=f"{p.cpu_freq_mhz:.0f} MHz  ·  {p.cpu_governor}",
                     font=F_MONO_XS, text_color=T2).pack(anchor="w", padx=10, pady=(0, 4))
        bar = ctk.CTkProgressBar(cpu_col, height=5, corner_radius=2,
                                 fg_color=BG2, progress_color=cpu_c)
        bar.set(p.cpu_percent / 100)
        bar.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(cpu_col,
                     text=f"Load {p.load_avg_1:.2f} / {p.load_avg_5:.2f} / {p.load_avg_15:.2f}",
                     font=F_MONO_XS, text_color=T2).pack(anchor="w", padx=10, pady=(0, 8))

        # RAM column
        ram_c = RED if p.ram_percent >= 85 else AMBER if p.ram_percent >= 65 else GREEN
        ram_col = ctk.CTkFrame(row, fg_color=BG3, corner_radius=6)
        ram_col.grid(row=0, column=1, padx=(0, 6), sticky="nsew")
        ctk.CTkLabel(ram_col, text="RAM", font=F_LABEL, text_color=T2
                     ).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkLabel(ram_col, text=f"{p.ram_percent:.0f}%",
                     font=F_MED, text_color=ram_c).pack(anchor="w", padx=10)
        ctk.CTkLabel(ram_col, text=f"{p.ram_used_gb:.1f}GB / {p.ram_total_gb:.1f}GB",
                     font=F_MONO_XS, text_color=T2).pack(anchor="w", padx=10, pady=(0, 4))
        rbar = ctk.CTkProgressBar(ram_col, height=5, corner_radius=2,
                                  fg_color=BG2, progress_color=ram_c)
        rbar.set(p.ram_percent / 100)
        rbar.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(ram_col,
                     text=f"Swap {p.swap_used_gb:.1f}/{p.swap_total_gb:.1f}GB ({p.swap_percent:.0f}%)",
                     font=F_MONO_XS, text_color=T2).pack(anchor="w", padx=10, pady=(0, 8))

        # Disk column
        disk_col = ctk.CTkFrame(row, fg_color=BG3, corner_radius=6)
        disk_col.grid(row=0, column=2, sticky="nsew")
        ctk.CTkLabel(disk_col, text="DISKS", font=F_LABEL, text_color=T2
                     ).pack(anchor="w", padx=10, pady=(8, 0))
        for d in p.disks[:5]:
            dc   = RED if d["percent"] >= 90 else AMBER if d["percent"] >= 75 else GREEN
            drow = ctk.CTkFrame(disk_col, fg_color="transparent")
            drow.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(drow, text=f"{d['mountpoint']:<14}",
                         font=F_MONO_XS, text_color=T2, width=100, anchor="w").pack(side="left")
            dbar = ctk.CTkProgressBar(drow, height=5, corner_radius=2,
                                      fg_color=BG2, progress_color=dc, width=80)
            dbar.set(d["percent"] / 100)
            dbar.pack(side="left", padx=(4, 4))
            ctk.CTkLabel(drow, text=f"{d['percent']:.0f}%",
                         font=F_MONO_XS, text_color=dc).pack(side="left")
        ctk.CTkFrame(disk_col, height=6, fg_color="transparent").pack()

    # ── Processes ─────────────────────────────────────────────────────────────

    def _render_processes(self, r: ScanResult):
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        susp = len(r.suspicious_procs)
        _card_header(card, "⚙  Process Analysis",
                     f"{susp} suspicious" if susp else "clean",
                     RED if susp else GREEN)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(8, 12))
        row.columnconfigure((0, 1), weight=1, uniform="pr")

        for col_idx, (procs, title, sort_key) in enumerate([
            (r.top_cpu_procs, "TOP CPU CONSUMERS", "cpu_pct"),
            (r.top_mem_procs, "TOP MEMORY CONSUMERS", "mem_pct"),
        ]):
            frame = ctk.CTkFrame(row, fg_color=BG3, corner_radius=6)
            frame.grid(row=0, column=col_idx,
                       padx=(0, 6 if col_idx == 0 else 0), sticky="nsew")
            ctk.CTkLabel(frame, text=title, font=F_MONO_XS, text_color=T2
                         ).pack(anchor="w", padx=10, pady=(8, 4))
            hdr = ctk.CTkFrame(frame, fg_color=BG4, corner_radius=0)
            hdr.pack(fill="x")
            for txt, w in [("PROCESS", 110), ("PID", 55),
                           ("CPU%" if col_idx == 0 else "MEM%", 50),
                           ("MEM MB", 60), ("USER", 0)]:
                ctk.CTkLabel(hdr, text=txt, font=F_MONO_XS, text_color=T2,
                             width=w, anchor="w").pack(
                    side="left", padx=(8 if txt == "PROCESS" else 4, 0), pady=4)

            for proc in procs:
                prow = ctk.CTkFrame(frame, fg_color="transparent")
                prow.pack(fill="x")
                c = (RED if (proc.cpu_pct > 40 if col_idx == 0 else proc.mem_pct > 20)
                     else AMBER if (proc.cpu_pct > 20 if col_idx == 0 else proc.mem_pct > 10)
                     else T2)
                ctk.CTkLabel(prow, text=proc.name[:15], font=F_LABEL,
                             text_color=T1, width=110, anchor="w").pack(side="left", padx=(8, 4), pady=5)
                ctk.CTkLabel(prow, text=str(proc.pid), font=F_MONO_XS,
                             text_color=T2, width=55, anchor="w").pack(side="left", padx=4)
                val = f"{proc.cpu_pct:.1f}" if col_idx == 0 else f"{proc.mem_pct:.2f}"
                ctk.CTkLabel(prow, text=val, font=F_MONO_XS,
                             text_color=c, width=50, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(prow, text=f"{proc.mem_mb:.0f}", font=F_MONO_XS,
                             text_color=T2, width=60, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(prow, text=proc.user[:10], font=F_MONO_XS,
                             text_color=T2, anchor="w").pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkFrame(frame, height=6, fg_color="transparent").pack()

        if r.suspicious_procs:
            scard = ctk.CTkFrame(card, fg_color="#2a0808", corner_radius=6,
                                 border_width=1, border_color=RED_BORDER)
            scard.pack(fill="x", padx=14, pady=(0, 12))
            ctk.CTkLabel(scard, text="⚠  SUSPICIOUS PROCESSES DETECTED",
                         font=F_LABEL, text_color=RED).pack(anchor="w", padx=12, pady=(8, 4))
            for sp in r.suspicious_procs:
                sr = ctk.CTkFrame(scard, fg_color="transparent")
                sr.pack(fill="x", padx=12, pady=3)
                ctk.CTkLabel(sr,
                             text=f"PID {sp.pid:6d}  {sp.name:<20s}  CPU {sp.cpu_pct:5.1f}%  [{sp.user}]",
                             font=F_MONO_XS, text_color=RED, anchor="w").pack(side="left")
                ctk.CTkLabel(sr, text="→ Investigate",
                             font=F_MONO_XS, text_color=AMBER).pack(side="right")
            ctk.CTkFrame(scard, height=6, fg_color="transparent").pack()

    # ── Ports ──────────────────────────────────────────────────────────────────

    def _render_ports(self, r: ScanResult):
        if not r.open_ports:
            return
        red_count = sum(1 for p in r.open_ports if p.risk == "red")
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        _card_header(card, f"🔒  Open Ports  ({len(r.open_ports)})",
                     f"{red_count} high-risk", RED if red_count else AMBER)
        hdr = ctk.CTkFrame(card, fg_color=BG3, corner_radius=0)
        hdr.pack(fill="x")
        for txt, w in [("PORT", 70), ("PROTO", 60), ("SERVICE", 130), ("RISK", 100), ("NOTE", 0)]:
            ctk.CTkLabel(hdr, text=txt, font=F_MONO_XS, text_color=T2,
                         width=w if w else 0, anchor="w").pack(
                side="left", padx=(12 if txt == "PORT" else 4, 0), pady=5,
                fill="x" if not w else None, expand=(not w))
        for port in r.open_ports:
            fg2, bg2, bd2 = RISK_COLORS.get(port.risk, (T2, BG3, BORDER))
            prow = ctk.CTkFrame(card, fg_color="transparent")
            prow.pack(fill="x")
            ctk.CTkLabel(prow, text=str(port.port),
                         font=("Courier New", 10, "bold"), text_color=fg2,
                         width=70, anchor="w").pack(side="left", padx=(12, 4), pady=6)
            ctk.CTkLabel(prow, text=port.proto, font=F_MONO_XS,
                         text_color=T2, width=60, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(prow, text=port.process[:16], font=F_LABEL,
                         text_color=T1, width=130, anchor="w").pack(side="left", padx=4)
            rf = ctk.CTkFrame(prow, fg_color=bg2, corner_radius=3,
                              border_width=1, border_color=bd2)
            icon = {"green": "●", "amber": "◆", "red": "▲"}.get(port.risk, "?")
            ctk.CTkLabel(rf, text=f"{icon} {port.risk.upper()}",
                         font=F_MONO_XS, text_color=fg2, padx=6, pady=2).pack()
            rf.pack(side="left", padx=4, pady=4)
            ctk.CTkLabel(prow, text=port.note[:55], font=F_MONO_XS,
                         text_color=T2, anchor="w").pack(side="left", fill="x", expand=True, padx=(8, 12))
            _divider(card)

    # ── Issues ────────────────────────────────────────────────────────────────

    def _render_issues(self, r: ScanResult):
        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        crit = sum(1 for i in r.issues if i.severity == "CRITICAL")
        badge_c = RED if crit else AMBER if r.issues else GREEN
        _card_header(card, "⚠  Issues",
                     f"{len(r.issues)} issues" if r.issues else "clean", badge_c)
        if not r.issues:
            ctk.CTkLabel(card, text="  ✓  No issues detected — system looks healthy.",
                         font=F_MONO_SM, text_color=GREEN).pack(anchor="w", padx=14, pady=12)
            return
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            grp = [i for i in r.issues if i.severity == sev]
            if not grp:
                continue
            fg2, bg2, bd2 = SEV_COLORS[sev]
            gh = ctk.CTkFrame(card, fg_color=bg2, corner_radius=0)
            gh.pack(fill="x")
            ctk.CTkLabel(gh,
                         text=f"  {SEV_ICONS[sev]}  {sev}  —  {len(grp)} issue(s)",
                         font=("Courier New", 9, "bold"), text_color=fg2
                         ).pack(anchor="w", padx=6, pady=4)
            for issue in grp:
                irow = ctk.CTkFrame(card, fg_color="transparent")
                irow.pack(fill="x", padx=14, pady=(6, 0))
                ctk.CTkLabel(irow, text=issue.title,
                             font=F_LABEL, text_color=T1, anchor="w").pack(anchor="w")
                ctk.CTkLabel(irow, text=f"  {issue.detail}",
                             font=F_MONO_XS, text_color=T2,
                             anchor="w", wraplength=540, justify="left").pack(anchor="w", pady=(2, 2))
                if issue.fix_hint:
                    hf = ctk.CTkFrame(irow, fg_color=BG3, corner_radius=4)
                    hf.pack(fill="x", pady=(0, 6))
                    ctk.CTkLabel(hf, text="$  " + issue.fix_hint[:100],
                                 font=F_MONO_XS, text_color=CYAN, anchor="w"
                                 ).pack(anchor="w", padx=8, pady=4)
                _divider(card)
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

    # ── Recommendations (UPGRADED v4.1) ───────────────────────────────────────

    def _render_recommendations(self, r: ScanResult):
        recs = r.rich_recommendations
        if not recs:
            recs_simple = r.recommendations
            card = _card(self._body)
            card.pack(fill="x", pady=(0, 8))
            _card_header(card, "💡  Recommendations", "0", GREEN)
            ctk.CTkLabel(card, text="  ✓  System is healthy — no recommendations.",
                         font=F_MONO_SM, text_color=GREEN).pack(anchor="w", padx=14, pady=12)
            return

        card = _card(self._body)
        card.pack(fill="x", pady=(0, 8))
        crit_r = sum(1 for rec in recs if rec.priority == "CRITICAL")
        high_r = sum(1 for rec in recs if rec.priority == "HIGH")
        badge_c = RED if crit_r else AMBER if high_r else GREEN
        _card_header(card, f"💡  Intelligent Recommendations  ({len(recs)})",
                     f"{crit_r} critical · {high_r} high", badge_c)

        current_group = None
        for idx, rec in enumerate(recs, 1):
            # Group separator
            if rec.group != current_group:
                current_group = rec.group
                icon = GROUP_ICONS.get(rec.group, "•")
                gh = ctk.CTkFrame(card, fg_color=BG3, corner_radius=0)
                gh.pack(fill="x")
                ctk.CTkLabel(gh, text=f"  {icon}  {current_group.upper()}",
                             font=("Courier New", 9, "bold"),
                             text_color=CYAN).pack(anchor="w", padx=8, pady=5)

            fg2, bg2, bd2 = SEV_COLORS.get(rec.priority, (T2, BG3, BORDER))
            impact_c = IMPACT_COLORS.get(rec.impact, T2)

            rrow = ctk.CTkFrame(card, fg_color="transparent")
            rrow.pack(fill="x", padx=14, pady=(8, 0))

            # Header line
            hline = ctk.CTkFrame(rrow, fg_color="transparent")
            hline.pack(fill="x")

            # Priority badge
            pf = ctk.CTkFrame(hline, fg_color=bg2, corner_radius=3,
                              border_width=1, border_color=bd2)
            ctk.CTkLabel(pf, text=f"{SEV_ICONS[rec.priority]} {rec.priority}",
                         font=F_MONO_XS, text_color=fg2, padx=5, pady=2).pack()
            pf.pack(side="left", padx=(0, 6))

            # Impact badge
            imp_bg = {"high": "#2a0808", "medium": "#1f1600", "low": "#0a1f06"}.get(rec.impact, BG3)
            imp_bd = {"high": RED_BORDER, "medium": AMBER_BORDER, "low": GREEN_BORDER}.get(rec.impact, BORDER)
            imf = ctk.CTkFrame(hline, fg_color=imp_bg, corner_radius=3,
                               border_width=1, border_color=imp_bd)
            ctk.CTkLabel(imf, text=f"IMPACT: {rec.impact.upper()}",
                         font=F_MONO_XS, text_color=impact_c, padx=5, pady=2).pack()
            imf.pack(side="left", padx=(0, 8))

            ctk.CTkLabel(hline, text=f"#{idx:02d}  {rec.group}",
                         font=F_MONO_XS, text_color=T2).pack(side="right")

            # Problem
            ctk.CTkLabel(rrow, text=rec.problem,
                         font=F_LABEL, text_color=T1,
                         anchor="w", wraplength=540, justify="left").pack(anchor="w", pady=(4, 2))

            # Solution
            sol_f = ctk.CTkFrame(rrow, fg_color=BG3, corner_radius=4)
            sol_f.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(sol_f, text=f"→  {rec.solution}",
                         font=F_MONO_XS, text_color=T1,
                         anchor="w", wraplength=520, justify="left"
                         ).pack(anchor="w", padx=10, pady=5)

            # Command block
            if rec.command:
                cmd_f = ctk.CTkFrame(rrow, fg_color="#00121a", corner_radius=4,
                                     border_width=1, border_color=CYAN_BORDER)
                cmd_f.pack(fill="x", pady=(0, 4))
                ctk.CTkLabel(cmd_f, text="⚠ Suggested command — review before running:",
                             font=("Courier New", 8), text_color=T2
                             ).pack(anchor="w", padx=10, pady=(4, 0))
                ctk.CTkLabel(cmd_f, text=f"$  {rec.command}",
                             font=F_MONO_XS, text_color=CYAN,
                             anchor="w", wraplength=520
                             ).pack(anchor="w", padx=10, pady=(2, 6))

            if rec.rationale:
                ctk.CTkLabel(rrow, text=f"ℹ  {rec.rationale}",
                             font=F_MONO_XS, text_color=T2,
                             anchor="w", wraplength=520).pack(anchor="w", pady=(0, 4))

            _divider(card)

        ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

    # ─────────────────────────────────────────────────────────────────────────
    # SAVE REPORTS
    # ─────────────────────────────────────────────────────────────────────────

    def _save_reports(self):
        if not self._result:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_path  = str(REPORT_DIR / f"scan_report_{ts}.txt")
        json_path = str(REPORT_DIR / f"scan_report_{ts}.json")
        try:
            gen = ReportGenerator(self._result)
            gen.write_txt(txt_path)
            gen.write_json(json_path)
            self._log.write("OK", f"TXT  → {txt_path}")
            self._log.write("OK", f"JSON → {json_path}")
            self._save_btn.configure(text="✓  Saved!")
            self.after(2500, lambda: self._save_btn.configure(text="💾  SAVE REPORTS"))
        except Exception as exc:
            self._log.write("ERR", f"Save failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# PATCH FUNCTION  (backward-compatible with gui.py)
# ══════════════════════════════════════════════════════════════════════════════

def patch_scan_view(app) -> None:
    try:
        import gui as _g
        if _g.VIEW_CLASSES.get("scan") is ProductionScanView:
            return
        _g.VIEW_CLASSES["scan"] = ProductionScanView
        if hasattr(app, "content") and getattr(app.content, "_cur", None):
            cur = app.content._cur
            if isinstance(cur, _g.ScanView) or \
               type(cur).__name__ in ("ScanView", "ProductionScanView"):
                app.content.show("scan")
    except Exception as exc:
        print(f"[jenix_scan_view] patch_scan_view error: {exc}")
