import subprocess, threading, shutil, json, os, time, platform
from pathlib import Path
import snapshot as snap
from snapshot import sudo_available
import fleet_auth
import topology_auth
import checkpoint as cp

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

_OS = platform.system()  # "Linux", "Darwin", "Windows"

# Per-OS command table for scan/boost/clean/fix. Every command below is
# real and source-verified (see JENIX Master Context v66), not guessed.
# macOS 'fix' is intentionally verify-only: Apple removed repair_packages
# (the old live-repair tool) in Sierra when System Integrity Protection
# shipped, and no replacement exists on any modern macOS -- the output
# text discloses this honestly instead of implying false parity.
#
# NOTE (as of this patch): macOS boost's jenix-sysctl-restore-macos helper
# is NOT YET provisioned by install_jenix.sh -- that step is pending,
# blocked on confirming for real whether `purge` needs sudo on the target
# macOS version. Until that helper exists on a given machine, boost's
# later two sudo -n calls will just fail harmlessly (nonzero exit,
# reported in output, no crash) and only `purge` will actually run there.
COMMAND_MAP_BY_OS = {
    "Linux": {
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
    },
    "Darwin": {
        "scan":  "echo '[SCAN] Starting system scan...' && "
                 "df -h && echo '---' && vm_stat && echo '---' && "
                 "lsof -iTCP -sTCP:LISTEN -n -P 2>/dev/null | head -20 && echo '[SCAN] Done.'",
        "boost": "echo '[BOOST] Applying performance boost...' && "
                 "sudo -n purge && "
                 "sudo -n /usr/local/sbin/jenix-sysctl-restore-macos kern.ipc.maxsockbuf 8388608 && "
                 "sudo -n /usr/local/sbin/jenix-sysctl-restore-macos net.inet.tcp.sendspace 131072 && "
                 "sudo -n /usr/local/sbin/jenix-sysctl-restore-macos net.inet.tcp.recvspace 131072 && "
                 "echo '[BOOST] Done.'",
        "clean": "echo '[CLEAN] Cleaning system...' && "
                 "sudo -n periodic daily weekly monthly && "
                 "echo '[CLEAN] Done.'",
        "fix":   "echo '[FIX] macOS blocks live repair of protected system files since System "
                 "Integrity Protection (Apple removed repair_packages in Sierra, no replacement exists). "
                 "Running verify-only check instead...' && "
                 "diskutil verifyVolume / && "
                 "echo '[FIX] Verify complete. For a full repair, boot into Recovery Mode and run "
                 "Disk Utility First Aid.'",
    },
    "Windows": {
        "scan":  'powershell -NoProfile -Command "Get-Volume; '
                 'Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize; '
                 'netstat -ano | findstr LISTENING"',
        "boost": 'powershell -NoProfile -Command "powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c; '
                 'netsh interface tcp set global autotuninglevel=normal"',
        "clean": "DISM /Online /Cleanup-Image /StartComponentCleanup",
        "fix":   'powershell -NoProfile -Command "sfc /scannow; DISM /Online /Cleanup-Image /RestoreHealth"',
    },
}

