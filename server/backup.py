"""
JENIX Database Backup System
Runs daily — keeps last 7 backups.
"""
import asyncio, os, shutil
from datetime import datetime, timedelta
from pathlib import Path

BACKUP_DIR = Path.home() / ".jenix" / "backups"
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
    print(f"[backup] ✅ Backup created: {dest}")

    # Remove old backups beyond MAX_BACKUPS
    backups = sorted(BACKUP_DIR.glob("jenix_*.db"))
    while len(backups) > MAX_BACKUPS:
        old = backups.pop(0)
        old.unlink()
        print(f"[backup] Removed old backup: {old.name}")

    size_kb = dest.stat().st_size / 1024
    return str(dest)

def list_backups() -> list:
    """List all available backups."""
    if not BACKUP_DIR.exists():
        return []
    backups = sorted(BACKUP_DIR.glob("jenix_*.db"), reverse=True)
    return [{
        "filename": b.name,
        "path":     str(b),
        "size_kb":  round(b.stat().st_size / 1024, 1),
        "created":  datetime.fromtimestamp(
            b.stat().st_mtime).isoformat(),
    } for b in backups]

def restore_backup(filename: str) -> bool:
    """Restore a specific backup."""
    src = BACKUP_DIR / filename
    if not src.exists():
        return False
    # Backup current DB first
    backup_now()
    shutil.copy2(src, DB_PATH)
    print(f"[backup] ✅ Restored from: {filename}")
    return True
