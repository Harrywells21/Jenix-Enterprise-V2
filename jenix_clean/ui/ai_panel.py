# JENIX AI Recommendations Panel – integrates jenix_ai.py with the CustomTkinter GUI

import customtkinter as ctk
import threading
from typing import List

# color constants (must match jenix.py)
BG1          = "#0A0E1A"
BG2          = "#111827"
BG3          = "#1A2235"
BG4          = "#1f2d42"
CYAN         = "#00E5FF"
CYANL        = "#00b0c8"
GREEN        = "#39FF14"
AMBER        = "#FFB800"
RED          = "#FF4444"
T1           = "#E8EAF0"
T2           = "#7B8BA0"
BORDER       = "#1e2d45"
CYAN_BORDER  = "#007a8a"
GREEN_BORDER = "#1a6b0a"
AMBER_BORDER = "#7a5800"
RED_BORDER   = "#8a1a1a"

F_MONO    = ("Courier New", 11)
F_MONO_SM = ("Courier New", 10)
F_MONO_XS = ("Courier New", 9)
F_LABEL   = ("Helvetica", 10, "bold")
F_TITLE   = ("Helvetica", 13, "bold")
F_NAV     = ("Helvetica", 8, "bold")
F_BIG     = ("Courier New", 22, "bold")

# priority → (fg_color, bg_color, border_color, icon)
PRIORITY_STYLE = {
    "Critical": (RED,   "#2a0808", RED_BORDER,   "🔴"),
    "High":     (AMBER, "#1f1600", AMBER_BORDER, "🟠"),
    "Medium":   (CYAN,  "#001e26", CYAN_BORDER,  "🟡"),
    "Low":      (GREEN, "#0a1f06", GREEN_BORDER, "🟢"),
}

CATEGORY_ICONS = {
    "Security":    "🔒",
    "Performance": "⚡",
    "Packages":    "📦",
    "Storage":     "💾",
    "Network":     "🌐",
    "Health":      "🩺",
    "Tools":       "🔧",
}


# ── health score widget ────────────────────────────────────────────────────────

