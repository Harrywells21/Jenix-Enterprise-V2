import psutil, socket, platform, time

_prev_net  = None
_prev_disk = None
_prev_ts   = None

def get_system_info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "ip":       _get_ip(),
        "os_name":  f"{platform.system()} {platform.release()}",
        "kernel":   platform.version()[:60],
    }

def _get_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
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

    # Disk usage (root partition)
    try:
        disk = psutil.disk_usage("/").percent
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
