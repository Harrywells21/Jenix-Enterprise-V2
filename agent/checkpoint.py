import json, os, shutil, tarfile, uuid
from pathlib import Path
from datetime import datetime, timezone

CHECKPOINT_DIR = Path.home() / ".jenix" / "checkpoints"

# Fixed built-in default path set -- always included, merged with whatever
# extra paths the admin types in when dispatching checkpoint_start.
DEFAULT_PATHS = ["/etc", "/home", "/var/www", "/opt"]

# Explicit exclude list -- never captured regardless of read permission.
# These hold credentials/secrets that must not end up inside a checkpoint
# archive: shipping them in a tarball (which may get copied, restored onto
# a different machine, or handed to a buyer/developer for support) would be
# a real security exposure on its own, separate from the permission-error
# issue below. Extend this list if a deployment surfaces other sensitive
# paths under the default set (e.g. /home/*/.ssh/id_rsa, /home/*/.aws/credentials).
SENSITIVE_SKIP = {
    "/etc/shadow", "/etc/shadow-",
    "/etc/gshadow", "/etc/gshadow-",
    "/etc/.pwd.lock",
    "/etc/sudoers",
    "/etc/credstore", "/etc/credstore.encrypted",
    "/etc/ssl/private",
    "/etc/ssh/ssh_host_rsa_key", "/etc/ssh/ssh_host_ecdsa_key",
    "/etc/ssh/ssh_host_ed25519_key",
}

# Minimum free space (bytes) required to start OR continue a checkpoint.
# Chosen as a safety margin, not a hard minimum for the archive itself --
# running a machine down to near-zero free space breaks unrelated things
# (logging, sqlite writes, temp files) well before the disk is literally
# full at 0 bytes. 500MB is deliberately conservative for a general-purpose
# fleet tool; a future admin-configurable threshold could replace this.
MIN_FREE_BYTES = 500 * 1024 * 1024

# How often (every N tar.add calls) to re-check free space during a large
# walk. Checking before every single file is wasteful (disk_usage() is a
# real syscall); checking too rarely on a fast-filling disk risks a large
# overshoot. 25 is a reasonable middle ground for typical file sizes.
CHECK_EVERY_N_ITEMS = 25

# Files at or above this size get an individual disk-space check immediately
# before being added to the archive, in addition to the periodic every-N-items
# check above. A single large file (multi-hundred-MB or multi-GB) can push
# free space from comfortably-above-threshold to critically-low within one
# tar.add() call, before the next periodic tick even runs -- this catches
# that case specifically, without adding a disk_usage() syscall for every
# ordinary small file.
LARGE_FILE_BYTES = 20 * 1024 * 1024


class CheckpointDiskFullError(Exception):
    """Raised when free disk space drops below MIN_FREE_BYTES before or
    during a checkpoint. The caller (agent/executor.py) already catches
    generic exceptions from create_checkpoint() and reports them via
    log(f"[CHECKPOINT] Failed: {e}"), so no executor.py changes are needed --
    this just makes the failure message specific and actionable instead of
    a generic OSError, and guarantees no corrupt half-written archive is
    left behind."""
    pass


def _existing_paths(paths):
    out = []
    for p in paths:
        pp = Path(p)
        if pp.exists():
            out.append(str(pp))
    return out


def _is_sensitive(path_str: str) -> bool:
    if path_str in SENSITIVE_SKIP:
        return True
    return any(
        path_str == s or path_str.startswith(s.rstrip("/") + "/")
        for s in SENSITIVE_SKIP
    )


def _is_checkpoint_storage(path_str: str) -> bool:
    """CHECKPOINT_DIR (~/.jenix/checkpoints) lives under /home, which is
    itself one of DEFAULT_PATHS -- without this exclusion, a checkpoint
    would eventually walk into its own in-progress archive and try to tar
    itself into itself. Excluded unconditionally, independent of
    SENSITIVE_SKIP (this is a correctness issue, not a security one)."""
    cp_dir = str(CHECKPOINT_DIR)
    return path_str == cp_dir or path_str.startswith(cp_dir.rstrip("/") + "/")


def _check_disk_space(archive_path: Path, skipped: list, context: str = "") -> None:
    """Raises CheckpointDiskFullError and cleans up the partial archive if
    free space has dropped below MIN_FREE_BYTES. Checked against the
    filesystem backing CHECKPOINT_DIR, since that's where the archive is
    actually being written."""
    free = shutil.disk_usage(CHECKPOINT_DIR).free
    if free < MIN_FREE_BYTES:
        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise CheckpointDiskFullError(
            f"Insufficient disk space{context} (free: {free / (1024*1024):.1f}MB, "
            f"required: {MIN_FREE_BYTES / (1024*1024):.0f}MB). "
            f"Partial archive removed. {len(skipped)} item(s) had already been "
            f"processed before space ran out."
        )


