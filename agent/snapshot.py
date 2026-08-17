import json, subprocess, uuid
from pathlib import Path
from datetime import datetime, timezone

SNAPSHOT_DIR = Path.home() / ".jenix" / "snapshots"
SYSCTL_KEYS  = ["vm.swappiness", "net.core.rmem_max"]  # exactly what 'boost' touches

def _sysctl_get(key):
    try:
        out = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None

def sudo_available() -> bool:
    """Check passwordless sudo works, without ever prompting for a password."""
    try:
        out = subprocess.run(["sudo", "-n", "true"], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False

def _dpkg_selections():
    try:
        out = subprocess.run(["dpkg", "--get-selections"], capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        pkgs = {}
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                pkgs[parts[0]] = parts[1]
        return pkgs
    except Exception:
        return None

def create_snapshot(reason: str) -> dict:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_id = uuid.uuid4().hex[:12]
    data = {
        "id": snap_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "sysctl": {k: _sysctl_get(k) for k in SYSCTL_KEYS},
        "dpkg_selections": _dpkg_selections(),
    }
    (SNAPSHOT_DIR / f"{snap_id}.json").write_text(json.dumps(data))
    return data

def latest_snapshot_id():
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else None

def load_snapshot(snap_id: str):
    path = SNAPSHOT_DIR / f"{snap_id}.json"
    return json.loads(path.read_text()) if path.exists() else None

def restore_snapshot(snap_id: str, log) -> bool:
    data = load_snapshot(snap_id)
    if not data:
        log(f"[ROLLBACK] Restore point {snap_id} not found on this machine\n")
        return False

    log(f"[ROLLBACK] Restoring point {snap_id} — taken {data['created_at']} ({data['reason']})\n")

    for key, val in (data.get("sysctl") or {}).items():
        if val is None:
            continue
        try:
            r = subprocess.run(["sudo", "-n", "/usr/local/sbin/jenix-sysctl-restore", key, val],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                log(f"[ROLLBACK] Restored {key} = {val}\n")
            else:
                log(f"[ROLLBACK] Failed to restore {key}: {r.stderr.strip()}\n")
        except Exception as e:
            log(f"[ROLLBACK] Failed to restore {key}: {e}\n")

    before, after = data.get("dpkg_selections"), _dpkg_selections()
    if before and after is not None:
        missing = [p for p, state in before.items() if state == "install" and after.get(p) != "install"]
        if missing:
            log(f"[ROLLBACK] Reinstalling {len(missing)} package(s) removed since this restore point\n")
            try:
                r = subprocess.run(["sudo", "-n", "/usr/local/sbin/jenix-apt-reinstall"] + missing,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    log(f"[ROLLBACK] Package reinstall failed: {r.stderr.strip()}\n")
            except Exception as e:
                log(f"[ROLLBACK] Package reinstall failed: {e}\n")
        else:
            log("[ROLLBACK] No packages need reinstalling\n")
    else:
        log("[ROLLBACK] Package-state comparison unavailable on this OS — sysctl values restored only\n")

    log("[ROLLBACK] Done.\n")
    return True
