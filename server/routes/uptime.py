"""
JENIX Uptime Monitor
Tracks machine uptime, downtime incidents, SLA compliance.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from db import get_db, Machine, Metric, Alert
from auth import get_current_user, User
from datetime import datetime, timedelta

router = APIRouter(prefix="/uptime", tags=["uptime"])

@router.get("/{machine_id}")
def get_uptime(machine_id: int,
               days: int = 30,
               db: Session = Depends(get_db),
               _:  User    = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        return {"error": "Machine not found"}

    since = datetime.utcnow() - timedelta(days=days)

    # Get offline alerts as downtime incidents
    offline_alerts = db.query(Alert).filter(
        Alert.machine_id == machine_id,
        Alert.type       == "offline",
        Alert.timestamp  >= since
    ).order_by(Alert.timestamp.desc()).all()

    # Calculate uptime percentage
    total_minutes    = days * 24 * 60
    downtime_minutes = len(offline_alerts) * 5  # estimate 5min per incident
    uptime_minutes   = max(0, total_minutes - downtime_minutes)
    uptime_pct       = round((uptime_minutes / total_minutes) * 100, 2)

    # SLA compliance
    sla_target  = 99.0
    sla_met     = uptime_pct >= sla_target

    # Daily breakdown (last 30 days)
    daily = []
    for i in range(min(days, 30)):
        day    = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end   = day.replace(hour=23, minute=59, second=59)

        # Count metrics for this day
        metric_count = db.query(func.count(Metric.id)).filter(
            Metric.machine_id == machine_id,
            Metric.timestamp  >= day_start,
            Metric.timestamp  <= day_end
        ).scalar()

        # Count offline alerts for this day
        offline_count = db.query(func.count(Alert.id)).filter(
            Alert.machine_id == machine_id,
            Alert.type       == "offline",
            Alert.timestamp  >= day_start,
            Alert.timestamp  <= day_end
        ).scalar()

        status = "up"   if metric_count > 0 and offline_count == 0 \
            else "down" if offline_count > 0 \
            else "unknown"

        daily.append({
            "date":          day.strftime("%Y-%m-%d"),
            "status":        status,
            "metric_count":  metric_count,
            "incidents":     offline_count,
        })

    return {
        "machine_id":      machine_id,
        "hostname":        m.hostname,
        "current_status":  m.status,
        "days_monitored":  days,
        "uptime_pct":      uptime_pct,
        "downtime_minutes":downtime_minutes,
        "incidents":       len(offline_alerts),
        "sla_target":      sla_target,
        "sla_met":         sla_met,
        "daily":           daily,
        "last_seen":       m.last_seen.isoformat() if m.last_seen else None,
    }

@router.get("/fleet/summary")
def fleet_uptime_summary(db: Session = Depends(get_db),
                         _:  User    = Depends(get_current_user)):
    machines = db.query(Machine).all()
    since    = datetime.utcnow() - timedelta(days=30)
    results  = []

    for m in machines:
        offline_count = db.query(func.count(Alert.id)).filter(
            Alert.machine_id == m.id,
            Alert.type       == "offline",
            Alert.timestamp  >= since
        ).scalar()

        total_minutes    = 30 * 24 * 60
        downtime_minutes = offline_count * 5
        uptime_pct = round(
            max(0, (total_minutes - downtime_minutes) / total_minutes * 100), 2
        )

        results.append({
            "machine_id":  m.id,
            "hostname":    m.hostname,
            "status":      m.status,
            "uptime_pct":  uptime_pct,
            "incidents":   offline_count,
            "sla_met":     uptime_pct >= 99.0,
        })

    fleet_avg = round(
        sum(r["uptime_pct"] for r in results) / len(results), 2
    ) if results else 100.0

    return {
        "fleet_uptime_pct": fleet_avg,
        "machines":         results,
        "sla_target":       99.0,
        "period_days":      30,
    }
