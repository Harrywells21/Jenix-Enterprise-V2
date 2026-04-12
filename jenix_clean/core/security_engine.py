"""
core/security_engine.py
───────────────────────
Network security scanning engine for JENIX.

Provides:
  - scan_ports()     : List all listening TCP/UDP ports with process info
  - classify_risk()  : Assign a risk tier (green / yellow / red) to each port

All public functions return:
    {"success": bool, "message": str, "data": dict}
"""

from utils.system_utils import run_cmd, which
from utils.logger import log, audit

# ── Risk classification tables ────────────────────────────────────────────────

# Ports that are universally expected and low-risk
_GREEN_PORTS = {
    22,    # SSH
    80,    # HTTP
    443,   # HTTPS
    53,    # DNS (local resolver)
    123,   # NTP
    631,   # CUPS (local printing)
    5353,  # mDNS (Avahi)
}

# Ports that are common but deserve a second look
_YELLOW_PORTS = {
    21,    # FTP — unencrypted
    23,    # Telnet
    25,    # SMTP
    110,   # POP3
    143,   # IMAP
    3306,  # MySQL
    5432,  # PostgreSQL
    6379,  # Redis
    27017, # MongoDB
    8080,  # HTTP alt / dev servers
    8443,  # HTTPS alt
    3000,  # Node dev
    4000,  # Various dev servers
    5000,  # Flask / dev
    9200,  # Elasticsearch
    9300,  # Elasticsearch transport
}

# Processes that are well-known and trusted system services
_TRUSTED_PROCESSES = {
    "sshd", "nginx", "apache2", "httpd", "systemd", "systemd-resolve",
    "systemd-network", "dnsmasq", "cups", "avahi-daemon", "chronyd",
    "ntpd", "postfix", "dovecot", "mariadbd", "mysqld", "postgres",
    "redis-server", "mongod", "elasticsearch", "node", "python3",
    "python", "flask", "gunicorn", "uvicorn",
}

# Processes that are immediately suspicious regardless of port
_SUSPICIOUS_PROCESSES = {
    "nc", "ncat", "netcat", "nmap", "socat", "telnet", "rsh", "rlogin",
    "cryptominer", "xmrig", "minerd", "bash", "sh", "dash", "zsh",
    "ksh", "python", "perl", "ruby",   # flagged when on unusual high ports
}

# Ports that are outright red regardless of classification range
_RED_PORTS = {
    31337,  # Back Orifice
    1337,   # Common backdoor
    4444,   # Metasploit default
    5554,   # Sasser worm
    9999,   # Common RAT
    12345,  # NetBus / various backdoors
    27374,  # SubSeven
    65535,  # Common scan target
}


# ── Port output parser ────────────────────────────────────────────────────────

def _parse_ss_output(stdout: str) -> list:
    """
    Parse ``ss -tulnp`` output into a list of port dicts.

    Each dict: {port: int, proto: str, pid: int, process: str, local_addr: str}
    """
    ports = []
    seen  = set()

    for line in stdout.splitlines():
        parts = line.split()
        # ss header line or empty
        if not parts or parts[0] in ("Netid", "State"):
            continue
        # Minimum expected columns: Netid State Recv-Q Send-Q Local Peer [Process]
        if len(parts) < 5:
            continue

        try:
            # Column 0: protocol (tcp, udp, tcp6, udp6 …)
            proto_raw = parts[0].lower()
            proto     = "tcp" if "tcp" in proto_raw else "udp"

            # Column 4: local address:port  (e.g. "0.0.0.0:22" or "[::]:443")
            local    = parts[4]
            port_str = local.rsplit(":", 1)[-1]
            port     = int(port_str)

            # Last column may contain process info: users:(("sshd",pid=1234,fd=3))
            pid     = 0
            process = "unknown"
            proc_col = parts[-1] if parts[-1].startswith("users:") else ""
            if proc_col:
                # Extract process name
                name_start = proc_col.find('("')
                name_end   = proc_col.find('"', name_start + 2)
                if name_start != -1 and name_end != -1:
                    process = proc_col[name_start + 2 : name_end]
                # Extract pid
                pid_marker = "pid="
                pid_idx    = proc_col.find(pid_marker)
                if pid_idx != -1:
                    pid_substr = proc_col[pid_idx + len(pid_marker):]
                    pid_end    = pid_substr.find(",")
                    pid_end    = pid_end if pid_end != -1 else pid_substr.find(")")
                    if pid_end != -1:
                        pid = int(pid_substr[:pid_end])

            key = (port, proto)
            if key in seen:
                continue
            seen.add(key)

            ports.append({
                "port":       port,
                "proto":      proto,
                "pid":        pid,
                "process":    process,
                "local_addr": local,
            })

        except (IndexError, ValueError):
            continue

    return sorted(ports, key=lambda p: p["port"])


