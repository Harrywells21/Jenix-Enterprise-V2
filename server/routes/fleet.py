"""
JENIX Fleet Operations — broadcast commands to multiple machines.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Machine, Command, AuditLog
from auth import require_operator, User
from ws.handler import send_command
from datetime import datetime

router = APIRouter(prefix="/fleet", tags=["fleet"])

ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines

@router.post("/command")
async def fleet_command(body: FleetCommand,
                        db:   Session = Depends(get_db),
                        current_user: User = Depends(require_operator)):
    if body.type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown command")

    # Get target machines
    if body.machine_ids:
        machines = db.query(Machine)\
                     .filter(Machine.id.in_(body.machine_ids),
                             Machine.status == "online").all()
    else:
        machines = db.query(Machine)\
                     .filter(Machine.status == "online").all()

    if not machines:
        raise HTTPException(status_code=400, detail="No online machines found")

    results = []
    for m in machines:
        cmd = Command(
            machine_id = m.id,
            user_id    = current_user.id,
            type       = body.type,
            status     = "pending"
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)

        sent = await send_command(m.token, {
            "cmd": body.type, "cmd_id": cmd.id
        })

        if sent:
            cmd.status = "running"
        else:
            cmd.status = "failed"
            cmd.output = "Agent not connected"

        log = AuditLog(
            machine_id = m.id,
            user_id    = current_user.id,
            action     = f"fleet_{body.type}",
            detail     = f"Fleet command '{body.type}' sent by {current_user.name}",
            status     = "ok" if sent else "warning"
        )
        db.add(log)
        db.commit()

        results.append({
            "machine_id": m.id,
            "hostname":   m.hostname,
            "cmd_id":     cmd.id,
            "sent":       sent,
            "status":     cmd.status,
        })

    sent_count   = sum(1 for r in results if r["sent"])
    failed_count = len(results) - sent_count

    return {
        "ok":           True,
        "total":        len(results),
        "sent":         sent_count,
        "failed":       failed_count,
        "results":      results,
    }

@router.get("/status")
def fleet_status(db: Session = Depends(get_db),
                 _:  User    = Depends(require_operator)):
    machines = db.query(Machine).all()
    return {
        "total":   len(machines),
        "online":  sum(1 for m in machines if m.status == "online"),
        "offline": sum(1 for m in machines if m.status == "offline"),
    }
