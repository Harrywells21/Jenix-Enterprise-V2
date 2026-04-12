"""
jenix_scan_engine.py
════════════════════
JENIX v4.1 — Production-Grade System Scan Engine  (UPGRADED)

Changes vs v4.0:
  ✦ WeightedHealthScorer  — CPU 30% / RAM 25% / Disk 20% / Proc 15% / Sec 10%
  ✦ Grade table           — A/B/C/D/F with status label
  ✦ IntelligentRecommendationEngine — grouped, prioritised, with impact + fix cmds
  ✦ InsightEngine         — plain-English system summary + verdicts
  ✦ ReportGenerator v2    — SUMMARY / HEALTH / ISSUES / RECOMMENDATIONS / COMMANDS
  ✦ All public API kept identical to v4.0 — drop-in compatible
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Safe psutil import ────────────────────────────────────────────────────────
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

def _bootstrap_psutil():
    global psutil, _HAS_PSUTIL
    if _HAS_PSUTIL:
        return True
    for cmd in [
        [sys.executable, "-m", "pip", "install", "--quiet", "psutil"],
        ["pip3", "install", "--quiet", "psutil"],
    ]:
        try:
            import subprocess
            if subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0:
                import importlib
                psutil = importlib.import_module("psutil")
                _HAS_PSUTIL = True
                return True
        except Exception:
            pass
    return False

_bootstrap_psutil()


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SystemInfo:
    hostname:       str = ""
    os_name:        str = ""
    kernel_version: str = ""
    architecture:   str = ""
    boot_time:      str = ""
    uptime_seconds: int = 0
    uptime_str:     str = ""
    cpu_model:      str = ""
    cpu_cores:      int = 0
    cpu_threads:    int = 0
    total_ram_gb:   float = 0.0
    python_version: str = ""

@dataclass
class PerformanceStats:
    cpu_percent:       float = 0.0
    cpu_per_core:      List[float] = field(default_factory=list)
    cpu_freq_mhz:      float = 0.0
    cpu_governor:      str = "unknown"
    ram_total_gb:      float = 0.0
    ram_used_gb:       float = 0.0
    ram_available_gb:  float = 0.0
    ram_percent:       float = 0.0
    swap_total_gb:     float = 0.0
    swap_used_gb:      float = 0.0
    swap_percent:      float = 0.0
    disks:             List[Dict] = field(default_factory=list)
    load_avg_1:        float = 0.0
    load_avg_5:        float = 0.0
    load_avg_15:       float = 0.0

@dataclass
class ProcessInfo:
    pid:     int
    name:    str
    cpu_pct: float
    mem_pct: float
    mem_mb:  float
    status:  str
    user:    str

@dataclass
class PortInfo:
    port:    int
    proto:   str
    process: str
    pid:     int
    risk:    str   # green / amber / red
    note:    str

@dataclass
class Issue:
    severity:    str   # LOW / MEDIUM / HIGH / CRITICAL
    category:    str
    title:       str
    detail:      str
    fix_hint:    str = ""

# ── NEW: richer recommendation dataclass ─────────────────────────────────────
@dataclass
class Recommendation:
    priority:    str          # CRITICAL / HIGH / MEDIUM / LOW
    group:       str          # Performance / Security / System Cleanup
    problem:     str
    solution:    str
    impact:      str          # low / medium / high
    command:     str = ""     # suggested safe command — never auto-executed
    rationale:   str = ""

# ── NEW: insight / verdict dataclass ─────────────────────────────────────────
@dataclass
class SystemInsight:
    performance_verdict: str = ""   # e.g. "System performance is stable"
    risk_summary:        str = ""   # e.g. "Potential security risk detected"
    system_summary:      str = ""   # plain-English narrative
    status_label:        str = ""   # Excellent / Good / Warning / Critical

@dataclass
class ScanResult:
    timestamp:           str = ""
    duration_s:          float = 0.0
    system_info:         SystemInfo = field(default_factory=SystemInfo)
    performance:         PerformanceStats = field(default_factory=PerformanceStats)
    top_cpu_procs:       List[ProcessInfo] = field(default_factory=list)
    top_mem_procs:       List[ProcessInfo] = field(default_factory=list)
    suspicious_procs:    List[ProcessInfo] = field(default_factory=list)
    open_ports:          List[PortInfo] = field(default_factory=list)
    issues:              List[Issue] = field(default_factory=list)
    health_score:        int = 100
    health_grade:        str = "A"
    health_status:       str = "Excellent"          # NEW
    recommendations:     List[str] = field(default_factory=list)
    rich_recommendations:List[Recommendation] = field(default_factory=list)  # NEW
    insight:             SystemInsight = field(default_factory=SystemInsight) # NEW


# ══════════════════════════════════════════════════════════════════════════════
# 2. HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _run(cmd: str, timeout: int = 10) -> Tuple[int, str, str]:
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)

def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

def _fmt_uptime(secs: int) -> str:
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

_SAFE_PROCESSES = {
    "systemd", "init", "kthreadd", "kworker", "ksoftirqd", "migration",
    "rcu_sched", "watchdog", "kswapd", "kdevtmpfs", "kauditd",
    "NetworkManager", "dbus-daemon", "polkitd", "sshd", "cron", "rsyslogd",
    "journald", "dockerd", "containerd", "postgres", "mysql", "nginx",
    "apache2", "httpd", "systemd-resolved", "systemd-networkd", "avahi-daemon",
    "cups", "chronyd", "ntpd", "ufw-init", "fail2ban-server", "python3",
    "python", "node", "bash", "sh", "zsh",
}

_RISK_DB: Dict[int, Tuple[str, str]] = {
    21:    ("FTP",        "red"),
    22:    ("SSH",        "green"),
    23:    ("Telnet",     "red"),
    25:    ("SMTP",       "amber"),
    53:    ("DNS",        "green"),
    80:    ("HTTP",       "green"),
    443:   ("HTTPS",      "green"),
    445:   ("SMB",        "red"),
    3306:  ("MySQL",      "red"),
    3389:  ("RDP",        "red"),
    5432:  ("PostgreSQL", "amber"),
    5900:  ("VNC",        "red"),
    6379:  ("Redis",      "red"),
    8080:  ("HTTP-Alt",   "amber"),
    9200:  ("Elastic",    "red"),
    27017: ("MongoDB",    "red"),
}


# ══════════════════════════════════════════════════════════════════════════════
# 3. COLLECTORS  (unchanged from v4.0)
# ══════════════════════════════════════════════════════════════════════════════

class SystemInfoCollector:
    def collect(self) -> SystemInfo:
        info = SystemInfo()
        import platform, socket
        info.hostname       = _safe(socket.gethostname, "unknown")
        info.architecture   = _safe(platform.machine, "unknown")
        info.python_version = _safe(lambda: sys.version.split()[0], "unknown")
        try:
            import distro
            info.os_name = distro.name(pretty=True) or platform.platform()
        except ImportError:
            info.os_name = platform.platform()
        info.kernel_version = _safe(platform.release, "unknown")
        if _HAS_PSUTIL:
            bt = _safe(lambda: psutil.boot_time(), 0.0)
            if bt:
                info.boot_time      = datetime.fromtimestamp(bt).strftime("%Y-%m-%d %H:%M:%S")
                info.uptime_seconds = int(time.time() - bt)
                info.uptime_str     = _fmt_uptime(info.uptime_seconds)
        rc, out, _ = _run("cat /proc/cpuinfo | grep 'model name' | head -1", timeout=3)
        if rc == 0 and ":" in out:
            info.cpu_model = out.split(":", 1)[1].strip()
        else:
            info.cpu_model = _safe(lambda: str(os.cpu_count()) + "-core CPU", "unknown")
        if _HAS_PSUTIL:
            info.cpu_cores    = _safe(lambda: psutil.cpu_count(logical=False) or 1, 1)
            info.cpu_threads  = _safe(lambda: psutil.cpu_count(logical=True) or 1, 1)
            info.total_ram_gb = _safe(
                lambda: round(psutil.virtual_memory().total / 1024**3, 2), 0.0)
        return info


class PerformanceCollector:
    def collect(self) -> PerformanceStats:
        p = PerformanceStats()
        if not _HAS_PSUTIL:
            return p
        _ = psutil.cpu_percent(interval=None)
        time.sleep(0.5)
        p.cpu_percent  = _safe(lambda: psutil.cpu_percent(interval=None), 0.0)
        p.cpu_per_core = _safe(lambda: psutil.cpu_percent(interval=0, percpu=True), [])
        try:
            freq = psutil.cpu_freq()
            if freq:
                p.cpu_freq_mhz = round(freq.current, 1)
        except Exception:
            pass
        gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        try:
            p.cpu_governor = Path(gov_path).read_text().strip()
        except Exception:
            p.cpu_governor = "unknown"
        mem = _safe(psutil.virtual_memory)
        if mem:
            p.ram_total_gb     = round(mem.total / 1024**3, 2)
            p.ram_used_gb      = round(mem.used  / 1024**3, 2)
            p.ram_available_gb = round(mem.available / 1024**3, 2)
            p.ram_percent      = mem.percent
        swap = _safe(psutil.swap_memory)
        if swap:
            p.swap_total_gb = round(swap.total / 1024**3, 2)
            p.swap_used_gb  = round(swap.used  / 1024**3, 2)
            p.swap_percent  = swap.percent
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    p.disks.append({
                        "mountpoint": part.mountpoint,
                        "fstype":     part.fstype,
                        "total_gb":   round(usage.total / 1024**3, 2),
                        "used_gb":    round(usage.used  / 1024**3, 2),
                        "free_gb":    round(usage.free  / 1024**3, 2),
                        "percent":    usage.percent,
                    })
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass
        try:
            la = os.getloadavg()
            p.load_avg_1, p.load_avg_5, p.load_avg_15 = la
        except Exception:
            pass
        return p


class ProcessCollector:
    def collect(self) -> Tuple[List[ProcessInfo], List[ProcessInfo], List[ProcessInfo]]:
        if not _HAS_PSUTIL:
            return [], [], []
        procs: List[ProcessInfo] = []
        try:
            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent",
                 "memory_info", "status", "username"]
            ):
                try:
                    i = proc.info
                    mem_mb = round((i.get("memory_info") or
                                    type("X", (), {"rss": 0})()).rss / 1024**2, 1)
                    procs.append(ProcessInfo(
                        pid     = i.get("pid", 0),
                        name    = i.get("name", "unknown") or "unknown",
                        cpu_pct = round(i.get("cpu_percent") or 0.0, 1),
                        mem_pct = round(i.get("memory_percent") or 0.0, 2),
                        mem_mb  = mem_mb,
                        status  = i.get("status", "unknown") or "unknown",
                        user    = i.get("username", "?") or "?",
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        time.sleep(0.3)
        try:
            for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    for p in procs:
                        if p.pid == proc.info["pid"]:
                            p.cpu_pct = round(proc.info.get("cpu_percent") or 0.0, 1)
                            break
                except Exception:
                    pass
        except Exception:
            pass
        top_cpu = sorted(procs, key=lambda x: x.cpu_pct, reverse=True)[:5]
        top_mem = sorted(procs, key=lambda x: x.mem_pct, reverse=True)[:5]
        suspicious = [
            p for p in procs
            if p.cpu_pct > 25.0
            and p.name.lower() not in {s.lower() for s in _SAFE_PROCESSES}
            and p.pid > 1
        ]
        return top_cpu, top_mem, suspicious


class PortCollector:
    def collect(self) -> List[PortInfo]:
        ports: List[PortInfo] = []
        seen: set = set()
        if shutil.which("ss"):
            rc, out, _ = _run("ss -tulnp 2>/dev/null", timeout=8)
        elif shutil.which("netstat"):
            rc, out, _ = _run("netstat -tulnp 2>/dev/null", timeout=8)
        else:
            return ports
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            proto = parts[0].lower().rstrip("46")
            local = parts[4] if shutil.which("ss") else parts[3]
            port_str = local.rsplit(":", 1)[-1]
            try:
                port_num = int(port_str)
            except ValueError:
                continue
            if port_num in seen:
                continue
            seen.add(port_num)
            pid = 0
            proc_name = "unknown"
            pid_m = re.search(r'pid=(\d+)', line)
            if pid_m:
                pid = int(pid_m.group(1))
            proc_m = re.search(r'"([^"]+)"', line)
            if proc_m:
                proc_name = proc_m.group(1)
            elif pid:
                rc2, pn, _ = _run(f"ps -p {pid} -o comm= 2>/dev/null", timeout=3)
                if rc2 == 0 and pn:
                    proc_name = pn.strip()
            known = _RISK_DB.get(port_num)
            svc  = known[0] if known else proc_name
            risk = known[1] if known else "amber"
            note = {
                "green": "Expected system service",
                "amber": "Review — verify this port is intentional",
                "red":   "High risk — restrict or close if not required",
            }.get(risk, "Unknown service")
            if port_num > 49152:
                risk = "amber"
            ports.append(PortInfo(
                port=port_num, proto=proto, process=svc,
                pid=pid, risk=risk, note=note,
            ))
        return sorted(ports, key=lambda x: (
            {"red": 0, "amber": 1, "green": 2}.get(x.risk, 3), x.port
        ))


# ══════════════════════════════════════════════════════════════════════════════
# 4. ISSUE DETECTOR  (unchanged from v4.0)
# ══════════════════════════════════════════════════════════════════════════════

class IssueDetector:
    def detect(
        self,
        perf:       PerformanceStats,
        procs_cpu:  List[ProcessInfo],
        suspicious: List[ProcessInfo],
        ports:      List[PortInfo],
    ) -> List[Issue]:
        issues: List[Issue] = []

        if perf.cpu_percent >= 90:
            issues.append(Issue("CRITICAL", "CPU",
                f"CPU usage at {perf.cpu_percent:.0f}%",
                "System is severely overloaded. Investigate immediately.",
                "ps aux --sort=-%cpu | head -20"))
        elif perf.cpu_percent >= 75:
            issues.append(Issue("HIGH", "CPU",
                f"CPU usage at {perf.cpu_percent:.0f}%",
                "Sustained high CPU may cause system instability.",
                "top  (press P to sort by CPU)"))
        elif perf.cpu_percent >= 50:
            issues.append(Issue("MEDIUM", "CPU",
                f"CPU usage at {perf.cpu_percent:.0f}%",
                "CPU load is elevated — monitor over time.",
                "top -b -n1 | head -25"))

        if perf.ram_percent >= 90:
            issues.append(Issue("CRITICAL", "Memory",
                f"RAM at {perf.ram_percent:.0f}% ({perf.ram_used_gb:.1f}GB / {perf.ram_total_gb:.1f}GB)",
                "System is critically low on memory. OOM killer may activate.",
                "sync && echo 3 | sudo tee /proc/sys/vm/drop_caches"))
        elif perf.ram_percent >= 80:
            issues.append(Issue("HIGH", "Memory",
                f"RAM at {perf.ram_percent:.0f}%",
                "High memory pressure.",
                "ps aux --sort=-%mem | head -10"))
        elif perf.ram_percent >= 65:
            issues.append(Issue("MEDIUM", "Memory",
                f"RAM at {perf.ram_percent:.0f}%",
                "Memory usage is moderate.",
                "watch -n 2 free -h"))

        if perf.swap_total_gb > 0 and perf.swap_percent >= 70:
            issues.append(Issue("HIGH", "Memory",
                f"Swap at {perf.swap_percent:.0f}% ({perf.swap_used_gb:.1f}GB used)",
                "Heavy swap usage indicates memory pressure.",
                "ps aux --sort=-%mem | head -10"))
        elif perf.swap_total_gb == 0 and perf.ram_total_gb < 4:
            issues.append(Issue("MEDIUM", "Memory",
                "No swap configured on a low-RAM system",
                f"System has {perf.ram_total_gb:.1f}GB RAM and no swap — OOM risk.",
                "fallocate -l 4G /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"))

        for disk in perf.disks:
            mp  = disk["mountpoint"]
            pct = disk["percent"]
            if pct >= 95:
                issues.append(Issue("CRITICAL", "Storage",
                    f"Disk {mp} at {pct:.0f}% ({disk['used_gb']:.1f}GB / {disk['total_gb']:.1f}GB)",
                    "Disk is almost full. Writes may fail.",
                    "du -sh /* 2>/dev/null | sort -rh | head -20"))
            elif pct >= 85:
                issues.append(Issue("HIGH", "Storage",
                    f"Disk {mp} at {pct:.0f}%",
                    "Disk space is running low.",
                    "sudo apt-get clean && sudo journalctl --vacuum-size=100M"))
            elif pct >= 70:
                issues.append(Issue("LOW", "Storage",
                    f"Disk {mp} at {pct:.0f}%",
                    "Disk usage is notable.",
                    "ncdu /  (interactive disk analyser)"))

        import multiprocessing
        cpu_count = multiprocessing.cpu_count() or 1
        if perf.load_avg_1 > cpu_count * 2:
            issues.append(Issue("CRITICAL", "CPU",
                f"1-min load average {perf.load_avg_1:.2f} (CPUs: {cpu_count})",
                "System is severely overloaded.",
                "top -b -n1 | head -20"))
        elif perf.load_avg_1 > cpu_count * 1.5:
            issues.append(Issue("HIGH", "CPU",
                f"1-min load average {perf.load_avg_1:.2f}",
                "Load average exceeds CPU capacity.",
                "ps aux --sort=-%cpu | head -15"))

        for sp in suspicious:
            issues.append(Issue("HIGH", "Processes",
                f"Suspicious process: '{sp.name}' (PID {sp.pid})",
                f"Using {sp.cpu_pct:.1f}% CPU, {sp.mem_pct:.1f}% RAM.",
                f"ls -la /proc/{sp.pid}/exe && cat /proc/{sp.pid}/cmdline"))

        for p in [p for p in ports if p.risk == "red"]:
            issues.append(Issue("HIGH", "Security",
                f"High-risk port open: {p.port}/{p.proto} ({p.process})",
                p.note,
                f"sudo ufw deny {p.port}  OR  sudo systemctl stop {p.process}"))

        return issues


# ══════════════════════════════════════════════════════════════════════════════
# 5. WEIGHTED HEALTH SCORER  (NEW v4.1)
#    Weights: CPU 30% · RAM 25% · Disk 20% · Processes 15% · Security 10%
#    Grade:   A 90–100 · B 75–89 · C 60–74 · D 40–59 · F <40
#    Status:  Excellent · Good · Warning · Critical
# ══════════════════════════════════════════════════════════════════════════════

class WeightedHealthScorer:
    # (min_score, grade, status)
    _GRADE_TABLE = [
        (90, "A", "Excellent"),
        (75, "B", "Good"),
        (60, "C", "Warning"),
        (40, "D", "Warning"),
        (0,  "F", "Critical"),
    ]

    # Component weights (must sum to 1.0)
    W_CPU   = 0.30
    W_RAM   = 0.25
    W_DISK  = 0.20
    W_PROC  = 0.15
    W_SEC   = 0.10

    # ── component scorers (each returns 0–100) ────────────────────────────────

    def _score_cpu(self, perf: PerformanceStats) -> float:
        """Higher CPU → lower component score."""
        cpu = perf.cpu_percent
        load_penalty = 0.0
        try:
            import multiprocessing
            cores = multiprocessing.cpu_count() or 1
            ratio = perf.load_avg_1 / cores
            if ratio > 2.0:
                load_penalty = 25
            elif ratio > 1.5:
                load_penalty = 15
            elif ratio > 1.0:
                load_penalty = 8
        except Exception:
            pass

        if cpu >= 90:
            base = 10
        elif cpu >= 75:
            base = 30
        elif cpu >= 50:
            base = 55
        elif cpu >= 25:
            base = 78
        else:
            base = 100

        return max(0.0, base - load_penalty)

    def _score_ram(self, perf: PerformanceStats) -> float:
        ram = perf.ram_percent
        swap_penalty = 0.0
        if perf.swap_total_gb > 0 and perf.swap_percent >= 70:
            swap_penalty = 20
        elif perf.swap_total_gb == 0 and perf.ram_total_gb < 4:
            swap_penalty = 15

        if ram >= 90:
            base = 5
        elif ram >= 80:
            base = 25
        elif ram >= 65:
            base = 55
        elif ram >= 40:
            base = 80
        else:
            base = 100

        return max(0.0, base - swap_penalty)

    def _score_disk(self, perf: PerformanceStats) -> float:
        if not perf.disks:
            return 100.0
        # Score based on worst partition
        worst = max(d["percent"] for d in perf.disks)
        if worst >= 95:
            return 0.0
        elif worst >= 85:
            return 20.0
        elif worst >= 70:
            return 55.0
        elif worst >= 50:
            return 80.0
        return 100.0

    def _score_processes(self, suspicious: List[ProcessInfo]) -> float:
        n = len(suspicious)
        if n == 0:
            return 100.0
        elif n == 1:
            return 60.0
        elif n <= 3:
            return 35.0
        return 10.0

    def _score_security(self, ports: List[PortInfo]) -> float:
        red   = sum(1 for p in ports if p.risk == "red")
        amber = sum(1 for p in ports if p.risk == "amber")
        if red >= 4:
            return 0.0
        elif red == 3:
            return 10.0
        elif red == 2:
            return 25.0
        elif red == 1:
            return 50.0
        elif amber >= 5:
            return 65.0
        elif amber >= 2:
            return 80.0
        return 100.0

    # ── public entry point ────────────────────────────────────────────────────

    def score(
        self,
        perf:       PerformanceStats,
        issues:     List[Issue],
        ports:      List[PortInfo],
        suspicious: List[ProcessInfo],
    ) -> Tuple[int, str, str]:
        """Returns (score 0–100, grade A–F, status label)."""
        cpu_s  = self._score_cpu(perf)
        ram_s  = self._score_ram(perf)
        disk_s = self._score_disk(perf)
        proc_s = self._score_processes(suspicious)
        sec_s  = self._score_security(ports)

        weighted = (
            cpu_s  * self.W_CPU +
            ram_s  * self.W_RAM +
            disk_s * self.W_DISK +
            proc_s * self.W_PROC +
            sec_s  * self.W_SEC
        )

        # Critical-issue penalty (each critical shaves off additional points)
        crit_count = sum(1 for i in issues if i.severity == "CRITICAL")
        high_count = sum(1 for i in issues if i.severity == "HIGH")
        penalty = min(crit_count * 4, 12) + min(high_count * 1.5, 6)
        final = max(0, min(100, round(weighted - penalty)))

        grade = "F"
        status = "Critical"
        for threshold, g, s in self._GRADE_TABLE:
            if final >= threshold:
                grade = g
                status = s
                break

        return final, grade, status

    # expose component breakdown for the report
    def component_breakdown(
        self,
        perf:       PerformanceStats,
        ports:      List[PortInfo],
        suspicious: List[ProcessInfo],
    ) -> Dict[str, float]:
        return {
            "cpu":      round(self._score_cpu(perf), 1),
            "ram":      round(self._score_ram(perf), 1),
            "disk":     round(self._score_disk(perf), 1),
            "processes":round(self._score_processes(suspicious), 1),
            "security": round(self._score_security(ports), 1),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 6. INTELLIGENT RECOMMENDATION ENGINE  (NEW v4.1)
# ══════════════════════════════════════════════════════════════════════════════

class IntelligentRecommendationEngine:
    """
    Produces structured Recommendation objects grouped by:
      Performance · Security · System Cleanup
    Each item includes: problem, solution, impact, command.
    Results are sorted CRITICAL first → LOW last.
    """

    _PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    def generate(
        self,
        info:    SystemInfo,
        perf:    PerformanceStats,
        issues:  List[Issue],
        ports:   List[PortInfo],
        suspicious: List[ProcessInfo],
    ) -> List[Recommendation]:
        recs: List[Recommendation] = []

        # ── PERFORMANCE ───────────────────────────────────────────────────────

        if perf.cpu_percent >= 90:
            recs.append(Recommendation(
                priority = "CRITICAL",
                group    = "Performance",
                problem  = f"CPU is critically overloaded at {perf.cpu_percent:.0f}%.",
                solution = "Identify and terminate runaway processes immediately.",
                impact   = "high",
                command  = "ps aux --sort=-%cpu | head -20",
                rationale= "Sustained 90%+ CPU causes latency spikes and potential crashes.",
            ))
        elif perf.cpu_percent >= 75:
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "Performance",
                problem  = f"CPU usage is elevated at {perf.cpu_percent:.0f}%.",
                solution = "Review the top CPU consumers and consider rescheduling or killing them.",
                impact   = "medium",
                command  = "top -b -n1 | head -25",
            ))

        if perf.cpu_governor not in ("performance", "schedutil", "ondemand"):
            recs.append(Recommendation(
                priority = "MEDIUM",
                group    = "Performance",
                problem  = f"CPU governor is set to '{perf.cpu_governor}' — suboptimal for most workloads.",
                solution = "Switch to 'schedutil' for a balanced performance/power profile.",
                impact   = "medium",
                command  = "echo schedutil | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor",
            ))

        if perf.ram_percent >= 85:
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "Performance",
                problem  = f"RAM is {perf.ram_percent:.0f}% full ({perf.ram_used_gb:.1f}GB / {perf.ram_total_gb:.1f}GB).",
                solution = "Drop the page cache to immediately reclaim memory.",
                impact   = "high",
                command  = "sync && echo 3 | sudo tee /proc/sys/vm/drop_caches",
            ))
        elif perf.ram_percent >= 65:
            recs.append(Recommendation(
                priority = "MEDIUM",
                group    = "Performance",
                problem  = f"RAM usage is moderate at {perf.ram_percent:.0f}%.",
                solution = "Monitor memory trends. Drop caches if usage continues rising.",
                impact   = "medium",
                command  = "free -h && cat /proc/meminfo | grep -i cache",
            ))

        if perf.swap_total_gb > 0 and perf.swap_percent >= 50:
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "Performance",
                problem  = f"Swap is {perf.swap_percent:.0f}% full — system is compensating for RAM pressure.",
                solution = "Reduce the swappiness value and identify high-memory processes.",
                impact   = "high",
                command  = "sudo sysctl -w vm.swappiness=10",
            ))

        if perf.swap_total_gb == 0 and perf.ram_total_gb < 8:
            recs.append(Recommendation(
                priority = "MEDIUM",
                group    = "Performance",
                problem  = f"No swap space configured on a system with only {perf.ram_total_gb:.1f}GB RAM.",
                solution = "Create a 4GB swapfile to act as a safety net against OOM kills.",
                impact   = "medium",
                command  = ("sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile "
                            "&& sudo mkswap /swapfile && sudo swapon /swapfile"),
            ))

        worst_disk = max((d["percent"] for d in perf.disks), default=0)
        if worst_disk >= 90:
            mp = next((d["mountpoint"] for d in perf.disks if d["percent"] == worst_disk), "/")
            recs.append(Recommendation(
                priority = "CRITICAL",
                group    = "System Cleanup",
                problem  = f"Disk partition '{mp}' is {worst_disk:.0f}% full — writes may start failing.",
                solution = "Run a disk audit and remove redundant files, old journals, and package caches.",
                impact   = "high",
                command  = "du -sh /* 2>/dev/null | sort -rh | head -20",
            ))
        elif worst_disk >= 80:
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "System Cleanup",
                problem  = f"Disk usage is high at {worst_disk:.0f}%.",
                solution = "Clean package caches and rotate old logs.",
                impact   = "medium",
                command  = "sudo apt-get clean && sudo journalctl --vacuum-size=100M",
            ))

        # ── SECURITY ──────────────────────────────────────────────────────────

        red_ports = [p for p in ports if p.risk == "red"]
        if red_ports:
            port_list = ", ".join(str(p.port) for p in red_ports[:4])
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "Security",
                problem  = f"High-risk ports are open: {port_list}.",
                solution = "Restrict or close these ports using a firewall unless explicitly required.",
                impact   = "high",
                command  = f"sudo ufw deny {red_ports[0].port}   # repeat for each port",
            ))

        if not shutil.which("ufw") and not shutil.which("firewall-cmd"):
            recs.append(Recommendation(
                priority = "CRITICAL",
                group    = "Security",
                problem  = "No firewall tool detected on this system.",
                solution = "Install and enable UFW to enforce network access controls.",
                impact   = "high",
                command  = "sudo apt install ufw && sudo ufw enable",
            ))

        if not shutil.which("fail2ban-server"):
            recs.append(Recommendation(
                priority = "MEDIUM",
                group    = "Security",
                problem  = "fail2ban is not installed — SSH brute-force attacks are unmitigated.",
                solution = "Install fail2ban to automatically block repeated login failures.",
                impact   = "medium",
                command  = "sudo apt install fail2ban && sudo systemctl enable --now fail2ban",
            ))

        for sp in suspicious:
            recs.append(Recommendation(
                priority = "HIGH",
                group    = "Security",
                problem  = f"Process '{sp.name}' (PID {sp.pid}) is consuming {sp.cpu_pct:.1f}% CPU and is not on the safe list.",
                solution = "Inspect the process binary and command line. Kill if confirmed malicious.",
                impact   = "high",
                command  = f"ls -la /proc/{sp.pid}/exe && kill -9 {sp.pid}  # only after investigation",
            ))

        # ── SYSTEM CLEANUP ────────────────────────────────────────────────────

        rc, out, _ = _run("find /var/log -name '*.gz' -mtime +30 2>/dev/null | wc -l", timeout=8)
        try:
            old_logs = int(out)
            if old_logs > 5:
                recs.append(Recommendation(
                    priority = "LOW",
                    group    = "System Cleanup",
                    problem  = f"{old_logs} compressed log files older than 30 days found in /var/log.",
                    solution = "Remove stale compressed logs to reclaim disk space.",
                    impact   = "low",
                    command  = "sudo find /var/log -name '*.gz' -mtime +30 -delete",
                ))
        except Exception:
            pass

        rc2, tmp_size, _ = _run("du -sm /tmp 2>/dev/null | cut -f1", timeout=5)
        try:
            if int(tmp_size) > 500:
                recs.append(Recommendation(
                    priority = "LOW",
                    group    = "System Cleanup",
                    problem  = f"/tmp is consuming {tmp_size}MB of disk space.",
                    solution = "Clear temporary files to free space and speed up disk I/O.",
                    impact   = "low",
                    command  = "sudo rm -rf /tmp/* /var/tmp/*",
                ))
        except Exception:
            pass

        if not recs:
            recs.append(Recommendation(
                priority = "LOW",
                group    = "Performance",
                problem  = "No significant issues detected.",
                solution = "Continue regular scanning and keep packages up to date.",
                impact   = "low",
                command  = "sudo apt-get update && sudo apt-get upgrade -y",
                rationale= "Proactive maintenance prevents future problems.",
            ))

        # Sort: CRITICAL → HIGH → MEDIUM → LOW, then by group
        recs.sort(key=lambda r: (
            self._PRIORITY_ORDER.get(r.priority, 99),
            r.group,
        ))
        return recs

    def to_simple_list(self, recs: List[Recommendation]) -> List[str]:
        """Backward-compatible: convert to plain string list."""
        icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
        result = []
        for r in recs:
            icon = icons.get(r.priority, "•")
            result.append(
                f"{icon} [{r.group}] {r.problem} → {r.solution}"
            )
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 7. INSIGHT ENGINE  (NEW v4.1)
# ══════════════════════════════════════════════════════════════════════════════

class InsightEngine:
    """Generates plain-English verdicts and a system narrative."""

    def generate(
        self,
        perf:       PerformanceStats,
        issues:     List[Issue],
        ports:      List[PortInfo],
        suspicious: List[ProcessInfo],
        health_score: int,
        status:     str,
    ) -> SystemInsight:
        insight = SystemInsight()

        # ── Performance verdict ───────────────────────────────────────────────
        crit_cpu = perf.cpu_percent >= 85
        crit_ram = perf.ram_percent >= 85
        worst_disk = max((d["percent"] for d in perf.disks), default=0)

        if crit_cpu and crit_ram:
            insight.performance_verdict = (
                "System performance is severely degraded — both CPU and RAM are critically loaded."
            )
        elif crit_cpu:
            insight.performance_verdict = (
                f"System performance is degraded due to high CPU usage ({perf.cpu_percent:.0f}%)."
            )
        elif crit_ram:
            insight.performance_verdict = (
                f"System performance is degraded due to high memory pressure ({perf.ram_percent:.0f}% RAM used)."
            )
        elif worst_disk >= 90:
            insight.performance_verdict = (
                f"System performance may degrade soon — disk is at {worst_disk:.0f}% capacity."
            )
        elif perf.cpu_percent < 30 and perf.ram_percent < 60:
            insight.performance_verdict = "System performance is stable with healthy resource headroom."
        else:
            insight.performance_verdict = "System performance is acceptable but worth monitoring."

        # ── Risk summary ──────────────────────────────────────────────────────
        red_count = sum(1 for p in ports if p.risk == "red")
        no_firewall = not shutil.which("ufw") and not shutil.which("firewall-cmd")

        if red_count >= 3 or (red_count >= 1 and no_firewall):
            insight.risk_summary = (
                f"Significant security risk detected — {red_count} high-risk port(s) open"
                + (" with no active firewall." if no_firewall else ".")
            )
        elif red_count >= 1:
            insight.risk_summary = (
                f"Potential security risk detected — {red_count} high-risk port(s) should be reviewed."
            )
        elif suspicious:
            insight.risk_summary = (
                f"Suspicious process activity detected ({len(suspicious)} process(es)) — investigate immediately."
            )
        elif no_firewall:
            insight.risk_summary = "No firewall is active — system is exposed to network threats."
        else:
            insight.risk_summary = "No immediate security risks detected."

        # ── System summary narrative ──────────────────────────────────────────
        parts = []

        # Resource load narrative
        if perf.cpu_percent >= 75:
            parts.append(f"your system is under high CPU load ({perf.cpu_percent:.0f}%)")
        if perf.ram_percent >= 80:
            parts.append(f"memory is heavily utilised ({perf.ram_percent:.0f}%)")
        if worst_disk >= 85:
            parts.append(f"disk space is critically low ({worst_disk:.0f}%)")
        if suspicious:
            parts.append(f"{len(suspicious)} unrecognised process(es) are consuming significant resources")
        if red_count > 0:
            parts.append(f"{red_count} high-risk network port(s) are open")

        crit_issues = [i for i in issues if i.severity == "CRITICAL"]
        high_issues = [i for i in issues if i.severity == "HIGH"]

        if parts:
            narrative_body = ", and ".join(parts[:3])
            insight.system_summary = (
                f"Your system is {status.lower()}: {narrative_body.capitalize()}. "
                f"{len(crit_issues)} critical and {len(high_issues)} high-severity issue(s) require attention."
            )
        else:
            insight.system_summary = (
                f"Your system is in {status.lower()} condition (score {health_score}/100). "
                "Resource usage is within normal bounds and no critical issues were detected."
            )

        insight.status_label = status
        return insight


# ══════════════════════════════════════════════════════════════════════════════
# 8. MAIN SCAN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ScanEngine:
    def __init__(self):
        self._sys_col   = SystemInfoCollector()
        self._perf_col  = PerformanceCollector()
        self._proc_col  = ProcessCollector()
        self._port_col  = PortCollector()
        self._issues    = IssueDetector()
        self._scorer    = WeightedHealthScorer()
        self._recs      = IntelligentRecommendationEngine()
        self._insight   = InsightEngine()

    def run_full_scan(
        self,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> ScanResult:
        def tick(pct: int, msg: str):
            if progress_cb:
                try:
                    progress_cb(pct, msg)
                except Exception:
                    pass

        result  = ScanResult()
        t_start = time.time()
        result.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        tick(5,  "Collecting system information…")
        result.system_info = self._sys_col.collect()

        tick(20, "Measuring CPU, RAM, and disk performance…")
        result.performance = self._perf_col.collect()

        tick(45, "Profiling processes…")
        result.top_cpu_procs, result.top_mem_procs, result.suspicious_procs = \
            self._proc_col.collect()

        tick(65, "Scanning open network ports…")
        result.open_ports = self._port_col.collect()

        tick(78, "Running issue detection…")
        result.issues = self._issues.detect(
            result.performance,
            result.top_cpu_procs,
            result.suspicious_procs,
            result.open_ports,
        )

        tick(87, "Computing weighted health score…")
        result.health_score, result.health_grade, result.health_status = \
            self._scorer.score(
                result.performance,
                result.issues,
                result.open_ports,
                result.suspicious_procs,
            )

        tick(92, "Generating intelligent recommendations…")
        result.rich_recommendations = self._recs.generate(
            result.system_info,
            result.performance,
            result.issues,
            result.open_ports,
            result.suspicious_procs,
        )
        result.recommendations = self._recs.to_simple_list(result.rich_recommendations)

        tick(97, "Generating system insights…")
        result.insight = self._insight.generate(
            result.performance,
            result.issues,
            result.open_ports,
            result.suspicious_procs,
            result.health_score,
            result.health_status,
        )

        result.duration_s = round(time.time() - t_start, 2)
        tick(100, (
            f"Scan complete in {result.duration_s}s — "
            f"Score {result.health_score}/100 · Grade {result.health_grade} · {result.health_status}"
        ))
        return result


# ══════════════════════════════════════════════════════════════════════════════
# 9. ENHANCED REPORT GENERATOR  (NEW v4.1)
#    Sections: EXECUTIVE SUMMARY · HEALTH SCORE · ISSUES · RECOMMENDATIONS
#              COMMAND SUGGESTIONS · SYSTEM INFORMATION · PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

class ReportGenerator:
    def __init__(self, result: ScanResult):
        self.r = result
        self._scorer = WeightedHealthScorer()

    def _divider(self, char: str = "═", width: int = 76) -> str:
        return char * width

    def _section(self, title: str, char: str = "═", width: int = 76) -> str:
        bar = char * width
        return f"\n{bar}\n  {title.upper()}\n{bar}\n"

    def _sub_section(self, title: str, width: int = 76) -> str:
        return f"\n  ─{'─' * (len(title) + 2)}─\n  {title}\n  ─{'─' * (len(title) + 2)}─"

    # ── TXT ──────────────────────────────────────────────────────────────────

    def as_txt(self) -> str:
        r   = self.r
        W   = 76
        out = []

        # ── HEADER ────────────────────────────────────────────────────────────
        out += [
            "═" * W,
            "  JENIX v4.1 — Intelligent System Scan Report".center(W),
            f"  Generated: {r.timestamp}  ·  Duration: {r.duration_s}s".center(W),
            f"  Host: {r.system_info.hostname}  ·  OS: {r.system_info.os_name.split('(')[0].strip()}".center(W),
            "═" * W,
        ]

        # ── EXECUTIVE SUMMARY ─────────────────────────────────────────────────
        out.append(self._section("1 · Executive Summary"))
        out += [
            f"  Status   : {r.health_status.upper()}",
            f"  Score    : {r.health_score}/100  (Grade {r.health_grade})",
            f"  Issues   : {len(r.issues)} total  "
            f"({sum(1 for i in r.issues if i.severity=='CRITICAL')} critical  ·  "
            f"{sum(1 for i in r.issues if i.severity=='HIGH')} high  ·  "
            f"{sum(1 for i in r.issues if i.severity=='MEDIUM')} medium)",
            "",
            "  SYSTEM OVERVIEW",
            f"  {r.insight.system_summary}",
            "",
            "  PERFORMANCE VERDICT",
            f"  {r.insight.performance_verdict}",
            "",
            "  SECURITY OVERVIEW",
            f"  {r.insight.risk_summary}",
        ]

        # ── HEALTH SCORE ──────────────────────────────────────────────────────
        out.append(self._section("2 · Health Score  (Weighted)"))

        score_bar = ("█" * (r.health_score // 10)).ljust(10, "░")
        grade_desc = {
            "A": "Excellent — system is in great shape",
            "B": "Good — minor improvements possible",
            "C": "Warning — attention recommended",
            "D": "Poor — multiple issues need addressing",
            "F": "Critical — immediate action required",
        }.get(r.health_grade, "")

        out += [
            f"  Overall Score  :  {r.health_score:3d} / 100   [{score_bar}]   Grade {r.health_grade}",
            f"  Status         :  {r.health_status}",
            f"  Meaning        :  {grade_desc}",
            "",
            "  COMPONENT BREAKDOWN  (Weights: CPU 30% · RAM 25% · Disk 20% · Processes 15% · Security 10%)",
        ]

        breakdown = self._scorer.component_breakdown(
            r.performance, r.open_ports, r.suspicious_procs
        )
        weights = {"cpu": 30, "ram": 25, "disk": 20, "processes": 15, "security": 10}
        labels  = {"cpu": "CPU", "ram": "RAM", "disk": "Disk",
                   "processes": "Processes", "security": "Security"}
        for key in ("cpu", "ram", "disk", "processes", "security"):
            val  = breakdown[key]
            w    = weights[key]
            bar  = ("█" * int(val / 10)).ljust(10, "░")
            flag = " ← needs attention" if val < 50 else ""
            out.append(
                f"  {labels[key]:<12} ({w:2d}%)  {val:5.1f}/100  [{bar}]{flag}"
            )

        # ── ISSUES ────────────────────────────────────────────────────────────
        out.append(self._section(f"3 · Issues  ({len(r.issues)} detected)"))

        if not r.issues:
            out.append("  ✓  No issues detected. System looks healthy.")
        else:
            sev_order  = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            sev_icons  = {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH",
                          "MEDIUM":   "🟡 MEDIUM",   "LOW":  "🟢 LOW"}
            for sev in sev_order:
                grp = [i for i in r.issues if i.severity == sev]
                if not grp:
                    continue
                out += ["", f"  {sev_icons[sev]}  ({len(grp)} issue(s)):", "  " + "─" * 60]
                for issue in grp:
                    out += [
                        f"  ▸ [{issue.category}] {issue.title}",
                        f"    {issue.detail}",
                    ]
                    if issue.fix_hint:
                        out.append(f"    Suggested command:  {issue.fix_hint}")
                    out.append("")

        # ── RECOMMENDATIONS ───────────────────────────────────────────────────
        out.append(self._section(f"4 · Recommendations  ({len(r.rich_recommendations)} items)"))

        if r.rich_recommendations:
            current_group = None
            for idx, rec in enumerate(r.rich_recommendations, 1):
                if rec.group != current_group:
                    current_group = rec.group
                    out += ["", f"  ── {current_group.upper()} ──", ""]
                icon_map = {
                    "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"
                }
                icon = icon_map.get(rec.priority, "•")
                out += [
                    f"  {idx:02d}. {icon} [{rec.priority}]  {rec.problem}",
                    f"      Solution : {rec.solution}",
                    f"      Impact   : {rec.impact.upper()}",
                ]
                if rec.command:
                    out.append(f"      Command  : {rec.command}")
                if rec.rationale:
                    out.append(f"      Note     : {rec.rationale}")
                out.append("")

        # ── COMMAND SUGGESTIONS ───────────────────────────────────────────────
        out.append(self._section("5 · Command Suggestions  (review before running)"))
        out += [
            "  The following commands were suggested based on detected issues.",
            "  ⚠  JENIX never executes these automatically. Review each carefully.",
            "",
        ]

        cmds_seen: set = set()
        has_cmds = False
        for rec in r.rich_recommendations:
            if rec.command and rec.command not in cmds_seen:
                cmds_seen.add(rec.command)
                icon_map = {
                    "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"
                }
                out += [
                    f"  [{rec.priority}] {rec.problem[:60]}",
                    f"  $ {rec.command}",
                    "",
                ]
                has_cmds = True
        if not has_cmds:
            out.append("  No specific commands suggested at this time.")

        # ── SYSTEM INFORMATION ────────────────────────────────────────────────
        si = r.system_info
        out.append(self._section("6 · System Information"))
        out += [
            f"  Hostname       : {si.hostname}",
            f"  OS             : {si.os_name}",
            f"  Kernel         : {si.kernel_version}",
            f"  Architecture   : {si.architecture}",
            f"  Boot Time      : {si.boot_time}",
            f"  Uptime         : {si.uptime_str}",
            f"  CPU Model      : {si.cpu_model}",
            f"  CPU Cores      : {si.cpu_cores} physical / {si.cpu_threads} logical",
            f"  Total RAM      : {si.total_ram_gb} GB",
            f"  Python         : {si.python_version}",
        ]

        # ── PERFORMANCE ───────────────────────────────────────────────────────
        p = r.performance
        out.append(self._section("7 · Performance Details"))
        out += [
            f"  CPU Usage      : {p.cpu_percent:.1f}%",
            f"  CPU Frequency  : {p.cpu_freq_mhz:.0f} MHz",
            f"  CPU Governor   : {p.cpu_governor}",
            f"  Load Average   : {p.load_avg_1:.2f}  {p.load_avg_5:.2f}  {p.load_avg_15:.2f}  (1/5/15 min)",
            f"  RAM Used       : {p.ram_used_gb:.2f} GB / {p.ram_total_gb:.2f} GB  ({p.ram_percent:.0f}%)",
            f"  RAM Available  : {p.ram_available_gb:.2f} GB",
            f"  Swap Used      : {p.swap_used_gb:.2f} GB / {p.swap_total_gb:.2f} GB  ({p.swap_percent:.0f}%)",
            "",
            "  DISK PARTITIONS:",
        ]
        for d in p.disks:
            bar  = ("█" * int(d["percent"] / 10)).ljust(10, "░")
            flag = " ← LOW SPACE" if d["percent"] >= 85 else ""
            out.append(
                f"    {d['mountpoint']:20s}  {d['used_gb']:6.1f}GB / {d['total_gb']:6.1f}GB  "
                f"[{bar}] {d['percent']:.0f}%{flag}"
            )

        # ── TOP PROCESSES ─────────────────────────────────────────────────────
        out.append(self._section("8 · Top Processes"))
        out.append("  TOP CPU CONSUMERS:")
        for i, proc in enumerate(r.top_cpu_procs, 1):
            out.append(
                f"    {i}. {proc.name:<22s}  PID {proc.pid:6d}  "
                f"CPU {proc.cpu_pct:5.1f}%  MEM {proc.mem_mb:7.1f}MB  [{proc.user}]"
            )
        out.append("\n  TOP MEMORY CONSUMERS:")
        for i, proc in enumerate(r.top_mem_procs, 1):
            out.append(
                f"    {i}. {proc.name:<22s}  PID {proc.pid:6d}  "
                f"MEM {proc.mem_pct:5.2f}%  ({proc.mem_mb:7.1f}MB)  [{proc.user}]"
            )
        if r.suspicious_procs:
            out.append("\n  ⚠  SUSPICIOUS PROCESSES:")
            for sp in r.suspicious_procs:
                out.append(
                    f"    !! {sp.name:<20s}  PID {sp.pid:6d}  "
                    f"CPU {sp.cpu_pct:5.1f}%  [{sp.user}]  — investigate"
                )
        else:
            out.append("\n  ✓  No suspicious processes detected.")

        # ── OPEN PORTS ────────────────────────────────────────────────────────
        out.append(self._section(f"9 · Open Ports  ({len(r.open_ports)} found)"))
        if r.open_ports:
            out.append(f"  {'PORT':<8} {'PROTO':<6} {'SERVICE':<18} {'RISK':<8} NOTE")
            out.append("  " + "─" * 70)
            for port in r.open_ports:
                risk_icon = {"red": "▲▲▲", "amber": "◆◆ ", "green": "●  "}.get(port.risk, "?  ")
                out.append(
                    f"  {port.port:<8} {port.proto:<6} {port.process:<18} "
                    f"{risk_icon} {port.risk.upper():<6}  {port.note}"
                )
        else:
            out.append("  No open ports detected or scan unavailable.")

        # ── FOOTER ────────────────────────────────────────────────────────────
        out += [
            "",
            "═" * W,
            f"  JENIX v4.1  ·  Scan completed: {r.timestamp}  ·  Score {r.health_score}/100  ·  Grade {r.health_grade}".center(W),
            "═" * W,
            "",
        ]

        return "\n".join(out)

    def write_txt(self, path: str) -> str:
        Path(path).write_text(self.as_txt(), encoding="utf-8")
        return path

    # ── JSON ─────────────────────────────────────────────────────────────────

    def as_dict(self) -> dict:
        r = self.r
        breakdown = self._scorer.component_breakdown(
            r.performance, r.open_ports, r.suspicious_procs
        )
        return {
            "jenix_version":   "4.1",
            "timestamp":       r.timestamp,
            "duration_s":      r.duration_s,
            "health_score":    r.health_score,
            "health_grade":    r.health_grade,
            "health_status":   r.health_status,
            "score_breakdown": breakdown,
            "insight": {
                "system_summary":      r.insight.system_summary,
                "performance_verdict": r.insight.performance_verdict,
                "risk_summary":        r.insight.risk_summary,
                "status_label":        r.insight.status_label,
            },
            "system_info":     asdict(r.system_info),
            "performance":     asdict(r.performance),
            "top_cpu_processes":    [asdict(p) for p in r.top_cpu_procs],
            "top_mem_processes":    [asdict(p) for p in r.top_mem_procs],
            "suspicious_processes": [asdict(p) for p in r.suspicious_procs],
            "open_ports":           [asdict(p) for p in r.open_ports],
            "issues":               [asdict(i) for i in r.issues],
            "issue_summary": {
                "CRITICAL": sum(1 for i in r.issues if i.severity == "CRITICAL"),
                "HIGH":     sum(1 for i in r.issues if i.severity == "HIGH"),
                "MEDIUM":   sum(1 for i in r.issues if i.severity == "MEDIUM"),
                "LOW":      sum(1 for i in r.issues if i.severity == "LOW"),
            },
            "recommendations": [
                {
                    "priority": rec.priority,
                    "group":    rec.group,
                    "problem":  rec.problem,
                    "solution": rec.solution,
                    "impact":   rec.impact,
                    "command":  rec.command,
                    "rationale":rec.rationale,
                }
                for rec in r.rich_recommendations
            ],
            "simple_recommendations": r.recommendations,
        }

    def write_json(self, path: str) -> str:
        Path(path).write_text(
            json.dumps(self.as_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
