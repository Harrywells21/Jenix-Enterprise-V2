from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db import get_db, Metric, Alert
from auth import get_current_user, User

router = APIRouter(prefix="/machines", tags=["metrics"])

# ── Last 100 metrics for a machine ────────────────────────────────────────
@router.get("/{machine_id}/metrics")
def get_metrics(machine_id: int, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    rows = db.query(Metric)\
             .filter(Metric.machine_id == machine_id)\
             .order_by(Metric.timestamp.desc())\
             .limit(100).all()
    return [{"cpu": r.cpu, "ram": r.ram, "disk": r.disk,
             "net_mb": r.net_mb, "disk_mb": r.disk_mb,
             "timestamp": r.timestamp.isoformat()} for r in reversed(rows)]

# ── Latest single metric ───────────────────────────────────────────────────
@router.get("/{machine_id}/metrics/latest")
def get_latest(machine_id: int, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    row = db.query(Metric)\
            .filter(Metric.machine_id == machine_id)\
            .order_by(Metric.timestamp.desc())\
            .first()
    if not row:
        return {"cpu": 0, "ram": 0, "disk": 0, "net_mb": 0, "disk_mb": 0}
    return {"cpu": row.cpu, "ram": row.ram, "disk": row.disk,
            "net_mb": row.net_mb, "disk_mb": row.disk_mb,
            "timestamp": row.timestamp.isoformat()}

# ── Alerts for a machine ───────────────────────────────────────────────────
@router.get("/{machine_id}/alerts")
def get_alerts(machine_id: int, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    alerts = db.query(Alert)\
               .filter(Alert.machine_id == machine_id)\
               .order_by(Alert.timestamp.desc())\
               .limit(20).all()
    return [{"id": a.id, "level": a.level, "type": a.type,
             "message": a.message, "is_read": a.is_read,
             "timestamp": a.timestamp.isoformat()} for a in alerts]

# ── Mark alert as read ─────────────────────────────────────────────────────
@router.patch("/{machine_id}/alerts/{alert_id}/read")
def mark_read(machine_id: int, alert_id: int,
              db: Session = Depends(get_db),
              _:  User    = Depends(get_current_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_read = True
        db.commit()
    return {"ok": True}