def _check_disk_space_for_file(file_size: int, archive_path: Path, skipped: list, context: str = "") -> None:
    """Same guard as _check_disk_space, but pre-checks against a specific
    upcoming file's size rather than just the current free-space reading.
    Called before adding any file >= LARGE_FILE_BYTES, so a single huge file
    can't push free space from comfortably-above-threshold to critical in
    one tar.add() call before the next periodic _tick() check would catch it."""
    free = shutil.disk_usage(CHECKPOINT_DIR).free
    if free - file_size < MIN_FREE_BYTES:
        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise CheckpointDiskFullError(
            f"Insufficient disk space{context} (free: {free / (1024*1024):.1f}MB, "
            f"file size: {file_size / (1024*1024):.1f}MB, required margin after: "
            f"{MIN_FREE_BYTES / (1024*1024):.0f}MB). "
            f"Partial archive removed. {len(skipped)} item(s) had already been "
            f"processed before space ran out."
        )


def _safe_add_tree(tar, top_path: str, skipped: list, archive_path: Path, counter: list) -> None:
    """Adds top_path to tar, walking it manually (instead of tarfile's own
    recursive add) so that any single unreadable or excluded file is skipped
    and logged rather than aborting the whole archive mid-build. Every skip --
    whether a permission error or an explicit sensitive-path exclusion -- is
    recorded in `skipped` with a reason, so the checkpoint metadata always
    shows exactly what was and wasn't captured.

    `counter` is a single-element list used as a mutable int, so free-space
    checks can be paced across every call to this function within one
    checkpoint run (not just within one top-level path)."""
    top = Path(top_path)

    if _is_sensitive(str(top)):
        skipped.append({"path": str(top), "reason": "excluded (sensitive)"})
        return
    if _is_checkpoint_storage(str(top)):
        skipped.append({"path": str(top), "reason": "excluded (checkpoint storage)"})
        return

    def _tick():
        counter[0] += 1
        if counter[0] % CHECK_EVERY_N_ITEMS == 0:
            _check_disk_space(archive_path, skipped, context=f" while processing {top_path}")

    if top.is_symlink() or top.is_file():
        try:
            if top.is_file() and not top.is_symlink():
                try:
                    fsize = top.stat().st_size
                except OSError:
                    fsize = 0
                if fsize >= LARGE_FILE_BYTES:
                    _check_disk_space_for_file(fsize, archive_path, skipped,
                        context=f" before adding large file {top} ({fsize / (1024*1024):.1f}MB)")
            tar.add(str(top), arcname=str(top).lstrip("/"), recursive=False)
            _tick()
        except CheckpointDiskFullError:
            raise
        except (PermissionError, OSError) as e:
            skipped.append({"path": str(top), "reason": str(e)})
        return

    if not top.is_dir():
        return

    try:
        tar.add(str(top), arcname=str(top).lstrip("/"), recursive=False)
        _tick()
    except CheckpointDiskFullError:
        raise
    except (PermissionError, OSError) as e:
        skipped.append({"path": str(top), "reason": str(e)})

    def _on_walk_error(err):
        skipped.append({"path": getattr(err, "filename", str(top)), "reason": str(err)})

    for root, dirs, files in os.walk(top, onerror=_on_walk_error):
        rootp = Path(root)
        keep_dirs = []
        for d in dirs:
            dpath = rootp / d
            if _is_sensitive(str(dpath)):
                skipped.append({"path": str(dpath), "reason": "excluded (sensitive)"})
                continue
            if _is_checkpoint_storage(str(dpath)):
                skipped.append({"path": str(dpath), "reason": "excluded (checkpoint storage)"})
                continue
            keep_dirs.append(d)
            try:
                tar.add(str(dpath), arcname=str(dpath).lstrip("/"), recursive=False)
                _tick()
            except CheckpointDiskFullError:
                raise
            except (PermissionError, OSError) as e:
                skipped.append({"path": str(dpath), "reason": str(e)})
        dirs[:] = keep_dirs

        for f in files:
            fpath = rootp / f
            if _is_sensitive(str(fpath)):
                skipped.append({"path": str(fpath), "reason": "excluded (sensitive)"})
                continue
            if _is_checkpoint_storage(str(fpath)):
                skipped.append({"path": str(fpath), "reason": "excluded (checkpoint storage)"})
                continue
            try:
                if not fpath.is_symlink():
                    try:
                        fsize = fpath.stat().st_size
                    except OSError:
                        fsize = 0
                    if fsize >= LARGE_FILE_BYTES:
                        _check_disk_space_for_file(fsize, archive_path, skipped,
                            context=f" before adding large file {fpath} ({fsize / (1024*1024):.1f}MB)")
                tar.add(str(fpath), arcname=str(fpath).lstrip("/"), recursive=False)
                _tick()
            except CheckpointDiskFullError:
                raise
            except (PermissionError, OSError) as e:
                skipped.append({"path": str(fpath), "reason": str(e)})


