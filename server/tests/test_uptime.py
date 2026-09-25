"""Tests for GET /api/uptime/{machine_id} and /api/uptime/fleet/summary.

Rewritten for the Sept 25 real-downtime-window redesign: downtime is now
measured from real DowntimeWindow rows (start/end timestamps written at the
actual WS state-flip points in ws/handler.py) instead of a flat 5-minutes-
per-offline-alert estimate. This file supersedes the old formula-snapshot
version, which locked in the pre-redesign flat-estimate behavior.
"""
from datetime import datetime, timedelta
from conftest import auth_headers
from db import Machine, DowntimeWindow


def _make_machine(db_session, hostname):
    m = Machine(hostname=hostname, ip="10.0.0.5", os_name="Linux",
                kernel="6.8", token=f"tok-{hostname}", status="online")
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def test_uptime_100pct_with_no_downtime_windows(client, db_session, admin_user):
    m = _make_machine(db_session, "clean-machine")
    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=30", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["uptime_pct"] == 100.0
    assert body["downtime_minutes"] == 0
    assert body["incidents"] == 0
    assert body["sla_met"] is True


def test_uptime_reflects_real_closed_downtime_window_duration(client, db_session, admin_user):
    m = _make_machine(db_session, "downtime-machine")
    now = datetime.utcnow()
    db_session.add(DowntimeWindow(
        machine_id=m.id,
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=1),
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=30", headers=h)
    body = r.json()
    assert body["incidents"] == 1
    assert body["downtime_minutes"] == 60.0
    total_minutes = 30 * 24 * 60
    expected_pct = round((total_minutes - 60.0) / total_minutes * 100, 2)
    assert body["uptime_pct"] == expected_pct


def test_uptime_counts_still_open_window_up_to_now(client, db_session, admin_user):
    m = _make_machine(db_session, "still-down-machine")
    now = datetime.utcnow()
    db_session.add(DowntimeWindow(
        machine_id=m.id,
        started_at=now - timedelta(minutes=30),
        ended_at=None,
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=30", headers=h)
    body = r.json()
    assert body["incidents"] == 1
    assert 29.0 <= body["downtime_minutes"] <= 31.0


def test_uptime_window_outside_requested_days_is_excluded(client, db_session, admin_user):
    m = _make_machine(db_session, "old-window-machine")
    now = datetime.utcnow()
    db_session.add(DowntimeWindow(
        machine_id=m.id,
        started_at=now - timedelta(days=40),
        ended_at=now - timedelta(days=39),
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=30", headers=h)
    body = r.json()
    assert body["downtime_minutes"] == 0
    assert body["incidents"] == 0


def test_uptime_window_straddling_range_boundary_is_clipped(client, db_session, admin_user):
    m = _make_machine(db_session, "straddling-machine")
    now = datetime.utcnow()
    since_30d = now - timedelta(days=30)
    db_session.add(DowntimeWindow(
        machine_id=m.id,
        started_at=since_30d - timedelta(hours=2),
        ended_at=since_30d + timedelta(hours=1),
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=30", headers=h)
    body = r.json()
    assert body["downtime_minutes"] == 60.0
    assert body["incidents"] == 1


def test_uptime_machine_not_found(client, db_session, admin_user):
    h = auth_headers(admin_user)
    r = client.get("/api/uptime/999999", headers=h)
    assert r.status_code == 200
    assert r.json() == {"error": "Machine not found"}


def test_uptime_daily_breakdown_marks_down_day_correctly(client, db_session, admin_user):
    m = _make_machine(db_session, "daily-machine")
    now = datetime.utcnow()
    # anchored minutes-before-now (not hours) so it can never cross a UTC
    # day boundary and land on "yesterday" depending on wall-clock time
    window_end   = now - timedelta(minutes=1)
    window_start = window_end - timedelta(minutes=2)
    db_session.add(DowntimeWindow(
        machine_id=m.id,
        started_at=window_start,
        ended_at=window_end,
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get(f"/api/uptime/{m.id}?days=7", headers=h)
    body = r.json()
    today = next(d for d in body["daily"] if d["date"] == now.strftime("%Y-%m-%d"))
    assert today["status"] == "down"
    assert today["incidents"] == 1


def test_fleet_uptime_summary_shape_and_values(client, db_session, admin_user):
    m1 = _make_machine(db_session, "fleet-clean")
    m2 = _make_machine(db_session, "fleet-down")
    now = datetime.utcnow()
    db_session.add(DowntimeWindow(
        machine_id=m2.id,
        started_at=now - timedelta(hours=1),
        ended_at=now,
    ))
    db_session.commit()

    h = auth_headers(admin_user)
    r = client.get("/api/uptime/fleet/summary", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["sla_target"] == 99.0
    assert body["period_days"] == 30
    by_host = {row["hostname"]: row for row in body["machines"]}
    assert by_host["fleet-clean"]["uptime_pct"] == 100.0
    assert by_host["fleet-down"]["incidents"] == 1
    assert by_host["fleet-down"]["uptime_pct"] < 100.0
