from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Machine, AuditLog
from auth import get_current_user, require_admin, User
from datetime import datetime
import secrets

router = APIRouter(prefix="/machines", tags=["machines"])

class MachineRegister(BaseModel):
    hostname: str
    ip:       str
    os_name:  str = ""
    kernel:   str = ""

class MachineOut(BaseModel):
    id:        int
    hostname:  str
    ip:        str
    os_name:   str
    kernel:    str
    status:    str
    last_seen: datetime
    class Config:
        from_attributes = True

# ── Register (called by agent) ─────────────────────────────────────────────
@router.post("/register")
def register(body: MachineRegister, db: Session = Depends(get_db)):
    existing = db.query(Machine).filter(
        Machine.hostname == body.hostname,
        Machine.ip == body.ip
    ).first()
    if existing:
        existing.os_name   = body.os_name
        existing.kernel    = body.kernel
        existing.status    = "online"
        existing.last_seen = datetime.utcnow()
        db.commit()
        return {"token": existing.token, "machine_id": existing.id}
    token   = secrets.token_hex(32)
    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="online"
    )
    db.add(machine); db.commit(); db.refresh(machine)
    log = AuditLog(machine_id=machine.id, action="registered",
                   detail=f"{body.hostname} ({body.ip}) joined",
                   status="ok")
    db.add(log); db.commit()
    return {"token": token, "machine_id": machine.id}

# ── List all machines ──────────────────────────────────────────────────────
@router.get("", response_model=list[MachineOut])
def list_machines(db: Session = Depends(get_db),
                  _:  User    = Depends(get_current_user)):
    return db.query(Machine).order_by(Machine.hostname).all()

# ── Single machine ─────────────────────────────────────────────────────────
@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: int, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return m

# ── Delete machine (admin only) ────────────────────────────────────────────
@router.delete("/{machine_id}")
def delete_machine(machine_id: int, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(m); db.commit()
    return {"ok": True}

# ── Audit log for machine ──────────────────────────────────────────────────
@router.get("/{machine_id}/logs")
def get_logs(machine_id: int, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    logs = db.query(AuditLog)\
             .filter(AuditLog.machine_id == machine_id)\
             .order_by(AuditLog.timestamp.desc())\
             .limit(50).all()
    return [{"id": l.id, "action": l.action, "detail": l.detail,
             "status": l.status,
             "timestamp": l.timestamp.isoformat()} for l in logs]
