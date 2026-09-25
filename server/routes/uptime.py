"""
JENIX Uptime Monitor
Tracks machine uptime, downtime incidents, SLA compliance.

Downtime is measured from real DowntimeWindow rows (opened when a machine's
status flips to "offline" via WS disconnect or the offline_watchdog poller,
closed when it reconnects/reports online again -- see db.py's DowntimeWindow
model and the state-flip points in ws/handler.py) rather than a flat
5-minutes-per-offline-alert estimate. Response shape is unchanged from the
prior version, so no frontend changes are required.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from db import get_db, Machine, Metric, Alert, DowntimeWindow
from auth import get_current_user, User
from datetime import datetime, timedelta

router = APIRouter(prefix="/uptime", tags=["uptime"])


def _downtime_minutes_and_windows(db, machine_id, since, now):
    windows = db.query(DowntimeWindow).filter(
        DowntimeWindow.machine_id == machine_id,
        DowntimeWindow.started_at < now,
        or_(DowntimeWindow.ended_at.is_(None), DowntimeWindow.ended_at >= since)
    ).order_by(DowntimeWindow.started_at.desc()).all()

    seconds = 0.0
    for w in windows:
        w_start = max(w.started_at, since)
        w_end   = w.ended_at or now
        seconds += max(0.0, (w_end - w_start).total_seconds())

    return round(seconds / 60, 2), windows


@router.get("/{machine_id}")
def get_uptime(machine_id: int,
               days: int = 30,
               db: Session = Depends(get_db),
               _:  User    = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        return {"error": "Machine not found"}

    now   = datetime.utcnow()
    since = now - timedelta(days=days)

    downtime_minutes, windows = _downtime_minutes_and_windows(db, machine_id, since, now)

    total_minutes  = days * 24 * 60
    uptime_minutes = max(0, total_minutes - downtime_minutes)
    uptime_pct     = round((uptime_minutes / total_minutes) * 100, 2)

    sla_target = 99.0
    sla_met    = uptime_pct >= sla_target

    daily = []
    for i in range(min(days, 30)):
        day       = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        metric_count = db.query(func.count(Metric.id)).filter(
            Metric.machine_id == machine_id,
            Metric.timestamp  >= day_start,
            Metric.timestamp  <= day_end
        ).scalar()

        day_windows = [
            w for w in windows
            if (w.started_at <= day_end) and ((w.ended_at or now) >= day_start)
        ]

        status = "down" if day_windows \
            else "up" if metric_count > 0 \
            else "unknown"

        daily.append({
            "date":         day.strftime("%Y-%m-%d"),
            "status":       status,
            "metric_count": metric_count,
            "incidents":    len(day_windows),
        })

    return {
        "machine_id":       machine_id,
        "hostname":         m.hostname,
        "current_status":   m.status,
        "days_monitored":   days,
        "uptime_pct":       uptime_pct,
        "downtime_minutes": downtime_minutes,
        "incidents":        len(windows),
        "sla_target":       sla_target,
        "sla_met":          sla_met,
        "daily":            daily,
        "last_seen":        m.last_seen.isoformat() if m.last_seen else None,
    }

@router.get("/fleet/summary")
def fleet_uptime_summary(db: Session = Depends(get_db),
                         _:  User    = Depends(get_current_user)):
    machines = db.query(Machine).all()
    now      = datetime.utcnow()
    since    = now - timedelta(days=30)
    results  = []

    for m in machines:
        downtime_minutes, windows = _downtime_minutes_and_windows(db, m.id, since, now)
        total_minutes = 30 * 24 * 60
        uptime_pct = round(
            max(0, (total_minutes - downtime_minutes) / total_minutes * 100), 2
        )

        results.append({
            "machine_id":  m.id,
            "hostname":    m.hostname,
            "status":      m.status,
            "uptime_pct":  uptime_pct,
            "incidents":   len(windows),
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
