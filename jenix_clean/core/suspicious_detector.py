"""
jenix_suspicious_process_detector.py
═════════════════════════════════════
JENIX v4.4 — Correlation Engine: Enhanced Suspicious Process Detection Module
           + Real-Time Monitoring Engine
           + Threat Intelligence Integration

v4.4 New additions on top of v4.2.1:
  ✦ ThreatIntelligence integrated into SuspiciousProcessDetector.detect()
        · Known-bad process names  — IOC database match raises threat_score
        · Suspicious ports         — flags connections to known C2/malware ports
        · Suspicious path patterns — broader pattern coverage beyond v4.x rules
        · Reason: "Matched known threat pattern: ..."
        · Score bonus applied per match (default +30 per hit)
  ✦ All previous fields, dataclasses, and API preserved — zero breaking changes

v4.2.1 additions (unchanged):
  ✦ RealTimeMonitor — background-thread continuous process surveillance

v4.2 additions (unchanged):
  ✦ CorrelationEngine  — weighted signal scoring system
  ✦ SuspiciousProcessIssue extended with threat_score / threat_level /
    correlation_summary

v4.1 additions (unchanged):
  ✦ SuspiciousProcessIssue  — rich dataclass replacing bare ProcessInfo
  ✦ SuspiciousProcessDetector — multi-signal heuristic engine
  ✦ Patched ScanEngine.run_full_scan
  ✦ EnhancedReportGenerator

Usage:
  # Drop-in replacement for ScanEngine:
  from jenix_suspicious_process_detector import ScanEngine

  # Real-time monitoring (optional, opt-in):
  from jenix_suspicious_process_detector import RealTimeMonitor
  monitor = RealTimeMonitor(interval=10, on_threat_detected=my_callback)
  monitor.start()
  ...
  monitor.stop()

  # Threat Intelligence (opt-in enrichment):
  from jenix_suspicious_process_detector import ScanEngine, ThreatIntelligence
  # TI is enabled by default inside ScanEngine.run_full_scan and
  # RealTimeMonitor._scan_cycle.  Pass enable_threat_intel=False to disable.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ── Import everything from the base engine ────────────────────────────────────
from jenix_scan_engine import (
    Issue,
    PerformanceStats,
    PortInfo,
    ProcessInfo,
    Recommendation,
    ReportGenerator,
    ScanResult,
    SystemInfo,
    WeightedHealthScorer,
    _HAS_PSUTIL,
    _SAFE_PROCESSES,
    _run,
    _safe,
)

# ── Optional Threat Intelligence (graceful degradation if absent) ─────────────
try:
    from threat_intelligence import ThreatIntelligence, ForensicCapture
    _HAS_TI = True
except ImportError:
    ThreatIntelligence = None   # type: ignore
    ForensicCapture    = None   # type: ignore
    _HAS_TI = False

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# 0. SIGNAL WEIGHTS  — single source of truth for the correlation engine
# ══════════════════════════════════════════════════════════════════════════════

SIGNAL_WEIGHTS: Dict[str, int] = {
    "LOW":      10,
    "MEDIUM":   25,
    "HIGH":     40,
    "CRITICAL": 60,
}

_THREAT_THRESHOLDS = [
    (100, "CRITICAL"),
    (70,  "HIGH"),
    (40,  "MEDIUM"),
    (0,   "LOW"),
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. RICH SUSPICIOUS-PROCESS DATACLASS  (v4.2 — extended with correlation fields)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SuspiciousProcessIssue:
    """
    Replaces bare ProcessInfo for flagged processes.
    All original ProcessInfo fields are preserved plus forensic extras (v4.1)
    and correlation scoring fields (v4.2).
    """
    # ── Core identity (mirrors ProcessInfo) ───────────────────────────────────
    pid:          int
    name:         str
    cpu_pct:      float
    mem_pct:      float
    mem_mb:       float
    status:       str
    user:         str

    # ── Forensic fields (v4.1) ────────────────────────────────────────────────
    exe_path:     str = ""
    cmdline:      str = ""
    create_time:  float = 0.0
    uptime_hours: float = 0.0
    ppid:         int = 0
    parent_name:  str = ""
    open_files:   int = 0
    connections:  int = 0

    # ── Per-signal metadata (v4.1) ────────────────────────────────────────────
    reasons:      List[str] = field(default_factory=list)
    severity:     str = "HIGH"          # legacy per-signal severity (preserved)
    issue_type:   str = "suspicious_process"

    # ── Correlation scoring (v4.2) ────────────────────────────────────────────
    threat_score:         int  = 0
    threat_level:         str  = "LOW"
    correlation_summary:  str  = ""

    # ── Suggested actions ─────────────────────────────────────────────────────
    kill_process:        str = ""
    investigate_process: str = ""

    # ── signal_weights tracking (internal) ────────────────────────────────────
    _signal_weights: List[Tuple[str, int]] = field(
        default_factory=list, repr=False, compare=False
    )

    # ── v4.4: raw psutil connections (populated by ForensicCapture, TI) ───────
    _raw_connections: List[Any] = field(
        default_factory=list, repr=False, compare=False
    )

    def to_issue(self) -> Issue:
        """Convert to a standard Issue for backward compatibility."""
        detail = (
            f"PID {self.pid} | CPU {self.cpu_pct:.1f}% | "
            f"RAM {self.mem_pct:.1f}% ({self.mem_mb:.0f}MB) | "
            f"Uptime {self.uptime_hours:.1f}h | "
            f"Path: {self.exe_path or '(unknown)'} | "
            f"Threat Score: {self.threat_score} [{self.threat_level}]"
        )
        return Issue(
            severity  = self.threat_level,
            category  = "suspicious_process",
            title     = (
                f"Suspicious process: '{self.name}' (PID {self.pid}) "
                f"— Score {self.threat_score} [{self.threat_level}]"
            ),
            detail    = f"{detail}\n    Summary: {self.correlation_summary}",
            fix_hint  = self.kill_process or self.investigate_process,
        )

    def to_recommendation(self) -> Recommendation:
        """Convert to a Recommendation for the report engine."""
        icon_map = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
        icon = icon_map.get(self.threat_level, "•")
        return Recommendation(
            priority  = self.threat_level,
            group     = "Security",
            problem   = (
                f"{icon} [{self.threat_level} | Score {self.threat_score}] "
                f"Process '{self.name}' (PID {self.pid}): {self.correlation_summary}"
            ),
            solution  = (
                "Investigate binary, parent process, and network connections. "
                "Kill only after confirming it is malicious."
            ),
            impact    = "high" if self.threat_level in ("CRITICAL", "HIGH") else "medium",
            command   = self.investigate_process,
            rationale = self.kill_process,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. CORRELATION ENGINE  (v4.2)
# ══════════════════════════════════════════════════════════════════════════════

class CorrelationEngine:
    """
    Combines individual heuristic signal hits into a single weighted
    threat_score and derives a correlated threat_level and a
    human-readable correlation_summary.
    """

    _FRAGMENT_MAP: List[Tuple[str, str]] = [
        ("High CPU",                    "sustained high CPU consumption"),
        ("High RAM",                    "elevated memory footprint"),
        ("High absolute RAM",           "large absolute memory usage"),
        ("suspicious path",             "binary running from a world-writable or temp directory"),
        ("not owned by any",            "no installed package claims this binary"),
        ("long runtime",                "abnormally long uptime for a non-daemon process"),
        ("Extreme runtime",             "extreme uptime suggesting a persistent hidden workload"),
        ("Name/binary mismatch",        "process name does not match its binary — possible masquerading"),
        ("unresolvable",                "executable path is hidden or deleted"),
        ("hidden filename",             "binary uses a hidden (dot-prefixed) filename"),
        ("Malformed",                   "executable path contains traversal or double-slash sequences"),
        ("Root process",                "root-owned process with active network connections and no package owner"),
        # v4.4: TI-specific fragments
        ("Matched known threat pattern","matched entry in threat intelligence IOC database"),
    ]

    _TAIL_MAP: Dict[str, str] = {
        "CRITICAL": (
            "The combination of signals indicates a high-confidence threat — "
            "likely malware, rootkit, or an actively exploited process."
        ),
        "HIGH": (
            "The correlated signals strongly suggest malicious or unauthorised activity; "
            "immediate investigation is recommended."
        ),
        "MEDIUM": (
            "Multiple weak-to-medium signals correlate into a notable risk; "
            "manual verification is advised."
        ),
        "LOW": (
            "A single low-weight signal was observed; monitor the process "
            "but no immediate action is required."
        ),
    }

    def score_and_summarise(
        self,
        reasons: List[str],
        signal_severities: List[str],
    ) -> Tuple[int, str, str]:
        threat_score = sum(SIGNAL_WEIGHTS.get(sev, 0) for sev in signal_severities)

        threat_level = "LOW"
        for threshold, level in _THREAT_THRESHOLDS:
            if threat_score > threshold:
                threat_level = level
                break

        narrative_parts: List[str] = []
        used: Set[str] = set()

        for reason in reasons:
            reason_lower = reason.lower()
            for keyword, fragment in self._FRAGMENT_MAP:
                if keyword.lower() in reason_lower and fragment not in used:
                    narrative_parts.append(fragment)
                    used.add(fragment)
                    break
            else:
                trimmed = reason.split("(")[0].rstrip(": ").strip()
                if trimmed and trimmed not in used:
                    narrative_parts.append(trimmed.lower())
                    used.add(trimmed)

        if not narrative_parts:
            narrative_parts = ["heuristic signal match"]

        if len(narrative_parts) == 1:
            reason_phrase = narrative_parts[0]
        elif len(narrative_parts) == 2:
            reason_phrase = f"{narrative_parts[0]} and {narrative_parts[1]}"
        else:
            reason_phrase = (
                ", ".join(narrative_parts[:-1]) + f", and {narrative_parts[-1]}"
            )

        tail = self._TAIL_MAP.get(threat_level, "")
        summary = f"Process flagged due to {reason_phrase} — {tail}"

        return threat_score, threat_level, summary


# ══════════════════════════════════════════════════════════════════════════════
# 3. PACKAGE ORACLE
# ══════════════════════════════════════════════════════════════════════════════

class _PackageOracle:
    def __init__(self):
        self._cache: Dict[str, Optional[str]] = {}
        self._has_dpkg   = bool(shutil.which("dpkg"))
        self._has_rpm    = bool(shutil.which("rpm"))
        self._has_pacman = bool(shutil.which("pacman"))

    def owner(self, exe_path: str) -> Optional[str]:
        if not exe_path or exe_path in ("<unknown>", ""):
            return None
        if exe_path in self._cache:
            return self._cache[exe_path]

        pkg = None
        if self._has_dpkg:
            rc, out, _ = _run(f"dpkg -S {exe_path} 2>/dev/null", timeout=5)
            if rc == 0 and ":" in out:
                pkg = out.split(":")[0].strip()
        if pkg is None and self._has_rpm:
            rc, out, _ = _run(f"rpm -qf {exe_path} 2>/dev/null", timeout=5)
            if rc == 0 and "not owned" not in out:
                pkg = out.strip()
        if pkg is None and self._has_pacman:
            rc, out, _ = _run(f"pacman -Qo {exe_path} 2>/dev/null", timeout=5)
            if rc == 0 and "owned by" in out:
                pkg = out.split("owned by")[-1].strip()

        self._cache[exe_path] = pkg
        return pkg


# ══════════════════════════════════════════════════════════════════════════════
# 4. SUSPICIOUS PROCESS DETECTOR  (v4.4 — TI-aware)
# ══════════════════════════════════════════════════════════════════════════════

_SUSPICIOUS_PATH_PREFIXES = (
    "/tmp/", "/var/tmp/", "/dev/shm/", "/run/shm/",
    "/home/", "/root/", "/var/www/",
)

_TRUSTED_PATH_PREFIXES = (
    "/usr/bin/", "/usr/sbin/", "/usr/lib/", "/usr/libexec/",
    "/bin/", "/sbin/", "/lib/", "/opt/",
    "/usr/local/bin/", "/usr/local/sbin/",
    "/snap/", "/var/lib/docker/", "/nix/store/",
)

_LONG_LIVED_DAEMONS: Set[str] = {
    "systemd", "init", "dockerd", "containerd", "postgres", "mysql",
    "mongod", "nginx", "apache2", "httpd", "redis-server", "sshd",
    "networkmanager", "dbus-daemon", "journald", "rsyslogd",
    "chronyd", "ntpd", "cron", "atd", "udevd", "polkitd",
    "fail2ban-server", "node", "python3", "java", "ruby",
}

_RAM_PCT_THRESHOLD    = 10.0
_RAM_MB_THRESHOLD     = 500.0
_CPU_PCT_THRESHOLD    = 70.0
_UPTIME_NONDAEMON_H   = 7 * 24
_UPTIME_ANY_H         = 30 * 24


@dataclass
class _Signal:
    reason:   str
    severity: str


class SuspiciousProcessDetector:
    """
    Multi-signal heuristic engine with integrated CorrelationEngine
    and optional ThreatIntelligence enrichment (v4.4).

    Parameters
    ──────────
    enable_threat_intel
        If True (default) and threat_intelligence.py is importable,
        each detected process is enriched with TI signals after the
        heuristic pass.  Set False to restore v4.2.1 behaviour exactly.
    ti_instance
        Optional pre-constructed ThreatIntelligence instance.
        If None and enable_threat_intel=True, a default instance is created.
    """

    def __init__(
        self,
        enable_threat_intel: bool = True,
        ti_instance: Optional[Any] = None,
    ) -> None:
        self._oracle      = _PackageOracle()
        self._correlator  = CorrelationEngine()

        # ── Threat Intelligence (v4.4) ────────────────────────────────────────
        self._ti: Optional[Any] = None
        if enable_threat_intel and _HAS_TI:
            self._ti = ti_instance or ThreatIntelligence()

    def detect(
        self,
        perf: PerformanceStats,
    ) -> List[SuspiciousProcessIssue]:
        if not _HAS_PSUTIL or psutil is None:
            return []

        detected: List[SuspiciousProcessIssue] = []

        try:
            for proc in psutil.process_iter([
                "pid", "name", "cpu_percent", "memory_percent",
                "memory_info", "status", "username",
                "create_time", "ppid", "exe", "cmdline",
            ]):
                try:
                    spi = self._analyse(proc, perf)
                    if spi is not None and spi.reasons:
                        detected.append(spi)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

        time.sleep(0.3)
        pid_map = {s.pid: s for s in detected}
        try:
            for proc in psutil.process_iter(["pid", "cpu_percent"]):
                try:
                    pid = proc.info["pid"]
                    if pid in pid_map:
                        cpu = proc.info.get("cpu_percent") or 0.0
                        pid_map[pid].cpu_pct = round(cpu, 1)
                        self._recompute_correlation(pid_map[pid])
                except Exception:
                    pass
        except Exception:
            pass

        # ── v4.4: TI enrichment pass ──────────────────────────────────────────
        if self._ti is not None:
            for spi in detected:
                try:
                    self._ti.enrich(spi)
                except Exception:
                    pass   # TI errors must never break the scan

        return sorted(detected, key=lambda x: (
            {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x.threat_level, 4),
            -x.threat_score,
            -x.cpu_pct,
        ))

    def detect_single(self, proc: Any) -> Optional[SuspiciousProcessIssue]:
        """
        Analyse a single psutil.Process object.
        Used by RealTimeMonitor to avoid a full re-scan.
        Includes TI enrichment (v4.4).
        """
        if not _HAS_PSUTIL or psutil is None:
            return None
        try:
            dummy_perf = _make_dummy_perf()
            spi = self._analyse(proc, dummy_perf)
            if spi is not None and self._ti is not None:
                try:
                    self._ti.enrich(spi)
                except Exception:
                    pass
            return spi
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
        except Exception:
            return None

    def _analyse(
        self,
        proc: Any,
        perf: PerformanceStats,
    ) -> Optional[SuspiciousProcessIssue]:
        info = proc.info
        pid  = info.get("pid", 0)
        name = (info.get("name") or "unknown").lower()

        if pid <= 1:
            return None

        exe_path    = ""
        cmdline_str = ""
        create_time = 0.0
        ppid        = info.get("ppid", 0) or 0
        parent_name = ""
        mem_info    = info.get("memory_info")
        mem_mb      = round((mem_info.rss if mem_info else 0) / 1024**2, 1)
        cpu_pct     = round(info.get("cpu_percent") or 0.0, 1)
        mem_pct     = round(info.get("memory_percent") or 0.0, 2)
        status      = info.get("status", "unknown") or "unknown"
        user        = info.get("username", "?") or "?"

        try:
            exe_path = proc.exe() or ""
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            exe_path = ""

        try:
            cmdline_str = " ".join(proc.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cmdline_str = name

        try:
            create_time = proc.create_time()
        except Exception:
            create_time = 0.0

        uptime_h = (time.time() - create_time) / 3600.0 if create_time else 0.0

        try:
            parent = proc.parent()
            if parent:
                parent_name = (parent.name() or "").lower()
        except Exception:
            pass

        open_files_count = 0
        try:
            open_files_count = len(proc.open_files())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

        connections_count = 0
        try:
            connections_count = len(proc.connections())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

        signals: List[_Signal] = []

        if cpu_pct >= _CPU_PCT_THRESHOLD:
            signals.append(_Signal(
                reason   = f"High CPU usage: {cpu_pct:.1f}% (threshold {_CPU_PCT_THRESHOLD:.0f}%)",
                severity = "HIGH",
            ))

        if mem_pct >= _RAM_PCT_THRESHOLD:
            signals.append(_Signal(
                reason   = f"High RAM usage: {mem_pct:.1f}% of system RAM ({mem_mb:.0f}MB)",
                severity = "MEDIUM",
            ))
        elif mem_mb >= _RAM_MB_THRESHOLD:
            signals.append(_Signal(
                reason   = f"High absolute RAM: {mem_mb:.0f}MB (threshold {_RAM_MB_THRESHOLD:.0f}MB)",
                severity = "MEDIUM",
            ))

        path_suspicious, path_reason = self._check_path(exe_path, name)
        if path_suspicious:
            signals.append(_Signal(reason=path_reason, severity="HIGH"))

        safe_names_lower = {s.lower() for s in _SAFE_PROCESSES}
        if exe_path and name not in safe_names_lower:
            pkg = self._oracle.owner(exe_path)
            if pkg is None:
                signals.append(_Signal(
                    reason   = (
                        f"Binary '{exe_path}' is not owned by any installed package "
                        f"(dpkg/rpm/pacman)"
                    ),
                    severity = "MEDIUM",
                ))

        if uptime_h > 0:
            is_daemon = name in _LONG_LIVED_DAEMONS
            if not is_daemon and uptime_h > _UPTIME_NONDAEMON_H:
                signals.append(_Signal(
                    reason   = (
                        f"Unusually long runtime: {uptime_h:.0f}h "
                        f"({uptime_h / 24:.1f} days) for a non-daemon process"
                    ),
                    severity = "MEDIUM",
                ))
            elif uptime_h > _UPTIME_ANY_H:
                signals.append(_Signal(
                    reason   = f"Extreme runtime: {uptime_h:.0f}h ({uptime_h / 24:.1f} days)",
                    severity = "MEDIUM",
                ))

        if exe_path:
            binary_name = Path(exe_path).name.lower()
            interpreters = {
                "python", "python3", "python2", "node", "ruby",
                "perl", "bash", "sh", "zsh", "php", "java",
            }
            if (
                name not in interpreters
                and binary_name not in interpreters
                and binary_name != name
                and not binary_name.startswith(name[:4])
                and not name.startswith(binary_name[:4])
            ):
                signals.append(_Signal(
                    reason   = (
                        f"Name/binary mismatch: process reports as '{name}' "
                        f"but binary is '{binary_name}' — possible masquerading"
                    ),
                    severity = "HIGH",
                ))

        if (
            user in ("root", "0")
            and connections_count > 0
            and exe_path
            and self._oracle.owner(exe_path) is None
        ):
            signals.append(_Signal(
                reason   = (
                    f"Root process with {connections_count} network connection(s) "
                    f"and no package owner"
                ),
                severity = "CRITICAL",
            ))

        if not signals:
            return None

        all_severities = [s.severity for s in signals]
        reasons_list   = [s.reason for s in signals]

        legacy_severity = max(
            all_severities,
            key=lambda sv: {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(sv, 0),
        )

        if name in safe_names_lower and legacy_severity in ("LOW", "MEDIUM"):
            return None

        threat_score, threat_level, correlation_summary = (
            self._correlator.score_and_summarise(reasons_list, all_severities)
        )

        investigate_cmds = (
            f"ls -la /proc/{pid}/exe 2>/dev/null; "
            f"cat /proc/{pid}/cmdline 2>/dev/null | tr '\\0' ' '; "
            f"lsof -p {pid} 2>/dev/null | head -20; "
            f"ss -tulnp 2>/dev/null | grep {pid}"
        )
        kill_cmd = (
            f"# ⚠ Verify before killing:\n"
            f"# sudo kill -15 {pid}   # graceful SIGTERM first\n"
            f"# sudo kill -9  {pid}   # force kill if SIGTERM fails"
        )

        return SuspiciousProcessIssue(
            pid                  = pid,
            name                 = name,
            cpu_pct              = cpu_pct,
            mem_pct              = mem_pct,
            mem_mb               = mem_mb,
            status               = status,
            user                 = user,
            exe_path             = exe_path,
            cmdline              = cmdline_str[:200],
            create_time          = create_time,
            uptime_hours         = round(uptime_h, 1),
            ppid                 = ppid,
            parent_name          = parent_name,
            open_files           = open_files_count,
            connections          = connections_count,
            reasons              = reasons_list,
            severity             = legacy_severity,
            issue_type           = "suspicious_process",
            threat_score         = threat_score,
            threat_level         = threat_level,
            correlation_summary  = correlation_summary,
            kill_process         = kill_cmd,
            investigate_process  = investigate_cmds,
            _signal_weights      = list(zip(reasons_list, [
                SIGNAL_WEIGHTS.get(sv, 0) for sv in all_severities
            ])),
        )

    def _recompute_correlation(self, spi: SuspiciousProcessIssue) -> None:
        if not spi._signal_weights:
            return
        reasons    = [r for r, _ in spi._signal_weights]
        severities = []
        for _, w in spi._signal_weights:
            rev = {v: k for k, v in SIGNAL_WEIGHTS.items()}
            severities.append(rev.get(w, "LOW"))

        ts, tl, cs = self._correlator.score_and_summarise(reasons, severities)
        spi.threat_score        = ts
        spi.threat_level        = tl
        spi.correlation_summary = cs

    def _check_path(self, exe_path: str, proc_name: str) -> Tuple[bool, str]:
        if not exe_path:
            if proc_name not in {s.lower() for s in _SAFE_PROCESSES}:
                return True, "Executable path is unresolvable (deleted or hidden binary)"
            return False, ""

        for prefix in _SUSPICIOUS_PATH_PREFIXES:
            if exe_path.startswith(prefix):
                return True, (
                    f"Binary running from suspicious path: '{exe_path}' "
                    f"(world-writable or temp directory)"
                )

        binary_name = Path(exe_path).name
        if binary_name.startswith("."):
            return True, f"Binary has hidden filename: '{binary_name}'"

        if "//" in exe_path or ".." in exe_path:
            return True, f"Malformed executable path: '{exe_path}'"

        return False, ""


# ══════════════════════════════════════════════════════════════════════════════
# 4a. PERF STUB helper for single-process analysis in RealTimeMonitor
# ══════════════════════════════════════════════════════════════════════════════

def _make_dummy_perf() -> PerformanceStats:
    """
    Return a zeroed PerformanceStats instance so SuspiciousProcessDetector
    can analyse a single process without a full system scan.
    """
    try:
        import dataclasses
        if dataclasses.is_dataclass(PerformanceStats):
            fields    = dataclasses.fields(PerformanceStats)
            defaults  = {}
            for f in fields:
                if f.default is not dataclasses.MISSING:
                    defaults[f.name] = f.default
                elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                    defaults[f.name] = f.default_factory()
                else:
                    ann = f.type
                    if ann in (float, "float"):
                        defaults[f.name] = 0.0
                    elif ann in (int, "int"):
                        defaults[f.name] = 0
                    elif ann in (list, "List", "list"):
                        defaults[f.name] = []
                    elif ann in (dict, "Dict", "dict"):
                        defaults[f.name] = {}
                    elif ann in (str, "str"):
                        defaults[f.name] = ""
                    elif ann in (bool, "bool"):
                        defaults[f.name] = False
                    else:
                        defaults[f.name] = None
            return PerformanceStats(**defaults)
    except Exception:
        pass
    return PerformanceStats()


# ══════════════════════════════════════════════════════════════════════════════
# 5. SEVERITY ESCALATION HELPER  (v4.1 — preserved)
# ══════════════════════════════════════════════════════════════════════════════

_SEV_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

def _escalate(current: str, candidate: str) -> str:
    return candidate if _SEV_RANK.get(candidate, 0) > _SEV_RANK.get(current, 0) else current


# ══════════════════════════════════════════════════════════════════════════════
# 6. SCANRESULT INJECTION HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _inject_rich_suspicious(result: ScanResult, data: List[SuspiciousProcessIssue]) -> None:
    result.__dict__["rich_suspicious_procs"] = data


# ══════════════════════════════════════════════════════════════════════════════
# 7. REAL-TIME MONITOR  (v4.2.1 — unchanged API; v4.4 TI via detector)
# ══════════════════════════════════════════════════════════════════════════════

_SCORE_ESCALATION_DELTA = 20
_ALERT_LEVELS: Set[str] = {"HIGH", "CRITICAL"}
_rtm_logger = logging.getLogger("jenix.realtime")


@dataclass
class _ProcessSnapshot:
    """
    Lightweight per-process cache entry stored between monitor cycles.
    """
    pid:          int
    name:         str
    cpu_pct:      float
    mem_mb:       float
    connections:  int
    threat_score: int
    threat_level: str
    exe_path:     str
    last_seen:    float = field(default_factory=time.time)
    issue:        Optional[SuspiciousProcessIssue] = field(
        default=None, repr=False, compare=False
    )


class RealTimeMonitor:
    """
    JENIX v4.4 — Real-Time Process Monitor
    ─────────────────────────────────────────
    Unchanged public API from v4.2.1.  TI enrichment is applied automatically
    inside SuspiciousProcessDetector.detect_single() — no changes required here.

    Parameters
    ──────────
    interval
        Seconds between scan cycles (minimum 1 s).
    on_threat_detected
        Optional callback: (issue: SuspiciousProcessIssue) -> None.
    alert_levels
        Set of threat_level strings that generate alerts. Default: {"HIGH","CRITICAL"}.
    score_escalation_delta
        Minimum score increase before re-alerting a known process. Default: 20.
    logger
        Custom logger.
    enable_threat_intel
        Pass-through to SuspiciousProcessDetector. Default: True.
    """

    def __init__(
        self,
        interval:               float                                         = 5.0,
        on_threat_detected:     Optional[Callable[[SuspiciousProcessIssue], None]] = None,
        alert_levels:           Optional[Set[str]]                           = None,
        score_escalation_delta: int                                          = _SCORE_ESCALATION_DELTA,
        logger:                 Optional[logging.Logger]                     = None,
        enable_threat_intel:    bool                                         = True,
    ) -> None:
        if not _HAS_PSUTIL or psutil is None:
            raise RuntimeError(
                "RealTimeMonitor requires psutil.  Install it with:  pip install psutil"
            )

        self._interval         = max(1.0, float(interval))
        self._callback         = on_threat_detected
        self._alert_levels     = alert_levels or _ALERT_LEVELS
        self._escalation_delta = int(score_escalation_delta)
        self._log              = logger or _rtm_logger

        self._detector = SuspiciousProcessDetector(
            enable_threat_intel=enable_threat_intel
        )

        self._lock:           threading.Lock             = threading.Lock()
        self._stop_event:     threading.Event            = threading.Event()
        self._thread:         Optional[threading.Thread] = None
        self._cache:          Dict[int, _ProcessSnapshot] = {}
        self._current_issues: Dict[int, SuspiciousProcessIssue] = {}
        self._cycle:          int = 0

    # ── Public lifecycle API ──────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._log.warning("RealTimeMonitor.start() called but monitor is already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target = self._run_loop,
                name   = "jenix-rtm",
                daemon = True,
            )
            self._thread.start()
            self._log.info(
                "RealTimeMonitor started  (interval=%.1fs, alert_levels=%s)",
                self._interval, self._alert_levels,
            )
            print(
                f"[JENIX-RTM] Real-Time Monitor started "
                f"(interval={self._interval}s, alert_levels={sorted(self._alert_levels)})"
            )

    def stop(self, timeout: float = 15.0) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._log.info("RealTimeMonitor.stop() called but monitor is not running.")
                return
            self._stop_event.set()

        if timeout > 0:
            self._thread.join(timeout=timeout)

        with self._lock:
            alive = self._thread.is_alive() if self._thread else False

        if alive:
            self._log.warning("RealTimeMonitor thread did not exit within %.1fs.", timeout)
        else:
            self._log.info("RealTimeMonitor stopped.")
            print("[JENIX-RTM] Real-Time Monitor stopped.")

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_snapshot(self) -> Dict[int, SuspiciousProcessIssue]:
        with self._lock:
            return dict(self._current_issues)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            issues  = list(self._current_issues.values())
            by_level: Dict[str, int] = {}
            for spi in issues:
                by_level[spi.threat_level] = by_level.get(spi.threat_level, 0) + 1
            return {
                "is_running":    self._thread is not None and self._thread.is_alive(),
                "cycle":         self._cycle,
                "interval_s":    self._interval,
                "tracked_pids":  len(self._cache),
                "total_threats": len(issues),
                "by_level":      by_level,
            }

    # ── Internal monitor loop ─────────────────────────────────────────────────

    def _run_loop(self) -> None:
        self._log.debug("Monitor loop starting.")
        while not self._stop_event.is_set():
            cycle_start = time.monotonic()
            try:
                self._scan_cycle()
            except Exception as exc:
                self._log.error("Unexpected error in monitor cycle: %s", exc, exc_info=True)

            elapsed   = time.monotonic() - cycle_start
            remaining = self._interval - elapsed
            if remaining > 0:
                self._stop_event.wait(timeout=remaining)
        self._log.debug("Monitor loop exited cleanly.")

    def _scan_cycle(self) -> None:
        with self._lock:
            self._cycle += 1

        now         = time.time()
        seen_pids:  Set[int] = set()
        new_issues: Dict[int, SuspiciousProcessIssue] = {}
        alerts:     List[Tuple[str, SuspiciousProcessIssue]] = []

        try:
            live_procs = list(psutil.process_iter([
                "pid", "name", "cpu_percent", "memory_percent",
                "memory_info", "status", "username",
                "create_time", "ppid", "exe", "cmdline",
            ]))
        except Exception:
            return

        time.sleep(0.15)

        for proc in live_procs:
            try:
                pid  = proc.info.get("pid", 0)
                name = (proc.info.get("name") or "").lower()
            except Exception:
                continue

            if pid <= 1:
                continue

            seen_pids.add(pid)

            try:
                cpu_now  = round(proc.cpu_percent() or 0.0, 1)
                mem_info = proc.memory_info()
                mem_mb   = round((mem_info.rss if mem_info else 0) / 1024**2, 1)
                try:
                    conns = len(proc.connections())
                except Exception:
                    conns = 0
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

            with self._lock:
                cached = self._cache.get(pid)

            if cached is not None:
                cpu_changed  = abs(cpu_now - cached.cpu_pct) >= 10.0
                mem_changed  = abs(mem_mb  - cached.mem_mb)  >= 50.0
                conn_changed = conns != cached.connections

                if not (cpu_changed or mem_changed or conn_changed):
                    if cached.issue is not None:
                        new_issues[pid] = cached.issue
                    with self._lock:
                        if pid in self._cache:
                            self._cache[pid].last_seen = now
                    continue

            spi = self._detector.detect_single(proc)

            if spi is None:
                with self._lock:
                    self._cache.pop(pid, None)
                continue

            new_issues[pid] = spi

            if spi.threat_level in self._alert_levels:
                if cached is None:
                    alerts.append(("new", spi))
                elif spi.threat_score - cached.threat_score >= self._escalation_delta:
                    alerts.append(("escalated", spi))

            snap = _ProcessSnapshot(
                pid          = pid,
                name         = name,
                cpu_pct      = cpu_now,
                mem_mb       = mem_mb,
                connections  = conns,
                threat_score = spi.threat_score,
                threat_level = spi.threat_level,
                exe_path     = spi.exe_path,
                last_seen    = now,
                issue        = spi,
            )
            with self._lock:
                self._cache[pid] = snap

        with self._lock:
            stale = [pid for pid in self._cache if pid not in seen_pids]
            for pid in stale:
                del self._cache[pid]
            self._current_issues = new_issues

        for reason, spi in alerts:
            self._emit_alert(reason, spi)

    def _emit_alert(self, reason: str, spi: SuspiciousProcessIssue) -> None:
        ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level   = spi.threat_level
        action  = "New suspicious process detected" if reason == "new" \
                  else "Threat score escalated"

        divider = "─" * 66
        lines   = [
            "",
            f"  {divider}",
            f"  [ALERT][{level}]  {action}                    {ts}",
            f"  {divider}",
            f"  PID        : {spi.pid}",
            f"  Name       : {spi.name}",
            f"  Score      : {spi.threat_score}",
            f"  Threat     : {spi.threat_level}",
            f"  User       : {spi.user}",
            f"  Binary     : {spi.exe_path or '(unresolvable)'}",
            f"  CPU        : {spi.cpu_pct:.1f}%",
            f"  RAM        : {spi.mem_pct:.2f}%  ({spi.mem_mb:.0f} MB)",
            f"  Signals    : {len(spi.reasons)}",
        ]

        for i, r in enumerate(spi.reasons, 1):
            short = r[:80] + ("…" if len(r) > 80 else "")
            lines.append(f"  Signal {i:02d}  : {short}")

        lines += [
            f"  Summary    : {spi.correlation_summary[:120]}",
            f"  Investigate: {spi.investigate_process.split(';')[0].strip()}",
            f"  {divider}",
            "",
        ]

        print("\n".join(lines))
        _rtm_logger.warning(
            "[ALERT][%s] %s — PID %d (%s) score=%d",
            level, action, spi.pid, spi.name, spi.threat_score,
        )

        if self._callback is not None:
            try:
                self._callback(spi)
            except Exception as exc:
                _rtm_logger.error(
                    "on_threat_detected callback raised an exception: %s", exc, exc_info=True
                )


# ══════════════════════════════════════════════════════════════════════════════
# 8. PATCHED ScanEngine  (transparent drop-in)
# ══════════════════════════════════════════════════════════════════════════════

from jenix_scan_engine import ScanEngine as _BaseScanEngine

class ScanEngine(_BaseScanEngine):
    """
    Drop-in replacement for the base ScanEngine.
    Adds SuspiciousProcessDetector + CorrelationEngine + ThreatIntelligence
    on top of every full scan (v4.4).

    Parameters
    ──────────
    enable_threat_intel
        Enable ThreatIntelligence enrichment.  Default: True.
    """

    def __init__(self, enable_threat_intel: bool = True):
        super().__init__()
        self._susp_detector = SuspiciousProcessDetector(
            enable_threat_intel=enable_threat_intel
        )

    def run_full_scan(
        self,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> ScanResult:
        result = super().run_full_scan(progress_cb=progress_cb)

        if progress_cb:
            try:
                progress_cb(98, "Running correlation-engine suspicious process detection…")
            except Exception:
                pass

        rich_suspicious = self._susp_detector.detect(result.performance)
        _inject_rich_suspicious(result, rich_suspicious)

        result.issues = [
            i for i in result.issues
            if not (i.category == "Processes" and "suspicious process" in i.title.lower())
        ]
        for spi in rich_suspicious:
            result.issues.append(spi.to_issue())

        result.rich_recommendations = [
            r for r in result.rich_recommendations
            if not (
                r.group == "Security"
                and "is consuming" in r.problem
                and "CPU" in r.problem
            )
        ]
        for spi in rich_suspicious:
            result.rich_recommendations.append(spi.to_recommendation())

        from jenix_scan_engine import IntelligentRecommendationEngine
        result.recommendations = IntelligentRecommendationEngine().to_simple_list(
            result.rich_recommendations
        )

        scorer = WeightedHealthScorer()
        result.health_score, result.health_grade, result.health_status = scorer.score(
            result.performance,
            result.issues,
            result.open_ports,
            rich_suspicious,
        )

        if progress_cb:
            try:
                critical = sum(1 for s in rich_suspicious if s.threat_level == "CRITICAL")
                high     = sum(1 for s in rich_suspicious if s.threat_level == "HIGH")
                ti_note  = "  [TI active]" if _HAS_TI else ""
                progress_cb(100, (
                    f"Correlation scan complete{ti_note} — "
                    f"Score {result.health_score}/100 · Grade {result.health_grade} · "
                    f"{len(rich_suspicious)} flagged "
                    f"({critical} CRITICAL, {high} HIGH)"
                ))
            except Exception:
                pass

        return result


# ══════════════════════════════════════════════════════════════════════════════
# 9. ENHANCED ReportGenerator  (v4.4 — TI signals shown in forensics section)
# ══════════════════════════════════════════════════════════════════════════════

class EnhancedReportGenerator(ReportGenerator):
    """
    Extends base ReportGenerator to render the Suspicious Processes section
    with full correlation data, TI matches, and forensic extras in TXT/JSON.
    """

    def as_txt(self) -> str:
        base = super().as_txt()
        rich = getattr(self.r, "rich_suspicious_procs", [])
        if not rich:
            return base

        W   = 76
        out = [self._section(f"10 · Suspicious Process Forensics  ({len(rich)} flagged)")]

        sev_icons = {
            "CRITICAL": "🔴 CRITICAL",
            "HIGH":     "🟠 HIGH",
            "MEDIUM":   "🟡 MEDIUM",
            "LOW":      "🟢 LOW",
        }

        for idx, spi in enumerate(rich, 1):
            level_icon = sev_icons.get(spi.threat_level, spi.threat_level)
            score_bar  = self._score_bar(spi.threat_score)

            # Check for TI signals in reasons
            ti_signals  = [r for r in spi.reasons if "known threat pattern" in r.lower()]
            ti_badge    = "  ⚡ TI MATCH" if ti_signals else ""

            out += [
                f"  {'─' * 72}",
                f"  [{idx:02d}]  {level_icon}  ·  Threat Score: {spi.threat_score:>3d}  "
                f"{score_bar}{ti_badge}",
                f"         Process: '{spi.name}'  (PID {spi.pid})",
                f"  {'─' * 72}",
                "",
                f"  CORRELATION SUMMARY:",
                f"  {spi.correlation_summary}",
                "",
                f"  Binary Path    : {spi.exe_path or '(unresolvable)'}",
                f"  Command Line   : {spi.cmdline[:80] or '(unknown)'}",
                f"  User           : {spi.user}  |  PPID {spi.ppid} ({spi.parent_name or '?'})",
                f"  CPU            : {spi.cpu_pct:.1f}%",
                f"  RAM            : {spi.mem_pct:.2f}%  ({spi.mem_mb:.0f} MB)",
                f"  Uptime         : {spi.uptime_hours:.1f} hours  "
                f"({spi.uptime_hours / 24:.1f} days)",
                f"  Open Files     : {spi.open_files}  |  Network Connections: {spi.connections}",
                "",
                "  SIGNAL BREAKDOWN  (reason → weight):",
            ]

            for reason, weight in (spi._signal_weights or []):
                rev = {v: k for k, v in SIGNAL_WEIGHTS.items()}
                sev_label = rev.get(weight, "?")
                ti_flag   = " ⚡" if "known threat pattern" in reason.lower() else ""
                out.append(f"    [{sev_label:8s} +{weight:>2d}]{ti_flag}  {reason}")

            out += [
                "",
                "  INVESTIGATE:",
                f"  $ {spi.investigate_process}",
                "",
                "  KILL (only after investigation):",
            ]
            for line in spi.kill_process.splitlines():
                out.append(f"  {line}")
            out.append("")

        out += [
            "═" * W,
            "  ⚠  Never kill a process without investigation. False positives exist.",
            "  ⚡  TI MATCH = process name/path/port matched threat intelligence IOC database.",
            "═" * W,
            "",
        ]

        footer_start = base.rfind("\n" + "═" * W)
        if footer_start != -1:
            return base[:footer_start] + "\n" + "\n".join(out) + base[footer_start:]
        return base + "\n" + "\n".join(out)

    def as_dict(self) -> dict:
        d    = super().as_dict()
        rich = getattr(self.r, "rich_suspicious_procs", [])
        d["suspicious_processes_forensic"] = [
            {
                "issue_type":          spi.issue_type,
                "threat_score":        spi.threat_score,
                "threat_level":        spi.threat_level,
                "correlation_summary": spi.correlation_summary,
                "ti_matches":          [r for r in spi.reasons
                                        if "known threat pattern" in r.lower()],
                "signal_breakdown":    [
                    {
                        "reason":    r,
                        "weight":    w,
                        "is_ti_hit": "known threat pattern" in r.lower(),
                    }
                    for r, w in (spi._signal_weights or [])
                ],
                "severity":            spi.severity,
                "pid":                 spi.pid,
                "name":                spi.name,
                "cpu_pct":             spi.cpu_pct,
                "mem_pct":             spi.mem_pct,
                "mem_mb":              spi.mem_mb,
                "exe_path":            spi.exe_path,
                "cmdline":             spi.cmdline,
                "uptime_hours":        spi.uptime_hours,
                "user":                spi.user,
                "ppid":                spi.ppid,
                "parent_name":         spi.parent_name,
                "open_files":          spi.open_files,
                "connections":         spi.connections,
                "reasons":             spi.reasons,
                "suggested_actions": {
                    "investigate_process": spi.investigate_process,
                    "kill_process":        spi.kill_process,
                },
            }
            for spi in rich
        ]
        return d

    @staticmethod
    def _score_bar(score: int, width: int = 20) -> str:
        filled = min(int(score / 120 * width), width)
        return f"[{'█' * filled}{'░' * (width - filled)}]"


# ══════════════════════════════════════════════════════════════════════════════
# 10. STANDALONE TEST  (python3 jenix_suspicious_process_detector.py)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import signal as _signal

    print("JENIX v4.4 — TI + Forensics + Real-Time Monitor (standalone test)")
    print("─" * 70)
    if _HAS_TI:
        print("  ✅  threat_intelligence.py loaded — TI enrichment active")
    else:
        print("  ⚠   threat_intelligence.py not found — TI enrichment disabled")
    print()

    RUN_SCAN = True

    if RUN_SCAN:
        print("\n[1/2] Running one-shot full scan…\n")

        def progress(pct, msg):
            print(f"  [{pct:3d}%] {msg}")

        engine = ScanEngine()
        result = engine.run_full_scan(progress_cb=progress)
        report = EnhancedReportGenerator(result)
        print(report.as_txt())

        rich = getattr(result, "rich_suspicious_procs", [])
        if rich:
            print("\n" + "═" * 76)
            print("  CORRELATION SCORE SUMMARY TABLE")
            print("═" * 76)
            print(f"  {'PID':>7}  {'Name':<20}  {'Score':>6}  {'Level':>8}  {'TI':>4}  Signals")
            print(f"  {'─' * 7}  {'─' * 20}  {'─' * 6}  {'─' * 8}  {'─' * 4}  {'─' * 20}")
            for spi in rich:
                sigs    = len(spi._signal_weights or [])
                ti_hits = sum(1 for r in spi.reasons if "known threat pattern" in r.lower())
                ti_mark = f"⚡×{ti_hits}" if ti_hits else "—"
                print(
                    f"  {spi.pid:>7}  {spi.name:<20}  {spi.threat_score:>6}  "
                    f"{spi.threat_level:>8}  {ti_mark:>4}  {sigs} signal(s)"
                )
            print("═" * 76 + "\n")

    print("\n[2/2] Starting Real-Time Monitor (Ctrl-C to stop)…\n")

    def my_alert_callback(issue: SuspiciousProcessIssue) -> None:
        print(
            f"  [CALLBACK] on_threat_detected fired for PID {issue.pid} "
            f"({issue.name}) — score {issue.threat_score}"
        )

    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    )

    monitor = RealTimeMonitor(
        interval            = 5,
        on_threat_detected  = my_alert_callback,
        alert_levels        = {"HIGH", "CRITICAL"},
    )
    monitor.start()

    def _shutdown(signum, frame):
        print("\n[JENIX-RTM] Received shutdown signal.")
        monitor.stop()
        stats = monitor.get_stats()
        print(f"\n[JENIX-RTM] Final stats: {stats}")

    _signal.signal(_signal.SIGINT,  _shutdown)
    _signal.signal(_signal.SIGTERM, _shutdown)

    try:
        while monitor.is_running():
            time.sleep(1)
    except SystemExit:
        pass

    print("[JENIX-RTM] Exiting.")
