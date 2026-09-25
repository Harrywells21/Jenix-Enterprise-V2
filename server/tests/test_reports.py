"""Tests for routes/reports.py: single-machine/fleet/audit PDF report
generation, CSV exports, listing, download (dual auth path), delete, and
the shared _compute_risk_score / _health_status helpers.

REPORTS_DIR is monkeypatched to tmp_path for every test in this file
(autouse fixture below) so nothing here ever writes into the real
server/reports/ directory -- same isolation pattern this session already
used for ENV_PATH (notify_settings.py) and BACKUP_DIR (backup.py).
"""
import pytest
from conftest import auth_headers
from db import Machine, Alert, AuditLog
from auth import create_token
from routes.reports import _compute_risk_score, _health_status


@pytest.fixture(autouse=True)
def _isolate_reports_dir(tmp_path, monkeypatch):
    import routes.reports as reports_module
    monkeypatch.setattr(reports_module, "REPORTS_DIR", str(tmp_path))


def _make_machine(db_session, hostname="test-machine", token="tok-reports-1"):
    m = Machine(hostname=hostname, ip="10.0.0.50", os_name="Linux",
                kernel="6.8", token=token, status="online")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def _make_alert(db_session, machine_id, level="warning", type_="cpu", message="CPU at 88.0%"):
    a = Alert(machine_id=machine_id, level=level, type=type_, message=message)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _make_audit_log(db_session, machine_id, action="test_action", detail="test detail"):
    l = AuditLog(machine_id=machine_id, action=action, detail=detail, status="ok")
    db_session.add(l)
    db_session.commit()
    db_session.refresh(l)
    return l


# ── _compute_risk_score / _health_status (pure functions, no client) ───────

def test_risk_score_zero_with_no_metrics_and_no_alerts():
    assert _compute_risk_score([], 0, 0) == 0


def test_risk_score_single_maxed_metric_cannot_reach_100():
    # Docstring's own claim: a single maxed-out metric alone can't reach 100
    # because each of CPU/RAM/Disk only contributes up to 30 of the 100 points.
    metrics = [{"cpu": 100, "ram": 0, "disk": 0}]
    score = _compute_risk_score(metrics, 0, 0)
    assert score == 30
    assert score < 100


def test_risk_score_alert_points_capped_at_10():
    # critical_count=100 would be 400 pts uncapped; alert contribution caps at 10.
    score = _compute_risk_score([], 100, 0)
    assert score == 10


def test_health_status_boundaries():
    assert _health_status(84.99) == "\u2713 OK"
    assert _health_status(85.0) == "\u26a0 WATCH"
    assert _health_status(94.99) == "\u26a0 WATCH"
    assert _health_status(95.0) == "\u26d4 CRITICAL"


# ── POST /reports/{machine_id} (single-machine PDF) ─────────────────────────

