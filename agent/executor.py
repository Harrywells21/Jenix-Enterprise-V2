import subprocess, threading, shutil, json
import snapshot as snap
from snapshot import sudo_available
import fleet_auth

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
    return "unrecognized"

COMMAND_MAP = {
    "scan":  "echo '[SCAN] Starting system scan...' && "
             "df -h && echo '---' && free -h && echo '---' && "
             "ss -tulnp 2>/dev/null | head -20 && echo '[SCAN] Done.'",
    "boost": "echo '[BOOST] Applying performance boost...' && "
             "sudo -n /usr/local/sbin/jenix-sysctl-restore vm.swappiness 10 && "
             "sudo -n /usr/local/sbin/jenix-sysctl-restore net.core.rmem_max 16777216 && "
             "echo '[BOOST] Done.'",
    "clean": "echo '[CLEAN] Cleaning system...' && "
             "sudo -n apt-get autoremove -y && "
             "sudo -n apt-get autoclean -y && "
             "sudo -n journalctl --vacuum-time=7d && "
             "echo '[CLEAN] Done.'",
    "fix":   "echo '[FIX] Running fixes...' && "
             "sudo -n apt-get install -f -y && "
             "sudo -n dpkg --configure -a && "
             "echo '[FIX] Done.'",
}

SNAPSHOT_BEFORE = {"boost", "clean", "fix"}

def execute_command(cmd_type: str, cmd_id: int, send_fn, params: dict | None = None) -> None:
    params = params or {}

    if cmd_type == "exec":
        def _run_exec():
            script    = params.get("script")
            signature = params.get("signature")
            if not script or not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[EXEC] Missing script or signature — rejected\n",
                         "status": "failed"})
                return
            payload = json.dumps({"type": "exec", "script": script},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not fleet_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[EXEC] Signature verification failed — this command was not "
                                   "authenticated with the fleet master key. Rejected, nothing executed.\n",
                         "status": "failed"})
                return
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": "[EXEC] Signature verified. Running script as unprivileged agent user (no sudo).\n",
                     "status": "running"})
            try:
                proc = subprocess.Popen(script, shell=True, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": line, "status": "running"})
                proc.wait()
                final_status = "done" if proc.returncode == 0 else "failed"
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[EXEC] Finished (exit {proc.returncode})\n", "status": final_status})
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": f"[ERROR] {e}\n", "status": "failed"})
        threading.Thread(target=_run_exec, daemon=True).start()
        return

    if cmd_type == "rollback":
        def _run_rollback():
            snap_id = params.get("snapshot_id") or snap.latest_snapshot_id()
            if not snap_id:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[ROLLBACK] No restore point found on this machine\n",
                         "status": "failed"})
                return
            def _log(msg):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": msg, "status": "running"})
            ok = snap.restore_snapshot(snap_id, _log)
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[ROLLBACK] {'Completed' if ok else 'Failed'}\n",
                     "status": "done" if ok else "failed"})
        threading.Thread(target=_run_rollback, daemon=True).start()
        return

    shell_cmd = COMMAND_MAP.get(cmd_type)
    if not shell_cmd:
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"Unknown command: {cmd_type}\n", "status": "failed"})
        return

    if cmd_type in ("clean", "fix") and shutil.which("apt-get") is None:
        detected = _detect_pkg_manager()
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"[JENIX] '{cmd_type}' is currently supported on Debian/Ubuntu (apt-based) systems only. "
                           f"Detected on this machine: {detected}. No changes were made to this system.\n",
                 "status": "failed"})
        return

    def _run():
        try:
            if cmd_type in SNAPSHOT_BEFORE:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[JENIX] Creating restore point before {cmd_type}...\n", "status": "running"})
                s = snap.create_snapshot(reason=f"before {cmd_type} (cmd #{cmd_id})")
                send_fn({"type": "snapshot", "snapshot_id": s["id"], "reason": s["reason"], "cmd_id": cmd_id})
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[JENIX] Restore point {s['id']} created\n", "status": "running"})

            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[JENIX] Starting: {cmd_type}\n", "status": "running"})
            proc = subprocess.Popen(shell_cmd, shell=True, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": line, "status": "running"})
            proc.wait()
            final_status = "done" if proc.returncode == 0 else "failed"
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[JENIX] {cmd_type.upper()} finished (exit {proc.returncode})\n",
                     "status": final_status})
        except Exception as e:
            send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": f"[ERROR] {e}\n", "status": "failed"})

    threading.Thread(target=_run, daemon=True).start()
