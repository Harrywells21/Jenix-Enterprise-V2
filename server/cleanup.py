"""
JENIX Cleanup Jobs
- Delete metrics older than 7 days
- Delete read alerts older than 30 days
- Clean expired blacklisted tokens
Runs automatically on a schedule.
"""
import asyncio
from datetime import datetime, timedelta

async def run_cleanup():
    """Run all cleanup tasks every 6 hours."""
    while True:
        await asyncio.sleep(6 * 3600)  # every 6 hours
        try:
            _cleanup_metrics()
            _cleanup_alerts()
            _cleanup_tokens()
            print(f"[cleanup] Done at {datetime.utcnow().isoformat()}")
        except Exception as e:
            print(f"[cleanup] Error: {e}")

def _cleanup_metrics():
    from db import SessionLocal, Metric
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = db.query(Metric)\
                    .filter(Metric.timestamp < cutoff)\
                    .delete()
        db.commit()
        if deleted:
            print(f"[cleanup] Deleted {deleted} old metric rows")
    finally:
        db.close()

def _cleanup_alerts():
    from db import SessionLocal, Alert
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        deleted = db.query(Alert).filter(
            Alert.is_read   == True,
            Alert.timestamp < cutoff
        ).delete()
        db.commit()
        if deleted:
            print(f"[cleanup] Deleted {deleted} old read alerts")
    finally:
        db.close()

def _cleanup_tokens():
    from security import cleanup_old_tokens
    cleanup_old_tokens()
    print("[cleanup] Expired tokens cleared")

def run_cleanup_now():
    """Run cleanup immediately — useful for testing."""
    _cleanup_metrics()
    _cleanup_alerts()
    _cleanup_tokens()
    return {"ok": True, "ran_at": datetime.utcnow().isoformat()}
