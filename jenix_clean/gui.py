#!/usr/bin/env python3
# JENIX v4.2 Enterprise — Production-Grade Linux Optimization Framework
# pip install customtkinter psutil matplotlib distro

import subprocess, sys, os, re, shutil, threading, time, json, logging, hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List, Dict, Tuple, Any
from dataclasses import dataclass, field, asdict

# ── bootstrap distro ──────────────────────────────────────────────────────────
def _bootstrap():
    try:
        import distro; return
    except ImportError: pass
    for cmd in [[sys.executable,"-m","pip","install","--quiet","distro"],
                ["pip3","install","--quiet","distro"]]:
        try:
            if subprocess.run(cmd,capture_output=True,timeout=60).returncode==0: return
        except: pass
_bootstrap()

import customtkinter as ctk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

try:
    import distro as _distro_lib; _HAS_DISTRO=True
except ImportError:
    _HAS_DISTRO=False
import weakref as _weakref
 
_APP_REF = None   # weakref.ref to JenixApp — set in JenixApp.__init__
 
 
def _get_app():
    """
    Safely dereference the weakref to JenixApp.
    Returns the live app instance, or None if it has been garbage-collected
    or its Tk window is already destroyed.
    """
    if _APP_REF is None:
        return None
    try:
        app = _APP_REF()
        if app is not None and app.winfo_exists():
            return app
    except Exception:
        pass
    return None
 
 
def safe_animate(widget, value):
    try:
        if widget and widget.winfo_exists():
            widget.animate(value)
    except Exception:
        pass
 
 
def safe_after(widget, delay, func, *args):
    try:
        if widget and widget.winfo_exists():
            if args:
                widget.after(delay, func, *args)
            else:
                widget.after(delay, func)
    except Exception:
        pass
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 ── LOGGING & PATHS

import logging as _logging
from pathlib import Path

LOG_DIR = Path.home() / ".jenix" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = LOG_DIR / "audit.log"

log = _logging.getLogger("jenix")
log.setLevel(_logging.DEBUG)

