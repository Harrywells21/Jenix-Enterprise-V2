from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Machine, Command, AuditLog
from auth import get_current_user, require_operator, User
from ws.handler import send_command
from datetime import datetime

router = APIRouter(prefix="/machines", tags=["commands"])

ALLOWED = {"scan", "boost", "clean", "fix", "rollback", "exec", "reassign_server"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set
SIGNED  = {"exec", "reassign_server"}  # require a valid master-key signature instead of a node passphrase

class CommandRequest(BaseModel):
    type: str
    params: dict = {}
    passphrase: str | None = None
    script:     str | None = None      # required when type == "exec"
    signature:  str | None = None      # required when type == "exec"; verified independently by the agent, never by this server

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
    if body.type == "exec":
        if not body.script or not body.signature:
            raise HTTPException(status_code=400,
                                detail="'exec' requires both 'script' and 'signature'. "
                                       "This server does not verify the signature itself — "
                                       "the agent independently verifies it against the buyer's master public key.")
    if body.type == "reassign_server":
        if not body.params.get("server_url") or not body.signature:
            raise HTTPException(status_code=400,
                                detail="'reassign_server' requires both params.server_url and 'signature'. "
                                       "This server does not verify the signature itself — "
                                       "the agent independently verifies it against the buyer's topology public "
                                       "key and only accepts a target URL from its baked-in trusted floor list.")
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
        "script":     body.script,
        "signature":  body.signature,
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

# ── Fleet-wide command history (all machines, single query) ────────────────
@router.get("/history/all")
def list_all_commands(limit: int = 200,
                      db: Session = Depends(get_db),
                      _:  User    = Depends(get_current_user)):
    """Mirrors routes/audit.py's get_audit_logs pattern: one query across all
    commands, joined against a hostname lookup built from a single Machine
    query — never one HTTP/DB call per machine. Keep it this way; a
    per-machine fan-out from master is what caused the FD-exhaustion crash."""
    commands = db.query(Command)\
                 .order_by(Command.created_at.desc())\
                 .limit(limit).all()
    machines = {m.id: m.hostname for m in db.query(Machine).all()}

    result = []
    for c in commands:
        result.append({
            "id":         c.id,
            "machine_id": c.machine_id,
            "hostname":   machines.get(c.machine_id, "Unknown"),
            "user_id":    c.user_id,
            "type":       c.type,
            "status":     c.status,
            "output":     c.output,
            "snapshot_id": c.snapshot_id,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        })
    return result
