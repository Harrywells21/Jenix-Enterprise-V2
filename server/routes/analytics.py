"""
JENIX Fleet Analytics — powers the executive dashboard.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db import get_db, Machine, Metric, Alert, Command, AuditLog
from auth import get_current_user, User
from health_score import calculate_health_score
from datetime import datetime, timedelta

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/fleet")
def fleet_overview(db: Session = Depends(get_db),
                   _:  User    = Depends(get_current_user)):
    machines = db.query(Machine).all()
    total    = len(machines)
    online   = sum(1 for m in machines if m.status == "online")
    offline  = total - online

    # Fleet-wide metric averages (last 100 per machine)
    all_cpu, all_ram, all_disk = [], [], []
    machine_scores = []

    for m in machines:
        metrics = db.query(Metric)\
                    .filter(Metric.machine_id == m.id)\
                    .order_by(Metric.timestamp.desc())\
                    .limit(100).all()
        alerts = db.query(Alert)\
                   .filter(Alert.machine_id == m.id)\
                   .order_by(Alert.timestamp.desc())\
                   .limit(20).all()

        metrics_list = [{"cpu": x.cpu, "ram": x.ram,
                          "disk": x.disk} for x in metrics]
        alerts_list  = [{"level": a.level, "is_read": a.is_read,
                          "type": a.type} for a in alerts]

        if metrics_list:
            all_cpu.append(sum(x["cpu"]  for x in metrics_list) / len(metrics_list))
            all_ram.append(sum(x["ram"]  for x in metrics_list) / len(metrics_list))
            all_disk.append(sum(x["disk"] for x in metrics_list) / len(metrics_list))

        score_data = calculate_health_score(
            {"status": m.status},
            metrics_list, alerts_list
        )
        machine_scores.append({
            "id":       m.id,
            "hostname": m.hostname,
            "ip":       m.ip,
            "os_name":  m.os_name,
            "status":   m.status,
            "score":    score_data["score"],
            "grade":    score_data["grade"],
            "color":    score_data["color"],
            "cpu":      all_cpu[-1] if all_cpu else 0,
            "ram":      all_ram[-1] if all_ram else 0,
            "disk":     all_disk[-1] if all_disk else 0,
            "breakdown": score_data["breakdown"],
        })

    # Sort by score ascending (worst first)
    machine_scores.sort(key=lambda x: x["score"])

    # Critical alerts count
    critical_alerts = db.query(Alert)\
                        .filter(Alert.level == "critical",
                                Alert.is_read == False)\
                        .count()
    warning_alerts  = db.query(Alert)\
                        .filter(Alert.level == "warning",
                                Alert.is_read == False)\
                        .count()

    # Commands run in last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    commands_24h = db.query(Command)\
                     .filter(Command.created_at >= since)\
                     .count()

    # Estimated hours saved (each command saves ~30min manual work)
    hours_saved = commands_24h * 0.5

    # Activity timeline (last 20 audit log entries across all machines)
    recent_logs = db.query(AuditLog)\
                    .order_by(AuditLog.timestamp.desc())\
                    .limit(20).all()
    activity = [{
        "action":    l.action,
        "detail":    l.detail,
        "status":    l.status,
        "timestamp": l.timestamp.isoformat(),
        "machine_id": l.machine_id,
    } for l in recent_logs]

    return {
        "total":           total,
        "online":          online,
        "offline":         offline,
        "avg_cpu":         round(sum(all_cpu)  / len(all_cpu),  1) if all_cpu  else 0,
        "avg_ram":         round(sum(all_ram)  / len(all_ram),  1) if all_ram  else 0,
        "avg_disk":        round(sum(all_disk) / len(all_disk), 1) if all_disk else 0,
        "critical_alerts": critical_alerts,
        "warning_alerts":  warning_alerts,
        "commands_24h":    commands_24h,
        "hours_saved":     hours_saved,
        "machine_scores":  machine_scores,
        "activity":        activity,
    }

@router.get("/machine/{machine_id}/score")
def machine_score(machine_id: int,
                  db: Session = Depends(get_db),
                  _:  User    = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        return {"score": 0, "grade": "Unknown", "color": "#666"}

    metrics = db.query(Metric)\
                .filter(Metric.machine_id == machine_id)\
                .order_by(Metric.timestamp.desc())\
                .limit(100).all()
    alerts  = db.query(Alert)\
                .filter(Alert.machine_id == machine_id)\
                .order_by(Alert.timestamp.desc())\
                .limit(20).all()

    metrics_list = [{"cpu": x.cpu, "ram": x.ram,
                      "disk": x.disk} for x in metrics]
    alerts_list  = [{"level": a.level, "is_read": a.is_read,
                      "type": a.type} for a in alerts]

    return calculate_health_score(
        {"status": m.status},
        metrics_list, alerts_list
    )

@router.get("/alerts/all")
def all_alerts(db: Session = Depends(get_db),
               _:  User    = Depends(get_current_user)):
    alerts = db.query(Alert)\
               .order_by(Alert.timestamp.desc())\
               .limit(100).all()
    machines = {m.id: m.hostname for m in db.query(Machine).all()}
    return [{
        "id":         a.id,
        "machine_id": a.machine_id,
        "hostname":   machines.get(a.machine_id, "Unknown"),
        "level":      a.level,
        "type":       a.type,
        "message":    a.message,
        "is_read":    a.is_read,
        "timestamp":  a.timestamp.isoformat(),
    } for a in alerts]

@router.post("/alerts/mark-all-read")
def mark_all_read(db: Session = Depends(get_db),
                  _:  User    = Depends(get_current_user)):
    db.query(Alert).update({"is_read": True})
    db.commit()
    return {"ok": True}

@router.get("/savings")
def cost_savings(db: Session = Depends(get_db),
                 _:  User    = Depends(get_current_user)):
    # Commands run this month
    since_month = datetime.utcnow() - timedelta(days=30)
    since_week  = datetime.utcnow() - timedelta(days=7)

    monthly_cmds = db.query(Command)\
                     .filter(Command.created_at >= since_month,
                             Command.status == "done").count()
    weekly_cmds  = db.query(Command)\
                     .filter(Command.created_at >= since_week,
                             Command.status == "done").count()

    hourly_rate   = 45   # avg sysadmin hourly rate USD
    mins_per_task = 30   # mins saved per automated task

    monthly_hours = monthly_cmds * (mins_per_task / 60)
    weekly_hours  = weekly_cmds  * (mins_per_task / 60)
    monthly_saved = monthly_hours * hourly_rate
    weekly_saved  = weekly_hours  * hourly_rate

    # Payback period (assuming $65k license)
    license_cost   = 65000
    annual_savings = monthly_saved * 12
    payback_months = round(license_cost / monthly_saved, 1) if monthly_saved > 0 else 999

    return {
        "weekly_commands":  weekly_cmds,
        "monthly_commands": monthly_cmds,
        "weekly_hours":     round(weekly_hours,  1),
        "monthly_hours":    round(monthly_hours, 1),
        "weekly_saved":     round(weekly_saved,  2),
        "monthly_saved":    round(monthly_saved, 2),
        "annual_savings":   round(annual_savings, 2),
        "payback_months":   payback_months,
        "license_cost":     license_cost,
        "hourly_rate":      hourly_rate,
    }