class HealthScoreWidget(ctk.CTkFrame):
    """
    Prominent health score display.

    Shows:
      - Large numeric score (0–100) in a colour that reflects severity
      - Letter grade (A / B / C / D)
      - Short status label
      - Mini metric strip: CPU / RAM / worst-disk percentages
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color=BG2, corner_radius=10,
                         border_width=1, border_color=BORDER)
        self._build()

    def _build(self):
        # ── top row: score + grade ────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 0))

        # score number
        self._score_lbl = ctk.CTkLabel(
            top, text="—",
            font=("Courier New", 52, "bold"),
            text_color=T2,
        )
        self._score_lbl.pack(side="left")

        ctk.CTkLabel(top, text="/100", font=("Courier New", 14),
                     text_color=T2).pack(side="left", anchor="s", pady=(0, 12))

        # grade badge
        grade_col = ctk.CTkFrame(top, fg_color="transparent")
        grade_col.pack(side="left", padx=18, anchor="center")

        self._grade_badge = ctk.CTkFrame(grade_col, fg_color=BG3,
                                          corner_radius=6, width=52, height=52)
        self._grade_badge.pack()
        self._grade_badge.pack_propagate(False)
        self._grade_lbl = ctk.CTkLabel(self._grade_badge, text="—",
                                        font=("Courier New", 24, "bold"),
                                        text_color=T2)
        self._grade_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # status text
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", anchor="center")
        self._status_lbl = ctk.CTkLabel(right, text="Run a scan to assess system health.",
                                         font=F_MONO_SM, text_color=T2,
                                         wraplength=260, justify="right")
        self._status_lbl.pack(anchor="e")

        # ── score bar ──────────────────────────────────────────────────────────
        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                        fg_color=BG3, progress_color=CYAN)
        self._bar.set(0)
        self._bar.pack(fill="x", padx=18, pady=(8, 0))

        # ── metric strip ──────────────────────────────────────────────────────
        strip = ctk.CTkFrame(self, fg_color=BG3, corner_radius=6)
        strip.pack(fill="x", padx=18, pady=(10, 14))

        self._metric_labels: dict = {}
        for key, label in [("cpu", "CPU"), ("ram", "RAM"), ("disk", "Disk")]:
            col = ctk.CTkFrame(strip, fg_color="transparent")
            col.pack(side="left", expand=True, padx=6, pady=8)
            ctk.CTkLabel(col, text=label, font=F_MONO_XS, text_color=T2).pack()
            val_lbl = ctk.CTkLabel(col, text="—", font=("Courier New", 13, "bold"),
                                    text_color=T1)
            val_lbl.pack()
            self._metric_labels[key] = val_lbl

    # ── public ────────────────────────────────────────────────────────────────

    def update(self, analysis: dict):
        """Refresh all displayed values from an analyze_system() result dict."""
        score   = analysis.get("health_score", 0)
        metrics = analysis.get("metrics", {})
        issues  = analysis.get("issues", [])

        # Score colour
        if score >= 90:
            color = GREEN
        elif score >= 75:
            color = CYAN
        elif score >= 55:
            color = AMBER
        else:
            color = RED

        # Grade
        grade = ("A" if score >= 90 else
                 "B" if score >= 75 else
                 "C" if score >= 55 else "D")

        # Status text
        if not issues:
            status = "✓  System is healthy."
        elif score >= 75:
            status = f"⚠  {len(issues)} minor issue(s) detected."
        elif score >= 55:
            status = f"⚠  {len(issues)} issue(s) need attention."
        else:
            status = f"🔴  {len(issues)} critical issue(s) — action required."

        self._score_lbl.configure(text=str(score), text_color=color)
        self._grade_lbl.configure(text=grade, text_color=color)
        self._grade_badge.configure(border_color=color, border_width=2)
        self._status_lbl.configure(text=status, text_color=color if score < 55 else T1)
        self._bar.configure(progress_color=color)
        self._bar.set(score / 100)

        # Metric strip
        cpu  = metrics.get("cpu_percent",    0.0)
        ram  = metrics.get("ram_percent",    0.0)
        disk = metrics.get("worst_disk_pct", 0.0)

        def _metric_color(pct):
            return RED if pct >= 90 else AMBER if pct >= 75 else CYAN if pct >= 50 else GREEN

        for key, pct in [("cpu", cpu), ("ram", ram), ("disk", disk)]:
            self._metric_labels[key].configure(
                text=f"{pct:.0f}%", text_color=_metric_color(pct)
            )


# ── issues list widget ────────────────────────────────────────────────────────

class IssuesList(ctk.CTkFrame):
    """Compact scrollable list of detected issues."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        ctk.CTkLabel(self, text="⚠  Detected Issues",
                     font=F_LABEL, text_color=T1).pack(
            anchor="w", padx=14, pady=(10, 4))
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               height=130,
                                               scrollbar_button_color=BG3,
                                               scrollbar_button_hover_color=BG4)
        self._scroll.pack(fill="x", padx=6, pady=(4, 8))
        self._placeholder = ctk.CTkLabel(self._scroll,
                                          text="No issues detected.",
                                          font=F_MONO_XS, text_color=T2)
        self._placeholder.pack(pady=10)

    def update(self, issues: list):
        for w in self._scroll.winfo_children():
            w.destroy()
        if not issues:
            ctk.CTkLabel(self._scroll, text="✓  No issues detected.",
                         font=F_MONO_XS, text_color=GREEN).pack(
                anchor="w", padx=8, pady=6)
            return
        for issue in issues:
            row = ctk.CTkFrame(self._scroll, fg_color=BG3, corner_radius=4)
            row.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(row, text=f"• {issue}", font=F_MONO_XS,
                         text_color=AMBER, anchor="w",
                         wraplength=500, justify="left").pack(
                anchor="w", padx=10, pady=4)


# ── recommendations list widget ───────────────────────────────────────────────

