from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Machine, AuditLog, hash_passphrase
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
        existing.status    = "offline"  # WS handler (agent_endpoint) sets "online" once truly connected
        existing.last_seen = datetime.utcnow()
        db.commit()
        return {"token": existing.token, "machine_id": existing.id}
    token   = secrets.token_hex(32)
    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="offline"  # WS handler (agent_endpoint) sets "online" once truly connected
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

# ── Restore points (snapshots) for machine ─────────────────────────────────
@router.get("/{machine_id}/snapshots")
def list_snapshots(machine_id: int, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    from db import Snapshot
    rows = db.query(Snapshot).filter(Snapshot.machine_id == machine_id)\
             .order_by(Snapshot.created_at.desc()).limit(20).all()
    return [{"id": s.id, "reason": s.reason,
             "created_at": s.created_at.isoformat()} for s in rows]

# ── Node action passphrase (gates boost/clean/fix/rollback) ────────────────
class PassphraseIn(BaseModel):
    passphrase: str

@router.post("/{machine_id}/passphrase")
def set_passphrase(machine_id: int, body: PassphraseIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    if len(body.passphrase) < 8:
        raise HTTPException(status_code=400, detail="Passphrase must be at least 8 characters")
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    m.action_passphrase_hash = hash_passphrase(body.passphrase)
    db.commit()
    log = AuditLog(machine_id=machine_id, user_id=current_user.id,
                   action="passphrase_set",
                   detail=f"Node action passphrase set/changed by {current_user.name}",
                   status="ok")
    db.add(log); db.commit()
    return {"ok": True}

@router.delete("/{machine_id}/passphrase")
def clear_passphrase(machine_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    m.action_passphrase_hash = None
    db.commit()
    log = AuditLog(machine_id=machine_id, user_id=current_user.id,
                   action="passphrase_cleared",
                   detail=f"Node action passphrase removed by {current_user.name}",
                   status="warning")
    db.add(log); db.commit()
    return {"ok": True}

@router.get("/{machine_id}/passphrase-status")
def passphrase_status(machine_id: int, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return {"is_set": bool(m.action_passphrase_hash)}

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
