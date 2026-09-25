"""Tests for routes/fleet.py: fleet-wide command dispatch (ALLOWED/GATED/
SIGNED validation, per-machine send_command results, gated passphrase
skip) and GET /fleet/status counts.

send_command (ws.handler.send_command) is monkeypatched per test since no
real agent WebSocket is connected in the test process -- tests control
whether dispatch appears to succeed ("sent") or fail ("agent not
connected") independently of any real network state.
"""
import pytest
from conftest import auth_headers
from db import Machine, Command, AuditLog
import routes.fleet as fleet_module


async def _fake_send_command_ok(token, payload):
    return True


async def _fake_send_command_fail(token, payload):
    return False


def _make_machine(db_session, hostname="fleet-machine", token="tok-fleet-1", status="online"):
    m = Machine(hostname=hostname, ip="10.0.0.70", os_name="Linux",
                kernel="6.8", token=token, status=status)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


# ── POST /fleet/command ──────────────────────────────────────────────────

def test_fleet_command_unknown_type_is_400(client, db_session, operator_user):
    _make_machine(db_session)
    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command", json={"type": "not_a_real_type"}, headers=h)
    assert r.status_code == 400


def test_fleet_command_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    _make_machine(db_session, hostname="fleet-viewer-blocked", token="tok-fleet-viewer")
    h = auth_headers(viewer_user)
    r = client.post("/api/fleet/command", json={"type": "scan"}, headers=h)
    assert r.status_code == 403


def test_fleet_command_no_online_machines_is_400(client, db_session, operator_user):
    _make_machine(db_session, hostname="fleet-offline", token="tok-fleet-offline", status="offline")
    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command", json={"type": "scan"}, headers=h)
    assert r.status_code == 400


def test_fleet_command_exec_without_signature_is_400(client, db_session, operator_user):
    _make_machine(db_session, hostname="fleet-exec-nosig", token="tok-fleet-exec-nosig")
    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command",
                     json={"type": "exec", "script": "echo hi"}, headers=h)
    assert r.status_code == 400


def test_fleet_command_exec_with_signature_but_no_script_is_400(client, db_session, operator_user):
    _make_machine(db_session, hostname="fleet-exec-noscript", token="tok-fleet-exec-noscript")
    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command",
                     json={"type": "exec", "signature": "deadbeef"}, headers=h)
    assert r.status_code == 400


def test_fleet_command_dispatches_to_online_machines_only(client, db_session, admin_user, operator_user, monkeypatch):
    _make_machine(db_session, hostname="fleet-online-1", token="tok-fleet-online-1", status="online")
    _make_machine(db_session, hostname="fleet-offline-1", token="tok-fleet-offline-1", status="offline")
    monkeypatch.setattr(fleet_module, "send_command", _fake_send_command_ok)

    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command", json={"type": "scan"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["sent"] == 1
    assert body["failed"] == 0
    assert body["results"][0]["hostname"] == "fleet-online-1"


def test_fleet_command_filtered_by_machine_ids(client, db_session, admin_user, operator_user, monkeypatch):
    m1 = _make_machine(db_session, hostname="fleet-filter-a", token="tok-fleet-filter-a")
    _make_machine(db_session, hostname="fleet-filter-b", token="tok-fleet-filter-b")
    monkeypatch.setattr(fleet_module, "send_command", _fake_send_command_ok)

    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command",
                     json={"type": "scan", "machine_ids": [m1.id]}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["hostname"] == "fleet-filter-a"


def test_fleet_command_agent_not_connected_marks_failed(client, db_session, admin_user, operator_user, monkeypatch):
    _make_machine(db_session, hostname="fleet-agent-down", token="tok-fleet-agent-down")
    monkeypatch.setattr(fleet_module, "send_command", _fake_send_command_fail)

    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command", json={"type": "scan"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] == 0
    assert body["failed"] == 1
    assert body["results"][0]["status"] == "failed"


def test_fleet_command_creates_command_and_audit_rows(client, db_session, admin_user, operator_user, monkeypatch):
    m = _make_machine(db_session, hostname="fleet-audit-check", token="tok-fleet-audit-check")
    monkeypatch.setattr(fleet_module, "send_command", _fake_send_command_ok)

    h = auth_headers(operator_user)
    client.post("/api/fleet/command", json={"type": "boost"}, headers=h)

    cmd = db_session.query(Command).filter(Command.machine_id == m.id).first()
    assert cmd is not None
    assert cmd.type == "boost"
    assert cmd.status == "running"

    log = db_session.query(AuditLog).filter(
        AuditLog.machine_id == m.id, AuditLog.action == "fleet_boost").first()
    assert log is not None
    assert log.status == "ok"


def test_fleet_command_gated_type_skips_when_no_passphrase_set(client, db_session, admin_user, operator_user, monkeypatch):
    # GATED types only enforce a passphrase check if the machine HAS
    # action_passphrase_hash set -- with none set, the gate is a no-op
    # and dispatch proceeds normally (per fleet.py's own conditional).
    _make_machine(db_session, hostname="fleet-gated-nopass", token="tok-fleet-gated-nopass")
    monkeypatch.setattr(fleet_module, "send_command", _fake_send_command_ok)

    h = auth_headers(operator_user)
    r = client.post("/api/fleet/command", json={"type": "clean"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] == 1
    assert body["skipped_gated"] == []


# ── GET /fleet/status ─────────────────────────────────────────────────────

def test_fleet_status_counts_online_and_offline(client, db_session, operator_user):
    _make_machine(db_session, hostname="status-online-1", token="tok-status-online-1", status="online")
    _make_machine(db_session, hostname="status-online-2", token="tok-status-online-2", status="online")
    _make_machine(db_session, hostname="status-offline-1", token="tok-status-offline-1", status="offline")

    h = auth_headers(operator_user)
    r = client.get("/api/fleet/status", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["online"] == 2
    assert body["offline"] == 1


def test_fleet_status_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    h = auth_headers(viewer_user)
    r = client.get("/api/fleet/status", headers=h)
    assert r.status_code == 403
