# ai_engine.py — JENIX AI Advisor Backend
# Handles: System analysis, recommendations, priority classification, fix detection, clean targets

import subprocess, re, shutil, logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Callable, Tuple

log = logging.getLogger("jenix.ai")


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: str, timeout: int = 15) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


# ── constants ─────────────────────────────────────────────────────────────────

PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

# Tool: (binary_to_check, apt_pkg, dnf_pkg, pacman_pkg, description, category, priority)
RECOMMENDED_TOOLS = [
    ("htop",         "htop",           "htop",           "htop",           "Interactive process viewer",             "Tools",       "Medium"),
    ("iotop",        "iotop",          "iotop",          "iotop",          "Real-time disk I/O monitor",             "Tools",       "Medium"),
    ("ncdu",         "ncdu",           "ncdu",           "ncdu",           "Interactive disk usage analyser",        "Tools",       "Medium"),
    ("smartctl",     "smartmontools",  "smartmontools",  "smartmontools",  "S.M.A.R.T. disk health monitoring",     "Storage",     "High"),
    ("fail2ban-server","fail2ban",     "fail2ban",       "fail2ban",       "SSH brute-force prevention",            "Security",    "High"),
    ("rkhunter",     "rkhunter",       "rkhunter",       "rkhunter",       "Rootkit detection scanner",             "Security",    "Medium"),
    ("rsync",        "rsync",          "rsync",          "rsync",          "Incremental backup tool",               "Tools",       "Medium"),
    ("timeshift",    "timeshift",      "timeshift",      "timeshift",      "System snapshot and restore",           "Tools",       "High"),
    ("ufw",          "ufw",            "ufw",            "ufw",            "Simple firewall management",            "Security",    "High"),
    ("lynis",        "lynis",          "lynis",          "lynis",          "Security auditing and hardening",       "Security",    "Medium"),
    ("nethogs",      "nethogs",        "nethogs",        "nethogs",        "Per-process network bandwidth",         "Tools",       "Low"),
    ("mtr",          "mtr",            "mtr",            "mtr",            "Network diagnostic (traceroute+ping)",  "Network",     "Low"),
]

# (path, description, clean_cmd, safe_to_auto_clean)
CLEAN_TARGETS_TEMPLATE = [
    ("Package cache",   "/var/cache/apt /var/cache/dnf /var/cache/pacman/pkg", True),
    ("Temp files",      "/tmp /var/tmp",                                        True),
    ("User cache",      "~/.cache",                                             True),
    ("Journal logs",    "/var/log/journal",                                     True),
    ("Crash reports",   "/var/crash",                                           True),
    ("Thumbnail cache", "~/.cache/thumbnails",                                  True),
]


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class Recommendation:
    priority:  str    # Critical | High | Medium | Low
    category:  str    # Security | Performance | Packages | Storage | Network | Health | Tools
    title:     str
    detail:    str
    command:   str    = ""
    safe:      bool   = True
    source:    str    = ""   # which check generated this

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class FixIssue:
    severity:   str   # critical | high | medium | low
    category:   str
    title:      str
    detail:     str
    fix_cmd:    str
    revert_cmd: str   = ""
    fixed:      bool  = False

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class CleanTarget:
    name:      str
    paths:     str
    size_mb:   float
    file_count: int
    clean_cmd: str
    safe:      bool
    selected:  bool = True

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class SystemProfile:
    distro_name:    str    = "Unknown"
    distro_family:  str    = "unknown"
    kernel:         str    = ""
    arch:           str    = ""
    cpu_model:      str    = ""
    cpu_cores:      int    = 0
    ram_total_gb:   float  = 0.0
    ram_used_pct:   float  = 0.0
    swap_total_gb:  float  = 0.0
    has_ssd:        bool   = False
    has_nvidia_gpu: bool   = False
    boot_time_s:    Optional[float] = None
    uptime_s:       int    = 0
    pkg_manager:    str    = "apt"

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class AnalysisReport:
    profile:         SystemProfile
    recommendations: List[Recommendation] = field(default_factory=list)
    fix_issues:      List[FixIssue]       = field(default_factory=list)
    clean_targets:   List[CleanTarget]    = field(default_factory=list)
    health_score:    int                  = 100
    summary:         dict                 = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "profile":         self.profile.to_dict(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "fix_issues":      [f.to_dict() for f in self.fix_issues],
            "clean_targets":   [c.to_dict() for c in self.clean_targets],
            "health_score":    self.health_score,
            "summary":         self.summary,
        }


# ── AIEngine ──────────────────────────────────────────────────────────────────

