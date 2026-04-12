"""
threat_intelligence.py
══════════════════════
JENIX v4.4 — Threat Intelligence & Forensic Capture Module

Provides two independent, zero-dependency-on-each-other capabilities:

  ✦ ThreatIntelligence   — lightweight local IOC database (process names,
                           suspicious ports, suspicious execution paths).
                           Scores and annotates SuspiciousProcessIssue objects
                           produced by SuspiciousProcessDetector.

  ✦ ForensicCapture      — captures a full forensic snapshot of a process
                           (PID, name, cmdline, exe, open files, network
                           connections, optional SHA-256 of the binary)
                           and writes it as JSON to
                           ~/.jenix/forensics/<pid>_<timestamp>.json.

Both components are opt-in and add zero overhead to the existing scan path
unless explicitly called.  They integrate with:

  • SuspiciousProcessDetector  (via ThreatIntelligence.enrich())
  • AutoResponder              (via ForensicCapture.capture_before_kill())

Usage (stand-alone):
  from threat_intelligence import ThreatIntelligence, ForensicCapture

  ti = ThreatIntelligence()
  fc = ForensicCapture()

  # Enrich a SuspiciousProcessIssue with TI signals:
  ti.enrich(issue)

  # Capture forensics before a kill:
  snapshot_path = fc.capture(pid)

Design goals:
  • O(1) lookups via frozenset / dict  (no regex on the hot path)
  • Graceful degradation if psutil / hashlib unavailable
  • All disk I/O is in ForensicCapture; ThreatIntelligence is pure in-memory
  • Thread-safe (ForensicCapture uses a per-instance lock for the JSON write)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None          # type: ignore
    _HAS_PSUTIL = False

# ── Module logger ─────────────────────────────────────────────────────────────
_ti_logger = logging.getLogger("jenix.threat_intel")

# ── Forensics output directory ────────────────────────────────────────────────
_FORENSICS_DIR = Path.home() / ".jenix" / "forensics"

# ── Score bonus applied when a TI rule matches ───────────────────────────────
_TI_SCORE_BONUS = 30   # added directly to SuspiciousProcessIssue.threat_score

# ── Severity label injected into _signal_weights ─────────────────────────────
_TI_SEVERITY = "HIGH"


# ══════════════════════════════════════════════════════════════════════════════
# BUILT-IN IOC DATABASES
# ══════════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Known-bad process names
# These are names that have been associated with malware, cryptominers,
# rootkits, reverse shells, or other malicious tooling.  The list is
# intentionally conservative to minimise false positives.
# ---------------------------------------------------------------------------
_KNOWN_BAD_NAMES: FrozenSet[str] = frozenset({
    # Cryptominers
    "xmrig", "xmrigdaemon", "xmrig-notls", "minergate", "cpuminer",
    "minerd", "cgminer", "bfgminer", "ethminer", "nbminer", "t-rex",
    "teamredminer", "lolminer", "phoenixminer", "gminer",
    # Generic miner wrapper names observed in the wild
    "kdevtmpfsi", "kinsing", "kworkerds", "sysupdate", "networkservice",
    "update-center", "java32", "java64",
    # Reverse-shell / C2 tooling names used in attacks
    "msf",  "msfconsole", "meterpreter",
    "empire", "covenant", "sliver", "havoc",
    # Coin-miner dropper names
    "dbused", "autoupdater", "bioset", "pamdicks",
    # Linux-specific rootkit / botnet process names
    "ld-linux-x86", "kauditd_", "kblockd_", "watchbog",
    "ziggy", "dota3", "httpshelper",
    # Crypto-jacking via shell names
    "bashcrypto", "cr5sh",
})

# ---------------------------------------------------------------------------
# Suspicious listening / connecting ports
# Includes common C2 ports, well-known RAT ports, and ports that have no
# legitimate reason to appear in most production environments.
# ---------------------------------------------------------------------------
_SUSPICIOUS_PORTS: FrozenSet[int] = frozenset({
    # Common C2 / RAT ports
    1080,   # SOCKS proxy used by many C2 frameworks
    4444,   # Metasploit default reverse shell
    4445,   # Metasploit alternate
    5555,   # Android Debug Bridge; also used by botnets
    6666,   # IRC C2
    6667,   # IRC C2
    6668,   # IRC C2
    6669,   # IRC C2
    7777,   # Common C2 / coin-miner pool alt-port
    8888,   # Jupyter (legitimate but frequently exploited); also C2
    9001,   # Tor ORPort default
    9050,   # Tor SOCKSPort
    9051,   # Tor ControlPort
    12345,  # NetBus RAT
    27374,  # Sub7 RAT
    31337,  # Back Orifice / elite hacker tradition
    65535,  # Often used by coin-miner C2 to avoid detection
    # Coin-miner pool ports
    3333,   # Monero pool (standard)
    3334,
    5556,
    7778,
    10008,
    14444,
    14433,
    # Common coin-miner SSL alt-ports
    443,    # Included because miners tunnel over 443; flag only if exe is suspicious
    # !! Note: 443 is valid for most processes; the check is combined with
    # !!        other signals — not used as a standalone kill trigger.
})

# ---------------------------------------------------------------------------
# Suspicious execution-path prefixes / substrings
# These paths indicate that a binary is running from a world-writable,
# memory-mapped, or otherwise anomalous location.
# ---------------------------------------------------------------------------
_SUSPICIOUS_PATH_PATTERNS: Tuple[str, ...] = (
    "/tmp/",
    "/var/tmp/",
    "/dev/shm/",
    "/run/shm/",
    "/proc/",            # executing directly from /proc is deeply suspicious
    "/sys/",
    "/.cache/",
    "/home/",            # binaries executing directly from home dirs
    "/root/",
    "/var/www/",         # web root — should never spawn persistent processes
    "/srv/",
    # Hidden directories anywhere in the path
    "/.",                # catches /.hidden/something OR /home/user/.evil/bin
)

# Specific filenames (not just paths) that are highly suspicious
_SUSPICIOUS_FILENAMES: FrozenSet[str] = frozenset({
    ".x", ".sh", ".py", ".pl", ".rb",  # hidden script-extension binaries
    "a.out",             # default compiler output — never in production
    "payload", "dropper", "loader", "stager", "implant",
    "beacon", "agent", "rat", "shell",
    "reverse", "bind",
})


# ══════════════════════════════════════════════════════════════════════════════
# 1.  THREAT INTELLIGENCE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ThreatIntelligence:
    """
    Lightweight, in-memory threat intelligence engine.

    Maintains three IOC sets (bad names, suspicious ports, suspicious paths)
    and exposes a single enrich() method that annotates a
    SuspiciousProcessIssue with additional signals when a match is found.

    All lookups are O(1) (frozenset membership) except the path-pattern scan
    which is O(P) where P = number of path patterns (currently < 30).

    Thread-safe: all instance state is read-only after __init__; enrich()
    mutates only the passed-in issue object (caller's responsibility).

    Parameters
    ──────────
    extra_bad_names
        Additional process names to treat as known-bad.
    extra_suspicious_ports
        Additional ports to flag.
    extra_path_patterns
        Additional path prefixes / substrings to treat as suspicious.
    ti_score_bonus
        Score added to threat_score on a TI hit.  Default: 30.
    """

    def __init__(
        self,
        extra_bad_names:        Optional[Set[str]]   = None,
        extra_suspicious_ports: Optional[Set[int]]   = None,
        extra_path_patterns:    Optional[Tuple[str, ...]] = None,
        ti_score_bonus:         int                  = _TI_SCORE_BONUS,
    ) -> None:
        self._bad_names: FrozenSet[str] = (
            _KNOWN_BAD_NAMES | frozenset(n.lower() for n in (extra_bad_names or set()))
        )
        self._suspicious_ports: FrozenSet[int] = (
            _SUSPICIOUS_PORTS | frozenset(extra_suspicious_ports or set())
        )
        self._path_patterns: Tuple[str, ...] = (
            _SUSPICIOUS_PATH_PATTERNS + tuple(extra_path_patterns or ())
        )
        self._score_bonus = int(ti_score_bonus)

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, issue: Any) -> List[Tuple[str, str]]:
        """
        Evaluate a SuspiciousProcessIssue (or duck-typed object) against the
        IOC database.

        Returns a list of (reason_string, severity_string) tuples —
        one per matched rule.  Returns an empty list if no rules match.

        This method is pure (no side-effects); call enrich() to mutate
        the issue in-place.
        """
        hits: List[Tuple[str, str]] = []

        name     = (getattr(issue, "name",     "") or "").lower().strip()
        exe_path = (getattr(issue, "exe_path", "") or "").strip()
        cmdline  = (getattr(issue, "cmdline",  "") or "").lower()

        # ── 1. Known-bad process name ─────────────────────────────────────────
        if name in self._bad_names:
            hits.append((
                f"Matched known threat pattern: process name '{name}' "
                f"is in the known-bad IOC database",
                "HIGH",
            ))

        # Also check if any token in the cmdline matches a known-bad name
        # (catches renamed processes where argv[0] leaks the real identity)
        else:
            for token in cmdline.split()[:5]:   # only first 5 tokens for speed
                clean = token.lstrip("./").split("/")[-1].lower()
                if clean in self._bad_names:
                    hits.append((
                        f"Matched known threat pattern: cmdline token '{clean}' "
                        f"is in the known-bad IOC database",
                        "HIGH",
                    ))
                    break

        # ── 2. Suspicious executable path ────────────────────────────────────
        if exe_path:
            for pattern in self._path_patterns:
                if pattern in exe_path:
                    hits.append((
                        f"Matched known threat pattern: executable path '{exe_path}' "
                        f"contains suspicious pattern '{pattern}'",
                        "HIGH",
                    ))
                    break  # one path hit is enough

            # Hidden or bare filename check
            binary_name = Path(exe_path).name.lower()
            if binary_name in _SUSPICIOUS_FILENAMES:
                hits.append((
                    f"Matched known threat pattern: binary filename '{binary_name}' "
                    f"matches a known-suspicious filename",
                    "HIGH",
                ))

        # ── 3. Suspicious network connections ────────────────────────────────
        #   We check the live connections stored on the issue (if present)
        #   as well as any port numbers embedded in the cmdline.
        self._check_ports(issue, hits)

        return hits

    def enrich(self, issue: Any) -> bool:
        """
        Mutate a SuspiciousProcessIssue in-place by appending TI-derived
        signals to its reasons list, adding to its threat_score, and
        recalculating its threat_level.

        Returns True if at least one TI rule matched.
        """
        hits = self.check(issue)
        if not hits:
            return False

        reasons_attr = getattr(issue, "reasons", None)
        if reasons_attr is None:
            return False

        sw_attr = getattr(issue, "_signal_weights", None)

        for reason, severity in hits:
            if reason not in reasons_attr:
                reasons_attr.append(reason)
                if sw_attr is not None:
                    from threat_intelligence import _SEVERITY_WEIGHT_MAP
                    sw_attr.append((reason, _SEVERITY_WEIGHT_MAP.get(severity, 40)))

        # Bump threat_score
        current_score = getattr(issue, "threat_score", 0)
        new_score     = current_score + self._score_bonus * len(hits)
        try:
            object.__setattr__(issue, "threat_score", new_score)
        except (AttributeError, TypeError):
            issue.threat_score = new_score

        # Recalculate threat_level from new score
        new_level = _score_to_level(new_score)
        try:
            object.__setattr__(issue, "threat_level", new_level)
        except (AttributeError, TypeError):
            issue.threat_level = new_level

        # Append a TI summary to correlation_summary
        ti_note = (
            f" [TI: {len(hits)} IOC match(es) +{self._score_bonus * len(hits)} pts]"
        )
        cs = getattr(issue, "correlation_summary", "") or ""
        try:
            object.__setattr__(issue, "correlation_summary", cs.rstrip(".") + ti_note)
        except (AttributeError, TypeError):
            issue.correlation_summary = cs.rstrip(".") + ti_note

        _ti_logger.warning(
            "TI enrichment: PID %d (%s) — %d IOC hit(s), new score=%d [%s]",
            getattr(issue, "pid",  0),
            getattr(issue, "name", "?"),
            len(hits),
            new_score,
            new_level,
        )
        return True

    def is_known_bad_name(self, name: str) -> bool:
        """Quick check — True if the name is in the known-bad IOC set."""
        return name.lower().strip() in self._bad_names

    def is_suspicious_port(self, port: int) -> bool:
        """Quick check — True if the port is flagged as suspicious."""
        return port in self._suspicious_ports

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_ports(self, issue: Any, hits: List[Tuple[str, str]]) -> None:
        """
        Append a hit if the issue has connections on a suspicious port.
        Reads from issue.connections (int count) but also inspects
        issue._raw_connections (list[psutil._common.sconn]) if present,
        since that richer field is populated by ForensicCapture.
        """
        raw_conns = getattr(issue, "_raw_connections", None)
        if raw_conns:
            flagged_ports: Set[int] = set()
            for conn in raw_conns:
                lport = getattr(getattr(conn, "laddr", None), "port", 0) or 0
                rport = getattr(getattr(conn, "raddr", None), "port", 0) or 0
                for p in (lport, rport):
                    if p and p in self._suspicious_ports:
                        # 443 is only flagged when combined with other signals
                        if p == 443:
                            existing_reasons = getattr(issue, "reasons", [])
                            if not existing_reasons:
                                continue
                        flagged_ports.add(p)

            for p in sorted(flagged_ports):
                hits.append((
                    f"Matched known threat pattern: process has connection on "
                    f"suspicious port {p}",
                    "HIGH",
                ))


# ══════════════════════════════════════════════════════════════════════════════
# 2.  FORENSIC CAPTURE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ForensicSnapshot:
    """
    Immutable forensic record for a single process capture.
    All fields are JSON-serialisable.
    """
    pid:             int
    name:            str
    cmdline:         str
    exe_path:        str
    username:        str
    status:          str
    create_time_utc: str
    capture_time_utc:str
    open_files:      List[str]          = field(default_factory=list)
    connections:     List[Dict]         = field(default_factory=list)
    sha256_binary:   Optional[str]      = None
    environment:     Dict[str, str]     = field(default_factory=dict)
    parent_pid:      int                = 0
    parent_name:     str                = ""
    threads:         int                = 0
    cpu_pct:         float              = 0.0
    mem_rss_mb:      float              = 0.0
    capture_path:    str                = ""   # set after write

    def to_dict(self) -> dict:
        return {
            "jenix_forensic_version": "4.4",
            "capture_time_utc":  self.capture_time_utc,
            "pid":               self.pid,
            "name":              self.name,
            "cmdline":           self.cmdline,
            "exe_path":          self.exe_path,
            "username":          self.username,
            "status":            self.status,
            "create_time_utc":   self.create_time_utc,
            "parent_pid":        self.parent_pid,
            "parent_name":       self.parent_name,
            "threads":           self.threads,
            "cpu_pct":           self.cpu_pct,
            "mem_rss_mb":        self.mem_rss_mb,
            "open_files":        self.open_files,
            "connections":       self.connections,
            "sha256_binary":     self.sha256_binary,
            "environment":       self.environment,
            "capture_path":      self.capture_path,
        }


class ForensicCapture:
    """
    Captures a detailed forensic snapshot of a running process and writes
    it to ~/.jenix/forensics/<pid>_<timestamp>.json before the process
    is killed by AutoResponder.

    Features
    ────────
    • PID, name, cmdline, exe path, username, status, parent
    • Open file paths (up to max_files)
    • Network connections with local/remote address and state
    • Optional SHA-256 hash of the binary on disk
    • Optional environment variables (disabled by default — may leak secrets)
    • Thread-safe write via a per-instance lock

    Parameters
    ──────────
    capture_sha256
        Compute and store SHA-256 of the binary.  Default True.
        Set False to skip the disk I/O on very large binaries.
    capture_env
        Store environment variables.  Default False — may leak credentials.
    max_files
        Maximum number of open file paths to capture.  Default 100.
    max_connections
        Maximum number of connections to capture.  Default 50.
    forensics_dir
        Output directory.  Default ~/.jenix/forensics/
    """

    def __init__(
        self,
        capture_sha256:    bool            = True,
        capture_env:       bool            = False,
        max_files:         int             = 100,
        max_connections:   int             = 50,
        forensics_dir:     Optional[Path]  = None,
    ) -> None:
        self._capture_sha256   = capture_sha256
        self._capture_env      = capture_env
        self._max_files        = max_files
        self._max_connections  = max_connections
        self._forensics_dir    = forensics_dir or _FORENSICS_DIR
        self._lock             = threading.Lock()

        # Ensure output directory exists
        try:
            self._forensics_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _ti_logger.error("Could not create forensics dir %s: %s",
                             self._forensics_dir, exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def capture(self, pid: int, issue: Any = None) -> Optional[Path]:
        """
        Capture a forensic snapshot for `pid` and write it to disk.

        Parameters
        ──────────
        pid
            The PID of the process to snapshot.
        issue
            Optional SuspiciousProcessIssue — used to pre-populate fields
            that are cheap to copy rather than re-query from psutil.

        Returns
        ───────
        Path to the written JSON file, or None if the capture failed.
        """
        if not _HAS_PSUTIL or psutil is None:
            _ti_logger.warning("ForensicCapture.capture() requires psutil — skipping")
            return None

        snapshot = self._build_snapshot(pid, issue)
        if snapshot is None:
            return None

        return self._write_snapshot(snapshot)

    def capture_before_kill(self, issue: Any) -> Optional[Path]:
        """
        Convenience wrapper called by AutoResponder before killing a process.
        Extracts pid from issue and calls capture().
        """
        pid = getattr(issue, "pid", 0)
        if not pid:
            return None
        return self.capture(pid, issue=issue)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_snapshot(self, pid: int, issue: Any) -> Optional[ForensicSnapshot]:
        """
        Construct a ForensicSnapshot by interrogating the live process.
        Returns None if the process no longer exists.
        """
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            _ti_logger.warning("ForensicCapture: PID %d no longer exists", pid)
            return None
        except Exception as exc:
            _ti_logger.error("ForensicCapture: cannot open PID %d: %s", pid, exc)
            return None

        # ── Basic identity ────────────────────────────────────────────────────
        name = ""
        try:   name = proc.name() or ""
        except Exception: pass

        cmdline = ""
        try:   cmdline = " ".join(proc.cmdline())
        except Exception:
            if issue:
                cmdline = getattr(issue, "cmdline", "") or ""

        exe_path = ""
        try:   exe_path = proc.exe() or ""
        except Exception:
            if issue:
                exe_path = getattr(issue, "exe_path", "") or ""

        username = ""
        try:   username = proc.username() or ""
        except Exception: pass

        status = ""
        try:   status = proc.status() or ""
        except Exception: pass

        create_time_utc = ""
        try:
            ct = proc.create_time()
            create_time_utc = datetime.fromtimestamp(
                ct, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception: pass

        parent_pid  = 0
        parent_name = ""
        try:
            parent = proc.parent()
            if parent:
                parent_pid  = parent.pid
                parent_name = parent.name() or ""
        except Exception: pass

        threads = 0
        try:   threads = proc.num_threads()
        except Exception: pass

        cpu_pct = 0.0
        try:   cpu_pct = round(proc.cpu_percent(interval=0.1), 2)
        except Exception: pass

        mem_rss_mb = 0.0
        try:
            mi = proc.memory_info()
            mem_rss_mb = round(mi.rss / 1024**2, 2)
        except Exception: pass

        # ── Open files ────────────────────────────────────────────────────────
        open_files: List[str] = []
        try:
            for f in proc.open_files()[:self._max_files]:
                open_files.append(getattr(f, "path", str(f)))
        except Exception: pass

        # ── Network connections ───────────────────────────────────────────────
        connections: List[Dict] = []
        raw_conns = []
        try:
            raw_conns = proc.connections()
            for conn in raw_conns[:self._max_connections]:
                laddr = getattr(conn, "laddr", None)
                raddr = getattr(conn, "raddr", None)
                connections.append({
                    "fd":     getattr(conn, "fd",     -1),
                    "family": str(getattr(conn, "family", "")),
                    "type":   str(getattr(conn, "type",   "")),
                    "laddr":  f"{laddr.ip}:{laddr.port}" if laddr else "",
                    "raddr":  f"{raddr.ip}:{raddr.port}" if raddr else "",
                    "status": getattr(conn, "status",  ""),
                })
        except Exception: pass

        # Attach raw conns to issue so ThreatIntelligence can inspect ports
        if issue is not None and raw_conns:
            try:
                object.__setattr__(issue, "_raw_connections", raw_conns)
            except (AttributeError, TypeError):
                issue._raw_connections = raw_conns

        # ── SHA-256 of binary ─────────────────────────────────────────────────
        sha256_binary: Optional[str] = None
        if self._capture_sha256 and exe_path:
            sha256_binary = self._hash_file(exe_path)

        # ── Environment ───────────────────────────────────────────────────────
        environment: Dict[str, str] = {}
        if self._capture_env:
            try:
                environment = dict(proc.environ())
            except Exception: pass

        return ForensicSnapshot(
            pid              = pid,
            name             = name,
            cmdline          = cmdline,
            exe_path         = exe_path,
            username         = username,
            status           = status,
            create_time_utc  = create_time_utc,
            capture_time_utc = now_utc,
            open_files       = open_files,
            connections      = connections,
            sha256_binary    = sha256_binary,
            environment      = environment,
            parent_pid       = parent_pid,
            parent_name      = parent_name,
            threads          = threads,
            cpu_pct          = cpu_pct,
            mem_rss_mb       = mem_rss_mb,
        )

    def _write_snapshot(self, snapshot: ForensicSnapshot) -> Optional[Path]:
        """
        Serialise the snapshot to JSON and write to disk (thread-safe).
        Returns the written path or None on error.
        """
        ts_str    = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{snapshot.pid}_{ts_str}.json"
        out_path  = self._forensics_dir / filename

        snapshot.capture_path = str(out_path)

        with self._lock:
            try:
                out_path.write_text(
                    json.dumps(snapshot.to_dict(), indent=2, default=str),
                    encoding="utf-8",
                )
                _ti_logger.info(
                    "Forensic snapshot saved: %s  (PID %d, %s)",
                    out_path, snapshot.pid, snapshot.name,
                )
                print(
                    f"  [FORENSICS]  Snapshot saved → {out_path}  "
                    f"(PID {snapshot.pid}, '{snapshot.name}')"
                )
                return out_path
            except OSError as exc:
                _ti_logger.error(
                    "Failed to write forensic snapshot for PID %d: %s",
                    snapshot.pid, exc,
                )
                return None

    @staticmethod
    def _hash_file(path: str, chunk_size: int = 65536) -> Optional[str]:
        """
        Compute SHA-256 of a file in streaming chunks.
        Returns the hex digest or None if the file cannot be read.
        """
        try:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except (OSError, PermissionError):
            return None
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

# Maps SIGNAL_WEIGHTS-compatible severity strings to score values
_SEVERITY_WEIGHT_MAP: Dict[str, int] = {
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


def _score_to_level(score: int) -> str:
    """Convert a numeric threat_score to a threat_level string."""
    for threshold, level in _THREAT_THRESHOLDS:
        if score > threshold:
            return level
    return "LOW"
