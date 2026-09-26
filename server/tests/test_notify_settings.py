"""
Tests for server/routes/notify_settings.py.

No DB model backs this route -- it reads/writes an .env file directly
and gates on require_admin. We redirect ENV_PATH to a tmp file per test
and monkeypatch the notifications/alerting module attributes that the
route checks for its "restart_required" / already-active logic.
"""
import pytest
from routes import notify_settings as ns_module
from conftest import auth_headers
import notifications
import alerting


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(ns_module, "ENV_PATH", str(path))
    return path


def test_get_notify_defaults_when_no_env_file(client, admin_user, env_file):
    resp = client.get("/api/settings/notifications", headers=auth_headers(admin_user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["slack_webhook"] == ""
    assert body["smtp_port"] == 587
    assert body["smtp_configured"] is False
    assert body["slack_configured"] is False
    assert body["teams_configured"] is False


def test_get_notify_requires_admin(client, viewer_user, env_file):
    resp = client.get("/api/settings/notifications", headers=auth_headers(viewer_user))
    assert resp.status_code == 403


def test_update_notify_writes_env_file(client, admin_user, env_file):
    payload = {
        "slack_webhook": "https://hooks.slack.com/x",
        "teams_webhook": "",
        "alert_email": "ops@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
        "smtp_user": "user@example.com",
        "smtp_pass": "",
    }
    resp = client.post("/api/settings/notifications", json=payload, headers=auth_headers(admin_user))
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    contents = env_file.read_text()
    assert "SLACK_WEBHOOK=https://hooks.slack.com/x" in contents
    assert "SMTP_PORT=2525" in contents
    assert "SMTP_PASS=" not in contents


def test_update_notify_preserves_smtp_pass_when_blank(client, admin_user, env_file):
    env_file.write_text("SMTP_PASS=existing-secret\nSLACK_WEBHOOK=old\n")
    payload = {
        "slack_webhook": "new-hook", "teams_webhook": "", "alert_email": "",
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }
    client.post("/api/settings/notifications", json=payload, headers=auth_headers(admin_user))
    contents = env_file.read_text()
    assert "SMTP_PASS=existing-secret" in contents
    assert "SLACK_WEBHOOK=new-hook" in contents


def test_update_notify_flags_restart_required_when_live_mismatch(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "SLACK_WEBHOOK", "")
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK", "")
    monkeypatch.setattr(alerting, "ALERT_EMAIL", "")
    monkeypatch.setattr(alerting, "SMTP_HOST", "")
    monkeypatch.setattr(alerting, "SMTP_PORT", 587)
    monkeypatch.setattr(alerting, "SMTP_USER", "")
    monkeypatch.setattr(alerting, "SMTP_PASS", "")

    payload = {
        "slack_webhook": "https://hooks.slack.com/new",
        "teams_webhook": "", "alert_email": "", "smtp_host": "",
        "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }
    resp = client.post("/api/settings/notifications", json=payload, headers=auth_headers(admin_user))
    assert resp.json()["restart_required"] is True


def test_update_notify_no_restart_needed_when_already_live(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "SLACK_WEBHOOK", "same-hook")
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK", "")
    monkeypatch.setattr(alerting, "ALERT_EMAIL", "")
    monkeypatch.setattr(alerting, "SMTP_HOST", "")
    monkeypatch.setattr(alerting, "SMTP_PORT", 587)
    monkeypatch.setattr(alerting, "SMTP_USER", "")
    monkeypatch.setattr(alerting, "SMTP_PASS", "")

    payload = {
        "slack_webhook": "same-hook", "teams_webhook": "", "alert_email": "",
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
    }
    resp = client.post("/api/settings/notifications", json=payload, headers=auth_headers(admin_user))
    assert resp.json()["restart_required"] is False


def test_test_notification_slack_not_configured(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "SLACK_WEBHOOK", "")
    resp = client.post("/api/settings/notifications/test", json={"type": "slack"}, headers=auth_headers(admin_user))
    body = resp.json()
    assert body["ok"] is False
    assert "not active" in body["message"]


def test_test_notification_slack_configured_calls_notify(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "SLACK_WEBHOOK", "https://hooks.slack.com/x")
    called = {}
    def fake_notify_slack(title, msg, level):
        called["hit"] = (title, msg, level)
    monkeypatch.setattr(notifications, "notify_slack", fake_notify_slack)

    resp = client.post("/api/settings/notifications/test", json={"type": "slack"}, headers=auth_headers(admin_user))
    assert resp.json()["ok"] is True
    assert called["hit"][0] == "JENIX Test Notification"


def test_test_notification_teams_not_configured(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "TEAMS_WEBHOOK", "")
    resp = client.post("/api/settings/notifications/test", json={"type": "teams"}, headers=auth_headers(admin_user))
    assert resp.json()["ok"] is False


def test_test_notification_email_not_fully_configured(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(alerting, "SMTP_USER", "")
    monkeypatch.setattr(alerting, "SMTP_PASS", "")
    monkeypatch.setattr(alerting, "ALERT_EMAIL", "")
    resp = client.post("/api/settings/notifications/test", json={"type": "email"}, headers=auth_headers(admin_user))
    assert resp.json()["ok"] is False


def test_test_notification_email_configured_calls_send(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(alerting, "SMTP_USER", "u")
    monkeypatch.setattr(alerting, "SMTP_PASS", "p")
    monkeypatch.setattr(alerting, "ALERT_EMAIL", "ops@example.com")
    called = {}
    def fake_send(subject, html):
        called["hit"] = True
    monkeypatch.setattr(alerting, "send_alert_email", fake_send)

    resp = client.post("/api/settings/notifications/test", json={"type": "email"}, headers=auth_headers(admin_user))
    assert resp.json()["ok"] is True
    assert called["hit"] is True


def test_test_notification_unknown_type(client, admin_user, env_file):
    resp = client.post("/api/settings/notifications/test", json={"type": "carrier-pigeon"}, headers=auth_headers(admin_user))
    body = resp.json()
    assert body["ok"] is False
    assert "Unknown notification type" in body["message"]


def test_test_notification_exception_is_caught(client, admin_user, env_file, monkeypatch):
    monkeypatch.setattr(notifications, "SLACK_WEBHOOK", "https://hooks.slack.com/x")
    def boom(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(notifications, "notify_slack", boom)

    resp = client.post("/api/settings/notifications/test", json={"type": "slack"}, headers=auth_headers(admin_user))
    body = resp.json()
    assert body["ok"] is False
    assert "network down" in body["message"]
