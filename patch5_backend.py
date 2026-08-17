import sys

def patch(path, replacements):
    with open(path, "r") as f:
        content = f.read()
    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            print(f"FAILED on {path} [{label}]: found {count} occurrences (expected 1)")
            print("---- looking for ----")
            print(old)
            sys.exit(1)
        content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} OK ({len(replacements)} change(s))")

# ---- server/db.py ----
db_replacements = [
    (
'''SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# ── Models ─────────────────────────────────────────────────────────────────''',
'''SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# ── Passphrase hashing (shared by node action-passphrase feature) ──────────
from passlib.context import CryptContext
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_passphrase(raw: str) -> str:
    return _pwd_ctx.hash(raw)

def verify_passphrase(raw: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(raw, hashed)
    except Exception:
        return False

# ── Models ─────────────────────────────────────────────────────────────────''',
        "add passphrase hash/verify helpers"
    ),
    (
'''    token       = Column(String, unique=True, index=True, nullable=False)
    status      = Column(String, default="offline")   # online / offline / warning''',
'''    token       = Column(String, unique=True, index=True, nullable=False)
    status      = Column(String, default="offline")   # online / offline / warning
    action_passphrase_hash = Column(String, nullable=True)  # gates boost/clean/fix/rollback''',
        "add action_passphrase_hash column to Machine"
    ),
    (
'''def init_db():
    Base.metadata.create_all(bind=engine)
    _seed_admin()''',
'''def _migrate_schema():
    """Additive column migration for existing installs (create_all only handles new tables)."""
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(machines)").fetchall()]
        if "action_passphrase_hash" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN action_passphrase_hash VARCHAR")
            conn.commit()
            print("✅ Migrated: added machines.action_passphrase_hash")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_admin()''',
        "add schema migration for existing installs"
    ),
]
patch("server/db.py", db_replacements)

# ---- server/routes/agents.py ----
agents_replacements = [
    (
'''from db import get_db, Machine, AuditLog''',
'''from db import get_db, Machine, AuditLog, hash_passphrase''',
        "import hash_passphrase"
    ),
    (
'''# ── Audit log for machine ──────────────────────────────────────────────────''',
'''# ── Node action passphrase (gates boost/clean/fix/rollback) ────────────────
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

# ── Audit log for machine ──────────────────────────────────────────────────''',
        "add passphrase set/clear/status endpoints"
    ),
]
patch("server/routes/agents.py", agents_replacements)

# ---- server/routes/commands.py ----
commands_replacements = [
    (
'''ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}

class CommandRequest(BaseModel):
    type: str
    params: dict = {}''',
'''ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set

class CommandRequest(BaseModel):
    type: str
    params: dict = {}
    passphrase: str | None = None''',
        "add GATED set and passphrase field"
    ),
    (
'''    if m.status != "online":
        raise HTTPException(status_code=400, detail="Machine is offline")
    cmd = Command(machine_id=machine_id, user_id=current_user.id,''',
'''    if m.status != "online":
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
    cmd = Command(machine_id=machine_id, user_id=current_user.id,''',
        "verify passphrase before dispatch for gated commands"
    ),
]
patch("server/routes/commands.py", commands_replacements)

print("ALL BACKEND PATCHES APPLIED")
