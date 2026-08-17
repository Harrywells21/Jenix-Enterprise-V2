import sys

def patch(path, replacements):
    with open(path, "r") as f:
        content = f.read()
    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            print(f"FAILED on {path} [{label}]: found {count} occurrences (expected 1)")
            print("---- looking for ----")
            print(old)
            sys.exit(1)
        content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} OK ({len(replacements)} change(s))")

replacements = [
    (
'''import subprocess, threading
import snapshot as snap
from snapshot import sudo_available''',
'''import subprocess, threading, shutil
import snapshot as snap
from snapshot import sudo_available

def _detect_pkg_manager():
    if shutil.which("apt-get"):
        return "apt (Debian/Ubuntu)"
    if shutil.which("dnf"):
        return "dnf (Fedora/RHEL)"
    if shutil.which("yum"):
        return "yum (RHEL/CentOS)"
    if shutil.which("pacman"):
        return "pacman (Arch)"
    if shutil.which("brew"):
        return "brew (macOS)"
    if shutil.which("choco") or shutil.which("winget"):
        return "Windows"
    return "unrecognized"''',
        "add package manager detection"
    ),
    (
'''    if cmd_type in ("boost", "clean", "fix") and not sudo_available():
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": "[JENIX] Passwordless sudo is not configured on this machine. "
                           "This command requires elevated privileges. See setup docs for the required sudoers rule.\\n",
                 "status": "failed"})
        return''',
'''    if cmd_type in ("boost", "clean", "fix") and not sudo_available():
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": "[JENIX] Passwordless sudo is not configured on this machine. "
                           "This command requires elevated privileges. See setup docs for the required sudoers rule.\\n",
                 "status": "failed"})
        return

    if cmd_type in ("clean", "fix") and shutil.which("apt-get") is None:
        detected = _detect_pkg_manager()
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"[JENIX] '{cmd_type}' is currently supported on Debian/Ubuntu (apt-based) systems only. "
                           f"Detected on this machine: {detected}. No changes were made to this system.\\n",
                 "status": "failed"})
        return''',
        "add non-Debian unsupported messaging for clean/fix"
    ),
]
patch("agent/executor.py", replacements)
print("ALL PATCHES APPLIED")