class AIEngine:
    """
    Backend engine for AI-driven system analysis.
    All methods return structured dicts — no GUI, no printing.

    Usage:
        engine = AIEngine()
        report = engine.full_analysis()
        print(report.to_dict())
    """

    def __init__(self, distro_family: str = ""):
        self._family = distro_family or self._detect_family()

    # ── analyze_system ────────────────────────────────────────────────────────

    def analyze_system(self) -> dict:
        """
        Collect CPU, memory, and disk metrics and return a health assessment.

        Scoring logic:
          - Starts at 100
          - CPU > 85% → −20 (Critical), > 70% → −10 (High), > 50% → −5 (Medium)
          - RAM > 90% → −20 (Critical), > 80% → −10 (High), > 65% → −5 (Medium)
          - Any disk > 90% → −20 (Critical), > 80% → −10 (High), > 70% → −5 (Medium)

        Returns:
            {
                "health_score":    int (0–100),
                "issues":          list of str,
                "recommendations": list of str,
                "metrics":         dict  (cpu_pct, ram_pct, disks),
            }
        """
        issues          = []
        recommendations = []
        deductions      = 0

        # ── CPU ──────────────────────────────────────────────────────────────
        cpu_pct = 0.0
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=0.5)
        except ImportError:
            rc, out, _ = _run("grep 'cpu ' /proc/stat", timeout=3)
            # single-snapshot approximation (not idle %) — just read load avg
            rc2, load_out, _ = _run("cat /proc/loadavg", timeout=3)
            try:
                cores = 1
                rc3, c_out, _ = _run("nproc", timeout=3)
                if rc3 == 0 and c_out.isdigit():
                    cores = int(c_out)
                load1 = float(load_out.split()[0])
                cpu_pct = min(100.0, round(load1 / cores * 100, 1))
            except Exception:
                cpu_pct = 0.0

        if cpu_pct > 85:
            issues.append(f"CPU usage critical: {cpu_pct:.0f}%")
            recommendations.append("Enable Gaming Mode to kill non-essential apps and free CPU cycles")
            deductions += 20
        elif cpu_pct > 70:
            issues.append(f"CPU usage high: {cpu_pct:.0f}%")
            recommendations.append("Enable Gaming Mode to prioritise foreground performance")
            deductions += 10
        elif cpu_pct > 50:
            issues.append(f"CPU usage elevated: {cpu_pct:.0f}%")
            recommendations.append("Close unused applications to reduce CPU load")
            deductions += 5

        # ── RAM ──────────────────────────────────────────────────────────────
        ram_pct = 0.0
        ram_total_gb = 0.0
        try:
            import psutil
            mem = psutil.virtual_memory()
            ram_pct      = mem.percent
            ram_total_gb = round(mem.total / 1024**3, 1)
        except ImportError:
            rc, out, _ = _run("free -b", timeout=3)
            for line in (out or "").splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    try:
                        total = int(parts[1])
                        used  = int(parts[2])
                        ram_pct      = round(used / total * 100, 1) if total else 0.0
                        ram_total_gb = round(total / 1024**3, 1)
                    except (IndexError, ValueError, ZeroDivisionError):
                        pass
                    break

        if ram_pct > 90:
            issues.append(f"RAM usage critical: {ram_pct:.0f}%")
            recommendations.append("Run Deep Clean to free memory immediately")
            deductions += 20
        elif ram_pct > 80:
            issues.append(f"RAM usage high: {ram_pct:.0f}%")
            recommendations.append("Run Deep Clean or Work Mode to recover memory")
            deductions += 10
        elif ram_pct > 65:
            issues.append(f"RAM usage elevated: {ram_pct:.0f}%")
            recommendations.append("Consider closing background applications")
            deductions += 5

        # ── Disk ─────────────────────────────────────────────────────────────
        disk_info = []
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_info.append({
                        "mountpoint": part.mountpoint,
                        "percent":    usage.percent,
                        "used_gb":    round(usage.used  / 1024**3, 1),
                        "total_gb":   round(usage.total / 1024**3, 1),
                        "free_gb":    round(usage.free  / 1024**3, 1),
                    })
                except (PermissionError, OSError):
                    continue
        except ImportError:
            rc, out, _ = _run("df -BG --output=target,pcent,size,used,avail 2>/dev/null", timeout=8)
            for line in (out or "").splitlines()[1:]:
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    disk_info.append({
                        "mountpoint": parts[0],
                        "percent":    float(parts[1].rstrip("%")),
                        "total_gb":   float(parts[2].rstrip("G")),
                        "used_gb":    float(parts[3].rstrip("G")),
                        "free_gb":    float(parts[4].rstrip("G")),
                    })
                except (ValueError, IndexError):
                    continue

        worst_disk_pct = 0.0
        for disk in disk_info:
            pct = disk["percent"]
            worst_disk_pct = max(worst_disk_pct, pct)
            if pct >= 90:
                issues.append(
                    f"Disk '{disk['mountpoint']}' almost full: {pct:.0f}% "
                    f"({disk['free_gb']:.1f} GB free)"
                )
                recommendations.append(
                    f"Clear cache on '{disk['mountpoint']}' — run Deep Clean"
                )
                deductions += 20
            elif pct >= 80:
                issues.append(
                    f"Disk '{disk['mountpoint']}' running low: {pct:.0f}% used"
                )
                recommendations.append(
                    "Run Deep Clean to recover disk space"
                )
                deductions += 10
            elif pct >= 70:
                issues.append(
                    f"Disk '{disk['mountpoint']}' at {pct:.0f}% capacity"
                )
                recommendations.append("Consider clearing package cache and old logs")
                deductions += 5

        # ── Health score ──────────────────────────────────────────────────────
        health_score = max(0, min(100, 100 - deductions))

        # ── Smart mode suggestion ─────────────────────────────────────────────
        if cpu_pct > 70 and ram_pct < 70:
            recommendations.insert(0, "💡 Best Mode: Gaming Mode — CPU is bottleneck")
        elif ram_pct > 75 or worst_disk_pct > 80:
            recommendations.insert(0, "💡 Best Mode: Deep Clean — memory/disk pressure detected")
        elif cpu_pct > 40 or ram_pct > 50:
            recommendations.insert(0, "💡 Best Mode: Work Mode — light optimisation recommended")

        log.info(
            f"analyze_system → score={health_score}, "
            f"cpu={cpu_pct:.0f}%, ram={ram_pct:.0f}%, issues={len(issues)}"
        )

        return {
            "health_score":    health_score,
            "issues":          issues,
            "recommendations": recommendations,
            "metrics": {
                "cpu_percent":    cpu_pct,
                "ram_percent":    ram_pct,
                "ram_total_gb":   ram_total_gb,
                "disks":          disk_info,
                "worst_disk_pct": worst_disk_pct,
            },
        }

    # ── real-time monitor ─────────────────────────────────────────────────────

    def monitor_loop(
        self,
        interval: float = 5.0,
        iterations: int = 0,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """
        Simple real-time monitoring loop.

        Refreshes stats every *interval* seconds.
        If *callback* is provided, it is called with the latest analysis dict.
        If *iterations* is 0, loops indefinitely until interrupted.

        Args:
            interval:   Seconds between refreshes.
            iterations: Number of iterations (0 = infinite).
            callback:   Optional function called with each analysis result.
        """
        import time as _time

        count = 0
        try:
            while True:
                result = self.analyze_system()
                if callback:
                    try:
                        callback(result)
                    except Exception as cb_exc:
                        log.warning(f"monitor_loop callback error: {cb_exc}")
                count += 1
                if iterations > 0 and count >= iterations:
                    break
                _time.sleep(interval)
        except KeyboardInterrupt:
            log.info("monitor_loop interrupted by user")

    # ── full analysis ─────────────────────────────────────────────────────────

    def full_analysis(
        self, progress_cb: Optional[Callable[[str], None]] = None
    ) -> AnalysisReport:
        """
        Run complete system analysis.
        Returns AnalysisReport with recommendations, fix issues, and clean targets.
        """
        if progress_cb: progress_cb("Building system profile…")
        profile = self.build_system_profile()

        report = AnalysisReport(profile=profile)

        if progress_cb: progress_cb("Checking security…")
        report.recommendations += self._check_security(profile)

        if progress_cb: progress_cb("Checking performance…")
        report.recommendations += self._check_performance(profile)

        if progress_cb: progress_cb("Checking packages…")
        report.recommendations += self._check_packages(profile)
        report.fix_issues       = self._detect_fix_issues(profile)

        if progress_cb: progress_cb("Scanning clean targets…")
        report.clean_targets = self._scan_clean_targets(profile)

        if progress_cb: progress_cb("Running tool checks…")
        report.recommendations += self._check_missing_tools(profile)

        if progress_cb: progress_cb("Distro-specific checks…")
        report.recommendations += self._check_distro_specific(profile)

        # sort and score
        report.recommendations.sort(
            key=lambda r: (PRIORITY_ORDER.get(r.priority, 99), r.category)
        )
        report.health_score = self._compute_health_score(report)
        report.summary      = self._build_summary(report)

        log.info(
            f"AI analysis complete: {len(report.recommendations)} recs, "
            f"{len(report.fix_issues)} fix issues, score={report.health_score}"
        )
        return report

    # ── system profile ────────────────────────────────────────────────────────

    def build_system_profile(self) -> SystemProfile:
        """Collect hardware, OS, and runtime information."""
        import platform
        profile = SystemProfile()

        try:
            import distro as _dl
            profile.distro_name   = _dl.name(pretty=True) or "Unknown"
            profile.distro_family = self._family
        except ImportError:
            profile.distro_name   = platform.platform()
            profile.distro_family = self._family

        profile.kernel = platform.release()
        profile.arch   = platform.machine()

        # CPU
        rc, out, _ = _run("lscpu 2>/dev/null", timeout=5)
        for line in out.splitlines():
            if "Model name" in line:
                profile.cpu_model = line.split(":", 1)[1].strip()
            if re.match(r"^CPU\(s\):", line):
                try: profile.cpu_cores = int(line.split(":")[1].strip())
                except: pass

        # RAM
        try:
            import psutil
            mem = psutil.virtual_memory()
            profile.ram_total_gb = round(mem.total / 1024**3, 2)
            profile.ram_used_pct = mem.percent
            swap = psutil.swap_memory()
            profile.swap_total_gb = round(swap.total / 1024**3, 2)
        except ImportError:
            rc, out, _ = _run("free -b 2>/dev/null", timeout=3)
            for line in out.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    try:
                        profile.ram_total_gb = round(int(parts[1]) / 1024**3, 2)
                        profile.ram_used_pct = round(int(parts[2]) / int(parts[1]) * 100, 1)
                    except: pass

        # SSD detection
        rc, out, _ = _run("lsblk -d -o name,rota 2>/dev/null | grep ' 0'", timeout=5)
        profile.has_ssd = bool(out)

        # NVIDIA GPU
        rc, out, _ = _run("lspci 2>/dev/null | grep -i nvidia", timeout=5)
        profile.has_nvidia_gpu = rc == 0 and bool(out)

        # Boot time
        rc, out, _ = _run("systemd-analyze time 2>/dev/null", timeout=8)
        m = re.search(r"reached after ([\d.]+)s", out)
        if not m:
            m = re.search(r"reached after ([\d.]+)min", out)
            if m: profile.boot_time_s = float(m.group(1)) * 60
        else:
            profile.boot_time_s = float(m.group(1))

        # Uptime
        try:
            import psutil, time
            profile.uptime_s = int(time.time() - psutil.boot_time())
        except: pass

        # Package manager
        pm_map = {"debian": "apt", "fedora": "dnf", "arch": "pacman", "suse": "zypper"}
        profile.pkg_manager = pm_map.get(self._family, "apt")

        return profile

    # ── recommendation checks ─────────────────────────────────────────────────

    def _check_security(self, profile: SystemProfile) -> List[Recommendation]:
        recs = []

        # Firewall
        fw_active = False
        if shutil.which("ufw"):
            rc, out, _ = _run("sudo ufw status 2>/dev/null", timeout=5)
            fw_active = "active" in out.lower()
        elif shutil.which("firewall-cmd"):
            rc, out, _ = _run("sudo firewall-cmd --state 2>/dev/null", timeout=5)
            fw_active = "running" in out.lower()

        if not fw_active:
            fw_cmd = ("sudo ufw enable" if shutil.which("ufw")
                      else "sudo systemctl enable --now firewalld"
                      if shutil.which("firewall-cmd") else "")
            if fw_cmd:
                recs.append(Recommendation(
                    "Critical", "Security", "No active firewall",
                    "System has no enforced firewall rules — all ports are unprotected.",
                    fw_cmd, source="firewall_check",
                ))

        # SSH config
        try:
            try:
                cfg = open("/etc/ssh/sshd_config").read()
            except PermissionError:
                rc, cfg, _ = _run("sudo cat /etc/ssh/sshd_config 2>/dev/null", timeout=5)
            except FileNotFoundError:
                cfg = ""

            SSH_RISKS = [
                (r"^PermitRootLogin\s+yes", "Critical", "SSH root login enabled",
                 "Allows direct root brute-force over SSH.",
                 "sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config "
                 "&& sudo systemctl restart sshd", False),
                (r"^PasswordAuthentication\s+yes", "High", "SSH password auth enabled",
                 "Password-based SSH is vulnerable to brute-force attacks. Use key auth.",
                 "# Edit /etc/ssh/sshd_config: set PasswordAuthentication no", False),
                (r"^PermitEmptyPasswords\s+yes", "Critical", "SSH empty passwords allowed",
                 "Accounts with blank passwords are remotely accessible.",
                 "# Edit /etc/ssh/sshd_config: set PermitEmptyPasswords no", False),
            ]
            for pattern, priority, title, detail, cmd, safe in SSH_RISKS:
                if re.search(pattern, cfg, re.MULTILINE | re.IGNORECASE):
                    recs.append(Recommendation(
                        priority, "Security", title, detail, cmd, safe,
                        source="ssh_check",
                    ))
        except Exception:
            pass

        # Distro-specific security
        if profile.distro_family == "debian":
            if not shutil.which("unattended-upgrade"):
                recs.append(Recommendation(
                    "Medium", "Security", "Auto security updates not configured",
                    "unattended-upgrades installs security patches automatically.",
                    "sudo apt install -y unattended-upgrades && "
                    "sudo dpkg-reconfigure -plow unattended-upgrades",
                    source="auto_updates",
                ))

        return recs

    def _check_performance(self, profile: SystemProfile) -> List[Recommendation]:
        recs = []

        # CPU
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu > 85:
                recs.append(Recommendation("Critical", "Performance",
                    f"CPU load critical ({cpu:.0f}%)",
                    "System is severely overloaded. Identify runaway processes.",
                    "ps aux --sort=-%cpu | head -15", source="cpu_check"))
            elif cpu > 70:
                recs.append(Recommendation("High", "Performance",
                    f"CPU load high ({cpu:.0f}%)",
                    "Sustained high CPU usage degrades responsiveness.",
                    "ps aux --sort=-%cpu | head -10", source="cpu_check"))
        except ImportError:
            pass

        # RAM
        if profile.ram_used_pct > 90:
            recs.append(Recommendation("Critical", "Performance",
                f"RAM usage critical ({profile.ram_used_pct:.0f}%)",
                "Risk of OOM kills and application crashes.",
                "ps aux --sort=-%mem | head -10", source="ram_check"))
        elif profile.ram_used_pct > 80:
            recs.append(Recommendation("High", "Performance",
                f"RAM usage high ({profile.ram_used_pct:.0f}%)",
                "High memory pressure. Consider adding swap.",
                "free -h && swapon --show", source="ram_check"))

        # Swap
        if profile.swap_total_gb == 0 and profile.ram_total_gb < 8:
            recs.append(Recommendation("High", "Performance",
                f"No swap on low-RAM system ({profile.ram_total_gb:.1f} GB RAM)",
                "Without swap, low-memory conditions cause OOM crashes.",
                "sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile "
                "&& sudo mkswap /swapfile && sudo swapon /swapfile",
                source="swap_check"))

        # Swappiness
        rc, out, _ = _run("cat /proc/sys/vm/swappiness", timeout=3)
        if rc == 0 and out.isdigit() and int(out) > 30:
            recs.append(Recommendation("Medium", "Performance",
                f"vm.swappiness too high ({out})",
                "High swappiness causes excessive disk swapping on SSD/fast RAM systems.",
                "sudo sysctl -w vm.swappiness=10 && "
                "echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf",
                source="swappiness_check"))

        # SSD TRIM
        if profile.has_ssd:
            timer_rc, timer_out, _ = _run(
                "systemctl is-enabled fstrim.timer 2>/dev/null", timeout=3)
            fstab_rc, fstab_out, _ = _run(
                "grep -i discard /etc/fstab 2>/dev/null", timeout=3)
            if "enabled" not in timer_out and not fstab_out:
                recs.append(Recommendation("Medium", "Storage",
                    "SSD TRIM not scheduled",
                    "Weekly fstrim maintains SSD write performance and lifespan.",
                    "sudo systemctl enable --now fstrim.timer",
                    source="ssd_trim_check"))

        # Boot time
        if profile.boot_time_s and profile.boot_time_s > 30:
            recs.append(Recommendation("Medium", "Performance",
                f"Slow boot time ({profile.boot_time_s:.0f}s)",
                "Identify slow systemd units to reduce boot time.",
                "systemd-analyze blame | head -15",
                source="boot_check"))

        # Disk usage
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    if u.percent >= 90:
                        recs.append(Recommendation("Critical", "Storage",
                            f"Disk '{part.mountpoint}' at {u.percent:.0f}%",
                            f"Nearly full ({u.used // 1024**3}GB / {u.total // 1024**3}GB). "
                            "System may fail to write logs or crash.",
                            f"sudo du -sh {part.mountpoint}/* 2>/dev/null | sort -rh | head -10",
                            False, source="disk_check"))
                    elif u.percent >= 80:
                        recs.append(Recommendation("High", "Storage",
                            f"Disk '{part.mountpoint}' at {u.percent:.0f}%",
                            f"Low disk space ({u.free // 1024**3}GB free). Plan cleanup.",
                            f"ncdu {part.mountpoint}",
                            source="disk_check"))
                except PermissionError:
                    pass
        except ImportError:
            pass

        # CPU temperature
        rc, temp_out, _ = _run(
            "sensors -A 2>/dev/null | grep -iE 'Package id 0|Tdie|CPU Temp'", timeout=5)
        m = re.search(r"[+]?([\d.]+)°C", temp_out)
        if m:
            t = float(m.group(1))
            if t > 90:
                recs.append(Recommendation("Critical", "Health",
                    f"CPU temperature critical ({t:.0f}°C)",
                    "CPU is dangerously hot. Check cooling immediately.",
                    "sensors", False, source="temp_check"))
            elif t > 80:
                recs.append(Recommendation("High", "Health",
                    f"CPU temperature very high ({t:.0f}°C)",
                    "Above safe range for most CPUs. Check fan operation.",
                    "watch -n 2 sensors", source="temp_check"))
            elif t > 70:
                recs.append(Recommendation("Medium", "Health",
                    f"CPU temperature elevated ({t:.0f}°C)",
                    "Monitor for spikes and ensure adequate case ventilation.",
                    "sensors", source="temp_check"))

        return recs

    def _check_packages(self, profile: SystemProfile) -> List[Recommendation]:
        recs = []
        pm = profile.pkg_manager

        if pm == "apt":
            recs.append(Recommendation("High", "Packages", "Run full system update",
                "Keep packages updated to patch security vulnerabilities.",
                "sudo apt update && sudo apt upgrade -y",
                source="update_check"))
            rc, out, _ = _run("apt-get check 2>&1", timeout=10)
            if rc != 0 and re.search(r"broken|unmet", out, re.IGNORECASE):
                recs.append(Recommendation("Critical", "Packages", "Broken APT dependencies",
                    "Broken packages may prevent updates and cause instability.",
                    "sudo apt --fix-broken install",
                    source="broken_pkg_check"))
            rc2, out2, _ = _run("dpkg -l | grep -cE '^.H|^.F|^iF' 2>/dev/null", timeout=5)
            if rc2 == 0 and out2.isdigit() and int(out2) > 0:
                recs.append(Recommendation("Critical", "Packages",
                    f"{out2} half-installed packages",
                    "Half-installed packages corrupt the package database.",
                    "sudo dpkg --configure -a && sudo apt --fix-broken install",
                    source="dpkg_check"))

        elif pm == "dnf":
            recs.append(Recommendation("High", "Packages", "Run full system update",
                "Apply security and feature updates.",
                "sudo dnf upgrade -y", source="update_check"))

        elif pm == "pacman":
            recs.append(Recommendation("High", "Packages", "Run full system update",
                "Apply all available updates from Arch repositories.",
                "sudo pacman -Syu", source="update_check"))

        return recs

    # ── fix issue detection ───────────────────────────────────────────────────

    def _detect_fix_issues(self, profile: SystemProfile) -> List[FixIssue]:
        """Detect actionable issues that can be automatically fixed."""
        issues = []
        pm = profile.pkg_manager

        # Broken packages
        if pm == "apt":
            rc, out, _ = _run("apt-get check 2>&1", timeout=10)
            if rc != 0:
                issues.append(FixIssue("critical", "Packages",
                    "Broken APT package state",
                    out[:200] if out else "APT check failed",
                    "sudo apt --fix-broken install -y",
                    "sudo apt update"))
        elif pm == "pacman":
            rc, out, _ = _run("pacman -Qdt 2>/dev/null | wc -l", timeout=8)
            if rc == 0 and out.isdigit() and int(out) > 0:
                issues.append(FixIssue("medium", "Packages",
                    f"{out} orphaned pacman packages",
                    "Orphaned packages waste disk space.",
                    "sudo pacman -Rns $(pacman -Qdtq) --noconfirm",
                    ""))

        # Disk pressure
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    if u.percent >= 90:
                        clean_cmd = {"apt":"sudo apt clean && sudo apt autoremove -y",
                                     "dnf":"sudo dnf clean all","pacman":"sudo pacman -Sc --noconfirm"
                                     }.get(pm, "sudo apt clean")
                        issues.append(FixIssue("critical", "Storage",
                            f"Disk '{part.mountpoint}' at {u.percent:.0f}%",
                            f"{u.used//1024**3}GB used of {u.total//1024**3}GB total",
                            clean_cmd, ""))
                except PermissionError:
                    pass
        except ImportError:
            pass

        # RAM pressure
        if profile.ram_used_pct > 85:
            issues.append(FixIssue("high", "Memory",
                f"RAM at {profile.ram_used_pct:.0f}%",
                f"System is using {profile.ram_used_pct:.0f}% of available RAM.",
                "sync && echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null",
                ""))

        # Zombie processes
        rc, out, _ = _run("ps aux | awk '$8==\"Z\"' | grep -v STAT | wc -l", timeout=5)
        try:
            zombies = int(out) - 1
            if zombies > 2:
                issues.append(FixIssue("medium", "Processes",
                    f"{zombies} zombie processes",
                    "Zombies accumulate PID table entries and indicate process bugs.",
                    "# Reboot recommended to clear zombie processes", ""))
        except (ValueError, TypeError):
            pass

        # Swappiness
        rc, out, _ = _run("cat /proc/sys/vm/swappiness", timeout=3)
        if rc == 0 and out.isdigit() and int(out) > 30:
            issues.append(FixIssue("medium", "Performance",
                f"Swappiness too high ({out})",
                "Recommended value for SSD systems: ≤10",
                f"sudo sysctl -w vm.swappiness=10 && "
                f"echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf",
                f"sudo sysctl -w vm.swappiness={out}"))

        # Firewall
        fw_active = False
        if shutil.which("ufw"):
            rc, out, _ = _run("sudo ufw status 2>/dev/null", timeout=5)
            fw_active = "active" in out.lower()
        if not fw_active:
            cmd = "sudo ufw enable" if shutil.which("ufw") else \
                  "sudo systemctl enable --now firewalld" if shutil.which("firewall-cmd") else ""
            if cmd:
                issues.append(FixIssue("critical", "Security",
                    "No active firewall",
                    "System has no enforced firewall rules.",
                    cmd, ""))

        issues.sort(key=lambda i: (
            {"critical":0,"high":1,"medium":2,"low":3}.get(i.severity, 4), i.category
        ))
        return issues

    # ── clean targets ─────────────────────────────────────────────────────────

    def _scan_clean_targets(self, profile: SystemProfile) -> List[CleanTarget]:
        """Scan the system for cleanable files and return CleanTarget list."""
        from pathlib import Path as _Path
        targets = []

        pm_clean = {"apt":    "sudo apt-get clean && sudo apt-get autoclean",
                    "dnf":    "sudo dnf clean all",
                    "pacman": "sudo pacman -Sc --noconfirm",
                    "zypper": "sudo zypper clean --all"}.get(profile.pkg_manager, "sudo apt-get clean")

        raw_targets = [
            ("Package cache",    "/var/cache/apt /var/cache/dnf /var/cache/pacman/pkg", pm_clean,         True),
            ("Temp files",       "/tmp /var/tmp",  "sudo rm -rf /tmp/* /var/tmp/* 2>/dev/null||true",     True),
            ("User cache",       str(_Path.home()/".cache"),
             "rm -rf ~/.cache/mozilla ~/.cache/google-chrome ~/.cache/chromium 2>/dev/null||true",         True),
            ("Journal logs",     "/var/log/journal","sudo journalctl --vacuum-size=100M",                  True),
            ("Crash reports",    "/var/crash",      "sudo rm -rf /var/crash/* 2>/dev/null||true",          True),
            ("Thumbnail cache",  str(_Path.home()/".cache/thumbnails"),
             "rm -rf ~/.cache/thumbnails/* 2>/dev/null||true",                                             True),
        ]

        for name, paths, cmd, safe in raw_targets:
            total_mb = 0.0
            total_count = 0
            for p in paths.split():
                real_p = p.replace("~", str(_Path.home()))
                if _Path(real_p).exists():
                    rc, sz, _ = _run(f"du -sm {real_p} 2>/dev/null | cut -f1", timeout=8)
                    rc2, cnt, _ = _run(f"find {real_p} -type f 2>/dev/null | wc -l", timeout=8)
                    try: total_mb += float(sz) if rc == 0 else 0
                    except: pass
                    try: total_count += int(cnt) if rc2 == 0 else 0
                    except: pass
            targets.append(CleanTarget(
                name=name, paths=paths, size_mb=round(total_mb, 1),
                file_count=total_count, clean_cmd=cmd, safe=safe
            ))

        # Orphaned packages
        orphan_cmd = {"apt":    "deborphan 2>/dev/null",
                      "dnf":    "package-cleanup --leaves 2>/dev/null",
                      "pacman": "pacman -Qdt 2>/dev/null"}.get(profile.pkg_manager, "")
        if orphan_cmd:
            rc, out, _ = _run(orphan_cmd, timeout=15)
            count = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0
            if count > 0:
                pm_remove = {"apt":    "sudo apt-get autoremove --purge -y",
                             "dnf":    "sudo dnf autoremove -y",
                             "pacman": "sudo pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null||true"
                             }.get(profile.pkg_manager, "sudo apt-get autoremove --purge -y")
                targets.append(CleanTarget(
                    name="Orphaned packages", paths="", size_mb=0.0,
                    file_count=count, clean_cmd=pm_remove, safe=True
                ))

        # Old log archives
        rc, out, _ = _run("find /var/log -name '*.gz' -mtime +30 2>/dev/null | wc -l", timeout=8)
        try:
            old_logs = int(out)
        except (ValueError, TypeError):
            old_logs = 0
        if old_logs > 0:
            rc2, sz_out, _ = _run(
                "find /var/log -name '*.gz' -mtime +30 2>/dev/null | "
                "xargs du -sc 2>/dev/null | tail -1 | cut -f1", timeout=8)
            try: log_mb = int(sz_out) / 1024
            except: log_mb = 0.0
            targets.append(CleanTarget(
                name="Old compressed logs", paths="/var/log",
                size_mb=round(log_mb, 1), file_count=old_logs,
                clean_cmd="sudo find /var/log -name '*.gz' -mtime +30 -delete 2>/dev/null||true",
                safe=True
            ))

        return targets

    # ── missing tools ─────────────────────────────────────────────────────────

    def _check_missing_tools(self, profile: SystemProfile) -> List[Recommendation]:
        recs = []
        pm = profile.pkg_manager
        pkg_idx = {"apt": 1, "dnf": 2, "pacman": 3, "zypper": 1}.get(pm, 1)

        for binary, apt_pkg, dnf_pkg, pacman_pkg, desc, cat, priority in RECOMMENDED_TOOLS:
            if shutil.which(binary.split("-")[0]):
                continue
            pkg_map = {1: apt_pkg, 2: dnf_pkg, 3: pacman_pkg}
            pkg_name = pkg_map.get(pkg_idx, apt_pkg)
            install_cmds = {
                "apt":    f"sudo apt-get install -y {pkg_name}",
                "dnf":    f"sudo dnf install -y {pkg_name}",
                "pacman": f"sudo pacman -S --noconfirm {pkg_name}",
                "zypper": f"sudo zypper install -y {pkg_name}",
            }
            recs.append(Recommendation(
                priority, cat, f"'{binary.split('-')[0]}' not installed",
                desc, install_cmds.get(pm, f"sudo apt-get install -y {pkg_name}"),
                source="tool_check",
            ))
        return recs

    # ── distro-specific checks ────────────────────────────────────────────────

    def _check_distro_specific(self, profile: SystemProfile) -> List[Recommendation]:
        recs = []
        family = profile.distro_family

        if family == "arch":
            if not shutil.which("yay") and not shutil.which("paru"):
                recs.append(Recommendation("Low", "Tools", "No AUR helper installed",
                    "yay or paru lets you install community packages from the AUR.",
                    "git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si",
                    source="arch_check"))
            if not shutil.which("reflector"):
                recs.append(Recommendation("Low", "Performance", "'reflector' not installed",
                    "Automatically selects the fastest Arch mirrors for downloads.",
                    "sudo pacman -S --noconfirm reflector",
                    source="arch_check"))

        elif family == "fedora":
            if not shutil.which("semanage"):
                recs.append(Recommendation("Medium", "Security",
                    "SELinux management tools missing",
                    "policycoreutils-python-utils provides semanage and other tools.",
                    "sudo dnf install -y policycoreutils-python-utils",
                    source="fedora_check"))

        if profile.has_nvidia_gpu:
            if not shutil.which("gamemode"):
                recs.append(Recommendation("Low", "Performance",
                    "GameMode not installed (NVIDIA GPU detected)",
                    "GameMode optimises CPU governor and GPU settings during gaming.",
                    {"apt":"sudo apt-get install -y gamemode",
                     "dnf":"sudo dnf install -y gamemode",
                     "pacman":"sudo pacman -S --noconfirm gamemode",
                     "zypper":"sudo zypper install -y gamemode"}.get(profile.pkg_manager,
                     "sudo apt-get install -y gamemode"),
                    source="nvidia_check"))

        return recs

    # ── scoring ───────────────────────────────────────────────────────────────

    def _compute_health_score(self, report: AnalysisReport) -> int:
        score = 100
        for rec in report.recommendations:
            score -= {"Critical": 18, "High": 8, "Medium": 3, "Low": 1}.get(rec.priority, 0)
        for issue in report.fix_issues:
            score -= {"critical": 15, "high": 8, "medium": 3, "low": 1}.get(issue.severity, 0)
        return max(0, min(100, score))

    def _build_summary(self, report: AnalysisReport) -> dict:
        by_priority: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for r in report.recommendations:
            by_priority[r.priority]  = by_priority.get(r.priority, 0) + 1
            by_category[r.category]  = by_category.get(r.category, 0) + 1
        total_clean_mb = sum(c.size_mb for c in report.clean_targets)
        critical_fix = sum(1 for i in report.fix_issues if i.severity == "critical")
        return {
            "health_score":       report.health_score,
            "grade":              "A" if report.health_score >= 90 else
                                  "B" if report.health_score >= 75 else
                                  "C" if report.health_score >= 55 else "D",
            "total_recs":         len(report.recommendations),
            "by_priority":        by_priority,
            "by_category":        by_category,
            "fix_issues":         len(report.fix_issues),
            "critical_fixes":     critical_fix,
            "cleanable_mb":       round(total_clean_mb, 1),
            "distro":             report.profile.distro_name,
            "pkg_manager":        report.profile.pkg_manager,
        }

    # ── quick lookups ─────────────────────────────────────────────────────────

    def get_recommendations_by_priority(
        self, recs: List[Recommendation], priority: str
    ) -> List[Recommendation]:
        return [r for r in recs if r.priority == priority]

    def get_recommendations_by_category(
        self, recs: List[Recommendation], category: str
    ) -> List[Recommendation]:
        return [r for r in recs if r.category == category]

    def filter_safe(self, recs: List[Recommendation]) -> List[Recommendation]:
        return [r for r in recs if r.safe]

    # ── distro detection ──────────────────────────────────────────────────────

    @staticmethod
    def _detect_family() -> str:
        try:
            import distro as _dl
            id_like = (_dl.id() + " " + _dl.like()).lower()
        except ImportError:
            id_like = ""
            for p in ("/etc/os-release", "/usr/lib/os-release"):
                try:
                    for line in open(p):
                        if line.startswith("ID_LIKE=") or line.startswith("ID="):
                            id_like = line.split("=", 1)[1].strip().strip('"').lower()
                            break
                    if id_like:
                        break
                except OSError:
                    pass

        if any(k in id_like for k in ("ubuntu","debian","mint","pop","kali","elementary")):
            return "debian"
        if any(k in id_like for k in ("fedora","rhel","centos","almalinux","rocky")):
            return "fedora"
        if any(k in id_like for k in ("arch","manjaro","endeavour","garuda","artix")):
            return "arch"
        if any(k in id_like for k in ("suse","opensuse","leap","tumbleweed")):
            return "suse"
        return "debian"   # safe default


# ── module-level singleton ────────────────────────────────────────────────────

ai_engine = AIEngine()


# ── standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    engine = AIEngine()

    print("=== System Profile ===")
    profile = engine.build_system_profile()
    print(json.dumps(profile.to_dict(), indent=2))

    print("\n=== Full Analysis ===")
    def cb(msg): print(f"  → {msg}")
    report = engine.full_analysis(progress_cb=cb)

    print(f"\nHealth Score: {report.health_score}/100  (Grade: {report.summary.get('grade')})")
    print(f"Recommendations: {len(report.recommendations)}")
    print(f"Fix Issues:      {len(report.fix_issues)}")
    print(f"Clean Targets:   {len(report.clean_targets)}  ({report.summary.get('cleanable_mb')} MB)")

    print("\n=== analyze_system() ===")
    result = engine.analyze_system()
    print(json.dumps(result, indent=2))

    print("\n=== Top Recommendations ===")
    for r in report.recommendations[:6]:
        print(f"  [{r.priority:8s}] [{r.category:12s}] {r.title}")

    print("\n=== Fix Issues ===")
    for i in report.fix_issues:
        print(f"  [{i.severity:8s}] [{i.category:10s}] {i.title}")

    print("\n=== Clean Targets ===")
    for c in report.clean_targets:
        print(f"  {c.name:<28} {c.size_mb:>8.1f} MB  {c.file_count:>6} files")
