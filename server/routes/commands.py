from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Machine, Command, AuditLog
from auth import get_current_user, require_operator, User
from ws.handler import send_command
from datetime import datetime

router = APIRouter(prefix="/machines", tags=["commands"])

ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set

class CommandRequest(BaseModel):
    type: str
    params: dict = {}
    passphrase: str | None = None

class CommandOut(BaseModel):
    id:         int
    type:       str
    status:     str
    output:     str
    created_at: datetime
    class Config:
        from_attributes = True

# ── Send command ───────────────────────────────────────────────────────────
@router.post("/{machine_id}/command")
async def run_command(machine_id: int,
                      body: CommandRequest,
                      db:   Session = Depends(get_db),
                      current_user: User = Depends(require_operator)):
    if body.type not in ALLOWED:
        raise HTTPException(status_code=400,
                            detail=f"Unknown command. Allowed: {ALLOWED}")
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    if m.status != "online":
        raise HTTPException(status_code=400, detail="Machine is offline")
    if body.type in GATED and m.action_passphrase_hash:
        from db import verify_passphrase
        if not body.passphrase or not verify_passphrase(body.passphrase, m.action_passphrase_hash):
            log = AuditLog(machine_id=machine_id, user_id=current_user.id,
                           action=f"{body.type}_denied",
                           detail=f"Passphrase check failed for '{body.type}' by {current_user.name}",
                           status="critical")
            db.add(log); db.commit()
            raise HTTPException(status_code=403, detail="Invalid or missing node passphrase")
    cmd = Command(machine_id=machine_id, user_id=current_user.id,
                  type=body.type, status="pending")
    db.add(cmd); db.commit(); db.refresh(cmd)
    log = AuditLog(machine_id=machine_id, user_id=current_user.id,
                   action=body.type,
                   detail=f"Command '{body.type}' sent by {current_user.name}",
                   status="ok")
    db.add(log); db.commit()
    # Send via WebSocket to agent
    sent = await send_command(m.token, {
        "type":       "command",
        "command":    body.type,
        "command_id": cmd.id,
        "params":     body.params,
    })
    if not sent:
        cmd.status = "failed"
        cmd.output = "Agent not connected via WebSocket"
        db.commit()
        raise HTTPException(status_code=503, detail="Agent not connected")
    cmd.status = "running"
    db.commit()
    return {"ok": True, "cmd_id": cmd.id}

# ── Get command status ─────────────────────────────────────────────────────
@router.get("/{machine_id}/command/{cmd_id}", response_model=CommandOut)
def get_command(machine_id: int, cmd_id: int,
                db: Session = Depends(get_db),
                _:  User    = Depends(get_current_user)):
    cmd = db.query(Command).filter(
        Command.id == cmd_id,
        Command.machine_id == machine_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    return cmd

# ── List recent commands ───────────────────────────────────────────────────
@router.get("/{machine_id}/commands", response_model=list[CommandOut])
def list_commands(machine_id: int, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return db.query(Command)\
             .filter(Command.machine_id == machine_id)\
             .order_by(Command.created_at.desc())\
             .limit(20).all()
