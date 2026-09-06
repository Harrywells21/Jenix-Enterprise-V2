from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os
import hashlib
import json
import datetime as dt_module
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jenix.db')}"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

from sqlalchemy import event

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
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

# ── Models ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, default="viewer")   # admin / operator / viewer
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    audit_logs    = relationship("AuditLog", back_populates="user")


class Machine(Base):
    __tablename__ = "machines"
    id          = Column(Integer, primary_key=True, index=True)
    hostname    = Column(String, nullable=False)
    ip          = Column(String, nullable=False)
    os_name     = Column(String, default="")
    kernel      = Column(String, default="")
    token       = Column(String, unique=True, index=True, nullable=False)
    status      = Column(String, default="offline")   # online / offline / warning
    action_passphrase_hash = Column(String, nullable=True)  # gates boost/clean/fix/rollback
    current_version   = Column(String, nullable=True)   # version string agent last reported
    available_version = Column(String, nullable=True)   # version staged/approved for this machine, if any
    upgrade_status     = Column(String, nullable=True)  # None / "pending" / "downloading" / "done" / "failed"
    checkpoint_status      = Column(String, nullable=True)  # None / "armed" / "restoring"
    checkpoint_snapshot_id = Column(String, nullable=True)  # id of the checkpoint currently armed on this machine, if any
    checkpoint_armed_at    = Column(DateTime, nullable=True)
    redirect_target_url    = Column(String, nullable=True)  # set by approve-with-redirect; agent told to reconnect elsewhere, then this row is deleted
    site_id     = Column(Integer, nullable=True)  # optional Site grouping, no enforced FK (matches redirect_target_url convention)
    last_risk_score = Column(Integer, nullable=True)  # risk score (0-100) from the most recent report generation
    last_risk_at    = Column(DateTime, nullable=True)  # timestamp of that scan, for delta display in next report
    last_seen   = Column(DateTime, default=datetime.utcnow)
    created_at  = Column(DateTime, default=datetime.utcnow)
    metrics     = relationship("Metric",   back_populates="machine", cascade="all, delete")
    commands    = relationship("Command",  back_populates="machine", cascade="all, delete")
    audit_logs  = relationship("AuditLog", back_populates="machine", cascade="all, delete")
    schedules   = relationship("Schedule", back_populates="machine", cascade="all, delete")
    reports     = relationship("Report",   back_populates="machine", cascade="all, delete")
    alerts      = relationship("Alert",    back_populates="machine", cascade="all, delete")
    cve_scans   = relationship("CveScan",  back_populates="machine", cascade="all, delete")


class Site(Base):
    __tablename__ = "sites"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Metric(Base):
    __tablename__ = "metrics"
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    cpu        = Column(Float, default=0.0)
    ram        = Column(Float, default=0.0)
    disk       = Column(Float, default=0.0)
    net_mb     = Column(Float, default=0.0)
    disk_mb    = Column(Float, default=0.0)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="metrics")


class Command(Base):
    __tablename__ = "commands"
    id          = Column(Integer, primary_key=True, index=True)
    machine_id  = Column(Integer, ForeignKey("machines.id"), nullable=False)
    user_id     = Column(Integer, nullable=True)
    type        = Column(String, nullable=False)   # scan / boost / clean / fix / rollback
    status      = Column(String, default="pending") # pending / running / done / failed
    output      = Column(Text, default="")
    snapshot_id = Column(String, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow)
    machine     = relationship("Machine", back_populates="commands")


class Snapshot(Base):
    __tablename__ = "snapshots"
    id         = Column(String, primary_key=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    reason     = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=True)
    user_id    = Column(Integer, ForeignKey("users.id"),    nullable=True)
    action     = Column(String, nullable=False)
    detail     = Column(Text, default="")
    status     = Column(String, default="ok")   # ok / warning / critical
    timestamp  = Column(DateTime, default=datetime.utcnow)
    content_hash = Column(String, nullable=True)  # SHA256, set at insert time via after_insert listener
    machine    = relationship("Machine", back_populates="audit_logs")
    user       = relationship("User",    back_populates="audit_logs")


def compute_audit_hash(log_id, machine_id, user_id, action, detail, status, timestamp) -> str:
    if isinstance(timestamp, str):
        try:
            ts = dt_module.datetime.fromisoformat(timestamp.replace(" ", "T", 1)).isoformat()
        except ValueError:
            ts = timestamp
    elif hasattr(timestamp, "isoformat"):
        ts = timestamp.isoformat()
    else:
        ts = str(timestamp)
    data = {"id": log_id, "machine_id": machine_id, "user_id": user_id,
            "action": action, "detail": detail, "status": status, "timestamp": ts}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


from sqlalchemy import event as _sa_event

@_sa_event.listens_for(AuditLog, "after_insert")
def _set_audit_content_hash(mapper, connection, target):
    h = compute_audit_hash(target.id, target.machine_id, target.user_id,
                            target.action, target.detail, target.status, target.timestamp)
    connection.execute(
        AuditLog.__table__.update().where(AuditLog.__table__.c.id == target.id).values(content_hash=h)
    )


class Schedule(Base):
    __tablename__ = "schedules"
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    scan_type  = Column(String, default="security")  # security / health / full
    frequency  = Column(String, default="daily")     # daily / weekly
    hour       = Column(Integer, default=2)          # 2am default
    is_active  = Column(Boolean, default=True)
    last_run   = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="schedules")