def test_generate_report_404_unknown_machine(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/reports/999999", headers=h)
    assert r.status_code == 404


def test_generate_report_success_creates_pdf_and_db_row(client, db_session, admin_user):
    m = _make_machine(db_session)
    _make_alert(db_session, m.id)
    _make_audit_log(db_session, m.id)
    h = auth_headers(admin_user)
    r = client.post(f"/api/reports/{m.id}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "report_id" in body
    assert body["filename"].endswith(".pdf")
    assert body["size_kb"] > 0

    listing = client.get("/api/reports", headers=h).json()
    assert any(x["id"] == body["report_id"] for x in listing)


def test_generate_report_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    m = _make_machine(db_session, hostname="viewer-blocked", token="tok-reports-viewer")
    h = auth_headers(viewer_user)
    r = client.post(f"/api/reports/{m.id}", headers=h)
    assert r.status_code == 403


def test_generate_report_allows_operator(client, db_session, admin_user, operator_user):
    m = _make_machine(db_session, hostname="operator-allowed", token="tok-reports-operator")
    h = auth_headers(operator_user)
    r = client.post(f"/api/reports/{m.id}", headers=h)
    assert r.status_code == 200


# ── POST /reports/fleet ──────────────────────────────────────────────────────

def test_fleet_report_default_includes_all_machines(client, db_session, admin_user):
    m1 = _make_machine(db_session, hostname="fleet-1", token="tok-fleet-1")
    m2 = _make_machine(db_session, hostname="fleet-2", token="tok-fleet-2")
    h = auth_headers(admin_user)
    r = client.post("/api/reports/fleet", json={}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body["machines_included"]) == {"fleet-1", "fleet-2"}


def test_fleet_report_filtered_by_machine_ids(client, db_session, admin_user):
    m1 = _make_machine(db_session, hostname="fleet-a", token="tok-fleet-a")
    m2 = _make_machine(db_session, hostname="fleet-b", token="tok-fleet-b")
    h = auth_headers(admin_user)
    r = client.post("/api/reports/fleet", json={"machine_ids": [m1.id]}, headers=h)
    assert r.status_code == 200
    assert r.json()["machines_included"] == ["fleet-a"]


def test_fleet_report_404_when_no_machines_match(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/reports/fleet", json={"machine_ids": [999999]}, headers=h)
    assert r.status_code == 404


def test_fleet_report_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    _make_machine(db_session, hostname="fleet-viewer-blocked", token="tok-fleet-viewer")
    h = auth_headers(viewer_user)
    r = client.post("/api/reports/fleet", json={}, headers=h)
    assert r.status_code == 403


# ── POST /reports/audit ──────────────────────────────────────────────────────

def test_audit_report_no_body_whole_floor(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="audit-floor", token="tok-audit-floor")
    _make_audit_log(db_session, m.id)
    h = auth_headers(admin_user)
    r = client.post("/api/reports/audit", headers=h)
    assert r.status_code == 200
    assert r.json()["scope"] == "floor"


def test_audit_report_scoped_to_machine_ids(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="audit-scoped", token="tok-audit-scoped")
    _make_audit_log(db_session, m.id)
    h = auth_headers(admin_user)
    r = client.post("/api/reports/audit", json={"machine_ids": [m.id]}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "machine"
    assert body["machines"] == ["audit-scoped"]


def test_audit_report_404_unknown_machine_id(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/reports/audit", json={"machine_ids": [999999]}, headers=h)
    assert r.status_code == 404


def test_audit_report_400_bad_iso_date(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/reports/audit", json={"start": "not-a-real-date"}, headers=h)
    assert r.status_code == 400


def test_audit_report_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    h = auth_headers(viewer_user)
    r = client.post("/api/reports/audit", headers=h)
    assert r.status_code == 403


# ── GET /reports/audit/csv and GET /reports/{machine_id}/alerts/csv ─────────

def test_export_audit_csv_returns_csv(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="audit-csv", token="tok-audit-csv")
    _make_audit_log(db_session, m.id)
    h = auth_headers(admin_user)
    r = client.get("/api/reports/audit/csv", headers=h)
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]


def test_export_alerts_csv_returns_csv(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="alerts-csv", token="tok-alerts-csv")
    _make_alert(db_session, m.id)
    h = auth_headers(admin_user)
    r = client.get(f"/api/reports/{m.id}/alerts/csv", headers=h)
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]


def test_export_alerts_csv_404_unknown_machine(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/reports/999999/alerts/csv", headers=h)
    assert r.status_code == 404


def test_csv_exports_allow_viewer(client, db_session, admin_user, viewer_user):
    # get_current_user only (not require_operator) -- any authenticated role.
    m = _make_machine(db_session, hostname="csv-viewer-ok", token="tok-csv-viewer")
    _make_alert(db_session, m.id)
    h = auth_headers(viewer_user)
    r = client.get(f"/api/reports/{m.id}/alerts/csv", headers=h)
    assert r.status_code == 200


# ── GET /reports (list) ──────────────────────────────────────────────────────

def test_list_reports_returns_created_reports(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="list-reports", token="tok-list-reports")
    h = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h).json()
    r = client.get("/api/reports", headers=h)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert created["report_id"] in ids


def test_list_reports_allows_viewer(client, db_session, admin_user, viewer_user):
    h = auth_headers(viewer_user)
    r = client.get("/api/reports", headers=h)
    assert r.status_code == 200


# ── GET /reports/{report_id}/download (dual auth path) ─────────────────────

def test_download_report_with_bearer_header(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="download-header", token="tok-download-header")
    h = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h).json()
    r = client.get(f"/api/reports/{created['report_id']}/download", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_download_report_with_query_token(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="download-query", token="tok-download-query")
    h = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h).json()
    raw_token = create_token({"sub": str(admin_user.id)})
    r = client.get(f"/api/reports/{created['report_id']}/download?token={raw_token}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_download_report_401_with_no_token(client, db_session, admin_user):
    m = _make_machine(db_session, hostname="download-none", token="tok-download-none")
    h = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h).json()
    r = client.get(f"/api/reports/{created['report_id']}/download")
    assert r.status_code == 401


def test_download_report_404_unknown_report_id(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/reports/999999/download", headers=h)
    assert r.status_code == 404


# ── DELETE /reports/{report_id} ──────────────────────────────────────────────

def test_delete_report_removes_file_and_row(client, db_session, admin_user):
    import os
    m = _make_machine(db_session, hostname="delete-me", token="tok-delete-me")
    h = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h).json()

    listing_before = client.get("/api/reports", headers=h).json()
    row = next(x for x in listing_before if x["id"] == created["report_id"])
    # Confirm the file really exists on disk before deleting, so the
    # assertion after delete actually proves removal, not just a 200.
    from db import Report
    db_row = db_session.query(Report).filter(Report.id == created["report_id"]).first()
    assert os.path.exists(db_row.filepath)

    r = client.delete(f"/api/reports/{created['report_id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert not os.path.exists(db_row.filepath)

    listing_after = client.get("/api/reports", headers=h).json()
    assert not any(x["id"] == created["report_id"] for x in listing_after)


def test_delete_report_404_unknown(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.delete("/api/reports/999999", headers=h)
    assert r.status_code == 404


def test_delete_report_requires_operator_not_viewer(client, db_session, admin_user, viewer_user):
    m = _make_machine(db_session, hostname="delete-viewer-blocked", token="tok-delete-viewer")
    h_admin = auth_headers(admin_user)
    created = client.post(f"/api/reports/{m.id}", headers=h_admin).json()
    h_viewer = auth_headers(viewer_user)
    r = client.delete(f"/api/reports/{created['report_id']}", headers=h_viewer)
    assert r.status_code == 403
