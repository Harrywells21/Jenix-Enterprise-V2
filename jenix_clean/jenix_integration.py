"""
jenix_integration.py
════════════════════
JENIX v4.4 — Backend Integration Patch for gui.py
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ── Patch guard — ensures patch_app() runs exactly once ──────────────────────
_PATCHED: bool = False

# ── Re-entry guard for _gui_log to prevent infinite loops ────────────────────
_GUI_LOG_ACTIVE = threading.local()

# ── Centralised logger ────────────────────────────────────────────────────────
_integration_logger = logging.getLogger("jenix.integration")


# ══════════════════════════════════════════════════════════════════════════════
# 1. SAFE IMPORT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _import_scan_engine():
    for mod_name in ("jenix_suspicious_process_detector", "jenix_scan_engine"):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "ScanEngine"):
                return mod.ScanEngine
        except ImportError:
            continue
    return None


def _import_fix_engine():
    try:
        from fix_engine import FixEngine
        return FixEngine
    except ImportError:
        return None


def _import_auto_responder():
    try:
        from auto_responder import AutoResponder, create_auto_response_monitor
        return AutoResponder, create_auto_response_monitor
    except ImportError:
        return None, None


def _import_realtime_monitor():
    try:
        from jenix_suspicious_process_detector import RealTimeMonitor
        return RealTimeMonitor
    except ImportError:
        return None


def _import_persistence():
    try:
        from jenix_persistence import PersistenceDetector, PersistenceRemediator
        return PersistenceDetector, PersistenceRemediator
    except ImportError:
        return None, None


# ══════════════════════════════════════════════════════════════════════════════
# 2. GUI LOG BRIDGE — with re-entry guard to prevent infinite loops
# ══════════════════════════════════════════════════════════════════════════════

def _gui_log(app: Any, level: str, msg: str) -> None:
    """
    Forward a log message to the rt_log panel only.
    Uses a thread-local re-entry guard to prevent infinite loops.
    Does NOT call _log() or utils.logger to avoid routing back here.
    """
    # Re-entry guard — if we're already inside _gui_log on this thread, skip
    if getattr(_GUI_LOG_ACTIVE, "active", False):
        return
    _GUI_LOG_ACTIVE.active = True

    try:
        # Only log to stdlib directly — never via _log() from gui.py
        level_upper = level.upper()
        if level_upper in ("OK", "SUCCESS"):
            _integration_logger.info(msg)
        elif level_upper in ("WARN", "WARNING"):
            _integration_logger.warning(msg)
        elif level_upper in ("ERR", "ERROR"):
            _integration_logger.error(msg)
        else:
            _integration_logger.info(msg)

        def _post():
            try:
                if not app.winfo_exists():
                    return
                # Primary: rt_log panel only — no LogBox to avoid double logging
                rt = getattr(app, "rt_log", None)
                if rt is not None and hasattr(rt, "log"):
                    try:
                        rt.log(msg, level)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            app.after(0, _post)
        except Exception:
            pass

    finally:
        _GUI_LOG_ACTIVE.active = False


# ══════════════════════════════════════════════════════════════════════════════
# 3. CORE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _init_components(app: Any) -> None:
    """
    Instantiate all backend components and attach them to *app*.
    All failures are caught individually so a missing module never
    prevents the others from loading.
    """

    # ── 3a. ScanEngine ────────────────────────────────────────────────────────
    ScanEngine = _import_scan_engine()
    if ScanEngine is not None:
        try:
            try:
                app._scan_engine = ScanEngine(enable_persistence=True)
            except TypeError:
                app._scan_engine = ScanEngine()
            _gui_log(app, "OK", "ScanEngine initialised")
        except Exception as exc:
            app._scan_engine = None
            _integration_logger.error("ScanEngine init failed: %s", exc)
            _gui_log(app, "WARN", f"ScanEngine init failed: {exc}")
    else:
        app._scan_engine = None
        _integration_logger.warning("ScanEngine not available — optional module missing")

    # ── 3b. FixEngine ─────────────────────────────────────────────────────────
    if getattr(app, "fix_engine", None) is None:
        FixEngine = _import_fix_engine()
        if FixEngine is not None:
            try:
                app.fix_engine = FixEngine(
                    confirm_fn=lambda prompt: _threadsafe_confirm(app, prompt)
                )
                _gui_log(app, "OK", "FixEngine initialised")
            except Exception as exc:
                app.fix_engine = None
                _integration_logger.error("FixEngine init failed: %s", exc)
                _gui_log(app, "WARN", f"FixEngine init failed: {exc}")

    # ── 3c. PersistenceDetector ───────────────────────────────────────────────
    PersistenceDetector, PersistenceRemediator = _import_persistence()
    if PersistenceDetector is not None:
        try:
            app._persistence_detector   = PersistenceDetector()
            app._persistence_remediator = PersistenceRemediator()
            _gui_log(app, "OK", "PersistenceDetector initialised")
        except Exception as exc:
            app._persistence_detector   = None
            app._persistence_remediator = None
            _integration_logger.error("PersistenceDetector init failed: %s", exc)
    else:
        app._persistence_detector   = None
        app._persistence_remediator = None

    # ── 3d. AutoResponder + RealTimeMonitor ───────────────────────────────────
    _init_monitor_and_responder(app)

    # ── 3e. State flags ───────────────────────────────────────────────────────
    app._monitoring_active  = False
    app._scan_running       = False
    app._last_scan_result   = None
    app._persistence_issues = []

    _gui_log(app, "INFO", "JENIX backend integration complete")


def _init_monitor_and_responder(app: Any) -> None:
    """
    Build AutoResponder and RealTimeMonitor (both optional).
    Neither is started here — call app.start_monitoring() for that.
    """
    AutoResponder, create_auto_response_monitor = _import_auto_responder()
    RealTimeMonitor = _import_realtime_monitor()

    app._auto_responder = None
    app._rtm            = None

    if AutoResponder is None:
        _integration_logger.warning("AutoResponder unavailable — monitoring disabled")
        _gui_log(app, "WARN", "RealTimeMonitor not available")
        return

    fix_engine = getattr(app, "fix_engine", None)

    try:
        app._auto_responder = AutoResponder(
            fix_engine           = fix_engine,
            high_threat_callback = lambda issue: _on_high_threat(app, issue),
            paused               = True,
            enable_forensics     = True,
            forensic_sha256      = True,
        )
        _gui_log(app, "OK", "AutoResponder initialised (paused)")
    except Exception as exc:
        _integration_logger.error("AutoResponder init failed: %s", exc)
        _gui_log(app, "WARN", f"AutoResponder init failed: {exc}")
        return

    if RealTimeMonitor is None:
        _integration_logger.warning("RealTimeMonitor not available")
        return

    try:
        app._rtm = RealTimeMonitor(
            interval            = 10.0,
            on_threat_detected  = lambda issue: _on_threat_detected(app, issue),
            alert_levels        = {"HIGH", "CRITICAL"},
            enable_threat_intel = True,
        )
        _gui_log(app, "OK", "RealTimeMonitor created (not yet started)")
    except Exception as exc:
        _integration_logger.error("RealTimeMonitor init failed: %s", exc)
        _gui_log(app, "WARN", f"RealTimeMonitor init failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. THREAT CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def _on_threat_detected(app: Any, issue: Any) -> None:
    level = getattr(issue, "threat_level", "UNKNOWN")
    pid   = getattr(issue, "pid",          "?")
    name  = getattr(issue, "name",         "?")
    score = getattr(issue, "threat_score", 0)

    log_level = "ERR" if level == "CRITICAL" else "WARN"
    _gui_log(app, log_level, f"[{level}] Process '{name}' PID {pid} score={score}")

    responder = getattr(app, "_auto_responder", None)
    if responder is not None:
        try:
            responder.handle_threat(issue)
        except Exception as exc:
            _integration_logger.error("AutoResponder.handle_threat failed: %s", exc)


def _on_high_threat(app: Any, issue: Any) -> None:
    name  = getattr(issue, "name",         "?")
    pid   = getattr(issue, "pid",          "?")
    score = getattr(issue, "threat_score", 0)
    _gui_log(app, "WARN", f"[HIGH] '{name}' PID {pid} score={score} — manual review required")


# ══════════════════════════════════════════════════════════════════════════════
# 5. PUBLIC API FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def run_scan(app: Any, progress_cb: Optional[Callable] = None) -> None:
    """Execute a full system scan on a background thread."""
    if getattr(app, "_scan_running", False):
        _gui_log(app, "WARN", "Scan already in progress")
        return

    if getattr(app, "_scan_engine", None) is None:
        _gui_log(app, "WARN", "ScanEngine not available — using legacy scan")
        return

    app._scan_running = True
    _gui_log(app, "INFO", "Full system scan started…")

    def _worker():
        try:
            def _progress(pct: int, msg: str):
                _integration_logger.debug("[%3d%%] %s", pct, msg)
                if progress_cb:
                    try:
                        progress_cb(pct, msg)
                    except Exception:
                        pass

            result = app._scan_engine.run_full_scan(progress_cb=_progress)
            app._last_scan_result = result

            persistence_issues = []
            detector = getattr(app, "_persistence_detector", None)
            if detector is not None:
                try:
                    persistence_issues = detector.scan()
                    app._persistence_issues = persistence_issues
                except Exception as exc:
                    _integration_logger.error("Persistence scan failed: %s", exc)

            app.after(0, lambda r=result, pi=persistence_issues:
                      _update_gui_after_scan(app, r, pi))

        except Exception as exc:
            _integration_logger.error("run_scan worker failed: %s", exc)
            app.after(0, lambda e=str(exc): _gui_log(app, "ERR", f"Scan failed: {e}"))
        finally:
            app._scan_running = False

    threading.Thread(target=_worker, name="jenix-scan", daemon=True).start()


def _update_gui_after_scan(app: Any, result: Any, persistence_issues: list) -> None:
    """Called on the main thread after a scan completes."""
    try:
        score      = getattr(result, "health_score",  0)
        grade      = getattr(result, "health_grade",  "?")
        status     = getattr(result, "health_status", "?")
        issues     = getattr(result, "issues",        [])
        ports      = getattr(result, "open_ports",    [])
        rich_procs = getattr(result, "rich_suspicious_procs",
                             getattr(result, "suspicious_procs", []))

        crit_count = sum(1 for i in issues if getattr(i, "severity", "") == "CRITICAL")
        high_count = sum(1 for i in issues if getattr(i, "severity", "") == "HIGH")
        red_ports  = sum(1 for p in ports  if getattr(p, "risk",     "") == "red")
        rich_count = len(rich_procs)

        _update_scan_cards(app, score, len(issues), len(ports))

        _gui_log(app, "OK",   f"Scan done — Score {score}/100 Grade {grade} [{status}]")
        _gui_log(app, "INFO", f"Issues: {len(issues)} total ({crit_count} critical, {high_count} high)")
        _gui_log(app, "INFO", f"Ports: {len(ports)} open ({red_ports} high-risk)")

        if rich_count:
            _gui_log(app, "WARN", f"Suspicious processes: {rich_count} flagged")

        if persistence_issues:
            p_high = sum(1 for p in persistence_issues if getattr(p, "risk", "") == "HIGH")
            _gui_log(app, "WARN" if p_high else "INFO",
                     f"Persistence scan: {len(persistence_issues)} items ({p_high} HIGH risk)")
            for pi in persistence_issues[:5]:
                _gui_log(app, "WARN" if getattr(pi, "risk", "") == "HIGH" else "INFO",
                         f"  [{pi.risk}] [{pi.source.upper()}] {pi.name}: {pi.reason}")

        fix_engine = getattr(app, "fix_engine", None)
        if fix_engine is not None and result is not None:
            try:
                plans = fix_engine.plan_fixes(result)
                if plans:
                    _gui_log(app, "INFO", f"FixEngine: {len(plans)} fix(es) planned")
            except Exception as exc:
                _integration_logger.warning("plan_fixes failed: %s", exc)

    except Exception as exc:
        _integration_logger.error("_update_gui_after_scan failed: %s", exc)
        _gui_log(app, "WARN", f"Post-scan GUI update error: {exc}")


def _update_scan_cards(app: Any, score: int, issue_count: int, port_count: int) -> None:
    """Update the StatCard widgets on the active ScanView (best-effort)."""
    try:
        from gui import GREEN, AMBER, RED, CYAN

        view  = getattr(app.content, "_cur", None)
        if view is None:
            return
        cards = getattr(view, "_cards", {})

        if "health" in cards:
            col = GREEN if score >= 80 else AMBER if score >= 60 else RED
            cards["health"].set(str(score), col)
        if "issues" in cards:
            cards["issues"].set(str(issue_count), RED if issue_count > 0 else GREEN)
        if "ports" in cards:
            cards["ports"].set(str(port_count), CYAN)
    except Exception:
        pass


def start_monitoring(app: Any) -> None:
    """Start the RealTimeMonitor and unpause the AutoResponder."""
    rtm       = getattr(app, "_rtm",            None)
    responder = getattr(app, "_auto_responder", None)

    if rtm is None:
        _gui_log(app, "WARN", "RealTimeMonitor not available")
        return

    if getattr(app, "_monitoring_active", False):
        _gui_log(app, "INFO", "Monitoring already active")
        return

    try:
        if responder is not None:
            responder.resume()
        rtm.start()
        app._monitoring_active = True
        _gui_log(app, "OK", "Real-Time Monitor started")
    except Exception as exc:
        _integration_logger.error("start_monitoring failed: %s", exc)
        _gui_log(app, "ERR", f"Failed to start monitoring: {exc}")


def stop_monitoring(app: Any) -> None:
    """Stop the RealTimeMonitor and pause the AutoResponder."""
    rtm       = getattr(app, "_rtm",            None)
    responder = getattr(app, "_auto_responder", None)

    if not getattr(app, "_monitoring_active", False):
        return

    try:
        if responder is not None:
            responder.pause()
        if rtm is not None:
            try:
                rtm.stop(timeout=8.0)
            except TypeError:
                rtm.stop()
        app._monitoring_active = False
        _gui_log(app, "OK", "Real-Time Monitor stopped")
    except Exception as exc:
        _integration_logger.error("stop_monitoring failed: %s", exc)
        _gui_log(app, "WARN", f"Stop-monitoring error: {exc}")


def rollback_action(app: Any) -> None:
    """Roll back the last automated kill recorded by AutoResponder."""
    responder = getattr(app, "_auto_responder", None)
    if responder is None:
        _gui_log(app, "WARN", "AutoResponder not available — cannot rollback")
        return

    _gui_log(app, "INFO", "Attempting rollback of last automated action…")

    def _worker():
        try:
            record = responder.rollback_last_action()
            if record is None:
                app.after(0, lambda: _gui_log(app, "INFO", "No automated actions to rollback"))
            else:
                outcome  = getattr(record, "outcome",        "unknown")
                name     = getattr(record, "name",           "?")
                pid      = getattr(record, "pid",            "?")
                forensic = getattr(record, "forensic_path",  "")
                msg = f"Rollback for '{name}' PID {pid} — outcome: {outcome}"
                if forensic:
                    msg += f" [forensic: {Path(forensic).name}]"
                app.after(0, lambda m=msg: _gui_log(app, "OK", m))
        except Exception as exc:
            _integration_logger.error("rollback_action worker failed: %s", exc)
            app.after(0, lambda e=str(exc): _gui_log(app, "ERR", f"Rollback failed: {e}"))

    threading.Thread(target=_worker, name="jenix-rollback", daemon=True).start()


def auto_fix_all(
    app:         Any,
    dry_run:     bool = True,
    confirm_all: bool = False,
) -> None:
    """Run FixEngine.apply_all_fixes() on the last scan result."""
    fix_engine  = getattr(app, "fix_engine",        None)
    scan_result = getattr(app, "_last_scan_result",  None)

    if fix_engine is None:
        _gui_log(app, "WARN", "FixEngine not available")
        return

    if scan_result is None:
        _gui_log(app, "WARN", "No scan result available — run a scan first")
        return

    mode = "DRY RUN" if dry_run else "LIVE"
    _gui_log(app, "INFO", f"AUTO FIX starting ({mode})…")

    def _worker():
        try:
            summary = fix_engine.apply_all_fixes(
                scan_result, dry_run=dry_run, confirm_all=confirm_all,
            )
            app.after(0, lambda s=summary: _show_autofix_result(app, s))
        except Exception as exc:
            _integration_logger.error("auto_fix_all worker failed: %s", exc)
            app.after(0, lambda e=str(exc): _gui_log(app, "ERR", f"AUTO FIX failed: {e}"))

    threading.Thread(target=_worker, name="jenix-autofix", daemon=True).start()


def _show_autofix_result(app: Any, summary: Any) -> None:
    """Open the AutoFixResultModal defined in gui.py."""
    applied = getattr(summary, "applied", 0)
    failed  = getattr(summary, "failed",  0)
    skipped = getattr(summary, "skipped", 0)
    msg     = getattr(summary, "smart_message", "")

    _gui_log(app, "OK" if failed == 0 and applied > 0 else "INFO",
             f"AUTO FIX — applied:{applied} failed:{failed} skipped:{skipped}")
    if msg:
        _gui_log(app, "INFO", msg[:120])

    try:
        from gui import AutoFixResultModal
        AutoFixResultModal(app, summary)
    except Exception as exc:
        _integration_logger.warning("AutoFixResultModal unavailable: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# 6. MONITORING CONTROL PANEL INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def _inject_monitoring_panel(app: Any) -> None:
    """
    Adds a small Real-Time Monitor control panel to the current ScanView
    if one exists and does not already have the panel.
    """
    try:
        import customtkinter as ctk
        from gui import (
            BG2, BG3, BG4, BORDER, CYAN, CYANL, GREEN, AMBER,
            CYAN_BORDER, AMBER_BORDER,
            F_MONO_XS, F_LABEL, T1, T2,
        )
    except Exception:
        return

    view = getattr(app.content, "_cur", None)
    if view is None:
        return

    if getattr(view, "_monitor_panel_injected", False):
        return

    # Find the scrollable frame
    scroll = None
    for child in view.winfo_children():
        if "scrollableframe" in type(child).__name__.lower():
            scroll = child
            break
    if scroll is None:
        return

    try:
        panel = ctk.CTkFrame(
            scroll, fg_color=BG2, corner_radius=8,
            border_width=1, border_color=BORDER,
        )
        panel.pack(fill="x", pady=(0, 10), padx=0)

        hdr = ctk.CTkFrame(panel, fg_color="transparent", height=36)
        hdr.pack(fill="x", padx=14, pady=(10, 0))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🛡  Real-Time Monitor",
                     font=F_LABEL, text_color=T1).pack(side="left")

        from gui import GREEN_BORDER
        status_badge = ctk.CTkFrame(
            hdr, fg_color="#0a1f06", corner_radius=4,
            border_width=1, border_color=GREEN_BORDER,
        )
        _status_lbl = ctk.CTkLabel(
            status_badge, text="● STOPPED",
            font=F_MONO_XS, text_color=GREEN, padx=8, pady=3,
        )
        _status_lbl.pack()
        status_badge.pack(side="right")

        ctk.CTkFrame(panel, height=1, fg_color=BORDER).pack(fill="x", pady=(6, 0))

        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.pack(padx=14, pady=10)

        def _toggle_monitor():
            if getattr(app, "_monitoring_active", False):
                stop_monitoring(app)
                try:
                    _status_lbl.configure(text="● STOPPED", text_color=GREEN)
                    start_btn.configure(text="▶  START MONITOR")
                except Exception:
                    pass
            else:
                start_monitoring(app)
                try:
                    _status_lbl.configure(text="● RUNNING", text_color=CYAN)
                    start_btn.configure(text="■  STOP MONITOR")
                except Exception:
                    pass

        start_btn = ctk.CTkButton(
            btn_row, text="▶  START MONITOR", width=160, height=30,
            font=F_MONO_XS, fg_color=GREEN, hover_color="#2acc0e",
            text_color="#000000", corner_radius=6,
            command=_toggle_monitor,
        )
        start_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="⟳  FULL SCAN", width=120, height=30,
            font=F_MONO_XS, fg_color=CYAN, hover_color=CYANL,
            text_color="#000000", corner_radius=6,
            command=lambda: run_scan(app),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="↩  ROLLBACK", width=110, height=30,
            font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
            text_color=AMBER, corner_radius=6,
            border_width=1, border_color=AMBER_BORDER,
            command=lambda: rollback_action(app),
        ).pack(side="left")

        view._monitor_panel_injected = True

    except Exception as exc:
        _integration_logger.warning("_inject_monitoring_panel failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# 7. THREAD-SAFE CONFIRM BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

def _threadsafe_confirm(app: Any, prompt: str) -> bool:
    """
    Blocks the calling (worker) thread until the user responds via GUI dialog.
    Returns True if confirmed, False otherwise. Times out after 30 s → False.
    """
    result_holder: List[bool] = [False]
    done_event = threading.Event()

    def _show():
        try:
            import customtkinter as ctk
            from gui import (
                BG1, BG2, BG3, BG4, BORDER, AMBER, AMBER_BORDER,
                F_MONO_XS, F_MONO_SM, T1, T2,
            )

            dlg = ctk.CTkToplevel(app)
            dlg.title("JENIX — Confirm")
            dlg.geometry("520x220")
            dlg.configure(fg_color=BG1)
            dlg.grab_set()
            dlg.lift()

            ctk.CTkFrame(dlg, height=3, fg_color=AMBER, corner_radius=0).pack(fill="x")
            body = ctk.CTkFrame(dlg, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=20, pady=14)

            ctk.CTkLabel(
                body, text="⚠  Fix Action Requires Confirmation",
                font=("Courier New", 12, "bold"), text_color=AMBER,
            ).pack(anchor="w", pady=(0, 8))

            mf = ctk.CTkFrame(body, fg_color=BG2, corner_radius=6,
                               border_width=1, border_color=BORDER)
            mf.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(
                mf, text=str(prompt)[:280],
                font=F_MONO_XS, text_color=T1,
                wraplength=460, justify="left",
            ).pack(anchor="w", padx=12, pady=10)

            br = ctk.CTkFrame(body, fg_color="transparent")
            br.pack(fill="x")

            def _yes():
                result_holder[0] = True
                done_event.set()
                dlg.destroy()

            def _no():
                done_event.set()
                dlg.destroy()

            ctk.CTkButton(
                br, text="✓  YES", width=100, height=30,
                fg_color=AMBER, hover_color="#d49a00",
                text_color="#000000", font=F_MONO_SM,
                corner_radius=4, command=_yes,
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                br, text="✕  NO", width=80, height=30,
                fg_color=BG3, hover_color=BG4,
                text_color=T2, font=F_MONO_XS,
                corner_radius=4, command=_no,
            ).pack(side="left")

        except Exception as exc:
            _integration_logger.error("_threadsafe_confirm dialog failed: %s", exc)
            done_event.set()

    app.after(0, _show)
    done_event.wait(timeout=30)
    return result_holder[0]


# ══════════════════════════════════════════════════════════════════════════════
# 8. PERSISTENCE REPORT
# ══════════════════════════════════════════════════════════════════════════════

def show_persistence_report(app: Any) -> None:
    issues = getattr(app, "_persistence_issues", [])
    if not issues:
        _gui_log(app, "INFO", "No persistence issues found (run a scan first)")
        return

    lines = [
        "JENIX — PERSISTENCE SCAN REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Issues found: {len(issues)}",
        "═" * 70, "",
    ]
    risk_icons = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}
    for pi in issues:
        icon = risk_icons.get(getattr(pi, "risk", "LOW"), "•")
        lines += [
            f"{icon} [{pi.risk}] [{pi.source.upper()}] {pi.name}",
            f"   Command : {pi.command[:110]}",
            f"   Reason  : {pi.reason}",
            f"   Fix     : {pi.fix_suggestion}",
            "",
        ]

    report_txt = "\n".join(lines)

    try:
        from gui import _TextWindow
        _TextWindow(app, "Persistence Scan Report", report_txt)
    except Exception as exc:
        _integration_logger.warning("_TextWindow unavailable: %s", exc)
        _gui_log(app, "INFO", f"Persistence report ({len(issues)} items) — see log")


# ══════════════════════════════════════════════════════════════════════════════
# 9. MONITORING STATS
# ══════════════════════════════════════════════════════════════════════════════

def get_monitoring_stats(app: Any) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "monitoring_active": getattr(app, "_monitoring_active", False),
        "scan_running":      getattr(app, "_scan_running",      False),
        "persistence_issues":len(getattr(app, "_persistence_issues", [])),
    }

    rtm = getattr(app, "_rtm", None)
    if rtm is not None:
        try:
            stats["rtm"] = rtm.get_stats()
        except Exception:
            stats["rtm"] = {}

    responder = getattr(app, "_auto_responder", None)
    if responder is not None:
        try:
            stats["auto_responder"] = responder.get_stats()
        except Exception:
            stats["auto_responder"] = {}

    fix_engine = getattr(app, "fix_engine", None)
    if fix_engine is not None:
        try:
            stats["rollbacks_available"] = fix_engine.list_available_rollbacks()
        except Exception:
            stats["rollbacks_available"] = []

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# 10. GRACEFUL SHUTDOWN
# ══════════════════════════════════════════════════════════════════════════════

def _on_app_close(app: Any) -> None:
    """Ensure background threads are stopped before the window closes."""
    _integration_logger.info("JENIX shutdown — stopping background threads")
    try:
        stop_monitoring(app)
    except Exception as exc:
        _integration_logger.warning("stop_monitoring on close failed: %s", exc)
    try:
        app.destroy()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# 11. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def patch_app(app: Any) -> None:
    """
    Attach all JENIX backend components to *app* and expose the public API
    as methods on the app instance. Guarded by _PATCHED so it runs only once.
    """
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    _integration_logger.info("patch_app() called — initialising backend components")

    # Initialise all backend singletons
    _init_components(app)

    # Bind public methods to the app instance
    import types

    app.run_scan                = types.MethodType(lambda self, cb=None: run_scan(self, cb),               app)
    app.start_monitoring        = types.MethodType(lambda self: start_monitoring(self),                    app)
    app.stop_monitoring         = types.MethodType(lambda self: stop_monitoring(self),                     app)
    app.rollback_action         = types.MethodType(lambda self: rollback_action(self),                     app)
    app.auto_fix_all            = types.MethodType(lambda self, d=True, c=False: auto_fix_all(self, d, c), app)
    app.show_persistence_report = types.MethodType(lambda self: show_persistence_report(self),             app)
    app.get_monitoring_stats    = types.MethodType(lambda self: get_monitoring_stats(self),                app)

    # Expose a convenience _gui_log method
    app._gui_log = lambda level, msg: _gui_log(app, level, msg)

    # Patch nav so monitoring panel is injected when Scan tab is shown
    _original_nav = app._nav

    def _patched_nav(key: str) -> None:
        _original_nav(key)
        if key == "scan":
            app.after(200, lambda: _inject_monitoring_panel(app))

    app._nav = _patched_nav

    # Register clean shutdown
    app.protocol("WM_DELETE_WINDOW", lambda: _on_app_close(app))

    # Inject monitoring panel now if scan tab is already showing
    app.after(500, lambda: _inject_monitoring_panel(app))

    # Log completion using print to avoid any routing loop
    print("[jenix_integration] patch applied successfully")
    _integration_logger.info("patch_app() complete")
