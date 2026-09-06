import os, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from db import get_db, User

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SECRET_KEY = os.getenv("SECRET_KEY", "jenix_secret")
ALGORITHM  = os.getenv("ALGORITHM",  "HS256")
EXPIRE_HRS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 24))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2  = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=EXPIRE_HRS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

WS_DASHBOARD_TOKEN_EXPIRE_SECONDS = 45

def create_ws_token(user_id: int) -> str:
    """Short-lived token (default 45s) for authenticating a dashboard
    WebSocket connection, which can't send an Authorization header like a
    normal request. Tagged with purpose=ws_dashboard so it can never be
    reused as a real bearer token against a regular endpoint even if it
    leaked (e.g. into a browser console log or URL bar history)."""
    payload = {
        "sub": str(user_id),
        "purpose": "ws_dashboard",
        "exp": datetime.utcnow() + timedelta(seconds=WS_DASHBOARD_TOKEN_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_ws_token(token: str) -> dict:
    """Validates a ws-dashboard token. Raises ValueError (not
    HTTPException -- this is called from raw WebSocket code, not a FastAPI
    route) on anything missing/invalid/expired/wrong-purpose, so callers
    can catch one exception type and close the socket with code=4001."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise ValueError("invalid or expired ws token")
    if payload.get("purpose") != "ws_dashboard":
        raise ValueError("wrong token purpose")
    return payload

def get_current_user(token: str = Depends(oauth2),
                     db: Session = Depends(get_db)) -> User:
    # Check blacklist first
    from security import is_token_blacklisted
    if is_token_blacklisted(token):
        raise HTTPException(status_code=401,
                            detail="Token has been revoked. Please login again.")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401,
                            detail="Invalid token payload")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401,
                            detail="User not found or inactive")
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403,
                            detail="Admin access required")
    return current_user

def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403,
                            detail="Operator access required")
    return current_user

def authenticate_user(email: str, password: str, db: Session):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user
