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

ALLOWED = {"scan", "boost", "clean", "fix", "rollback", "exec"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set
SIGNED  = {"exec"}  # require a valid master-key signature instead of a node passphrase

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines
    params:     dict = {}
    passphrase: str | None = None  # applied uniformly; machines with a different/no passphrase set are skipped, not bypassed
    script:     str | None = None      # required when type == "exec"
    signature:  str | None = None      # required when type == "exec"; verified independently by each agent, never by this server

@router.post("/command")
async def fleet_command(body: FleetCommand,
                        db:   Session = Depends(get_db),
                        current_user: User = Depends(require_operator)):
    if body.type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown command")

    if body.type in SIGNED:
        if not body.script or not body.signature:
            raise HTTPException(status_code=400,
                                detail="'exec' requires both 'script' and 'signature'. "
                                       "This server does not verify the signature itself — "
                                       "each agent independently verifies it against the buyer's master public key.")

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

    from db import verify_passphrase
    results = []
    skipped_gated = []
    for m in machines:
        if body.type in GATED and m.action_passphrase_hash:
            if not body.passphrase or not verify_passphrase(body.passphrase, m.action_passphrase_hash):
                log = AuditLog(
                    machine_id = m.id,
                    user_id    = current_user.id,
                    action     = f"fleet_{body.type}_denied",
                    detail     = f"Fleet passphrase check failed for '{body.type}' on {m.hostname} by {current_user.name}",
                    status     = "critical"
                )
                db.add(log); db.commit()
                skipped_gated.append({"machine_id": m.id, "hostname": m.hostname,
                                       "reason": "passphrase required or incorrect"})
                continue
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
            "type":       "command",
            "command":    body.type,
            "command_id": cmd.id,
            "params":     body.params,
            "script":     body.script,
            "signature":  body.signature,
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
        "ok":            True,
        "total":         len(results),
        "sent":          sent_count,
        "failed":        failed_count,
        "results":       results,
        "skipped_gated": skipped_gated,
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
