"""
JENIX Enterprise — Auth utilities
JWT + bcrypt + role-based access
"""

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .models import User, AuditLog, get_db

SECRET_KEY     = os.getenv("SECRET_KEY", "change_me_in_production_please")
JWT_ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HRS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
LICENSE_SECRET = os.getenv("LICENSE_SECRET", "license_secret_change_me")

bearer_scheme = HTTPBearer(auto_error=False)


# ── Password ───────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ────────────────────────────────────────────────────────────────────

def create_token(user_id: str, username: str, role: str,
                 tenant_id: Optional[str] = None) -> str:
    payload = {
        "sub":       user_id,
        "username":  username,
        "role":      role,
        "tenant_id": tenant_id,
        "iat":       datetime.utcnow(),
        "exp":       datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HRS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


# ── Dependency: current user ───────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

def require_role(*roles):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency

require_admin    = require_role("admin")
require_operator = require_role("admin", "operator")
require_viewer   = require_role("admin", "operator", "viewer")


# ── WebSocket auth ─────────────────────────────────────────────────────────

async def ws_auth(websocket: WebSocket) -> Optional[dict]:
    """Authenticate WebSocket connections via query param or header."""
    token = websocket.query_params.get("token")
    if not token:
        token = websocket.headers.get("X-API-Key")
    if not token:
        return None
    try:
        return decode_token(token)
    except Exception:
        return None


# ── Audit log with SHA-256 tamper-proof hash ───────────────────────────────

def write_audit(db: Session, action: str, detail: str = "",
                node_id: str = None, user_id: str = None,
                ip: str = None):
    entry_data = json.dumps({
        "action":    action,
        "detail":    detail,
        "node_id":   node_id,
        "user_id":   user_id,
        "ip":        ip,
        "timestamp": datetime.utcnow().isoformat(),
    }, sort_keys=True)

    sha = hashlib.sha256(
        hmac.new(LICENSE_SECRET.encode(), entry_data.encode(), hashlib.sha256).digest()
    ).hexdigest()

    log = AuditLog(
        node_id=node_id, user_id=user_id,
        action=action, detail=detail,
        ip_address=ip, sha256=sha,
    )
    db.add(log)
    db.commit()
    return log


# ── License generation & validation ───────────────────────────────────────

def generate_license_key(company: str, node_limit: int = -1) -> str:
    payload = json.dumps({
        "company":    company,
        "node_limit": node_limit,
        "issued":     datetime.utcnow().isoformat(),
        "uuid":       str(uuid.uuid4()),
    }, sort_keys=True)
    sig = hmac.new(LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    import base64
    b64 = base64.b64encode(payload.encode()).decode()
    return f"JENIX-{sig[:16].upper()}-{b64[:32]}-{sig[16:32].upper()}"

def validate_license_key(key: str) -> bool:
    return key.startswith("JENIX-") and len(key) > 20