class Report(Base):
    __tablename__ = "reports"
    id           = Column(Integer, primary_key=True, index=True)
    machine_id   = Column(Integer, ForeignKey("machines.id"), nullable=True)  # null for fleet-wide reports
    machine_ids  = Column(String, nullable=True)  # comma-separated machine IDs, only set for fleet-wide reports
    report_type  = Column(String, default="single")  # "single" or "fleet"
    filename     = Column(String, nullable=False)
    filepath     = Column(String, nullable=False)
    size_kb      = Column(Float, default=0.0)
    created_at   = Column(DateTime, default=datetime.utcnow)
    machine      = relationship("Machine", back_populates="reports")


class CveScan(Base):
    __tablename__ = "cve_scans"
    id                   = Column(Integer, primary_key=True, index=True)
    machine_id           = Column(Integer, ForeignKey("machines.id"), nullable=False)
    triggered_by_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    triggered_by_name    = Column(String, default="System")
    scanned_at           = Column(DateTime, default=datetime.utcnow)
    packages_scanned     = Column(Integer, default=0)
    vulnerable_packages  = Column(Integer, default=0)
    total_vulns          = Column(Integer, default=0)
    critical             = Column(Integer, default=0)
    high                 = Column(Integer, default=0)
    risk_level           = Column(String, default="LOW")
    machine              = relationship("Machine", back_populates="cve_scans")
    findings             = relationship("CveFinding", back_populates="scan", cascade="all, delete")


class CveFinding(Base):
    __tablename__ = "cve_findings"
    id         = Column(Integer, primary_key=True, index=True)
    scan_id    = Column(Integer, ForeignKey("cve_scans.id"), nullable=False)
    package    = Column(String, nullable=False)
    version    = Column(String, default="")
    cve_id     = Column(String, nullable=False)
    summary    = Column(Text, default="")
    severity   = Column(String, default="UNKNOWN")
    url        = Column(String, default="")
    scan       = relationship("CveScan", back_populates="findings")


class Alert(Base):
    __tablename__ = "alerts"
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    level      = Column(String, default="warning")  # warning / critical
    type       = Column(String, nullable=False)      # cpu / ram / disk / offline / port
    message    = Column(Text, nullable=False)
    is_read    = Column(Boolean, default=False)
    timestamp  = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="alerts")


class License(Base):
    __tablename__ = "license"
    id           = Column(Integer, primary_key=True)
    key          = Column(String, unique=True, nullable=False)
    company_name = Column(String, nullable=False)
    max_nodes    = Column(Integer, default=-1)   # -1 = unlimited
    is_perpetual = Column(Boolean, default=True)
    expires_at   = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, default=datetime.utcnow)


# ── Helpers ────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_schema():
    """Additive column migration for existing installs (create_all only handles new tables)."""
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(machines)").fetchall()]
        if "action_passphrase_hash" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN action_passphrase_hash VARCHAR")
            conn.commit()
            print("✅ Migrated: added machines.action_passphrase_hash")

        for col in ("current_version", "available_version", "upgrade_status"):
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE machines ADD COLUMN {col} VARCHAR")
                conn.commit()
                print(f"✅ Migrated: added machines.{col}")
        for col in ("checkpoint_status", "checkpoint_snapshot_id"):
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE machines ADD COLUMN {col} VARCHAR")
                conn.commit()
                print(f"✅ Migrated: added machines.{col}")
        if "checkpoint_armed_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN checkpoint_armed_at DATETIME")
            conn.commit()
            print("✅ Migrated: added machines.checkpoint_armed_at")
        if "redirect_target_url" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN redirect_target_url VARCHAR")
            conn.commit()
            print("✅ Migrated: added machines.redirect_target_url")
        if "last_risk_score" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN last_risk_score INTEGER")
            conn.commit()
            print("✅ Migrated: added machines.last_risk_score")
        if "last_risk_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN last_risk_at DATETIME")
            conn.commit()
            print("✅ Migrated: added machines.last_risk_at")
        if "site_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN site_id INTEGER")
            conn.commit()
            print("✅ Migrated: added machines.site_id")

        audit_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(audit_logs)").fetchall()]
        if "content_hash" not in audit_cols:
            conn.exec_driver_sql("ALTER TABLE audit_logs ADD COLUMN content_hash VARCHAR")
            conn.commit()
            print("✅ Migrated: added audit_logs.content_hash")

        report_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(reports)").fetchall()]
        if "machine_ids" not in report_cols:
            conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN machine_ids VARCHAR")
            conn.commit()
            print("✅ Migrated: added reports.machine_ids")
        if "report_type" not in report_cols:
            conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN report_type VARCHAR DEFAULT 'single'")
            conn.commit()
            print("✅ Migrated: added reports.report_type")


def backfill_audit_hashes():
    """One-time (idempotent) backfill of content_hash for rows that predate the column."""
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT id, machine_id, user_id, action, detail, status, timestamp "
            "FROM audit_logs WHERE content_hash IS NULL"
        ).fetchall()
        for log_id, machine_id, user_id, action, detail, status, timestamp in rows:
            h = compute_audit_hash(log_id, machine_id, user_id, action, detail, status, timestamp)
            conn.exec_driver_sql("UPDATE audit_logs SET content_hash = ? WHERE id = ?", (h, log_id))
        conn.commit()
    if rows:
        print(f"✅ Backfilled content_hash for {len(rows)} audit_logs rows")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    backfill_audit_hashes()
    _seed_admin()


def _seed_admin():
    """Create default admin user if none exists."""
    from passlib.context import CryptContext
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    db = SessionLocal()
    try:
        if not db.query(User).first():
            admin = User(
                name          = "Admin",
                email         = os.getenv("ADMIN_EMAIL", "admin@jenix.io"),
                password_hash = pwd_ctx.hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                role          = "admin",
                is_active     = True,
            )
            db.add(admin)
            db.commit()
            print("✅ Default admin created:", admin.email)
    finally:
        db.close()


class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"
    id         = Column(Integer, primary_key=True)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