def _parse_netstat_output(stdout: str) -> list:
    """
    Fallback parser for ``netstat -tulnp`` output.
    Mirrors the same dict shape as _parse_ss_output.
    """
    ports = []
    seen  = set()

    for line in stdout.splitlines():
        parts = line.split()
        # Skip headers and blank lines
        if not parts or parts[0] in ("Active", "Proto", "Netid"):
            continue
        if len(parts) < 4:
            continue

        try:
            proto_raw = parts[0].lower()
            if not ("tcp" in proto_raw or "udp" in proto_raw):
                continue
            proto = "tcp" if "tcp" in proto_raw else "udp"

            # netstat column 3 is Local Address
            local    = parts[3]
            port_str = local.rsplit(":", 1)[-1]
            port     = int(port_str)

            pid     = 0
            process = "unknown"
            # netstat puts pid/program in last column when run with -p
            if len(parts) >= 7 and "/" in parts[-1]:
                pid_proc = parts[-1]
                pid_part, proc_part = pid_proc.split("/", 1)
                try:
                    pid = int(pid_part)
                except ValueError:
                    pass
                process = proc_part.strip() or "unknown"

            key = (port, proto)
            if key in seen:
                continue
            seen.add(key)

            ports.append({
                "port":       port,
                "proto":      proto,
                "pid":        pid,
                "process":    process,
                "local_addr": local,
            })

        except (IndexError, ValueError):
            continue

    return sorted(ports, key=lambda p: p["port"])


def _flag_process(process: str, port: int) -> dict:
    """
    Return a dict with 'flagged' bool and 'flag_reason' string.

    Flags:
      - Process is in the known-suspicious list
      - Process is 'unknown' on a privileged port (< 1024)
      - A shell interpreter is listening on any port (unusual)
      - Process is unknown on a non-registered high port
    """
    proc_lower = process.lower().strip()

    # Shell on any listening port is extremely suspicious
    _shells = {"bash", "sh", "dash", "zsh", "ksh", "fish", "csh", "tcsh"}
    if proc_lower in _shells:
        return {
            "flagged":     True,
            "flag_reason": f"Shell process '{process}' listening on a port — likely backdoor",
        }

    # Known bad tools
    _bad_tools = {"nc", "ncat", "netcat", "socat", "nmap", "xmrig", "minerd",
                  "cryptominer", "telnetd", "rshd", "rlogind"}
    if proc_lower in _bad_tools:
        return {
            "flagged":     True,
            "flag_reason": f"Suspicious tool '{process}' is listening — investigate immediately",
        }

    # Unknown process on a privileged port
    if process == "unknown" and port < 1024:
        return {
            "flagged":     True,
            "flag_reason": f"Privileged port {port} has no identifiable process (run as root?)",
        }

    # Unknown process on a high non-registered port
    if process == "unknown" and port > 49151:
        return {
            "flagged":     True,
            "flag_reason": f"High dynamic port {port} with unknown owning process",
        }

    return {"flagged": False, "flag_reason": ""}


# ── Public API ────────────────────────────────────────────────────────────────

def scan_ports() -> dict:
    """
    Enumerate all listening TCP/UDP ports using ``ss``, falling back to
    ``netstat`` if ss is unavailable.

    Enhanced behaviour vs. baseline:
      • Uses the correct parser for each tool (ss vs netstat).
      • Attaches per-port process flags from _flag_process().
      • risk_summary now includes a 'flagged' count.

    Returns:
        {"success": bool, "message": str,
         "data": {"ports": list, "risk_summary": dict}}
    """
    log.info("[security] scan_ports started")

    stdout = ""
    tool   = None

    if which("ss"):
        rc, stdout, stderr = run_cmd("ss -tulnp", timeout=15)
        tool = "ss"
    elif which("netstat"):
        rc, stdout, stderr = run_cmd("netstat -tulnp", timeout=15)
        tool = "netstat"
    else:
        log.warning("[security] Neither ss nor netstat available")
        return {
            "success": False,
            "message": "Port scanning tools (ss / netstat) not found on this system.",
            "data":    {"ports": [], "risk_summary": {}},
        }

    if rc != 0:
        log.error(f"[security] {tool} failed: {stderr}")
        return {
            "success": False,
            "message": f"{tool} command failed: {stderr[:120]}",
            "data":    {"ports": [], "risk_summary": {}},
        }

    # Choose the correct parser
    if tool == "ss":
        ports = _parse_ss_output(stdout)
    else:
        ports = _parse_netstat_output(stdout)

    # Attach process flags to every port entry
    for p in ports:
        flag_info = _flag_process(p["process"], p["port"])
        p["flagged"]     = flag_info["flagged"]
        p["flag_reason"] = flag_info["flag_reason"]

    # Build risk summary
    risk_summary = {
        "total":   len(ports),
        "green":   sum(1 for p in ports if p["port"] in _GREEN_PORTS),
        "yellow":  sum(1 for p in ports if p["port"] in _YELLOW_PORTS),
        "red":     sum(
            1 for p in ports
            if p["port"] not in _GREEN_PORTS and p["port"] not in _YELLOW_PORTS
        ),
        "flagged": sum(1 for p in ports if p["flagged"]),
    }

    flagged_ports = [p for p in ports if p["flagged"]]
    warning_msg   = ""
    if flagged_ports:
        names = ", ".join(
            f"{p['port']}/{p['proto']} ({p['process']})" for p in flagged_ports
        )
        warning_msg = f" WARNING — flagged ports: {names}."

    log.info(f"[security] Found {len(ports)} listening port(s)")
    audit("security", "scan_ports executed", {
        "total":   len(ports),
        **risk_summary,
    })

    return {
        "success": True,
        "message": f"Found {len(ports)} listening port(s).{warning_msg}",
        "data": {
            "ports":        ports,
            "risk_summary": risk_summary,
        },
    }


