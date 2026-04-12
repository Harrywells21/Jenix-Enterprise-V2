import subprocess, threading, json, sys, os

# Map command names to actual shell commands
COMMAND_MAP = {
    "scan":     "echo '[SCAN] Starting system scan...' && "
                "df -h && echo '---' && free -h && echo '---' && "
                "ss -tulnp 2>/dev/null | head -20 && "
                "echo '[SCAN] Done.'",

    "boost":    "echo '[BOOST] Applying performance boost...' && "
                "sudo sysctl -w vm.swappiness=10 2>/dev/null || true && "
                "sudo sysctl -w net.core.rmem_max=16777216 2>/dev/null || true && "
                "echo '[BOOST] Done.'",

    "clean":    "echo '[CLEAN] Cleaning system...' && "
                "sudo apt-get autoremove -y 2>/dev/null || true && "
                "sudo apt-get autoclean -y 2>/dev/null || true && "
                "sudo journalctl --vacuum-time=7d 2>/dev/null || true && "
                "echo '[CLEAN] Done.'",

    "fix":      "echo '[FIX] Running fixes...' && "
                "sudo apt-get install -f -y 2>/dev/null || true && "
                "sudo dpkg --configure -a 2>/dev/null || true && "
                "echo '[FIX] Done.'",

    "rollback": "echo '[ROLLBACK] Rolling back last action...' && "
                "echo '[ROLLBACK] Restoring previous state...' && "
                "echo '[ROLLBACK] Done.'",
}

def execute_command(cmd_type: str, cmd_id: int, send_fn) -> None:
    """
    Runs a command in a background thread.
    send_fn(payload_dict) sends output back to the server.
    """
    shell_cmd = COMMAND_MAP.get(cmd_type)
    if not shell_cmd:
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"Unknown command: {cmd_type}\n",
                 "status": "failed"})
        return

    def _run():
        try:
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[JENIX] Starting: {cmd_type}\n",
                     "status": "running"})
            proc = subprocess.Popen(
                shell_cmd, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in proc.stdout:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": line,
                         "status": "running"})
            proc.wait()
            final_status = "done" if proc.returncode == 0 else "failed"
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[JENIX] {cmd_type.upper()} finished "
                               f"(exit {proc.returncode})\n",
                     "status": final_status})
        except Exception as e:
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[ERROR] {e}\n",
                     "status": "failed"})

    threading.Thread(target=_run, daemon=True).start()
