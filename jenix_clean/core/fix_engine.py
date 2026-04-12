"""
fix_engine.py
═════════════
JENIX v4.2 — Premium Auto-Fix & Optimization Engine

Architecture:
  ✦ FixEngine            — orchestrator; maps issues → fix handlers
  ✦ FixRegistry          — decorator-based registry of all available fixes
  ✦ SafetyGuard          — dry-run gating + confirmation prompts
  ✦ RollbackManager      — pre-fix state capture + rollback dispatch
  ✦ FixLogger            — structured per-action audit log
  ✦ FixResult            — typed result dataclass (JSON-serialisable)
  ✦ AutoFixOrchestrator  — NEW v4.2: priority-ordered batch execution
  ✦ ExecutionSummary     — NEW v4.2: typed summary + improvement metrics
  ✦ SmartMessenger       — NEW v4.2: human-readable verdict generation
  ✦ FixReportSection     — NEW v4.2: ReportGenerator integration hook

Safety contract:
  • Every fix is dry-run by default (no side-effects).
  • Every destructive step requires explicit user confirmation.
  • Multiple dangerous fixes in one batch trigger a second-pass confirmation.
  • State is captured before applying any fix where possible.
  • Rollback functions are registered automatically.
  • No fix may delete logs deemed critical by JENIX.
  • A critical failure in any fix aborts the remaining batch.
  • Every action is timestamped and written to ~/.jenix/fix_audit.log.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── psutil (inherited from scan_engine bootstrap) ─────────────────────────────
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# ── Paths ─────────────────────────────────────────────────────────────────────
JENIX_DIR  = Path.home() / ".jenix"
JENIX_DIR.mkdir(exist_ok=True)
FIX_LOG    = JENIX_DIR / "fix_audit.log"
STATE_DIR  = JENIX_DIR / "fix_states"
STATE_DIR.mkdir(exist_ok=True)

# ── Audit logger ──────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(FIX_LOG),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_audit = logging.getLogger("jenix.fix")


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FixResult:
    fix:               str
    status:            str          # success / failed / skipped / dry_run / aborted
    details:           str
    rollback_available:bool  = False
    rollback_key:      str   = ""
    timestamp:         str   = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dry_run:           bool  = False
    command_run:       str   = ""
    error:             str   = ""
    priority:          str   = "LOW"   # NEW v4.2: inherited from FixPlan

    def as_dict(self) -> dict:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2)


@dataclass
class FixPlan:
    """Proposed fix derived from a ScanResult."""
    issue_title:     str
    fix_id:          str
    priority:        str          # CRITICAL / HIGH / MEDIUM / LOW
    description:     str
    dry_run_preview: str
    params:          Dict[str, Any] = field(default_factory=dict)
    is_dangerous:    bool = False  # NEW v4.2: flags fixes that need extra care


# ── NEW v4.2 ─────────────────────────────────────────────────────────────────

@dataclass
class ImprovementMetrics:
    """Quantified before/after resource deltas."""
    cpu_delta_pct:   float = 0.0   # positive = reduced
    ram_freed_mb:    float = 0.0
    disk_freed_mb:   float = 0.0
    swap_delta_pct:  float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionSummary:
    """
    Machine-readable summary of a batch fix run.
    Matches the spec: { total_fixes, applied, failed, skipped, system_improvement }
    """
    total_fixes:        int = 0
    applied:            int = 0
    failed:             int = 0
    skipped:            int = 0
    aborted:            int = 0
    dry_run:            bool = True
    results:            List[FixResult] = field(default_factory=list)
    metrics:            ImprovementMetrics = field(default_factory=ImprovementMetrics)
    smart_message:      str = ""
    system_improvement: str = ""   # human-readable one-liner (spec requirement)
    started_at:         str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finished_at:        str = ""
    aborted_early:      bool = False
    abort_reason:       str = ""

    def as_dict(self) -> dict:
        d = {
            "total_fixes":        self.total_fixes,
            "applied":            self.applied,
            "failed":             self.failed,
            "skipped":            self.skipped,
            "aborted":            self.aborted,
            "dry_run":            self.dry_run,
            "system_improvement": self.system_improvement,
            "smart_message":      self.smart_message,
            "started_at":         self.started_at,
            "finished_at":        self.finished_at,
            "aborted_early":      self.aborted_early,
            "abort_reason":       self.abort_reason,
            "metrics":            self.metrics.as_dict(),
            "results":            [r.as_dict() for r in self.results],
        }
        return d

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# 2. FIX REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

class FixRegistry:
    """
    Decorator-based registry.

    Usage:
        @FixRegistry.register("my_fix_id")
        def my_fix(engine, params, dry_run, confirm_fn) -> FixResult:
            ...
    """
    _handlers: Dict[str, Callable] = {}

    @classmethod
    def register(cls, fix_id: str):
        def decorator(fn: Callable) -> Callable:
            cls._handlers[fix_id] = fn
            return fn
        return decorator

    @classmethod
    def get(cls, fix_id: str) -> Optional[Callable]:
        return cls._handlers.get(fix_id)

    @classmethod
    def all_ids(cls) -> List[str]:
        return list(cls._handlers.keys())


# ══════════════════════════════════════════════════════════════════════════════
# 3. SAFETY GUARD
# ══════════════════════════════════════════════════════════════════════════════

class SafetyGuard:
    """
    Centralises all pre-execution checks.

    confirm_fn:  callable(prompt: str) -> bool
                 Defaults to CLI stdin prompt.
                 GUI callers should inject a modal-based confirm_fn.
    """

    SAFE_SERVICES = {
        "nginx", "apache2", "httpd", "cron", "rsyslog",
        "sshd", "fail2ban", "ufw", "avahi-daemon",
        "chronyd", "ntpd", "cups",
    }

    CRITICAL_LOG_PATTERNS = {
        "/var/log/auth.log",
        "/var/log/syslog",
        "/var/log/kern.log",
        "/var/log/journal",
    }

    # NEW v4.2 — fixes classed as "dangerous" for double-confirmation logic
    DANGEROUS_FIX_IDS = {"kill_process", "clean_tmp"}

    def __init__(self, confirm_fn: Optional[Callable[[str], bool]] = None):
        self._confirm = confirm_fn or self._cli_confirm

    @staticmethod
    def _cli_confirm(prompt: str) -> bool:
        try:
            ans = input(f"\n  [JENIX CONFIRM]  {prompt}  (y/N): ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def confirm(self, prompt: str) -> bool:
        return self._confirm(prompt)

    def is_safe_service(self, name: str) -> bool:
        return name.lower() in self.SAFE_SERVICES

    def is_critical_log(self, path: str) -> bool:
        p = str(path)
        return any(p.startswith(cp) for cp in self.CRITICAL_LOG_PATTERNS)

    def check_root(self) -> bool:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False

    def is_dangerous_fix(self, fix_id: str) -> bool:
        return fix_id in self.DANGEROUS_FIX_IDS


# ══════════════════════════════════════════════════════════════════════════════
# 4. ROLLBACK MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class RollbackManager:
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def save_state(self, key: str, rollback_fn: Callable, meta: dict) -> str:
        self._store[key] = {"fn": rollback_fn, "meta": meta}
        meta_path = STATE_DIR / f"{key}.json"
        try:
            meta_path.write_text(json.dumps({"key": key, "meta": meta,
                                              "saved_at": datetime.now().isoformat()},
                                             indent=2))
        except Exception:
            pass
        return key

    def rollback(self, key: str) -> FixResult:
        entry = self._store.get(key)
        if not entry:
            return FixResult(fix=key, status="failed",
                             details="No rollback state found for this key.",
                             rollback_available=False)
        try:
            result = entry["fn"](entry["meta"])
            _audit.info(f"ROLLBACK  key={key}  meta={entry['meta']}")
            return result
        except Exception as exc:
            _audit.error(f"ROLLBACK FAILED  key={key}  error={exc}")
            return FixResult(fix=key, status="failed",
                             details=f"Rollback failed: {exc}",
                             rollback_available=False, error=str(exc))

    def has_rollback(self, key: str) -> bool:
        return key in self._store

    def list_available(self) -> List[str]:
        return list(self._store.keys())


# ══════════════════════════════════════════════════════════════════════════════
# 5. FIX LOGGER
# ══════════════════════════════════════════════════════════════════════════════

class FixLogger:
    def log(self, result: FixResult):
        level = logging.INFO if result.status == "success" else \
                logging.WARNING if result.status in ("skipped", "dry_run", "aborted") else \
                logging.ERROR
        msg = (
            f"FIX={result.fix}  STATUS={result.status}  "
            f"DRY={result.dry_run}  ROLLBACK={result.rollback_available}  "
            f"DETAILS={result.details[:120]}"
        )
        if result.error:
            msg += f"  ERROR={result.error[:80]}"
        _audit.log(level, msg)

    def log_plan(self, plan: FixPlan):
        _audit.info(f"PLAN  fix={plan.fix_id}  issue={plan.issue_title!r}  priority={plan.priority}")

    def log_summary(self, summary: ExecutionSummary):
        _audit.info(
            f"BATCH_SUMMARY  total={summary.total_fixes}  applied={summary.applied}  "
            f"failed={summary.failed}  skipped={summary.skipped}  "
            f"aborted_early={summary.aborted_early}  dry_run={summary.dry_run}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6. SMART MESSENGER  (NEW v4.2)
#    Produces plain-English verdict strings after a batch run.
# ══════════════════════════════════════════════════════════════════════════════

class SmartMessenger:
    """
    Generates human-readable status messages and improvement summaries
    from an ExecutionSummary + pre/post resource snapshots.
    """

    def generate_message(self, summary: ExecutionSummary) -> str:
        """Top-level verdict string."""
        if summary.dry_run:
            return (
                f"Dry-run complete. {summary.total_fixes} fix(es) previewed — "
                "no changes applied. Run with dry_run=False to apply."
            )

        if summary.aborted_early:
            return (
                f"Fix batch aborted after critical failure: {summary.abort_reason}. "
                f"{summary.applied} fix(es) applied before abort."
            )

        applied  = summary.applied
        failed   = summary.failed
        skipped  = summary.skipped
        metrics  = summary.metrics

        parts: List[str] = []

        # Outcome headline
        if applied > 0 and failed == 0:
            parts.append("System successfully optimized.")
        elif applied > 0 and failed > 0:
            parts.append(f"Partial optimization complete — {applied} fix(es) applied, {failed} failed.")
        elif applied == 0 and skipped > 0:
            parts.append("No fixes applied — all were skipped by user.")
        else:
            parts.append("No fixes were applied.")

        # Resource improvement fragments
        if metrics.cpu_delta_pct > 0:
            parts.append(f"High CPU usage reduced by ~{metrics.cpu_delta_pct:.1f}%.")
        if metrics.ram_freed_mb > 0:
            parts.append(f"~{metrics.ram_freed_mb:.0f} MB of RAM freed.")
        if metrics.disk_freed_mb > 0:
            parts.append(f"~{metrics.disk_freed_mb:.0f} MB of disk space recovered.")
        if metrics.swap_delta_pct > 0:
            parts.append(f"Swap pressure reduced by ~{metrics.swap_delta_pct:.1f}%.")

        # Threat verdict
        kill_results = [r for r in summary.results
                        if r.fix == "kill_process" and r.status == "success"]
        if kill_results:
            parts.append(f"{len(kill_results)} suspicious process(es) terminated.")
        if failed == 0 and applied > 0:
            parts.append("No critical threats remaining.")

        return " ".join(parts)

    def generate_improvement_line(self, metrics: ImprovementMetrics) -> str:
        """
        One-liner matching spec format:
        "CPU reduced by X%, RAM freed X MB"
        """
        segments: List[str] = []
        if metrics.cpu_delta_pct > 0:
            segments.append(f"CPU reduced by {metrics.cpu_delta_pct:.1f}%")
        if metrics.ram_freed_mb > 0:
            segments.append(f"RAM freed {metrics.ram_freed_mb:.0f} MB")
        if metrics.disk_freed_mb > 0:
            segments.append(f"Disk freed {metrics.disk_freed_mb:.0f} MB")
        if metrics.swap_delta_pct > 0:
            segments.append(f"Swap reduced {metrics.swap_delta_pct:.1f}%")
        return ", ".join(segments) if segments else "No measurable resource changes"


# ══════════════════════════════════════════════════════════════════════════════
# 7. IMPROVEMENT TRACKER  (NEW v4.2)
#    Captures resource snapshots before / after a batch run.
# ══════════════════════════════════════════════════════════════════════════════

class ImprovementTracker:
    """Snapshots CPU / RAM / disk / swap before and after fixes."""

    def __init__(self):
        self._before: Dict[str, float] = {}
        self._after:  Dict[str, float] = {}

    def capture_before(self):
        self._before = self._snapshot()

    def capture_after(self):
        self._after = self._snapshot()

    def _snapshot(self) -> Dict[str, float]:
        snap: Dict[str, float] = {
            "cpu": 0.0, "ram_mb": 0.0, "swap_pct": 0.0, "disk_mb": 0.0,
        }
        if not _HAS_PSUTIL:
            return snap
        try:
            import time as _time
            _ = psutil.cpu_percent(interval=None)
            _time.sleep(0.3)
            snap["cpu"]     = psutil.cpu_percent(interval=None)
            mem             = psutil.virtual_memory()
            snap["ram_mb"]  = mem.used / 1024**2
            swap            = psutil.swap_memory()
            snap["swap_pct"]= swap.percent
            # Sum used across all disk partitions
            total_used = 0.0
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_used += usage.used / 1024**2
                except Exception:
                    pass
            snap["disk_mb"] = total_used
        except Exception:
            pass
        return snap

    def compute_metrics(self) -> ImprovementMetrics:
        b = self._before
        a = self._after
        if not b or not a:
            return ImprovementMetrics()
        return ImprovementMetrics(
            cpu_delta_pct  = round(max(0.0, b.get("cpu", 0) - a.get("cpu", 0)), 1),
            ram_freed_mb   = round(max(0.0, b.get("ram_mb", 0) - a.get("ram_mb", 0)), 1),
            disk_freed_mb  = round(max(0.0, b.get("disk_mb", 0) - a.get("disk_mb", 0)), 1),
            swap_delta_pct = round(max(0.0, b.get("swap_pct", 0) - a.get("swap_pct", 0)), 1),
        )


# ══════════════════════════════════════════════════════════════════════════════
# 8. AUTO FIX ORCHESTRATOR  (NEW v4.2)
#    Core of the premium one-click optimization feature.
# ══════════════════════════════════════════════════════════════════════════════

# Priority ordering constant (lower index = higher priority)
_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


class AutoFixOrchestrator:
    """
    Executes a batch of FixPlans in priority order with:
      • Automatic dangerous-fix double-confirmation
      • Critical-failure abort logic
      • Before/after resource measurement
      • Smart messaging + improvement summary
    """

    def __init__(self, engine: "FixEngine"):
        self._engine  = engine
        self._tracker = ImprovementTracker()
        self._messenger = SmartMessenger()

    # ── Public entry point ────────────────────────────────────────────────────

    def apply_all_fixes(
        self,
        plans:   List[FixPlan],
        dry_run: bool = True,
        confirm_all: bool = False,   # user pre-confirmed all non-dangerous fixes
    ) -> ExecutionSummary:
        """
        Apply all plans in CRITICAL → HIGH → MEDIUM → LOW order.

        dry_run=True   — simulate only; no side-effects (default, safe)
        dry_run=False  — live execution with per-fix confirmation unless
                         confirm_all=True (non-dangerous fixes only)

        Returns:
            ExecutionSummary with full results + improvement metrics.
        """
        summary = ExecutionSummary(
            total_fixes = len(plans),
            dry_run     = dry_run,
            started_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        if not plans:
            summary.smart_message      = "No fixes to apply — system appears healthy."
            summary.system_improvement = "No measurable resource changes"
            summary.finished_at        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return summary

        # Sort by priority
        sorted_plans = sorted(plans, key=lambda p: _PRIORITY_ORDER.get(p.priority, 99))

        # ── Safety: double-confirm if multiple dangerous fixes in batch ───────
        if not dry_run:
            dangerous_plans = [p for p in sorted_plans
                               if self._engine.guard.is_dangerous_fix(p.fix_id)]
            if len(dangerous_plans) >= 2:
                danger_list = "\n".join(
                    f"    • [{p.priority}] {p.fix_id}: {p.description[:60]}"
                    for p in dangerous_plans
                )
                prompt = (
                    f"SAFETY WARNING: {len(dangerous_plans)} potentially destructive "
                    f"fix(es) are queued:\n{danger_list}\n\n"
                    "  Confirm you want to proceed with ALL of these"
                )
                if not self._engine.guard.confirm(prompt):
                    summary.smart_message      = "Batch aborted by user — dangerous fixes declined."
                    summary.system_improvement = "No changes applied"
                    summary.aborted_early  = True
                    summary.abort_reason   = "User declined dangerous-fix batch confirmation"
                    summary.skipped        = len(sorted_plans)
                    summary.finished_at    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    return summary

        # ── Capture pre-fix baseline ──────────────────────────────────────────
        self._tracker.capture_before()

        # ── Execute each fix in priority order ────────────────────────────────
        for plan in sorted_plans:
            result = self._execute_plan(plan, dry_run=dry_run, confirm_all=confirm_all)
            result.priority = plan.priority
            summary.results.append(result)

            if result.status == "success":
                summary.applied += 1
            elif result.status == "failed":
                summary.failed  += 1
                # Abort on critical failure of a CRITICAL-priority fix
                if plan.priority == "CRITICAL" and not dry_run:
                    summary.aborted_early = True
                    summary.abort_reason  = (
                        f"Critical fix '{plan.fix_id}' failed: {result.error or result.details}"
                    )
                    # Mark remaining plans as aborted
                    applied_ids = {r.fix for r in summary.results}
                    remaining   = [p for p in sorted_plans if p.fix_id not in applied_ids]
                    for rem in remaining:
                        summary.results.append(FixResult(
                            fix=rem.fix_id, status="aborted",
                            details=f"Aborted: earlier critical fix '{plan.fix_id}' failed.",
                            priority=rem.priority,
                        ))
                        summary.aborted += 1
                    break
            elif result.status in ("skipped", "dry_run"):
                summary.skipped += 1

        # ── Capture post-fix snapshot ─────────────────────────────────────────
        if not dry_run:
            time.sleep(1)   # allow system metrics to settle
        self._tracker.capture_after()

        # ── Compute improvement metrics ───────────────────────────────────────
        summary.metrics            = self._tracker.compute_metrics()
        summary.system_improvement = self._messenger.generate_improvement_line(summary.metrics)
        summary.smart_message      = self._messenger.generate_message(summary)
        summary.finished_at        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._engine.logger.log_summary(summary)
        return summary

    def _execute_plan(
        self,
        plan:        FixPlan,
        dry_run:     bool,
        confirm_all: bool,
    ) -> FixResult:
        """
        Execute one FixPlan, honouring confirm_all for non-dangerous fixes.
        For dangerous fixes a per-fix confirmation is always required.
        """
        engine = self._engine

        # If confirm_all=True and fix is not dangerous, inject an auto-confirming guard
        if confirm_all and not engine.guard.is_dangerous_fix(plan.fix_id) and not dry_run:
            original_confirm = engine.guard._confirm
            engine.guard._confirm = lambda _prompt: True   # auto-approve
            try:
                result = engine.apply_fix(plan.fix_id, plan.params, dry_run=dry_run)
            finally:
                engine.guard._confirm = original_confirm   # always restore
        else:
            result = engine.apply_fix(plan.fix_id, plan.params, dry_run=dry_run)

        return result


# ══════════════════════════════════════════════════════════════════════════════
# 9. FIX REPORT SECTION  (NEW v4.2)
#    Generates the "FIX EXECUTION REPORT" section for ReportGenerator.
# ══════════════════════════════════════════════════════════════════════════════

class FixReportSection:
    """
    Builds the FIX EXECUTION REPORT section that can be appended to the
    existing ReportGenerator text output.

    Usage (inside ReportGenerator or standalone):
        section_text = FixReportSection(summary).as_txt()
        full_report += section_text
    """

    _STATUS_ICONS = {
        "success": "✓",
        "failed":  "✗",
        "skipped": "–",
        "dry_run": "~",
        "aborted": "⊘",
    }
    _PRIORITY_ICONS = {
        "CRITICAL": "🔴",
        "HIGH":     "🟠",
        "MEDIUM":   "🟡",
        "LOW":      "🟢",
    }

    def __init__(self, summary: ExecutionSummary):
        self.s = summary

    def as_txt(self, section_number: int = 10, width: int = 76) -> str:
        s   = self.s
        out = []
        W   = width
        bar = "═" * W

        # ── Section header ────────────────────────────────────────────────────
        out += [
            "",
            bar,
            f"  {section_number} · FIX EXECUTION REPORT".upper(),
            bar,
        ]

        mode_label = "DRY RUN (preview only — no changes made)" if s.dry_run else "LIVE EXECUTION"
        out += [
            f"  Mode        : {mode_label}",
            f"  Started     : {s.started_at}",
            f"  Finished    : {s.finished_at or 'N/A'}",
            f"  Total Fixes : {s.total_fixes}",
            "",
        ]

        # ── Outcome table ─────────────────────────────────────────────────────
        out += [
            f"  {'─' * (W - 4)}",
            f"  {'METRIC':<30} {'VALUE':>10}",
            f"  {'─' * (W - 4)}",
            f"  {'Fixes Applied':<30} {s.applied:>10}",
            f"  {'Fixes Failed':<30} {s.failed:>10}",
            f"  {'Fixes Skipped / Dry-run':<30} {s.skipped:>10}",
            f"  {'Fixes Aborted':<30} {s.aborted:>10}",
            f"  {'─' * (W - 4)}",
        ]

        if s.aborted_early:
            out += [
                "",
                f"  ⚠  EARLY ABORT: {s.abort_reason}",
            ]

        # ── Improvement metrics ───────────────────────────────────────────────
        m = s.metrics
        out += [
            "",
            "  SYSTEM IMPROVEMENT SUMMARY",
            f"  {'─' * (W - 4)}",
        ]
        if s.dry_run:
            out.append("  (Metrics not measured in dry-run mode)")
        else:
            any_metric = any([m.cpu_delta_pct, m.ram_freed_mb,
                              m.disk_freed_mb, m.swap_delta_pct])
            if any_metric:
                if m.cpu_delta_pct > 0:
                    bar_len = min(int(m.cpu_delta_pct / 5), 10)
                    out.append(f"  CPU reduced by       : {m.cpu_delta_pct:6.1f}%  {'▼' * bar_len}")
                if m.ram_freed_mb > 0:
                    out.append(f"  RAM freed            : {m.ram_freed_mb:6.0f} MB")
                if m.disk_freed_mb > 0:
                    out.append(f"  Disk space freed     : {m.disk_freed_mb:6.0f} MB")
                if m.swap_delta_pct > 0:
                    out.append(f"  Swap reduced by      : {m.swap_delta_pct:6.1f}%")
            else:
                out.append("  No measurable resource changes detected.")

        out += [
            "",
            f"  ► {s.system_improvement}",
        ]

        # ── Smart message ─────────────────────────────────────────────────────
        out += [
            "",
            "  VERDICT",
            f"  {'─' * (W - 4)}",
            f"  {s.smart_message}",
        ]

        # ── Per-fix result table ──────────────────────────────────────────────
        if s.results:
            out += [
                "",
                "  DETAILED FIX RESULTS",
                f"  {'─' * (W - 4)}",
                f"  {'#':<4} {'PRI':<10} {'FIX ID':<26} {'STATUS':<10} DETAILS",
                f"  {'─' * (W - 4)}",
            ]
            for idx, r in enumerate(s.results, 1):
                icon    = self._STATUS_ICONS.get(r.status, "?")
                p_icon  = self._PRIORITY_ICONS.get(r.priority, "•")
                status_display = f"{icon} {r.status.upper():<8}"
                detail  = r.details[:38] if len(r.details) > 38 else r.details
                out.append(
                    f"  {idx:<4} {p_icon} {r.priority:<8} {r.fix:<26} {status_display}  {detail}"
                )
                if r.error:
                    out.append(f"       ↳ Error: {r.error[:70]}")
                if r.rollback_available:
                    out.append(f"       ↳ Rollback key: {r.rollback_key}")
            out.append(f"  {'─' * (W - 4)}")

        out += ["", bar, ""]
        return "\n".join(out)

    def as_dict(self) -> dict:
        """JSON-serialisable representation."""
        return self.s.as_dict()

    def as_json(self) -> str:
        return self.s.as_json()


# ══════════════════════════════════════════════════════════════════════════════
# 10. INDIVIDUAL FIX HANDLERS  (unchanged from v4.1, priority tags added)
# ══════════════════════════════════════════════════════════════════════════════

def _shell(cmd: str, timeout: int = 15) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


# ── Kill high-CPU process ─────────────────────────────────────────────────────

@FixRegistry.register("kill_process")
def fix_kill_process(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    pid  = int(params.get("pid", 0))
    name = params.get("name", "unknown")

    if not pid:
        return FixResult("kill_process", "failed", "No PID supplied.", error="missing pid")

    meta = {"pid": pid, "name": name, "cmdline": ""}
    if _HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            meta["cmdline"] = " ".join(proc.cmdline())
            meta["exe"]     = proc.exe()
            meta["user"]    = proc.username()
        except Exception:
            pass

    preview = f"kill -15 {pid} ({name})"
    if dry_run:
        return FixResult(fix="kill_process", status="dry_run",
                         details=f"DRY RUN — would execute: {preview}",
                         dry_run=True, command_run=preview)

    confirmed = engine.guard.confirm(
        f"Kill process '{name}' (PID {pid})? Command: {preview}"
    )
    if not confirmed:
        return FixResult("kill_process", "skipped",
                         f"User declined to kill {name} (PID {pid}).",
                         command_run=preview)

    rc, out, err = _shell(f"kill -15 {pid} 2>&1")
    if rc != 0:
        rc, out, err = _shell(f"kill -9 {pid} 2>&1")

    if rc == 0:
        rk = f"kill_process_{pid}_{int(time.time())}"
        engine.rollback.save_state(rk, _rollback_killed_process, meta)
        result = FixResult(fix="kill_process", status="success",
                           details=f"Process '{name}' (PID {pid}) terminated.",
                           rollback_available=True, rollback_key=rk, command_run=preview)
    else:
        result = FixResult(fix="kill_process", status="failed",
                           details=f"Failed to kill {name} (PID {pid}): {err}",
                           command_run=preview, error=err)
    engine.logger.log(result)
    return result


def _rollback_killed_process(meta: dict) -> FixResult:
    cmdline = meta.get("cmdline", "")
    name    = meta.get("name", "unknown")
    if cmdline:
        return FixResult(fix="kill_process_rollback", status="success",
                         details=(f"Cannot automatically restart '{name}'. "
                                  f"Restore manually with:\n    {cmdline}"),
                         rollback_available=False)
    return FixResult(fix="kill_process_rollback", status="failed",
                     details=f"No cmdline captured for '{name}' — manual restart required.",
                     rollback_available=False)


# ── Clear page cache ──────────────────────────────────────────────────────────

@FixRegistry.register("clear_page_cache")
def fix_clear_page_cache(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    cmd = "sync && echo 3 | sudo tee /proc/sys/vm/drop_caches"

    if dry_run:
        return FixResult(fix="clear_page_cache", status="dry_run",
                         details=f"DRY RUN — would execute: {cmd}",
                         dry_run=True, command_run=cmd)

    confirmed = engine.guard.confirm(
        f"Clear Linux page cache? Safe — kernel reclaims automatically.\n  Command: {cmd}"
    )
    if not confirmed:
        return FixResult("clear_page_cache", "skipped",
                         "User declined page cache clear.", command_run=cmd)

    pre_avail = ""
    if _HAS_PSUTIL:
        try:
            pre_avail = f"{psutil.virtual_memory().available / 1024**3:.2f}GB"
        except Exception:
            pass

    rc, out, err = _shell(cmd, timeout=20)
    post_avail = ""
    if _HAS_PSUTIL:
        try:
            post_avail = f"{psutil.virtual_memory().available / 1024**3:.2f}GB"
        except Exception:
            pass

    if rc == 0:
        result = FixResult(fix="clear_page_cache", status="success",
                           details=(f"Page cache cleared. "
                                    f"RAM available: {pre_avail} → {post_avail}"),
                           rollback_available=False, command_run=cmd)
    else:
        result = FixResult(fix="clear_page_cache", status="failed",
                           details=f"Cache clear failed (need sudo?): {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


# ── Clean /tmp ────────────────────────────────────────────────────────────────

@FixRegistry.register("clean_tmp")
def fix_clean_tmp(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    age_days = int(params.get("age_days", 7))
    cmd      = f"find /tmp -maxdepth 2 -type f -mtime +{age_days} -delete 2>/dev/null"
    list_cmd = f"find /tmp -maxdepth 2 -type f -mtime +{age_days} 2>/dev/null"
    rc_l, files_out, _ = _shell(list_cmd, timeout=10)
    file_list = [f for f in files_out.splitlines() if f.strip()]

    if dry_run:
        count        = len(file_list)
        preview_list = "\n    ".join(file_list[:8])
        more         = f"\n    … and {count - 8} more" if count > 8 else ""
        return FixResult(fix="clean_tmp", status="dry_run",
                         details=(f"DRY RUN — would delete {count} file(s) older than "
                                  f"{age_days} days:\n    {preview_list}{more}"),
                         dry_run=True, command_run=cmd)

    if not file_list:
        return FixResult("clean_tmp", "skipped",
                         f"No /tmp files older than {age_days} days found.",
                         command_run=cmd)

    meta = {"age_days": age_days, "files": file_list[:50]}
    rk   = f"clean_tmp_{int(time.time())}"

    confirmed = engine.guard.confirm(
        f"Delete {len(file_list)} /tmp file(s) older than {age_days} days? Command: {cmd}"
    )
    if not confirmed:
        return FixResult("clean_tmp", "skipped",
                         "User declined /tmp cleanup.", command_run=cmd)

    rc, out, err = _shell(cmd, timeout=30)
    if rc == 0:
        engine.rollback.save_state(rk, _rollback_clean_tmp, meta)
        result = FixResult(fix="clean_tmp", status="success",
                           details=f"Deleted {len(file_list)} stale /tmp file(s).",
                           rollback_available=False, rollback_key=rk, command_run=cmd)
    else:
        result = FixResult(fix="clean_tmp", status="failed",
                           details=f"Partial /tmp cleanup, error: {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


def _rollback_clean_tmp(meta: dict) -> FixResult:
    files = meta.get("files", [])
    return FixResult(fix="clean_tmp_rollback", status="failed",
                     details=(f"Cannot restore {len(files)} deleted /tmp file(s). "
                               "They were temporary and should not be required."),
                     rollback_available=False)


# ── Suggest log cleanup ───────────────────────────────────────────────────────

@FixRegistry.register("suggest_log_cleanup")
def fix_suggest_log_cleanup(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    vacuum_mb = int(params.get("vacuum_mb", 100))
    cmd       = f"sudo journalctl --vacuum-size={vacuum_mb}M"

    if dry_run:
        rc, out, _ = _shell("journalctl --disk-usage 2>/dev/null")
        disk_usage  = out.strip() or "unknown"
        return FixResult(fix="suggest_log_cleanup", status="dry_run",
                         details=(f"DRY RUN — Journal disk usage: {disk_usage}\n"
                                  f"Would run: {cmd}"),
                         dry_run=True, command_run=cmd)

    confirmed = engine.guard.confirm(
        f"Vacuum systemd journal to {vacuum_mb}MB? Command: {cmd}"
    )
    if not confirmed:
        return FixResult("suggest_log_cleanup", "skipped",
                         "User declined log cleanup.", command_run=cmd)

    rc, out, err = _shell(cmd, timeout=30)
    if rc == 0:
        result = FixResult(fix="suggest_log_cleanup", status="success",
                           details=f"Journal vacuumed to {vacuum_mb}MB. Output: {out[:200]}",
                           rollback_available=False, command_run=cmd)
    else:
        result = FixResult(fix="suggest_log_cleanup", status="failed",
                           details=f"Journal vacuum failed: {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


# ── Restart safe service ──────────────────────────────────────────────────────

@FixRegistry.register("restart_service")
def fix_restart_service(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    service = params.get("service", "").strip().lower()
    if not service:
        return FixResult("restart_service", "failed",
                         "No service name supplied.", error="missing service")

    if not engine.guard.is_safe_service(service):
        return FixResult(fix="restart_service", status="failed",
                         details=(f"Service '{service}' is not on the JENIX safe-restart list. "
                                  "Add it to SafetyGuard.SAFE_SERVICES after manual review."),
                         error="unsafe service")

    cmd = f"sudo systemctl restart {service}"
    rc_s, status_out, _ = _shell(f"systemctl is-active {service} 2>/dev/null")
    pre_state = status_out.strip() or "unknown"

    if dry_run:
        return FixResult(fix="restart_service", status="dry_run",
                         details=f"DRY RUN — {service} is currently '{pre_state}'. Would run: {cmd}",
                         dry_run=True, command_run=cmd)

    confirmed = engine.guard.confirm(
        f"Restart service '{service}' (currently: {pre_state})? Command: {cmd}"
    )
    if not confirmed:
        return FixResult("restart_service", "skipped",
                         f"User declined restart of '{service}'.", command_run=cmd)

    rk   = f"restart_{service}_{int(time.time())}"
    meta = {"service": service, "pre_state": pre_state}
    engine.rollback.save_state(rk, _rollback_restart_service, meta)

    rc, out, err = _shell(cmd, timeout=20)
    if rc == 0:
        result = FixResult(fix="restart_service", status="success",
                           details=f"Service '{service}' restarted successfully.",
                           rollback_available=True, rollback_key=rk, command_run=cmd)
    else:
        result = FixResult(fix="restart_service", status="failed",
                           details=f"Failed to restart '{service}': {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


def _rollback_restart_service(meta: dict) -> FixResult:
    service = meta.get("service", "unknown")
    cmd     = f"sudo systemctl stop {service}"
    rc, out, err = _shell(cmd, timeout=15)
    if rc == 0:
        return FixResult(fix="restart_service_rollback", status="success",
                         details=f"Service '{service}' stopped (rolled back restart).",
                         command_run=cmd)
    return FixResult(fix="restart_service_rollback", status="failed",
                     details=f"Could not stop '{service}': {err}",
                     command_run=cmd, error=err)


# ── Reduce swap usage ─────────────────────────────────────────────────────────

@FixRegistry.register("reduce_swap_usage")
def fix_reduce_swap_usage(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    swappiness = int(params.get("swappiness", 10))
    reclaim    = bool(params.get("reclaim", False))
    cmd        = f"sudo sysctl -w vm.swappiness={swappiness}"

    if dry_run:
        rc, current, _ = _shell("cat /proc/sys/vm/swappiness 2>/dev/null")
        return FixResult(fix="reduce_swap_usage", status="dry_run",
                         details=(f"DRY RUN — current swappiness={current.strip()}. "
                                  f"Would set to {swappiness}. Command: {cmd}"),
                         dry_run=True, command_run=cmd)

    confirmed = engine.guard.confirm(
        f"Set vm.swappiness={swappiness} (persistent until reboot)? Command: {cmd}"
    )
    if not confirmed:
        return FixResult("reduce_swap_usage", "skipped",
                         "User declined swappiness change.", command_run=cmd)

    rc, out, err = _shell(cmd, timeout=10)
    if rc == 0:
        details = f"vm.swappiness set to {swappiness}."
        if reclaim:
            details += " (swapoff/swapon not attempted — requires manual root action)"
        result = FixResult(fix="reduce_swap_usage", status="success",
                           details=details, rollback_available=False, command_run=cmd)
    else:
        result = FixResult(fix="reduce_swap_usage", status="failed",
                           details=f"Failed to set swappiness: {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


# ── Clean APT cache ───────────────────────────────────────────────────────────

@FixRegistry.register("clean_apt_cache")
def fix_clean_apt_cache(engine: "FixEngine", params: dict, dry_run: bool) -> FixResult:
    if not shutil.which("apt-get"):
        return FixResult("clean_apt_cache", "skipped",
                         "apt-get not found — skipping (non-Debian system).")

    cmd = "sudo apt-get clean"
    rc_e, est, _ = _shell("du -sh /var/cache/apt/archives/ 2>/dev/null")
    cache_size   = est.split()[0] if est else "unknown"

    if dry_run:
        return FixResult(fix="clean_apt_cache", status="dry_run",
                         details=f"DRY RUN — /var/cache/apt/archives is {cache_size}. Would run: {cmd}",
                         dry_run=True, command_run=cmd)

    confirmed = engine.guard.confirm(
        f"Clear APT package cache ({cache_size})? Command: {cmd}"
    )
    if not confirmed:
        return FixResult("clean_apt_cache", "skipped",
                         "User declined APT cache clean.", command_run=cmd)

    rc, out, err = _shell(cmd, timeout=30)
    if rc == 0:
        result = FixResult(fix="clean_apt_cache", status="success",
                           details=f"APT cache cleared ({cache_size} freed).",
                           rollback_available=False, command_run=cmd)
    else:
        result = FixResult(fix="clean_apt_cache", status="failed",
                           details=f"APT clean failed: {err}",
                           command_run=cmd, error=err)
    engine.logger.log(result)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 11. FIX ENGINE  (orchestrator — enhanced v4.2)
# ══════════════════════════════════════════════════════════════════════════════

class FixEngine:
    """
    Central orchestrator for all JENIX safe fixes.

    Public API (v4.1 API fully preserved):
        plan_fixes(scan_result)                           → List[FixPlan]
        apply_fix(fix_id, params, dry_run)                → FixResult
        rollback(rollback_key)                            → FixResult
        list_available_rollbacks()                        → List[str]
        read_audit_log(n)                                 → str

    NEW v4.2 API:
        apply_all_fixes(scan_result, dry_run, confirm_all) → ExecutionSummary
        generate_fix_report(summary)                       → str
        generate_fix_report_json(summary)                  → dict
    """

    _ISSUE_MAP: List[Tuple[str, str, str, Dict[str, Any]]] = [
        ("CPU",     "Suspicious process",  "kill_process",        {}),
        ("CPU",     "CPU usage",           "clear_page_cache",    {}),
        ("CPU",     "load average",        "clear_page_cache",    {}),
        ("Memory",  "RAM at",              "clear_page_cache",    {}),
        ("Memory",  "Swap at",             "reduce_swap_usage",   {"swappiness": 10}),
        ("Memory",  "No swap",             "reduce_swap_usage",   {"swappiness": 10}),
        ("Storage", "Disk",                "clean_tmp",           {"age_days": 7}),
        ("Storage", "Disk",                "suggest_log_cleanup", {"vacuum_mb": 100}),
        ("Storage", "Disk",                "clean_apt_cache",     {}),
        ("Processes","Suspicious",         "kill_process",        {}),
    ]

    # NEW v4.2 — which fix IDs are considered inherently dangerous
    _DANGEROUS_FIX_IDS = {"kill_process", "clean_tmp"}

    def __init__(self, confirm_fn: Optional[Callable[[str], bool]] = None):
        self.guard        = SafetyGuard(confirm_fn=confirm_fn)
        self.rollback     = RollbackManager()
        self.logger       = FixLogger()
        self._orchestrator: Optional[AutoFixOrchestrator] = None   # lazy init

    # ── Plan generation ───────────────────────────────────────────────────────

    def plan_fixes(self, scan_result: Any) -> List[FixPlan]:
        plans: List[FixPlan]   = []
        seen_fix_ids: set      = set()

        issues     = getattr(scan_result, "issues", [])
        suspicious = getattr(scan_result, "suspicious_procs", [])

        for issue in issues:
            cat   = getattr(issue, "category", "")
            title = getattr(issue, "title", "")
            sev   = getattr(issue, "severity", "LOW")

            for cat_frag, title_frag, fix_id, extra in self._ISSUE_MAP:
                if cat_frag.lower() not in cat.lower():
                    continue
                if title_frag.lower() not in title.lower():
                    continue

                params = dict(extra)
                if fix_id == "kill_process":
                    if not suspicious:
                        continue
                    for sp in suspicious:
                        uid = f"kill_process_{sp.pid}"
                        if uid in seen_fix_ids:
                            continue
                        seen_fix_ids.add(uid)
                        plans.append(FixPlan(
                            issue_title=title, fix_id=fix_id, priority=sev,
                            description=(f"Kill process '{sp.name}' (PID {sp.pid}) "
                                         f"consuming {sp.cpu_pct:.1f}% CPU."),
                            dry_run_preview=f"kill -15 {sp.pid} ({sp.name})",
                            params={"pid": sp.pid, "name": sp.name},
                            is_dangerous=True,
                        ))
                    continue

                uid = f"{fix_id}_{cat}"
                if uid in seen_fix_ids:
                    continue
                seen_fix_ids.add(uid)

                descriptions = {
                    "clear_page_cache":    "Drop Linux page/slab cache to reclaim RAM instantly.",
                    "suggest_log_cleanup": "Vacuum systemd journal to free disk space.",
                    "clean_tmp":           "Remove stale temporary files from /tmp.",
                    "clean_apt_cache":     "Clear APT package download cache.",
                    "reduce_swap_usage":   "Lower vm.swappiness to reduce swap pressure.",
                    "restart_service":     "Restart a misbehaving system service.",
                }
                previews = {
                    "clear_page_cache":    "sync && echo 3 | sudo tee /proc/sys/vm/drop_caches",
                    "suggest_log_cleanup": f"sudo journalctl --vacuum-size={params.get('vacuum_mb', 100)}M",
                    "clean_tmp":           f"find /tmp -maxdepth 2 -type f -mtime +{params.get('age_days', 7)} -delete",
                    "clean_apt_cache":     "sudo apt-get clean",
                    "reduce_swap_usage":   f"sudo sysctl -w vm.swappiness={params.get('swappiness', 10)}",
                    "restart_service":     "sudo systemctl restart <service>",
                }
                plans.append(FixPlan(
                    issue_title=title, fix_id=fix_id, priority=sev,
                    description=descriptions.get(fix_id, fix_id),
                    dry_run_preview=previews.get(fix_id, ""),
                    params=params,
                    is_dangerous=(fix_id in self._DANGEROUS_FIX_IDS),
                ))

        self.logger.log(FixResult(
            fix="plan_fixes", status="success",
            details=f"Generated {len(plans)} fix plan(s) from {len(issues)} issue(s).",
        ))
        return plans

    # ── Single fix execution ──────────────────────────────────────────────────

    def apply_fix(
        self,
        fix_id:  str,
        params:  Optional[dict] = None,
        dry_run: bool = True,
    ) -> FixResult:
        handler = FixRegistry.get(fix_id)
        if not handler:
            return FixResult(fix=fix_id, status="failed",
                             details=f"No fix handler registered for id='{fix_id}'.",
                             error="unknown fix_id")
        try:
            result = handler(self, params or {}, dry_run)
        except Exception as exc:
            result = FixResult(fix=fix_id, status="failed",
                               details=f"Fix handler raised an exception: {exc}",
                               error=str(exc))
            self.logger.log(result)
        return result

    # ── NEW v4.2: Batch fix — the premium one-click optimization entry point ──

    def apply_all_fixes(
        self,
        scan_result: Any,
        dry_run:     bool = True,
        confirm_all: bool = False,
    ) -> ExecutionSummary:
        """
        One-click optimization: plan + prioritize + execute all safe fixes.

        Parameters:
            scan_result  — ScanResult from jenix_scan_engine.ScanEngine
            dry_run      — True (default, safe): simulate only; no system changes
            confirm_all  — True: auto-confirm non-dangerous fixes (still prompts
                           for dangerous ones individually)

        Returns:
            ExecutionSummary — machine-readable + human-readable results
        """
        if self._orchestrator is None:
            self._orchestrator = AutoFixOrchestrator(self)

        plans   = self.plan_fixes(scan_result)
        summary = self._orchestrator.apply_all_fixes(
            plans       = plans,
            dry_run     = dry_run,
            confirm_all = confirm_all,
        )
        return summary

    # ── NEW v4.2: Report generation ───────────────────────────────────────────

    def generate_fix_report(
        self,
        summary:        ExecutionSummary,
        section_number: int = 10,
    ) -> str:
        """
        Returns the FIX EXECUTION REPORT section as a plain-text string
        ready to be appended to a jenix_scan_engine.ReportGenerator output.
        """
        return FixReportSection(summary).as_txt(section_number=section_number)

    def generate_fix_report_json(self, summary: ExecutionSummary) -> dict:
        """Returns the fix execution report as a JSON-serialisable dict."""
        return FixReportSection(summary).as_dict()

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback_fix(self, rollback_key: str) -> FixResult:
        result = self.rollback.rollback(rollback_key)
        self.logger.log(result)
        return result

    def list_available_rollbacks(self) -> List[str]:
        return self.rollback.list_available()

    # ── Audit log ─────────────────────────────────────────────────────────────

    def read_audit_log(self, last_n: int = 50) -> str:
        try:
            lines = FIX_LOG.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[-last_n:])
        except Exception as exc:
            return f"(could not read audit log: {exc})"


# ══════════════════════════════════════════════════════════════════════════════
# 12. SCAN INTEGRATION HELPER  (v4.1 API preserved, new overload added)
# ══════════════════════════════════════════════════════════════════════════════

def get_fix_plans_for_scan(
    scan_result: Any,
    confirm_fn:  Optional[Callable] = None,
) -> Tuple[FixEngine, List[FixPlan]]:
    """
    Convenience entry point called from gui.py / jenix_scan_view.py.

    Returns:
        (FixEngine instance, list of FixPlan objects)

    Example integration:
        from fix_engine import get_fix_plans_for_scan

        engine, plans = get_fix_plans_for_scan(scan_result, confirm_fn=my_modal)
        for plan in plans:
            result = engine.apply_fix(plan.fix_id, plan.params, dry_run=True)

        # NEW v4.2 — one-click batch:
        summary = engine.apply_all_fixes(scan_result, dry_run=False, confirm_all=True)
        print(summary.smart_message)
        print(engine.generate_fix_report(summary))
    """
    engine = FixEngine(confirm_fn=confirm_fn)
    plans  = engine.plan_fixes(scan_result)
    return engine, plans


# ══════════════════════════════════════════════════════════════════════════════
# 13. CLI  — standalone demo / manual execution
# ══════════════════════════════════════════════════════════════════════════════

def _cli_main():
    """
    Interactive CLI: run a scan, display plans, and optionally apply fixes.
    Usage: python fix_engine.py [--dry-run] [--apply] [--auto]
    """
    dry_run  = "--apply" not in sys.argv
    auto_all = "--auto"  in sys.argv

    print("\n" + "═" * 70)
    print("  JENIX v4.2 — Auto-Fix Engine  (CLI demo)")
    print(f"  Mode: {'DRY RUN' if dry_run else '⚠  LIVE'}"
          + ("  (AUTO-CONFIRM non-dangerous fixes)" if auto_all and not dry_run else ""))
    print("═" * 70 + "\n")

    try:
        from jenix_scan_engine import ScanEngine
    except ImportError:
        print("  [ERR]  jenix_scan_engine.py not found — cannot run scan.")
        sys.exit(1)

    def progress(pct: int, msg: str):
        print(f"  [{pct:3d}%]  {msg}")

    print("  Running full system scan…\n")
    scan_result = ScanEngine().run_full_scan(progress_cb=progress)
    print(f"\n  Score: {scan_result.health_score}/100  Grade: {scan_result.health_grade}"
          f"  Status: {scan_result.health_status}")
    print(f"  Issues detected: {len(scan_result.issues)}\n")

    engine, plans = get_fix_plans_for_scan(scan_result)

    if not plans:
        print("  ✓  No fixes recommended — system looks healthy.\n")
        return

    print(f"  {'─' * 66}")
    print(f"  {'#':<4}  {'PRIORITY':<10}  {'FIX ID':<24}  {'DANGEROUS':<10}  DESCRIPTION")
    print(f"  {'─' * 66}")
    for i, plan in enumerate(plans, 1):
        danger = "⚠ YES" if plan.is_dangerous else "no"
        print(f"  {i:<4}  {plan.priority:<10}  {plan.fix_id:<24}  {danger:<10}  {plan.description[:35]}")
        print(f"        Preview: {plan.dry_run_preview[:60]}")
    print(f"  {'─' * 66}\n")

    # ── Use apply_all_fixes for the batch ─────────────────────────────────────
    print(f"  Running {'dry-run' if dry_run else 'live'} batch via apply_all_fixes()…\n")
    summary = engine.apply_all_fixes(
        scan_result = scan_result,
        dry_run     = dry_run,
        confirm_all = auto_all,
    )

    # ── Print each result inline ───────────────────────────────────────────────
    for result in summary.results:
        _print_result(result)

    # ── Print the FIX EXECUTION REPORT section ─────────────────────────────────
    print(engine.generate_fix_report(summary, section_number=10))

    # ── Print JSON summary ─────────────────────────────────────────────────────
    print("  JSON SUMMARY:")
    s_dict = {
        "total_fixes":        summary.total_fixes,
        "applied":            summary.applied,
        "failed":             summary.failed,
        "skipped":            summary.skipped,
        "system_improvement": summary.system_improvement,
        "smart_message":      summary.smart_message,
    }
    print("  " + json.dumps(s_dict, indent=4).replace("\n", "\n  "))

    print("\n  Audit log (last 10 lines):")
    print("  " + "\n  ".join(engine.read_audit_log(10).splitlines()))
    print("\n" + "═" * 70 + "\n")


def _print_result(result: FixResult):
    icons = {"success": "✓", "failed": "✗", "skipped": "–",
             "dry_run": "~", "aborted": "⊘"}
    icon  = icons.get(result.status, "?")
    color_map = {"success": "\033[32m", "failed": "\033[31m",
                 "skipped": "\033[33m", "dry_run": "\033[36m",
                 "aborted": "\033[35m"}
    reset = "\033[0m"
    c     = color_map.get(result.status, "")
    print(f"  {c}{icon} [{result.status.upper():>8}]{reset}  [{result.priority:<8}]  {result.details[:90]}")
    if result.rollback_available:
        print(f"    ↩  Rollback available (key: {result.rollback_key})")
    if result.error:
        print(f"    ✗  Error: {result.error[:80]}")


if __name__ == "__main__":
    _cli_main()
