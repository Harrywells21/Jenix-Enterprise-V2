"""
core/boost_engine.py
────────────────────
System optimisation engine for JENIX.

Provides:
  - gaming_mode()    : Aggressive optimisation for gaming sessions
  - work_mode()      : Light optimisation for productivity
  - deep_clean()     : Remove tmp/cache/unused packages
  - preview_clean()  : Dry-run — shows what deep_clean() would remove
  - suggest_mode()   : AI-driven automatic mode recommendation

All public functions return:
    {"success": bool, "message": str, "data": dict}
"""

import os
import shutil
from pathlib import Path

from utils.system_utils import run_cmd, which, dir_size_mb, get_memory_info
from utils.logger import log, audit
from utils.privilege_manager import priv

# ── Constants ─────────────────────────────────────────────────────────────────

# Safe-to-kill process names during gaming mode.
# Only well-known background / browser apps — never system daemons.
_GAMING_KILL_TARGETS = [
    "firefox", "chromium", "chrome", "brave", "opera",
    "thunderbird", "slack", "discord", "telegram-desktop",
    "dropbox", "spotify", "zoom", "teams",
    "update-notifier", "packagekitd",
]

# Directories targeted by deep_clean / preview_clean
_CLEAN_TARGETS = [
    "/tmp",
    str(Path.home() / ".cache"),
]

# ── Internal helpers ──────────────────────────────────────────────────────────

def _drop_caches() -> bool:
    """Flush FS buffers and drop kernel page/slab caches. Safe — no dirty pages lost."""
    run_cmd("sync")
    cmd = priv.wrap("sh -c 'echo 3 > /proc/sys/vm/drop_caches'")
    rc, _, stderr = run_cmd(cmd)
    if rc != 0:
        log.warning(f"[boost] drop_caches failed: {stderr}")
        return False
    return True


def _kill_process(name: str) -> bool:
    """Send SIGTERM to all processes matching *name*. Returns True if any matched."""
    rc, stdout, _ = run_cmd(f"pgrep -x {name}")
    if rc != 0 or not stdout.strip():
        return False
    run_cmd(f"pkill -TERM -x {name}")
    log.info(f"[boost] Sent SIGTERM to '{name}'")
    return True


def _measure_free_mb() -> float:
    """Return currently available memory in MB."""
    info = get_memory_info()
    return round(info.get("available", 0.0) * 1024, 1)


def _dir_size_mb_safe(path: str) -> float:
    try:
        return dir_size_mb(path)
    except Exception:
        return 0.0


# ── AI integration ────────────────────────────────────────────────────────────

def suggest_mode() -> dict:
    """
    Use the AI engine to analyse the current system state and recommend
    the best boost mode automatically.

    Reads CPU, RAM, and disk metrics from AIEngine.analyze_system() and
    maps the results to gaming_mode, work_mode, or deep_clean.

    Returns:
        {
            "success":         bool,
            "message":         str,
            "data": {
                "recommended_mode": str,   # "gaming_mode" | "work_mode" | "deep_clean" | "none"
                "reason":           str,
                "health_score":     int,
                "issues":           list,
                "metrics":          dict,
            }
        }
    """
    try:
        from core.ai_engine import AIEngine
    except ImportError:
        # Try relative import fallback
        try:
            from ai_engine import AIEngine
        except ImportError:
            return {
                "success": False,
                "message": "AI engine not available",
                "data": {"recommended_mode": "none", "reason": "Import failed"},
            }

    engine = AIEngine()
    analysis = engine.analyze_system()

    health_score = analysis.get("health_score", 100)
    issues       = analysis.get("issues", [])
    metrics      = analysis.get("metrics", {})

    cpu_pct          = metrics.get("cpu_percent",    0.0)
    ram_pct          = metrics.get("ram_percent",    0.0)
    worst_disk_pct   = metrics.get("worst_disk_pct", 0.0)

    # Rule-based mode selection
    if cpu_pct > 70 and ram_pct < 75 and worst_disk_pct < 80:
        recommended = "gaming_mode"
        reason = (
            f"CPU is heavily loaded ({cpu_pct:.0f}%). "
            "Gaming Mode will kill non-essential processes and set the CPU governor "
            "to performance to maximise responsiveness."
        )
    elif worst_disk_pct >= 85 or ram_pct >= 85:
        recommended = "deep_clean"
        reason = (
            f"System resources are critically constrained "
            f"(RAM {ram_pct:.0f}%, disk {worst_disk_pct:.0f}%). "
            "Deep Clean will free disk space and reduce memory pressure."
        )
    elif cpu_pct > 40 or ram_pct > 55 or worst_disk_pct > 60:
        recommended = "work_mode"
        reason = (
            f"Moderate resource usage detected "
            f"(CPU {cpu_pct:.0f}%, RAM {ram_pct:.0f}%). "
            "Work Mode will sync buffers and clear stale temp files."
        )
    else:
        recommended = "none"
        reason = (
            f"System is healthy (score {health_score}/100). "
            "No boost mode is currently necessary."
        )

    log.info(f"[boost] suggest_mode → {recommended} (score={health_score})")
    audit("boost", "suggest_mode called", {
        "recommended": recommended,
        "health_score": health_score,
        "cpu": cpu_pct,
        "ram": ram_pct,
        "disk": worst_disk_pct,
    })

    return {
        "success": True,
        "message": f"Recommended mode: {recommended}. {reason}",
        "data": {
            "recommended_mode": recommended,
            "reason":           reason,
            "health_score":     health_score,
            "issues":           issues,
            "metrics":          metrics,
        },
    }


