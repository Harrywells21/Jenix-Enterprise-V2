"""Tests for routes/audit.py: tamper-evident audit log listing, per-log
hash verification (including the None-stored-hash and tampered-hash
paths), and the CSV export's dual auth path.

AuditLog rows get their content_hash populated automatically by a
SQLAlchemy after_insert hook (see db.py) -- so most tests here get a real
computed hash for free. The "no stored hash" and "tampered" cases are
simulated with a direct UPDATE after insert, since the hook always runs
on a normal insert.
"""
import pytest
from conftest import auth_headers
from db import AuditLog
from auth import create_token


def _make_log(db_session, machine_id=None, action="test_action", detail="test detail", status="ok"):
    log = AuditLog(machine_id=machine_id, action=action, detail=detail, status=status)
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


# ── GET /audit/logs ───────────────────────────────────────────────────────

def test_get_logs_returns_entries_with_hash_fields(client, db_session, admin_user):
    log = _make_log(db_session, action="login")
    h = auth_headers(admin_user)
    r = client.get("/api/audit/logs", headers=h)
    assert r.status_code == 200
    body = r.json()
    entry = next(x for x in body if x["id"] == log.id)
    assert entry["action"] == "login"
    assert entry["full_hash"]
    assert entry["hash"] == entry["full_hash"][:16] + "..."


def test_get_logs_allows_viewer(client, db_session, admin_user, viewer_user):
    _make_log(db_session)
    h = auth_headers(viewer_user)
    r = client.get("/api/audit/logs", headers=h)
    assert r.status_code == 200


def test_get_logs_respects_limit(client, db_session, admin_user):
    for i in range(5):
        _make_log(db_session, action=f"action-{i}")
    h = auth_headers(admin_user)
    r = client.get("/api/audit/logs?limit=2", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── GET /audit/logs/verify/{log_id} ──────────────────────────────────────

def test_verify_log_not_found(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/audit/logs/verify/999999", headers=h)
    assert r.status_code == 200
    assert r.json()["verified"] is False


def test_verify_log_matches_real_computed_hash(client, db_session, admin_user):
    log = _make_log(db_session, action="verify-me")
    h = auth_headers(admin_user)
    r = client.get(f"/api/audit/logs/verify/{log.id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["hash"] == body["stored_hash"]


def test_verify_log_none_stored_hash_returns_none(client, db_session, admin_user):
    log = _make_log(db_session, action="legacy-no-hash")
    db_session.query(AuditLog).filter(AuditLog.id == log.id).update({"content_hash": None})
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/audit/logs/verify/{log.id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is None
    assert "error" in body


def test_verify_log_detects_tampering(client, db_session, admin_user):
    log = _make_log(db_session, action="tamper-me", detail="original detail")
    db_session.query(AuditLog).filter(AuditLog.id == log.id).update({"content_hash": "0" * 64})
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/audit/logs/verify/{log.id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is False
    assert body["stored_hash"] == "0" * 64
    assert body["hash"] != body["stored_hash"]


# ── GET /audit/logs/export ───────────────────────────────────────────────

def test_export_csv_with_bearer_header(client, db_session, admin_user):
    _make_log(db_session, action="export-me")
    h = auth_headers(admin_user)
    r = client.get("/api/audit/logs/export", headers=h)
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]
    assert "ID,Timestamp,Machine,Action,Detail,Status,SHA256 Hash" in r.text


def test_export_csv_with_query_token(client, db_session, admin_user):
    _make_log(db_session, action="export-query")
    token = create_token({"sub": str(admin_user.id)})
    r = client.get(f"/api/audit/logs/export?token={token}")
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]


def test_export_csv_401_with_no_token(client, db_session):
    r = client.get("/api/audit/logs/export")
    assert r.status_code == 401
