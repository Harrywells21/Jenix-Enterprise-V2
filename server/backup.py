"""
JENIX Database Backup System
Runs daily — keeps last 7 backups.
"""
import asyncio, os, shutil
from datetime import datetime, timedelta
from pathlib import Path

BACKUP_DIR = Path(__file__).parent / "backups"
DB_PATH    = Path(__file__).parent / "jenix.db"
MAX_BACKUPS = 7

async def run_backup_scheduler():
    """Run backup every 24 hours."""
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            backup_now()
        except Exception as e:
            print(f"[backup] Error: {e}")

def backup_now() -> str:
    """Create a timestamped backup of the database."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        print("[backup] No database found — skipping")
        return ""

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest      = BACKUP_DIR / f"jenix_{timestamp}.db"
    shutil.copy2(DB_PATH, dest)
    print(f"[backup] Backup created: {dest}")

    # Remove old backups beyond MAX_BACKUPS
    backups = sorted(BACKUP_DIR.glob("jenix_*.db"))
    while len(backups) > MAX_BACKUPS:
        old = backups.pop(0)
        old.unlink()
        print(f"[backup] Removed old backup: {old.name}")

    size_kb = dest.stat().st_size / 1024
    return str(dest)

def _backup_created_at(b) -> str:
    """Real backup creation time comes from the filename itself
    (jenix_YYYYMMDD_HHMMSS.db) — file mtime is NOT reliable here
    since backup_now() uses shutil.copy2, which preserves the
    SOURCE db's mtime on the copy rather than stamping the actual
    backup time. Falls back to mtime only if a filename doesn't
    match the expected pattern (e.g. a hand-renamed file)."""
    stem = b.stem  # "jenix_20260914_111137"
    parts = stem.split("_")
    if len(parts) == 3:
        try:
            return datetime.strptime(parts[1] + "_" + parts[2], "%Y%m%d_%H%M%S").isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(b.stat().st_mtime).isoformat()

def list_backups() -> list:
    """List all available backups."""
    if not BACKUP_DIR.exists():
        return []
    backups = sorted(BACKUP_DIR.glob("jenix_*.db"), reverse=True)
    return [{
        "filename": b.name,
        "path":     str(b),
        "size_kb":  round(b.stat().st_size / 1024, 1),
        "created":  _backup_created_at(b),
    } for b in backups]

def restore_backup(filename: str) -> bool:
    """Restore a specific backup."""
    src = BACKUP_DIR / filename
    if not src.exists():
        return False
    # Backup current DB first
    backup_now()
    shutil.copy2(src, DB_PATH)
    print(f"[backup] Restored from: {filename}")
    return True
