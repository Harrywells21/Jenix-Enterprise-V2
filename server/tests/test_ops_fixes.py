"""Tests for the Sept 25 ops-decisions patch set:
(a) /api/analytics/savings figures are now configurable + labeled as estimates
(b) alert-mutation routes now require operator role, not just any authed user
(c) /api/settings/notifications/test no longer false-positives when nothing
    is actually configured on the running process, and saving settings now
    reports whether a restart is needed for them to take effect
"""
from passlib.context import CryptContext
from conftest import auth_headers
from db import User

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_user(db_session, email, role):
    u = User(name=role.title(), email=email,
             password_hash=_pwd_ctx.hash("pw123456"),
             role=role, is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_savings_returns_configurable_defaults_and_note(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/analytics/savings", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["hourly_rate"] == 45.0
    assert body["license_cost"] == 65000.0
    assert "note" in body and "estimate" in body["note"].lower()


def test_alert_mark_all_read_requires_operator_not_viewer(client, db_session, admin_user):
    viewer = _make_user(db_session, "viewer1@jenix.io", "viewer")
    h = auth_headers(viewer)
    r = client.post("/api/analytics/alerts/mark-all-read", headers=h)
    assert r.status_code == 403


def test_alert_mark_all_read_allows_operator(client, db_session, admin_user):
    operator = _make_user(db_session, "operator1@jenix.io", "operator")
    h = auth_headers(operator)
    r = client.post("/api/analytics/alerts/mark-all-read", headers=h)
    assert r.status_code == 200


def test_alert_status_change_requires_operator_not_viewer(client, db_session, admin_user):
    from db import Machine, Alert
    m = Machine(hostname="ops-fix-machine", ip="10.0.0.9", os_name="Linux",
                kernel="6.8", token="tok-ops-fix", status="online")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    a = Alert(machine_id=m.id, level="warning", type="cpu", message="test")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    viewer = _make_user(db_session, "viewer2@jenix.io", "viewer")
    h = auth_headers(viewer)
    r = client.patch(f"/api/analytics/alerts/{a.id}/status", json={"status": "acknowledged"}, headers=h)
    assert r.status_code == 403


def test_alert_assign_requires_operator_not_viewer(client, db_session, admin_user):
    from db import Machine, Alert
    m = Machine(hostname="ops-fix-machine-2", ip="10.0.0.10", os_name="Linux",
                kernel="6.8", token="tok-ops-fix-2", status="online")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    a = Alert(machine_id=m.id, level="warning", type="ram", message="test")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    viewer = _make_user(db_session, "viewer3@jenix.io", "viewer")
    h = auth_headers(viewer)
    r = client.patch(f"/api/analytics/alerts/{a.id}/assign", json={"user_id": admin_user.id}, headers=h)
    assert r.status_code == 403


def test_notify_test_slack_reports_false_when_not_configured(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/settings/notifications/test", json={"type": "slack"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "not active" in body["message"].lower() or "restart" in body["message"].lower()


def test_notify_test_teams_reports_false_when_not_configured(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/settings/notifications/test", json={"type": "teams"}, headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_notify_test_email_reports_false_when_not_configured(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/settings/notifications/test", json={"type": "email"}, headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_update_notify_reports_restart_required(client, db_session, admin_user, tmp_path, monkeypatch):
    # Isolate ENV_PATH so this NEVER touches the real server/.env (which also
    # holds SECRET_KEY) -- same isolation pattern as test_backup.py's
    # BACKUP_DIR and test_whitelabel.py's WHITELABEL_FILE.
    import routes.notify_settings as ns
    fake_env = tmp_path / ".env"
    fake_env.write_text("SECRET_KEY=unrelated-test-value\n")
    monkeypatch.setattr(ns, "ENV_PATH", str(fake_env))

    h = auth_headers(admin_user)
    r = client.post("/api/settings/notifications",
                    json={"slack_webhook": "https://hooks.slack.com/services/TEST/TEST/TEST"},
                    headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "restart_required" in body
    # the write landed in the isolated fake file, not the real one
    assert "SLACK_WEBHOOK=https://hooks.slack.com/services/TEST/TEST/TEST" in fake_env.read_text()
