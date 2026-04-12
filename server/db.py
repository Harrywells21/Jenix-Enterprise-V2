from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jenix.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

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
    last_seen   = Column(DateTime, default=datetime.utcnow)
    created_at  = Column(DateTime, default=datetime.utcnow)
    metrics     = relationship("Metric",   back_populates="machine", cascade="all, delete")
    commands    = relationship("Command",  back_populates="machine", cascade="all, delete")
    audit_logs  = relationship("AuditLog", back_populates="machine", cascade="all, delete")
    schedules   = relationship("Schedule", back_populates="machine", cascade="all, delete")
    reports     = relationship("Report",   back_populates="machine", cascade="all, delete")
    alerts      = relationship("Alert",    back_populates="machine", cascade="all, delete")


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
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    user_id    = Column(Integer, nullable=True)
    type       = Column(String, nullable=False)   # scan / boost / clean / fix / rollback
    status     = Column(String, default="pending") # pending / running / done / failed
    output     = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="commands")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=True)
    user_id    = Column(Integer, ForeignKey("users.id"),    nullable=True)
    action     = Column(String, nullable=False)
    detail     = Column(Text, default="")
    status     = Column(String, default="ok")   # ok / warning / critical
    timestamp  = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="audit_logs")
    user       = relationship("User",    back_populates="audit_logs")


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
    id         = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    filename   = Column(String, nullable=False)
    filepath   = Column(String, nullable=False)
    size_kb    = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    machine    = relationship("Machine", back_populates="reports")


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


def init_db():
    Base.metadata.create_all(bind=engine)
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
