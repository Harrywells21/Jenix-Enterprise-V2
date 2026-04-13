"""
JENIX Security Module
- Rate limiting
- Token blacklist (DB-persisted)
- Security headers
- Input sanitization
"""
import os, time, hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Security Headers ───────────────────────────────────────────────────────
SECURITY_HEADERS = {
    "X-Content-Type-Options":  "nosniff",
    "X-Frame-Options":         "DENY",
    "X-XSS-Protection":        "1; mode=block",
    "Referrer-Policy":         "strict-origin-when-cross-origin",
    "Permissions-Policy":      "geolocation=(), microphone=()",
    "Cache-Control":           "no-store",
}

# ── Rate Limiter ───────────────────────────────────────────────────────────
_rate_store = defaultdict(list)

def check_rate_limit(key: str, max_req: int,
                     window_sec: int) -> bool:
    now  = time.time()
    hits = [h for h in _rate_store[key] if now - h < window_sec]
    _rate_store[key] = hits
    if len(hits) >= max_req:
        return False
    _rate_store[key].append(now)
    return True

def rate_limit_login(ip: str) -> bool:
    return check_rate_limit(f"login:{ip}", 10, 60)

def rate_limit_api(ip: str) -> bool:
    return check_rate_limit(f"api:{ip}", 300, 60)

# ── Token Blacklist (DB-backed) ────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def blacklist_token(token: str):
    from db import SessionLocal, BlacklistedToken
    db = SessionLocal()
    try:
        h = _hash_token(token)
        if not db.query(BlacklistedToken)\
                 .filter(BlacklistedToken.token_hash == h).first():
            db.add(BlacklistedToken(token_hash=h))
            db.commit()
    finally:
        db.close()

def is_token_blacklisted(token: str) -> bool:
    from db import SessionLocal, BlacklistedToken
    db = SessionLocal()
    try:
        h = _hash_token(token)
        return db.query(BlacklistedToken)\
                 .filter(BlacklistedToken.token_hash == h)\
                 .first() is not None
    finally:
        db.close()

def cleanup_old_tokens():
    """Remove tokens older than 48 hours — run periodically."""
    from db import SessionLocal, BlacklistedToken
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=48)
        db.query(BlacklistedToken)\
          .filter(BlacklistedToken.created_at < cutoff)\
          .delete()
        db.commit()
    finally:
        db.close()

# ── Input Sanitization ─────────────────────────────────────────────────────
def sanitize_string(s: str, max_len: int = 255) -> str:
    if not s:
        return ""
    return s.replace("\x00", "").strip()[:max_len]

def sanitize_command(cmd: str) -> str:
    allowed = {"scan","boost","clean","fix","rollback","security","health"}
    c = cmd.lower().strip()
    return c if c in allowed else ""
