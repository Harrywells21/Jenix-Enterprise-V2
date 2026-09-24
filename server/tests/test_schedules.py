"""Route tests for routes/schedules.py (mounted at /api/schedules).

Written against the real source pasted 2026-09-24: list = any authed user,
create/delete/toggle = operator or admin. routes.schedules imports
add_schedule/remove_schedule BY NAME from scheduler, so they are patched on
routes.schedules (the real APScheduler singleton is never touched).
"""
import pytest
from conftest import auth_headers
from db import Machine, Schedule
import routes.schedules as sched_routes


@pytest.fixture(autouse=True)
def fake_scheduler(monkeypatch):
    calls = {"add": [], "remove": []}
    monkeypatch.setattr(sched_routes, "add_schedule",
                        lambda s: calls["add"].append(s.id))
    monkeypatch.setattr(sched_routes, "remove_schedule",
                        lambda sid: calls["remove"].append(sid))
    return calls


def make_machine(db, token="tok-sch-1"):
    m = Machine(hostname="host-sch", ip="10.0.2.1", token=token, status="online")
    db.add(m); db.commit(); db.refresh(m)
    return m


def make_schedule(db, machine_id, **kw):
    s = Schedule(machine_id=machine_id, **kw)
    db.add(s); db.commit(); db.refresh(s)
    return s


# ---- list -----------------------------------------------------------------

def test_list_schedules_requires_auth(client):
    assert client.get("/api/schedules").status_code == 401


def test_list_schedules_viewer_can_read(client, db_session, viewer_user):
    m = make_machine(db_session)
    s = make_schedule(db_session, m.id, scan_type="health", frequency="weekly", hour=4)
    r = client.get("/api/schedules", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == [{"id": s.id, "machine_id": m.id, "scan_type": "health",
                         "frequency": "weekly", "hour": 4, "is_active": True}]


# ---- create ---------------------------------------------------------------

def test_create_schedule_defaults(client, db_session, operator_user, fake_scheduler):
    m = make_machine(db_session)
    r = client.post("/api/schedules", json={"machine_id": m.id},
                    headers=auth_headers(operator_user))
    assert r.status_code == 200
    body = r.json()
    assert (body["scan_type"], body["frequency"], body["hour"], body["is_active"]) == \
           ("security", "daily", 2, True)
    assert fake_scheduler["add"] == [body["id"]]


def test_create_schedule_custom_fields(client, db_session, admin_user):
    m = make_machine(db_session)
    r = client.post("/api/schedules",
                    json={"machine_id": m.id, "scan_type": "full",
                          "frequency": "weekly", "hour": 23},
                    headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json()["scan_type"] == "full" and r.json()["hour"] == 23


def test_create_schedule_unknown_machine_404_and_not_scheduled(client, operator_user, fake_scheduler):
    r = client.post("/api/schedules", json={"machine_id": 99999},
                    headers=auth_headers(operator_user))
    assert r.status_code == 404
    assert fake_scheduler["add"] == []


def test_create_schedule_forbidden_for_viewer(client, db_session, viewer_user, fake_scheduler):
    m = make_machine(db_session)
    r = client.post("/api/schedules", json={"machine_id": m.id},
                    headers=auth_headers(viewer_user))
    assert r.status_code == 403
    assert db_session.query(Schedule).count() == 0
    assert fake_scheduler["add"] == []


# ---- delete ---------------------------------------------------------------

def test_delete_schedule(client, db_session, operator_user, fake_scheduler):
    m = make_machine(db_session)
    s = make_schedule(db_session, m.id)
    sid = s.id
    r = client.delete(f"/api/schedules/{sid}", headers=auth_headers(operator_user))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert db_session.query(Schedule).filter(Schedule.id == sid).first() is None
    assert fake_scheduler["remove"] == [sid]


def test_delete_schedule_unknown_404(client, operator_user, fake_scheduler):
    r = client.delete("/api/schedules/99999", headers=auth_headers(operator_user))
    assert r.status_code == 404
    assert fake_scheduler["remove"] == []


def test_delete_schedule_forbidden_for_viewer(client, db_session, viewer_user):
    m = make_machine(db_session)
    s = make_schedule(db_session, m.id)
    r = client.delete(f"/api/schedules/{s.id}", headers=auth_headers(viewer_user))
    assert r.status_code == 403
    assert db_session.query(Schedule).count() == 1


# ---- toggle ---------------------------------------------------------------

def test_toggle_schedule_off_then_on(client, db_session, operator_user, fake_scheduler):
    m = make_machine(db_session)
    s = make_schedule(db_session, m.id)
    h = auth_headers(operator_user)
    r1 = client.patch(f"/api/schedules/{s.id}/toggle", headers=h)
    assert r1.status_code == 200 and r1.json() == {"ok": True, "is_active": False}
    assert fake_scheduler["remove"] == [s.id] and fake_scheduler["add"] == []
    r2 = client.patch(f"/api/schedules/{s.id}/toggle", headers=h)
    assert r2.json() == {"ok": True, "is_active": True}
    assert fake_scheduler["add"] == [s.id]
    db_session.refresh(s)
    assert s.is_active is True


def test_toggle_schedule_unknown_404(client, operator_user):
    r = client.patch("/api/schedules/99999/toggle", headers=auth_headers(operator_user))
    assert r.status_code == 404


def test_toggle_schedule_forbidden_for_viewer(client, db_session, viewer_user):
    m = make_machine(db_session)
    s = make_schedule(db_session, m.id)
    r = client.patch(f"/api/schedules/{s.id}/toggle", headers=auth_headers(viewer_user))
    assert r.status_code == 403
    db_session.refresh(s)
    assert s.is_active is True