class AIRecommendationsList(ctk.CTkFrame):
    """Scrollable list of AI-generated action recommendations."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        ctk.CTkLabel(self, text="💡  AI Recommendations",
                     font=F_LABEL, text_color=T1).pack(
            anchor="w", padx=14, pady=(10, 4))
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               height=160,
                                               scrollbar_button_color=BG3,
                                               scrollbar_button_hover_color=BG4)
        self._scroll.pack(fill="x", padx=6, pady=(4, 8))
        ctk.CTkLabel(self._scroll, text="Run a scan to see recommendations.",
                     font=F_MONO_XS, text_color=T2).pack(pady=10)

    def update(self, recommendations: list):
        for w in self._scroll.winfo_children():
            w.destroy()
        if not recommendations:
            ctk.CTkLabel(self._scroll, text="✓  System is optimally configured.",
                         font=F_MONO_XS, text_color=GREEN).pack(
                anchor="w", padx=8, pady=6)
            return

        for i, rec in enumerate(recommendations, 1):
            # Distinguish the "best mode" suggestion (inserted at index 0 with 💡)
            is_mode_tip = rec.startswith("💡")
            bg = "#001e26" if is_mode_tip else BG3
            border = CYAN_BORDER if is_mode_tip else BORDER

            card = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4,
                                border_width=1 if is_mode_tip else 0,
                                border_color=border)
            card.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(card,
                         text=f"{i:02d}. {rec}",
                         font=F_MONO_XS,
                         text_color=CYAN if is_mode_tip else T1,
                         anchor="w", wraplength=500, justify="left").pack(
                anchor="w", padx=10, pady=(5, 5))


# ── single recommendation card ─────────────────────────────────────────────────

class RecommendationCard(ctk.CTkFrame):
    def __init__(self, parent, rec, index: int):
        fg, bg, border, icon = PRIORITY_STYLE.get(
            rec.priority, (T2, BG3, BORDER, "⚪"))
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=border)

        # header row
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(10, 4))

        # priority badge
        badge = ctk.CTkFrame(hdr, fg_color=bg, corner_radius=4,
                              border_width=1, border_color=border)
        badge.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(badge, text=f"{icon} {rec.priority}",
                     font=F_MONO_XS, text_color=fg, padx=6, pady=2).pack()

        # category
        cat_icon = CATEGORY_ICONS.get(rec.category, "•")
        ctk.CTkLabel(hdr, text=f"{cat_icon}  {rec.category}",
                     font=("Helvetica", 9, "bold"), text_color=T2).pack(side="left")

        # index number
        ctk.CTkLabel(hdr, text=f"#{index:02d}",
                     font=F_MONO_XS, text_color=T2).pack(side="right")

        # title
        ctk.CTkLabel(self, text=rec.title, font=F_LABEL,
                     text_color=T1, anchor="w", wraplength=540).pack(
            anchor="w", padx=12, pady=(0, 4))

        # detail text
        ctk.CTkLabel(self, text=rec.detail, font=F_MONO_XS,
                     text_color=T2, anchor="w", wraplength=540,
                     justify="left").pack(anchor="w", padx=12, pady=(0, 6))

        # command block
        if rec.command:
            cmd_frame = ctk.CTkFrame(self, fg_color=BG3, corner_radius=6)
            cmd_frame.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(cmd_frame, text="$  " + rec.command,
                         font=("Courier New", 9), text_color=CYAN,
                         anchor="w", wraplength=520).pack(
                anchor="w", padx=10, pady=6)

        # unsafe warning
        if not rec.safe:
            warn = ctk.CTkFrame(self, fg_color="#2a1500", corner_radius=4,
                                border_width=1, border_color=AMBER_BORDER)
            warn.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(warn, text="⚠  Review carefully before running – this command modifies system config.",
                         font=F_MONO_XS, text_color=AMBER, padx=8, pady=4).pack(anchor="w")

        if rec.safe and rec.command:
            ctk.CTkFrame(self, height=4, fg_color="transparent").pack()


# ── summary stat strip ─────────────────────────────────────────────────────────

class RecommendationSummary(ctk.CTkFrame):
    def __init__(self, parent, recs: List):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)

        counts = {}
        for r in recs:
            counts[r.priority] = counts.get(r.priority, 0) + 1

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=12)

        for priority, (fg, bg, border, icon) in PRIORITY_STYLE.items():
            n = counts.get(priority, 0)
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", expand=True)
            ctk.CTkLabel(col, text=str(n), font=("Courier New", 20, "bold"),
                         text_color=fg).pack()
            ctk.CTkLabel(col, text=f"{icon} {priority}", font=F_MONO_XS,
                         text_color=T2).pack()

        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")

        # category breakdown
        cat_counts = {}
        for r in recs:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1

        cats_row = ctk.CTkFrame(self, fg_color="transparent")
        cats_row.pack(fill="x", padx=14, pady=8)
        for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
            icon = CATEGORY_ICONS.get(cat, "•")
            pill = ctk.CTkFrame(cats_row, fg_color=BG3, corner_radius=4)
            pill.pack(side="left", padx=(0, 6), pady=2)
            ctk.CTkLabel(pill, text=f"{icon} {cat} ({n})",
                         font=F_MONO_XS, text_color=T2, padx=6, pady=3).pack()


# ── filter bar ────────────────────────────────────────────────────────────────

class FilterBar(ctk.CTkFrame):
    PRIORITIES  = ["All", "Critical", "High", "Medium", "Low"]
    CATEGORIES  = ["All", "Security", "Performance", "Packages",
                   "Storage", "Network", "Health", "Tools"]

    def __init__(self, parent, on_filter):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        self.on_filter = on_filter
        self._priority = "All"
        self._category = "All"
        self._build()

    def _build(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=8)

        ctk.CTkLabel(row, text="Priority:", font=F_MONO_XS,
                     text_color=T2).pack(side="left", padx=(0, 6))
        self._pri_var = ctk.StringVar(value="All")
        pri_menu = ctk.CTkOptionMenu(row, values=self.PRIORITIES,
                                      variable=self._pri_var,
                                      fg_color=BG3, button_color=BG4,
                                      button_hover_color=BG4,
                                      dropdown_fg_color=BG3,
                                      text_color=T1, font=F_MONO_XS,
                                      width=110, height=26,
                                      command=self._on_priority)
        pri_menu.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row, text="Category:", font=F_MONO_XS,
                     text_color=T2).pack(side="left", padx=(0, 6))
        self._cat_var = ctk.StringVar(value="All")
        cat_menu = ctk.CTkOptionMenu(row, values=self.CATEGORIES,
                                      variable=self._cat_var,
                                      fg_color=BG3, button_color=BG4,
                                      button_hover_color=BG4,
                                      dropdown_fg_color=BG3,
                                      text_color=T1, font=F_MONO_XS,
                                      width=130, height=26,
                                      command=self._on_category)
        cat_menu.pack(side="left")

    def _on_priority(self, val):
        self._priority = val
        self.on_filter(self._priority, self._category)

    def _on_category(self, val):
        self._category = val
        self.on_filter(self._priority, self._category)


# ── main AI recommendations panel ─────────────────────────────────────────────

class AIRecommendationsPanel(ctk.CTkFrame):
    """
    Drop-in view panel for the JENIX GUI.

    Accepts a ScanReport, runs JENIXAdvisor asynchronously,
    and updates the GUI on the main thread via after().

    Also exposes a real-time health dashboard powered by AIEngine.analyze_system()
    with a Refresh button so the user can re-poll on demand.

    Usage (from ContentPanel.show or anywhere in the GUI):
        panel = AIRecommendationsPanel(parent_frame)
        panel.pack(fill="both", expand=True)
        panel.load_report(scan_report)   # triggers async analysis
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._all_recs  = []
        self._cards     = []
        self._filter_priority = "All"
        self._filter_category = "All"
        self._monitoring      = False
        self._build_skeleton()

    def _build_skeleton(self):
        # ── top header ────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=BG2, corner_radius=8,
                            border_width=1, border_color=BORDER)
        top.pack(fill="x", padx=14, pady=(14, 8))

        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(inner, text="🤖  AI Advisor",
                     font=F_TITLE, text_color=CYAN).pack(side="left")

        # Refresh button
        self._refresh_btn = ctk.CTkButton(
            inner, text="⟳  Refresh",
            font=F_MONO_XS,
            width=90, height=26,
            fg_color=BG3, hover_color=BG4,
            border_width=1, border_color=CYAN_BORDER,
            text_color=CYAN,
            command=self._on_refresh,
        )
        self._refresh_btn.pack(side="right")

        self._status_lbl = ctk.CTkLabel(inner, text="Awaiting scan…",
                                         font=F_MONO_XS, text_color=T2)
        self._status_lbl.pack(side="right", padx=(0, 10))

        # ── progress bar (shown while loading) ───────────────────────────────
        self._progress = ctk.CTkProgressBar(self, height=3, corner_radius=0,
                                             fg_color=BG3, progress_color=CYAN)
        self._progress.set(0)
        self._progress.pack(fill="x", padx=14, pady=(0, 4))
        self._progress.pack_forget()

        # ── health score widget ───────────────────────────────────────────────
        self._health_widget = HealthScoreWidget(self)
        self._health_widget.pack(fill="x", padx=14, pady=(0, 8))

        # ── issues list ───────────────────────────────────────────────────────
        self._issues_list = IssuesList(self)
        self._issues_list.pack(fill="x", padx=14, pady=(0, 8))

        # ── AI recommendations list ───────────────────────────────────────────
        self._ai_recs_list = AIRecommendationsList(self)
        self._ai_recs_list.pack(fill="x", padx=14, pady=(0, 8))

        # ── summary strip placeholder ─────────────────────────────────────────
        self._summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._summary_frame.pack(fill="x", padx=14, pady=(0, 6))

        # ── filter bar placeholder ────────────────────────────────────────────
        self._filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._filter_frame.pack(fill="x", padx=14, pady=(0, 8))

        # ── scrollable card area ──────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               scrollbar_button_color=BG3,
                                               scrollbar_button_hover_color=BG4)
        self._scroll.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # idle placeholder
        self._idle_lbl = ctk.CTkLabel(
            self._scroll,
            text="Run a system scan to generate AI recommendations.",
            font=F_MONO_SM, text_color=T2,
        )
        self._idle_lbl.pack(pady=40)

    # ── public API ─────────────────────────────────────────────────────────────

    def load_report(self, report):
        """Call this after a scan completes to trigger async AI analysis."""
        from jenix_ai import RecommendationBridge
        self._show_loading()
        bridge = RecommendationBridge(gui_callback=self._on_recs_ready)
        bridge.run(report)

    def load_mock(self):
        """Load a demo set of recommendations without a real scan (for testing)."""
        from jenix_ai import JENIXAdvisor, Recommendation
        from types import SimpleNamespace

        mock_report = SimpleNamespace(
            distro="Ubuntu 22.04.3 LTS",
            kernel="5.15.0-91-generic",
            hostname="jenix-demo",
            packages=SimpleNamespace(
                package_manager="apt", broken=2, orphaned=14,
                missing_deps=1, broken_list=["libssl:broken", "curl:broken"],
                total_installed=1842,
            ),
            cpu=SimpleNamespace(model="Intel i7-10700", cores=8, threads=16,
                                load_percent=82.0, temperature_c=78.0),
            ram=SimpleNamespace(total_gb=8.0, used_gb=6.9, free_gb=1.1, percent_used=86.0),
            gpu=SimpleNamespace(model="NVIDIA GeForce RTX 3060", load_percent=40.0,
                                memory_used_mb=3200, memory_total_mb=12288, available=True),
            disks=[SimpleNamespace(mount="/", device="/dev/sda1",
                                   total_gb=200.0, used_gb=189.0,
                                   free_gb=11.0, percent_used=94.5)],
            open_ports=[
                SimpleNamespace(port=22,   protocol="tcp", service="SSH",    risk="low",  description="Secure Shell"),
                SimpleNamespace(port=23,   protocol="tcp", service="Telnet", risk="high", description="Unencrypted terminal"),
                SimpleNamespace(port=3306, protocol="tcp", service="MySQL",  risk="medium",description="MySQL database"),
                SimpleNamespace(port=5900, protocol="tcp", service="VNC",    risk="high", description="VNC remote desktop"),
            ],
            health=SimpleNamespace(
                uptime_str="up 3 days, 14 hours",
                load_avg_1=3.2, load_avg_5=2.8, load_avg_15=1.4,
                active_processes=312, zombie_processes=3,
                cache_files_mb=6200.0, temp_files_mb=2300.0,
            ),
        )

        self._show_loading()
        advisor = JENIXAdvisor(on_complete=self._on_recs_ready)
        advisor.analyse_async(mock_report)

    def refresh_health(self):
        """
        Run AIEngine.analyze_system() in a background thread and update
        the health score, issues, and AI recommendations widgets.
        """
        self._status_lbl.configure(text="🔄  Refreshing…", text_color=CYAN)
        self._refresh_btn.configure(state="disabled", text="…")

        def _worker():
            try:
                from core.ai_engine import AIEngine
            except ImportError:
                try:
                    from ai_engine import AIEngine
                except ImportError:
                    self.after(0, self._refresh_done_error,
                               "AI engine unavailable")
                    return
            try:
                engine   = AIEngine()
                analysis = engine.analyze_system()
                self.after(0, self._apply_health_refresh, analysis)
            except Exception as exc:
                self.after(0, self._refresh_done_error, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    # ── internal ───────────────────────────────────────────────────────────────

    def _on_refresh(self):
        self.refresh_health()

    def _apply_health_refresh(self, analysis: dict):
        """Called on main thread after refresh_health() completes."""
        self._health_widget.update(analysis)
        self._issues_list.update(analysis.get("issues", []))
        self._ai_recs_list.update(analysis.get("recommendations", []))

        score  = analysis.get("health_score", 0)
        issues = analysis.get("issues", [])

        color  = (GREEN if score >= 90 else
                  CYAN  if score >= 75 else
                  AMBER if score >= 55 else RED)

        self._status_lbl.configure(
            text=f"Score: {score}/100  ·  {len(issues)} issue(s)",
            text_color=color,
        )
        self._refresh_btn.configure(state="normal", text="⟳  Refresh")

    def _refresh_done_error(self, msg: str):
        self._status_lbl.configure(
            text=f"⚠  Refresh failed: {msg[:60]}",
            text_color=RED,
        )
        self._refresh_btn.configure(state="normal", text="⟳  Refresh")

    def _show_loading(self):
        self._idle_lbl.pack_forget()
        self._clear_cards()
        self._status_lbl.configure(text="🔄  Analysing system data…", text_color=T2)
        self._progress.pack(fill="x", padx=14, pady=(0, 4))
        self._animate_progress(0)

    def _animate_progress(self, val):
        if val < 0.9:
            self._progress.set(val)
            self.after(80, self._animate_progress, min(val + 0.015, 0.9))

    def _on_recs_ready(self, recs):
        # safe to call from any thread – routes to main thread via after()
        self.after(0, self._render_recs, recs)

    def _render_recs(self, recs):
        self._all_recs = recs
        self._progress.set(1.0)
        self.after(300, self._progress.pack_forget)

        total    = len(recs)
        critical = sum(1 for r in recs if r.priority == "Critical")
        high     = sum(1 for r in recs if r.priority == "High")
        self._status_lbl.configure(
            text=f"✓  {total} recommendations  ·  {critical} critical  ·  {high} high",
            text_color=RED if critical > 0 else AMBER if high > 0 else GREEN)

        # rebuild summary
        for w in self._summary_frame.winfo_children():
            w.destroy()
        RecommendationSummary(self._summary_frame, recs).pack(fill="x")

        # rebuild filter bar
        for w in self._filter_frame.winfo_children():
            w.destroy()
        FilterBar(self._filter_frame, self._apply_filter).pack(fill="x")

        self._filter_priority = "All"
        self._filter_category = "All"
        self._apply_filter("All", "All")

    def _apply_filter(self, priority: str, category: str):
        self._filter_priority = priority
        self._filter_category = category
        filtered = [r for r in self._all_recs
                    if (priority == "All" or r.priority == priority)
                    and (category == "All" or r.category == category)]
        self._render_cards(filtered)

    def _render_cards(self, recs):
        self._clear_cards()
        if not recs:
            lbl = ctk.CTkLabel(self._scroll,
                               text="No recommendations match the selected filters.",
                               font=F_MONO_SM, text_color=T2)
            lbl.pack(pady=30)
            self._cards.append(lbl)
            return

        for i, rec in enumerate(recs, 1):
            card = RecommendationCard(self._scroll, rec, i)
            card.pack(fill="x", pady=(0, 8))
            self._cards.append(card)

    def _clear_cards(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._cards = []


# ── standalone demo ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTk()
    root.title("JENIX – AI Recommendations Demo")
    root.geometry("900x780")
    root.configure(fg_color=BG1)

    ctk.CTkFrame(root, height=2, fg_color=CYAN, corner_radius=0).pack(fill="x")

    hdr = ctk.CTkFrame(root, height=46, fg_color=BG2, corner_radius=0)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    ctk.CTkLabel(hdr, text="JENIX", font=("Courier New", 15, "bold"),
                 text_color=CYAN).pack(side="left", padx=18, pady=10)
    ctk.CTkLabel(hdr, text="AI Recommendations Panel",
                 font=("Helvetica", 11), text_color=T2).pack(side="left")

    ctk.CTkFrame(root, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")

    panel = AIRecommendationsPanel(root)
    panel.pack(fill="both", expand=True)

    # Trigger real-time health refresh after the window appears
    root.after(600, panel.refresh_health)

    # Also load mock data for the detailed recommendation cards
    root.after(1200, panel.load_mock)

    root.mainloop()
