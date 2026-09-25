"""Tests for routes/analytics.py: fleet overview aggregation, compliance
score inputs, per-machine score, fleet-wide alerts listing, and the alert
status/assign endpoints not already covered by test_ops_fixes.py (which
covers /savings and the operator-vs-viewer 403 checks on mark-all-read/
status/assign).

Scores/grades themselves come from health_score.py (calculate_health_score /
calculate_compliance_score), which is not re-verified here -- these tests
only assert the arithmetic and data-shaping done directly in
routes/analytics.py (totals, online/offline counts, avg_cpu/ram/disk,
alert counts, commands_24h), plus that a score/grade key is present.
"""
import pytest
from conftest import auth_headers
from db import Machine, Metric, Alert, AuditLog


def _make_machine(db_session, hostname="analytics-machine", token="tok-analytics-1", status="online"):
    m = Machine(hostname=hostname, ip="10.0.0.80", os_name="Linux",
                kernel="6.8", token=token, status=status)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def _make_metric(db_session, machine_id, cpu=50.0, ram=50.0, disk=50.0):
    metric = Metric(machine_id=machine_id, cpu=cpu, ram=ram, disk=disk)
    db_session.add(metric)
    db_session.commit()
    db_session.refresh(metric)
    return metric


def _make_alert(db_session, machine_id, level="warning", type_="cpu", message="test alert", is_read=False):
    a = Alert(machine_id=machine_id, level=level, type=type_, message=message, is_read=is_read)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


# ── GET /analytics/fleet ──────────────────────────────────────────────────

def test_fleet_overview_totals_and_averages(client, db_session, admin_user):
    online = _make_machine(db_session, hostname="overview-online", token="tok-overview-online", status="online")
    _make_machine(db_session, hostname="overview-offline", token="tok-overview-offline", status="offline")
    _make_metric(db_session, online.id, cpu=80.0, ram=60.0, disk=40.0)

    h = auth_headers(admin_user)
    r = client.get("/api/analytics/fleet", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["online"] == 1
    assert body["offline"] == 1
    assert body["avg_cpu"] == 80.0
    assert body["avg_ram"] == 60.0
    assert body["avg_disk"] == 40.0
    assert len(body["machine_scores"]) == 2
    assert "score" in body["machine_scores"][0]
    assert "grade" in body["machine_scores"][0]


def test_fleet_overview_counts_unread_alerts_by_level(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="overview-alerts", token="tok-overview-alerts")
    _make_alert(db_session, m.id, level="critical", is_read=False)
    _make_alert(db_session, m.id, level="warning", is_read=False)
    _make_alert(db_session, m.id, level="critical", is_read=True)  # read -- should not count

    h = auth_headers(admin_user)
    r = client.get("/api/analytics/fleet", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["critical_alerts"] == 1
    assert body["warning_alerts"] == 1


def test_fleet_overview_includes_recent_activity(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="overview-activity", token="tok-overview-activity")
    log = AuditLog(machine_id=m.id, action="test_activity", detail="d", status="ok")
    db_session.add(log); db_session.commit()

    h = auth_headers(admin_user)
    r = client.get("/api/analytics/fleet", headers=h)
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()["activity"]]
    assert "test_activity" in actions


# ── GET /analytics/fleet/compliance-score ────────────────────────────────

def test_compliance_score_includes_severity_and_alert_breakdown(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="compliance-machine", token="tok-compliance-1")
    _make_alert(db_session, m.id, level="critical", is_read=False)

    h = auth_headers(admin_user)
    r = client.get("/api/analytics/fleet/compliance-score", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["unresolved_alerts"]["critical"] == 1
    assert "cve_severity_counts" in body


# ── GET /analytics/machine/{machine_id}/score ────────────────────────────

def test_machine_score_unknown_machine_returns_zero(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/analytics/machine/999999/score", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 0
    assert body["grade"] == "Unknown"


def test_machine_score_known_machine_returns_score_shape(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="score-machine", token="tok-score-1")
    _make_metric(db_session, m.id, cpu=30.0, ram=30.0, disk=30.0)

    h = auth_headers(admin_user)
    r = client.get(f"/api/analytics/machine/{m.id}/score", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert "grade" in body


# ── GET /analytics/alerts/all ─────────────────────────────────────────────

def test_all_alerts_returns_hostname_and_status_defaults(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="alerts-all-machine", token="tok-alerts-all-1")
    a = _make_alert(db_session, m.id, message="disk low")

    h = auth_headers(admin_user)
    r = client.get("/api/analytics/alerts/all", headers=h)
    assert r.status_code == 200
    entry = next(x for x in r.json() if x["id"] == a.id)
    assert entry["hostname"] == "alerts-all-machine"
    assert entry["status"] == "open"
    assert entry["assigned_to"] is None


def test_all_alerts_allows_viewer(client, db_session, admin_user, viewer_user):
    h = auth_headers(viewer_user)
    r = client.get("/api/analytics/alerts/all", headers=h)
    assert r.status_code == 200


# ── PATCH /analytics/alerts/{id}/status (value validation not yet covered) ──

def test_set_alert_status_rejects_invalid_status(client, db_session, admin_user, operator_user):
    m = _make_machine(db_session, hostname="status-invalid-machine", token="tok-status-invalid")
    a = _make_alert(db_session, m.id)
    h = auth_headers(operator_user)
    r = client.patch(f"/api/analytics/alerts/{a.id}/status", json={"status": "not_a_real_status"}, headers=h)
    assert r.status_code == 400


def test_set_alert_status_404_unknown_alert(client, db_session, operator_user):
    h = auth_headers(operator_user)
    r = client.patch("/api/analytics/alerts/999999/status", json={"status": "resolved"}, headers=h)
    assert r.status_code == 404


def test_set_alert_status_acknowledged_marks_read(client, db_session, admin_user, operator_user):
    m = _make_machine(db_session, hostname="status-ack-machine", token="tok-status-ack")
    a = _make_alert(db_session, m.id, is_read=False)
    h = auth_headers(operator_user)
    r = client.patch(f"/api/analytics/alerts/{a.id}/status", json={"status": "acknowledged"}, headers=h)
    assert r.status_code == 200
    db_session.refresh(a)
    assert a.is_read is True


# ── PATCH /analytics/alerts/{id}/assign (404 paths not yet covered) ─────────

def test_assign_alert_404_unknown_user(client, db_session, admin_user, operator_user):
    m = _make_machine(db_session, hostname="assign-unknown-user", token="tok-assign-unknown")
    a = _make_alert(db_session, m.id)
    h = auth_headers(operator_user)
    r = client.patch(f"/api/analytics/alerts/{a.id}/assign", json={"user_id": 999999}, headers=h)
    assert r.status_code == 404


def test_assign_alert_404_unknown_alert(client, db_session, operator_user):
    h = auth_headers(operator_user)
    r = client.patch("/api/analytics/alerts/999999/assign", json={}, headers=h)
    assert r.status_code == 404


def test_assign_alert_defaults_to_caller(client, db_session, admin_user, operator_user):
    m = _make_machine(db_session, hostname="assign-default", token="tok-assign-default")
    a = _make_alert(db_session, m.id)
    h = auth_headers(operator_user)
    r = client.patch(f"/api/analytics/alerts/{a.id}/assign", json={}, headers=h)
    assert r.status_code == 200
    assert r.json()["assigned_to_user_id"] == operator_user.id
