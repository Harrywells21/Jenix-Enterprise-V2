"""Route tests for routes/uptime.py (mounted at /api/uptime). Any authed user.

Source-verified: uptime_pct is an ESTIMATE, not a measurement -- the route
charges a flat 5 minutes of downtime per offline Alert row inside the window
(total minutes = days * 24 * 60). These tests pin that formula so any change
to it is deliberate.
"""
from datetime import datetime, timedelta
from conftest import auth_headers
from db import Alert, Machine, Metric


def make_machine(db, token="tok-up-1", hostname="host-up"):
    m = Machine(hostname=hostname, ip="10.0.4.1", token=token, status="online")
    db.add(m); db.commit(); db.refresh(m)
    return m


def add_alerts(db, machine_id, n=1, type_="offline", when=None):
    for _ in range(n):
        db.add(Alert(machine_id=machine_id, type=type_, level="critical",
                     message=f"{type_} event", timestamp=when or datetime.utcnow()))
    db.commit()


def get_uptime(client, user, machine_id, query=""):
    return client.get(f"/api/uptime/{machine_id}{query}", headers=auth_headers(user))


# ---- per-machine ----------------------------------------------------------

def test_uptime_routes_require_auth(client):
    assert client.get("/api/uptime/1").status_code == 401
    assert client.get("/api/uptime/fleet/summary").status_code == 401


def test_uptime_no_incidents_is_100_percent(client, db_session, viewer_user):
    m = make_machine(db_session)
    before = datetime.utcnow().strftime("%Y-%m-%d")
    r = get_uptime(client, viewer_user, m.id)
    after = datetime.utcnow().strftime("%Y-%m-%d")
    assert r.status_code == 200
    b = r.json()
    assert (b["machine_id"], b["hostname"], b["current_status"]) == (m.id, "host-up", "online")
    assert (b["uptime_pct"], b["downtime_minutes"], b["incidents"]) == (100.0, 0, 0)
    assert (b["sla_target"], b["sla_met"], b["days_monitored"]) == (99.0, True, 30)
    assert len(b["daily"]) == 30
    assert b["daily"][0]["date"] in {before, after}
    assert isinstance(b["last_seen"], str)


def test_uptime_charges_five_minutes_per_offline_alert(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alerts(db_session, m.id, n=1)
    b = get_uptime(client, viewer_user, m.id).json()
    assert (b["incidents"], b["downtime_minutes"], b["uptime_pct"]) == (1, 5, 99.99)
    assert b["sla_met"] is True


def test_uptime_days_param_changes_window(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alerts(db_session, m.id, n=1)
    b = get_uptime(client, viewer_user, m.id, "?days=7").json()
    assert (b["days_monitored"], b["uptime_pct"], len(b["daily"])) == (7, 99.95, 7)


def test_uptime_daily_breakdown_capped_at_30_days(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alerts(db_session, m.id, n=1)
    b = get_uptime(client, viewer_user, m.id, "?days=60").json()
    assert (b["days_monitored"], b["uptime_pct"], len(b["daily"])) == (60, 99.99, 30)


def test_uptime_sla_breached_with_many_incidents(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alerts(db_session, m.id, n=90)
    b = get_uptime(client, viewer_user, m.id).json()
    assert (b["downtime_minutes"], b["uptime_pct"], b["sla_met"]) == (450, 98.96, False)


def test_uptime_counts_only_offline_alerts_for_this_machine(client, db_session, viewer_user):
    m1 = make_machine(db_session, token="tok-up-a")
    m2 = make_machine(db_session, token="tok-up-b", hostname="other")
    add_alerts(db_session, m1.id, n=3, type_="cpu")
    add_alerts(db_session, m2.id, n=2, type_="offline")
    b = get_uptime(client, viewer_user, m1.id).json()
    assert (b["incidents"], b["uptime_pct"]) == (0, 100.0)


def test_uptime_ignores_alerts_outside_window(client, db_session, viewer_user):
    m = make_machine(db_session)
    add_alerts(db_session, m.id, n=1, when=datetime.utcnow() - timedelta(days=40))
    assert get_uptime(client, viewer_user, m.id).json()["incidents"] == 0
    assert get_uptime(client, viewer_user, m.id, "?days=60").json()["incidents"] == 1


def test_uptime_todays_daily_status(client, db_session, viewer_user):
    up = make_machine(db_session, token="tok-up-1", hostname="h-up")
    down = make_machine(db_session, token="tok-up-2", hostname="h-down")
    idle = make_machine(db_session, token="tok-up-3", hostname="h-idle")
    db_session.add(Metric(machine_id=up.id, cpu=1.0, ram=1.0, disk=1.0))
    db_session.commit()
    add_alerts(db_session, down.id, n=1)
    t_up = get_uptime(client, viewer_user, up.id).json()["daily"][0]
    t_down = get_uptime(client, viewer_user, down.id).json()["daily"][0]
    t_idle = get_uptime(client, viewer_user, idle.id).json()["daily"][0]
    assert (t_up["status"], t_up["metric_count"], t_up["incidents"]) == ("up", 1, 0)
    assert (t_down["status"], t_down["incidents"]) == ("down", 1)
    assert t_idle["status"] == "unknown"


# ---- fleet summary --------------------------------------------------------

def test_fleet_summary_empty(client, viewer_user):
    r = client.get("/api/uptime/fleet/summary", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == {"fleet_uptime_pct": 100.0, "machines": [],
                        "sla_target": 99.0, "period_days": 30}


def test_fleet_summary_per_machine_and_average(client, db_session, viewer_user):
    a = make_machine(db_session, token="tok-up-a", hostname="quiet")
    b = make_machine(db_session, token="tok-up-b", hostname="noisy")
    add_alerts(db_session, b.id, n=4)
    body = client.get("/api/uptime/fleet/summary", headers=auth_headers(viewer_user)).json()
    by = {m["hostname"]: m for m in body["machines"]}
    assert (by["quiet"]["uptime_pct"], by["quiet"]["incidents"], by["quiet"]["sla_met"]) == (100.0, 0, True)
    assert (by["noisy"]["uptime_pct"], by["noisy"]["incidents"], by["noisy"]["sla_met"]) == (99.95, 4, True)
    assert by["quiet"]["machine_id"] == a.id and by["noisy"]["status"] == "online"
    assert body["fleet_uptime_pct"] == round(sum(m["uptime_pct"] for m in body["machines"]) / 2, 2)


def test_fleet_summary_flags_sla_breach_and_ignores_old_alerts(client, db_session, viewer_user):
    bad = make_machine(db_session, token="tok-up-a", hostname="bad")
    old = make_machine(db_session, token="tok-up-b", hostname="old")
    add_alerts(db_session, bad.id, n=90)
    add_alerts(db_session, old.id, n=5, when=datetime.utcnow() - timedelta(days=45))
    body = client.get("/api/uptime/fleet/summary", headers=auth_headers(viewer_user)).json()
    by = {m["hostname"]: m for m in body["machines"]}
    assert (by["bad"]["uptime_pct"], by["bad"]["sla_met"]) == (98.96, False)
    assert (by["old"]["incidents"], by["old"]["uptime_pct"]) == (0, 100.0)