def classify_risk() -> dict:
    """
    Scan all listening ports and assign each one a risk tier.

    Tiers:
      green  — well-known, expected service (SSH, HTTP, HTTPS, DNS …)
      yellow — common but warrants review (DB ports, FTP, unencrypted mail …)
      red    — unknown / suspicious (unlisted high ports, known bad ports,
               suspicious processes, shell listeners …)

    Enhanced behaviour vs. baseline:
      • Known-bad ports (_RED_PORTS) are always red regardless of range.
      • Flagged processes escalate any entry to red.
      • Each entry carries 'flagged' and 'flag_reason' from scan_ports().
      • Detailed notes explain exactly why each tier was assigned.

    Returns:
        {"success": bool, "message": str,
         "data": {"ports": list, "risk_summary": dict}}
    """
    log.info("[security] classify_risk started")

    # Re-use scan_ports to get the raw list (already includes flag info)
    scan_result = scan_ports()
    if not scan_result["success"]:
        return scan_result

    raw_ports  = scan_result["data"]["ports"]
    classified = []

    for entry in raw_ports:
        port    = entry["port"]
        process = entry.get("process", "unknown")
        flagged = entry.get("flagged", False)
        flag_reason = entry.get("flag_reason", "")

        # ── Tier determination ─────────────────────────────────────────────

        # 1. Known-bad ports are always red — regardless of anything else
        if port in _RED_PORTS:
            risk = "red"
            note = f"Port {port} is on the known-malicious list — investigate immediately"

        # 2. Flagged process → escalate to red with explanation
        elif flagged:
            risk = "red"
            note = flag_reason or f"Process '{process}' flagged as suspicious"

        # 3. Green safe-list
        elif port in _GREEN_PORTS:
            risk = "green"
            if process not in _TRUSTED_PROCESSES and process != "unknown":
                # Unexpected process on a normally-safe port
                risk = "yellow"
                note = (
                    f"Port {port} is normally safe but is held by '{process}' "
                    f"instead of the expected service — verify"
                )
            else:
                note = "Expected system service"

        # 4. Yellow known-service list
        elif port in _YELLOW_PORTS:
            risk = "yellow"
            note = "Common service — verify it is intentional and access is restricted"

        # 5. Privileged port not in any list
        elif port < 1024:
            risk = "yellow"
            note = f"Privileged port {port} not in the safe-list — review owning service"

        # 6. Registered port range (1024–49151) not explicitly known
        elif 1024 <= port <= 49151:
            if process in _TRUSTED_PROCESSES:
                risk = "yellow"
                note = f"Registered port {port} held by trusted service '{process}' — verify intent"
            elif process == "unknown":
                risk = "red"
                note = f"Registered port {port} has no identifiable owning process"
            else:
                risk = "yellow"
                note = f"Registered port {port} — unfamiliar service '{process}', verify"

        # 7. Dynamic / ephemeral / very high port
        else:
            if process in _TRUSTED_PROCESSES:
                # e.g. a known service bound to a non-standard high port
                risk = "yellow"
                note = (
                    f"High port {port} held by '{process}' — "
                    f"unusual binding, confirm it is intentional"
                )
            else:
                risk = "red"
                note = (
                    f"High/dynamic port {port} with unrecognised process '{process}' "
                    f"— potentially suspicious"
                )

        classified.append({
            **entry,
            "risk":        risk,
            "note":        note,
        })

    # Summary counts
    risk_summary = {
        "green":   sum(1 for p in classified if p["risk"] == "green"),
        "yellow":  sum(1 for p in classified if p["risk"] == "yellow"),
        "red":     sum(1 for p in classified if p["risk"] == "red"),
        "flagged": sum(1 for p in classified if p.get("flagged", False)),
        "total":   len(classified),
    }

    red_count     = risk_summary["red"]
    flagged_count = risk_summary["flagged"]

    msg = (
        f"Classified {len(classified)} port(s). "
        f"{risk_summary['green']} green, "
        f"{risk_summary['yellow']} yellow, "
        f"{red_count} red."
    )
    if red_count:
        msg += " — Review red ports immediately."
    if flagged_count:
        msg += f" {flagged_count} port(s) have flagged/suspicious processes."

    audit("security", "classify_risk executed", risk_summary)

    return {
        "success": True,
        "message": msg,
        "data": {
            "ports":        classified,
            "risk_summary": risk_summary,
        },
    }
