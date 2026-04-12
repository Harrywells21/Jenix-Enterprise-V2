# core/rollback_engine.py — JENIX Rollback Backend
# Handles: Change logging, package snapshots, config backups, revert execution

import subprocess, json, shutil, hashlib, time, logging, re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Callable, Dict

log = logging.getLogger("jenix.rollback")


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: str, timeout: int = 120) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)


def _is_safe_revert_cmd(cmd: str) -> Tuple[bool, str]:
    """
    Validate a revert command before execution.
    Returns (is_safe: bool, reason: str).
    """
    if not cmd or not cmd.strip():
        return False, "Empty revert command"

    stripped = cmd.strip()

    if stripped.startswith("#"):
        return False, f"Manual action required — not executable: {stripped[1:].strip()}"

    _CHAIN_PATTERNS = [
        r"&&", r"\|\|",
        r";",
        r"`[^`]+`",
        r"\$\s*\(",
        r"\|\s*(bash|sh|zsh|dash|python|perl|ruby|nc|ncat|curl|wget)",
    ]
    for pattern in _CHAIN_PATTERNS:
        if re.search(pattern, stripped):
            return False, f"Revert command contains disallowed shell construct: {pattern!r}"

    _SAFE_PREFIXES = (
        "sudo apt-get", "sudo apt ", "sudo dnf", "sudo pacman", "sudo zypper",
        "sudo sysctl", "sudo cp", "sudo mv", "sudo systemctl", "sudo service",
        "sudo tee", "sysctl", "cp", "mv", "systemctl", "service",
    )
    if not any(stripped.startswith(pfx) for pfx in _SAFE_PREFIXES):
        return False, (
            f"Revert command does not start with a recognised safe verb. "
            f"Got: {stripped[:60]!r}"
        )

    _DANGEROUS_PATTERNS = [
        r">\s*/dev/sd[a-z]",
        r">\s*/dev/nvme",
        r"rm\s+-rf\s+/",
        r"mkfs",
        r"dd\s+if=",
    ]
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return False, f"Revert command matches dangerous pattern: {pattern!r}"

    return True, "ok"


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class RollbackEntry:
    id:          str
    ts:          str
    action_type: str
    description: str
    revert_cmd:  str
    metadata:    dict = field(default_factory=dict)
    reverted:    bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RevertResult:
    entry_id:    str
    description: str
    success:     bool
    output:      str
    error:       str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SnapshotInfo:
    label:      str
    path:       str
    ts:         str
    kind:       str
    size_kb:    int
    line_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RollbackStats:
    total:    int
    pending:  int
    reverted: int
    by_type:  Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── RollbackEngine ────────────────────────────────────────────────────────────

