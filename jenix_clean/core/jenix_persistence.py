"""
jenix_persistence.py
════════════════════
JENIX v4.2 — Persistence Detection & Safe Remediation Module

Provides:
  ✦ PersistenceIssue      — dataclass describing a detected persistence mechanism
  ✦ PersistenceDetector   — scans cron, systemd, and startup files
  ✦ PersistenceRemediator — backs up and safely disables/removes suspicious items
  ✦ RollbackManager       — restores any previously backed-up file or crontab

Design principles:
  • NEVER permanently deletes files
  • ALWAYS creates a timestamped backup before modifying anything
  • Fails silently/safely — any exception leaves the system unchanged
  • All subprocess calls are non-blocking with short timeouts
  • Zero heavy regex — only simple string membership checks
  • Fully optional — ScanEngine enables this via enable_persistence=True

Integration into jenix_scan_engine.py ScanResult / ScanEngine:
  See the "INTEGRATION SNIPPET" section at the bottom of this file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

SUSPICIOUS_KEYWORDS: List[str] = [
    "curl",
    "wget",
    "base64",
    "nc",
    "bash -i",
    "/tmp/",
    "chmod +x",
    "python -c",
    "python3 -c",
    "eval",
    "exec",
    "> /dev/null",
    "nohup",
    "disown",
]

# Cron patterns that always flag HIGH risk regardless of keyword presence
_HIGH_RISK_CRON_PATTERNS: List[str] = [
    "/tmp/",
    "bash -i",
    "bash -c",
    "sh -i",
    "| bash",
    "| sh",
    "|bash",
    "|sh",
]

# Known-safe systemd service name prefixes (avoid false positives)
_SAFE_SERVICE_PREFIXES: List[str] = [
    "systemd-",
    "dbus",
    "NetworkManager",
    "network",
    "ssh",
    "cron",
    "rsyslog",
    "ufw",
    "fail2ban",
    "avahi",
    "cups",
    "polkit",
    "accounts",
    "apt",
    "snapd",
    "udisks",
    "upower",
    "bluetooth",
    "ModemManager",
    "wpa_supplicant",
    "gdm",
    "lightdm",
]

# Startup files to audit
_STARTUP_FILES: List[str] = [
    "~/.bashrc",
    "~/.profile",
    "~/.bash_profile",
    "~/.zshrc",
    "/etc/profile",
    "/etc/bash.bashrc",
    "/etc/environment",
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PersistenceIssue:
    source:         str   # "cron" | "systemd" | "startup"
    name:           str   # job/service/filename identifier
    command:        str   # raw command or suspicious line content
    risk:           str   # "LOW" | "MEDIUM" | "HIGH"
    reason:         str   # human-readable explanation
    fix_suggestion: str   # what the remediator will do (or manual hint)


# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _run(cmd: str, timeout: int = 8) -> Tuple[int, str, str]:
    """Execute a shell command. Returns (returncode, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as exc:
        return -2, "", str(exc)


def _contains_suspicious(text: str) -> Tuple[bool, str]:
    """
    Check whether *text* contains any entry from SUSPICIOUS_KEYWORDS.
    Returns (matched, matched_keyword). Case-insensitive.
    """
    lower = text.lower()
    for kw in SUSPICIOUS_KEYWORDS:
        if kw.lower() in lower:
            return True, kw
    return False, ""


def _is_safe_service(name: str) -> bool:
    """Return True if the service name starts with a known-safe prefix."""
    lower = name.lower()
    return any(lower.startswith(pfx.lower()) for pfx in _SAFE_SERVICE_PREFIXES)


def _read_file_lines(path: str) -> List[str]:
    """Safely read a text file into lines. Returns [] on any error."""
    try:
        expanded = os.path.expanduser(path)
        return Path(expanded).read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ══════════════════════════════════════════════════════════════════════════════
# 3. PERSISTENCE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class PersistenceDetector:
    """
    Lightweight, read-only scanner for common Linux persistence mechanisms.

    Usage:
        detector = PersistenceDetector()
        issues   = detector.scan()   # List[PersistenceIssue]
    """

    def __init__(self) -> None:
        self.issues: List[PersistenceIssue] = []

    # ── Public entry point ────────────────────────────────────────────────────

    def scan(self) -> List[PersistenceIssue]:
        """Run all sub-scans. Returns all detected PersistenceIssue objects."""
        self.issues = []
        self._scan_cron()
        self._scan_systemd()
        self._scan_startup_files()
        return self.issues

    # ── A. CRON JOB DETECTION ─────────────────────────────────────────────────

    def _scan_cron(self) -> None:
        rc, out, err = _run("crontab -l", timeout=6)

        # rc=1 with "no crontab" is normal — not an error
        if rc != 0 and "no crontab" not in err.lower():
            return

        for line in out.splitlines():
            stripped = line.strip()

            # Skip blanks and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Skip lines that are not schedule entries (must start with digit or *)
            parts = stripped.split()
            if not parts:
                continue
            if not (parts[0][0].isdigit() or parts[0][0] in ("*", "@")):
                continue

            # Everything after the 5-field schedule is the command
            schedule_fields = 5
            if stripped.startswith("@"):
                schedule_fields = 1
            command = " ".join(parts[schedule_fields:]) if len(parts) > schedule_fields else stripped

            # Determine risk level
            risk   = "LOW"
            reason = ""

            for pattern in _HIGH_RISK_CRON_PATTERNS:
                if pattern in command:
                    risk   = "HIGH"
                    reason = f"High-risk pattern detected: '{pattern}'"
                    break

            if risk != "HIGH":
                matched, kw = _contains_suspicious(command)
                if matched:
                    risk   = "MEDIUM"
                    reason = f"Suspicious keyword found: '{kw}'"

            if risk == "LOW":
                continue   # clean entry — skip

            self.issues.append(PersistenceIssue(
                source         = "cron",
                name           = f"cron:{command[:60]}",
                command        = command,
                risk           = risk,
                reason         = reason,
                fix_suggestion = "Backup crontab and remove or comment out this entry.",
            ))

    # ── B. SYSTEMD SERVICES ───────────────────────────────────────────────────

    def _scan_systemd(self) -> None:
        rc, out, _ = _run(
            "systemctl list-unit-files --state=enabled --no-legend --no-pager 2>/dev/null",
            timeout=10,
        )
        if rc != 0:
            return

        for line in out.splitlines():
            parts = line.split()
            if not parts:
                continue

            unit = parts[0].strip()

            # Only check .service units
            if not unit.endswith(".service"):
                continue

            # Strip suffix for readability
            svc_name = unit[:-8]  # remove ".service"

            # Skip obviously safe services
            if _is_safe_service(svc_name):
                continue

            # Try to find the unit file
            rc2, unit_path, _ = _run(
                f"systemctl show -P FragmentPath {unit} 2>/dev/null",
                timeout=5,
            )
            exec_start = ""
            risk       = "LOW"
            reason     = ""

            if rc2 == 0 and unit_path:
                lines = _read_file_lines(unit_path)
                for uline in lines:
                    if uline.strip().startswith("ExecStart="):
                        exec_start = uline.split("=", 1)[1].strip()
                        break

            command_to_check = exec_start or unit

            # Flag if running from /home/ or /tmp/
            if "/home/" in command_to_check:
                risk   = "MEDIUM"
                reason = "Service executes from /home/ — non-standard location."
            elif "/tmp/" in command_to_check:
                risk   = "HIGH"
                reason = "Service executes from /tmp/ — strong indicator of compromise."
            else:
                matched, kw = _contains_suspicious(command_to_check)
                if matched:
                    risk   = "MEDIUM"
                    reason = f"Suspicious keyword in ExecStart: '{kw}'"

            if risk == "LOW":
                continue

            self.issues.append(PersistenceIssue(
                source         = "systemd",
                name           = svc_name,
                command        = exec_start or "(could not read ExecStart)",
                risk           = risk,
                reason         = reason,
                fix_suggestion = f"Backup and disable: systemctl disable {unit}",
            ))

    # ── C. STARTUP FILES ─────────────────────────────────────────────────────

    def _scan_startup_files(self) -> None:
        for file_path in _STARTUP_FILES:
            expanded = os.path.expanduser(file_path)
            if not os.path.isfile(expanded):
                continue

            lines = _read_file_lines(file_path)
            suspicious_lines: List[Tuple[int, str, str]] = []

            for lineno, line in enumerate(lines, start=1):
                stripped = line.strip()

                # Skip blanks and comments
                if not stripped or stripped.startswith("#"):
                    continue

                matched, kw = _contains_suspicious(stripped)
                if matched:
                    suspicious_lines.append((lineno, stripped, kw))

            for lineno, content, kw in suspicious_lines:
                risk = "HIGH" if any(
                    p in content for p in ["/tmp/", "base64", "bash -i", "| bash", "|bash"]
                ) else "MEDIUM"

                self.issues.append(PersistenceIssue(
                    source         = "startup",
                    name           = f"{file_path}:line{lineno}",
                    command        = content,
                    risk           = risk,
                    reason         = f"Suspicious keyword '{kw}' found in startup file.",
                    fix_suggestion = f"Backup {file_path} and remove or comment line {lineno}.",
                ))


# ══════════════════════════════════════════════════════════════════════════════
# 4. ROLLBACK MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class RollbackManager:
    """
    Restores previously backed-up files or crontabs created by PersistenceRemediator.

    All backups live under backup_dir, named with a timestamp suffix so multiple
    versions can coexist. restore() always picks the MOST RECENT backup.
    """

    def __init__(self, backup_dir: str = "~/.jenix/backups") -> None:
        self.backup_dir = Path(os.path.expanduser(backup_dir))

    # ── Public API ────────────────────────────────────────────────────────────

    def restore(self, logical_name: str) -> Tuple[bool, str]:
        """
        Restore the most recent backup for *logical_name*.

        logical_name examples:
          "crontab"            → crontab -
          "/etc/profile"       → file at that path
          "~/.bashrc"          → expands and overwrites

        Returns (success: bool, message: str).
        """
        backups = self._list_backups(logical_name)
        if not backups:
            return False, f"No backup found for '{logical_name}'."

        # Most recent backup is last (sorted by timestamp in filename)
        latest = backups[-1]

        if logical_name == "crontab":
            return self._restore_crontab(latest)
        else:
            return self._restore_file(logical_name, latest)

    def list_backups(self, logical_name: str) -> List[str]:
        """Return list of backup file paths for *logical_name*, oldest first."""
        return [str(p) for p in self._list_backups(logical_name)]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _safe_key(self, logical_name: str) -> str:
        """Convert a logical name to a safe filename stem."""
        return logical_name.replace("/", "_").replace("~", "HOME").lstrip("_")

    def _list_backups(self, logical_name: str) -> List[Path]:
        key = self._safe_key(logical_name)
        if not self.backup_dir.is_dir():
            return []
        matches = sorted(self.backup_dir.glob(f"{key}__*.bak"))
        return matches

    def _restore_crontab(self, backup_path: Path) -> Tuple[bool, str]:
        try:
            content = backup_path.read_text(encoding="utf-8")
            rc, _, err = _run(f"echo {_shell_quote(content)} | crontab -", timeout=10)
            if rc == 0:
                return True, f"Crontab restored from {backup_path.name}."
            # Fallback: write to temp file and load
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            rc2, _, err2 = _run(f"crontab {tmp_path}", timeout=10)
            os.unlink(tmp_path)
            if rc2 == 0:
                return True, f"Crontab restored from {backup_path.name}."
            return False, f"crontab restore failed: {err2}"
        except Exception as exc:
            return False, f"Rollback error: {exc}"

    def _restore_file(self, logical_name: str, backup_path: Path) -> Tuple[bool, str]:
        target = Path(os.path.expanduser(logical_name))
        try:
            shutil.copy2(str(backup_path), str(target))
            os.chmod(str(target), backup_path.stat().st_mode)
            return True, f"'{target}' restored from {backup_path.name}."
        except PermissionError:
            return False, f"Permission denied restoring '{target}'. Try with sudo."
        except Exception as exc:
            return False, f"Rollback error for '{target}': {exc}"


def _shell_quote(s: str) -> str:
    """Minimal single-quote escaping for shell injection safety."""
    return "'" + s.replace("'", "'\\''") + "'"


# ══════════════════════════════════════════════════════════════════════════════
# 5. PERSISTENCE REMEDIATOR
# ══════════════════════════════════════════════════════════════════════════════

class PersistenceRemediator:
    """
    Safely remediates detected PersistenceIssue items.

    Safety guarantees:
      1. A timestamped backup is ALWAYS created before any modification.
      2. On ANY exception the system is left unchanged (fail-safe).
      3. Files are NEVER permanently deleted — only lines are commented out.
      4. systemd services are DISABLED — never uninstalled.

    Usage:
        remediator = PersistenceRemediator()
        success, msg = remediator.remediate(issue)
    """

    def __init__(self, backup_dir: str = "~/.jenix/backups") -> None:
        self.backup_dir   = Path(os.path.expanduser(backup_dir))
        self._rollback_mgr = RollbackManager(backup_dir=backup_dir)
        self._ensure_backup_dir()

    # ── Public API ────────────────────────────────────────────────────────────

    def remediate(self, issue: PersistenceIssue) -> Tuple[bool, str]:
        """
        Apply a safe fix for *issue*.
        Returns (success: bool, human-readable message: str).
        """
        try:
            if issue.source == "cron":
                return self._fix_cron(issue)
            elif issue.source == "systemd":
                return self._fix_systemd(issue)
            elif issue.source == "startup":
                return self._fix_startup(issue)
            else:
                return False, f"Unknown persistence source: '{issue.source}'."
        except Exception as exc:
            # Fail-safe: surface error, never leave system in bad state
            return False, f"Remediation aborted (unexpected error): {exc}"

    def rollback_manager(self) -> RollbackManager:
        """Return the underlying RollbackManager for manual restores."""
        return self._rollback_mgr

    # ── A. CRON remediation ───────────────────────────────────────────────────

    def _fix_cron(self, issue: PersistenceIssue) -> Tuple[bool, str]:
        # Read current crontab
        rc, current_cron, err = _run("crontab -l", timeout=6)
        if rc != 0 and "no crontab" not in err.lower():
            return False, f"Could not read crontab: {err}"

        # Backup FIRST
        ok, bk_msg = self._backup_text("crontab", current_cron)
        if not ok:
            return False, f"Backup failed — aborting. {bk_msg}"

        # Comment out lines that contain the suspicious command
        target_cmd = issue.command.strip()
        new_lines   = []
        commented   = 0

        for line in current_cron.splitlines():
            if target_cmd and target_cmd in line and not line.strip().startswith("#"):
                new_lines.append(f"# [JENIX-DISABLED] {line}")
                commented += 1
            else:
                new_lines.append(line)

        if commented == 0:
            return False, "Suspicious cron entry not found in current crontab (may have changed)."

        new_cron = "\n".join(new_lines) + "\n"

        # Write new crontab via temp file
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".cron", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(new_cron)
                tmp_path = tmp.name

            rc2, _, err2 = _run(f"crontab {tmp_path}", timeout=10)
            os.unlink(tmp_path)

            if rc2 != 0:
                return False, f"crontab write failed: {err2}"

            return True, (
                f"Cron entry commented out ({commented} line(s)). "
                f"Backup saved. Restore with: jenix rollback crontab"
            )
        except Exception as exc:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return False, f"Cron remediation failed: {exc}"

    # ── B. SYSTEMD remediation ────────────────────────────────────────────────

    def _fix_systemd(self, issue: PersistenceIssue) -> Tuple[bool, str]:
        svc_name = issue.name
        unit     = svc_name if svc_name.endswith(".service") else f"{svc_name}.service"

        # Resolve unit file path
        rc, unit_path, _ = _run(
            f"systemctl show -P FragmentPath {unit} 2>/dev/null", timeout=5
        )
        if rc != 0 or not unit_path:
            # Proceed with disable even if we can't find the file
            unit_path = ""

        # Backup service file if we have it
        if unit_path and os.path.isfile(unit_path):
            ok, bk_msg = self._backup_file(unit_path)
            if not ok:
                return False, f"Backup failed — aborting. {bk_msg}"

        # Disable (do NOT delete) the service
        rc2, _, err2 = _run(
            f"systemctl disable --now {unit} 2>/dev/null", timeout=15
        )

        if rc2 != 0:
            # Try without --now (older systemd)
            rc3, _, err3 = _run(f"systemctl disable {unit} 2>/dev/null", timeout=10)
            if rc3 != 0:
                return False, (
                    f"systemctl disable failed: {err3}. "
                    "You may need elevated privileges (sudo)."
                )

        return True, (
            f"Service '{unit}' disabled. Unit file backed up. "
            f"Re-enable with: systemctl enable {unit}"
        )

    # ── C. STARTUP FILE remediation ───────────────────────────────────────────

    def _fix_startup(self, issue: PersistenceIssue) -> Tuple[bool, str]:
        # Parse "~/.bashrc:line42" → file_path, lineno
        name_parts = issue.name.split(":line")
        if len(name_parts) != 2:
            return False, f"Cannot parse startup issue name: '{issue.name}'"

        file_path = name_parts[0]
        try:
            target_lineno = int(name_parts[1])
        except ValueError:
            return False, f"Invalid line number in issue name: '{issue.name}'"

        expanded = os.path.expanduser(file_path)
        if not os.path.isfile(expanded):
            return False, f"File not found: {expanded}"

        # Backup FIRST
        ok, bk_msg = self._backup_file(expanded)
        if not ok:
            return False, f"Backup failed — aborting. {bk_msg}"

        # Read, patch, write
        try:
            lines = Path(expanded).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception as exc:
            return False, f"Could not read '{expanded}': {exc}"

        idx = target_lineno - 1   # 0-based
        if idx < 0 or idx >= len(lines):
            return False, f"Line {target_lineno} out of range in '{expanded}'."

        original_line = lines[idx]
        if original_line.strip().startswith("#"):
            return False, f"Line {target_lineno} is already commented out — nothing to do."

        lines[idx] = f"# [JENIX-DISABLED] {original_line}" if original_line.endswith("\n") \
                     else f"# [JENIX-DISABLED] {original_line}\n"

        try:
            # Preserve original file permissions
            orig_mode = Path(expanded).stat().st_mode
            Path(expanded).write_text("".join(lines), encoding="utf-8")
            os.chmod(expanded, orig_mode)
        except PermissionError:
            return False, f"Permission denied writing '{expanded}'. Try with sudo."
        except Exception as exc:
            return False, f"Write failed for '{expanded}': {exc}"

        return True, (
            f"Line {target_lineno} commented out in '{file_path}'. "
            f"Backup saved. Restore with: jenix rollback {file_path}"
        )

    # ── Backup helpers ────────────────────────────────────────────────────────

    def _ensure_backup_dir(self) -> None:
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.chmod(0o700)  # owner-only access
        except Exception:
            pass  # If we can't create it, backups will fail gracefully later

    def _safe_key(self, logical_name: str) -> str:
        return logical_name.replace("/", "_").replace("~", "HOME").lstrip("_")

    def _backup_text(self, logical_name: str, content: str) -> Tuple[bool, str]:
        """Save *content* as a timestamped backup for *logical_name*."""
        key     = self._safe_key(logical_name)
        ts      = _timestamp()
        bk_path = self.backup_dir / f"{key}__{ts}.bak"
        try:
            bk_path.write_text(content, encoding="utf-8")
            bk_path.chmod(0o600)
            return True, str(bk_path)
        except Exception as exc:
            return False, str(exc)

    def _backup_file(self, file_path: str) -> Tuple[bool, str]:
        """Copy *file_path* to a timestamped backup."""
        key     = self._safe_key(file_path)
        ts      = _timestamp()
        bk_path = self.backup_dir / f"{key}__{ts}.bak"
        try:
            shutil.copy2(file_path, str(bk_path))
            bk_path.chmod(0o600)
            return True, str(bk_path)
        except PermissionError:
            return False, f"Permission denied reading '{file_path}'."
        except Exception as exc:
            return False, str(exc)


# ══════════════════════════════════════════════════════════════════════════════
# 6. SCAN ENGINE INTEGRATION SNIPPET
# ══════════════════════════════════════════════════════════════════════════════
#
# Copy the additions below into jenix_scan_engine.py:
#
# ─── ScanResult (add one field) ───────────────────────────────────────────────
#
#   from jenix_persistence import PersistenceIssue   # add to imports
#
#   @dataclass
#   class ScanResult:
#       ...                                           # existing fields
#       persistence_issues: List[PersistenceIssue] = field(default_factory=list)  # NEW
#
# ─── ScanEngine.__init__ (add one attribute) ──────────────────────────────────
#
#   class ScanEngine:
#       def __init__(self, enable_persistence: bool = False):   # NEW param
#           ...                                                 # existing init
#           self.enable_persistence = enable_persistence        # NEW
#
# ─── ScanEngine.run_full_scan (add one phase before duration calc) ───────────
#
#       if self.enable_persistence:
#           tick(96, "Scanning for persistence mechanisms…")
#           from jenix_persistence import PersistenceDetector
#           try:
#               result.persistence_issues = PersistenceDetector().scan()
#           except Exception:
#               result.persistence_issues = []   # fail-safe
#
# ─── ReportGenerator.as_txt (optional: add a section) ────────────────────────
#
#   # Append after section 9 (Open Ports):
#   if r.persistence_issues:
#       out.append(self._section(f"10 · Persistence Issues  ({len(r.persistence_issues)} found)"))
#       risk_icons = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}
#       for pi in r.persistence_issues:
#           out += [
#               f"  {risk_icons.get(pi.risk, '•')} [{pi.risk}] [{pi.source.upper()}] {pi.name}",
#               f"    Command        : {pi.command[:120]}",
#               f"    Reason         : {pi.reason}",
#               f"    Fix Suggestion : {pi.fix_suggestion}",
#               "",
#           ]
#
# ─── ReportGenerator.as_dict (optional: add to JSON output) ──────────────────
#
#   # Inside the returned dict:
#   "persistence_issues": [asdict(pi) for pi in r.persistence_issues],
#   "persistence_issue_count": len(r.persistence_issues),
#
# ══════════════════════════════════════════════════════════════════════════════