def create_checkpoint(extra_paths: list | None = None) -> dict:
    """Tars the merged (default + extra) path list. Paths that don't exist
    on this machine are silently skipped rather than failing the whole
    checkpoint -- mirrors snapshot.py's tolerant style for optional data.
    Individual files that can't be read (permission errors) or that are
    explicitly excluded for security reasons are also skipped rather than
    aborting the whole checkpoint; every skip is recorded in meta['skipped'].

    Raises CheckpointDiskFullError (caught upstream by executor.py, which
    already logs any exception as "[CHECKPOINT] Failed: {e}") if free disk
    space drops below MIN_FREE_BYTES either before starting or at any point
    during the archive build. No corrupt/partial archive is left behind
    in that case."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    merged = list(dict.fromkeys(DEFAULT_PATHS + (extra_paths or [])))  # dedup, preserve order
    live_paths = _existing_paths(merged)

    cp_id = uuid.uuid4().hex[:12]
    archive_path = CHECKPOINT_DIR / f"{cp_id}.tar.gz"
    skipped: list = []

    # Upfront check -- fail fast before creating any archive at all if
    # there's already not enough room to reasonably start.
    _check_disk_space(archive_path, skipped, context=" before starting checkpoint")

    counter = [0]
    with tarfile.open(archive_path, "w:gz") as tar:
        for p in live_paths:
            # Store with paths relative to "/" so extractall(path="/") on
            # restore puts everything back exactly where it came from,
            # without ever writing an absolute path from inside the tar.
            _safe_add_tree(tar, p, skipped, archive_path, counter)

    meta = {
        "id": cp_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_paths": merged,
        "paths": live_paths,
        "archive": str(archive_path),
        "skipped": skipped,
    }
    (CHECKPOINT_DIR / f"{cp_id}.json").write_text(json.dumps(meta))
    return meta


def load_checkpoint(cp_id: str):
    meta_path = CHECKPOINT_DIR / f"{cp_id}.json"
    return json.loads(meta_path.read_text()) if meta_path.exists() else None


def list_checkpoints() -> list:
    """Enumerate checkpoints stored on this machine with real on-disk sizes.
    Not yet wired to any command/route -- this is groundwork for a future
    admin-facing cleanup view (e.g. after a checkpoint fails on low disk
    space, showing what old checkpoints could be discarded to free room).
    Deleting a listed checkpoint should go through the existing
    discard_checkpoint(cp_id, log), which already safely removes both the
    archive and its metadata -- no new deletion logic needed for that."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for meta_path in sorted(CHECKPOINT_DIR.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        archive = Path(meta.get("archive", ""))
        size = archive.stat().st_size if archive.exists() else 0
        out.append({
            "id": meta.get("id"),
            "created_at": meta.get("created_at"),
            "size_bytes": size,
            "num_skipped": len(meta.get("skipped", [])),
        })
    return out


def restore_checkpoint(cp_id: str, log) -> bool:
    meta = load_checkpoint(cp_id)
    if not meta:
        log(f"[CHECKPOINT] Checkpoint {cp_id} not found on this machine\n")
        return False

    archive_path = Path(meta["archive"])
    if not archive_path.exists():
        log(f"[CHECKPOINT] Archive missing from disk for {cp_id}\n")
        return False

    log(f"[CHECKPOINT] Restoring {cp_id} -- taken {meta['created_at']}, "
        f"paths: {', '.join(meta['paths']) or '(none captured)'}\n")

    restore_skipped = []
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                try:
                    tar.extract(member, path="/")
                except (PermissionError, OSError) as e:
                    restore_skipped.append({"path": member.name, "reason": str(e)})

        if restore_skipped:
            log(f"[CHECKPOINT] Restore complete with {len(restore_skipped)} "
                f"file(s) skipped (permission errors) -- see below.\n")
            for s in restore_skipped[:20]:
                log(f"[CHECKPOINT] skipped: /{s['path']} -- {s['reason']}\n")
        else:
            log("[CHECKPOINT] Restore complete.\n")
        return True
    except Exception as e:
        log(f"[CHECKPOINT] Restore failed: {e}\n")
        return False


def discard_checkpoint(cp_id: str, log) -> bool:
    """'Keep Current State' -- clears the checkpoint, no filesystem change."""
    meta = load_checkpoint(cp_id)
    if not meta:
        log(f"[CHECKPOINT] Checkpoint {cp_id} not found on this machine\n")
        return False
    Path(meta["archive"]).unlink(missing_ok=True)
    (CHECKPOINT_DIR / f"{cp_id}.json").unlink(missing_ok=True)
    log(f"[CHECKPOINT] Discarded {cp_id}. No filesystem changes were made.\n")
    return True
