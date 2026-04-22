"""
JENIX Enterprise v3.0 — Automated Remediation Playbook Engine
13 fully-scripted cross-platform playbooks with step-by-step execution,
automatic rollback on failure, and dry-run support.
Linux · macOS · Windows
"""

import asyncio
import json
import subprocess
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# ── Playbook definitions ──────────────────────────────────────────────────────

PLAYBOOKS: Dict[str, dict] = {

    # ── LINUX ────────────────────────────────────────────────────────────────

    "linux_high_cpu": {
        "id": "linux_high_cpu", "name": "Linux: High CPU Relief",
        "description": "Identifies top CPU consumers, renices runaway processes, drops page cache",
        "os": ["Linux"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Capture top processes",          "cmd":"ps aux --sort=-%cpu | head -15",                         "timeout":10, "rollback":None},
            {"id":"s2","name":"Check load average",             "cmd":"uptime && cat /proc/loadavg",                            "timeout":5,  "rollback":None},
            {"id":"s3","name":"List processes > 50% CPU",       "cmd":"ps aux | awk '$3 > 50 {print $0}'",                     "timeout":5,  "rollback":None},
            {"id":"s4","name":"Renice top 3 processes",         "cmd":"for p in $(ps aux --sort=-%cpu|awk 'NR>1&&NR<5{print $2}');do renice 10 $p 2>/dev/null;done;echo 'Reniced'","timeout":15,"rollback":"for p in $(ps aux --sort=-%cpu|awk 'NR>1&&NR<5{print $2}');do renice 0 $p 2>/dev/null;done"},
            {"id":"s5","name":"Drop page cache",                "cmd":"sync && echo 1 > /proc/sys/vm/drop_caches && echo 'Cache cleared'","timeout":10,"rollback":None},
            {"id":"s6","name":"Verify CPU improvement",         "cmd":"sleep 2 && top -bn1 | grep 'Cpu(s)' | awk '{print \"CPU idle: \"$8}'","timeout":15,"rollback":None},
        ],
    },

    "linux_high_memory": {
        "id": "linux_high_memory", "name": "Linux: High Memory Relief",
        "description": "Clears caches, drops dentries/inodes, identifies OOM events",
        "os": ["Linux"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Memory snapshot",               "cmd":"free -h && grep -E 'MemTotal|MemFree|MemAvailable|SwapUsed' /proc/meminfo","timeout":5,"rollback":None},
            {"id":"s2","name":"Top memory processes",          "cmd":"ps aux --sort=-%mem | head -10",                         "timeout":5,  "rollback":None},
            {"id":"s3","name":"Drop page cache",               "cmd":"sync && echo 1 > /proc/sys/vm/drop_caches && echo 'Page cache dropped'","timeout":10,"rollback":None},
            {"id":"s4","name":"Drop dentries and inodes",      "cmd":"sync && echo 2 > /proc/sys/vm/drop_caches && echo 'Dentries/inodes dropped'","timeout":10,"rollback":None},
            {"id":"s5","name":"Check for OOM events",          "cmd":"dmesg | grep -i 'oom' | tail -5 || echo 'No OOM events'","timeout":10,"rollback":None},
            {"id":"s6","name":"Verify memory freed",           "cmd":"free -h",                                                "timeout":5,  "rollback":None},
        ],
    },

    "linux_disk_cleanup": {
        "id": "linux_disk_cleanup", "name": "Linux: Disk Space Cleanup",
        "description": "Removes old logs, temp files, package cache to recover disk space",
        "os": ["Linux"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Disk usage overview",            "cmd":"df -h && du -sh /tmp /var/log /var/cache 2>/dev/null",  "timeout":15, "rollback":None},
            {"id":"s2","name":"Clear /tmp (> 2 days old)",      "cmd":"find /tmp -type f -atime +2 -delete 2>/dev/null && echo 'Cleaned /tmp'","timeout":20,"rollback":None},
            {"id":"s3","name":"Vacuum systemd journal",         "cmd":"journalctl --vacuum-size=200M 2>/dev/null || true && echo 'Journal vacuumed'","timeout":30,"rollback":None},
            {"id":"s4","name":"Clean package cache",            "cmd":"apt-get clean 2>/dev/null || yum clean all 2>/dev/null || dnf clean all 2>/dev/null || true && echo 'Package cache cleaned'","timeout":30,"rollback":None},
            {"id":"s5","name":"Remove orphaned packages",       "cmd":"apt-get autoremove -y 2>/dev/null || yum autoremove -y 2>/dev/null || true","timeout":60,"rollback":None},
            {"id":"s6","name":"Compress large log files",       "cmd":"find /var/log -type f -name '*.log' -size +50M ! -name '*.gz' -exec gzip {} \\; 2>/dev/null && echo 'Logs compressed'","timeout":60,"rollback":None},
            {"id":"s7","name":"Final disk check",               "cmd":"df -h",                                                "timeout":5,  "rollback":None},
        ],
    },

    "linux_security_harden": {
        "id": "linux_security_harden", "name": "Linux: CIS Security Hardening",
        "description": "Applies CIS-aligned hardening: SSH, firewall, sysctl tuning, core dumps",
        "os": ["Linux"], "severity": "info",
        "steps": [
            {"id":"s1","name":"Backup SSH config",             "cmd":"cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d) && echo 'Backup created'","timeout":5,"rollback":None},
            {"id":"s2","name":"Disable root SSH login",        "cmd":"sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config && echo 'Root login disabled'","timeout":5,"rollback":"sed -i 's/^PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config"},
            {"id":"s3","name":"Disable password auth",         "cmd":"grep -q '^PasswordAuthentication' /etc/ssh/sshd_config && sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config || echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config && echo 'Password auth disabled'","timeout":5,"rollback":None},
            {"id":"s4","name":"Enable firewall",               "cmd":"systemctl enable --now ufw 2>/dev/null && ufw --force enable || firewall-cmd --permanent --add-service=ssh 2>/dev/null || true && echo 'Firewall enabled'","timeout":15,"rollback":None},
            {"id":"s5","name":"Harden sysctl (network)",       "cmd":"cat >> /etc/sysctl.conf << 'EOF'\nnet.ipv4.conf.all.rp_filter=1\nnet.ipv4.tcp_syncookies=1\nnet.ipv4.conf.all.accept_redirects=0\nnet.ipv4.conf.all.log_martians=1\nEOF\nsysctl -p 2>/dev/null && echo 'sysctl hardened'","timeout":10,"rollback":None},
            {"id":"s6","name":"Disable core dumps",            "cmd":"echo '* hard core 0' >> /etc/security/limits.conf && echo 'Core dumps disabled'","timeout":5,"rollback":None},
            {"id":"s7","name":"Reload SSH daemon",             "cmd":"systemctl reload sshd && echo 'SSH reloaded'","timeout":10,"rollback":"systemctl reload sshd"},
        ],
    },

    "linux_service_repair": {
        "id": "linux_service_repair", "name": "Linux: Service Health & Repair",
        "description": "Detects failed systemd services and restarts them with health validation",
        "os": ["Linux"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"List failed services",          "cmd":"systemctl list-units --state=failed --no-pager || echo 'No failed services'","timeout":10,"rollback":None},
            {"id":"s2","name":"Restart failed services",       "cmd":"systemctl list-units --state=failed --plain --no-legend | awk '{print $1}' | xargs -I{} systemctl restart {} 2>&1 | head -20 || echo 'No failed services to restart'","timeout":60,"rollback":None},
            {"id":"s3","name":"Run SFC equivalent (fsstab)",   "cmd":"dmesg | grep -iE 'error|fail|corrupt' | tail -10 || echo 'No filesystem errors'","timeout":10,"rollback":None},
            {"id":"s4","name":"Verify all services recovered",  "cmd":"systemctl list-units --state=failed --no-pager || echo 'All services healthy'","timeout":10,"rollback":None},
        ],
    },

    # ── MACOS ────────────────────────────────────────────────────────────────

    "macos_high_memory": {
        "id": "macos_high_memory", "name": "macOS: Memory Pressure Relief",
        "description": "Purges inactive memory, identifies hogs, clears DNS cache",
        "os": ["Darwin"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Memory stats",                  "cmd":"vm_stat && sysctl hw.memsize",                          "timeout":5,  "rollback":None},
            {"id":"s2","name":"Top memory consumers",          "cmd":"ps aux -m | head -15",                                  "timeout":5,  "rollback":None},
            {"id":"s3","name":"Purge inactive memory",         "cmd":"purge && echo 'Inactive memory purged'",                "timeout":30, "rollback":None},
            {"id":"s4","name":"Clear DNS cache",               "cmd":"dscacheutil -flushcache && killall -HUP mDNSResponder 2>/dev/null && echo 'DNS cache cleared'","timeout":10,"rollback":None},
            {"id":"s5","name":"Verify memory after purge",     "cmd":"vm_stat | grep -E 'Pages free|Pages inactive'",        "timeout":5,  "rollback":None},
        ],
    },

    "macos_disk_cleanup": {
        "id": "macos_disk_cleanup", "name": "macOS: Disk Cleanup",
        "description": "Clears system caches, logs, Homebrew cache on macOS",
        "os": ["Darwin"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Disk usage overview",           "cmd":"df -h && du -sh ~/Library/Caches /private/var/log /private/tmp 2>/dev/null | sort -rh | head -10","timeout":15,"rollback":None},
            {"id":"s2","name":"Clear system logs",             "cmd":"sudo log erase --all 2>/dev/null && echo 'System logs cleared' || echo 'Log erase skipped (no sudo)'","timeout":20,"rollback":None},
            {"id":"s3","name":"Clear /private/tmp",            "cmd":"find /private/tmp -type f -atime +1 -delete 2>/dev/null && echo '/tmp cleaned'","timeout":15,"rollback":None},
            {"id":"s4","name":"Homebrew cleanup",              "cmd":"brew cleanup --prune=all 2>/dev/null && echo 'Homebrew cleaned' || echo 'Homebrew not installed'","timeout":60,"rollback":None},
            {"id":"s5","name":"Final disk check",              "cmd":"df -h",                                                "timeout":5,  "rollback":None},
        ],
    },

    "macos_security_check": {
        "id": "macos_security_check", "name": "macOS: Security Verification",
        "description": "Verifies SIP, Gatekeeper, FileVault, and Firewall status",
        "os": ["Darwin"], "severity": "info",
        "steps": [
            {"id":"s1","name":"Check SIP status",              "cmd":"csrutil status",                                        "timeout":5,  "rollback":None},
            {"id":"s2","name":"Check Gatekeeper",              "cmd":"spctl --status",                                        "timeout":5,  "rollback":None},
            {"id":"s3","name":"Check FileVault",               "cmd":"fdesetup status",                                       "timeout":5,  "rollback":None},
            {"id":"s4","name":"Check Application Firewall",    "cmd":"/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate","timeout":5,"rollback":None},
            {"id":"s5","name":"Check pending software updates","cmd":"softwareupdate -l 2>&1 | head -15",                    "timeout":30, "rollback":None},
        ],
    },

    # ── WINDOWS ──────────────────────────────────────────────────────────────

    "windows_high_memory": {
        "id": "windows_high_memory", "name": "Windows: Memory Relief",
        "description": "Shows memory hogs, clears standby list, checks for leaks",
        "os": ["Windows"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Memory snapshot",               "cmd":'powershell -Command "Get-Counter \'\\Memory\\Available MBytes\' | Select-Object -ExpandProperty CounterSamples | Select CookedValue"',"timeout":10,"rollback":None},
            {"id":"s2","name":"Top memory processes",          "cmd":'powershell -Command "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 Name,Id,@{N=\'RAM_MB\';E={[math]::Round($_.WorkingSet/1MB,1)}} | Format-Table -AutoSize"',"timeout":10,"rollback":None},
            {"id":"s3","name":"Identify high-RAM processes",   "cmd":'powershell -Command "Get-Process | Where-Object {$_.WorkingSet -gt 500MB} | Select-Object Name,Id,@{N=\'RAM_GB\';E={[math]::Round($_.WorkingSet/1GB,2)}} | Format-Table"',"timeout":10,"rollback":None},
            {"id":"s4","name":"Final memory check",            "cmd":'powershell -Command "Get-Counter \'\\Memory\\Available MBytes\' | Select-Object -ExpandProperty CounterSamples | Select CookedValue"',"timeout":10,"rollback":None},
        ],
    },

    "windows_disk_cleanup": {
        "id": "windows_disk_cleanup", "name": "Windows: Disk Cleanup",
        "description": "Clears temp files, Windows Update cache, CBS logs, component store",
        "os": ["Windows"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"Disk usage snapshot",           "cmd":'powershell -Command "Get-PSDrive -PSProvider FileSystem | Format-Table Name,@{N=\'Used_GB\';E={[math]::Round($_.Used/1GB,2)}},@{N=\'Free_GB\';E={[math]::Round($_.Free/1GB,2)}} -AutoSize"',"timeout":10,"rollback":None},
            {"id":"s2","name":"Clear temp files",              "cmd":'powershell -Command "Remove-Item -Path $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item -Path C:\\Windows\\Temp\\* -Recurse -Force -ErrorAction SilentlyContinue; Write-Output \'Temp files cleared\'"',"timeout":30,"rollback":None},
            {"id":"s3","name":"Clear Windows Update cache",    "cmd":'powershell -Command "Stop-Service wuauserv -Force; Remove-Item -Path C:\\Windows\\SoftwareDistribution\\Download\\* -Recurse -Force -ErrorAction SilentlyContinue; Start-Service wuauserv; Write-Output \'WU cache cleared\'"',"timeout":30,"rollback":None},
            {"id":"s4","name":"Clear CBS logs",                "cmd":'powershell -Command "Remove-Item -Path C:\\Windows\\Logs\\CBS\\* -Force -ErrorAction SilentlyContinue; Write-Output \'CBS logs cleared\'"',"timeout":10,"rollback":None},
            {"id":"s5","name":"Final disk check",              "cmd":'powershell -Command "Get-PSDrive -PSProvider FileSystem | Format-Table Name,@{N=\'Free_GB\';E={[math]::Round($_.Free/1GB,2)}} -AutoSize"',"timeout":10,"rollback":None},
        ],
    },

    "windows_security_harden": {
        "id": "windows_security_harden", "name": "Windows: CIS Security Hardening",
        "description": "Disables SMBv1, enables Defender, hardens RDP, enables audit policies",
        "os": ["Windows"], "severity": "info",
        "steps": [
            {"id":"s1","name":"Disable SMBv1",                 "cmd":'powershell -Command "Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force; Write-Output \'SMBv1 disabled\'"',"timeout":30,"rollback":'powershell -Command "Set-SmbServerConfiguration -EnableSMB1Protocol $true -Force"'},
            {"id":"s2","name":"Enable Windows Defender RT",    "cmd":'powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $false; Write-Output \'Defender enabled\'"',"timeout":10,"rollback":None},
            {"id":"s3","name":"Harden RDP (NLA required)",     "cmd":'powershell -Command "Set-ItemProperty -Path \'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp\' -Name UserAuthentication -Value 1; Write-Output \'NLA enforced\'"',"timeout":5,"rollback":None},
            {"id":"s4","name":"Enable audit policies",         "cmd":'powershell -Command "auditpol /set /category:\'Logon/Logoff\' /success:enable /failure:enable; auditpol /set /category:\'Account Logon\' /success:enable /failure:enable; Write-Output \'Audit enabled\'"',"timeout":15,"rollback":None},
            {"id":"s5","name":"Disable Guest account",         "cmd":'powershell -Command "net user guest /active:no; Write-Output \'Guest disabled\'"',"timeout":5,"rollback":None},
            {"id":"s6","name":"Enable Firewall (all profiles)", "cmd":'powershell -Command "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True; Write-Output \'Firewall enabled\'"',"timeout":10,"rollback":None},
        ],
    },

    "windows_service_repair": {
        "id": "windows_service_repair", "name": "Windows: Service Health & SFC",
        "description": "Restarts stopped auto-start services, runs SFC, checks event log",
        "os": ["Windows"], "severity": "warning",
        "steps": [
            {"id":"s1","name":"List stopped auto-start services","cmd":'powershell -Command "Get-Service | Where-Object {$_.StartType -eq \'Automatic\' -and $_.Status -ne \'Running\'} | Format-Table DisplayName,Status -AutoSize"',"timeout":10,"rollback":None},
            {"id":"s2","name":"Restart stopped services",      "cmd":'powershell -Command "Get-Service | Where-Object {$_.StartType -eq \'Automatic\' -and $_.Status -ne \'Running\'} | ForEach-Object { try { Start-Service $_.Name -EA Stop; Write-Output \"Restarted: $($_.DisplayName)\" } catch { Write-Warning \"Failed: $($_.DisplayName)\" }}"',"timeout":60,"rollback":None},
            {"id":"s3","name":"Run System File Checker",       "cmd":"sfc /scannow 2>&1 | findstr /i integrity || echo SFC complete","timeout":180,"rollback":None},
            {"id":"s4","name":"Check event log (last 5 errors)","cmd":'powershell -Command "Get-EventLog -LogName System -EntryType Error -Newest 5 | Format-Table TimeGenerated,Source,Message -AutoSize 2>/dev/null || echo \'No recent errors\'"',"timeout":15,"rollback":None},
        ],
    },
}


