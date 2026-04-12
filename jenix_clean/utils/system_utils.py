"""
utils/system_utils.py
─────────────────────
Low-level system introspection helpers for JENIX.

Provides:
  - Command execution (sync / async / with timeout)
  - CPU, RAM, disk and network metric collection
  - Boot-time and uptime queries
  - File and path safety helpers

All functions are pure utilities — no GUI imports, no global state.

Usage:
    from utils.system_utils import run_cmd, get_memory_info
    rc, stdout, stderr = run_cmd("uname -r")
    mem = get_memory_info()
"""

import subprocess
import threading
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

# ── Type aliases ──────────────────────────────────────────────────────────────

CmdResult = Tuple[int, str, str]   # (return_code, stdout, stderr)

# ── Command execution ─────────────────────────────────────────────────────────

def run_cmd(
    cmd: str,
    timeout: int = 60,
    shell: bool = True,
) -> CmdResult:
    """
    Execute a shell command synchronously.

    Args:
        cmd:     Shell command string to execute.
        timeout: Seconds before the process is killed.
        shell:   Whether to run through the shell (default True).

    Returns:
        Tuple of (return_code, stdout, stderr).
        Returns (-1, "", "timeout") on timeout.
        Returns (-2, "", str(exc)) on unexpected error.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as exc:
        return -2, "", str(exc)


def run_cmd_bg(
    cmd: str,
    on_done: Optional[Callable[[int, str, str], None]] = None,
    timeout: int = 120,
) -> threading.Thread:
    """
    Execute a shell command in a background daemon thread.

    Args:
        cmd:     Shell command string to execute.
        on_done: Optional callback invoked with (rc, stdout, stderr) on completion.
        timeout: Seconds before the subprocess is killed.

    Returns:
        The running Thread object.
    """
    def _worker():
        rc, stdout, stderr = run_cmd(cmd, timeout=timeout)
        if on_done:
            try:
                on_done(rc, stdout, stderr)
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def which(binary: str) -> Optional[str]:
    """
    Return the full path of *binary* if it exists on PATH, else None.

    Thin wrapper around shutil.which so callers don't need to import shutil.

    Args:
        binary: Executable name (e.g. "ufw", "ss", "pacman").

    Returns:
        Absolute path string, or None.
    """
    return shutil.which(binary)


# ── CPU helpers ───────────────────────────────────────────────────────────────

def get_cpu_percent(interval: float = 0.5) -> float:
    """
    Return current system-wide CPU utilisation as a percentage.

    Args:
        interval: Seconds to sample over (passed to psutil).

    Returns:
        Float in range [0.0, 100.0].
    """
    try:
        import psutil
        return psutil.cpu_percent(interval=interval)
    except ImportError:
        pass

    # Fallback: parse /proc/stat for two samples
    def _read_cpu_stat():
        try:
            line = open("/proc/stat").readline()
            fields = list(map(int, line.split()[1:]))
            idle = fields[3]
            total = sum(fields)
            return idle, total
        except Exception:
            return 0, 1

    idle1, total1 = _read_cpu_stat()
    time.sleep(interval)
    idle2, total2 = _read_cpu_stat()

    delta_idle  = idle2 - idle1
    delta_total = total2 - total1
    if delta_total == 0:
        return 0.0
    return round((1.0 - delta_idle / delta_total) * 100.0, 1)


def get_cpu_governor() -> str:
    """
    Read the scaling governor for cpu0.

    Returns:
        Governor name (e.g. "performance", "powersave") or "unknown".
    """
    governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    return safe_read(governor_path).strip() or "unknown"


def get_cpu_count() -> Dict[str, int]:
    """
    Return logical and physical CPU core counts.

    Returns:
        Dict with keys "logical" and "physical".
    """
    try:
        import psutil
        return {
            "logical":  psutil.cpu_count(logical=True)  or 1,
            "physical": psutil.cpu_count(logical=False) or 1,
        }
    except ImportError:
        pass

    # Fallback: count processor entries in /proc/cpuinfo
    logical = 0
    physical_ids = set()
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("processor"):
                logical += 1
            elif line.startswith("physical id"):
                physical_ids.add(line.split(":")[1].strip())
    except Exception:
        logical = 1
    return {"logical": max(logical, 1), "physical": max(len(physical_ids), 1)}


# ── Memory helpers ────────────────────────────────────────────────────────────

def get_memory_info() -> Dict[str, float]:
    """
    Return current memory statistics in GB.

    Returns:
        Dict with keys: total, available, used, percent, swap_total, swap_used.
    """
    try:
        import psutil
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total":      round(mem.total      / 1024**3, 2),
            "available":  round(mem.available  / 1024**3, 2),
            "used":       round(mem.used       / 1024**3, 2),
            "percent":    mem.percent,
            "swap_total": round(swap.total     / 1024**3, 2),
            "swap_used":  round(swap.used      / 1024**3, 2),
        }
    except ImportError:
        pass

    # Fallback: parse /proc/meminfo
    info: Dict[str, int] = {}
    try:
        for line in open("/proc/meminfo"):
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])  # kB
    except Exception:
        pass

    total     = info.get("MemTotal",     0) * 1024
    free      = info.get("MemFree",      0) * 1024
    buffers   = info.get("Buffers",      0) * 1024
    cached    = info.get("Cached",       0) * 1024
    available = info.get("MemAvailable", free + buffers + cached) * 1024
    used      = total - available
    percent   = round(used / total * 100, 1) if total else 0.0
    swap_total = info.get("SwapTotal",   0) * 1024
    swap_free  = info.get("SwapFree",    0) * 1024

    return {
        "total":      round(total      / 1024**3, 2),
        "available":  round(available  / 1024**3, 2),
        "used":       round(used       / 1024**3, 2),
        "percent":    percent,
        "swap_total": round(swap_total / 1024**3, 2),
        "swap_used":  round((swap_total - swap_free) / 1024**3, 2),
    }


def get_swappiness() -> int:
    """
    Read the current vm.swappiness kernel parameter.

    Returns:
        Integer value (0–100), or -1 on failure.
    """
    val = safe_read("/proc/sys/vm/swappiness").strip()
    try:
        return int(val)
    except (ValueError, TypeError):
        return -1


# ── Disk helpers ──────────────────────────────────────────────────────────────

def get_disk_partitions() -> list:
    """
    Return a list of mounted disk partitions with usage statistics.

    Returns:
        List of dicts: {mountpoint, total_gb, used_gb, free_gb, percent, fstype}
    """
    result = []
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                result.append({
                    "mountpoint": part.mountpoint,
                    "total_gb":   round(usage.total / 1024**3, 2),
                    "used_gb":    round(usage.used  / 1024**3, 2),
                    "free_gb":    round(usage.free  / 1024**3, 2),
                    "percent":    usage.percent,
                    "fstype":     part.fstype,
                })
            except (PermissionError, OSError):
                continue
        return result
    except ImportError:
        pass

    # Fallback: parse df output
    rc, out, _ = run_cmd("df -BG --output=target,size,used,avail,pcent,fstype 2>/dev/null", timeout=8)
    if rc != 0:
        return result
    lines = out.splitlines()[1:]  # skip header
    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            result.append({
                "mountpoint": parts[0],
                "total_gb":   float(parts[1].rstrip("G")),
                "used_gb":    float(parts[2].rstrip("G")),
                "free_gb":    float(parts[3].rstrip("G")),
                "percent":    float(parts[4].rstrip("%")),
                "fstype":     parts[5],
            })
        except (ValueError, IndexError):
            continue
    return result


def get_disk_io() -> Dict[str, int]:
    """
    Return cumulative disk I/O counters.

    Returns:
        Dict with keys: read_bytes, write_bytes, read_count, write_count.
    """
    try:
        import psutil
        counters = psutil.disk_io_counters()
        if counters:
            return {
                "read_bytes":  counters.read_bytes,
                "write_bytes": counters.write_bytes,
                "read_count":  counters.read_count,
                "write_count": counters.write_count,
            }
    except (ImportError, AttributeError):
        pass

    # Fallback: /proc/diskstats (sum across all disks)
    read_bytes = write_bytes = read_count = write_count = 0
    try:
        for line in open("/proc/diskstats"):
            parts = line.split()
            if len(parts) < 14:
                continue
            read_count  += int(parts[3])
            read_bytes  += int(parts[5]) * 512
            write_count += int(parts[7])
            write_bytes += int(parts[9]) * 512
    except Exception:
        pass
    return {
        "read_bytes":  read_bytes,
        "write_bytes": write_bytes,
        "read_count":  read_count,
        "write_count": write_count,
    }


def is_ssd(device: str = "") -> bool:
    """
    Determine whether a block device is an SSD (rotational == 0).

    Args:
        device: Device name (e.g. "sda"). If empty, checks all disks.

    Returns:
        True if any/all checked device(s) are non-rotational.
    """
    if device:
        path = f"/sys/block/{device}/queue/rotational"
        return safe_read(path).strip() == "0"

    # Check all block devices
    rc, out, _ = run_cmd("lsblk -d -o name,rota 2>/dev/null", timeout=5)
    if rc == 0:
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "0":
                return True
    return False


# ── Network helpers ───────────────────────────────────────────────────────────

def get_network_io() -> Dict[str, int]:
    """
    Return cumulative network I/O counters.

    Returns:
        Dict with keys: bytes_sent, bytes_recv, packets_sent, packets_recv.
    """
    try:
        import psutil
        counters = psutil.net_io_counters()
        if counters:
            return {
                "bytes_sent":    counters.bytes_sent,
                "bytes_recv":    counters.bytes_recv,
                "packets_sent":  counters.packets_sent,
                "packets_recv":  counters.packets_recv,
            }
    except (ImportError, AttributeError):
        pass

    # Fallback: /proc/net/dev
    sent = recv = psent = precv = 0
    try:
        for line in open("/proc/net/dev"):
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            if "lo" in iface:
                continue
            parts = data.split()
            if len(parts) >= 9:
                recv  += int(parts[0])
                precv += int(parts[1])
                sent  += int(parts[8])
                psent += int(parts[9])
    except Exception:
        pass
    return {
        "bytes_sent":   sent,
        "bytes_recv":   recv,
        "packets_sent": psent,
        "packets_recv": precv,
    }


def get_open_ports() -> list:
    """
    Return a list of currently listening TCP/UDP ports.

    Prefers ``ss``; falls back to ``netstat``.

    Returns:
        List of dicts: {port, proto, pid, process}
    """
    ports = []

    # Try ss first
    if which("ss"):
        rc, out, _ = run_cmd("ss -tlunp 2>/dev/null", timeout=8)
        if rc == 0:
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 5:
                    continue
                proto = parts[0]
                local = parts[4]
                pid = process = ""
                if len(parts) > 6:
                    # extract pid/process from "users:(("name",pid=N,fd=M))"
                    import re
                    m = re.search(r'pid=(\d+)', parts[-1])
                    if m:
                        pid = m.group(1)
                    m2 = re.search(r'"([^"]+)"', parts[-1])
                    if m2:
                        process = m2.group(1)
                try:
                    port_str = local.rsplit(":", 1)[-1]
                    port_num = int(port_str)
                    ports.append({"port": port_num, "proto": proto,
                                  "pid": pid, "process": process})
                except (ValueError, IndexError):
                    continue
            return ports

    # Fallback: netstat
    if which("netstat"):
        rc, out, _ = run_cmd("netstat -tlunp 2>/dev/null", timeout=8)
        if rc == 0:
            import re
            for line in out.splitlines()[2:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                proto = parts[0]
                local = parts[3]
                pid = process = ""
                if len(parts) >= 7:
                    pid_proc = parts[6]
                    if "/" in pid_proc:
                        pid, process = pid_proc.split("/", 1)
                try:
                    port_num = int(local.rsplit(":", 1)[-1])
                    ports.append({"port": port_num, "proto": proto,
                                  "pid": pid, "process": process})
                except (ValueError, IndexError):
                    continue

    return ports


# ── System info ───────────────────────────────────────────────────────────────

def get_uptime_seconds() -> int:
    """
    Return system uptime in seconds.

    Returns:
        Integer seconds since last boot, or -1 on failure.
    """
    try:
        import psutil
        return int(time.time() - psutil.boot_time())
    except ImportError:
        pass

    # Fallback: /proc/uptime
    val = safe_read("/proc/uptime").split()
    try:
        return int(float(val[0]))
    except (IndexError, ValueError):
        return -1


def get_boot_time_seconds() -> float:
    """
    Return the time the system last booted as a UNIX timestamp.

    Returns:
        Float UNIX timestamp, or 0.0 on failure.
    """
    try:
        import psutil
        return psutil.boot_time()
    except ImportError:
        pass

    uptime = get_uptime_seconds()
    if uptime >= 0:
        return time.time() - uptime
    return 0.0


def get_kernel_version() -> str:
    """
    Return the running kernel version string (e.g. "6.8.0-45-generic").

    Returns:
        Kernel version string, or "unknown".
    """
    import platform
    try:
        return platform.release() or "unknown"
    except Exception:
        rc, out, _ = run_cmd("uname -r", timeout=5)
        return out if rc == 0 and out else "unknown"


# ── File / path helpers ───────────────────────────────────────────────────────

def safe_read(path: str) -> str:
    """
    Read a file safely, returning empty string on any error.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        File contents as a string, or "".
    """
    try:
        return Path(path).read_text()
    except Exception:
        return ""


def dir_size_mb(path: str) -> float:
    """
    Return the total size of a directory tree in megabytes.

    Args:
        path: Absolute path to the directory.

    Returns:
        Size in MB as a float, or 0.0 on failure / non-existent path.
    """
    p = Path(path)
    if not p.exists():
        return 0.0

    total = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file() and not f.is_symlink():
                    total += f.stat().st_size
            except (OSError, PermissionError):
                continue
        return round(total / (1024 ** 2), 2)
    except Exception:
        # Fallback to du command
        rc, out, _ = run_cmd(f"du -sm {path} 2>/dev/null | cut -f1", timeout=10)
        try:
            return float(out) if rc == 0 else 0.0
        except ValueError:
            return 0.0


def file_count(path: str) -> int:
    """
    Count regular files (non-recursive) inside a directory.

    Args:
        path: Absolute path to the directory.

    Returns:
        Integer file count, or 0 on failure.
    """
    p = Path(path)
    if not p.exists():
        return 0
    try:
        return sum(1 for f in p.iterdir() if f.is_file())
    except (OSError, PermissionError):
        return 0
