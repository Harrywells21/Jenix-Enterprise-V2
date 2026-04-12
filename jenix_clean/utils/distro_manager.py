"""
core/distro_manager.py
──────────────────────
Linux distribution detection and package-manager abstraction for JENIX.

Provides:
  - Automatic distro family identification (Debian, Fedora, Arch, SUSE)
  - Per-family command templates for install / remove / update / clean / query
  - Runtime support checks so the rest of the app can gate features cleanly
  - A ``DistroProfile`` dataclass exposing all resolved commands

Supported families:
  ┌────────────┬──────────────────────────────────────────────┐
  │ Family     │ Key Distros                                  │
  ├────────────┼──────────────────────────────────────────────┤
  │ debian     │ Ubuntu, Debian, Mint, Pop!_OS, Kali, Zorin   │
  │ fedora     │ Fedora, RHEL, CentOS, AlmaLinux, Rocky       │
  │ arch       │ Arch, Manjaro, EndeavourOS, Garuda            │
  │ suse       │ openSUSE Leap, Tumbleweed, SLES               │
  │ unknown    │ Anything else — commands degrade gracefully   │
  └────────────┴──────────────────────────────────────────────┘

Usage:
    from core.distro_manager import distro
    print(distro.label)          # "Ubuntu 24.04 [DEBIAN]"
    print(distro.upgrade)        # "sudo apt-get upgrade -y"
    rc, out, _ = run_cmd(distro.update)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# ── Family constants ──────────────────────────────────────────────────────────

DEBIAN  = "debian"
FEDORA  = "fedora"
ARCH    = "arch"
SUSE    = "suse"
UNKNOWN = "unknown"

# ── DistroProfile ─────────────────────────────────────────────────────────────

@dataclass
class DistroProfile:
    """
    Resolved profile for the running distribution.

    All command attributes are ready-to-execute shell strings.
    Attributes that cannot be resolved for the detected family fall back to
    ``"echo 'unsupported'"`` so callers never receive an empty string.

    Attributes:
        name:        Pretty name (e.g. "Ubuntu 24.04 LTS").
        version:     Version string (e.g. "24.04").
        id:          Canonical ID from /etc/os-release (e.g. "ubuntu").
        id_like:     Space-separated family IDs (e.g. "debian").
        family:      Resolved JENIX family constant (debian / fedora / arch / suse / unknown).
        pkg_manager: Name of the package manager binary (e.g. "apt-get", "dnf").
    """

    name:        str = "Unknown"
    version:     str = ""
    id:          str = ""
    id_like:     str = ""
    family:      str = UNKNOWN
    pkg_manager: str = ""

    # ── Resolved command strings (populated by DistroManager) ─────────────

    update:          str = "echo unsupported"
    upgrade:         str = "echo unsupported"
    fix_broken:      str = "echo unsupported"
    autoremove:      str = "echo unsupported"
    clean_cache:     str = "echo unsupported"
    list_upgradable: str = "echo"
    list_orphans:    str = "echo"
    list_installed:  str = "echo"

    @property
    def is_supported(self) -> bool:
        """True when the distro family is recognised."""
        return self.family != UNKNOWN

    @property
    def label(self) -> str:
        """Short human-readable label for UI display."""
        return f"{self.name} [{self.family.upper()}]"


# ── Command templates ─────────────────────────────────────────────────────────

# Each entry: family → command string
_UPDATE: Dict[str, str] = {
    DEBIAN:  "sudo apt-get update -qq",
    FEDORA:  "sudo dnf check-update -q",
    ARCH:    "sudo pacman -Sy --noconfirm",
    SUSE:    "sudo zypper refresh -q",
}

_UPGRADE: Dict[str, str] = {
    DEBIAN:  "sudo apt-get upgrade -y",
    FEDORA:  "sudo dnf upgrade -y",
    ARCH:    "sudo pacman -Su --noconfirm",
    SUSE:    "sudo zypper update -y",
}

_FIX_BROKEN: Dict[str, str] = {
    DEBIAN:  "sudo apt-get --fix-broken install -y",
    FEDORA:  "sudo dnf distro-sync -y",
    ARCH:    "sudo pacman -Syuu --noconfirm",
    SUSE:    "sudo zypper verify -y",
}

_AUTOREMOVE: Dict[str, str] = {
    DEBIAN:  "sudo apt-get autoremove --purge -y",
    FEDORA:  "sudo dnf autoremove -y",
    ARCH:    "sudo pacman -Rns $(pacman -Qdtq) --noconfirm 2>/dev/null || true",
    SUSE:    (
        "sudo zypper packages --unneeded "
        "| awk 'NR>4{print $5}' "
        "| xargs sudo zypper remove -y 2>/dev/null || true"
    ),
}

_CLEAN_CACHE: Dict[str, str] = {
    DEBIAN:  "sudo apt-get clean && sudo apt-get autoclean",
    FEDORA:  "sudo dnf clean all",
    ARCH:    "sudo pacman -Sc --noconfirm",
    SUSE:    "sudo zypper clean --all",
}

_LIST_UPGRADABLE: Dict[str, str] = {
    DEBIAN:  "apt list --upgradable 2>/dev/null",
    FEDORA:  "dnf check-update -q 2>/dev/null",
    ARCH:    "pacman -Qu 2>/dev/null",
    SUSE:    "zypper list-updates 2>/dev/null",
}

_LIST_ORPHANS: Dict[str, str] = {
    DEBIAN:  "deborphan 2>/dev/null",
    FEDORA:  "package-cleanup --leaves 2>/dev/null",
    ARCH:    "pacman -Qdt 2>/dev/null",
    SUSE:    "zypper packages --unneeded 2>/dev/null",
}

_LIST_INSTALLED: Dict[str, str] = {
    DEBIAN:  "dpkg --get-selections | grep -v deinstall | awk '{print $1}'",
    FEDORA:  "rpm -qa --queryformat '%{NAME}\\n'",
    ARCH:    "pacman -Qq",
    SUSE:    "rpm -qa --queryformat '%{NAME}\\n'",
}

_PKG_MANAGER: Dict[str, str] = {
    DEBIAN:  "apt-get",
    FEDORA:  "dnf",
    ARCH:    "pacman",
    SUSE:    "zypper",
}

# ── DistroManager ─────────────────────────────────────────────────────────────

class DistroManager:
    """
    Detects the running Linux distribution and exposes a resolved
    ``DistroProfile`` with all package-manager commands pre-filled.

    Singleton pattern — import and use ``distro`` from this module.

    Detection strategy:
      1. Try the ``distro`` PyPI package (most accurate).
      2. Parse ``/etc/os-release`` directly as a fallback.
      3. Check for known package manager binaries as a last resort.
    """

    def __init__(self) -> None:
        self._profile: Optional[DistroProfile] = None
        self._detect()

    # ── Detection ─────────────────────────────────────────────────────────

    def _detect(self) -> None:
        """
        Run the full detection pipeline and populate ``self._profile``.

        Sets family, resolves all command templates, and stores the result
        in ``self._profile``.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    def _parse_os_release(self) -> Dict[str, str]:
        """
        Parse /etc/os-release (or /usr/lib/os-release) into a key→value dict.

        Returns:
            Dict of unquoted key/value pairs, e.g.
            {"ID": "ubuntu", "VERSION_ID": "24.04", "NAME": "Ubuntu", ...}
            Returns empty dict on any read error.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    def _resolve_family(self, id_str: str, id_like_str: str) -> str:
        """
        Map distro ID strings to a JENIX family constant.

        Args:
            id_str:      Value of the ID field from os-release.
            id_like_str: Value of the ID_LIKE field from os-release (space-sep).

        Returns:
            One of: "debian", "fedora", "arch", "suse", "unknown".
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    def _build_profile(self, os_release: Dict[str, str], family: str) -> DistroProfile:
        """
        Construct a fully-resolved DistroProfile from raw os-release data.

        Args:
            os_release: Parsed os-release dict.
            family:     Resolved family constant.

        Returns:
            Populated DistroProfile instance.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    # ── Per-package helpers ────────────────────────────────────────────────

    def install_cmd(self, package: str) -> str:
        """
        Return the command to install *package* for the current distro.

        Args:
            package: Package name (e.g. "htop", "fail2ban").

        Returns:
            Ready-to-execute shell string.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    def remove_cmd(self, package: str) -> str:
        """
        Return the command to remove *package* for the current distro.

        Args:
            package: Package name.

        Returns:
            Ready-to-execute shell string.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    def is_installed(self, package: str) -> bool:
        """
        Check whether *package* is currently installed.

        Args:
            package: Package name.

        Returns:
            True if the package is installed, False otherwise.
        """
        raise NotImplementedError("Placeholder — implement in Phase 2")

    # ── Public profile access ─────────────────────────────────────────────

    @property
    def profile(self) -> DistroProfile:
        """The resolved DistroProfile (lazy-constructed on first access)."""
        if self._profile is None:
            self._detect()
        return self._profile  # type: ignore[return-value]

    # Convenience pass-throughs so callers can write ``distro.upgrade`` directly
    # instead of ``distro.profile.upgrade``.

    def __getattr__(self, name: str):
        """Proxy attribute access to the underlying DistroProfile."""
        profile = object.__getattribute__(self, "_profile")
        if profile is not None and hasattr(profile, name):
            return getattr(profile, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DistroManager profile={self._profile!r}>"


# ── Public singleton ──────────────────────────────────────────────────────────

distro = DistroManager()