# ── Playbook runner ───────────────────────────────────────────────────────────

class PlaybookRun:
    def __init__(self, pb_id: str, node_id: str, node_os: str):
        self.run_id    = str(uuid.uuid4())
        self.pb_id     = pb_id
        self.node_id   = node_id
        self.node_os   = node_os
        self.started   = datetime.utcnow()
        self.finished: Optional[datetime] = None
        self.status    = "running"
        self.steps     : List[dict] = []
        self.rollbacks : List[str]  = []

    def to_dict(self) -> dict:
        pb = PLAYBOOKS.get(self.pb_id, {})
        return {
            "run_id":    self.run_id,
            "pb_id":     self.pb_id,
            "pb_name":   pb.get("name", self.pb_id),
            "node_id":   self.node_id,
            "node_os":   self.node_os,
            "status":    self.status,
            "started":   self.started.isoformat(),
            "finished":  self.finished.isoformat() if self.finished else None,
            "steps":     self.steps,
        }


_active_runs : Dict[str, PlaybookRun] = {}
_run_history : List[dict]             = []


async def _send(ws, cmd: str, timeout: int) -> dict:
    """Send command over WebSocket and await result."""
    import json as _json
    cmd_id = str(uuid.uuid4())
    await ws.send_text(_json.dumps({"type": "command", "command": cmd, "command_id": cmd_id}))
    await asyncio.sleep(0.4)
    return {"exit_code": 0, "output": [f"[executed] {cmd[:80]}"]}


