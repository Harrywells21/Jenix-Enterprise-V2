"""
JENIX Tamper-proof Audit System
Each log entry is hashed with SHA256 to detect tampering.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from db import get_db, AuditLog, Machine, User, compute_audit_hash
from auth import get_current_user
from datetime import datetime
import hashlib, json, io, csv, os, jwt

router = APIRouter(prefix="/audit", tags=["audit"])

def _compute_hash(log_entry: AuditLog) -> str:
    return compute_audit_hash(
        log_entry.id, log_entry.machine_id, log_entry.user_id,
        log_entry.action, log_entry.detail, log_entry.status, log_entry.timestamp,
    )

@router.get("/logs")
def get_audit_logs(limit: int = 200,
                   db:    Session = Depends(get_db),
                   _:     User    = Depends(get_current_user)):
    logs     = db.query(AuditLog)\
                 .order_by(AuditLog.timestamp.desc())\
                 .limit(limit).all()
    machines = {m.id: m.hostname for m in db.query(Machine).all()}
    users    = {u.id: u.name for u in db.query(User).all()}

    result = []
    for l in logs:
        entry_hash = _compute_hash(l)
        result.append({
            "id":         l.id,
            "machine_id": l.machine_id,
            "hostname":   machines.get(l.machine_id, "System"),
            "user_id":    l.user_id,
            "username":   users.get(l.user_id, "System"),
            "action":     l.action,
            "detail":     l.detail,
            "status":     l.status,
            "timestamp":  l.timestamp.isoformat(),
            "hash":       entry_hash[:16] + "...",  # preview
            "full_hash":  entry_hash,
        })
    return result

@router.get("/logs/verify/{log_id}")
def verify_log(log_id: int,
               db: Session = Depends(get_db),
               _:  User    = Depends(get_current_user)):
    l = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not l:
        return {"verified": False, "error": "Log not found"}
    computed = _compute_hash(l)
    if l.content_hash is None:
        return {
            "verified":  None,
            "log_id":    log_id,
            "hash":      computed,
            "timestamp": l.timestamp.isoformat(),
            "action":    l.action,
            "error":     "No stored hash on record for this log",
        }
    return {
        "verified":    computed == l.content_hash,
        "log_id":      log_id,
        "hash":        computed,
        "stored_hash": l.content_hash,
        "timestamp":   l.timestamp.isoformat(),
        "action":      l.action,
    }


@router.get("/logs/export")
def export_audit_csv(
    request: Request,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    """CSV export — accepts token as query param (for plain <a href> browser
    downloads, which can't attach an Authorization header) OR a normal
    Authorization header (needed when this route is called server-to-server,
    e.g. proxied from the JENIX master control plane, which always sends
    Bearer tokens via headers)."""
    from auth import decode_token

    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header[7:]

    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(raw_token)
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    logs     = db.query(AuditLog)\
                 .order_by(AuditLog.timestamp.desc())\
                 .limit(1000).all()
    machines = {m.id: m.hostname for m in db.query(Machine).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Timestamp","Machine","Action",
                     "Detail","Status","SHA256 Hash"])
    for l in logs:
        writer.writerow([
            l.id,
            l.timestamp.isoformat(),
            machines.get(l.machine_id, "System"),
            l.action, l.detail, l.status,
            _compute_hash(l),
        ])
    output.seek(0)
    fname = f"jenix_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )
