from db import Machine, Metric, Alert
from tests.conftest import auth_headers


def make_machine(db_session, token="tok-met-1"):
    m = Machine(hostname="host-met", ip="10.0.0.30", os_name="linux",
                kernel="6.1", token=token, status="online")
    db_session.add(m); db_session.commit(); db_session.refresh(m)
    return m


def add_metric(db_session, machine_id, cpu=10.0, ram=20.0, disk=30.0):
    m = Metric(machine_id=machine_id, cpu=cpu, ram=ram, disk=disk,
               net_mb=1.0, disk_mb=2.0)
    db_session.add(m); db_session.commit()
    return m


def add_alert(db_session, machine_id, level="warning", type_="cpu",
              message="CPU high"):
    a = Alert(machine_id=machine_id, level=level, type=type_, message=message)
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    return a


# ── metrics ──────────────────────────────────────────────────────────────

def test_metrics_requires_auth(client, db_session):
    m = make_machine(db_session)
    r = client.get(f"/api/machines/{m.id}/metrics")
    assert r.status_code == 401


def test_metrics_returned_oldest_first(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_metric(db_session, m.id, cpu=1.0)
    add_metric(db_session, m.id, cpu=2.0)
    add_metric(db_session, m.id, cpu=3.0)
    r = client.get(f"/api/machines/{m.id}/metrics", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    cpus = [row["cpu"] for row in r.json()]
    # Real behavior: DB query orders desc (newest first) but the route
    # reverses the list before returning, so the API response is
    # chronological (oldest first) -- opposite of the raw query order.
    assert cpus == [1.0, 2.0, 3.0]


def test_metrics_empty_for_machine_with_none(client, db_session, viewer_user):
    m = make_machine(db_session)
    r = client.get(f"/api/machines/{m.id}/metrics", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == []


def test_latest_metric_no_data_returns_zeroed_defaults(client, db_session, viewer_user):
    m = make_machine(db_session)
    r = client.get(f"/api/machines/{m.id}/metrics/latest", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == {"cpu": 0, "ram": 0, "disk": 0, "net_mb": 0, "disk_mb": 0}


def test_latest_metric_returns_most_recent(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_metric(db_session, m.id, cpu=1.0)
    add_metric(db_session, m.id, cpu=99.0)
    r = client.get(f"/api/machines/{m.id}/metrics/latest", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json()["cpu"] == 99.0


# ── alerts ───────────────────────────────────────────────────────────────

def test_alerts_requires_auth(client, db_session):
    m = make_machine(db_session)
    r = client.get(f"/api/machines/{m.id}/alerts")
    assert r.status_code == 401


def test_alerts_scoped_to_machine(client, db_session, viewer_user):
    m1 = make_machine(db_session, token="tok-met-a")
    m2 = Machine(hostname="host-met-2", ip="10.0.0.31", token="tok-met-b", status="online")
    db_session.add(m2); db_session.commit(); db_session.refresh(m2)
    add_alert(db_session, m1.id, message="alert on m1")
    add_alert(db_session, m2.id, message="alert on m2")
    r = client.get(f"/api/machines/{m1.id}/alerts", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["message"] == "alert on m1"


def test_alert_starts_unread(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alert(db_session, m.id)
    r = client.get(f"/api/machines/{m.id}/alerts", headers=auth_headers(viewer_user))
    assert r.json()[0]["is_read"] is False


def test_mark_alert_read(client, db_session, viewer_user):
    m = make_machine(db_session)
    a = add_alert(db_session, m.id)
    r = client.patch(f"/api/machines/{m.id}/alerts/{a.id}/read",
                      headers=auth_headers(viewer_user))
    assert r.status_code == 200
    db_session.refresh(a)
    assert a.is_read is True


def test_mark_alert_read_unknown_id_still_returns_ok(client, db_session, viewer_user):
    # Real behavior: mark_read does "if alert:" and silently no-ops if not
    # found, still returning {"ok": True} -- no 404 for a bad alert_id.
    m = make_machine(db_session)
    r = client.patch(f"/api/machines/{m.id}/alerts/99999/read",
                      headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_mark_alert_read_ignores_machine_id_mismatch(client, db_session, viewer_user):
    # FLAGGED FINDING, not a bug fix: mark_read's query filters ONLY on
    # Alert.id ("db.query(Alert).filter(Alert.id == alert_id).first()") and
    # never checks that the alert's own machine_id matches the {machine_id}
    # in the URL path. This test documents that real, current behavior --
    # an alert belonging to a DIFFERENT machine than the one named in the
    # URL is still marked read successfully. Not silently patched here;
    # surfaced for the user's explicit sign-off per the standing rule that
    # unexpected route behavior isn't changed without confirmation.
    m1 = make_machine(db_session, token="tok-met-c")
    m2 = Machine(hostname="host-met-3", ip="10.0.0.32", token="tok-met-d", status="online")
    db_session.add(m2); db_session.commit(); db_session.refresh(m2)
    a = add_alert(db_session, m1.id, message="belongs to m1")
    # Note the mismatch: alert belongs to m1, but we PATCH via m2's URL.
    r = client.patch(f"/api/machines/{m2.id}/alerts/{a.id}/read",
                      headers=auth_headers(viewer_user))
    assert r.status_code == 200
    db_session.refresh(a)
    assert a.is_read is True  # documents the gap -- would fail if this were ever fixed