def apply_suggested_mode() -> dict:
    """
    Convenience function: call suggest_mode() then immediately execute
    the recommended mode.  Returns the result from the executed mode,
    augmented with the suggestion metadata.

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    suggestion = suggest_mode()
    mode_name  = suggestion.get("data", {}).get("recommended_mode", "none")

    mode_map = {
        "gaming_mode": gaming_mode,
        "work_mode":   work_mode,
        "deep_clean":  deep_clean,
    }

    if mode_name not in mode_map:
        return {
            "success": True,
            "message": suggestion.get("message", "No action required."),
            "data": suggestion.get("data", {}),
        }

    result = mode_map[mode_name]()
    result["data"]["suggested_by_ai"]  = True
    result["data"]["ai_reason"]        = suggestion["data"].get("reason", "")
    result["data"]["health_score"]     = suggestion["data"].get("health_score", 0)
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def gaming_mode() -> dict:
    """
    Aggressive optimisation for gaming sessions.

    Actions:
      - Kill known non-essential background apps (SIGTERM only)
      - Flush filesystem buffers and drop kernel caches
      - Set CPU governor to 'performance' if available

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    log.info("[boost] gaming_mode started")
    actions_taken = []
    killed        = []
    mem_before    = _measure_free_mb()

    # 1. Kill non-essential processes
    for name in _GAMING_KILL_TARGETS:
        if _kill_process(name):
            killed.append(name)
            actions_taken.append(f"killed:{name}")

    # 2. Sync + drop caches
    if _drop_caches():
        actions_taken.append("drop_caches")
    else:
        actions_taken.append("drop_caches:skipped(no_root)")

    # 3. Set CPU governor to performance
    governor_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    if Path(governor_path).exists():
        cmd = priv.wrap(f"sh -c 'echo performance > {governor_path}'")
        rc, _, _ = run_cmd(cmd)
        actions_taken.append(
            "cpu_governor:performance" if rc == 0
            else "cpu_governor:skipped(no_root)"
        )

    mem_after = _measure_free_mb()
    freed_mb  = max(0.0, round(mem_after - mem_before, 1))

    audit("boost", "gaming_mode executed", {
        "killed": len(killed),
        "freed_mb": freed_mb,
    })

    return {
        "success": True,
        "message": (
            f"Gaming mode active. Killed {len(killed)} app(s), "
            f"freed ~{freed_mb} MB RAM."
        ),
        "data": {
            "killed_processes": killed,
            "actions_taken":    actions_taken,
            "freed_mb":         freed_mb,
        },
    }


