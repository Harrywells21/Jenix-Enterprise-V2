from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, User
from auth import (authenticate_user, create_token, hash_password,
                  get_current_user, require_admin, oauth2)
from security import blacklist_token, is_token_blacklisted, rate_limit_login

router = APIRouter(prefix="/auth", tags=["auth"])

class UserCreate(BaseModel):
    name:     str
    email:    str
    password: str
    role:     str = "viewer"

class UserOut(BaseModel):
    id:        int
    name:      str
    email:     str
    role:      str
    is_active: bool
    class Config:
        from_attributes = True

@router.post("/login")
def login(request: Request,
          form: OAuth2PasswordRequestForm = Depends(),
          db:   Session = Depends(get_db)):
    # Rate limit by IP + username so one account can't block another
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit_login(client_ip, form.username):
        raise HTTPException(status_code=429,
                            detail="Too many login attempts. Try again in 1 minute.")
    user = authenticate_user(form.username, form.password, db)
    if not user:
        raise HTTPException(status_code=401,
                            detail="Invalid email or password")
    token = create_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "token_type": "bearer",
            "role": user.role, "name": user.name}

@router.post("/logout")
def logout(token: str = Depends(oauth2)):
    blacklist_token(token)
    return {"ok": True, "message": "Logged out successfully"}

@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db),
               _:  User    = Depends(require_admin)):
    return db.query(User).all()

@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate,
                db:   Session = Depends(get_db),
                _:    User    = Depends(require_admin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400,
                            detail="Email already exists")
    user = User(name=body.name, email=body.email,
                password_hash=hash_password(body.password),
                role=body.role)
    db.add(user); db.commit(); db.refresh(user)
    return user

@router.patch("/users/{user_id}/deactivate")
def deactivate_user(user_id: int,
                    db: Session = Depends(get_db),
                    _:  User    = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"ok": True}

@router.patch("/users/{user_id}/role")
def change_role(user_id: int, role: str,
                db: Session = Depends(get_db),
                _:  User    = Depends(require_admin)):
    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    db.commit()
    return {"ok": True}