_fh = _logging.FileHandler(AUDIT_LOG)
_fh.setFormatter(_logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(_fh)

_ch = _logging.StreamHandler()
_ch.setFormatter(_logging.Formatter("[%(levelname)s] %(message)s"))
log.addHandler(_ch)


def _log(level: str, msg: str):
    """
    Log to file/stdout AND route to the real-time log panel.
    Uses a weakref so _log() never prevents JenixApp from being GC'd.
    Safe to call from any thread.
    """
    getattr(log, level.lower(), log.info)(msg)
 
    app = _get_app()
    if app is not None:
        try:
            level_upper = level.upper()
            # Always schedule on the main thread — Tk is not thread-safe
            app.after(0, lambda m=msg, lv=level_upper: _route_to_rt_log(app, m, lv))
        except Exception:
            pass
 
 

def _route_to_rt_log(app_ref: "JenixApp", level: str, msg: str):
    """Called on the main thread; pushes a message into rt_log if it exists."""
    try:
        if app_ref is None:
            return
        if not app_ref.winfo_exists():
            return
        rt = getattr(app_ref, "rt_log", None)
        if rt is not None and hasattr(rt, "log"):
            rt.log(msg, level)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 ── DISTRO ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class DistroEngine:
    DEBIAN="debian"; FEDORA="fedora"; ARCH="arch"; SUSE="suse"; UNKNOWN="unknown"

    def __init__(self):
        self.name="Unknown"; self.version=""; self.family=self.UNKNOWN
        self._detect()
        _log("info", f"Distro: {self.name} | Family: {self.family}")

    def _detect(self):
        if _HAS_DISTRO:
            self.name    = _distro_lib.name(pretty=True) or "Unknown"
            self.version = _distro_lib.version() or ""
            id_like = (_distro_lib.id()+" "+_distro_lib.like()).lower()
        else:
            id_like=self._read_os_release(); self.name=id_like.split()[0].capitalize() if id_like else "Unknown"
        for k in ("ubuntu","debian","mint","pop","kali","elementary","zorin","raspbian"):
            if k in id_like: self.family=self.DEBIAN; return
        for k in ("fedora","rhel","centos","almalinux","rocky","oracle"):
            if k in id_like: self.family=self.FEDORA; return
        for k in ("arch","manjaro","endeavour","garuda","artix"):
            if k in id_like: self.family=self.ARCH; return
        for k in ("suse","opensuse","leap","tumbleweed"):
            if k in id_like: self.family=self.SUSE; return

    @staticmethod
    def _read_os_release():
        for p in ("/etc/os-release","/usr/lib/os-release"):
            try:
                for line in open(p):
                    if line.startswith("ID_LIKE=") or line.startswith("ID="):
                        return line.split("=",1)[1].strip().strip('"').lower()
            except: pass
        return ""

    @property
    def update(self):
        return {self.DEBIAN:"sudo apt-get update -qq",self.FEDORA:"sudo dnf check-update -q",
                self.ARCH:"sudo pacman -Sy --noconfirm",self.SUSE:"sudo zypper refresh -q"}.get(self.family,"echo unsupported")
    @property
    def upgrade(self):
        return {self.DEBIAN:"sudo apt-get upgrade -y",self.FEDORA:"sudo dnf upgrade -y",
                self.ARCH:"sudo pacman -Su --noconfirm",self.SUSE:"sudo zypper update -y"}.get(self.family,"echo unsupported")
    @property
    def fix_broken(self):
        return {self.DEBIAN:"sudo apt-get --fix-broken install -y",self.FEDORA:"sudo dnf distro-sync -y",
                self.ARCH:"sudo pacman -Syuu --noconfirm",self.SUSE:"sudo zypper verify -y"}.get(self.family,"echo unsupported")
    @property
    def autoremove(self):
        return {self.DEBIAN:"sudo apt-get autoremove --purge -y",self.FEDORA:"sudo dnf autoremove -y",
                self.ARCH:"sudo pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null||true",
                self.SUSE:"sudo zypper packages --unneeded|awk 'NR>4{print $5}'|xargs sudo zypper remove -y 2>/dev/null||true"
                }.get(self.family,"echo unsupported")
    @property
    def clean_cache(self):
        return {self.DEBIAN:"sudo apt-get clean && sudo apt-get autoclean",
                self.FEDORA:"sudo dnf clean all",self.ARCH:"sudo pacman -Sc --noconfirm",
                self.SUSE:"sudo zypper clean --all"}.get(self.family,"echo unsupported")
    @property
    def list_upgradable(self):
        return {self.DEBIAN:"apt list --upgradable 2>/dev/null",self.FEDORA:"dnf check-update -q 2>/dev/null",
                self.ARCH:"pacman -Qu 2>/dev/null",self.SUSE:"zypper list-updates 2>/dev/null"}.get(self.family,"echo")
    @property
    def list_orphans(self):
        return {self.DEBIAN:"deborphan 2>/dev/null",self.FEDORA:"package-cleanup --leaves 2>/dev/null",
                self.ARCH:"pacman -Qdt 2>/dev/null",self.SUSE:"zypper packages --unneeded 2>/dev/null"}.get(self.family,"echo")

    def install(self, pkg: str) -> str:
        return {self.DEBIAN:f"sudo apt-get install -y {pkg}",
                self.FEDORA:f"sudo dnf install -y {pkg}",
                self.ARCH:f"sudo pacman -S --noconfirm {pkg}",
                self.SUSE:f"sudo zypper install -y {pkg}"}.get(self.family,f"echo unsupported: {pkg}")

    @property
    def is_supported(self):
        return self.family != self.UNKNOWN

    @property
    def label(self):
        return f"{self.name} [{self.family}]"


# ── global distro instance ────────────────────────────────────────────────────
distro = DistroEngine()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 ── COMMAND RUNNER
# ══════════════════════════════════════════════════════════════════════════════
def run(cmd, timeout: int = 60, shell: bool = True):
    label = cmd if isinstance(cmd, str) else " ".join(cmd)
    _log("info", f"EXEC: {label[:100]}")
    try:
        r = subprocess.run(
            cmd, shell=shell, capture_output=True,
            text=True, timeout=timeout)
        if r.returncode != 0:
            _log("warning", f"rc={r.returncode}: {r.stderr[:80]}")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        _log("error", f"TIMEOUT: {label[:80]}")
        return -1, "", "timeout"
    except Exception as e:
        _log("error", str(e))
        return -2, "", str(e)


def run_pkg(action: str, pkg: str, timeout: int = 120):
    _pkg = pkg.strip()
    if not re.fullmatch(r"[a-zA-Z0-9_.+\-]+", _pkg):
        _log("error", f"run_pkg: rejected unsafe package name: {_pkg!r}")
        return -3, "", f"Unsafe package name: {_pkg!r}"

    _CMDS = {
        DistroEngine.DEBIAN: {
            "install": ["sudo", "apt-get", "install", "-y", _pkg],
            "remove":  ["sudo", "apt-get", "remove",  "-y", _pkg],
        },
        DistroEngine.FEDORA: {
            "install": ["sudo", "dnf", "install", "-y", _pkg],
            "remove":  ["sudo", "dnf", "remove",  "-y", _pkg],
        },
        DistroEngine.ARCH: {
            "install": ["sudo", "pacman", "-S", "--noconfirm", _pkg],
            "remove":  ["sudo", "pacman", "-R", "--noconfirm", _pkg],
        },
        DistroEngine.SUSE: {
            "install": ["sudo", "zypper", "install", "-y", _pkg],
            "remove":  ["sudo", "zypper", "remove",  "-y", _pkg],
        },
    }
    family_cmds = _CMDS.get(distro.family)
    if family_cmds is None:
        return -4, "", f"Unsupported distro family: {distro.family}"
    cmd_list = family_cmds.get(action)
    if cmd_list is None:
        return -5, "", f"Unknown action: {action}"

    return run(cmd_list, timeout=timeout, shell=False)


def run_bg(cmd, on_done=None, timeout: int = 120):
    def _worker():
        rc, out, err = run(cmd, timeout=timeout)
        if on_done:
            on_done(rc, out, err)
    threading.Thread(target=_worker, daemon=True).start()


# SECTION 4 ── ROLLBACK ENGINE
# ══════════════════════════════════════════════════════════════════════════════
try:
    from core.rollback_engine import RollbackEngine
    _log("info", "RollbackEngine loaded from core.rollback_engine")
except ImportError:
    try:
        import importlib, sys as _sys
        _spec = importlib.util.spec_from_file_location(
            "rollback_engine",
            Path(__file__).parent / "core" / "rollback_engine.py",
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        RollbackEngine = _mod.RollbackEngine
        _log("info", "RollbackEngine loaded via path fallback")
    except Exception as _e:
        _log("error", f"Could not import RollbackEngine: {_e}. Using stub.")

        class RollbackEngine:
            def __init__(self): self._entries = []
            def record(self, *a, **kw): return ""
            def snapshot_packages(self, label="", **kw):
                return {"status": "failed", "message": "RollbackEngine unavailable", "path": ""}
            def revert(self, *a, **kw):
                from dataclasses import dataclass
                @dataclass
                class _R: entry_id=""; description=""; success=False; output=""; error="stub"
                return _R()
            def revert_all(self, *a, **kw): return []
            def clear(self): pass
            @property
            def entries(self): return []
            @property
            def pending(self): return []
            @property
            def count(self): return 0
            @property
            def has_history(self): return False

rollback = RollbackEngine()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4b ── FIX ENGINE INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════
try:
    from fix_engine import FixEngine, ExecutionSummary, FixPlan
    _HAS_FIX_ENGINE = True
    _log("info", "FixEngine loaded successfully")
except ImportError as _fe:
    _HAS_FIX_ENGINE = False
    _log("warning", f"FixEngine not available: {_fe}")

    class ExecutionSummary:
        def __init__(self):
            self.total_fixes=0; self.applied=0; self.failed=0; self.skipped=0
            self.smart_message="FixEngine not available"; self.system_improvement="N/A"
            self.results=[]; self.dry_run=True; self.aborted_early=False; self.abort_reason=""
        def as_json(self): return json.dumps({"error":"FixEngine not available"}, indent=2)

    class FixPlan:
        pass

    class FixEngine:
        def __init__(self, confirm_fn=None): pass
        def plan_fixes(self, scan_result): return []
        def apply_fix(self, fix_id, params=None, dry_run=True): return None
        def apply_all_fixes(self, scan_result, dry_run=True, confirm_all=False):
            return ExecutionSummary()
        def generate_fix_report(self, summary, section_number=10): return "FixEngine unavailable"
        def generate_fix_report_json(self, summary): return {}
        def rollback_fix(self, key): return None
        def list_available_rollbacks(self): return []
        def read_audit_log(self, n=50): return ""

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 ── SECURITY SCAN ENGINE
# ══════════════════════════════════════════════════════════════════════════════
PORT_DB: Dict[int,Tuple[str,str,str]] = {
    20:("FTP-Data","File Transfer data channel","red"),
    21:("FTP","Unencrypted file transfer — credentials exposed","red"),
    22:("SSH","Encrypted remote shell — generally safe","green"),
    23:("Telnet","DANGEROUS — sends passwords in plain text","red"),
    25:("SMTP","Mail transfer — may relay spam if misconfigured","amber"),
    53:("DNS","Domain resolver — open resolver = DDoS risk","amber"),
    67:("DHCP-S","DHCP server — should be internal only","amber"),
    68:("DHCP-C","DHCP client — normal","green"),
    80:("HTTP","Unencrypted web — consider redirecting to HTTPS","amber"),
    110:("POP3","Email retrieval — unencrypted","amber"),
    111:("RPC","Portmapper — exploitable if exposed","amber"),
    143:("IMAP","Email access — unencrypted variant","amber"),
    443:("HTTPS","Encrypted web — safe","green"),
    445:("SMB","Windows shares — EternalBlue target, very risky","red"),
    631:("CUPS","Printer daemon — low risk if local","green"),
    993:("IMAPS","Encrypted IMAP — safe","green"),
    995:("POP3S","Encrypted POP3 — safe","green"),
    1194:("OpenVPN","VPN — safe if intentional","green"),
    1433:("MSSQL","Microsoft SQL Server — never expose publicly","red"),
    3306:("MySQL","Database — bind to 127.0.0.1 only","red"),
    3389:("RDP","Remote Desktop — ransomware entry point","red"),
    5432:("PostgreSQL","Database — should not be public","amber"),
    5900:("VNC","Remote desktop — often unencrypted","red"),
    6379:("Redis","In-memory DB — no auth by default","red"),
    8080:("HTTP-Alt","Dev server or proxy","amber"),
    8443:("HTTPS-Alt","Alternative HTTPS","green"),
    9200:("Elasticsearch","Search engine REST API — no auth by default","red"),
    27017:("MongoDB","Database — no auth by default in older versions","red"),
}

@dataclass
class PortResult:
    port:     int
    proto:    str
    service:  str
    pid:      Optional[int]
    process:  str
    risk:     str
    note:     str

class SecurityScanner:
    def scan_ports(self, progress_cb:Callable=None) -> List[PortResult]:
        if progress_cb: progress_cb("Running port scan…")
        results: List[PortResult] = []
        seen: set = set()

        if shutil.which("ss"):
            rc,out,_ = run("ss -tulnp 2>/dev/null", timeout=10)
        elif shutil.which("netstat"):
            rc,out,_ = run("netstat -tulnp 2>/dev/null", timeout=10)
        else:
            rc,out=-1,""

        if progress_cb: progress_cb("Parsing port data…")
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts)<5: continue
            proto = parts[0].lower().rstrip("46")
            local = parts[4] if shutil.which("ss") else parts[3]
            port_str = local.rsplit(":",1)[-1]
            try: port_num=int(port_str)
            except: continue
            if port_num in seen: continue
            seen.add(port_num)

            pid=None; proc_name="unknown"
            pid_m = re.search(r'pid=(\d+)',line)
            if pid_m: pid=int(pid_m.group(1))
            proc_m = re.search(r'"([^"]+)"',line)
            if proc_m: proc_name=proc_m.group(1)
            elif pid:
                rc2,pn,_ = run(f"ps -p {pid} -o comm= 2>/dev/null",timeout=3)
                if rc2==0 and pn: proc_name=pn

            known = PORT_DB.get(port_num)
            svc   = known[0] if known else proc_name
            note  = known[1] if known else f"Unknown service on port {port_num}"
            risk  = known[2] if known else "amber"

            if port_num > 49152: risk="green"
            if port_num in (22,80,443,631): risk="green"

            results.append(PortResult(
                port=port_num, proto=proto, service=svc,
                pid=pid, process=proc_name, risk=risk, note=note
            ))

        results.sort(key=lambda x:({"red":0,"amber":1,"green":2}.get(x.risk,3),x.port))
        _log("info",f"Security scan: {len(results)} ports found")
        return results

    def check_ssh(self) -> List[Tuple[str,str,str]]:
        findings = []
        try:
            cfg = Path("/etc/ssh/sshd_config").read_text()
        except:
            rc,cfg,_=run("sudo cat /etc/ssh/sshd_config 2>/dev/null",timeout=5)
            if rc!=0: return findings
        checks = [
            (r"^PermitRootLogin\s+yes","SSH root login enabled","red"),
            (r"^PasswordAuthentication\s+yes","SSH password auth enabled (brute-force risk)","amber"),
            (r"^X11Forwarding\s+yes","X11 forwarding enabled (info leakage risk)","amber"),
            (r"^PermitEmptyPasswords\s+yes","Empty passwords permitted — CRITICAL","red"),
        ]
        for pattern,msg,risk in checks:
            if re.search(pattern,cfg,re.MULTILINE|re.IGNORECASE):
                findings.append((msg,risk,pattern))
        return findings

    def check_firewall(self) -> Tuple[bool,str]:
        if shutil.which("ufw"):
            rc,out,_ = run("sudo ufw status 2>/dev/null",timeout=5)
            active = "active" in out.lower()
            return active, out
        if shutil.which("firewall-cmd"):
            rc,out,_ = run("sudo firewall-cmd --state 2>/dev/null",timeout=5)
            return "running" in out.lower(), out
        rc,out,_ = run("sudo iptables -L -n 2>/dev/null|head -5",timeout=5)
        return bool(out), out

    def check_suid(self) -> List[str]:
        rc,out,_ = run(
            "find /usr /bin /sbin -perm -4000 -type f 2>/dev/null | head -20", timeout=15)
        if rc==0 and out:
            return out.splitlines()
        return []

    def check_world_writable(self) -> int:
        rc,out,_ = run(
            "find /tmp /var/tmp -perm -0002 -type f 2>/dev/null | wc -l", timeout=10)
        try: return int(out)
        except: return 0

security_scanner = SecurityScanner()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 ── BOOST ENGINE
# ══════════════════════════════════════════════════════════════════════════════
SAFE_PROCS = {
    "systemd","init","kthreadd","kworker","ksoftirqd","migration","rcu_sched",
    "watchdog","cpuhp","kswapd","kdevtmpfs","kauditd","khugepaged","kintegrityd",
    "NetworkManager","dbus-daemon","polkitd","sshd","cron","rsyslogd","journald",
    "dockerd","containerd","postgres","mysql","nginx","apache","ufw","fail2ban"
}

@dataclass
class BoostTask:
    name:    str
    cmd:     str
    revert:  Optional[str]
    desc:    str
    mode:    str

GAMING_TASKS: List[BoostTask] = [
    BoostTask("CPU Performance Governor",
              "echo performance|sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor>/dev/null 2>&1||true",
              "echo powersave|sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor>/dev/null 2>&1||true",
              "Max CPU clock — disables power saving","gaming"),
    BoostTask("Disable CPU Turbo Boost Limit",
              "echo 0|sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo>/dev/null 2>&1||true",
              "echo 1|sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo>/dev/null 2>&1||true",
              "Allow CPU to boost above base clock","gaming"),
    BoostTask("Swappiness → 1",
              "sudo sysctl -w vm.swappiness=1",
              "sudo sysctl -w vm.swappiness=60",
              "Minimize swapping — keep RAM for game","gaming"),
    BoostTask("Drop File System Cache",
              "sync && echo 3|sudo tee /proc/sys/vm/drop_caches>/dev/null",
              None,
              "Free pagecache, dentries, inodes","gaming"),
    BoostTask("I/O Scheduler → mq-deadline",
              "for d in $(lsblk -dno NAME,TYPE|awk '$2==\"disk\"{print $1}'); do echo mq-deadline|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1||echo deadline|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1; done",
              "for d in $(lsblk -dno NAME,TYPE|awk '$2==\"disk\"{print $1}'); do echo none|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1; done",
              "Low-latency disk I/O scheduler","gaming"),
    BoostTask("Dirty Ratio → 5%",
              "sudo sysctl -w vm.dirty_ratio=5 && sudo sysctl -w vm.dirty_background_ratio=3",
              "sudo sysctl -w vm.dirty_ratio=20 && sudo sysctl -w vm.dirty_background_ratio=10",
              "Write dirty pages faster, free RAM quicker","gaming"),
    BoostTask("Transparent Huge Pages → madvise",
              "echo madvise|sudo tee /sys/kernel/mm/transparent_hugepage/enabled>/dev/null 2>&1||true",
              "echo always|sudo tee /sys/kernel/mm/transparent_hugepage/enabled>/dev/null 2>&1||true",
              "Reduce THP latency spikes","gaming"),
    BoostTask("Network Latency Tuning",
              "sudo sysctl -w net.ipv4.tcp_nodelay=1 && sudo sysctl -w net.core.rmem_max=16777216 && sudo sysctl -w net.core.wmem_max=16777216",
              "sudo sysctl -w net.ipv4.tcp_nodelay=0",
              "Lower TCP latency for online gaming","gaming"),
]

WORK_TASKS: List[BoostTask] = [
    BoostTask("CPU Balanced Governor",
              "echo schedutil|sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor>/dev/null 2>&1||echo ondemand|sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor>/dev/null 2>&1||true",
              "echo powersave|sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor>/dev/null 2>&1||true",
              "Balanced performance/power","work"),
    BoostTask("Swappiness → 10",
              "sudo sysctl -w vm.swappiness=10",
              "sudo sysctl -w vm.swappiness=60",
              "Reduced swapping for responsiveness","work"),
    BoostTask("VM Dirty Ratio → 15%",
              "sudo sysctl -w vm.dirty_ratio=15 && sudo sysctl -w vm.dirty_background_ratio=8",
              "sudo sysctl -w vm.dirty_ratio=20 && sudo sysctl -w vm.dirty_background_ratio=10",
              "Balanced write-back performance","work"),
    BoostTask("I/O Scheduler → bfq",
              "for d in $(lsblk -dno NAME,TYPE|awk '$2==\"disk\"{print $1}'); do echo bfq|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1||echo cfq|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1; done",
              "for d in $(lsblk -dno NAME,TYPE|awk '$2==\"disk\"{print $1}'); do echo none|sudo tee /sys/block/$d/queue/scheduler>/dev/null 2>&1; done",
              "BFQ scheduler — fair I/O for multitasking","work"),
    BoostTask("Enable Kernel ASLR",
              "sudo sysctl -w kernel.randomize_va_space=2",
              "sudo sysctl -w kernel.randomize_va_space=1",
              "Full ASLR for security + stability","work"),
    BoostTask("Inotify Watch Limit",
              "sudo sysctl -w fs.inotify.max_user_watches=524288",
              "sudo sysctl -w fs.inotify.max_user_watches=8192",
              "Fix 'too many open files' for IDEs","work"),
    BoostTask("TCP BBR Congestion Control",
              "sudo modprobe tcp_bbr 2>/dev/null; sudo sysctl -w net.ipv4.tcp_congestion_control=bbr 2>/dev/null||true",
              "sudo sysctl -w net.ipv4.tcp_congestion_control=cubic 2>/dev/null||true",
              "Google BBR for better network throughput","work"),
    BoostTask("Systemd Stop Timeout → 15s",
              "sudo sed -i 's/#DefaultTimeoutStopSec=.*/DefaultTimeoutStopSec=15s/' /etc/systemd/system.conf && sudo systemctl daemon-reload",
              "sudo sed -i 's/DefaultTimeoutStopSec=15s/#DefaultTimeoutStopSec=90s/' /etc/systemd/system.conf && sudo systemctl daemon-reload",
              "Faster system shutdown","work"),
]

class BoostEngine:
    def get_tasks(self, mode:str) -> List[BoostTask]:
        return GAMING_TASKS if mode=="gaming" else WORK_TASKS

    def renice_active(self, nice_val:int=-5) -> List[str]:
        changed=[]
        try:
            import psutil
            procs = sorted(psutil.process_iter(['pid','name','cpu_percent']),
                          key=lambda p: p.info['cpu_percent'], reverse=True)[:5]
            for p in procs:
                if p.info['name'] not in SAFE_PROCS:
                    try:
                        p.nice(nice_val)
                        changed.append(f"renice {p.info['name']} → {nice_val}")
                        try:
                            rollback.record("boost",f"Renice {p.info['name']}",
                                            f"sudo renice 0 -p {p.info['pid']}")
                        except Exception as _re:
                            _log("warning", f"Rollback record failed (renice): {_re}")
                    except: pass
        except ImportError: pass
        return changed

    def ionice_active(self) -> List[str]:
        changed=[]
        try:
            import psutil
            procs = sorted(psutil.process_iter(['pid','name']),
                          key=lambda p: p.info['pid'])[:3]
            for p in procs:
                if p.info['name'] not in SAFE_PROCS:
                    rc,_,_ = run(f"sudo ionice -c 2 -n 0 -p {p.info['pid']}", timeout=3)
                    if rc==0: changed.append(f"ionice {p.info['name']}")
        except: pass
        return changed

    def kill_non_essential(self, dry_run:bool=True) -> List[str]:
        killable=[]
        KILLABLE_PATTERNS = ["tracker","baloo","zeitgeist","evolution-calendar",
                             "gvfs-gdu","tumbler","docinfo","colord","upowerd-dbu"]
        try:
            import psutil
            for p in psutil.process_iter(['pid','name','status']):
                name = p.info['name'].lower()
                if any(k in name for k in KILLABLE_PATTERNS) and p.info['status']!='zombie':
                    killable.append((p.info['pid'],p.info['name']))
                    if not dry_run:
                        try:
                            p.kill()
                            try:
                                rollback.record("boost",f"Killed {p.info['name']}",
                                                f"# Process {p.info['name']} must be restarted manually")
                            except Exception as _re:
                                _log("warning", f"Rollback record failed (kill): {_re}")
                        except: pass
        except: pass
        return [f"PID {pid}: {name}" for pid,name in killable]

boost_engine = BoostEngine()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 ── DEEP CLEAN ENGINE
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class CleanTarget:
    name:     str
    path:     str
    size_mb:  float
    count:    int
    cmd:      str
    safe:     bool
    selected: bool = True

class DeepCleanEngine:
    def scan(self, progress_cb:Callable=None) -> List[CleanTarget]:
        targets=[]

        def _size(path:str) -> Tuple[float,int]:
            rc,out,_ = run(f"du -sm {path} 2>/dev/null|cut -f1",timeout=10)
            rc2,cnt,_ = run(f"find {path} -type f 2>/dev/null|wc -l",timeout=10)
            try: sz=float(out) if rc==0 else 0
            except: sz=0
            try: c=int(cnt) if rc2==0 else 0
            except: c=0
            return sz,c

        steps=[
            ("Package cache",  "/var/cache/apt /var/cache/dnf /var/cache/pacman/pkg",distro.clean_cache,True),
            ("Temp files",     "/tmp /var/tmp",f"sudo rm -rf /tmp/* /var/tmp/* 2>/dev/null||true",True),
            ("User cache",     str(Path.home()/".cache"),"rm -rf ~/.cache/mozilla ~/.cache/google-chrome ~/.cache/chromium ~/.cache/thumbnails 2>/dev/null||true",True),
            ("Old journal",    "/var/log/journal","sudo journalctl --vacuum-size=100M",True),
            ("Crash reports",  "/var/crash","sudo rm -rf /var/crash/* 2>/dev/null||true",True),
            ("Thumbnail cache",str(Path.home()/".cache/thumbnails"),"rm -rf ~/.cache/thumbnails/* 2>/dev/null||true",True),
        ]

        for i,(name,paths,cmd,safe) in enumerate(steps):
            if progress_cb: progress_cb(f"Scanning: {name}…")
            total_sz=0; total_cnt=0
            for p in paths.split():
                if Path(p.replace("~",str(Path.home()))).exists():
                    sz,cnt = _size(p)
                    total_sz+=sz; total_cnt+=cnt
            targets.append(CleanTarget(name,paths,round(total_sz,1),total_cnt,cmd,safe))

        if progress_cb: progress_cb("Scanning orphaned packages…")
        rc,out,_ = run(distro.list_orphans,timeout=15)
        orphan_count = len([l for l in out.splitlines() if l.strip()]) if rc==0 else 0
        if orphan_count>0:
            targets.append(CleanTarget("Orphaned packages","",0,orphan_count,distro.autoremove,True))

        if progress_cb: progress_cb("Scanning old logs…")
        rc,out,_ = run("find /var/log -name '*.gz' -mtime +30 2>/dev/null|wc -l",timeout=8)
        old_logs = int(out) if rc==0 and out.isdigit() else 0
        if old_logs>0:
            rc2,sz_out,_ = run("find /var/log -name '*.gz' -mtime +30 2>/dev/null|xargs du -sc 2>/dev/null|tail -1|cut -f1",timeout=8)
            try: log_mb=int(sz_out)/1024
            except: log_mb=0
            targets.append(CleanTarget("Old compressed logs","/var/log",round(log_mb,1),old_logs,
                "sudo find /var/log -name '*.gz' -mtime +30 -delete 2>/dev/null||true",True))

        _log("info",f"Deep clean scan: {len(targets)} targets")
        return targets

    def execute(self, targets:List[CleanTarget], progress_cb:Callable=None) -> Dict[str,Any]:
        results={"freed_mb":0,"errors":[],"done":[]}
        for t in targets:
            if not t.selected: continue
            if progress_cb: progress_cb(f"Cleaning: {t.name}…")
            size_before = t.size_mb
            rc,out,err = run(t.cmd,timeout=120)
            if rc==0:
                results["freed_mb"] += size_before
                results["done"].append(t.name)
                try:
                    rollback.record("clean",f"Cleaned {t.name}",
                                    f"# {t.name} cannot be automatically restored")
                except Exception as _re:
                    _log("warning", f"Rollback record failed (clean): {_re}")
                _log("info",f"Cleaned: {t.name} (~{size_before} MB)")
            else:
                results["errors"].append(f"{t.name}: {err[:60]}")
                _log("warning",f"Clean failed: {t.name}: {err[:60]}")
        return results

clean_engine = DeepCleanEngine()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 ── FIX ENGINE (LEGACY WRAPPER)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class FixIssue:
    severity:    str
    category:    str
    title:       str
    detail:      str
    fix_cmd:     str
    revert_cmd:  str = ""
    fixed:       bool = False

class FixEngineWrapper:
    def detect(self, progress_cb:Callable=None) -> List[FixIssue]:
        issues=[]

        if progress_cb: progress_cb("Checking broken packages…")
        if distro.family==DistroEngine.DEBIAN:
            rc,out,_ = run("dpkg -l|grep -E '^.H|^.F|^iF'",timeout=10)
            if rc==0 and out.strip():
                issues.append(FixIssue("critical","Packages","Broken/half-installed packages",
                    out[:200],distro.fix_broken,distro.update))
            rc2,out2,_ = run("apt-get check 2>&1|grep -iE 'broken|unmet'",timeout=10)
            if rc2==0 and out2:
                issues.append(FixIssue("critical","Packages","Unmet APT dependencies",
                    out2[:200],distro.fix_broken,""))

        if progress_cb: progress_cb("Checking pending updates…")
        rc,out,_ = run(distro.list_upgradable,timeout=20)
        upgradable=[l for l in out.splitlines() if "/" in l and l.strip()]
        if len(upgradable)>0:
            issues.append(FixIssue("high","Updates",
                f"{len(upgradable)} packages have updates available",
                f"Includes: {', '.join(u.split('/')[0] for u in upgradable[:5])}…",
                distro.upgrade,""))

        if progress_cb: progress_cb("Checking disk space…")
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    u=psutil.disk_usage(part.mountpoint)
                    if u.percent>=90:
                        issues.append(FixIssue("critical","Storage",
                            f"Disk {part.mountpoint} at {u.percent:.0f}%",
                            f"{u.used//1024**3}GB/{u.total//1024**3}GB used",
                            distro.clean_cache,""))
                except: pass
        except ImportError: pass

        if progress_cb: progress_cb("Checking memory…")
        try:
            import psutil
            mem=psutil.virtual_memory()
            if mem.percent>85:
                issues.append(FixIssue("high","Memory",
                    f"RAM at {mem.percent:.0f}%",
                    f"Used: {mem.used//1024**3}GB / Total: {mem.total//1024**3}GB",
                    "sync && echo 3|sudo tee /proc/sys/vm/drop_caches>/dev/null",
                    ""))
        except: pass

        if progress_cb: progress_cb("Checking firewall…")
        active,_ = security_scanner.check_firewall()
        if not active:
            fw_cmd = ("sudo ufw enable" if shutil.which("ufw") else
                      "sudo systemctl enable --now firewalld" if shutil.which("firewall-cmd") else "")
            if fw_cmd:
                issues.append(FixIssue("critical","Security","No active firewall",
                    "System has no enforced firewall rules",fw_cmd,""))

        if progress_cb: progress_cb("Checking SSH config…")
        ssh_issues = security_scanner.check_ssh()
        for msg,risk,_ in ssh_issues:
            sev = "critical" if risk=="red" else "high"
            issues.append(FixIssue(sev,"Security",msg,
                "Found in /etc/ssh/sshd_config",
                "# Edit /etc/ssh/sshd_config manually — see note",""))

        if progress_cb: progress_cb("Checking zombie processes…")
        rc,out,_ = run("ps aux|awk '$8==\"Z\"'|grep -v 'STAT'|wc -l",timeout=5)
        try:
            zombies=int(out)-1
            if zombies>2:
                issues.append(FixIssue("medium","Processes",
                    f"{zombies} zombie processes detected",
                    "Zombie processes consume PID table entries",
                    "# Reboot recommended to clear all zombies",""))
        except: pass

        if progress_cb: progress_cb("Checking swappiness…")
        rc,out,_ = run("cat /proc/sys/vm/swappiness",timeout=3)
        if rc==0 and out.isdigit() and int(out)>30:
            issues.append(FixIssue("medium","Performance",f"Swappiness too high ({out})",
                "Recommendation: ≤10 for SSD systems",
                "sudo sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10'|sudo tee -a /etc/sysctl.conf",
                f"sudo sysctl -w vm.swappiness={out}"))

        _log("info",f"Fix scan: {len(issues)} issues found")
        return issues

    def apply_fix(self, issue:FixIssue, progress_cb:Callable=None) -> Tuple[bool,str]:
        if issue.fix_cmd.startswith("#"):
            return False, issue.fix_cmd
        if progress_cb: progress_cb(f"Fixing: {issue.title}…")
        try:
            rollback.snapshot_packages(label="pre_fix")
        except Exception as _se:
            _log("warning", f"Pre-fix snapshot failed (continuing): {_se}")
        rc,out,err = run(issue.fix_cmd,timeout=180)
        if rc==0:
            issue.fixed=True
            if issue.revert_cmd:
                try:
                    rollback.record("fix",f"Fix: {issue.title}",issue.revert_cmd)
                except Exception as _re:
                    _log("warning", f"Rollback record failed (fix): {_re}")
            _log("info",f"Fixed: {issue.title}")
            return True, out
        else:
            _log("warning",f"Fix failed: {issue.title}: {err}")
            return False, err

fix_engine_wrapper = FixEngineWrapper()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 ── AI ADVISOR
# ══════════════════════════════════════════════════════════════════════════════
PRIORITY_ORDER={"Critical":0,"High":1,"Medium":2,"Low":3}

@dataclass
class AIRecommendation:
    priority: str; category: str; title: str; detail: str
    command: str=""; safe: bool=True

class AIAdvisor:
    def analyse(self, cb:Callable=None) -> List[AIRecommendation]:
        recs=[]
        def _add(priority,category,title,detail,command="",safe=True):
            recs.append(AIRecommendation(priority,category,title,detail,command,safe))
            _log("info",f"AI [{priority}] {title}")

        TOOLS=[("htop","Better process monitor"),("ncdu","Disk usage analyser"),
               ("smartctl","Disk health S.M.A.R.T."),("fail2ban-server","Brute-force prevention"),
               ("rkhunter","Rootkit scanner"),("rsync","Incremental backup"),
               ("timeshift","System snapshots")]
        for binary,desc in TOOLS:
            if not shutil.which(binary):
                tool=binary.replace("-server","")
                _add("Medium","Tools",f"'{tool}' not installed",desc,distro.install(tool))

        active,_ = security_scanner.check_firewall()
        if not active:
            fw_cmd="sudo ufw enable" if shutil.which("ufw") else "sudo systemctl enable --now firewalld"
            _add("Critical","Security","Firewall not active","System has no enforced firewall",fw_cmd)

        for msg,risk,_ in security_scanner.check_ssh():
            sev="Critical" if risk=="red" else "High"
            _add(sev,"Security",msg,"Found in /etc/ssh/sshd_config","# Edit sshd_config manually",False)

        try:
            import psutil
            cpu=psutil.cpu_percent(interval=0.5); mem=psutil.virtual_memory()
            if cpu>80: _add("High","Performance",f"CPU high ({cpu:.0f}%)","","ps aux --sort=-%cpu|head -10")
            if mem.percent>80: _add("High","Performance",f"RAM high ({mem.percent:.0f}%)","","free -h && swapon --show")
            swap=psutil.swap_memory()
            if swap.total==0 and mem.total<8*1024**3:
                _add("High","Performance","No swap on low-RAM system","",
                     "sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile")
            for part in psutil.disk_partitions(all=False):
                try:
                    u=psutil.disk_usage(part.mountpoint)
                    if u.percent>=90: _add("Critical","Storage",f"Disk {part.mountpoint} at {u.percent:.0f}%","",distro.clean_cache,False)
                except: pass
        except: pass

        is_ssd=bool(run("lsblk -d -o name,rota|grep ' 0'",timeout=5)[1])
        if is_ssd:
            timer=run("systemctl is-enabled fstrim.timer 2>/dev/null",timeout=3)[1]
            fstab=run("grep -i discard /etc/fstab 2>/dev/null",timeout=3)[1]
            if "enabled" not in timer and not fstab:
                _add("Medium","Storage","SSD TRIM not scheduled","Weekly fstrim not enabled",
                     "sudo systemctl enable --now fstrim.timer")

        if distro.family==DistroEngine.DEBIAN and not shutil.which("unattended-upgrade"):
            _add("Medium","Security","Auto security updates disabled","",
                 "sudo apt install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades")

        recs.sort(key=lambda r:(PRIORITY_ORDER.get(r.priority,99),r.category))
        _log("info",f"AI analysis complete: {len(recs)} recommendations")
        return recs

ai_advisor = AIAdvisor()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 ── DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════
BG1="#0A0E1A"; BG2="#111827"; BG3="#1A2235"; BG4="#1f2d42"
CYAN="#00E5FF"; CYANL="#00b0c8"; GREEN="#39FF14"; AMBER="#FFB800"; RED="#FF4444"
T1="#E8EAF0"; T2="#7B8BA0"; BORDER="#1e2d45"
CYAN_BORDER="#007a8a"; GREEN_BORDER="#1a6b0a"; AMBER_BORDER="#7a5800"; RED_BORDER="#8a1a1a"
CYAN_DIM="#004d5a"
PURPLE="#A855F7"; PURPLE_BG="#1a0a2e"; PURPLE_BORDER="#5b21b6"

F_MONO=("Courier New",11); F_MONO_SM=("Courier New",10); F_MONO_XS=("Courier New",9)
F_LABEL=("Helvetica",10,"bold"); F_TITLE=("Helvetica",13,"bold")
F_NAV=("Helvetica",8,"bold"); F_BIG=("Courier New",22,"bold")

RISK_COLORS={"green":(GREEN,"#0a1f06",GREEN_BORDER),
             "amber":(AMBER,"#1f1600",AMBER_BORDER),
             "red":  (RED,"#2a0808",RED_BORDER)}
PRIORITY_COLORS={"Critical":(RED,"#2a0808",RED_BORDER,"🔴"),
                 "High":    (AMBER,"#1f1600",AMBER_BORDER,"🟠"),
                 "Medium":  (CYAN,"#001e26",CYAN_BORDER,"🟡"),
                 "Low":     (GREEN,"#0a1f06",GREEN_BORDER,"🟢")}

def _bbg(c): return {CYAN:"#001e26",GREEN:"#0a1f06",AMBER:"#1f1600",RED:"#2a0808",PURPLE:"#1a0a2e"}.get(c,BG3)
def _bbd(c): return {CYAN:CYAN_BORDER,GREEN:GREEN_BORDER,AMBER:AMBER_BORDER,RED:RED_BORDER,PURPLE:PURPLE_BORDER}.get(c,BORDER)

def _card_hdr(card,title,badge,bc):
    h=ctk.CTkFrame(card,fg_color="transparent",height=36)
    h.pack(fill="x",padx=14,pady=(10,0)); h.pack_propagate(False)
    ctk.CTkLabel(h,text=title,font=F_LABEL,text_color=T1).pack(side="left")
    f=ctk.CTkFrame(h,fg_color=_bbg(bc),corner_radius=4,border_width=1,border_color=_bbd(bc))
    ctk.CTkLabel(f,text=badge,font=F_MONO_XS,text_color=bc,padx=6,pady=2).pack(); f.pack(side="right")
    ctk.CTkFrame(card,height=1,fg_color=BORDER).pack(fill="x",pady=(6,0))

def _risk_badge(parent,risk):
    fg,bg,bdr=RISK_COLORS.get(risk,(T2,BG3,BORDER))
    f=ctk.CTkFrame(parent,fg_color=bg,corner_radius=4,border_width=1,border_color=bdr)
    icon={"green":"●","amber":"◆","red":"▲"}.get(risk,"●")
    ctk.CTkLabel(f,text=f"{icon} {risk.upper()}",font=F_MONO_XS,text_color=fg,padx=6,pady=2).pack()
    return f

def _section_tag(parent,text,color=CYAN):
    f=ctk.CTkFrame(parent,fg_color="#0a1a22",corner_radius=4,border_width=1,border_color=CYAN_BORDER)
    ctk.CTkLabel(f,text=text,font=F_MONO_XS,text_color=color,padx=6,pady=2).pack()
    return f

def _distro_banner(parent):
    if not distro.is_supported:
        f=ctk.CTkFrame(parent,fg_color="#1f1600",corner_radius=6,border_width=1,border_color=AMBER_BORDER)
        f.pack(fill="x",padx=14,pady=(8,0))
        ctk.CTkLabel(f,text=f"⚠  Unsupported distro: {distro.name} — commands may not work",
                     font=F_MONO_XS,text_color=AMBER,padx=12,pady=6).pack(anchor="w")

# ── shared widgets ────────────────────────────────────────────────────────────
class LogBox(ctk.CTkFrame):
    def __init__(self,parent,height=160):
        super().__init__(parent,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        hdr=ctk.CTkFrame(self,fg_color="transparent",height=28)
        hdr.pack(fill="x",padx=12,pady=(8,0)); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr,text="›  Output",font=F_MONO_SM,text_color=T1).pack(side="left")
        _section_tag(hdr,"LIVE").pack(side="right")
        ctk.CTkFrame(self,height=1,fg_color=BORDER).pack(fill="x",pady=(4,0))
        self.box=ctk.CTkTextbox(self,font=F_MONO_XS,fg_color=BG1,text_color=T2,
                                 wrap="none",scrollbar_button_color=BG3,height=height)
        self.box.pack(fill="both",expand=True,padx=2,pady=2)
        self.box.configure(state="disabled")

    def write(self,level,msg):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        ts=datetime.now().strftime("%H:%M:%S")
        c={"OK":GREEN,"WARN":AMBER,"ERR":RED,"INFO":CYAN,"RUN":T2}.get(level.upper(),T2)
        line=f"  {ts}  [{level:4s}]  {msg}\n"
        try:
            self.box.configure(state="normal")
            self.box.insert("end",line)
            self.box.configure(state="disabled"); self.box.see("end")
        except Exception:
            pass
        _log("info",f"[{level}] {msg}")

class StatCard(ctk.CTkFrame):
    def __init__(self,parent,label,value,unit="",sub="",color=CYAN):
        super().__init__(parent,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        ctk.CTkLabel(self,text=label,font=F_MONO_XS,text_color=T2).pack(anchor="w",padx=12,pady=(10,0))
        r=ctk.CTkFrame(self,fg_color="transparent"); r.pack(anchor="w",padx=12)
        self._v=ctk.CTkLabel(r,text=value,font=F_BIG,text_color=color); self._v.pack(side="left")
        ctk.CTkLabel(r,text=unit,font=F_MONO_SM,text_color=T2).pack(side="left",pady=(8,0))
        ctk.CTkLabel(self,text=sub,font=F_MONO_XS,text_color=T2).pack(anchor="w",padx=12,pady=(0,10))

    def set(self,v,c=CYAN):
        try:
            if not self.winfo_exists():
                return
            self._v.configure(text=v,text_color=c)
        except Exception:
            pass

class ProgressTask(ctk.CTkFrame):
    def __init__(self,parent,name,desc,color=CYAN):
        super().__init__(parent,fg_color="transparent")
        top=ctk.CTkFrame(self,fg_color="transparent"); top.pack(fill="x")
        ctk.CTkLabel(top,text=name,font=F_LABEL,text_color=T1).pack(side="left")
        self._st=ctk.CTkLabel(top,text="PENDING",font=F_MONO_XS,text_color=T2); self._st.pack(side="right")
        ctk.CTkLabel(self,text=desc,font=F_MONO_XS,text_color=T2,anchor="w").pack(anchor="w")
        self._bar=ctk.CTkProgressBar(self,height=4,corner_radius=2,fg_color=BG3,progress_color=color)
        self._bar.set(0); self._bar.pack(fill="x",pady=(3,6))

    def set_running(self):
        try:
            if not self.winfo_exists(): return
            self._st.configure(text="RUNNING",text_color=CYAN)
        except Exception: pass

    def set_done(self):
        try:
            if not self.winfo_exists(): return
            self._st.configure(text="DONE",text_color=GREEN); self._bar.set(1.0)
        except Exception: pass

    def set_warn(self):
        try:
            if not self.winfo_exists(): return
            self._st.configure(text="WARN",text_color=AMBER); self._bar.set(1.0)
        except Exception: pass

    def set_fail(self):
        try:
            if not self.winfo_exists(): return
            self._st.configure(text="FAIL",text_color=RED)
        except Exception: pass

    def animate(self, v):
        try:
            if not self.winfo_exists():
                return
            self._bar.set(min(v, 0.95))
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10a ── REAL-TIME LOG PANEL
# ══════════════════════════════════════════════════════════════════════════════
class RealTimeLogPanel(ctk.CTkFrame):
    """
    A persistent real-time log panel that receives all _log() messages and
    displays them with colour-coded severity badges.  Thread-safe: callers
    must only invoke .log() from the main Tk thread (use app.after(0, ...)).
    """
    MAX_LINES = 500   # keep buffer bounded

    def __init__(self, parent, height: int = 180):
        super().__init__(parent, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        self._build(height)

    def _build(self, height: int):
        hdr = ctk.CTkFrame(self, fg_color=BG3, corner_radius=0, height=30)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        hi = ctk.CTkFrame(hdr, fg_color="transparent")
        hi.pack(fill="both", expand=True, padx=10)
        ctk.CTkLabel(hi, text="◉  REAL-TIME LOG",
                     font=("Courier New", 9, "bold"),
                     text_color=CYAN).pack(side="left", pady=5)
        # live badge
        lb = ctk.CTkFrame(hi, fg_color="#001e26", corner_radius=4,
                           border_width=1, border_color=CYAN_BORDER)
        ctk.CTkLabel(lb, text="● LIVE", font=("Courier New", 8, "bold"),
                      text_color=GREEN, padx=6, pady=2).pack()
        lb.pack(side="left", padx=6)
        # clear button
        ctk.CTkButton(hi, text="✕ Clear", width=60, height=20,
                       font=("Courier New", 8), fg_color=BG4,
                       hover_color=BG3, text_color=T2, corner_radius=4,
                       command=self.clear).pack(side="right", pady=5)
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")
        self._box = ctk.CTkTextbox(
            self, font=("Courier New", 9), fg_color=BG1, text_color=T2,
            wrap="none", scrollbar_button_color=BG3, height=height)
        self._box.pack(fill="both", expand=True, padx=2, pady=2)
        self._box.configure(state="disabled")
        self._line_count = 0

    # ── public API ──────────────────────────────────────────────────────────
    def log(self, msg: str, level: str = "INFO"):
        """
        Append a message.  Must be called from the main Tk thread.
        Safe to call even if the widget is being destroyed.
        """
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        level_map = {
            "INFO": (CYAN,  "INFO"),
            "WARNING": (AMBER, "WARN"),
            "WARN":    (AMBER, "WARN"),
            "ERROR":   (RED,   "ERR "),
            "ERR":     (RED,   "ERR "),
            "DEBUG":   (T2,    "DBG "),
            "OK":      (GREEN, "OK  "),
            "RUN":     (T2,    "RUN "),
            "CRITICAL":(RED,   "CRIT"),
        }
        col, tag = level_map.get(level.upper(), (T2, level[:4].upper().ljust(4)))
        line = f"  {ts}  [{tag}]  {msg}\n"

        try:
            self._box.configure(state="normal")
            self._box.insert("end", line)
            self._line_count += 1
            # Trim buffer when it grows too large
            if self._line_count > self.MAX_LINES:
                self._box.delete("1.0", "50.0")
                self._line_count = max(0, self._line_count - 50)
            self._box.configure(state="disabled")
            self._box.see("end")
        except Exception:
            pass

    def clear(self):
        try:
            if not self.winfo_exists():
                return
            self._box.configure(state="normal")
            self._box.delete("1.0", "end")
            self._box.configure(state="disabled")
            self._line_count = 0
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10b ── AUTO FIX RESULT MODAL
# ══════════════════════════════════════════════════════════════════════════════

class AutoFixResultModal(ctk.CTkToplevel):
    """Premium modal to display AutoFix execution results."""

    def __init__(self, parent, summary: ExecutionSummary):
        super().__init__(parent)
        self.title("JENIX — Auto Fix Results")
        self.geometry("820x680")
        self.resizable(True, True)
        self.configure(fg_color=BG1)
        self.grab_set()
        self.lift()
        self._summary = summary
        self._build(summary)

    def _build(self, s: ExecutionSummary):
        # Top accent bar
        ctk.CTkFrame(self, height=3, fg_color=GREEN if s.applied > 0 else RED,
                     corner_radius=0).pack(fill="x")

        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=64)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        hi = ctk.CTkFrame(hdr, fg_color="transparent")
        hi.pack(fill="both", expand=True, padx=20)

        icon = "✓" if s.applied > 0 and s.failed == 0 else "⚠" if s.applied > 0 else "✗"
        icon_col = GREEN if s.applied > 0 and s.failed == 0 else AMBER if s.applied > 0 else RED
        ctk.CTkLabel(hi, text=f"{icon}  AUTO FIX COMPLETE",
                     font=("Courier New", 16, "bold"), text_color=icon_col).pack(side="left", pady=16)
        ctk.CTkButton(hi, text="✕ Close", width=90, height=28,
                      font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                      text_color=T2, corner_radius=4,
                      command=self.destroy).pack(side="right", pady=18)

        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                       scrollbar_button_color=BG3)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Smart message banner
        msg_bg = "#0a1f06" if s.applied > 0 and s.failed == 0 else "#1f1600" if s.applied > 0 else "#2a0808"
        msg_bd = GREEN_BORDER if s.applied > 0 and s.failed == 0 else AMBER_BORDER if s.applied > 0 else RED_BORDER
        msg_col = GREEN if s.applied > 0 and s.failed == 0 else AMBER if s.applied > 0 else RED
        mc = ctk.CTkFrame(body, fg_color=msg_bg, corner_radius=8,
                           border_width=1, border_color=msg_bd)
        mc.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(mc, text=s.smart_message or "Fix execution complete.",
                     font=("Courier New", 11, "bold"), text_color=msg_col,
                     wraplength=740, justify="left").pack(anchor="w", padx=16, pady=12)

        # Stats row
        stats_row = ctk.CTkFrame(body, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 10))
        for i in range(4):
            stats_row.columnconfigure(i, weight=1, uniform="sr")

        stats = [
            ("APPLIED", str(s.applied), GREEN),
            ("FAILED",  str(s.failed),  RED if s.failed else T2),
            ("SKIPPED", str(s.skipped), AMBER if s.skipped else T2),
            ("TOTAL",   str(s.total_fixes), CYAN),
        ]
        for i, (lbl, val, col) in enumerate(stats):
            sc = ctk.CTkFrame(stats_row, fg_color=BG2, corner_radius=8,
                               border_width=1, border_color=BORDER)
            sc.grid(row=0, column=i, padx=(0, 6 if i < 3 else 0), sticky="nsew")
            ctk.CTkLabel(sc, text=val, font=("Courier New", 26, "bold"),
                          text_color=col).pack(pady=(10, 2))
            ctk.CTkLabel(sc, text=lbl, font=F_MONO_XS, text_color=T2).pack(pady=(0, 10))

        # Improvement line
        if s.system_improvement and s.system_improvement != "No measurable resource changes":
            imp = ctk.CTkFrame(body, fg_color="#001e26", corner_radius=8,
                                border_width=1, border_color=CYAN_BORDER)
            imp.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(imp, text=f"📈  {s.system_improvement}",
                          font=("Courier New", 10, "bold"), text_color=CYAN,
                          padx=14, pady=10).pack(anchor="w")

        # Aborted warning
        if s.aborted_early:
            ab = ctk.CTkFrame(body, fg_color="#2a0808", corner_radius=8,
                               border_width=1, border_color=RED_BORDER)
            ab.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(ab, text=f"⊘  ABORTED: {s.abort_reason}",
                          font=F_MONO_XS, text_color=RED, padx=14, pady=8).pack(anchor="w")

        # Per-result breakdown
        if s.results:
            rc_card = ctk.CTkFrame(body, fg_color=BG2, corner_radius=8,
                                    border_width=1, border_color=BORDER)
            rc_card.pack(fill="x", pady=(0, 10))
            _card_hdr(rc_card, "Fix Results", f"{len(s.results)} items", CYAN)

            STATUS_CFG = {
                "success": (GREEN,  "#0a1f06", GREEN_BORDER,  "✓"),
                "failed":  (RED,    "#2a0808", RED_BORDER,    "✗"),
                "skipped": (AMBER,  "#1f1600", AMBER_BORDER,  "–"),
                "dry_run": (CYAN,   "#001e26", CYAN_BORDER,   "~"),
                "aborted": (T2,     BG3,       BORDER,        "⊘"),
            }
            for res in s.results:
                cfg = STATUS_CFG.get(res.status, (T2, BG3, BORDER, "?"))
                fg, bg, bd, icon2 = cfg
                rrow = ctk.CTkFrame(rc_card, fg_color="transparent")
                rrow.pack(fill="x", padx=14, pady=(6, 0))
                top_r = ctk.CTkFrame(rrow, fg_color="transparent")
                top_r.pack(fill="x")
                sf = ctk.CTkFrame(top_r, fg_color=bg, corner_radius=3,
                                   border_width=1, border_color=bd)
                ctk.CTkLabel(sf, text=f"{icon2} {res.status.upper()}",
                              font=F_MONO_XS, text_color=fg, padx=5, pady=2).pack()
                sf.pack(side="left", padx=(0, 8))
                pri_col = {"CRITICAL":RED,"HIGH":AMBER,"MEDIUM":CYAN,"LOW":GREEN}.get(
                    getattr(res, 'priority', 'LOW'), T2)
                pf = ctk.CTkFrame(top_r, fg_color=_bbg(pri_col), corner_radius=3,
                                   border_width=1, border_color=_bbd(pri_col))
                ctk.CTkLabel(pf, text=getattr(res, 'priority', '—'),
                              font=F_MONO_XS, text_color=pri_col, padx=5, pady=2).pack()
                pf.pack(side="left", padx=(0, 8))
                ctk.CTkLabel(top_r, text=res.fix, font=F_LABEL,
                              text_color=T1, anchor="w").pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(rrow, text=res.details[:120],
                              font=F_MONO_XS, text_color=T2, anchor="w",
                              wraplength=680).pack(anchor="w", pady=(2, 6))
                ctk.CTkFrame(rc_card, height=1, fg_color=BORDER).pack(fill="x", padx=14)
            ctk.CTkFrame(rc_card, height=6, fg_color="transparent").pack()

        # Report buttons
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(btn_row, text="📋  VIEW FULL REPORT",
                       width=180, height=34, font=("Courier New", 10, "bold"),
                       fg_color=CYAN, hover_color=CYANL, text_color=BG1,
                       corner_radius=6,
                       command=lambda: self._show_report(s)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="{ } JSON",
                       width=100, height=34, font=F_MONO_XS,
                       fg_color=BG3, hover_color=BG4, text_color=CYAN,
                       corner_radius=6, border_width=1, border_color=CYAN_BORDER,
                       command=lambda: self._show_json(s)).pack(side="left")

    def _show_report(self, s: ExecutionSummary):
        try:
            from fix_engine import FixEngine as _FE
            eng = _FE()
            report_txt = eng.generate_fix_report(s)
        except Exception as _e:
            report_txt = f"Report generation failed: {_e}\n\n{s.smart_message}"
        _TextWindow(self, "Fix Execution Report", report_txt)

    def _show_json(self, s: ExecutionSummary):
        try:
            json_txt = s.as_json()
        except Exception as _e:
            json_txt = json.dumps({"error": str(_e)}, indent=2)
        _TextWindow(self, "Fix Report — JSON", json_txt)


