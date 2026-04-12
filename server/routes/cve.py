from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from db import get_db, Machine, AuditLog
from auth import get_current_user, require_operator, User
from cve_scanner import run_cve_scan
from datetime import datetime
import json

router = APIRouter(prefix="/cve", tags=["cve"])

# Cache scan results in memory
_scan_cache = {}

@router.post("/scan/{machine_id}")
async def trigger_cve_scan(
    machine_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator)
):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")

    # For local machine — run directly
    # For remote — would send via agent (future enhancement)
    log = AuditLog(
        machine_id = machine_id,
        user_id    = current_user.id,
        action     = "cve_scan",
        detail     = f"CVE scan triggered by {current_user.name}",
        status     = "ok"
    )
    db.add(log); db.commit()

    # Run scan in background
    def _do_scan():
        result = run_cve_scan(max_packages=30)
        _scan_cache[machine_id] = result

    background_tasks.add_task(_do_scan)
    return {"ok": True, "message": "CVE scan started — check back in 30 seconds"}

@router.get("/results/{machine_id}")
def get_cve_results(
    machine_id: int,
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user)
):
    if machine_id not in _scan_cache:
        return {"scanned": False,
                "message": "No scan results yet. Run a scan first."}
    return {"scanned": True, **_scan_cache[machine_id]}

@router.get("/summary")
def cve_summary(db: Session = Depends(get_db),
                _:  User    = Depends(get_current_user)):
    total_critical = sum(
        r.get("critical", 0) for r in _scan_cache.values()
    )
    total_high = sum(
        r.get("high", 0) for r in _scan_cache.values()
    )
    machines_scanned = len(_scan_cache)
    return {
        "machines_scanned": machines_scanned,
        "total_critical":   total_critical,
        "total_high":       total_high,
        "last_scans": {
            str(mid): {
                "scanned_at":          r.get("scanned_at"),
                "vulnerable_packages": r.get("vulnerable_packages"),
                "risk_level":          r.get("risk_level"),
            }
            for mid, r in _scan_cache.items()
        }
    }
