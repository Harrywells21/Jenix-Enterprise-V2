"""
auto_responder.py
═════════════════
JENIX v4.4 — Safe Auto-Response System + Forensic Capture

Stable version: all optional dependencies degrade gracefully.
No crashes if psutil, threat_intelligence, jenix_suspicious_process_detector,
or fix_engine are missing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ── Centralised logger (from utils/logger.py if available, else stdlib) ───────
try:
    from utils.logger import log as _root_log
    _logger = _root_log.getChild("auto_responder")
except Exception:
    _logger = logging.getLogger("jenix.auto_responder")

# ── Optional psutil ───────────────────────────────────────────────────────────
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil       = None          # type: ignore
    _HAS_PSUTIL = False

# ── Optional ForensicCapture (graceful degradation) ───────────────────────────
_ForensicCapture = None
_HAS_FORENSICS   = False
try:
    from threat_intelligence import ForensicCapture as _ForensicCapture
    _HAS_FORENSICS = True
except ImportError:
    pass

# ── Lazy imports from the JENIX suite ─────────────────────────────────────────
_SuspiciousProcessIssue: Any = None
_FixEngine:              Any = None
_FixResult:              Any = None


def _lazy_import() -> None:
    global _SuspiciousProcessIssue, _FixEngine, _FixResult
    if _SuspiciousProcessIssue is None:
        try:
            from jenix_suspicious_process_detector import SuspiciousProcessIssue
            _SuspiciousProcessIssue = SuspiciousProcessIssue
        except ImportError:
            _SuspiciousProcessIssue = object

    if _FixEngine is None:
        try:
            from fix_engine import FixEngine, FixResult
            _FixEngine = FixEngine
            _FixResult = FixResult
        except ImportError:
            _FixEngine = object
            _FixResult = object


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & DEFAULTS
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_SAFE_NAMES: Set[str] = {
    "systemd", "init", "upstart", "openrc", "runit", "s6-svscan",
    "login", "sddm", "gdm", "lightdm", "xdm",
    "sshd", "dbus-daemon", "dbus", "udevd", "systemd-udevd",
    "networkmanager", "networkd", "systemd-networkd",
    "systemd-resolved", "avahi-daemon", "wpa_supplicant",
    "auditd", "fail2ban-server", "apparmord", "selinuxd",
    "rsyslogd", "syslogd", "journald", "systemd-journald",
    "chronyd", "ntpd", "timesyncd", "systemd-timesyncd",
    "kthreadd", "ksoftirqd", "kworker", "migration",
    "rcu_sched", "rcu_bh", "watchdog",
}

_SAFE_PATH_PREFIXES: Tuple[str, ...] = (
    "/usr/lib/systemd/",
    "/lib/systemd/",
    "/usr/bin/dbus",
    "/usr/sbin/sshd",
    "/sbin/init",
)

_MAX_KERNEL_THREAD_HEURISTIC_PID = 1000
_DEFAULT_SIGTERM_GRACE           = 3.0

_JENIX_DIR    = Path.home() / ".jenix"
try:
    _JENIX_DIR.mkdir(exist_ok=True)
except OSError:
    pass
_AR_AUDIT_LOG = _JENIX_DIR / "auto_responder_audit.log"


# ══════════════════════════════════════════════════════════════════════════════
# 1. RESPONSE POLICY
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ResponsePolicy:
    level:            str
    auto_kill:        bool
    log_alert:        bool
    invoke_callback:  bool
    min_score:        int = 0

    def __str__(self) -> str:
        actions = []
        if self.auto_kill:       actions.append("auto-kill")
        if self.log_alert:       actions.append("log")
        if self.invoke_callback: actions.append("callback")
        return f"ResponsePolicy({self.level}: {', '.join(actions) or 'no-op'})"


_DEFAULT_POLICIES: Dict[str, ResponsePolicy] = {
    "CRITICAL": ResponsePolicy(
        level="CRITICAL", auto_kill=True,  log_alert=True,  invoke_callback=True,  min_score=100),
    "HIGH":     ResponsePolicy(
        level="HIGH",     auto_kill=False, log_alert=True,  invoke_callback=True,  min_score=70),
    "MEDIUM":   ResponsePolicy(
        level="MEDIUM",   auto_kill=False, log_alert=True,  invoke_callback=False, min_score=40),
    "LOW":      ResponsePolicy(
        level="LOW",      auto_kill=False, log_alert=False, invoke_callback=False, min_score=0),
}


# ══════════════════════════════════════════════════════════════════════════════
# 2. ACTION RECORD
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ActionRecord:
    action_id:      str
    pid:            int
    name:           str
    threat_level:   str
    threat_score:   int
    exe_path:       str
    cmdline:        str
    user:           str
    timestamp:      str
    kill_signal:    int
    outcome:        str
    veto_reason:    str = ""
    fix_result:     Any = None
    forensic_path:  str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "fix_result"}


# ══════════════════════════════════════════════════════════════════════════════
# 3. ROLLBACK STORE
# ══════════════════════════════════════════════════════════════════════════════

class RollbackStore:
    def __init__(self, max_size: int = 200) -> None:
        self._lock:     threading.Lock     = threading.Lock()
        self._records:  List[ActionRecord] = []
        self._max_size: int                = max_size

    def push(self, record: ActionRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_size:
                self._records.pop(0)

    def pop_last_killed(self) -> Optional[ActionRecord]:
        with self._lock:
            for i in range(len(self._records) - 1, -1, -1):
                if self._records[i].outcome == "killed":
                    return self._records.pop(i)
        return None

    def all_records(self) -> List[ActionRecord]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


# ══════════════════════════════════════════════════════════════════════════════
# 4. RESPONSE LOGGER  (delegates to utils.logger)
# ══════════════════════════════════════════════════════════════════════════════

class ResponseLogger:
    _PREFIX_MAP = {
        "response": "[AUTO-RESPONSE]",
        "rollback": "[ROLLBACK]",
        "veto":     "[VETO]",
        "high":     "[HIGH-ALERT]",
        "info":     "[INFO]",
        "error":    "[ERROR]",
        "forensic": "[FORENSICS]",
    }

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or _logger
        self._setup_audit_handler()

    def _setup_audit_handler(self) -> None:
        try:
            fh = logging.FileHandler(str(_AR_AUDIT_LOG), encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            # Avoid duplicate handlers
            existing_files = {
                getattr(h, "baseFilename", None)
                for h in self._log.handlers
            }
            if str(_AR_AUDIT_LOG) not in existing_files:
                self._log.addHandler(fh)
            self._log.setLevel(logging.DEBUG)
        except Exception:
            pass

    def _emit(self, kind: str, message: str, level: int = logging.INFO) -> None:
        prefix = self._PREFIX_MAP.get(kind, "[JENIX]")
        self._log.log(level, "%s  %s", prefix, message)

    def log_threat_received(self, issue: Any) -> None:
        self._emit("info", f"Threat received — PID {getattr(issue,'pid','?')} ({getattr(issue,'name','?')})"
                           f"  level={getattr(issue,'threat_level','?')}  score={getattr(issue,'threat_score',0)}")

    def log_veto(self, pid: int, name: str, reason: str) -> None:
        self._emit("veto", f"Kill vetoed — PID {pid} ({name})  reason: {reason}", level=logging.WARNING)

    def log_kill_attempt(self, pid: int, name: str, signal: int) -> None:
        self._emit("response", f"Sending SIG{'TERM' if signal == 15 else 'KILL'} to PID {pid} ({name})")

    def log_killed(self, pid: int, name: str, score: int) -> None:
        self._emit("response", f"Killed PID {pid} ({name})  [CRITICAL, score={score}]", level=logging.WARNING)

    def log_kill_failed(self, pid: int, name: str, error: str) -> None:
        self._emit("error", f"Kill FAILED — PID {pid} ({name})  error: {error}", level=logging.ERROR)

    def log_high_threat(self, issue: Any) -> None:
        self._emit("high", f"HIGH threat — PID {getattr(issue,'pid','?')} ({getattr(issue,'name','?')})"
                           f"  score={getattr(issue,'threat_score',0)}  (human review)", level=logging.WARNING)

    def log_rollback_start(self, record: ActionRecord) -> None:
        self._emit("rollback", f"Attempting rollback for PID {record.pid} ({record.name})")

    def log_rollback_result(self, pid: int, name: str, success: bool, detail: str) -> None:
        status = "success" if success else "best-effort"
        self._emit("rollback", f"PID {pid} ({name}) — rollback {status}: {detail}",
                   level=logging.INFO if success else logging.WARNING)

    def log_paused(self, paused: bool) -> None:
        state = "PAUSED (log-only)" if paused else "RESUMED"
        self._emit("info", f"AutoResponder {state}")

    def log_forensic_capture(self, pid: int, name: str, path: Optional[Path]) -> None:
        if path:
            self._emit("forensic", f"Snapshot saved for PID {pid} ({name}) → {path}")
        else:
            self._emit("forensic", f"Snapshot FAILED for PID {pid} ({name})", level=logging.WARNING)

    def log_info(self, message: str) -> None:
        self._emit("info", message)

    def log_error(self, message: str) -> None:
        self._emit("error", message, level=logging.ERROR)


# ══════════════════════════════════════════════════════════════════════════════
# 5. SAFETY GATE
# ══════════════════════════════════════════════════════════════════════════════

class SafetyGate:
    def __init__(
        self,
        safe_names:         Set[str]        = _DEFAULT_SAFE_NAMES,
        safe_path_prefixes: Tuple[str, ...] = _SAFE_PATH_PREFIXES,
        min_score:          int             = 0,
    ) -> None:
        self._safe_names         = {n.lower() for n in safe_names}
        self._safe_path_prefixes = safe_path_prefixes
        self._min_score          = min_score

    def add_safe_name(self, name: str) -> None:
        self._safe_names.add(name.lower())

    def add_safe_path_prefix(self, prefix: str) -> None:
        self._safe_path_prefixes = self._safe_path_prefixes + (prefix,)

    def check(self, issue: Any, policy: ResponsePolicy) -> Tuple[bool, str]:
        pid   = getattr(issue, "pid",          0)
        name  = getattr(issue, "name",         "").lower()
        exe   = getattr(issue, "exe_path",     "") or ""
        score = getattr(issue, "threat_score", 0)

        if pid <= 1:
            return False, "PID ≤ 1 — init/idle process is never touched"

        if not exe and pid < _MAX_KERNEL_THREAD_HEURISTIC_PID:
            return False, f"Likely kernel thread (no exe_path, PID {pid} < {_MAX_KERNEL_THREAD_HEURISTIC_PID})"

        for token in {name, name.split(":")[0].strip(), name.split(" ")[0].strip()}:
            if token in self._safe_names:
                return False, f"Process name '{token}' is on the safe allowlist"

        for prefix in self._safe_path_prefixes:
            if exe.startswith(prefix):
                return False, f"Executable '{exe}' is under trusted path prefix '{prefix}'"

        effective_min = max(self._min_score, policy.min_score)
        if score < effective_min:
            return False, f"Threat score {score} below minimum {effective_min}"

        if _HAS_PSUTIL and psutil is not None:
            try:
                live      = psutil.Process(pid)
                live_name = (live.name() or "").lower()
                live_exe  = ""
                try:
                    live_exe = live.exe() or ""
                except (psutil.AccessDenied, OSError):
                    pass
                if live_name != name:
                    return False, f"PID {pid} identity mismatch: stored='{name}' live='{live_name}'"
                if exe and live_exe and live_exe != exe:
                    return False, f"PID {pid} exe mismatch: stored='{exe}' live='{live_exe}'"
            except psutil.NoSuchProcess:
                return False, f"PID {pid} no longer exists"
            except psutil.AccessDenied:
                pass

        return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# 6. RESPONSE STATS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResponseStats:
    threats_received:    int = 0
    critical_received:   int = 0
    high_received:       int = 0
    medium_received:     int = 0
    low_received:        int = 0
    kills_attempted:     int = 0
    kills_succeeded:     int = 0
    kills_failed:        int = 0
    kills_vetoed:        int = 0
    rollbacks_attempted: int = 0
    rollbacks_succeeded: int = 0
    forensic_captures:   int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ══════════════════════════════════════════════════════════════════════════════
# 7. AUTO RESPONDER
# ══════════════════════════════════════════════════════════════════════════════

class AutoResponder:
    """
    JENIX v4.4 — Safe Auto-Response System.
    All optional dependencies degrade gracefully.
    """

    def __init__(
        self,
        fix_engine:               Any                                = None,
        sigterm_grace:            float                              = _DEFAULT_SIGTERM_GRACE,
        extra_safe_names:         Optional[Set[str]]                = None,
        extra_safe_path_prefixes: Optional[Tuple[str, ...]]        = None,
        policies:                 Optional[Dict[str, ResponsePolicy]] = None,
        high_threat_callback:     Optional[Callable[[Any], None]]  = None,
        paused:                   bool                              = False,
        logger:                   Optional[logging.Logger]         = None,
        enable_forensics:         bool                              = True,
        forensic_sha256:          bool                              = True,
        forensic_capture_env:     bool                              = False,
    ) -> None:
        _lazy_import()

        self._fix_engine    = fix_engine
        self._sigterm_grace = max(0.0, float(sigterm_grace))
        self._policies      = dict(_DEFAULT_POLICIES)
        if policies:
            self._policies.update(policies)

        self._high_threat_callback = high_threat_callback

        safe_names = set(_DEFAULT_SAFE_NAMES)
        if extra_safe_names:
            safe_names.update(extra_safe_names)

        safe_prefixes = _SAFE_PATH_PREFIXES
        if extra_safe_path_prefixes:
            safe_prefixes = safe_prefixes + tuple(extra_safe_path_prefixes)

        self._gate = SafetyGate(safe_names=safe_names, safe_path_prefixes=safe_prefixes)

        # Forensic capture (optional)
        self._forensic: Optional[Any] = None
        if enable_forensics and _HAS_FORENSICS and _ForensicCapture is not None:
            try:
                self._forensic = _ForensicCapture(
                    capture_sha256=forensic_sha256,
                    capture_env=forensic_capture_env,
                )
            except Exception as exc:
                _logger.warning("ForensicCapture init failed: %s", exc)

        self._lock           = threading.RLock()
        self._paused         = paused
        self._rollback_store = RollbackStore()
        self._stats          = ResponseStats()
        self._rlog           = ResponseLogger(logger=logger)

        forensic_status = (
            "enabled" if self._forensic is not None
            else "disabled (threat_intelligence.py unavailable)"
        )
        self._rlog.log_info(
            f"AutoResponder v4.4 initialised  "
            f"(sigterm_grace={self._sigterm_grace}s, paused={paused}, "
            f"forensics={forensic_status})"
        )

    # ── Primary callback ──────────────────────────────────────────────────────

    def handle_threat(self, issue: Any) -> None:
        with self._lock:
            self._stats.threats_received += 1

        level = getattr(issue, "threat_level", "LOW").upper()

        with self._lock:
            counter_map = {
                "CRITICAL": "critical_received", "HIGH": "high_received",
                "MEDIUM":   "medium_received",   "LOW":  "low_received",
            }
            attr = counter_map.get(level, "low_received")
            setattr(self._stats, attr, getattr(self._stats, attr) + 1)

        self._rlog.log_threat_received(issue)

        policy = self._policies.get(level)
        if policy is None:
            self._rlog.log_info(f"Unknown threat level '{level}' — no action taken")
            return

        if level == "CRITICAL":
            self._handle_critical(issue, policy)
        elif level == "HIGH":
            self._handle_high(issue, policy)
        elif level == "MEDIUM" and policy.log_alert:
            self._rlog.log_info(
                f"MEDIUM threat — PID {getattr(issue,'pid','?')} "
                f"({getattr(issue,'name','?')})  score={getattr(issue,'threat_score',0)}"
            )

    # ── Critical handler ──────────────────────────────────────────────────────

    def _handle_critical(self, issue: Any, policy: ResponsePolicy) -> ActionRecord:
        pid   = getattr(issue, "pid",          0)
        name  = getattr(issue, "name",         "unknown")
        score = getattr(issue, "threat_score", 0)

        with self._lock:
            paused = self._paused

        if paused:
            self._rlog.log_info(
                f"[PAUSED] Critical threat PID {pid} ({name}) score={score} — no auto-kill"
            )
            forensic_path = self._do_forensic_capture(pid, name, issue)
            record = self._build_record(
                issue=issue, outcome="skipped",
                veto_reason="AutoResponder is paused",
                signal=0, forensic_path=forensic_path,
            )
            with self._lock:
                self._rollback_store.push(record)
            return record

        self._rlog.log_info(f"Critical threat PID {pid} ({name}) score={score}")

        allowed, veto_reason = self._gate.check(issue, policy)
        if not allowed:
            self._rlog.log_veto(pid, name, veto_reason)
            with self._lock:
                self._stats.kills_vetoed += 1
            forensic_path = self._do_forensic_capture(pid, name, issue)
            record = self._build_record(
                issue=issue, outcome="vetoed",
                veto_reason=veto_reason, signal=0,
                forensic_path=forensic_path,
            )
            with self._lock:
                self._rollback_store.push(record)
            return record

        forensic_path = self._do_forensic_capture(pid, name, issue)

        params     = {"pid": pid, "name": name}
        fix_result = None
        outcome    = "failed"
        signal_used = 15

        with self._lock:
            self._stats.kills_attempted += 1

        self._rlog.log_kill_attempt(pid, name, signal=15)

        try:
            if self._fix_engine is not None:
                fix_result = self._fix_engine.apply_fix(
                    "kill_process", params=params, dry_run=False,
                )
                fix_status = getattr(fix_result, "status", "failed")
            else:
                fix_status = "failed"

            if fix_status == "success":
                outcome = "killed"
                self._rlog.log_killed(pid, name, score)
                with self._lock:
                    self._stats.kills_succeeded += 1
            else:
                self._rlog.log_kill_attempt(pid, name, signal=9)
                if self._kill_direct(pid, name):
                    outcome     = "killed"
                    signal_used = 9
                    self._rlog.log_killed(pid, name, score)
                    with self._lock:
                        self._stats.kills_succeeded += 1
                else:
                    error_msg = getattr(fix_result, "error", "") or "unknown"
                    self._rlog.log_kill_failed(pid, name, error_msg)
                    with self._lock:
                        self._stats.kills_failed += 1

        except Exception as exc:
            self._rlog.log_error(f"Exception during kill of PID {pid} ({name}): {exc}")
            with self._lock:
                self._stats.kills_failed += 1

        record = self._build_record(
            issue=issue, outcome=outcome, veto_reason="",
            signal=signal_used, fix_result=fix_result,
            forensic_path=forensic_path,
        )
        with self._lock:
            self._rollback_store.push(record)

        if policy.invoke_callback and self._high_threat_callback is not None:
            try:
                self._high_threat_callback(issue)
            except Exception as exc:
                self._rlog.log_error(f"high_threat_callback raised: {exc}")

        return record

    def _handle_high(self, issue: Any, policy: ResponsePolicy) -> None:
        self._rlog.log_high_threat(issue)
        if policy.invoke_callback and self._high_threat_callback is not None:
            try:
                self._high_threat_callback(issue)
            except Exception as exc:
                self._rlog.log_error(f"high_threat_callback raised: {exc}")

    # ── Forensic capture helper ───────────────────────────────────────────────

    def _do_forensic_capture(self, pid: int, name: str, issue: Any) -> str:
        if self._forensic is None:
            return ""
        try:
            snap_path = self._forensic.capture_before_kill(issue)
            self._rlog.log_forensic_capture(pid, name, snap_path)
            if snap_path:
                with self._lock:
                    self._stats.forensic_captures += 1
                return str(snap_path)
        except Exception as exc:
            self._rlog.log_error(f"ForensicCapture raised for PID {pid}: {exc}")
        return ""

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback_last_action(self) -> Optional[ActionRecord]:
        with self._lock:
            self._stats.rollbacks_attempted += 1

        record = self._rollback_store.pop_last_killed()
        if record is None:
            self._rlog.log_info("rollback_last_action() — no killed process records found")
            return None

        self._rlog.log_rollback_start(record)

        if record.forensic_path:
            self._rlog.log_info(f"Forensic snapshot: {record.forensic_path}")

        cmdline = record.cmdline.strip()
        if not cmdline or cmdline in ("<unknown>", "(unknown)"):
            self._rlog.log_rollback_result(
                record.pid, record.name, success=False,
                detail="No cmdline captured — cannot restart automatically",
            )
            return record

        try:
            proc = subprocess.Popen(
                cmdline, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(0.5)
            if proc.poll() is None:
                self._rlog.log_rollback_result(
                    record.pid, record.name, success=True,
                    detail=f"Restarted as PID {proc.pid}. Command: {cmdline[:80]}",
                )
                with self._lock:
                    self._stats.rollbacks_succeeded += 1
            else:
                self._rlog.log_rollback_result(
                    record.pid, record.name, success=False,
                    detail=f"Process exited immediately (rc={proc.poll()})",
                )
        except Exception as exc:
            self._rlog.log_rollback_result(
                record.pid, record.name, success=False,
                detail=f"Restart exception: {exc}",
            )

        return record

    # ── Pause / Resume ────────────────────────────────────────────────────────

    def pause(self) -> None:
        with self._lock:
            self._paused = True
        self._rlog.log_paused(True)

    def resume(self) -> None:
        with self._lock:
            self._paused = False
        self._rlog.log_paused(False)

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    # ── Allowlist management ──────────────────────────────────────────────────

    def add_safe_name(self, name: str) -> None:
        self._gate.add_safe_name(name)
        self._rlog.log_info(f"Safe name added: '{name}'")

    def add_safe_path_prefix(self, prefix: str) -> None:
        self._gate.add_safe_path_prefix(prefix)
        self._rlog.log_info(f"Safe path prefix added: '{prefix}'")

    def set_high_threat_callback(self, fn: Optional[Callable[[Any], None]]) -> None:
        with self._lock:
            self._high_threat_callback = fn

    # ── Observability ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            d = self._stats.to_dict()
            d["paused"]            = self._paused
            d["rollback_queue"]    = len(self._rollback_store)
            d["forensics_enabled"] = self._forensic is not None
        return d

    def get_action_history(self) -> List[dict]:
        return [r.to_dict() for r in self._rollback_store.all_records()]

    def get_audit_log(self, last_n: int = 50) -> str:
        try:
            lines = _AR_AUDIT_LOG.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[-last_n:])
        except Exception as exc:
            return f"(could not read audit log: {exc})"

    def list_forensic_snapshots(self) -> List[Path]:
        forensics_dir = Path.home() / ".jenix" / "forensics"
        if not forensics_dir.exists():
            return []
        return sorted(forensics_dir.glob("*.json"), reverse=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _kill_direct(self, pid: int, name: str) -> bool:
        try:
            if _HAS_PSUTIL and psutil is not None:
                proc = psutil.Process(pid)
                proc.kill()
                proc.wait(timeout=5)
                return True
            else:
                rc = subprocess.call(
                    ["kill", "-9", str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return rc == 0
        except Exception:
            return False

    def _collect_cmdline(self, pid: int) -> str:
        if _HAS_PSUTIL and psutil is not None:
            try:
                return " ".join(psutil.Process(pid).cmdline())
            except Exception:
                pass
        try:
            data = Path(f"/proc/{pid}/cmdline").read_bytes()
            return data.replace(b"\x00", b" ").decode(errors="replace").strip()
        except Exception:
            return ""

    def _build_record(
        self,
        issue:         Any,
        outcome:       str,
        veto_reason:   str,
        signal:        int,
        fix_result:    Any = None,
        forensic_path: str = "",
    ) -> ActionRecord:
        pid     = getattr(issue, "pid",          0)
        name    = getattr(issue, "name",         "unknown")
        exe     = getattr(issue, "exe_path",     "") or ""
        user    = getattr(issue, "user",         "?")
        score   = getattr(issue, "threat_score", 0)
        level   = getattr(issue, "threat_level", "UNKNOWN")
        cmdline = getattr(issue, "cmdline",      "")
        if not cmdline and outcome == "killed":
            cmdline = self._collect_cmdline(pid)

        return ActionRecord(
            action_id     = f"kill_{pid}_{int(time.time())}",
            pid           = pid,
            name          = name,
            threat_level  = level,
            threat_score  = score,
            exe_path      = exe,
            cmdline       = cmdline or "",
            user          = user,
            timestamp     = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            kill_signal   = signal,
            outcome       = outcome,
            veto_reason   = veto_reason,
            fix_result    = fix_result,
            forensic_path = forensic_path,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 8. CONVENIENCE FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def create_auto_response_monitor(
    scan_interval:               float                              = 5.0,
    sigterm_grace:               float                              = 3.0,
    extra_safe_names:            Optional[Set[str]]                = None,
    high_threat_callback:        Optional[Callable[[Any], None]]   = None,
    fix_confirm_fn:              Optional[Callable[[str], bool]]   = None,
    auto_confirm_non_dangerous:  bool                              = True,
    paused:                      bool                              = False,
    enable_forensics:            bool                              = True,
    forensic_sha256:             bool                              = True,
    enable_threat_intel:         bool                              = True,
) -> Tuple[Any, "AutoResponder"]:
    """
    Factory that constructs a (RealTimeMonitor, AutoResponder) pair.
    Raises ImportError if fix_engine.py or jenix_suspicious_process_detector.py
    are unavailable.
    """
    _lazy_import()

    if fix_confirm_fn is None and auto_confirm_non_dangerous:
        fix_confirm_fn = lambda _prompt: True

    try:
        from fix_engine import FixEngine
        fix_engine = FixEngine(confirm_fn=fix_confirm_fn)
    except ImportError as exc:
        raise ImportError(
            "fix_engine.py must be on the Python path to use "
            "create_auto_response_monitor()"
        ) from exc

    responder = AutoResponder(
        fix_engine           = fix_engine,
        sigterm_grace        = sigterm_grace,
        extra_safe_names     = extra_safe_names,
        high_threat_callback = high_threat_callback,
        paused               = paused,
        enable_forensics     = enable_forensics,
        forensic_sha256      = forensic_sha256,
    )

    try:
        from jenix_suspicious_process_detector import RealTimeMonitor
        monitor = RealTimeMonitor(
            interval            = scan_interval,
            on_threat_detected  = responder.handle_threat,
            alert_levels        = {"HIGH", "CRITICAL"},
            enable_threat_intel = enable_threat_intel,
        )
    except ImportError as exc:
        raise ImportError(
            "jenix_suspicious_process_detector.py must be on the Python path "
            "to use create_auto_response_monitor()"
        ) from exc

    return monitor, responder
