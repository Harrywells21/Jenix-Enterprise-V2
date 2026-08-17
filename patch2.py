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

# ---- agent/snapshot.py: add sudo_available() helper + fix restore_snapshot sudo calls ----
snapshot_replacements = [
    (
'''def _dpkg_selections():''',
'''def sudo_available() -> bool:
    """Check passwordless sudo works, without ever prompting for a password."""
    try:
        out = subprocess.run(["sudo", "-n", "true"], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False

def _dpkg_selections():''',
        "add sudo_available helper"
    ),
    (
'''    for key, val in (data.get("sysctl") or {}).items():
        if val is None:
            continue
        try:
            subprocess.run(["sudo", "sysctl", "-w", f"{key}={val}"], capture_output=True, text=True, timeout=5)
            log(f"[ROLLBACK] Restored {key} = {val}\\n")
        except Exception as e:
            log(f"[ROLLBACK] Failed to restore {key}: {e}\\n")''',
'''    if not sudo_available():
        log("[ROLLBACK] Passwordless sudo is not configured on this machine — "
            "cannot restore sysctl/package state. See setup docs for the required sudoers rule.\\n")
        return False

    for key, val in (data.get("sysctl") or {}).items():
        if val is None:
            continue
        try:
            r = subprocess.run(["sudo", "-n", "sysctl", "-w", f"{key}={val}"],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                log(f"[ROLLBACK] Restored {key} = {val}\\n")
            else:
                log(f"[ROLLBACK] Failed to restore {key}: {r.stderr.strip()}\\n")
        except Exception as e:
            log(f"[ROLLBACK] Failed to restore {key}: {e}\\n")''',
        "restore_snapshot sysctl sudo fix"
    ),
    (
'''            try:
                subprocess.run(["sudo", "apt-get", "install", "-y"] + missing,
                                capture_output=True, text=True, timeout=300)
            except Exception as e:
                log(f"[ROLLBACK] Package reinstall failed: {e}\\n")''',
'''            try:
                r = subprocess.run(["sudo", "-n", "apt-get", "install", "-y"] + missing,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    log(f"[ROLLBACK] Package reinstall failed: {r.stderr.strip()}\\n")
            except Exception as e:
                log(f"[ROLLBACK] Package reinstall failed: {e}\\n")''',
        "restore_snapshot apt-get sudo fix"
    ),
]
patch("agent/snapshot.py", snapshot_replacements)

# ---- agent/executor.py: check sudo up front, use sudo -n, detach stdin ----
executor_replacements = [
    (
'''import subprocess, threading
import snapshot as snap''',
'''import subprocess, threading
import snapshot as snap
from snapshot import sudo_available'''
    , "import sudo_available"
    ),
    (
'''    "boost": "echo '[BOOST] Applying performance boost...' && "
             "sudo sysctl -w vm.swappiness=10 2>/dev/null || true && "
             "sudo sysctl -w net.core.rmem_max=16777216 2>/dev/null || true && "
             "echo '[BOOST] Done.'",
    "clean": "echo '[CLEAN] Cleaning system...' && "
             "sudo apt-get autoremove -y 2>/dev/null || true && "
             "sudo apt-get autoclean -y 2>/dev/null || true && "
             "sudo journalctl --vacuum-time=7d 2>/dev/null || true && "
             "echo '[CLEAN] Done.'",
    "fix":   "echo '[FIX] Running fixes...' && "
             "sudo apt-get install -f -y 2>/dev/null || true && "
             "sudo dpkg --configure -a 2>/dev/null || true && "
             "echo '[FIX] Done.'",''',
'''    "boost": "echo '[BOOST] Applying performance boost...' && "
             "sudo -n sysctl -w vm.swappiness=10 && "
             "sudo -n sysctl -w net.core.rmem_max=16777216 && "
             "echo '[BOOST] Done.'",
    "clean": "echo '[CLEAN] Cleaning system...' && "
             "sudo -n apt-get autoremove -y && "
             "sudo -n apt-get autoclean -y && "
             "sudo -n journalctl --vacuum-time=7d && "
             "echo '[CLEAN] Done.'",
    "fix":   "echo '[FIX] Running fixes...' && "
             "sudo -n apt-get install -f -y && "
             "sudo -n dpkg --configure -a && "
             "echo '[FIX] Done.'",''',
        "remove blind || true, use sudo -n"
    ),
    (
'''    shell_cmd = COMMAND_MAP.get(cmd_type)
    if not shell_cmd:
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"Unknown command: {cmd_type}\\n", "status": "failed"})
        return''',
'''    shell_cmd = COMMAND_MAP.get(cmd_type)
    if not shell_cmd:
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"Unknown command: {cmd_type}\\n", "status": "failed"})
        return

    if cmd_type in ("boost", "clean", "fix") and not sudo_available():
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": "[JENIX] Passwordless sudo is not configured on this machine. "
                           "This command requires elevated privileges. See setup docs for the required sudoers rule.\\n",
                 "status": "failed"})
        return''',
        "sudo preflight check"
    ),
    (
'''            proc = subprocess.Popen(shell_cmd, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)''',
'''            proc = subprocess.Popen(shell_cmd, shell=True, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)''',
        "detach Popen stdin"
    ),
]
patch("agent/executor.py", executor_replacements)

print("ALL PATCHES APPLIED")