COMMAND_MAP = COMMAND_MAP_BY_OS.get(_OS, {})

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

    if cmd_type == "reassign_server":
        def _run_reassign():
            server_url = (params.get("server_url") or "").strip()
            signature  = params.get("signature")
            if not server_url or not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[REASSIGN] Missing server_url or signature — rejected\n",
                         "status": "failed"})
                return
            payload = json.dumps({"type": "reassign_server", "server_url": server_url},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[REASSIGN] Signature verification failed — this command was not "
                                   "authenticated with the fleet topology key. Rejected, nothing changed.\n",
                         "status": "failed"})
                return
            if not topology_auth.is_trusted_floor(server_url):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[REASSIGN] '{server_url}' is not in this agent's baked-in trusted floor "
                                   f"list. Rejected — rebuild/rebake this agent if the floor list changed.\n",
                         "status": "failed"})
                return
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[REASSIGN] Verified. Repointing this node to {server_url} and restarting...\n",
                     "status": "done"})
            try:
                server_file  = Path.home() / ".jenix" / "server_url"
                token_file   = Path.home() / ".jenix" / "agent.token"
                machine_file = Path.home() / ".jenix" / "agent.machine_id"
                server_file.parent.mkdir(parents=True, exist_ok=True)
                server_file.write_text(server_url)
                token_file.unlink(missing_ok=True)
                machine_file.unlink(missing_ok=True)
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[REASSIGN] Failed writing new config: {e}\n", "status": "failed"})
                return
            time.sleep(1.5)
            os._exit(0)
        threading.Thread(target=_run_reassign, daemon=True).start()
        return

    if cmd_type == "apply_upgrade":
        def _run_upgrade():
            import hashlib, tempfile, sys as _sys, stat, urllib.request

            version      = params.get("version")
            download_url = params.get("download_url")
            sha256       = params.get("sha256")
            signature    = params.get("signature")
            if not all([version, download_url, sha256, signature]):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[UPGRADE] Missing version/download_url/sha256/signature — rejected\n",
                         "status": "failed"})
                return
            payload = json.dumps({"type": "apply_upgrade", "version": version,
                                   "download_url": download_url, "sha256": sha256},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[UPGRADE] Signature verification failed — this command was not "
                                   "authenticated with the fleet topology key. Rejected, nothing downloaded.\n",
                         "status": "failed"})
                return

            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[UPGRADE] Verified. Downloading {version} from {download_url}...\n",
                     "status": "running"})
            try:
                current_bin = Path(_sys.argv[0]).resolve()
                tmp_fd, tmp_path_str = tempfile.mkstemp(dir=str(current_bin.parent), prefix=".jenix_upgrade_")
                tmp_path = Path(tmp_path_str)
                with urllib.request.urlopen(download_url, timeout=60) as resp, open(tmp_fd, "wb") as out:
                    shutil.copyfileobj(resp, out)

                digest = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
                if digest != sha256:
                    tmp_path.unlink(missing_ok=True)
                    send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                             "output": f"[UPGRADE] SHA-256 mismatch (expected {sha256}, got {digest}) — "
                                       f"deleted download, nothing replaced.\n",
                             "status": "failed"})
                    return

                tmp_path.chmod(current_bin.stat().st_mode | stat.S_IEXEC)
                backup_bin = current_bin.with_suffix(current_bin.suffix + ".bak_preupgrade")
                shutil.copy2(current_bin, backup_bin)
                tmp_path.replace(current_bin)

                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[UPGRADE] Verified and installed {version}. Relaunching...\n",
                         "status": "running"})

                env = os.environ.copy()
                subprocess.Popen([str(current_bin)], env=env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[UPGRADE] New process launched on {version}. This process is exiting now.\n",
                         "status": "done"})
                time.sleep(1.0)
                os._exit(0)
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[UPGRADE] Failed: {e}\n", "status": "failed"})
        threading.Thread(target=_run_upgrade, daemon=True).start()
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

    if cmd_type == "checkpoint_start":
        def _run_checkpoint_start():
            paths = params.get("paths") or []
            signature = params.get("signature")
            if not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Missing signature — rejected\n", "status": "failed"})
                return
            payload = json.dumps({"type": "checkpoint_start", "paths": sorted(paths)},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Signature verification failed — this command was not "
                                   "authenticated with the fleet topology key. Rejected, nothing snapshotted.\n",
                         "status": "failed"})
                return
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": "[CHECKPOINT] Verified. Creating checkpoint...\n", "status": "running"})
            try:
                meta = cp.create_checkpoint(extra_paths=paths)
                send_fn({"type": "checkpoint_status", "cmd_id": cmd_id,
                         "checkpoint_id": meta["id"], "status": "armed",
                         "paths": meta["paths"]})
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[CHECKPOINT] Armed. id={meta['id']}, paths: {', '.join(meta['paths'])}\n",
                         "status": "done"})
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[CHECKPOINT] Failed: {e}\n", "status": "failed"})
        threading.Thread(target=_run_checkpoint_start, daemon=True).start()
        return

    if cmd_type == "checkpoint_restore":
        def _run_checkpoint_restore():
            checkpoint_id = params.get("checkpoint_id")
            signature = params.get("signature")
            if not checkpoint_id or not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Missing checkpoint_id or signature — rejected\n", "status": "failed"})
                return
            payload = json.dumps({"type": "checkpoint_restore", "checkpoint_id": checkpoint_id},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Signature verification failed — rejected, nothing restored.\n",
                         "status": "failed"})
                return
            send_fn({"type": "checkpoint_status", "cmd_id": cmd_id,
                     "checkpoint_id": checkpoint_id, "status": "restoring"})
            def _log(msg):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": msg, "status": "running"})
            ok = cp.restore_checkpoint(checkpoint_id, _log)
            send_fn({"type": "checkpoint_status", "cmd_id": cmd_id,
                     "checkpoint_id": checkpoint_id, "status": "none" if ok else "armed"})
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[CHECKPOINT] {'Restore completed' if ok else 'Restore failed'}\n",
                     "status": "done" if ok else "failed"})
        threading.Thread(target=_run_checkpoint_restore, daemon=True).start()
        return

    if cmd_type == "checkpoint_discard":
        def _run_checkpoint_discard():
            checkpoint_id = params.get("checkpoint_id")
            signature = params.get("signature")
            if not checkpoint_id or not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Missing checkpoint_id or signature — rejected\n", "status": "failed"})
                return
            payload = json.dumps({"type": "checkpoint_discard", "checkpoint_id": checkpoint_id},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Signature verification failed — rejected, nothing changed.\n",
                         "status": "failed"})
                return
            def _log(msg):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id, "output": msg, "status": "running"})
            ok = cp.discard_checkpoint(checkpoint_id, _log)
            send_fn({"type": "checkpoint_status", "cmd_id": cmd_id,
                     "checkpoint_id": checkpoint_id, "status": "none" if ok else "armed"})
            send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                     "output": f"[CHECKPOINT] {'Discarded' if ok else 'Discard failed'}\n",
                     "status": "done" if ok else "failed"})
        threading.Thread(target=_run_checkpoint_discard, daemon=True).start()
        return

    if cmd_type == "checkpoint_list":
        def _run_checkpoint_list():
            signature = params.get("signature")
            if not signature:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Missing signature -- rejected\n", "status": "failed"})
                return
            payload = json.dumps({"type": "checkpoint_list"},
                                  sort_keys=True, separators=(",", ":")).encode()
            if not topology_auth.verify_signature(payload, signature):
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": "[CHECKPOINT] Signature verification failed -- this command was not "
                                   "authenticated with the fleet topology key. Rejected.\n",
                         "status": "failed"})
                return
            try:
                items = cp.list_checkpoints()
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": json.dumps(items), "status": "done"})
            except Exception as e:
                send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                         "output": f"[CHECKPOINT] Failed: {e}\n", "status": "failed"})
        threading.Thread(target=_run_checkpoint_list, daemon=True).start()
        return

    shell_cmd = COMMAND_MAP.get(cmd_type)
    if not shell_cmd:
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"Unknown command: {cmd_type}\n", "status": "failed"})
        return

    if _OS == "Linux" and cmd_type in ("clean", "fix") and shutil.which("apt-get") is None:
        detected = _detect_pkg_manager()
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": f"[JENIX] '{cmd_type}' is currently supported on Debian/Ubuntu (apt-based) Linux "
                           f"systems only. Detected on this machine: {detected}. No changes were made to this system.\n",
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
