"""
JENIX Scheduler — automated scans with duplicate guard.
"""
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

def init_scheduler():
    scheduler.start()
    print("✅ Scheduler started")
    _reload_schedules()

def _reload_schedules():
    from db import SessionLocal, Schedule
    db = SessionLocal()
    try:
        schedules = db.query(Schedule)\
                      .filter(Schedule.is_active == True).all()
        for s in schedules:
            _add_job(s)
        print(f"[scheduler] Loaded {len(schedules)} schedules")
    finally:
        db.close()

def _add_job(schedule):
    job_id = f"schedule_{schedule.id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if schedule.frequency == "daily":
        trigger = CronTrigger(hour=schedule.hour, minute=0)
    else:
        trigger = CronTrigger(
            day_of_week="mon", hour=schedule.hour, minute=0)
    scheduler.add_job(
        _run_scheduled_scan,
        trigger       = trigger,
        id            = job_id,
        args          = [schedule.id],
        replace_existing = True
    )

async def _run_scheduled_scan(schedule_id: int):
    from db import SessionLocal, Schedule, Machine, AuditLog, Command
    from ws.handler import send_command
    db = SessionLocal()
    try:
        s = db.query(Schedule)\
              .filter(Schedule.id == schedule_id).first()
        if not s or not s.is_active:
            return

        # ✅ Duplicate guard — skip if ran in last 23 hours
        if s.last_run:
            hours_since = (datetime.utcnow() - s.last_run)\
                          .total_seconds() / 3600
            if hours_since < 23:
                print(f"[scheduler] Skipping schedule {schedule_id}"
                      f" — ran {hours_since:.1f}h ago")
                return

        m = db.query(Machine)\
              .filter(Machine.id == s.machine_id).first()
        if not m or m.status != "online":
            print(f"[scheduler] Machine {s.machine_id} offline — skipping")
            return

        print(f"[scheduler] Running {s.scan_type} on {m.hostname}")
        cmd = Command(machine_id=m.id, type=s.scan_type,
                      status="pending")
        db.add(cmd); db.commit(); db.refresh(cmd)

        sent = await send_command(
            m.token, {"cmd": s.scan_type, "cmd_id": cmd.id})
        cmd.status = "running" if sent else "failed"
        if not sent:
            cmd.output = "Agent not connected"

        s.last_run = datetime.utcnow()
        log = AuditLog(
            machine_id = m.id,
            action     = "scheduled_scan",
            detail     = f"Scheduled {s.scan_type} ran automatically",
            status     = "ok"
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[scheduler] error: {e}")
    finally:
        db.close()

def add_schedule(schedule):
    _add_job(schedule)

def remove_schedule(schedule_id: int):
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