def work_mode() -> dict:
    """
    Light optimisation for productivity sessions.

    Actions:
      - Sync filesystem buffers only (no aggressive cache drop)
      - Remove /tmp files older than 1 day owned by current user

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    log.info("[boost] work_mode started")
    actions_taken = []
    cleaned_items = []

    # 1. Sync buffers
    rc, _, _ = run_cmd("sync")
    if rc == 0:
        actions_taken.append("sync_buffers")

    # 2. Remove stale /tmp files (>1 day, current user only)
    tmp_before = _dir_size_mb_safe("/tmp")
    uid = os.getuid()
    rc, stdout, _ = run_cmd(
        f"find /tmp -maxdepth 1 -mtime +1 -user {uid} -print"
    )
    if rc == 0:
        for path_str in stdout.splitlines():
            path_str = path_str.strip()
            if not path_str:
                continue
            try:
                p = Path(path_str)
                if p.is_file() or p.is_symlink():
                    p.unlink()
                    cleaned_items.append(path_str)
                elif p.is_dir():
                    shutil.rmtree(path_str, ignore_errors=True)
                    cleaned_items.append(path_str)
            except OSError:
                continue
        actions_taken.append(f"tmp_cleanup:{len(cleaned_items)}_items")

    freed_mb = max(0.0, round(tmp_before - _dir_size_mb_safe("/tmp"), 1))

    audit("boost", "work_mode executed", {
        "cleaned": len(cleaned_items),
        "freed_mb": freed_mb,
    })

    return {
        "success": True,
        "message": (
            f"Work mode active. Cleaned {len(cleaned_items)} temp item(s), "
            f"freed ~{freed_mb} MB."
        ),
        "data": {
            "cleaned_items": cleaned_items,
            "freed_mb":      freed_mb,
            "actions_taken": actions_taken,
        },
    }


def deep_clean() -> dict:
    """
    Thorough disk-space recovery.

    Actions:
      - Delete all contents of /tmp and ~/.cache
      - Remove unused packages via apt / dnf / pacman autoremove

    Returns:
        {"success": bool, "message": str,
         "data": {"cleaned_items": list, "freed_space": int}}
    """
    log.info("[boost] deep_clean started")
    cleaned_items  = []
    freed_mb_total = 0.0
    errors         = []

    # 1. Wipe each target directory's contents
    for target in _CLEAN_TARGETS:
        p = Path(target)
        if not p.exists():
            continue
        size_before = _dir_size_mb_safe(target)
        for child in p.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                    cleaned_items.append(str(child))
                elif child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                    cleaned_items.append(str(child))
            except OSError as exc:
                errors.append(f"{child}: {exc}")
        freed_mb_total += max(0.0, size_before - _dir_size_mb_safe(target))

    # 2. Remove unused packages
    pkg_cmd    = None
    pkg_result = "skipped"

    if which("apt-get") and priv.can_escalate:
        pkg_cmd = priv.wrap("apt-get autoremove -y -q")
    elif which("dnf") and priv.can_escalate:
        pkg_cmd = priv.wrap("dnf autoremove -y -q")
    elif which("pacman") and priv.can_escalate:
        # Only run if there are actually orphaned packages to remove
        rc_q, orphans, _ = run_cmd("pacman -Qdtq")
        if rc_q == 0 and orphans.strip():
            pkg_cmd = priv.wrap("pacman -Rns $(pacman -Qdtq) --noconfirm")

    if pkg_cmd:
        rc, _, stderr = run_cmd(pkg_cmd, timeout=120)
        pkg_result = "ok" if rc == 0 else f"failed:{stderr[:80]}"
        if rc != 0:
            errors.append(f"autoremove: {stderr[:120]}")

    freed_mb_int = int(freed_mb_total)
    audit("boost", "deep_clean executed", {
        "items":     len(cleaned_items),
        "freed_mb":  freed_mb_int,
        "pkg_clean": pkg_result,
    })

    return {
        "success": len(errors) == 0,
        "message": (
            f"Deep clean complete. Removed {len(cleaned_items)} item(s), "
            f"freed ~{freed_mb_int} MB."
            + (f" ({len(errors)} error(s))" if errors else "")
        ),
        "data": {
            "cleaned_items": cleaned_items,
            "freed_space":   freed_mb_int,
            "errors":        errors,
        },
    }


def preview_clean() -> dict:
    """
    Dry-run: report what deep_clean() would remove — nothing is deleted.

    Returns:
        {"success": bool, "message": str,
         "data": {"cleaned_items": list, "freed_space": int}}
    """
    log.info("[boost] preview_clean started (dry-run)")
    would_clean    = []
    freed_mb_total = 0.0

    for target in _CLEAN_TARGETS:
        p = Path(target)
        if not p.exists():
            continue
        for child in p.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    try:
                        size = child.stat().st_size / (1024 ** 2)
                    except OSError:
                        size = 0.0
                    would_clean.append(str(child))
                    freed_mb_total += size
                elif child.is_dir():
                    size = _dir_size_mb_safe(str(child))
                    would_clean.append(str(child))
                    freed_mb_total += size
            except OSError:
                continue

    freed_mb_int = int(freed_mb_total)
    log.info(f"[boost] preview: {len(would_clean)} items, ~{freed_mb_int} MB")

    return {
        "success": True,
        "message": (
            f"Preview: {len(would_clean)} item(s) would be removed "
            f"(~{freed_mb_int} MB)."
        ),
        "data": {
            "cleaned_items": would_clean,
            "freed_space":   freed_mb_int,
        },
    }
