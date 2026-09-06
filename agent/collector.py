import psutil, socket, platform, time, os
from urllib.parse import urlparse

_prev_net  = None
_prev_disk = None
_prev_ts   = None

def _get_os_type() -> str:
    """Normalized OS identifier for display/registration. platform.system()
    returns 'Linux', 'Darwin', or 'Windows' -- Darwin is mapped to 'macOS'
    to match what humans (and this codebase's binary_map/scan-command
    tables) call it. Previously this key was never set anywhere, so
    agent.py's info.get("os_type", "Linux") silently defaulted every
    machine -- including real macOS/Windows machines -- to "Linux" in
    the WS register message."""
    system = platform.system()
    return "macOS" if system == "Darwin" else system

def get_system_info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "ip":       _get_ip(),
        "os_name":  f"{platform.system()} {platform.release()}",
        "kernel":   platform.version()[:60],
        "os_type":  _get_os_type(),
    }

def _get_ip() -> str:
    """Deterministic IP selection: pick the local address the OS would
    actually use to route to the configured JENIX server, instead of
    routing to 8.8.8.8. On multi-homed hosts (e.g. this dev VM's NAT +
    Bridged adapters), routing to an arbitrary public IP can pick a
    different local interface across restarts/DHCP renewals, causing
    the same physical machine to report different self-IDed IPs and
    register as duplicate rows server-side. Routing specifically to the
    server's own host is stable for a given agent-server pairing."""
    server_url = os.getenv("JENIX_SERVER", "")
    if not server_url:
        server_file = None
        try:
            from pathlib import Path
            server_file = Path.home() / ".jenix" / "server_url"
            if server_file.exists():
                server_url = server_file.read_text().strip()
        except Exception:
            pass
    target_host = "8.8.8.8"
    target_port = 80
    if server_url:
        try:
            parsed = urlparse(server_url)
            if parsed.hostname:
                target_host = parsed.hostname
                target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_host, target_port))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def collect_metrics() -> dict:
    global _prev_net, _prev_disk, _prev_ts

    now = time.monotonic()

    # CPU — blocking 1s for accuracy
    cpu = psutil.cpu_percent(interval=1)

    # RAM
    ram = psutil.virtual_memory().percent

    # Disk usage: root partition on Linux/macOS; system drive on Windows
    # (Windows has no single "/" root -- psutil.disk_usage("/") raises there)
    try:
        disk_path = (os.environ.get("SystemDrive", "C:") + "\\") if platform.system() == "Windows" else "/"
        disk = psutil.disk_usage(disk_path).percent
    except Exception:
        disk = 0.0

    # Disk I/O delta
    disk_mb = 0.0
    try:
        curr_disk = psutil.disk_io_counters()
        if curr_disk and _prev_disk and _prev_ts:
            dt = max(now - _prev_ts, 0.001)
            delta = ((curr_disk.read_bytes  - _prev_disk.read_bytes) +
                     (curr_disk.write_bytes - _prev_disk.write_bytes))
            disk_mb = max(0.0, delta / dt / 1_048_576)
        _prev_disk = curr_disk
    except Exception:
        _prev_disk = None

    # Net I/O delta
    net_mb = 0.0
    try:
        curr_net = psutil.net_io_counters()
        if curr_net and _prev_net and _prev_ts:
            dt = max(now - _prev_ts, 0.001)
            delta = ((curr_net.bytes_sent - _prev_net.bytes_sent) +
                     (curr_net.bytes_recv - _prev_net.bytes_recv))
            net_mb = max(0.0, delta / dt / 1_048_576)
        _prev_net = curr_net
    except Exception:
        _prev_net = None

    _prev_ts = now

    return {
        "type":    "metrics",
        "cpu":     round(cpu,     2),
        "ram":     round(ram,     2),
        "disk":    round(disk,    2),
        "net_mb":  round(net_mb,  4),
        "disk_mb": round(disk_mb, 4),
    }