class _TextWindow(ctk.CTkToplevel):
    """Generic scrollable text window for reports."""
    def __init__(self, parent, title: str, content: str):
        super().__init__(parent)
        self.title(f"JENIX — {title}")
        self.geometry("900x640")
        self.configure(fg_color=BG1)
        self.lift()

        ctk.CTkFrame(self, height=2, fg_color=CYAN, corner_radius=0).pack(fill="x")
        h = ctk.CTkFrame(self, fg_color=BG2, height=44, corner_radius=0)
        h.pack(fill="x"); h.pack_propagate(False)
        hi = ctk.CTkFrame(h, fg_color="transparent")
        hi.pack(fill="both", expand=True, padx=14)
        ctk.CTkLabel(hi, text=title, font=("Courier New", 12, "bold"),
                      text_color=CYAN).pack(side="left", pady=10)
        ctk.CTkButton(hi, text="✕ Close", width=80, height=26,
                       font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                       text_color=T2, corner_radius=4,
                       command=self.destroy).pack(side="right", pady=9)
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")

        tb = ctk.CTkTextbox(self, font=("Courier New", 10), fg_color=BG1,
                             text_color=T2, wrap="none",
                             scrollbar_button_color=BG3)
        tb.pack(fill="both", expand=True, padx=8, pady=8)
        tb.insert("end", content)
        tb.configure(state="disabled")


class ConfirmDialog(ctk.CTkToplevel):
    """Reusable confirmation dialog."""
    def __init__(self, parent, title: str, message: str,
                 on_confirm: Callable, danger: bool = False):
        super().__init__(parent)
        self.title(f"JENIX — {title}")
        self.geometry("500x260")
        self.resizable(False, False)
        self.configure(fg_color=BG1)
        self.grab_set(); self.lift()
        self._result = False

        accent = RED if danger else AMBER
        ctk.CTkFrame(self, height=3, fg_color=accent, corner_radius=0).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        icon = "⚠" if danger else "❓"
        ctk.CTkLabel(body, text=f"{icon}  {title}",
                      font=("Courier New", 14, "bold"),
                      text_color=accent).pack(anchor="w", pady=(0, 12))

        msg_frame = ctk.CTkFrame(body, fg_color=BG2, corner_radius=8,
                                  border_width=1, border_color=BORDER)
        msg_frame.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(msg_frame, text=message, font=F_MONO_SM,
                      text_color=T1, wraplength=440,
                      justify="left").pack(anchor="w", padx=14, pady=12)

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")

        def _confirm():
            self._result = True
            if on_confirm: on_confirm()
            self.destroy()

        ctk.CTkButton(btn_row, text="✓  CONFIRM", width=140, height=36,
                       font=("Courier New", 10, "bold"),
                       fg_color=accent, hover_color=RED if danger else "#d49a00",
                       text_color=BG1, corner_radius=6,
                       command=_confirm).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="✕  CANCEL", width=100, height=36,
                       font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                       text_color=T2, corner_radius=6,
                       command=self.destroy).pack(side="left")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 ── BOOST VIEW