class RollbackEngine:
    """
    Backend engine for tracking and reverting system changes.
    All public methods are exception-safe — they never propagate to the GUI.

    Persists to:
        ~/.jenix/rollback.json    — action ledger
        ~/.jenix/snapshots/       — package lists and config backups
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self._base     = base_dir or (Path.home() / ".jenix")
        self._db_path  = self._base / "rollback.json"
        self._snap_dir = self._base / "snapshots"
        try:
            self._base.mkdir(exist_ok=True)
            self._snap_dir.mkdir(exist_ok=True)
        except Exception as ex:
            log.warning(f"Could not create rollback dirs: {ex}")
        self._entries: List[RollbackEntry] = []
        self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            raw = json.loads(self._db_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries_raw = raw
            elif isinstance(raw, dict):
                entries_raw = raw.get("actions") or raw.get("entries") or []
            else:
                entries_raw = []
            self._entries = [RollbackEntry(**e) for e in entries_raw]
            log.info(f"Rollback DB loaded: {len(self._entries)} entries")
        except Exception as ex:
            log.warning(f"Rollback DB load error: {ex}")
            self._entries = []

    def _save(self) -> None:
        try:
            payload = {
                "_meta": {
                    "schema_version": "1.0",
                    "app": "JENIX",
                },
                "actions": [asdict(e) for e in self._entries],
            }
            self._db_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception as ex:
            log.warning(f"Rollback DB save error: {ex}")

    # ── recording ─────────────────────────────────────────────────────────────

    def record(
        self,
        action_type: str,
        description: str,
        revert_cmd: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a reversible system change. Returns the unique entry ID."""
        try:
            eid = hashlib.md5(
                f"{action_type}{description}{time.time()}".encode()
            ).hexdigest()[:8]
            entry = RollbackEntry(
                id=eid,
                ts=datetime.now().isoformat(),
                action_type=action_type,
                description=description,
                revert_cmd=revert_cmd,
                metadata=metadata or {},
            )
            self._entries.append(entry)
            self._save()
            log.info(f"[TRACKED] {action_type}: {description}")
            return eid
        except Exception as ex:
            log.warning(f"record() failed: {ex}")
            return ""

    def record_install(self, package: str, distro_family: str = "debian") -> str:
        remove_cmds = {
            "debian": f"sudo apt-get remove -y {package}",
            "fedora": f"sudo dnf remove -y {package}",
            "arch":   f"sudo pacman -R --noconfirm {package}",
            "suse":   f"sudo zypper remove -y {package}",
        }
        revert_cmd = remove_cmds.get(distro_family, f"sudo apt-get remove -y {package}")
        return self.record("install", f"Installed package: {package}", revert_cmd,
                           {"package": package, "family": distro_family})

    def record_sysctl(self, key: str, old_value: str, new_value: str) -> str:
        return self.record(
            "sysctl",
            f"sysctl {key}: {old_value} → {new_value}",
            f"sudo sysctl -w {key}={old_value}",
            {"key": key, "old": old_value, "new": new_value},
        )

    def record_config(self, path: str, backup_path: str) -> str:
        return self.record(
            "config",
            f"Modified config: {path}",
            f"sudo cp {backup_path} {path}",
            {"original": path, "backup": backup_path},
        )

    def record_boost(self, task_name: str, revert_cmd: str) -> str:
        return self.record("boost", f"Boost: {task_name}", revert_cmd,
                           {"task": task_name})

    # ── snapshots ─────────────────────────────────────────────────────────────

    def snapshot_packages(self, label: str = "manual", list_cmd: str = "") -> dict:
        """
        Save the current package list to a timestamped file.

        Always returns a dict — never raises:
            {"status": "success"|"failed", "message": str, "path": str}

        Also returns legacy SnapshotInfo attributes on success so callers
        that check .path or .line_count continue to work.
        """
        try:
            if not list_cmd:
                list_cmd = self._detect_list_cmd()

            rc, out, err = _run(list_cmd, timeout=30)
            if rc != 0 or not out.strip():
                msg = f"Package list command failed (rc={rc}): {err[:80]}"
                log.warning(f"Package snapshot failed: {msg}")
                return {"status": "failed", "message": msg, "path": ""}

            ts_str    = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename  = f"pkgs_{label}_{ts_str}.txt"
            snap_path = self._snap_dir / filename
            snap_path.write_text(out, encoding="utf-8")

            size_kb    = snap_path.stat().st_size // 1024
            line_count = len(out.splitlines())
            log.info(f"Package snapshot saved: {snap_path} ({line_count} packages)")

            return {
                "status":     "success",
                "message":    f"Snapshot saved: {filename} ({line_count} packages)",
                "path":       str(snap_path),
                # Legacy fields — kept so old callers using .get() don't break
                "label":      label,
                "size_kb":    size_kb,
                "line_count": line_count,
            }
        except Exception as ex:
            msg = f"snapshot_packages() exception: {ex}"
            log.warning(msg)
            return {"status": "failed", "message": msg, "path": ""}

    def snapshot_config(self, path: str) -> SnapshotInfo:
        """Back up a config file before modifying it."""
        p = Path(path)
        if not p.exists():
            log.warning(f"Config snapshot: file not found: {path}")
            return SnapshotInfo(label=p.name, path="", ts="", kind="config",
                                size_kb=0, line_count=0)
        try:
            ts_str    = datetime.now().strftime("%Y%m%d_%H%M%S")
            snap_path = self._snap_dir / f"config_{p.name}_{ts_str}.bak"
            shutil.copy2(p, snap_path)
            size_kb = snap_path.stat().st_size // 1024
            log.info(f"Config snapshot saved: {snap_path}")
            return SnapshotInfo(
                label=p.name, path=str(snap_path),
                ts=datetime.now().isoformat(), kind="config",
                size_kb=size_kb, line_count=0,
            )
        except Exception as ex:
            log.warning(f"Config snapshot failed for {path}: {ex}")
            return SnapshotInfo(label=p.name, path="", ts="", kind="config",
                                size_kb=0, line_count=0)

    def list_snapshots(self) -> List[SnapshotInfo]:
        """Return all saved snapshots sorted newest-first."""
        snaps = []
        try:
            for f in sorted(self._snap_dir.iterdir(), reverse=True):
                if not f.is_file():
                    continue
                kind = "packages" if f.suffix == ".txt" else "config"
                size_kb = f.stat().st_size // 1024
                try:
                    lines = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                except Exception:
                    lines = 0
                snaps.append(SnapshotInfo(
                    label=f.stem, path=str(f), ts="", kind=kind,
                    size_kb=size_kb, line_count=lines,
                ))
        except Exception as ex:
            log.warning(f"list_snapshots() error: {ex}")
        return snaps

    def diff_packages(self, snap_path_before: str, snap_path_after: str) -> dict:
        try:
            before = set(Path(snap_path_before).read_text().splitlines())
            after  = set(Path(snap_path_after).read_text().splitlines())
            return {
                "added":     sorted(after - before),
                "removed":   sorted(before - after),
                "unchanged": len(before & after),
            }
        except Exception as ex:
            return {"error": str(ex), "added": [], "removed": [], "unchanged": 0}

    # ── reverting ─────────────────────────────────────────────────────────────

    def revert(
        self,
        entry_id: str,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> RevertResult:
        """Execute the revert command for a specific entry."""
        try:
            entry = next((e for e in self._entries if e.id == entry_id), None)
            if not entry:
                return RevertResult(
                    entry_id=entry_id, description="",
                    success=False, output="", error="Entry not found",
                )
            if entry.reverted:
                return RevertResult(
                    entry_id=entry_id, description=entry.description,
                    success=False, output="", error="Already reverted",
                )

            is_safe, reason = _is_safe_revert_cmd(entry.revert_cmd)
            if not is_safe:
                log.warning(f"[REVERT SKIPPED] {entry.description}: {reason}")
                return RevertResult(
                    entry_id=entry_id, description=entry.description,
                    success=False, output="",
                    error=f"Revert command rejected by safety check: {reason}",
                )

            if progress_cb:
                progress_cb(f"Reverting: {entry.description}")

            log.info(f"[REVERT] {entry.description} → {entry.revert_cmd}")
            rc, out, err = _run(entry.revert_cmd, timeout=120)

            if rc == 0:
                entry.reverted = True
                self._save()
                log.info(f"[REVERTED] {entry.description}")
                return RevertResult(
                    entry_id=entry_id, description=entry.description,
                    success=True, output=out, error="",
                )
            else:
                log.warning(f"[REVERT FAILED] {entry.description}: {err}")
                return RevertResult(
                    entry_id=entry_id, description=entry.description,
                    success=False, output=out, error=err,
                )
        except Exception as ex:
            log.error(f"revert() unexpected error for {entry_id}: {ex}")
            return RevertResult(
                entry_id=entry_id, description="",
                success=False, output="", error=str(ex),
            )

    def revert_all(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
        action_types: Optional[List[str]] = None,
    ) -> List[RevertResult]:
        """Revert all pending entries newest-first."""
        try:
            pending = self.get_pending()
            if action_types:
                pending = [e for e in pending if e.action_type in action_types]
            if not pending:
                log.info("[revert_all] No pending entries to revert")
                return []

            results: List[RevertResult] = []
            for entry in reversed(pending):
                try:
                    result = self.revert(entry.id, progress_cb)
                except Exception as ex:
                    log.error(f"[revert_all] Unexpected error for {entry.id}: {ex}")
                    result = RevertResult(
                        entry_id=entry.id, description=entry.description,
                        success=False, output="", error=f"Unexpected error: {ex}",
                    )
                results.append(result)

            success_count = sum(1 for r in results if r.success)
            log.info(f"[revert_all] {success_count}/{len(results)} reverted")
            return results
        except Exception as ex:
            log.error(f"revert_all() error: {ex}")
            return []

    def revert_last(self, n: int = 1) -> List[RevertResult]:
        """Revert the last n pending entries newest-first."""
        try:
            pending = self.get_pending()
            if not pending:
                return []
            to_revert = pending[-n:] if len(pending) >= n else pending[:]
            results: List[RevertResult] = []
            for entry in reversed(to_revert):
                try:
                    result = self.revert(entry.id)
                except Exception as ex:
                    log.error(f"[revert_last] Unexpected error for {entry.id}: {ex}")
                    result = RevertResult(
                        entry_id=entry.id, description=entry.description,
                        success=False, output="", error=f"Unexpected error: {ex}",
                    )
                results.append(result)
            return results
        except Exception as ex:
            log.error(f"revert_last() error: {ex}")
            return []

    # ── restore from snapshot ─────────────────────────────────────────────────

    def restore_packages_from_snapshot(
        self,
        snap_path: str,
        distro_family: str = "debian",
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> dict:
        try:
            current_snap = self.snapshot_packages("restore_compare")
            if current_snap.get("status") != "success":
                return {"error": "Could not get current package list",
                        "reinstalled": [], "failed": []}

            diff    = self.diff_packages(snap_path, current_snap["path"])
            removed = diff.get("removed", [])
            if not removed:
                return {"reinstalled": [], "failed": [], "skipped": 0,
                        "message": "No missing packages"}

            install_cmds = {
                "debian": "sudo apt-get install -y",
                "fedora": "sudo dnf install -y",
                "arch":   "sudo pacman -S --noconfirm",
                "suse":   "sudo zypper install -y",
            }
            base_cmd = install_cmds.get(distro_family, "sudo apt-get install -y")

            reinstalled = []
            failed      = []
            for pkg in removed:
                pkg = pkg.strip().split(":")[0]
                if not pkg:
                    continue
                if progress_cb:
                    progress_cb(f"Reinstalling {pkg}…")
                rc, _, err = _run(f"{base_cmd} {pkg}", timeout=120)
                if rc == 0:
                    reinstalled.append(pkg)
                    log.info(f"Reinstalled: {pkg}")
                else:
                    failed.append({"package": pkg, "error": err[:80]})
                    log.warning(f"Reinstall failed: {pkg}: {err[:60]}")

            return {
                "reinstalled": reinstalled,
                "failed":      failed,
                "skipped":     len(diff.get("added", [])),
                "message":     f"Restored {len(reinstalled)} packages, {len(failed)} failed",
            }
        except Exception as ex:
            log.error(f"restore_packages_from_snapshot() error: {ex}")
            return {"error": str(ex), "reinstalled": [], "failed": []}

    def restore_config(self, backup_path: str, target_path: str) -> dict:
        bp = Path(backup_path)
        if not bp.exists():
            return {"success": False, "error": f"Backup not found: {backup_path}"}
        rc, _, err = _run(f"sudo cp {backup_path} {target_path}", timeout=10)
        if rc == 0:
            log.info(f"Config restored: {target_path}")
            return {"success": True, "target": target_path, "source": backup_path}
        return {"success": False, "error": err}

    # ── queries ───────────────────────────────────────────────────────────────

    def get_all(self) -> List[RollbackEntry]:
        return list(self._entries)

    def get_pending(self) -> List[RollbackEntry]:
        return [e for e in self._entries if not e.reverted]

    def get_reverted(self) -> List[RollbackEntry]:
        return [e for e in self._entries if e.reverted]

    def get_by_type(self, action_type: str) -> List[RollbackEntry]:
        return [e for e in self._entries if e.action_type == action_type]

    def get_stats(self) -> RollbackStats:
        by_type: Dict[str, int] = {}
        for e in self._entries:
            by_type[e.action_type] = by_type.get(e.action_type, 0) + 1
        return RollbackStats(
            total=len(self._entries),
            pending=len(self.get_pending()),
            reverted=len(self.get_reverted()),
            by_type=by_type,
        )

    def find(self, entry_id: str) -> Optional[RollbackEntry]:
        return next((e for e in self._entries if e.id == entry_id), None)

    # ── convenience properties (used by GUI layer) ────────────────────────────

    @property
    def entries(self) -> List[RollbackEntry]:
        """All entries (reverted + pending). Alias for get_all()."""
        return self.get_all()

    @property
    def pending(self) -> List[RollbackEntry]:
        """Unreverted entries. Alias for get_pending()."""
        return self.get_pending()

    @property
    def count(self) -> int:
        """Number of pending (unreverted) entries."""
        return len(self.get_pending())

    @property
    def has_history(self) -> bool:
        return bool(self._entries)

    # ── management ────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._entries = []
        self._save()
        log.info("Rollback history cleared")

    def clear_reverted(self) -> int:
        before = len(self._entries)
        self._entries = [e for e in self._entries if not e.reverted]
        self._save()
        removed = before - len(self._entries)
        log.info(f"Removed {removed} reverted entries from ledger")
        return removed

    def delete_snapshot(self, snap_path: str) -> bool:
        try:
            Path(snap_path).unlink()
            log.info(f"Snapshot deleted: {snap_path}")
            return True
        except Exception as ex:
            log.warning(f"Snapshot delete failed: {ex}")
            return False

    def prune_snapshots(self, keep: int = 10) -> int:
        try:
            snaps = sorted(
                self._snap_dir.iterdir(),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            to_delete = snaps[keep:]
            for f in to_delete:
                try:
                    f.unlink()
                except Exception:
                    pass
            if to_delete:
                log.info(f"Pruned {len(to_delete)} old snapshots")
            return len(to_delete)
        except Exception as ex:
            log.warning(f"prune_snapshots() error: {ex}")
            return 0

    def export_ledger(self, export_path: str) -> dict:
        try:
            Path(export_path).write_text(
                json.dumps([asdict(e) for e in self._entries], indent=2),
                encoding="utf-8",
            )
            return {"success": True, "path": export_path, "entries": len(self._entries)}
        except Exception as ex:
            return {"success": False, "error": str(ex)}

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _detect_list_cmd() -> str:
        import shutil as _sh
        if _sh.which("dpkg"):
            return "dpkg --get-selections | grep -v deinstall | awk '{print $1}'"
        if _sh.which("rpm"):
            return "rpm -qa --queryformat '%{NAME}\n'"
        if _sh.which("pacman"):
            return "pacman -Qq"
        return "echo 'No package manager found'"


# ── module-level singleton ────────────────────────────────────────────────────

rollback_engine = RollbackEngine()
