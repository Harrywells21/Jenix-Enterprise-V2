"""
JENIX Enterprise — Database Models
SQLAlchemy ORM — works with SQLite (dev) and PostgreSQL (production)
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jenix.db")

# SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Users ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True)
    username      = Column(String, unique=True, nullable=False, index=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, default="viewer")   # admin / operator / viewer
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)
    tenant_id     = Column(String, ForeignKey("tenants.id"), nullable=True)


# ── Tenants (multi-tenant) ─────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"
    id         = Column(String, primary_key=True)
    name       = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active  = Column(Boolean, default=True)
    settings   = Column(JSON, default={})


# ── Nodes ─────────────────────────────────────────────────────────────────

class Node(Base):
    __tablename__ = "nodes"
    id            = Column(String, primary_key=True)
    name          = Column(String, nullable=False)
    os_type       = Column(String, default="Linux")   # Linux / Darwin / Windows
    os_pretty     = Column(String, nullable=True)
    hostname      = Column(String, nullable=True)
    ip_address    = Column(String, nullable=True)
    arch          = Column(String, nullable=True)
    is_online     = Column(Boolean, default=False)
    health_score  = Column(Integer, default=100)
    last_seen     = Column(DateTime, nullable=True)
    registered_at = Column(DateTime, default=datetime.utcnow)
    tenant_id     = Column(String, ForeignKey("tenants.id"), nullable=True)
    tags          = Column(JSON, default=[])
    extra_info    = Column(JSON, default={})

    metrics    = relationship("MetricSnapshot", back_populates="node",
                               cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="node",
                               cascade="all, delete-orphan")
    alerts     = relationship("Alert", back_populates="node",
                               cascade="all, delete-orphan")


# ── Metric snapshots ───────────────────────────────────────────────────────

class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    node_id      = Column(String, ForeignKey("nodes.id"), nullable=False, index=True)
    timestamp    = Column(DateTime, default=datetime.utcnow, index=True)
    cpu_percent  = Column(Float)
    ram_percent  = Column(Float)
    disk_percent = Column(Float)
    net_bytes_in = Column(Float, default=0)
    net_bytes_out= Column(Float, default=0)
    load_avg_1m  = Column(Float, nullable=True)
    raw          = Column(JSON, default={})   # full metrics blob

    node = relationship("Node", back_populates="metrics")


# ── Audit logs ─────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    node_id    = Column(String, ForeignKey("nodes.id"), nullable=True, index=True)
    user_id    = Column(String, ForeignKey("users.id"), nullable=True)
    timestamp  = Column(DateTime, default=datetime.utcnow, index=True)
    action     = Column(String, nullable=False)
    detail     = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    sha256     = Column(String, nullable=True)   # tamper-proof hash

    node = relationship("Node", back_populates="audit_logs")


# ── Alerts ─────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    node_id    = Column(String, ForeignKey("nodes.id"), nullable=True, index=True)
    timestamp  = Column(DateTime, default=datetime.utcnow, index=True)
    severity   = Column(String, default="warning")   # critical / warning / info
    type       = Column(String, nullable=False)       # cpu / ram / disk / offline
    message    = Column(Text)
    resolved   = Column(Boolean, default=False)
    resolved_at= Column(DateTime, nullable=True)

    node = relationship("Node", back_populates="alerts")


# ── Scan results (CVE) ─────────────────────────────────────────────────────

class ScanResult(Base):
    __tablename__ = "scan_results"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    node_id      = Column(String, ForeignKey("nodes.id"), nullable=False, index=True)
    scanned_at   = Column(DateTime, default=datetime.utcnow, index=True)
    total_pkgs   = Column(Integer, default=0)
    critical_cve = Column(Integer, default=0)
    high_cve     = Column(Integer, default=0)
    medium_cve   = Column(Integer, default=0)
    low_cve      = Column(Integer, default=0)
    findings     = Column(JSON, default=[])
    raw_packages = Column(JSON, default=[])


# ── Scheduled jobs ─────────────────────────────────────────────────────────

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    node_id     = Column(String, ForeignKey("nodes.id"), nullable=True)
    name        = Column(String, nullable=False)
    job_type    = Column(String, nullable=False)   # scan / boost / clean
    schedule    = Column(String, nullable=False)   # daily / weekly
    enabled     = Column(Boolean, default=True)
    last_run    = Column(DateTime, nullable=True)
    next_run    = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


# ── License ────────────────────────────────────────────────────────────────

class License(Base):
    __tablename__ = "licenses"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String, nullable=False)
    license_key  = Column(String, unique=True, nullable=False)
    node_limit   = Column(Integer, default=-1)   # -1 = unlimited
    issued_at    = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)
    features     = Column(JSON, default=[])


# ── Compliance reports ─────────────────────────────────────────────────────

class ComplianceReport(Base):
    __tablename__ = "compliance_reports"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    node_id     = Column(String, ForeignKey("nodes.id"), nullable=False)
    framework   = Column(String, default="CIS")   # CIS / SOC2 / HIPAA
    generated_at= Column(DateTime, default=datetime.utcnow)
    score       = Column(Integer, default=0)
    passed      = Column(Integer, default=0)
    failed      = Column(Integer, default=0)
    findings    = Column(JSON, default=[])


# ── Branding ───────────────────────────────────────────────────────────────

class BrandSettings(Base):
    __tablename__ = "brand_settings"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    company_name  = Column(String, default="JENIX Enterprise")
    logo_text     = Column(String, default="JENIX")
    primary_color = Column(String, default="#6366f1")
    sidebar_color = Column(String, default="#1e1e2e")
    updated_at    = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created.")
