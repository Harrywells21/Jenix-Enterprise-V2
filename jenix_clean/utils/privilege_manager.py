"""
utils/privilege_manager.py
──────────────────────────
Privilege detection and sudo management for JENIX.

Provides:
  - Runtime privilege level detection (root / sudo / unprivileged)
  - Sudo credential caching and validation
  - Safe command wrapping with appropriate privilege escalation
  - Polkit integration stub for GUI sudo prompts

Design goals:
  - JENIX never stores raw passwords.
  - All privilege escalation goes through this module so it can be
    audited and replaced (e.g. swap sudo for polkit) without touching
    the rest of the codebase.

Usage:
    from utils.privilege_manager import priv
    if priv.has_sudo:
        cmd = priv.wrap("apt-get update")
"""

import os
import shutil
import subprocess
from enum import Enum, auto
from typing import Optional

# ── Privilege level enum ──────────────────────────────────────────────────────

class PrivLevel(Enum):
    """Represents the effective privilege level of the running process."""

    ROOT         = auto()   # Running as UID 0
    SUDO_CACHED  = auto()   # sudo credentials are currently cached
    SUDO_ABLE    = auto()   # User is in sudoers but credentials not cached
    UNPRIVILEGED = auto()   # No sudo access detected


# ── PrivilegeManager ─────────────────────────────────────────────────────────