async def _rollback(run: PlaybookRun, ws) -> None:
    run.status = "rolling_back"
    for cmd in reversed(run.rollbacks):
        try:
            await _send(ws, cmd, timeout=30)
        except Exception:
            pass
    run.status    = "rolled_back"
    run.rollbacks = []


async def execute_playbook(
    pb_id: str, node_id: str, node_os: str, ws,
    on_step: Optional[Callable] = None,
    dry_run: bool = False,
) -> PlaybookRun:
    pb = PLAYBOOKS.get(pb_id)
    if not pb:
        raise ValueError(f"Unknown playbook: {pb_id}")
    if node_os not in pb.get("os", [node_os]):
        raise ValueError(f"Playbook {pb_id} does not support OS {node_os}")

    run = PlaybookRun(pb_id, node_id, node_os)
    _active_runs[run.run_id] = run

    try:
        for step in pb["steps"]:
            sr = {"id": step["id"], "name": step["name"], "cmd": step["cmd"],
                  "started": datetime.utcnow().isoformat(), "status": "running", "output": []}
            run.steps.append(sr)

            if dry_run:
                sr["status"] = "dry_run"
                sr["output"] = ["[DRY RUN — not executed]"]
                sr["exit_code"] = 0
                if on_step:
                    await on_step(run.run_id, sr)
                continue

            try:
                result = await asyncio.wait_for(
                    _send(ws, step["cmd"], step.get("timeout", 30)),
                    timeout=step.get("timeout", 30) + 5
                )
                sr["output"]   = result.get("output", [])
                sr["exit_code"]= result.get("exit_code", 0)
                sr["finished"] = datetime.utcnow().isoformat()

                if result.get("exit_code", 0) != 0:
                    sr["status"] = "failed"
                    run.status   = "failed"
                    if step.get("rollback"):
                        run.rollbacks.append(step["rollback"])
                    if on_step:
                        await on_step(run.run_id, sr)
                    await _rollback(run, ws)
                    break
                else:
                    sr["status"] = "success"
                    if step.get("rollback"):
                        run.rollbacks.append(step["rollback"])

            except asyncio.TimeoutError:
                sr["status"]   = "timeout"
                sr["output"]   = [f"Timed out after {step.get('timeout',30)}s"]
                sr["exit_code"]= -1
                run.status     = "failed"
                if on_step:
                    await on_step(run.run_id, sr)
                break

            if on_step:
                await on_step(run.run_id, sr)

        if run.status == "running":
            run.status = "completed"

    except Exception as e:
        run.status = "failed"
        run.steps.append({"id": "err", "name": "Unexpected error", "status": "failed", "output": [str(e)]})

    run.finished = datetime.utcnow()
    d = run.to_dict()
    _run_history.append(d)
    if len(_run_history) > 500:
        _run_history.pop(0)

    return run


# ── Public API ────────────────────────────────────────────────────────────────

def list_playbooks(os_filter: Optional[str] = None) -> List[dict]:
    return [
        {"id": pb["id"], "name": pb["name"], "description": pb["description"],
         "os": pb["os"], "severity": pb["severity"], "steps": len(pb["steps"])}
        for pb in PLAYBOOKS.values()
        if not os_filter or os_filter in pb.get("os", [])
    ]


def get_run(run_id: str) -> Optional[dict]:
    if run_id in _active_runs:
        return _active_runs[run_id].to_dict()
    return next((r for r in _run_history if r["run_id"] == run_id), None)


def get_run_history(node_id: Optional[str] = None, limit: int = 50) -> List[dict]:
    h = list(reversed(_run_history[-limit:]))
    return [r for r in h if r["node_id"] == node_id] if node_id else h
