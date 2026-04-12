"""
JENIX Security Hardening Module
- Rate limiting
- Token blacklist (logout)
- Security headers
- Input sanitization
"""
import os, time, hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Set
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Token Blacklist (invalidated tokens) ──────────────────────────────────
_blacklisted_tokens: Set[str] = set()

def blacklist_token(token: str):
    _blacklisted_tokens.add(hashlib.sha256(token.encode()).hexdigest())

def is_token_blacklisted(token: str) -> bool:
    return hashlib.sha256(token.encode()).hexdigest() in _blacklisted_tokens

# ── In-memory Rate Limiter ─────────────────────────────────────────────────
_rate_store = defaultdict(list)

def check_rate_limit(key: str, max_requests: int,
                     window_seconds: int) -> bool:
    """Returns True if allowed, False if rate limited."""
    now  = time.time()
    hits = _rate_store[key]
    # Remove old hits outside window
    _rate_store[key] = [h for h in hits if now - h < window_seconds]
    if len(_rate_store[key]) >= max_requests:
        return False
    _rate_store[key].append(now)
    return True

def rate_limit_login(ip: str) -> bool:
    """Max 10 login attempts per minute per IP."""
    return check_rate_limit(f"login:{ip}", 10, 60)

def rate_limit_api(ip: str) -> bool:
    """Max 300 requests per minute per IP."""
    return check_rate_limit(f"api:{ip}", 300, 60)

# ── Security Headers ───────────────────────────────────────────────────────
SECURITY_HEADERS = {
    "X-Content-Type-Options":    "nosniff",
    "X-Frame-Options":           "DENY",
    "X-XSS-Protection":          "1; mode=block",
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    "Permissions-Policy":        "geolocation=(), microphone=()",
    "Cache-Control":             "no-store",
}

# ── Input Sanitization ─────────────────────────────────────────────────────
def sanitize_string(s: str, max_len: int = 255) -> str:
    if not s:
        return ""
    # Remove null bytes and control chars
    s = s.replace("\x00", "").strip()
    # Limit length
    return s[:max_len]

def sanitize_command(cmd: str) -> str:
    allowed = {"scan", "boost", "clean", "fix", "rollback",
               "security", "health"}
    return cmd.lower().strip() if cmd.lower().strip() in allowed else ""