class PrivilegeManager:
    """
    Central authority for privilege checks and sudo command wrapping.

    Attributes:
        level (PrivLevel): Detected privilege level at construction time.

    Thread-safety:
        ``check()`` spawns no background threads and is safe to call from
        any thread.  ``wrap()`` is pure string manipulation — also thread-safe.
    """

    def __init__(self) -> None:
        self._level: Optional[PrivLevel] = None
        self._sudo_path: Optional[str] = shutil.which("sudo")
        self._pkexec_path: Optional[str] = shutil.which("pkexec")
        self._detect()

    # ── Detection ─────────────────────────────────────────────────────────

    def _detect(self) -> None:
        """
        Detect the current privilege level and populate ``self._level``.

        Detection order:
          1. UID == 0  →  ROOT
          2. sudo -n true succeeds  →  SUDO_CACHED
          3. sudo -l succeeds       →  SUDO_ABLE
          4. Otherwise              →  UNPRIVILEGED
        """
        if os.geteuid() == 0:
            self._level = PrivLevel.ROOT
            return

        if self._sudo_path:
            # Check if credentials are already cached (non-interactive)
            cached = subprocess.run(
                ["sudo", "-n", "true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if cached.returncode == 0:
                self._level = PrivLevel.SUDO_CACHED
                return

            # Check if user is in sudoers at all
            able = subprocess.run(
                ["sudo", "-l"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if able.returncode == 0:
                self._level = PrivLevel.SUDO_ABLE
                return

        self._level = PrivLevel.UNPRIVILEGED

    def refresh(self) -> PrivLevel:
        """
        Re-run detection and update ``self._level``.

        Call this after a user authenticates via a GUI sudo dialog so that
        the rest of the app sees the updated state.

        Returns:
            The refreshed PrivLevel.
        """
        self._detect()
        return self._level  # type: ignore[return-value]

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def level(self) -> PrivLevel:
        """Current privilege level (cached from last detection)."""
        return self._level  # type: ignore[return-value]

    @property
    def is_root(self) -> bool:
        """True when the process is running as UID 0."""
        return self._level is PrivLevel.ROOT

    @property
    def has_sudo(self) -> bool:
        """True when sudo is available and credentials are usable."""
        return self._level in (PrivLevel.ROOT, PrivLevel.SUDO_CACHED)

    @property
    def can_escalate(self) -> bool:
        """True when any form of privilege escalation is available."""
        return self._level in (
            PrivLevel.ROOT,
            PrivLevel.SUDO_CACHED,
            PrivLevel.SUDO_ABLE,
        )

    @property
    def escalator(self) -> str:
        """
        Return the preferred escalation prefix ("sudo", "pkexec", or "").

        Preference order: sudo > pkexec > none.
        """
        if self._sudo_path:
            return "sudo"
        if self._pkexec_path:
            return "pkexec"
        return ""

    # ── Command wrapping ──────────────────────────────────────────────────

    def wrap(self, cmd: str, force_sudo: bool = False) -> str:
        """
        Prepend the appropriate privilege prefix to *cmd* if required.

        If already root, *cmd* is returned unchanged.
        If sudo credentials are cached (or force_sudo is True), prepend "sudo ".
        If no escalation is possible, return *cmd* unchanged and log a warning.

        Args:
            cmd:        Raw shell command string (may already start with "sudo").
            force_sudo: If True, always prepend sudo even if credentials are
                        not currently cached.

        Returns:
            Command string, possibly prefixed with "sudo " or "pkexec ".
        """
        # Never double-wrap
        clean = self.strip_sudo(cmd)

        if self.is_root:
            return clean

        if self.has_sudo or force_sudo:
            return f"sudo {clean}"

        if self._pkexec_path:
            return f"pkexec {clean}"

        # No escalation available — return unwrapped (caller handles failure)
        return clean

    def strip_sudo(self, cmd: str) -> str:
        """
        Remove any leading "sudo " or "pkexec " prefix from *cmd*.

        Useful when the caller wants to decide separately whether to escalate.

        Args:
            cmd: Shell command string.

        Returns:
            Command string with privilege prefix removed.
        """
        for prefix in ("sudo ", "pkexec "):
            if cmd.startswith(prefix):
                return cmd[len(prefix):]
        return cmd

    # ── Sudo credential management ────────────────────────────────────────

    def request_credentials(self, reason: str = "") -> bool:
        """
        Interactively request sudo credentials (terminal prompt).

        This triggers a blocking ``sudo -v`` call which will prompt the user
        in the terminal that launched JENIX.  GUI-based prompting via polkit
        is handled separately in ``request_credentials_gui()``.

        Args:
            reason: Human-readable description shown to the user explaining
                    why elevated privileges are needed.

        Returns:
            True if credentials were accepted, False otherwise.
        """
        if reason:
            print(f"[JENIX] Elevated privileges required: {reason}")

        result = subprocess.run(["sudo", "-v"])
        if result.returncode == 0:
            self._level = PrivLevel.SUDO_CACHED
            return True
        return False

    def request_credentials_gui(self, reason: str = "") -> bool:
        """
        Request sudo credentials through a polkit / pkexec GUI dialog.

        Falls back to terminal prompt if polkit is unavailable.

        Args:
            reason: Human-readable explanation shown in the dialog.

        Returns:
            True if elevated access was granted, False otherwise.
        """
        if self._pkexec_path:
            # pkexec a harmless no-op to trigger the polkit dialog
            result = subprocess.run(
                ["pkexec", "true"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                self._level = PrivLevel.SUDO_CACHED
                return True
            return False

        # Polkit not available — fall back to terminal prompt
        return self.request_credentials(reason=reason)

    def invalidate_credentials(self) -> None:
        """
        Explicitly revoke cached sudo credentials (runs ``sudo -k``).

        Called on application exit and when the user logs out of a session.
        """
        if self._sudo_path:
            subprocess.run(
                ["sudo", "-k"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        if self._level is PrivLevel.SUDO_CACHED:
            self._level = PrivLevel.SUDO_ABLE

    # ── Validation helpers ────────────────────────────────────────────────

    def validate_cmd(self, cmd: str) -> bool:
        """
        Basic sanity-check a command string before execution.

        Rejects commands that:
          - Are empty or whitespace-only
          - Contain shell injection patterns (``; &&`` chaining without quoting)
          - Reference obviously dangerous paths (e.g. "rm -rf /")

        Args:
            cmd: Shell command string to validate.

        Returns:
            True if the command looks safe to pass to run_cmd().
        """
        if not cmd or not cmd.strip():
            return False

        # Reject dangerous rm patterns
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf /*",
            "rm -fr /",
            "mkfs",
            "> /dev/sda",
            "dd if=/dev/zero of=/dev/",
        ]
        for pattern in dangerous_patterns:
            if pattern in cmd:
                return False

        # Reject unquoted shell injection characters
        injection_tokens = [";", "&&", "||", "`", "$("]
        for token in injection_tokens:
            if token in cmd:
                return False

        return True

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PrivilegeManager level={self._level}>"


# ── Public singleton ──────────────────────────────────────────────────────────

priv = PrivilegeManager()