# ══════════════════════════════════════════════════════════════════════════════
class BoostView(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color="transparent")
        self._mode="work"; self._running=False
        self._task_widgets: List[ProgressTask]=[]
        self._build()

    def _build(self):
        scroll=ctk.CTkScrollableFrame(self,fg_color="transparent",
                                       scrollbar_button_color=BG3,scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both",expand=True,padx=14,pady=14)
        _distro_banner(scroll)

        mode_card=ctk.CTkFrame(scroll,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        mode_card.pack(fill="x",pady=(0,10))
        mc=ctk.CTkFrame(mode_card,fg_color="transparent"); mc.pack(fill="x",padx=16,pady=12)
        ctk.CTkLabel(mc,text="⚡  SYSTEM BOOST",font=("Courier New",14,"bold"),text_color=CYAN).pack(side="left")
        ctk.CTkLabel(mc,text=f"{distro.label}",font=F_MONO_XS,text_color=T2).pack(side="right")
        ctk.CTkFrame(mode_card,height=1,fg_color=BORDER).pack(fill="x")

        btns=ctk.CTkFrame(mode_card,fg_color="transparent"); btns.pack(padx=16,pady=10)
        self._gaming_btn=ctk.CTkButton(btns,text="🎮  GAMING MODE",width=160,height=36,
            font=("Courier New",10,"bold"),fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=6,border_width=1,border_color=BORDER,command=lambda:self._set_mode("gaming"))
        self._gaming_btn.pack(side="left",padx=(0,8))
        self._work_btn=ctk.CTkButton(btns,text="💼  WORK MODE",width=160,height=36,
            font=("Courier New",10,"bold"),fg_color=CYAN,hover_color=CYANL,text_color=BG1,
            corner_radius=6,command=lambda:self._set_mode("work"))
        self._work_btn.pack(side="left",padx=(0,8))
        self._run_btn=ctk.CTkButton(btns,text="▶  RUN BOOST",width=130,height=36,
            font=("Courier New",10,"bold"),fg_color=GREEN,hover_color="#2acc0e",text_color=BG1,
            corner_radius=6,command=self._run_boost)
        self._run_btn.pack(side="left")

        self._desc_lbl=ctk.CTkLabel(mode_card,
            text="Work Mode: Balanced performance, stability, and power efficiency.",
            font=F_MONO_XS,text_color=T2)
        self._desc_lbl.pack(padx=16,pady=(0,12))

        self._tasks_host=ctk.CTkFrame(scroll,fg_color="transparent")
        self._tasks_host.pack(fill="x",pady=(0,10))
        self._rebuild_tasks()

        proc_card=ctk.CTkFrame(scroll,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        proc_card.pack(fill="x",pady=(0,10))
        _card_hdr(proc_card,"⚡  Process Optimisation","advanced",AMBER)
        pr=ctk.CTkFrame(proc_card,fg_color="transparent"); pr.pack(padx=14,pady=8)
        ctk.CTkButton(pr,text="🔍 Preview Killable",width=150,height=28,
            font=F_MONO_XS,fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=4,border_width=1,border_color=BORDER,
            command=self._preview_procs).pack(side="left",padx=(0,8))
        ctk.CTkButton(pr,text="⚡ Renice Active",width=130,height=28,
            font=F_MONO_XS,fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=4,border_width=1,border_color=BORDER,
            command=self._renice).pack(side="left",padx=(0,8))
        ctk.CTkButton(pr,text="💾 Drop Caches",width=130,height=28,
            font=F_MONO_XS,fg_color=BG3,hover_color=BG4,text_color=AMBER,
            corner_radius=4,border_width=1,border_color=AMBER_BORDER,
            command=self._drop_caches).pack(side="left")

        self._result=ctk.CTkFrame(scroll,fg_color="#0a1f06",corner_radius=8,
                                   border_width=1,border_color=GREEN_BORDER)
        self._result_lbl=ctk.CTkLabel(self._result,text="",font=("Courier New",11,"bold"),text_color=GREEN)
        self._result_lbl.pack(pady=12)

        self.log=LogBox(scroll,height=130)
        self.log.pack(fill="x",pady=(0,4))
        self.log.write("INFO",f"Boost ready · distro: {distro.label}")

    def _set_mode(self,mode):
        self._mode=mode
        if mode=="gaming":
            self._gaming_btn.configure(fg_color=AMBER,hover_color="#d49a00",text_color=BG1,border_width=0)
            self._work_btn.configure(fg_color=BG3,hover_color=BG4,text_color=T2,border_width=1,border_color=BORDER)
            self._desc_lbl.configure(text="Gaming Mode: Maximum CPU/GPU performance, minimal background processes, aggressive RAM freeing.")
        else:
            self._work_btn.configure(fg_color=CYAN,hover_color=CYANL,text_color=BG1,border_width=0)
            self._gaming_btn.configure(fg_color=BG3,hover_color=BG4,text_color=T2,border_width=1,border_color=BORDER)
            self._desc_lbl.configure(text="Work Mode: Balanced performance, stability, and power efficiency.")
        self._rebuild_tasks()

    def _rebuild_tasks(self):
        for w in self._tasks_host.winfo_children(): w.destroy()
        tasks=boost_engine.get_tasks(self._mode)
        card=ctk.CTkFrame(self._tasks_host,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        card.pack(fill="x")
        col=AMBER if self._mode=="gaming" else CYAN
        _card_hdr(card,f"{'🎮 Gaming' if self._mode=='gaming' else '💼 Work'} Tasks",f"{len(tasks)} tasks",col)
        self._task_widgets=[]
        for i,t in enumerate(tasks):
            w=ProgressTask(card,t.name,t.desc,col)
            w.pack(fill="x",padx=14,pady=(6,0))
            self._task_widgets.append(w)
            if i<len(tasks)-1:
                ctk.CTkFrame(card,height=1,fg_color=BORDER).pack(fill="x",padx=14)
        ctk.CTkFrame(card,height=8,fg_color="transparent").pack()
        self._tasks_card=card

    def _run_boost(self):
        if self._running: return
        self._running=True
        self._run_btn.configure(state="disabled",text="⏳  RUNNING…")
        self._result.pack_forget()
        try:
            snap = rollback.snapshot_packages("pre_boost")
            if snap.get("status") == "success":
                self.log.write("INFO", f"Pre-boost snapshot: {snap.get('message','')}")
            else:
                self.log.write("WARN", f"Pre-boost snapshot skipped: {snap.get('message','')}")
        except Exception as _se:
            self.log.write("WARN", f"Pre-boost snapshot error: {_se}")
        self.log.write("INFO", "Boost Started")
        threading.Thread(target=self._execute_boost,daemon=True).start()

    def _execute_boost(self):
        tasks=boost_engine.get_tasks(self._mode)
        ok=fail=0
        try:
            safe_after(self, 0, lambda: self.log.write("INFO", "Applying optimizations…"))
            for i,(task,widget) in enumerate(zip(tasks,self._task_widgets)):
                safe_after(self, 0, widget.set_running)
                safe_after(self, 0, lambda m=f"Running: {task.name}": self.log.write("RUN", m))
                done=threading.Event(); rc_holder=[0]

                def _do(c=task.cmd,r=task.revert,d=task.name,flag=done,holder=rc_holder):
                    try:
                        rc,out,err=run(c,timeout=40)
                        if rc==0 and r:
                            try:
                                rollback.record("boost",f"Boost: {d}",r)
                            except Exception as _re:
                                _log("warning", f"Rollback record failed ({d}): {_re}")
                        holder[0]=rc
                    except Exception as _ex:
                        _log("error", f"Boost task exception ({d}): {_ex}")
                        holder[0]=-99
                    finally:
                        flag.set()

                threading.Thread(target=_do,daemon=True).start()
                v=0.0
                while not done.is_set():
                    safe_after(self, 0, lambda w2=widget, vv=v: safe_animate(w2, vv / 100))
                    v+=3; time.sleep(0.035)
                if rc_holder[0]==0:
                    safe_after(self, 0, widget.set_done)
                    safe_after(self, 0, lambda n=task.name: self.log.write("OK", f"✓ {n}"))
                    ok+=1
                else:
                    safe_after(self, 0, widget.set_warn)
                    safe_after(self, 0, lambda n=task.name: self.log.write("WARN", f"⚠ {n}"))
                    fail+=1
                time.sleep(0.05)
        except Exception as _ex:
            _log("error", f"_execute_boost outer exception: {_ex}")
            safe_after(self, 0, lambda e=str(_ex): self.log.write("ERR", f"Boost error: {e}"))
        finally:
            safe_after(self, 0, lambda o=ok, f2=fail: self._boost_done(o, f2))

    def _boost_done(self,ok,fail):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._running=False
        self._run_btn.configure(state="normal",text="▶  RUN BOOST")
        msg=f"✓  Boost Complete — {ok} applied"+(f", {fail} warnings" if fail else "")
        self._result_lbl.configure(text=msg)
        self._result.pack(fill="x",padx=14,pady=(0,6))
        self.log.write("OK", "Boost Completed")
        self.log.write("OK",msg)

    def _preview_procs(self):
        self.log.write("INFO","Scanning killable background processes…")
        procs=boost_engine.kill_non_essential(dry_run=True)
        if procs:
            for p in procs: self.log.write("INFO",f"  Killable: {p}")
        else:
            self.log.write("OK","No non-essential killable processes found")

    def _renice(self):
        self.log.write("INFO","Renicing top CPU processes…")
        changed=boost_engine.renice_active(-5)
        for c in changed: self.log.write("OK",c)
        if not changed: self.log.write("INFO","Nothing to renice")

    def _drop_caches(self):
        self.log.write("RUN","Dropping filesystem caches…")
        rc,_,err=run("sync && echo 3|sudo tee /proc/sys/vm/drop_caches>/dev/null",timeout=10)
        if rc==0: self.log.write("OK","Caches dropped — RAM freed")
        else: self.log.write("WARN",f"Failed: {err[:60]}")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 ── DEEP CLEAN VIEW
# ══════════════════════════════════════════════════════════════════════════════
class CleanView(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color="transparent")
        self._targets: List[CleanTarget]=[]
        self._check_vars: List[ctk.BooleanVar]=[]
        self._scanning=False; self._cleaning=False
        self._build()

    def _build(self):
        scroll=ctk.CTkScrollableFrame(self,fg_color="transparent",
                                       scrollbar_button_color=BG3,scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both",expand=True,padx=14,pady=14)
        _distro_banner(scroll)

        top=ctk.CTkFrame(scroll,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        top.pack(fill="x",pady=(0,10))
        tc=ctk.CTkFrame(top,fg_color="transparent"); tc.pack(fill="x",padx=16,pady=12)
        ctk.CTkLabel(tc,text="◻  DEEP CLEAN",font=("Courier New",14,"bold"),text_color=CYAN).pack(side="left")
        ctk.CTkLabel(tc,text=f"{distro.label}",font=F_MONO_XS,text_color=T2).pack(side="right")
        ctk.CTkFrame(top,height=1,fg_color=BORDER).pack(fill="x")
        br=ctk.CTkFrame(top,fg_color="transparent"); br.pack(padx=16,pady=10)
        self._scan_btn=ctk.CTkButton(br,text="🔍  PREVIEW SCAN",width=160,height=34,
            font=("Courier New",10,"bold"),fg_color=CYAN,hover_color=CYANL,text_color=BG1,
            corner_radius=6,command=self._start_scan)
        self._scan_btn.pack(side="left",padx=(0,8))
        self._clean_btn=ctk.CTkButton(br,text="◻  CLEAN SELECTED",width=160,height=34,
            font=("Courier New",10,"bold"),fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=6,state="disabled",command=self._start_clean)
        self._clean_btn.pack(side="left",padx=(0,8))
        self._sel_all_btn=ctk.CTkButton(br,text="☑ All",width=70,height=34,
            font=F_MONO_XS,fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=4,border_width=1,border_color=BORDER,command=self._select_all)
        self._sel_all_btn.pack(side="left",padx=(0,4))
        self._sel_none_btn=ctk.CTkButton(br,text="☐ None",width=70,height=34,
            font=F_MONO_XS,fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=4,border_width=1,border_color=BORDER,command=self._select_none)
        self._sel_none_btn.pack(side="left")

        self._prog=ctk.CTkProgressBar(scroll,height=3,corner_radius=0,fg_color=BG3,progress_color=CYAN)
        self._prog.set(0); self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.pack_forget()

        self._preview_host=ctk.CTkFrame(scroll,fg_color="transparent")
        self._preview_host.pack(fill="x",pady=(0,10))
        self._empty_lbl=ctk.CTkLabel(scroll,
            text="Click 🔍 PREVIEW SCAN to detect cleanable files before deleting anything.",
            font=F_MONO_SM,text_color=T2)
        self._empty_lbl.pack(pady=30)

        self._result=ctk.CTkFrame(scroll,fg_color="#0a1f06",corner_radius=8,
                                   border_width=1,border_color=GREEN_BORDER)
        self._rlbl=ctk.CTkLabel(self._result,text="",font=("Courier New",11,"bold"),text_color=GREEN)
        self._rlbl.pack(pady=12)

        self.log=LogBox(scroll,height=120)
        self.log.pack(fill="x",pady=(0,4))
        self.log.write("INFO","Deep clean ready — scan first to preview files")

    def _start_scan(self):
        if self._scanning: return
        self._scanning=True; self._scan_btn.configure(state="disabled",text="⏳  SCANNING…")
        self._empty_lbl.pack_forget(); self._result.pack_forget()
        for w in self._preview_host.winfo_children(): w.destroy()
        self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.set(0)
        self._animate_prog(0)
        threading.Thread(target=self._do_scan,daemon=True).start()

    def _animate_prog(self,v):
        if v<0.88:
            try:
                if not self.winfo_exists(): return
                self._prog.set(v)
            except Exception: return
            safe_after(self, 70, lambda: self._animate_prog(min(v+0.012,0.88)))

    def _do_scan(self):
        def cb(msg): safe_after(self, 0, lambda m=msg: self.log.write("INFO",m))
        targets=clean_engine.scan(cb)
        safe_after(self, 0, lambda t=targets: self._render_preview(t))

    def _render_preview(self,targets):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._targets=targets; self._check_vars=[]
        self._scanning=False; self._scan_btn.configure(state="normal",text="🔍  PREVIEW SCAN")
        try:
            self._prog.set(1.0)
        except Exception: pass
        safe_after(self, 400, self._prog.pack_forget)

        card=ctk.CTkFrame(self._preview_host,fg_color=BG2,corner_radius=8,
                          border_width=1,border_color=BORDER)
        card.pack(fill="x")
        total_mb=sum(t.size_mb for t in targets)
        _card_hdr(card,"Preview — Select items to clean",f"~{total_mb:.0f} MB",CYAN)

        hdr=ctk.CTkFrame(card,fg_color=BG3,corner_radius=0); hdr.pack(fill="x")
        for txt,w,side in [("",40,"left"),("Category",0,"left"),("Size",80,"right"),("Files",70,"right"),("Safe",50,"right")]:
            ctk.CTkLabel(hdr,text=txt,font=F_MONO_XS,text_color=T2,
                         width=w if w else 0,anchor="w" if side=="left" else "e").pack(
                side=side,padx=(12 if not txt else 4),pady=5,
                fill="x" if txt=="Category" else None,
                expand=(txt=="Category"))

        for i,t in enumerate(targets):
            var=ctk.BooleanVar(value=t.selected)
            self._check_vars.append(var)
            row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x")
            ctk.CTkCheckBox(row,text="",variable=var,width=30,
                            checkbox_height=16,checkbox_width=16,
                            fg_color=CYAN,hover_color=CYANL,
                            border_color=BORDER,
                            command=lambda i2=i,v2=var: self._toggle(i2,v2)).pack(side="left",padx=(12,4),pady=8)
            ctk.CTkLabel(row,text=t.name,font=F_LABEL,text_color=T1,anchor="w").pack(
                side="left",fill="x",expand=True,pady=8)
            sz_col=RED if t.size_mb>1000 else AMBER if t.size_mb>200 else T2
            ctk.CTkLabel(row,text=f"{t.size_mb:.0f} MB" if t.size_mb>0 else "—",
                         font=F_MONO_XS,text_color=sz_col,width=80,anchor="e").pack(side="left",padx=4)
            ctk.CTkLabel(row,text=str(t.count) if t.count>0 else "—",
                         font=F_MONO_XS,text_color=T2,width=70,anchor="e").pack(side="left",padx=4)
            safe_col=GREEN if t.safe else AMBER
            ctk.CTkLabel(row,text="✓" if t.safe else "!",
                         font=F_MONO_XS,text_color=safe_col,width=50,anchor="e").pack(side="right",padx=12)
            if i<len(targets)-1:
                ctk.CTkFrame(card,height=1,fg_color=BORDER).pack(fill="x",padx=14)

        ctk.CTkFrame(card,height=6,fg_color="transparent").pack()
        self._clean_btn.configure(state="normal",fg_color=CYAN,hover_color=CYANL,
                                   text_color=BG1,text="◻  CLEAN SELECTED")
        self.log.write("OK",f"Scan complete — {len(targets)} categories · ~{total_mb:.0f} MB freeable")

    def _toggle(self,i,var): self._targets[i].selected=var.get()
    def _select_all(self):
        for var in self._check_vars: var.set(True)
        for t in self._targets: t.selected=True
    def _select_none(self):
        for var in self._check_vars: var.set(False)
        for t in self._targets: t.selected=False

    def _start_clean(self):
        if self._cleaning: return
        selected=[t for t in self._targets if t.selected]
        if not selected: self.log.write("WARN","No items selected"); return
        self._cleaning=True
        self._clean_btn.configure(state="disabled",text="⏳  CLEANING…")
        self._result.pack_forget()
        threading.Thread(target=self._do_clean,daemon=True).start()

    def _do_clean(self):
        selected=[t for t in self._targets if t.selected]
        def cb(msg): safe_after(self, 0, lambda m=msg: self.log.write("RUN",m))
        results=clean_engine.execute(selected,cb)
        safe_after(self, 0, lambda r=results: self._clean_done(r))

    def _clean_done(self,results):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._cleaning=False
        self._clean_btn.configure(state="normal",text="◻  CLEAN SELECTED")
        msg=f"✓  Freed ~{results['freed_mb']:.0f} MB  ·  {len(results['done'])} categories cleaned"
        if results["errors"]: msg+=f"  ·  {len(results['errors'])} errors"
        self._rlbl.configure(text=msg)
        self._result.pack(fill="x",padx=14,pady=(8,4))
        self.log.write("OK",msg)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 ── SECURITY SCAN VIEW
# ══════════════════════════════════════════════════════════════════════════════
class SecurityView(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color="transparent")
        self._scanning=False; self._build()

    def _build(self):
        scroll=ctk.CTkScrollableFrame(self,fg_color="transparent",
                                       scrollbar_button_color=BG3,scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both",expand=True,padx=14,pady=14)

        top=ctk.CTkFrame(scroll,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        top.pack(fill="x",pady=(0,10))
        tc=ctk.CTkFrame(top,fg_color="transparent"); tc.pack(fill="x",padx=16,pady=12)
        ctk.CTkLabel(tc,text="🔒  SECURITY SCAN",font=("Courier New",14,"bold"),text_color=CYAN).pack(side="left")
        _section_tag(tc,"LIVE AUDIT").pack(side="right")
        ctk.CTkFrame(top,height=1,fg_color=BORDER).pack(fill="x")
        br=ctk.CTkFrame(top,fg_color="transparent"); br.pack(padx=16,pady=10)
        self._scan_btn=ctk.CTkButton(br,text="🔒  RUN FULL SCAN",width=160,height=34,
            font=("Courier New",10,"bold"),fg_color=CYAN,hover_color=CYANL,text_color=BG1,
            corner_radius=6,command=self._start_scan)
        self._scan_btn.pack(side="left",padx=(0,8))

        self._prog=ctk.CTkProgressBar(scroll,height=3,corner_radius=0,fg_color=BG3,progress_color=CYAN)
        self._prog.set(0); self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.pack_forget()

        self._summary_host=ctk.CTkFrame(scroll,fg_color="transparent")
        self._summary_host.pack(fill="x",pady=(0,8))

        self._results_host=ctk.CTkFrame(scroll,fg_color="transparent")
        self._results_host.pack(fill="x",pady=(0,8))

        self._idle_lbl=ctk.CTkLabel(scroll,
            text="Click 🔒 RUN FULL SCAN to audit ports, SSH, firewall, SUID files, and more.",
            font=F_MONO_SM,text_color=T2)
        self._idle_lbl.pack(pady=30)

        self.log=LogBox(scroll,height=120)
        self.log.pack(fill="x",pady=(0,4))
        self.log.write("INFO","Security scanner ready")

    def _start_scan(self):
        if self._scanning: return
        self._scanning=True; self._idle_lbl.pack_forget()
        self._scan_btn.configure(state="disabled",text="⏳  SCANNING…")
        for w in self._summary_host.winfo_children(): w.destroy()
        for w in self._results_host.winfo_children(): w.destroy()
        self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.set(0)
        self._animate_prog(0)
        threading.Thread(target=self._do_scan,daemon=True).start()

    def _animate_prog(self,v):
        if v<0.88:
            try:
                if not self.winfo_exists(): return
                self._prog.set(v)
            except Exception: return
            safe_after(self, 70, lambda: self._animate_prog(min(v+0.015,0.88)))

    def _do_scan(self):
        def cb(m): safe_after(self, 0, lambda msg=m: self.log.write("INFO",msg))
        cb("Scanning open ports…")
        ports=security_scanner.scan_ports(cb)
        cb("Checking SSH configuration…")
        ssh_issues=security_scanner.check_ssh()
        cb("Checking firewall status…")
        fw_active,fw_out=security_scanner.check_firewall()
        cb("Checking SUID files…")
        suid=security_scanner.check_suid()
        cb("Checking world-writable files…")
        ww=security_scanner.check_world_writable()
        safe_after(self, 0, lambda: self._render_results(ports,ssh_issues,fw_active,fw_out,suid,ww))

    def _render_results(self,ports,ssh_issues,fw_active,fw_out,suid,ww):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._scanning=False
        self._scan_btn.configure(state="normal",text="🔒  RUN FULL SCAN")
        try:
            self._prog.set(1.0)
        except Exception: pass
        safe_after(self, 400, self._prog.pack_forget)

        red_ct=sum(1 for p in ports if p.risk=="red")
        amb_ct=sum(1 for p in ports if p.risk=="amber")
        grn_ct=sum(1 for p in ports if p.risk=="green")

        for w in self._summary_host.winfo_children(): w.destroy()
        scard=ctk.CTkFrame(self._summary_host,fg_color=BG2,corner_radius=8,
                           border_width=1,border_color=BORDER)
        scard.pack(fill="x")
        sr=ctk.CTkFrame(scard,fg_color="transparent"); sr.pack(fill="x",padx=18,pady=10)
        for lbl,val,col in [("OPEN PORTS",len(ports),CYAN),
                             ("HIGH RISK",red_ct,RED),
                             ("MEDIUM RISK",amb_ct,AMBER),
                             ("SAFE",grn_ct,GREEN),
                             ("SSH ISSUES",len(ssh_issues),RED if ssh_issues else GREEN),
                             ("FIREWALL","ON" if fw_active else "OFF",GREEN if fw_active else RED)]:
            c=ctk.CTkFrame(sr,fg_color="transparent"); c.pack(side="left",expand=True)
            ctk.CTkLabel(c,text=str(val),font=("Courier New",18,"bold"),text_color=col).pack()
            ctk.CTkLabel(c,text=lbl,font=F_MONO_XS,text_color=T2).pack()

        for w in self._results_host.winfo_children(): w.destroy()

        if ports:
            pc=ctk.CTkFrame(self._results_host,fg_color=BG2,corner_radius=8,
                            border_width=1,border_color=BORDER)
            pc.pack(fill="x",pady=(0,8))
            _card_hdr(pc,f"Open Ports ({len(ports)})",f"{red_ct} high risk",RED if red_ct else AMBER)
            hdr=ctk.CTkFrame(pc,fg_color=BG3,corner_radius=0); hdr.pack(fill="x")
            for txt,w,side in [("PORT",70,"left"),("PROTO",60,"left"),("SERVICE",110,"left"),
                                ("PROCESS",110,"left"),("RISK",90,"left"),("DESCRIPTION",0,"left")]:
                ctk.CTkLabel(hdr,text=txt,font=F_MONO_XS,text_color=T2,width=w if w else 0,anchor="w").pack(
                    side="left",padx=(12 if txt=="PORT" else 4),pady=5,
                    fill="x" if not w else None,expand=(not w))
            ctk.CTkFrame(pc,height=1,fg_color=BORDER).pack(fill="x")
            for p in ports:
                fg,bg,bdr=RISK_COLORS.get(p.risk,(T2,BG3,BORDER))
                row=ctk.CTkFrame(pc,fg_color="transparent"); row.pack(fill="x")
                ctk.CTkLabel(row,text=str(p.port),font=("Courier New",10,"bold"),
                             text_color=fg,width=70,anchor="w").pack(side="left",padx=(12,4),pady=6)
                ctk.CTkLabel(row,text=p.proto,font=F_MONO_XS,text_color=T2,width=60,anchor="w").pack(side="left",padx=4)
                ctk.CTkLabel(row,text=p.service[:14],font=F_LABEL,text_color=T1,width=110,anchor="w").pack(side="left",padx=4)
                ctk.CTkLabel(row,text=p.process[:14],font=F_MONO_XS,text_color=T2,width=110,anchor="w").pack(side="left",padx=4)
                risk_f=ctk.CTkFrame(row,fg_color=bg,corner_radius=3,border_width=1,border_color=bdr)
                risk_f.pack(side="left",padx=4,pady=4)
                icon={"green":"●","amber":"◆","red":"▲"}.get(p.risk,"●")
                ctk.CTkLabel(risk_f,text=f"{icon} {p.risk.upper()}",font=F_MONO_XS,text_color=fg,padx=6,pady=2).pack()
                ctk.CTkLabel(row,text=p.note[:50],font=F_MONO_XS,text_color=T2,anchor="w").pack(
                    side="left",fill="x",expand=True,padx=(8,12))
                ctk.CTkFrame(pc,height=1,fg_color=BORDER).pack(fill="x",padx=14)

        if ssh_issues:
            sc2=ctk.CTkFrame(self._results_host,fg_color=BG2,corner_radius=8,
                             border_width=1,border_color=RED_BORDER)
            sc2.pack(fill="x",pady=(0,8))
            _card_hdr(sc2,"SSH Configuration Issues",f"{len(ssh_issues)} found",RED)
            for msg,risk,_ in ssh_issues:
                fr,bg,bdr=RISK_COLORS.get(risk,(T2,BG3,BORDER))
                row=ctk.CTkFrame(sc2,fg_color="transparent"); row.pack(fill="x",padx=14,pady=6)
                ctk.CTkLabel(row,text="▲",font=("Helvetica",8),text_color=fr).pack(side="left",padx=(0,8))
                ctk.CTkLabel(row,text=msg,font=F_LABEL,text_color=T1,anchor="w").pack(side="left")
                f=ctk.CTkFrame(row,fg_color=bg,corner_radius=3,border_width=1,border_color=bdr)
                ctk.CTkLabel(f,text=risk.upper(),font=F_MONO_XS,text_color=fr,padx=5,pady=2).pack()
                f.pack(side="right")
                ctk.CTkFrame(sc2,height=1,fg_color=BORDER).pack(fill="x",padx=14)

        fw_card=ctk.CTkFrame(self._results_host,fg_color=BG2,corner_radius=8,
                             border_width=1,border_color=GREEN_BORDER if fw_active else RED_BORDER)
        fw_card.pack(fill="x",pady=(0,8))
        fw_col=GREEN if fw_active else RED
        _card_hdr(fw_card,"Firewall","ACTIVE" if fw_active else "INACTIVE",fw_col)
        ctk.CTkLabel(fw_card,text=fw_out[:200] if fw_out else "Status unavailable",
                     font=F_MONO_XS,text_color=T2,anchor="w").pack(anchor="w",padx=14,pady=(6,10))

        if suid:
            suid_card=ctk.CTkFrame(self._results_host,fg_color=BG2,corner_radius=8,
                                   border_width=1,border_color=AMBER_BORDER)
            suid_card.pack(fill="x",pady=(0,8))
            _card_hdr(suid_card,f"SUID Files ({len(suid)})",f"{len(suid)} found",AMBER)
            for f_path in suid[:10]:
                ctk.CTkLabel(suid_card,text=f"  {f_path}",font=F_MONO_XS,text_color=T2,anchor="w").pack(anchor="w",padx=14,pady=2)
            ctk.CTkFrame(suid_card,height=6,fg_color="transparent").pack()

        self.log.write("OK",f"Scan done — {len(ports)} ports, {red_ct} high-risk, {len(ssh_issues)} SSH issues")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 ── FIX VIEW (UPGRADED with FixEngine integration)
# ══════════════════════════════════════════════════════════════════════════════
class FixView(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color="transparent")
        self._issues: List[FixIssue]=[]; self._scanning=False
        self._fix_engine: Optional[FixEngine] = None
        self._scan_result = None
        self._last_summary: Optional[ExecutionSummary] = None
        self._build()

    def _build(self):
        scroll=ctk.CTkScrollableFrame(self,fg_color="transparent",
                                       scrollbar_button_color=BG3,scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both",expand=True,padx=14,pady=14)
        _distro_banner(scroll)

        # ── AUTO FIX HERO CARD ──────────────────────────────────────────────
        hero = ctk.CTkFrame(scroll, fg_color=PURPLE_BG, corner_radius=10,
                             border_width=2, border_color=PURPLE_BORDER)
        hero.pack(fill="x", pady=(0, 12))
        hi = ctk.CTkFrame(hero, fg_color="transparent")
        hi.pack(fill="x", padx=20, pady=16)

        htxt = ctk.CTkFrame(hi, fg_color="transparent")
        htxt.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(htxt, text="🚀  AUTO FIX SYSTEM",
                      font=("Courier New", 18, "bold"), text_color=PURPLE).pack(anchor="w")
        ctk.CTkLabel(htxt, text="One-click AI-powered system repair · Priority-ordered · Safe execution",
                      font=F_MONO_SM, text_color=T2).pack(anchor="w", pady=(4, 0))

        hbtns = ctk.CTkFrame(hi, fg_color="transparent")
        hbtns.pack(side="right")

        self._autofix_dry_btn = ctk.CTkButton(
            hbtns, text="~ DRY RUN", width=110, height=36,
            font=("Courier New", 10, "bold"),
            fg_color=BG3, hover_color=BG4, text_color=CYAN,
            corner_radius=6, border_width=1, border_color=CYAN_BORDER,
            command=self._auto_fix_dry)
        self._autofix_dry_btn.pack(side="left", padx=(0, 8))

        self._autofix_btn = ctk.CTkButton(
            hbtns, text="🚀  AUTO FIX", width=140, height=36,
            font=("Courier New", 11, "bold"),
            fg_color=PURPLE, hover_color="#7c3aed", text_color="#ffffff",
            corner_radius=6, command=self._confirm_auto_fix)
        self._autofix_btn.pack(side="left")

        self._autofix_status = ctk.CTkLabel(
            hero, text="  Detect issues first, then use AUTO FIX to repair automatically.",
            font=F_MONO_XS, text_color=T2)
        self._autofix_status.pack(anchor="w", padx=20, pady=(0, 12))

        # ── DETECT + FIX ALL ROW ────────────────────────────────────────────
        top=ctk.CTkFrame(scroll,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        top.pack(fill="x",pady=(0,10))
        tc=ctk.CTkFrame(top,fg_color="transparent"); tc.pack(fill="x",padx=16,pady=12)
        ctk.CTkLabel(tc,text="🔧  FIX SYSTEM",font=("Courier New",14,"bold"),text_color=CYAN).pack(side="left")
        _section_tag(tc,f"{distro.family.upper()}").pack(side="right")
        ctk.CTkFrame(top,height=1,fg_color=BORDER).pack(fill="x")
        br=ctk.CTkFrame(top,fg_color="transparent"); br.pack(padx=16,pady=10)
        self._detect_btn=ctk.CTkButton(br,text="🔍  DETECT ISSUES",width=160,height=34,
            font=("Courier New",10,"bold"),fg_color=CYAN,hover_color=CYANL,text_color=BG1,
            corner_radius=6,command=self._start_detect)
        self._detect_btn.pack(side="left",padx=(0,8))
        self._fix_all_btn=ctk.CTkButton(br,text="🔧  FIX ALL",width=120,height=34,
            font=("Courier New",10,"bold"),fg_color=BG3,hover_color=BG4,text_color=T2,
            corner_radius=6,state="disabled",command=self._fix_all)
        self._fix_all_btn.pack(side="left")

        self._prog=ctk.CTkProgressBar(scroll,height=3,corner_radius=0,fg_color=BG3,progress_color=CYAN)
        self._prog.set(0); self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.pack_forget()

        self._issues_host=ctk.CTkFrame(scroll,fg_color="transparent")
        self._issues_host.pack(fill="x",pady=(0,8))
        self._idle_lbl=ctk.CTkLabel(scroll,
            text="Click 🔍 DETECT ISSUES to diagnose broken packages, security problems, and performance issues.",
            font=F_MONO_SM,text_color=T2)
        self._idle_lbl.pack(pady=30)

        self.log=LogBox(scroll,height=130)
        self.log.pack(fill="x",pady=(0,4))
        self.log.write("INFO","Fix engine ready — " + distro.label)
        if _HAS_FIX_ENGINE:
            self.log.write("OK","FixEngine v4.2 Enterprise loaded — AUTO FIX available")
        else:
            self.log.write("WARN","FixEngine not available — using legacy fix mode")

    # ── Auto Fix ──────────────────────────────────────────────────────────────

    def _confirm_auto_fix(self):
        if not self._issues and self._scan_result is None:
            self.log.write("WARN", "Run DETECT ISSUES first before using AUTO FIX")
            return

        def _proceed():
            self._run_auto_fix(dry_run=False)

        ConfirmDialog(
            self.winfo_toplevel(),
            title="Confirm AUTO FIX",
            message=(
                "AUTO FIX will apply all safe, priority-ordered fixes automatically.\n\n"
                "• Dangerous fixes will still require individual confirmation\n"
                "• A rollback snapshot will be created first\n"
                "• You can revert changes from the ROLLBACK tab\n\n"
                "Proceed with AUTO FIX?"
            ),
            on_confirm=_proceed,
            danger=False
        )

    def _auto_fix_dry(self):
        if not self._issues and self._scan_result is None:
            self.log.write("WARN", "Run DETECT ISSUES first")
            return
        self._run_auto_fix(dry_run=True)

    def _run_auto_fix(self, dry_run: bool):
        if not _HAS_FIX_ENGINE:
            self.log.write("ERR", "FixEngine not available — cannot run AUTO FIX")
            return

        mode = "DRY RUN" if dry_run else "LIVE"
        self.log.write("RUN", f"AUTO FIX starting ({mode} mode)…")
        self._autofix_btn.configure(state="disabled", text="⏳  FIXING…")
        self._autofix_dry_btn.configure(state="disabled")
        self._autofix_status.configure(
            text=f"  {'Simulating' if dry_run else 'Applying'} fixes…",
            text_color=CYAN)

        def _worker():
            try:
                if self._fix_engine is None:
                    self._fix_engine = FixEngine(confirm_fn=self._gui_confirm)

                scan_proxy = _ScanResultProxy(self._issues)
                summary = self._fix_engine.apply_all_fixes(
                    scan_proxy, dry_run=dry_run, confirm_all=not dry_run)
                safe_after(self, 0, lambda s=summary: self._auto_fix_done(s, dry_run))
            except Exception as exc:
                _log("error", f"AUTO FIX error: {exc}")
                safe_after(self, 0, lambda e=str(exc): self._auto_fix_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _gui_confirm(self, prompt: str) -> bool:
        result_holder = [False]
        done_event = threading.Event()

        def _show():
            dlg = ctk.CTkToplevel(self.winfo_toplevel())
            dlg.title("JENIX — Confirm Fix")
            dlg.geometry("500x240")
            dlg.configure(fg_color=BG1)
            dlg.grab_set(); dlg.lift()
            ctk.CTkFrame(dlg, height=3, fg_color=AMBER, corner_radius=0).pack(fill="x")
            body = ctk.CTkFrame(dlg, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=20, pady=16)
            ctk.CTkLabel(body, text="⚠  Confirm Fix Action",
                          font=("Courier New", 12, "bold"), text_color=AMBER).pack(anchor="w", pady=(0,8))
            mf = ctk.CTkFrame(body, fg_color=BG2, corner_radius=6, border_width=1, border_color=BORDER)
            mf.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(mf, text=prompt[:300], font=F_MONO_XS, text_color=T1,
                          wraplength=440, justify="left").pack(anchor="w", padx=12, pady=10)
            br = ctk.CTkFrame(body, fg_color="transparent")
            br.pack(fill="x")

            def _yes():
                result_holder[0] = True
                done_event.set()
                dlg.destroy()

            def _no():
                done_event.set()
                dlg.destroy()

            ctk.CTkButton(br, text="✓ YES", width=100, height=32,
                           fg_color=AMBER, hover_color="#d49a00", text_color=BG1,
                           font=F_MONO_SM, corner_radius=4,
                           command=_yes).pack(side="left", padx=(0,8))
            ctk.CTkButton(br, text="✕ NO", width=80, height=32,
                           fg_color=BG3, hover_color=BG4, text_color=T2,
                           font=F_MONO_XS, corner_radius=4,
                           command=_no).pack(side="left")

        safe_after(self, 0, _show)
        done_event.wait(timeout=30)
        return result_holder[0]

    def _auto_fix_done(self, summary: ExecutionSummary, dry_run: bool):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._last_summary = summary
        self._autofix_btn.configure(state="normal", text="🚀  AUTO FIX")
        self._autofix_dry_btn.configure(state="normal")

        mode_str = "DRY RUN" if dry_run else "LIVE"
        if summary.applied > 0 and summary.failed == 0:
            status_col = GREEN; status_icon = "✓"
        elif summary.applied > 0:
            status_col = AMBER; status_icon = "⚠"
        else:
            status_col = T2; status_icon = "–"

        self._autofix_status.configure(
            text=f"  {status_icon}  [{mode_str}] {summary.applied} applied · "
                 f"{summary.failed} failed · {summary.skipped} skipped",
            text_color=status_col)

        self.log.write("OK" if summary.applied > 0 else "INFO",
                       f"AUTO FIX complete — {summary.applied} applied, "
                       f"{summary.failed} failed, {summary.skipped} skipped")
        self.log.write("INFO", summary.smart_message[:100])

        AutoFixResultModal(self.winfo_toplevel(), summary)

    def _auto_fix_error(self, err: str):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._autofix_btn.configure(state="normal", text="🚀  AUTO FIX")
        self._autofix_dry_btn.configure(state="normal")
        self._autofix_status.configure(text=f"  ✗ Error: {err[:80]}", text_color=RED)
        self.log.write("ERR", f"AUTO FIX failed: {err}")

    def _start_detect(self):
        if self._scanning: return
        self._scanning=True; self._idle_lbl.pack_forget()
        self._detect_btn.configure(state="disabled",text="⏳  SCANNING…")
        for w in self._issues_host.winfo_children(): w.destroy()
        self._prog.pack(fill="x",padx=14,pady=(0,4)); self._animate_prog(0)
        threading.Thread(target=self._do_detect,daemon=True).start()

    def _animate_prog(self,v):
        if v<0.88:
            try:
                if not self.winfo_exists(): return
                self._prog.set(v)
            except Exception: return
            safe_after(self, 60, lambda: self._animate_prog(min(v+0.014,0.88)))

    def _do_detect(self):
        def cb(m): safe_after(self, 0, lambda msg=m: self.log.write("INFO",msg))
        issues=fix_engine_wrapper.detect(cb)
        safe_after(self, 0, lambda i=issues: self._render_issues(i))

    def _render_issues(self,issues):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._issues=issues; self._scanning=False
        self._detect_btn.configure(state="normal",text="🔍  DETECT ISSUES")
        try:
            self._prog.set(1.0)
        except Exception: pass
        safe_after(self, 400, self._prog.pack_forget)
        for w in self._issues_host.winfo_children(): w.destroy()

        if not issues:
            ok=ctk.CTkFrame(self._issues_host,fg_color="#0a1f06",corner_radius=8,
                            border_width=1,border_color=GREEN_BORDER)
            ok.pack(fill="x")
            ctk.CTkLabel(ok,text="✓  System looks healthy — no critical issues found",
                         font=("Courier New",12,"bold"),text_color=GREEN).pack(pady=14)
            self.log.write("OK","No issues detected")
            self._autofix_status.configure(
                text="  ✓ System appears healthy — no fixes needed.",
                text_color=GREEN)
            return

        SEV_COL={"critical":(RED,RED_BORDER),"high":(AMBER,AMBER_BORDER),
                 "medium":(CYAN,CYAN_BORDER),"low":(T2,BORDER)}
        crit=sum(1 for i in issues if i.severity=="critical")
        card=ctk.CTkFrame(self._issues_host,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        card.pack(fill="x")
        _card_hdr(card,f"{len(issues)} Issues Detected",f"{crit} critical",RED if crit else AMBER)

        self._autofix_status.configure(
            text=f"  {len(issues)} issues detected ({crit} critical) — ready for AUTO FIX",
            text_color=RED if crit else AMBER)

        self._fix_btns: Dict[int,ctk.CTkButton]={}
        for i,issue in enumerate(issues):
            col,bdr=SEV_COL.get(issue.severity,(T2,BORDER))
            row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x",padx=14,pady=(8,0))
            top_r=ctk.CTkFrame(row,fg_color="transparent"); top_r.pack(fill="x")

            f=ctk.CTkFrame(top_r,fg_color=_bbg(col),corner_radius=3,border_width=1,border_color=bdr)
            ctk.CTkLabel(f,text=issue.severity.upper(),font=F_MONO_XS,text_color=col,padx=5,pady=2).pack()
            f.pack(side="left",padx=(0,8))

            ctk.CTkLabel(top_r,text=issue.title,font=F_LABEL,text_color=T1,anchor="w").pack(side="left",fill="x",expand=True)

            btn_grp = ctk.CTkFrame(top_r, fg_color="transparent")
            btn_grp.pack(side="right")

            can_fix = not issue.fix_cmd.startswith("#") and not issue.fixed

            if can_fix:
                dry_btn = ctk.CTkButton(
                    btn_grp, text="~ DRY", width=60, height=24,
                    font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                    text_color=CYAN, corner_radius=4,
                    border_width=1, border_color=CYAN_BORDER,
                    command=lambda idx=i: self._fix_one(idx, dry_run=True))
                dry_btn.pack(side="left", padx=(0, 4))

            fix_btn = ctk.CTkButton(
                btn_grp,
                text="✓ Fixed" if issue.fixed else "⚡ Fix",
                width=70, height=24, font=F_MONO_XS,
                fg_color=GREEN if issue.fixed else col,
                hover_color="#2acc0e" if issue.fixed else CYANL,
                text_color=BG1, corner_radius=4,
                state="disabled" if issue.fixed or not can_fix else "normal",
                command=lambda idx=i: self._confirm_fix_one(idx))
            fix_btn.pack(side="left", padx=(0, 4))
            self._fix_btns[i] = fix_btn

            if issue.fixed and issue.revert_cmd and not issue.revert_cmd.startswith("#"):
                rb_btn = ctk.CTkButton(
                    btn_grp, text="↩", width=40, height=24,
                    font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                    text_color=AMBER, corner_radius=4,
                    border_width=1, border_color=AMBER_BORDER,
                    command=lambda idx=i: self._rollback_issue(idx))
                rb_btn.pack(side="left")

            ctk.CTkLabel(row,text=issue.detail[:120] if issue.detail else "",
                         font=F_MONO_XS,text_color=T2,anchor="w",wraplength=520).pack(anchor="w",pady=(2,6))

            if not issue.fix_cmd.startswith("#") and issue.fix_cmd:
                cf=ctk.CTkFrame(row,fg_color=BG3,corner_radius=4); cf.pack(fill="x",pady=(0,6))
                ctk.CTkLabel(cf,text="$  "+issue.fix_cmd[:100],font=F_MONO_XS,
                             text_color=CYAN,anchor="w").pack(anchor="w",padx=8,pady=4)
            elif issue.fix_cmd.startswith("#"):
                cf=ctk.CTkFrame(row,fg_color="#2a1500",corner_radius=4,
                                border_width=1,border_color=AMBER_BORDER)
                cf.pack(fill="x",pady=(0,6))
                ctk.CTkLabel(cf,text="⚠  "+issue.fix_cmd[2:],font=F_MONO_XS,
                             text_color=AMBER,anchor="w").pack(anchor="w",padx=8,pady=4)

            if i<len(issues)-1:
                ctk.CTkFrame(card,height=1,fg_color=BORDER).pack(fill="x",padx=14)
        ctk.CTkFrame(card,height=6,fg_color="transparent").pack()
        self._fix_all_btn.configure(state="normal",fg_color=CYAN,hover_color=CYANL,text_color=BG1)
        self.log.write("OK",f"Detected {len(issues)} issues — {crit} critical")

    def _fix_one(self, idx: int, dry_run: bool = False):
        issue = self._issues[idx]
        if issue.fix_cmd.startswith("#"):
            self.log.write("WARN", f"Manual action required: {issue.fix_cmd}")
            return
        mode = "DRY RUN" if dry_run else "LIVE"
        self.log.write("RUN", f"[{mode}] Fixing: {issue.title}")
        if dry_run:
            self.log.write("INFO", f"Would run: {issue.fix_cmd[:100]}")
            self.log.write("OK", f"Dry run complete for: {issue.title}")
            return
        def _do():
            ok, out = fix_engine_wrapper.apply_fix(issue)
            def _done(success=ok, output=out, title=issue.title):
                if success:
                    self.log.write("OK", f"Fixed: {title}")
                    self._render_issues(self._issues)
                else:
                    self.log.write("ERR", f"Failed: {title} — {output[:80]}")
            safe_after(self, 0, _done)
        threading.Thread(target=_do, daemon=True).start()

    def _fix_all(self):
        unfixed = [i for i in self._issues if not i.fixed and not i.fix_cmd.startswith("#")]
        if not unfixed:
            self.log.write("INFO", "No fixable issues remaining")
            return
        self.log.write("RUN", f"Fixing {len(unfixed)} issues…")
        self._fix_all_btn.configure(state="disabled", text="⏳  FIXING…")
        def _do():
            ok = fail = 0
            for issue in unfixed:
                success, out = fix_engine_wrapper.apply_fix(issue)
                if success:
                    ok += 1
                    safe_after(self, 0, lambda t=issue.title: self.log.write("OK", f"Fixed: {t}"))
                else:
                    fail += 1
                    safe_after(self, 0, lambda t=issue.title, o=out: self.log.write("ERR", f"Failed: {t} — {o[:60]}"))
            def _done():
                self.log.write("OK" if fail == 0 else "WARN",
                               f"Fix all complete — {ok} fixed, {fail} failed")
                self._fix_all_btn.configure(state="normal", text="🔧  FIX ALL")
                self._render_issues(self._issues)
            safe_after(self, 0, _done)
        threading.Thread(target=_do, daemon=True).start()

    def _rollback_issue(self, idx: int):
        issue = self._issues[idx]
        self.log.write("RUN", f"Rolling back: {issue.title}")
        rc, out, err = run(issue.revert_cmd, timeout=60)
        if rc == 0:
            issue.fixed = False
            self.log.write("OK", f"Reverted: {issue.title}")
            self._render_issues(self._issues)
        else:
            self.log.write("ERR", f"Revert failed: {err[:80]}")

    def _confirm_fix_one(self, idx: int):
        issue = self._issues[idx]
        def _proceed():
            self._fix_one(idx, dry_run=False)
        ConfirmDialog(
            self.winfo_toplevel(),
            title="Confirm Fix",
            message=f"Apply fix for:\n{issue.title}\n\nCommand: {issue.fix_cmd[:120]}",
            on_confirm=_proceed,
            danger=False
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 15 ── ROLLBACK VIEW
# ══════════════════════════════════════════════════════════════════════════════
class RollbackView(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                        scrollbar_button_color=BG3,
                                        scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both", expand=True, padx=14, pady=14)

        top = ctk.CTkFrame(scroll, fg_color=BG2, corner_radius=8,
                           border_width=1, border_color=BORDER)
        top.pack(fill="x", pady=(0, 10))
        tc = ctk.CTkFrame(top, fg_color="transparent")
        tc.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(tc, text="↩  ROLLBACK MANAGER",
                     font=("Courier New", 14, "bold"),
                     text_color=AMBER).pack(side="left")
        ctk.CTkLabel(tc, text=f"Tracked: {rollback.count} actions",
                     font=F_MONO_XS, text_color=T2).pack(side="right")
        ctk.CTkFrame(top, height=1, fg_color=BORDER).pack(fill="x")

        br = ctk.CTkFrame(top, fg_color="transparent")
        br.pack(padx=16, pady=10)
        ctk.CTkButton(br, text="↩  ROLLBACK ALL", width=160, height=34,
                      font=("Courier New", 10, "bold"),
                      fg_color=AMBER, hover_color="#d49a00", text_color=BG1,
                      corner_radius=6,
                      command=self._confirm_rollback_all).pack(side="left", padx=(0, 8))
        ctk.CTkButton(br, text="🗑  CLEAR HISTORY", width=150, height=34,
                      font=("Courier New", 10, "bold"),
                      fg_color=BG3, hover_color=BG4, text_color=RED,
                      corner_radius=6, border_width=1, border_color=RED_BORDER,
                      command=self._confirm_clear).pack(side="left")

        # Snapshot button
        ctk.CTkButton(br, text="📸  SNAPSHOT", width=130, height=34,
                      font=("Courier New", 10, "bold"),
                      fg_color=BG3, hover_color=BG4, text_color=CYAN,
                      corner_radius=6, border_width=1, border_color=CYAN_BORDER,
                      command=self._take_snapshot).pack(side="left", padx=(8, 0))

        # Entries list
        self._entries_host = ctk.CTkFrame(scroll, fg_color="transparent")
        self._entries_host.pack(fill="x", pady=(0, 10))
        self._render_entries()

        self.log = LogBox(scroll, height=120)
        self.log.pack(fill="x", pady=(0, 4))
        self.log.write("INFO", f"Rollback manager · {rollback.count} tracked actions")

    def _render_entries(self):
        for w in self._entries_host.winfo_children():
            w.destroy()

        entries = rollback.entries
        if not entries:
            empty = ctk.CTkFrame(self._entries_host, fg_color=BG2,
                                 corner_radius=8, border_width=1,
                                 border_color=BORDER)
            empty.pack(fill="x")
            ctk.CTkLabel(empty,
                         text="No rollback entries recorded yet.\nActions from Boost, Clean, and Fix tabs are tracked here.",
                         font=F_MONO_SM, text_color=T2).pack(pady=20)
            return

        card = ctk.CTkFrame(self._entries_host, fg_color=BG2,
                             corner_radius=8, border_width=1,
                             border_color=BORDER)
        card.pack(fill="x")
        _card_hdr(card, f"Rollback History ({len(entries)} entries)",
                  f"{rollback.count} total", AMBER)

        for i, entry in enumerate(reversed(entries)):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(6, 0))

            top_r = ctk.CTkFrame(row, fg_color="transparent")
            top_r.pack(fill="x")

            # Category badge
            cat = getattr(entry, "category", "action")
            cat_col = {"boost": CYAN, "clean": GREEN,
                       "fix": AMBER, "rollback": RED}.get(cat, T2)
            cf = ctk.CTkFrame(top_r, fg_color=_bbg(cat_col),
                               corner_radius=3, border_width=1,
                               border_color=_bbd(cat_col))
            ctk.CTkLabel(cf, text=cat.upper(), font=F_MONO_XS,
                          text_color=cat_col, padx=5, pady=2).pack()
            cf.pack(side="left", padx=(0, 8))

            desc = getattr(entry, "description", str(entry))
            ctk.CTkLabel(top_r, text=desc[:80], font=F_LABEL,
                          text_color=T1, anchor="w").pack(
                side="left", fill="x", expand=True)

            entry_id = getattr(entry, "entry_id", str(i))
            ctk.CTkButton(top_r, text="↩ Revert", width=80, height=24,
                           font=F_MONO_XS, fg_color=BG3, hover_color=BG4,
                           text_color=AMBER, corner_radius=4,
                           border_width=1, border_color=AMBER_BORDER,
                           command=lambda eid=entry_id: self._revert_one(eid)
                           ).pack(side="right")

            revert_cmd = getattr(entry, "revert_cmd", "")
            if revert_cmd:
                cf2 = ctk.CTkFrame(row, fg_color=BG3, corner_radius=4)
                cf2.pack(fill="x", pady=(2, 6))
                ctk.CTkLabel(cf2, text="$  " + str(revert_cmd)[:100],
                              font=F_MONO_XS, text_color=CYAN,
                              anchor="w").pack(anchor="w", padx=8, pady=4)

            if i < len(entries) - 1:
                ctk.CTkFrame(card, height=1, fg_color=BORDER).pack(
                    fill="x", padx=14)

        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

    def rollback_action(self):
        self._confirm_rollback_all()

    def _revert_one(self, entry_id: str):
        try:
            result = rollback.revert(entry_id)
            if result and getattr(result, "success", False):
                self.log.write("OK", f"Reverted: {getattr(result, 'description', entry_id)}")
            else:
                err = getattr(result, "error", "unknown error") if result else "no result"
                self.log.write("WARN", f"Revert failed: {err}")
        except Exception as e:
            self.log.write("ERR", f"Revert error: {e}")
        self._render_entries()

    def _confirm_rollback_all(self):
        if not rollback.has_history:
            self.log.write("INFO", "No rollback history to revert")
            return

        def _proceed():
            self._do_rollback_all()

        ConfirmDialog(
            self.winfo_toplevel(),
            title="Confirm Rollback All",
            message=(
                "This will revert ALL tracked actions.\n\n"
                "This cannot be undone. Proceed?"
            ),
            on_confirm=_proceed,
            danger=True
        )

    def _do_rollback_all(self):
        self.log.write("RUN", "Rolling back all actions…")
        try:
            results = rollback.revert_all()
            ok  = sum(1 for r in results if getattr(r, "success", False))
            fail = len(results) - ok
            self.log.write("OK" if fail == 0 else "WARN",
                           f"Rollback complete — {ok} ok, {fail} failed")
        except Exception as e:
            self.log.write("ERR", f"Rollback error: {e}")
        self._render_entries()

    def _confirm_clear(self):
        def _proceed():
            rollback.clear()
            self.log.write("OK", "Rollback history cleared")
            self._render_entries()

        ConfirmDialog(
            self.winfo_toplevel(),
            title="Clear History",
            message="Clear all rollback history? This cannot be undone.",
            on_confirm=_proceed,
            danger=True
        )

    def _take_snapshot(self):
        self.log.write("RUN", "Taking package snapshot…")
        def _do():
            try:
                snap = rollback.snapshot_packages("manual")
                level = "OK" if snap.get("status") == "success" else "WARN"
                safe_after(self, 0, lambda m=snap.get("message","done"):
                           self.log.write(level, f"Snapshot: {m}"))
            except Exception as e:
                safe_after(self, 0, lambda err=str(e):
                           self.log.write("ERR", f"Snapshot error: {err}"))
            safe_after(self, 0, self._render_entries)
        import threading
        threading.Thread(target=_do, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 16 ── AI VIEW  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════
PRIORITY_STYLE={"Critical":(RED,"#2a0808",RED_BORDER,"🔴"),
                "High":    (AMBER,"#1f1600",AMBER_BORDER,"🟠"),
                "Medium":  (CYAN,"#001e26",CYAN_BORDER,"🟡"),
                "Low":     (GREEN,"#0a1f06",GREEN_BORDER,"🟢")}
CAT_ICONS={"Security":"🔒","Performance":"⚡","Packages":"📦","Storage":"💾",
           "Network":"🌐","Health":"🩺","Tools":"🔧"}

class AIView(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color="transparent")
        self._recs: List[AIRecommendation]=[]; self._running=False
        self._build()

    def _build(self):
        top=ctk.CTkFrame(self,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        top.pack(fill="x",padx=14,pady=(14,8))
        tc=ctk.CTkFrame(top,fg_color="transparent"); tc.pack(fill="x",padx=16,pady=12)
        ctk.CTkLabel(tc,text="🤖  AI RECOMMENDATIONS",font=("Courier New",13,"bold"),text_color=CYAN).pack(side="left")
        self._status=ctk.CTkLabel(tc,text="Click ANALYSE",font=F_MONO_XS,text_color=T2); self._status.pack(side="right")
        ctk.CTkFrame(top,height=1,fg_color=BORDER).pack(fill="x")
        br=ctk.CTkFrame(top,fg_color="transparent"); br.pack(padx=16,pady=10)
        ctk.CTkLabel(br,text=f"Distro: {distro.label}",font=F_MONO_XS,text_color=T2).pack(side="left",padx=(0,16))
        self._btn=ctk.CTkButton(br,text="★  ANALYSE NOW",width=150,height=30,
            font=("Courier New",10,"bold"),fg_color=CYAN,hover_color=CYANL,text_color=BG1,
            corner_radius=6,command=self._run)
        self._btn.pack(side="left")

        self._prog=ctk.CTkProgressBar(self,height=3,corner_radius=0,fg_color=BG3,progress_color=CYAN)
        self._prog.set(0); self._prog.pack(fill="x",padx=14,pady=(0,4)); self._prog.pack_forget()

        self._summary=ctk.CTkFrame(self,fg_color="transparent"); self._summary.pack(fill="x",padx=14,pady=(0,4))
        self._filter=ctk.CTkFrame(self,fg_color="transparent"); self._filter.pack(fill="x",padx=14,pady=(0,6))

        self._scroll=ctk.CTkScrollableFrame(self,fg_color="transparent",
                                             scrollbar_button_color=BG3,scrollbar_button_hover_color=BG4)
        self._scroll.pack(fill="both",expand=True,padx=14,pady=(0,14))
        self._idle=ctk.CTkLabel(self._scroll,
            text="Press ★ ANALYSE NOW to scan your system for AI-powered recommendations.",
            font=F_MONO_SM,text_color=T2)
        self._idle.pack(pady=40)

    def _run(self):
        if self._running: return
        self._running=True; self._idle.pack_forget()
        self._btn.configure(state="disabled",text="⏳  ANALYSING…")
        self._status.configure(text="🔄  Scanning…",text_color=CYAN)
        self._prog.pack(fill="x",padx=14,pady=(0,4)); self._animate(0)
        def _do():
            recs=ai_advisor.analyse()
            safe_after(self, 0, lambda r=recs: self._render(r))
        threading.Thread(target=_do,daemon=True).start()

    def _animate(self,v):
        if v<0.9:
            try:
                if not self.winfo_exists(): return
                self._prog.set(v)
            except Exception: return
            safe_after(self, 70, lambda: self._animate(min(v+0.012,0.9)))

    def _render(self,recs):
        try:
            if not self.winfo_exists(): return
        except Exception: return
        self._recs=recs; self._running=False
        self._btn.configure(state="normal",text="★  ANALYSE NOW")
        try:
            self._prog.set(1.0)
        except Exception: pass
        safe_after(self, 300, self._prog.pack_forget)
        crit=sum(1 for r in recs if r.priority=="Critical")
        high=sum(1 for r in recs if r.priority=="High")
        col=RED if crit else AMBER if high else GREEN
        self._status.configure(text=f"✓ {len(recs)} recs · {crit} critical · {high} high",text_color=col)

        for w in self._summary.winfo_children(): w.destroy()
        sc=ctk.CTkFrame(self._summary,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        sc.pack(fill="x")
        sr=ctk.CTkFrame(sc,fg_color="transparent"); sr.pack(fill="x",padx=18,pady=10)
        counts={}
        for r in recs: counts[r.priority]=counts.get(r.priority,0)+1
        for pri,(fg,bg,bdr,icon) in PRIORITY_STYLE.items():
            c=ctk.CTkFrame(sr,fg_color="transparent"); c.pack(side="left",expand=True)
            ctk.CTkLabel(c,text=str(counts.get(pri,0)),font=("Courier New",18,"bold"),text_color=fg).pack()
            ctk.CTkLabel(c,text=f"{icon} {pri}",font=F_MONO_XS,text_color=T2).pack()

        for w in self._filter.winfo_children(): w.destroy()
        fc=ctk.CTkFrame(self._filter,fg_color=BG2,corner_radius=8,border_width=1,border_color=BORDER)
        fc.pack(fill="x")
        fr=ctk.CTkFrame(fc,fg_color="transparent"); fr.pack(fill="x",padx=14,pady=6)
        ctk.CTkLabel(fr,text="Filter:",font=F_MONO_XS,text_color=T2).pack(side="left",padx=(0,8))
        self._pri_var=ctk.StringVar(value="All")
        ctk.CTkOptionMenu(fr,values=["All","Critical","High","Medium","Low"],
                          variable=self._pri_var,fg_color=BG3,button_color=BG4,
                          dropdown_fg_color=BG3,text_color=T1,font=F_MONO_XS,
                          width=110,height=26,
                          command=lambda v: self._filter_cards(v,self._cat_var.get())).pack(side="left",padx=(0,10))
        ctk.CTkLabel(fr,text="Category:",font=F_MONO_XS,text_color=T2).pack(side="left",padx=(0,8))
        self._cat_var=ctk.StringVar(value="All")
        cats=["All"]+list(dict.fromkeys(r.category for r in recs))
        ctk.CTkOptionMenu(fr,values=cats,variable=self._cat_var,
                          fg_color=BG3,button_color=BG4,dropdown_fg_color=BG3,
                          text_color=T1,font=F_MONO_XS,width=130,height=26,
                          command=lambda v: self._filter_cards(self._pri_var.get(),v)).pack(side="left")

        self._filter_cards("All","All")

    def _filter_cards(self,pri,cat):
        filtered=[r for r in self._recs
                  if (pri=="All" or r.priority==pri) and (cat=="All" or r.category==cat)]
        for w in self._scroll.winfo_children(): w.destroy()
        if not filtered:
            ctk.CTkLabel(self._scroll,text="No recommendations match filters.",
                         font=F_MONO_SM,text_color=T2).pack(pady=30); return
        for i,rec in enumerate(filtered,1):
            fg,bg,bdr,icon=PRIORITY_STYLE.get(rec.priority,(T2,BG3,BORDER,"⚪"))
            card=ctk.CTkFrame(self._scroll,fg_color=BG2,corner_radius=8,
                              border_width=1,border_color=bdr)
            card.pack(fill="x",pady=(0,8))
            hdr=ctk.CTkFrame(card,fg_color="transparent"); hdr.pack(fill="x",padx=12,pady=(10,4))
            bf=ctk.CTkFrame(hdr,fg_color=bg,corner_radius=4,border_width=1,border_color=bdr)
            ctk.CTkLabel(bf,text=f"{icon} {rec.priority}",font=F_MONO_XS,text_color=fg,padx=6,pady=2).pack()
            bf.pack(side="left",padx=(0,8))
            cat_i=CAT_ICONS.get(rec.category,"•")
            ctk.CTkLabel(hdr,text=f"{cat_i}  {rec.category}",
                         font=("Helvetica",9,"bold"),text_color=T2).pack(side="left")
            ctk.CTkLabel(hdr,text=f"#{i:02d}",font=F_MONO_XS,text_color=T2).pack(side="right")
            ctk.CTkLabel(card,text=rec.title,font=F_LABEL,text_color=T1,
                         anchor="w",wraplength=520).pack(anchor="w",padx=12,pady=(0,4))
            if rec.detail:
                ctk.CTkLabel(card,text=rec.detail,font=F_MONO_XS,text_color=T2,
                             anchor="w",wraplength=520,justify="left").pack(anchor="w",padx=12,pady=(0,6))
            if rec.command:
                cf=ctk.CTkFrame(card,fg_color=BG3,corner_radius=6)
                cf.pack(fill="x",padx=12,pady=(0,10))
                ctk.CTkLabel(cf,text="$  "+rec.command,font=("Courier New",9),
                             text_color=CYAN,anchor="w",wraplength=500).pack(anchor="w",padx=10,pady=6)
            if not rec.safe:
                wf=ctk.CTkFrame(card,fg_color="#2a1500",corner_radius=4,
                                border_width=1,border_color=AMBER_BORDER)
                wf.pack(fill="x",padx=12,pady=(0,10))
                ctk.CTkLabel(wf,text="⚠  Review carefully — modifies system config",
                             font=F_MONO_XS,text_color=AMBER,padx=8,pady=4).pack(anchor="w")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 17 ── GRAPH VIEW  ── FIX 4 applied (Event-based loop, real I/O deltas)
# ══════════════════════════════════════════════════════════════════════════════
class GraphView(ctk.CTkFrame):
    MAX = 50

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        # Use an Event so the loop thread wakes instantly on shutdown
        self._stop_event = threading.Event()
        self._paused = False
        self._data = {k: [0.0] * self.MAX for k in ("cpu", "ram", "disk", "net")}
        self._lock = threading.Lock()
        self._mpl_canvas = None
        self._mpl_widget = None
        self._fig = None
        # Baseline counters for I/O delta calculations
        self._prev_net  = None
        self._prev_disk = None
        self._prev_ts   = None
        self._build()
        threading.Thread(target=self._loop, daemon=True).start()

    def _build(self):
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import psutil
        except ImportError as e:
            ctk.CTkLabel(
                self,
                text=f"Graph unavailable\n(missing: {e})",
                font=("Courier New", 13),
                text_color=T2,
            ).pack(expand=True)
            self._stop_event.set()
            return

        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=BG3)
        scroll.pack(fill="both", expand=True, padx=14, pady=14)

        # Header
        h = ctk.CTkFrame(scroll, fg_color=BG2, corner_radius=8,
                         border_width=1, border_color=BORDER)
        h.pack(fill="x", pady=(0, 10))
        hi = ctk.CTkFrame(h, fg_color="transparent")
        hi.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(hi, text="▦  Performance Dashboard",
                     font=F_TITLE, text_color=T1).pack(side="left")
        _section_tag(hi, "LIVE  ●").pack(side="right")

        self._monitor_btn = ctk.CTkButton(
            hi, text="⏸ PAUSE", width=100, height=28,
            font=("Courier New", 9, "bold"),
            fg_color=BG3, hover_color=BG4, text_color=AMBER,
            corner_radius=4, border_width=1, border_color=AMBER_BORDER,
            command=self.toggle_monitoring,
        )
        self._monitor_btn.pack(side="right", padx=(0, 8))

        # Pill row (4 stat cards) — show real units
        pill_row = ctk.CTkFrame(scroll, fg_color="transparent")
        pill_row.pack(fill="x", pady=(0, 10))
        pill_row.columnconfigure((0, 1, 2, 3), weight=1, uniform="p")

        self._pills = {}
        for i, (k, lbl, col) in enumerate([
            ("cpu",  "CPU",      CYAN),
            ("ram",  "RAM",      AMBER),
            ("disk", "DISK I/O", GREEN),
            ("net",  "NET I/O",  CYAN),
        ]):
            c = ctk.CTkFrame(pill_row, fg_color=BG2, corner_radius=8,
                              border_width=1, border_color=BORDER)
            c.grid(row=0, column=i,
                   padx=(0 if i == 0 else 4, 0), sticky="nsew")
            ctk.CTkLabel(c, text=lbl, font=F_MONO_XS, text_color=T2).pack(pady=(8, 0))
            lbl_widget = ctk.CTkLabel(
                c, text="—", font=("Courier New", 16, "bold"), text_color=col)
            lbl_widget.pack()
            ctk.CTkFrame(c, height=6, fg_color="transparent").pack()
            self._pills[k] = lbl_widget

        # Matplotlib figure — 4 stacked subplots
        fig = Figure(figsize=(8, 5), dpi=96, facecolor=BG2)
        fig.subplots_adjust(hspace=0.55, left=0.07, right=0.97,
                            top=0.92, bottom=0.08)

        self._axes = {}
        self._lines = {}
        self._fills = {}

        for i, (k, yl, col) in enumerate([
            ("cpu",  "CPU %",     CYAN),
            ("ram",  "RAM %",     AMBER),
            ("disk", "Disk MB/s", GREEN),
            ("net",  "Net MB/s",  "#00aaff"),
        ]):
            ax = fig.add_subplot(4, 1, i + 1)
            ax.set_facecolor(BG1)
            ax.set_ylim(0, 100)
            ax.set_xlim(0, self.MAX - 1)
            ax.tick_params(colors=T2, labelsize=7)
            for sp in ax.spines.values():
                sp.set_edgecolor(BORDER)
            ax.set_ylabel(yl, color=T2, fontsize=7, labelpad=4)
            ax.grid(True, color=BORDER, linewidth=0.5,
                    linestyle="--", alpha=0.6)
            ax.set_xticks([])
            xs = list(range(self.MAX))
            ys = list(self._data[k])
            fill = ax.fill_between(xs, ys, alpha=0.15, color=col)
            (ln,) = ax.plot(xs, ys, color=col, linewidth=1.4)
            self._axes[k] = ax
            self._lines[k] = ln
            self._fills[k] = fill

        cf = ctk.CTkFrame(scroll, fg_color=BG2, corner_radius=8,
                           border_width=1, border_color=BORDER)
        cf.pack(fill="x", pady=(0, 10))

        self._mpl_canvas = FigureCanvasTkAgg(fig, master=cf)
        self._mpl_widget = self._mpl_canvas.get_tk_widget()
        self._mpl_widget.pack(fill="both", expand=True, padx=4, pady=4)
        self._fig = fig
        self._mpl_canvas.draw()

    # ── Real metric collection ─────────────────────────────────────────────

    def _collect(self):
        """
        Collect real system metrics using psutil I/O counter deltas.
        Returns (cpu_pct, ram_pct, disk_mb_s, net_mb_s).
        All values are floats >= 0.
        """
        import psutil, time as _t

        now = _t.monotonic()

        try:
            cpu = float(psutil.cpu_percent(interval=1))
        except Exception:
            cpu = 0.0

        try:
            ram = float(psutil.virtual_memory().percent)
        except Exception:
            ram = 0.0

        # Disk I/O delta
        disk_mb = 0.0
        try:
            curr_disk = psutil.disk_io_counters()
            if curr_disk and self._prev_disk and self._prev_ts:
                dt = max(now - self._prev_ts, 0.001)
                delta = (
                    (curr_disk.read_bytes  - self._prev_disk.read_bytes) +
                    (curr_disk.write_bytes - self._prev_disk.write_bytes)
                )
                disk_mb = max(0.0, delta / dt / 1_048_576)
            self._prev_disk = curr_disk
        except Exception:
            self._prev_disk = None

        # Network I/O delta
        net_mb = 0.0
        try:
            curr_net = psutil.net_io_counters()
            if curr_net and self._prev_net and self._prev_ts:
                dt = max(now - self._prev_ts, 0.001)
                delta = (
                    (curr_net.bytes_sent - self._prev_net.bytes_sent) +
                    (curr_net.bytes_recv - self._prev_net.bytes_recv)
                )
                net_mb = max(0.0, delta / dt / 1_048_576)
            self._prev_net = curr_net
        except Exception:
            self._prev_net = None

        self._prev_ts = now
        return cpu, ram, disk_mb, net_mb

    def _loop(self):
        try:
            import psutil, time as _t
        except ImportError:
            return

        # Warm-up: first cpu_percent always returns 0.0 — discard it
        try:
            psutil.cpu_percent(interval=None)
            self._prev_net  = psutil.net_io_counters()
            self._prev_disk = psutil.disk_io_counters()
        except Exception:
            pass

        import time as _t
        self._prev_ts = _t.monotonic()

        # Wait before first real sample so delta time is meaningful
        self._stop_event.wait(timeout=1.5)

        while not self._stop_event.is_set():
            try:
                if not self._paused:
                    cpu, ram, disk_mb, net_mb = self._collect()

                    # Map physical MB/s to 0-100 display range:
                    #   disk: saturates at 500 MB/s  (SSD sequential cap)
                    #   net:  saturates at 100 MB/s  (typical gigabit)
                    disk_disp = min(disk_mb / 5.0, 100.0)
                    net_disp  = min(net_mb,        100.0)

                    with self._lock:
                        for k, v in [("cpu",  cpu),
                                     ("ram",  ram),
                                     ("disk", disk_disp),
                                     ("net",  net_disp)]:
                            self._data[k].append(float(v))
                            self._data[k] = self._data[k][-self.MAX:]
                        snap = {k: list(v) for k, v in self._data.items()}

                    pill_texts = {
                        "cpu":  f"{cpu:.0f}%",
                        "ram":  f"{ram:.0f}%",
                        "disk": f"{disk_mb:.1f} MB/s",
                        "net":  f"{net_mb:.2f} MB/s",
                    }

                    safe_after(self, 0, lambda s=snap: self._redraw(s))
                    safe_after(self, 0, lambda t=pill_texts: self._update_pills(t))

            except Exception as _e:
                try:
                    _log("warning", f"GraphView._loop: {_e}")
                except Exception:
                    pass

            # Event.wait gives instant wakeup when stop_event is set
            self._stop_event.wait(timeout=1.5)

    # ── Control ────────────────────────────────────────────────────────────

    def start_monitoring(self):
        try:
            self._paused = False
            if self.winfo_exists():
                self._monitor_btn.configure(
                    text="⏸ PAUSE", text_color=AMBER,
                    border_color=AMBER_BORDER)
            _log("info", "GraphView: monitoring started")
        except Exception as _e:
            _log("warning", f"start_monitoring: {_e}")

    def stop_monitoring(self):
        try:
            self._paused = True
            if self.winfo_exists():
                self._monitor_btn.configure(
                    text="▶ RESUME", text_color=GREEN,
                    border_color=GREEN_BORDER)
            _log("info", "GraphView: monitoring paused")
        except Exception as _e:
            _log("warning", f"stop_monitoring: {_e}")

    def toggle_monitoring(self):
        if self._paused:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    # ── Drawing ────────────────────────────────────────────────────────────

    def _redraw(self, snapshot):
        try:
            if not self.winfo_exists():
                return
            if self._mpl_canvas is None:
                return

            for k, ln in self._lines.items():
                y  = snapshot[k]
                xs = list(range(len(y)))
                ln.set_xdata(xs)
                ln.set_ydata(y)

                old = self._fills.get(k)
                if old is not None:
                    try:
                        old.remove()
                    except Exception:
                        pass
                self._fills[k] = self._axes[k].fill_between(
                    xs, y, alpha=0.15, color=ln.get_color())

            self._mpl_canvas.draw_idle()
            self._mpl_canvas.flush_events()

        except Exception:
            pass

    def _update_pills(self, texts: dict):
        try:
            if not self.winfo_exists():
                return
            for k, t in texts.items():
                if k in self._pills:
                    self._pills[k].configure(text=t)
        except Exception:
            pass

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def destroy(self):
        """
        Signal the background thread to stop instantly via Event,
        then clean up the matplotlib canvas before the Tk teardown.
        """
        self._stop_event.set()          # wakes _loop immediately
        try:
            if self._mpl_widget:
                self._mpl_widget.destroy()
        except Exception:
            pass
        try:
            if self._mpl_canvas:
                self._mpl_canvas.get_tk_widget().destroy()
        except Exception:
            pass
        super().destroy()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 18 ── SIDEBAR, TOPBAR, CONTENT PANEL
# ══════════════════════════════════════════════════════════════════════════════
NAV_ITEMS = [
    ("◈", "SCAN",     "scan"),
    ("⚡", "BOOST",   "boost"),
    ("◻", "CLEAN",   "clean"),
    ("🔒", "SECURE",  "secure"),
    ("🔧", "FIX",     "fix"),
    ("▦", "GRAPH",   "graph"),
    ("↩", "ROLLBACK","rollback"),
    ("🤖", "AI",      "ai"),
]
PAGE_META = {
    "scan":     ("System Scan",       "Adaptive health check",             "▶ SCAN",      CYAN,   [("Live", CYAN)]),
    "boost":    ("System Boost",      "Gaming & Work modes · cross-distro","▶ BOOST",     CYAN,   [("adaptive", CYAN)]),
    "clean":    ("Deep Clean",        "Preview + selective delete",        "◻ SCAN",      CYAN,   [("preview", GREEN)]),
    "secure":   ("Security Scan",     "Ports · SSH · firewall · SUID",     "🔒 SCAN",     CYAN,   [("full audit", CYAN)]),
    "fix":      ("Fix System",        "Detect & repair issues · AUTO FIX", "🚀 AUTO FIX", PURPLE, [("auto-fix", GREEN), ("Enterprise", PURPLE)]),
    "graph":    ("Performance Graph", "Live CPU · RAM · I/O · Net",        "⏸ PAUSE",     AMBER,  [("LIVE", GREEN)]),
    "rollback": ("Rollback Manager",  f"Tracked: {rollback.count} actions","↩ ROLLBACK",  AMBER,  [("undo", AMBER)]),
    "ai":       ("AI Recommendations","Prioritised suggestions",           "★ ANALYSE",   CYAN,   [("adaptive", CYAN)]),
}
VIEW_CLASSES = {
    "scan": None, "boost": BoostView, "clean": CleanView, "secure": SecurityView,
    "fix": FixView, "graph": GraphView, "rollback": RollbackView, "ai": AIView,
}


# ── Sidebar ───────────────────────────────────────────────────────────────────
class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, nav_cb):
        super().__init__(parent, width=72, fg_color=BG2, corner_radius=0,
                         border_width=0)
        self.pack_propagate(False)
        self._nav_cb = nav_cb
        self._btns: dict = {}
        self._active_key: str = ""
        self._build()

    def _build(self):
        ctk.CTkFrame(self, height=8, fg_color="transparent").pack(fill="x")

        for icon, label, key in NAV_ITEMS:
            btn_frame = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
            btn_frame.pack(fill="x", pady=1)

            icon_lbl = ctk.CTkLabel(
                btn_frame, text=icon,
                font=("Helvetica", 18),
                text_color=T2, width=72, height=36,
                anchor="center"
            )
            icon_lbl.pack(fill="x")

            txt_lbl = ctk.CTkLabel(
                btn_frame, text=label,
                font=F_NAV, text_color=T2,
                width=72, anchor="center"
            )
            txt_lbl.pack(fill="x")

            for widget in (btn_frame, icon_lbl, txt_lbl):
                widget.bind("<Enter>",  lambda e, k=key: self._on_hover(k, True))
                widget.bind("<Leave>",  lambda e, k=key: self._on_hover(k, False))
                widget.bind("<Button-1>", lambda e, k=key: self._on_click(k))

            self._btns[key] = {
                "frame": btn_frame,
                "icon":  icon_lbl,
                "txt":   txt_lbl,
            }

        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(
            self, text="v4.2 Enterprise",
            font=("Courier New", 7), text_color=T2
        ).pack(pady=(0, 8))

        self._activate("scan")

    def _on_hover(self, key: str, entering: bool):
        if key == self._active_key:
            return
        widgets = self._btns.get(key, {})
        col = T1 if entering else T2
        try:
            widgets["icon"].configure(text_color=col)
            widgets["txt"].configure(text_color=col)
            widgets["frame"].configure(fg_color=BG3 if entering else "transparent")
        except Exception:
            pass

    def _on_click(self, key: str):
        self._activate(key)
        try:
            self._nav_cb(key)
        except Exception as _e:
            _log("warning", f"Sidebar nav error: {_e}")

    def _activate(self, key: str):
        if self._active_key and self._active_key in self._btns:
            prev = self._btns[self._active_key]
            try:
                prev["frame"].configure(fg_color="transparent")
                prev["icon"].configure(text_color=T2)
                prev["txt"].configure(text_color=T2)
            except Exception:
                pass

        self._active_key = key
        curr = self._btns.get(key, {})
        try:
            curr["frame"].configure(fg_color=BG3)
            curr["icon"].configure(text_color=CYAN)
            curr["txt"].configure(text_color=CYAN)
        except Exception:
            pass


# ── TopBar  ── FIX 5 applied (_tick cancel-safe + destroy()) ─────────────────
class TopBar(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, height=50, fg_color=BG2, corner_radius=0, border_width=0)
        self.grid_propagate(False)
        self._tick_id = None          # FIX 5: track pending after() id
        self._build()
        self.after(1000, self._tick)

    def _build(self):
        self.pack_propagate(False)
        c = ctk.CTkFrame(self, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=14)
        self._build_brand(c)
        self._build_right(c)

    def _build_brand(self, parent):
        brand = ctk.CTkFrame(parent, fg_color="transparent")
        brand.pack(side="left", pady=8)
        ctk.CTkLabel(
            brand, text="JX", width=28, height=28,
            fg_color=CYAN, text_color=BG1,
            font=("Courier New", 11, "bold"), corner_radius=6
        ).pack(side="left", padx=(0, 8))
        nc = ctk.CTkFrame(brand, fg_color="transparent")
        nc.pack(side="left")
        ctk.CTkLabel(nc, text="JENIX", font=("Courier New", 15, "bold"), text_color=CYAN).pack(anchor="w")
        ctk.CTkLabel(
            nc,
            text=f"v4.2 Enterprise · {distro.name.split()[0].upper()} · LOCAL MODE",
            font=("Courier New", 8),
            text_color=T2
        ).pack(anchor="w")

    def _build_right(self, parent):
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.pack(side="right", pady=8)
        self._meta = ctk.CTkLabel(
            right,
            text="CPU --  ·  RAM --  ·  UPTIME --",
            font=F_MONO_SM,
            text_color=T2
        )
        self._meta.pack(side="left", padx=(0, 14))

        if _HAS_FIX_ENGINE:
            fe_f = ctk.CTkFrame(
                right, fg_color=PURPLE_BG, corner_radius=4,
                border_width=1, border_color=PURPLE_BORDER
            )
            fe_f.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(
                fe_f, text="🚀 AUTO FIX",
                font=("Courier New", 8, "bold"),
                text_color=PURPLE, padx=8, pady=4
            ).pack()

        forensics_dir = LOG_DIR / "forensics"
        forensics_dir.mkdir(parents=True, exist_ok=True)

        ctk.CTkButton(
            right, text="📂 Open Forensics", width=140, height=30,
            font=("Courier New", 9, "bold"),
            fg_color=BG3, hover_color=BG4, text_color=CYAN,
            corner_radius=6, border_width=1, border_color=CYAN_BORDER,
            command=lambda d=forensics_dir: self._open_forensics(d),
        ).pack(side="left", padx=(0, 10))

        pb = ctk.CTkFrame(
            right, fg_color="#0d2010", border_color="#1d4020",
            border_width=1, corner_radius=20
        )
        pb.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(pb, text="●", font=("Helvetica", 8), text_color=GREEN).pack(
            side="left", padx=(8, 3), pady=5)
        self._hlbl = ctk.CTkLabel(
            pb, text="System Ready",
            font=("Helvetica", 10, "bold"), text_color=GREEN
        )
        self._hlbl.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            right, text="⚙", width=28, height=28, corner_radius=6,
            fg_color=BG3, hover_color=BG4, text_color=T2,
            font=("Helvetica", 13), border_width=1, border_color=BORDER,
            command=self._open_settings
        ).pack(side="left")

    # ── FIX 5: cancel-safe _tick + destroy() ──────────────────────────────

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        try:
            import psutil as _p
            cpu    = _p.cpu_percent(interval=0.2)
            mem    = _p.virtual_memory()
            uptime = self._format_uptime(_p.boot_time())
            ram_gb = (
                f"{mem.used / 1024**3:.1f}/"
                f"{mem.total / 1024**3:.1f}GB"
            )
            text = f"CPU {cpu:.0f}%  ·  RAM {ram_gb}  ·  UP {uptime}"
        except Exception:
            text = "CPU --  ·  RAM --  ·  UPTIME --"
        try:
            self._meta.configure(text=text)
        except Exception:
            return
        try:
            if self.winfo_exists():
                # Store ID so we can cancel on destroy — prevents TclError
                self._tick_id = self.after(3000, self._tick)
        except Exception:
            pass

    def destroy(self):
        """Cancel the pending after() before Tk tears down the widget."""
        try:
            if self._tick_id is not None:
                self.after_cancel(self._tick_id)
                self._tick_id = None
        except Exception:
            pass
        super().destroy()

    # ── Helpers (unchanged) ────────────────────────────────────────────────

    @staticmethod
    def _format_uptime(boot_ts: float) -> str:
        try:
            import time
            elapsed = int(time.time() - boot_ts)
            d, rem  = divmod(elapsed, 86400)
            h, _    = divmod(rem, 3600)
            return f"{d}d {h}h" if d else f"{h}h"
        except Exception:
            return "--"

    def _open_settings(self):
        try:
            import sys
            gui_mod = sys.modules.get("__main__")
            SD = getattr(gui_mod, "SettingsDialog", None)
            if SD is None:
                import gui_additions as _ga
                SD = _ga.SettingsDialog
            SD(self.winfo_toplevel())
        except Exception as _e:
            _log("warning", f"Settings open error: {_e}")

    def _open_forensics(self, forensics_dir: Path):
        report_path = None
        try:
            report_path = self._generate_forensics_report(forensics_dir)
        except Exception as e:
            _log("warning", f"Forensics report generation failed: {e}")

        try:
            import subprocess, sys
            if sys.platform.startswith("linux"):
                managers = ["xdg-open", "nautilus", "thunar", "nemo", "dolphin", "pcmanfm"]
                for mgr in managers:
                    try:
                        subprocess.Popen([mgr, str(forensics_dir)],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                        return
                    except FileNotFoundError:
                        continue
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(forensics_dir)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(forensics_dir)])
        except Exception as e:
            _log("warning", f"Could not open file manager: {e}")
            if report_path and report_path.exists():
                _log("info", f"Report saved at: {report_path}")

    @staticmethod
    def _generate_forensics_report(forensics_dir: Path) -> Path:
        from datetime import datetime

        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_txt  = forensics_dir / f"forensics_{ts}.txt"

        sections    = []
        issue_count = 0
        risk_level  = "LOW"

        def bump_risk(level: str):
            nonlocal risk_level
            order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
            if order.get(level, 0) > order.get(risk_level, 0):
                risk_level = level

        def tag(label: str) -> str:
            return f"[{label.upper()}]"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sections.append("\n".join([
            "=" * 64,
            "        JENIX v4.2 Enterprise  —  AI FORENSIC INTELLIGENCE REPORT",
            "=" * 64,
            f"  Generated : {now_str}",
            f"  Distro    : {distro.label}",
            f"  Audit Log : {AUDIT_LOG}",
            "=" * 64,
        ]))

        perf_lines = ["=== SYSTEM PERFORMANCE ==="]
        try:
            import psutil as _p
            cpu = _p.cpu_percent(interval=0.3)
            mem = _p.virtual_memory()

            cpu_risk = "WARN" if cpu > 80 else "OK"
            mem_risk = "CRITICAL" if mem.percent > 90 else "WARN" if mem.percent > 70 else "OK"

            if cpu > 80:
                issue_count += 1
                bump_risk("MEDIUM")
            if mem.percent > 90:
                issue_count += 1
                bump_risk("HIGH")

            ram_used = mem.used  / 1024**3
            ram_tot  = mem.total / 1024**3
            perf_lines += [
                f"{tag(cpu_risk)} CPU Usage : {cpu:.1f}%",
                f"{tag(mem_risk)} RAM Usage : {mem.percent:.1f}%  ({ram_used:.1f} GB / {ram_tot:.1f} GB)",
            ]

            perf_lines += ["", "=== DISK STATUS ==="]
            for part in _p.disk_partitions(all=False):
                try:
                    u      = _p.disk_usage(part.mountpoint)
                    d_risk = "CRITICAL" if u.percent > 90 else "WARN" if u.percent > 80 else "OK"
                    if u.percent > 90:
                        issue_count += 1
                        bump_risk("HIGH")
                    perf_lines.append(
                        f"{tag(d_risk)} {part.mountpoint:<20} {u.percent:.1f}%  "
                        f"({u.used // 1024**3} GB used / {u.total // 1024**3} GB total)"
                    )
                except Exception:
                    pass
        except ImportError:
            perf_lines.append("[WARN] psutil not available — skipping performance data")
        except Exception as e:
            perf_lines.append(f"[WARN] Performance check error: {e}")

        sections.append("\n".join(perf_lines))

        net_lines  = ["=== NETWORK ANALYSIS ==="]
        risky_ports = {
            21:    "FTP (plaintext)",
            22:    "SSH (ensure key-only auth)",
            23:    "Telnet (plaintext protocol)",
            3306:  "MySQL (exposed to network)",
            5432:  "PostgreSQL (exposed to network)",
            6379:  "Redis (no auth by default)",
            27017: "MongoDB (no auth by default)",
        }
        try:
            rc, out, _ = run("ss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null", timeout=10)
            if out:
                net_lines.append("Open Ports:")
                for line in out.splitlines()[:30]:
                    net_lines.append(f"  {line}")
                net_lines.append("")
                for port, desc in risky_ports.items():
                    if f":{port}" in out:
                        issue_count += 1
                        bump_risk("HIGH")
                        net_lines.append(f"[CRITICAL] Port {port} open — {desc}")
            else:
                net_lines.append("[OK] No open listening ports detected")
        except Exception as e:
            net_lines.append(f"[WARN] Network check error: {e}")

        sections.append("\n".join(net_lines))

        fw_lines = ["=== FIREWALL STATUS ==="]
        try:
            active, _ = security_scanner.check_firewall()
            if not active:
                issue_count += 1
                bump_risk("HIGH")
                fw_lines.append("[CRITICAL] Firewall is INACTIVE — system is unprotected")
            else:
                fw_lines.append("[OK] Firewall is ACTIVE")
        except Exception as e:
            fw_lines.append(f"[WARN] Firewall check error: {e}")

        sections.append("\n".join(fw_lines))

        ssh_lines = ["=== SSH SECURITY ==="]
        try:
            ssh_issues = security_scanner.check_ssh()
            if ssh_issues:
                for msg, risk, _ in ssh_issues:
                    issue_count += 1
                    bump_risk(risk.upper() if risk.upper() in ("MEDIUM", "HIGH", "CRITICAL") else "MEDIUM")
                    ssh_lines.append(f"{tag(risk)} {msg}")
            else:
                ssh_lines.append("[OK] No SSH misconfigurations detected")
        except Exception as e:
            ssh_lines.append(f"[WARN] SSH check error: {e}")

        sections.append("\n".join(ssh_lines))

        score      = max(0, min(100, 100 - (issue_count * 5) - (20 if risk_level == "HIGH" else 10 if risk_level == "MEDIUM" else 0)))
        score_tag  = "CRITICAL" if score < 40 else "WARN" if score < 70 else "OK"
        threat_map = {
            "HIGH":   "Active security risks detected. Immediate remediation required.",
            "MEDIUM": "Moderate vulnerabilities present. Review recommended.",
            "LOW":    "System is operating within acceptable security parameters.",
        }
        threat_lines = [
            "=== THREAT ASSESSMENT ===",
            f"  Overall Risk Level   : {risk_level}",
            f"  Issues Detected      : {issue_count}",
            f"{tag(score_tag)} Attack Surface Score : {score}/100",
            f"  Summary              : {threat_map[risk_level]}",
        ]
        sections.append("\n".join(threat_lines))

        actions = []
        if risk_level == "HIGH":
            actions += [
                "Enable and configure firewall immediately  →  sudo ufw enable",
                "Close all unnecessary listening ports",
                "Harden SSH: disable PasswordAuthentication, restrict to key-based auth",
            ]
        if risk_level in ("HIGH", "MEDIUM"):
            actions += [
                "Apply all pending system package updates  →  sudo apt upgrade",
                "Audit running services and disable unused ones",
                "Review /var/log/auth.log for suspicious login attempts",
            ]
        if not actions:
            actions.append("No critical actions required — continue routine monitoring")

        action_lines = ["=== RECOMMENDED ACTIONS ==="] + [f"  - {a}" for a in actions]
        sections.append("\n".join(action_lines))
        sections.append("=" * 64)

        report_body = "\n\n".join(sections) + "\n"

        output_path = TopBar._try_write_pdf(forensics_dir, ts, report_body)
        if output_path is None:
            try:
                report_txt.write_text(report_body, encoding="utf-8")
                output_path = report_txt
            except Exception as e:
                _log("warning", f"Forensics report write error: {e}")
                return report_txt

        _log("info", f"Forensics report generated: {output_path.name}")
        return output_path

    @staticmethod
    def _try_write_pdf(forensics_dir: Path, ts: str, body: str):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles   import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units    import mm
            from reportlab.lib          import colors
            from reportlab.platypus     import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

            pdf_path = forensics_dir / f"forensics_{ts}.pdf"
            doc      = SimpleDocTemplate(
                str(pdf_path), pagesize=A4,
                leftMargin=20*mm, rightMargin=20*mm,
                topMargin=20*mm, bottomMargin=20*mm
            )
            styles  = getSampleStyleSheet()
            mono    = ParagraphStyle(
                "mono", parent=styles["Normal"],
                fontName="Courier", fontSize=8, leading=12,
                textColor=colors.HexColor("#1a1a2e"), spaceAfter=2
            )
            heading = ParagraphStyle(
                "heading", parent=styles["Normal"],
                fontName="Courier-Bold", fontSize=9, leading=14,
                textColor=colors.HexColor("#0a2240"),
                spaceBefore=8, spaceAfter=4
            )
            story = []
            for line in body.splitlines():
                if line.startswith("==="):
                    story.append(Spacer(1, 4))
                    story.append(HRFlowable(width="100%", thickness=0.5,
                                            color=colors.HexColor("#cccccc")))
                    story.append(Paragraph(line.strip("= "), heading))
                elif line.strip("=") == "":
                    story.append(HRFlowable(width="100%", thickness=0.5,
                                            color=colors.HexColor("#cccccc")))
                else:
                    safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(safe, mono))
            doc.build(story)
            return pdf_path
        except ImportError:
            return None
        except Exception as e:
            _log("warning", f"PDF generation error: {e}")
            return None


# ── ScanView ──────────────────────────────────────────────────────────────────
class ScanView(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._scanning = False
        self._cards = {}
        self._scan_result = None
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BG3,
            scrollbar_button_hover_color=BG4)
        scroll.pack(fill="both", expand=True, padx=14, pady=14)
        _distro_banner(scroll)

        ds = ctk.CTkFrame(scroll, fg_color=BG3, corner_radius=6,
                           border_width=1, border_color=BORDER)
        ds.pack(fill="x", pady=(8, 8))
        ctk.CTkLabel(ds, text=f"◈  {distro.label}", font=F_MONO_SM,
                     text_color=CYAN).pack(side="left", padx=14, pady=6)
        ctk.CTkLabel(ds, text=f"audit: {AUDIT_LOG}", font=F_MONO_XS,
                     text_color=T2).pack(side="right", padx=14)

        prow = ctk.CTkFrame(scroll, fg_color=BG2, corner_radius=8,
                             border_width=1, border_color=BORDER)
        prow.pack(fill="x", pady=(0, 10))
        pi = ctk.CTkFrame(prow, fg_color="transparent")
        pi.pack(fill="x", padx=14, pady=8)

        self._scan_btn = ctk.CTkButton(
            pi, text="▶  SCAN SYSTEM", width=140, height=30,
            font=("Courier New", 10, "bold"),
            fg_color=CYAN, hover_color=CYANL, text_color=BG1,
            corner_radius=6, command=self._start)
        self._scan_btn.pack(side="left", padx=(0, 12))

        self._quick_fix_btn = ctk.CTkButton(
            pi, text="🚀 AUTO FIX", width=120, height=30,
            font=("Courier New", 10, "bold"),
            fg_color=PURPLE, hover_color="#7c3aed", text_color="#ffffff",
            corner_radius=6, state="disabled",
            command=self._quick_autofix)
        self._quick_fix_btn.pack(side="left", padx=(0, 12))

        self._bar = ctk.CTkProgressBar(pi, height=6, corner_radius=3,
                                        fg_color=BG3, progress_color=CYAN)
        self._bar.set(0)
        self._bar.pack(side="left", fill="x", expand=True)

        self._prog_lbl = ctk.CTkLabel(pi, text="Ready", font=F_MONO_XS,
                                       text_color=T2, width=220, anchor="e")
        self._prog_lbl.pack(side="left", padx=(8, 0))

        stat_row = ctk.CTkFrame(scroll, fg_color="transparent")
        stat_row.pack(fill="x", pady=(0, 10))
        for i in range(4):
            stat_row.columnconfigure(i, weight=1, uniform="s")

        for i, (key, lbl, val, unit, sub, col) in enumerate([
            ("health", "HEALTH SCORE", "—", "/100", "Run scan to populate", GREEN),
            ("issues", "ISSUES FOUND", "—", "",     "Run scan to populate", AMBER),
            ("ports",  "OPEN PORTS",   "—", "",     "Port scan pending",    CYAN),
            ("boot",   "BOOT TIME",    "—", " s",   "Run scan to populate", RED),
        ]):
            c = StatCard(stat_row, lbl, val, unit, sub, col)
            c.grid(row=0, column=i, padx=(0, 8 if i < 3 else 0), sticky="nsew")
            self._cards[key] = c

        self._crit_host = ctk.CTkFrame(scroll, fg_color="transparent")
        self._crit_host.pack(fill="x", pady=(0, 10))

        self._tip = ctk.CTkLabel(
            scroll,
            text="💡  After scanning, click 🚀 AUTO FIX for one-click system repair, "
                 "or use Boost · Clean · Fix · AI tabs.",
            font=F_MONO_SM, text_color=T2)
        self._tip.pack(pady=10)

        self.log = LogBox(scroll, height=140)
        self.log.pack(fill="x", pady=(0, 4))
        self.log.write("INFO", f"JENIX v4.2 Enterprise · {distro.label}")
        self.log.write("INFO", f"Logs: {AUDIT_LOG}")
        if _HAS_FIX_ENGINE:
            self.log.write("OK", "FixEngine v4.2 Enterprise loaded — 🚀 AUTO FIX is available after scanning")
        self.log.write("INFO", "Click ▶ SCAN SYSTEM to begin")

    def _quick_autofix(self):
        try:
            top = self.winfo_toplevel()
            if hasattr(top, '_nav') and callable(top._nav):
                top._nav("fix")
            else:
                _log("warning", "_quick_autofix: root has no _nav method")
        except Exception as _e:
            _log("warning", f"_quick_autofix error: {_e}")

    def _start(self):
        if self._scanning:
            return
        self._scanning = True
        self._scan_btn.configure(state="disabled", text="⏳  SCANNING…")
        self._quick_fix_btn.configure(state="disabled")
        self._bar.set(0)
        threading.Thread(target=self._run, daemon=True).start()

    def run_scan(self):
        self._start()

    def _run(self):
        def tick(pct, msg):
            safe_after(self, 0, lambda: self._safe_bar_set(pct / 100))
            safe_after(self, 0, lambda m=msg: self._safe_prog_lbl(m))
            safe_after(self, 0, lambda m=msg: self.log.write("INFO", m))

        issues_crit = []
        issues_warn = []
        score = 100

        tick(10, "Checking CPU & RAM…")
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            if cpu > 85:
                issues_crit.append(f"CPU at {cpu:.0f}%")
                score -= 15
            if mem.percent > 90:
                issues_crit.append(f"RAM at {mem.percent:.0f}%")
                score -= 15
            elif mem.percent > 75:
                issues_warn.append(f"RAM at {mem.percent:.0f}%")
                score -= 5
        except Exception:
            pass

        tick(25, "Scanning disks…")
        try:
            import psutil
            for part in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    if u.percent >= 90:
                        issues_crit.append(f"Disk {part.mountpoint} {u.percent:.0f}%")
                        score -= 15
                    elif u.percent >= 80:
                        issues_warn.append(f"Disk {part.mountpoint} {u.percent:.0f}%")
                        score -= 5
                except Exception:
                    pass
        except Exception:
            pass

        tick(40, "Checking firewall…")
        fw_active, _ = security_scanner.check_firewall()
        if not fw_active:
            issues_crit.append("No active firewall")
            score -= 18

        tick(55, "Checking SSH…")
        ssh = security_scanner.check_ssh()
        for msg, risk, _ in ssh:
            if risk == "red":
                issues_crit.append(msg)
                score -= 15
            else:
                issues_warn.append(msg)
                score -= 5

        tick(70, "Scanning open ports…")
        ports = security_scanner.scan_ports()
        high_risk = [p for p in ports if p.risk == "red"]
        score -= len(high_risk) * 8

        tick(85, "Checking swappiness…")
        rc, out, _ = run("cat /proc/sys/vm/swappiness", timeout=3)
        if rc == 0 and out.isdigit() and int(out) > 30:
            issues_warn.append(f"Swappiness {out}")
            score -= 5

        boot_secs = 0
        try:
            rc2, bt_out, _ = run(
                "systemd-analyze 2>/dev/null | head -1 | grep -oP '[0-9]+\\.[0-9]+s' | head -1",
                timeout=5)
            if rc2 == 0 and bt_out:
                boot_secs = float(bt_out.replace("s", "").strip())
        except Exception:
            pass

        score = max(0, min(100, score))
        total_issues = len(issues_crit) + len(issues_warn)
        tick(100, f"Scan complete · score {score}/100")

        safe_after(self, 0, lambda s=score, t=total_issues, ic=issues_crit,
                   p=ports, hr=high_risk, bs=boot_secs:
                   self._scan_done(s, t, ic, p, hr, bs))

        for issue in issues_crit:
            safe_after(self, 0, lambda m=issue: self.log.write("ERR", m))
        for issue in issues_warn:
            safe_after(self, 0, lambda m=issue: self.log.write("WARN", m))

        if total_issues > 0 and _HAS_FIX_ENGINE:
            safe_after(self, 0, lambda s=score, hr=high_risk: self.log.write("OK",
                f"Score: {s}/100 · {len(hr)} high-risk ports · "
                f"Click 🚀 AUTO FIX or go to FIX tab for one-click repair"))
        else:
            safe_after(self, 0, lambda s=score, hr=high_risk: self.log.write("OK",
                f"Score: {s}/100 · {len(hr)} high-risk ports"))

        self._scanning = False

    def _safe_bar_set(self, v):
        try:
            if not self.winfo_exists():
                return
            self._bar.set(v)
        except Exception:
            pass

    def _safe_prog_lbl(self, m):
        try:
            if not self.winfo_exists():
                return
            self._prog_lbl.configure(text=m)
        except Exception:
            pass

    def _scan_done(self, score, total_issues, issues_crit, ports, high_risk, boot_secs=0):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        self._cards["health"].set(
            str(score),
            GREEN if score >= 80 else AMBER if score >= 60 else RED)
        self._cards["issues"].set(
            str(total_issues),
            RED if issues_crit else AMBER)
        self._cards["ports"].set(
            str(len(ports)),
            RED if high_risk else CYAN)

        if boot_secs > 0:
            self._cards["boot"].set(
                f"{boot_secs:.1f}",
                RED if boot_secs > 30 else AMBER if boot_secs > 15 else GREEN)
        else:
            self._cards["boot"].set("N/A", T2)

        self._scan_btn.configure(state="normal", text="▶  SCAN SYSTEM")
        self._quick_fix_btn.configure(
            state="normal" if _HAS_FIX_ENGINE else "disabled")


VIEW_CLASSES["scan"] = ScanView


# ── ContentPanel  ── FIX 6 applied (view cache — no rebuild on tab switch) ───
class ContentPanel(ctk.CTkFrame):
    """
    Hosts the active view with a view cache.

    Views are built once and hidden/shown with pack_forget()/pack().
    This eliminates the widget rebuild cost on every tab switch,
    making repeat navigation essentially instant.

    Cache policy:
    • Most views are cached indefinitely (fast re-display, preserved state).
    • _NO_CACHE views are destroyed and rebuilt on each visit so they always
      show fresh data (e.g. RollbackView reads the DB on init).
    """
    _NO_CACHE = {"rollback"}   # always rebuilt for fresh state

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self._cur: object = None
        self._cur_key: str = ""
        self._cache: dict = {}
        self._build_hdr()
        self._host = ctk.CTkFrame(self, fg_color="transparent")
        self._host.pack(fill="both", expand=True)
        self.show("scan")

    # ── Header ─────────────────────────────────────────────────────────────

    def _build_hdr(self):
        h = ctk.CTkFrame(self, height=52, fg_color=BG2,
                         corner_radius=0, border_width=0)
        h.pack(fill="x")
        h.pack_propagate(False)
        row = ctk.CTkFrame(h, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=18)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", pady=8)
        self._title = ctk.CTkLabel(left, text="", font=F_TITLE, text_color=T1)
        self._title.pack(anchor="w")
        self._sub = ctk.CTkLabel(left, text="", font=F_MONO_XS, text_color=T2)
        self._sub.pack(anchor="w")

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", pady=8)
        self._badges = ctk.CTkFrame(right, fg_color="transparent")
        self._badges.pack(side="left", padx=(0, 10))
        self._abtn = ctk.CTkButton(
            right, text="", width=120, height=30, corner_radius=6,
            fg_color=CYAN, hover_color=CYANL, text_color=BG1,
            font=("Courier New", 10, "bold"),
            command=self._on_action)
        self._abtn.pack(side="left")
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")

    def _update_header(self, key: str):
        """Refresh title, subtitle, action button and badge strip."""
        title, sub, btn, bc, badges = PAGE_META[key]
        self._title.configure(text=title)
        self._sub.configure(text=sub)
        hover_c = "#7c3aed" if bc == PURPLE else CYANL if bc == CYAN else bc
        self._abtn.configure(
            text=btn, fg_color=bc, hover_color=hover_c,
            text_color="#ffffff" if bc == PURPLE else BG1)

        for w in self._badges.winfo_children():
            w.destroy()
        for bt, bco in badges:
            f = ctk.CTkFrame(
                self._badges, fg_color=_bbg(bco), corner_radius=4,
                border_width=1, border_color=_bbd(bco))
            ctk.CTkLabel(f, text=bt, font=F_MONO_XS, text_color=bco,
                          padx=7, pady=3).pack()
            f.pack(side="left", padx=(0, 5))

    # ── Action button dispatch ─────────────────────────────────────────────

    def _on_action(self):
        try:
            key  = self._cur_key
            view = self._cur
            if view is None:
                return
            dispatch = {
                "scan":     lambda: view.run_scan()          if hasattr(view, "run_scan")          else None,
                "boost":    lambda: view._run_boost()        if hasattr(view, "_run_boost")        else None,
                "clean":    lambda: view._start_scan()       if hasattr(view, "_start_scan")       else None,
                "secure":   lambda: view._start_scan()       if hasattr(view, "_start_scan")       else None,
                "fix":      lambda: view._confirm_auto_fix() if hasattr(view, "_confirm_auto_fix") else None,
                "graph":    lambda: view.toggle_monitoring() if hasattr(view, "toggle_monitoring") else None,
                "rollback": lambda: view.rollback_action()   if hasattr(view, "rollback_action")   else None,
                "ai":       lambda: view._run()              if hasattr(view, "_run")              else None,
            }
            action = dispatch.get(key)
            if action:
                action()
        except Exception as _e:
            _log("warning", f"ContentPanel._on_action ({self._cur_key}): {_e}")

    # ── Navigation ────────────────────────────────────────────────────────

    def show(self, key: str):
        """
        Switch to the view for `key`.

        First visit  → build the view, cache it, pack it.
        Repeat visit → pack_forget() old, pack() cached — no rebuild.
        No-cache keys → destroy old instance, rebuild fresh each time.
        """
        # 1. Update header labels/buttons — no widget rebuild
        self._update_header(key)

        # 2. Hide the currently visible view (keep it alive in self._cache)
        if self._cur is not None:
            try:
                self._cur.pack_forget()
            except Exception:
                pass

        # 3. Get or create the target view
        if key in self._NO_CACHE:
            # Destroy stale instance so fresh state is guaranteed
            old = self._cache.pop(key, None)
            if old is not None:
                try:
                    old.destroy()
                except Exception:
                    pass
            new_view = VIEW_CLASSES[key](self._host)
            # Do NOT store in cache — it will be rebuilt next visit too
        elif key in self._cache:
            new_view = self._cache[key]          # instant — already built
        else:
            new_view = VIEW_CLASSES[key](self._host)
            self._cache[key] = new_view          # store for future visits

        # 4. Show the view
        self._cur     = new_view
        self._cur_key = key
        self._cur.pack(fill="both", expand=True)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def destroy(self):
        """Cleanly destroy all cached and active views."""
        for view in list(self._cache.values()):
            try:
                view.destroy()
            except Exception:
                pass
        self._cache.clear()
        if self._cur is not None and self._cur not in self._cache.values():
            try:
                self._cur.destroy()
            except Exception:
                pass
        super().destroy()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 19 ── ROOT APPLICATION  ── FIX 7 applied (weakref + shortcuts)
# ══════════════════════════════════════════════════════════════════════════════
class JenixApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"JENIX v4.2 Enterprise  ·  {distro.name}")
        self.geometry("1160x780")
        self.minsize(900, 600)
        self.resizable(True, True)
        self.configure(fg_color=BG1)

        # ── FIX 7a: Register global app reference as weakref ──────────────
        global _APP_REF
        _APP_REF = _weakref.ref(self)

        # ── SAFE LOGGER CONNECTION ─────────────────────────────────────────
        try:
            if '_USING_UTILS_LOGGER' in globals() and _USING_UTILS_LOGGER:
                set_gui_callback(self.update_log_panel)
        except Exception as e:
            print("Logger callback setup failed:", e)

        # Global FixEngine instance
        self.fix_engine: Optional[FixEngine] = None
        if _HAS_FIX_ENGINE:
            try:
                self.fix_engine = FixEngine()
                _log("info", "Global FixEngine initialized")
            except Exception as _fe_err:
                _log("warning", f"Global FixEngine init failed: {_fe_err}")

        self._build()

        _log("info", "JENIX v4.2 Enterprise started — Local Mode")

        self.after(500, self._startup_snapshot)
        self.after(800, lambda: self._emit_startup_logs())

    def _emit_startup_logs(self):
        """Post the three required startup demo log messages to rt_log."""
        for delay, msg in [
            (0,    "JENIX initialized"),
            (400,  "Monitoring engine active"),
            (800,  "System ready"),
        ]:
            self.after(delay, lambda m=msg: _log("info", m))

    def _startup_snapshot(self):
        def _do():
            try:
                snap = rollback.snapshot_packages("startup")
                if snap.get("status") == "success":
                    _log("info", f"Startup snapshot: {snap.get('message','')}")
                else:
                    _log("warning", f"Startup snapshot skipped: {snap.get('message','')}")
            except Exception as _ex:
                _log("warning", f"Startup snapshot error: {_ex}")
        threading.Thread(target=_do, daemon=True).start()

    # ── FIX 7c: _build() with shortcut binding wired in ───────────────────

    def _build(self):
        ctk.CTkFrame(self, height=2, fg_color=CYAN,
                     corner_radius=0).pack(fill="x")
        TopBar(self).pack(fill="x")
        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                     corner_radius=0).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self.sidebar = Sidebar(body, self._nav)
        self.sidebar.pack(side="left", fill="y")
        ctk.CTkFrame(body, width=1, fg_color=BORDER).pack(side="left", fill="y")

        # ── Main content area with persistent rt_log at the bottom ────────
        main_area = ctk.CTkFrame(body, fg_color="transparent")
        main_area.pack(side="left", fill="both", expand=True)

        self.content = ContentPanel(main_area)
        self.content.pack(side="top", fill="both", expand=True)

        # Real-time log panel — persists across page navigation
        ctk.CTkFrame(main_area, height=1, fg_color=BORDER).pack(fill="x")
        self.rt_log = RealTimeLogPanel(main_area, height=150)
        self.rt_log.pack(fill="x", padx=0, pady=0)

        # Bind keyboard shortcuts after all widgets are constructed
        self.after(100, self._bind_shortcuts)

    # ── FIX 7b: _nav() + keyboard shortcuts ───────────────────────────────

    def _nav(self, key: str):
        self.sidebar._activate(key)
        self.content.show(key)

    def _bind_shortcuts(self):
        """
        Bind global keyboard shortcuts.
        Called via after(100) so all widgets exist before bindings fire.
        """
        _pages = ["scan", "boost", "clean", "secure",
                  "fix", "graph", "rollback", "ai"]
        for i, page in enumerate(_pages, start=1):
            self.bind_all(
                f"<Control-Key-{i}>",
                lambda e, p=page: self._nav(p))

        # Ctrl+R: trigger the action button of the current view
        self.bind_all("<Control-r>",
                      lambda e: self.content._on_action())

        # Ctrl+S: manual package snapshot
        self.bind_all("<Control-s>",
                      lambda e: self._kbd_snapshot())

        # Escape: pause graph monitoring if on graph tab
        self.bind_all("<Escape>",
                      lambda e: self._kbd_escape())

        _log("info",
             "Shortcuts: Ctrl+1-8 (tabs), Ctrl+R (action), "
             "Ctrl+S (snapshot), Escape (stop graph)")

    def _kbd_snapshot(self):
        try:
            snap = rollback.snapshot_packages("kbd_manual")
            level = "info" if snap.get("status") == "success" else "warning"
            _log(level, f"Snapshot: {snap.get('message', '')}")
        except Exception as _e:
            _log("warning", f"Snapshot shortcut: {_e}")

    def _kbd_escape(self):
        try:
            if self.content._cur_key == "graph":
                view = self.content._cur
                if view and hasattr(view, "stop_monitoring"):
                    view.stop_monitoring()
        except Exception:
            pass

    # ── Public top-level aliases for jenix_integration.py ─────────────────

    def run_scan(self):
        try:
            self._nav("scan")
            safe_after(self, 200, lambda: self.content._on_action())
        except Exception as _e:
            _log("warning", f"JenixApp.run_scan error: {_e}")

    def start_monitoring(self):
        try:
            if self.content._cur_key == "graph" and hasattr(self.content._cur, 'start_monitoring'):
                self.content._cur.start_monitoring()
            else:
                self._nav("graph")
                safe_after(self, 300, lambda: (
                    self.content._cur.start_monitoring()
                    if hasattr(self.content._cur, 'start_monitoring') else None))
        except Exception as _e:
            _log("warning", f"JenixApp.start_monitoring error: {_e}")

    def stop_monitoring(self):
        try:
            if self.content._cur_key == "graph" and hasattr(self.content._cur, 'stop_monitoring'):
                self.content._cur.stop_monitoring()
            else:
                _log("info", "stop_monitoring: graph view not active; no-op")
        except Exception as _e:
            _log("warning", f"JenixApp.stop_monitoring error: {_e}")

    def rollback_action(self):
        try:
            self._nav("rollback")
            safe_after(self, 200, lambda: self.content._on_action())
        except Exception as _e:
            _log("warning", f"JenixApp.rollback_action error: {_e}")


if __name__ == "__main__":
    _log("info", f"JENIX v4.2 Enterprise · {distro.label} · pid={os.getpid()}")
    app = JenixApp()

    try:
        from gui_additions import apply_additions
        apply_additions(app)
        _log("info", "gui_additions applied")
    except ImportError:
        pass
    except Exception as _gae:
        print(f"[gui_additions] unexpected error: {_gae}")

    try:
        from jenix_integration import patch_app
        patch_app(app)
    except ImportError:
        pass
    except Exception as _ie:
        print(f"[jenix_integration] unexpected error: {_ie}")

    try:
        from jenix_scan_view import patch_scan_view
        patch_scan_view(app)
        _log("info", "jenix_scan_view patch applied")
    except ImportError:
        pass
    except Exception as _sve:
        print(f"[jenix_scan_view] unexpected error: {_sve}")

    app.mainloop()
    _log("info", "JENIX exited")
