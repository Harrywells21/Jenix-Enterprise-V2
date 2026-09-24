"""Route tests for routes/sites.py (mounted at /api/sites).

Written against the real source pasted 2026-09-24: list = any authed user,
create/delete = admin only, duplicate name -> 400, delete unassigns machines
(site_id -> None) rather than deleting them.
"""
from conftest import auth_headers
from db import Machine, Site


def make_machine(db, token, site_id=None, hostname="host-site"):
    m = Machine(hostname=hostname, ip="10.0.1.1", token=token,
                status="online", site_id=site_id)
    db.add(m); db.commit(); db.refresh(m)
    return m


def make_site(db, name):
    s = Site(name=name)
    db.add(s); db.commit(); db.refresh(s)
    return s


# ---- list -----------------------------------------------------------------

def test_list_sites_requires_auth(client):
    assert client.get("/api/sites").status_code == 401


def test_list_sites_empty(client, viewer_user):
    r = client.get("/api/sites", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == []


def test_list_sites_ordered_by_name_with_machine_counts(client, db_session, viewer_user):
    b = make_site(db_session, "Bravo")
    a = make_site(db_session, "Alpha")
    make_machine(db_session, "tok-site-1", site_id=a.id)
    make_machine(db_session, "tok-site-2", site_id=a.id)
    make_machine(db_session, "tok-site-3", site_id=b.id)
    make_machine(db_session, "tok-site-4", site_id=None)
    r = client.get("/api/sites", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == [
        {"id": a.id, "name": "Alpha", "machine_count": 2},
        {"id": b.id, "name": "Bravo", "machine_count": 1},
    ]


# ---- create ---------------------------------------------------------------

def test_create_site_as_admin(client, db_session, admin_user):
    r = client.post("/api/sites", json={"name": "HQ"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "HQ"
    assert db_session.query(Site).filter(Site.id == body["id"]).first() is not None


def test_create_site_forbidden_for_operator_and_viewer(client, db_session, operator_user, viewer_user):
    for u in (operator_user, viewer_user):
        r = client.post("/api/sites", json={"name": "Nope"}, headers=auth_headers(u))
        assert r.status_code == 403
    assert db_session.query(Site).count() == 0


def test_create_site_requires_auth(client):
    assert client.post("/api/sites", json={"name": "X"}).status_code == 401


def test_create_site_duplicate_name_rejected(client, db_session, admin_user):
    make_site(db_session, "HQ")
    r = client.post("/api/sites", json={"name": "HQ"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"]
    assert db_session.query(Site).count() == 1


def test_create_site_missing_name_is_422(client, admin_user):
    r = client.post("/api/sites", json={}, headers=auth_headers(admin_user))
    assert r.status_code == 422


# ---- delete ---------------------------------------------------------------

def test_delete_site_unassigns_machines_but_keeps_them(client, db_session, admin_user):
    s = make_site(db_session, "Temp")
    m = make_machine(db_session, "tok-site-5", site_id=s.id)
    r = client.delete(f"/api/sites/{s.id}", headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json() == {"status": "deleted"}
    assert db_session.query(Site).filter(Site.id == s.id).first() is None
    db_session.refresh(m)
    assert m.site_id is None


def test_delete_site_unknown_id_404(client, admin_user):
    r = client.delete("/api/sites/99999", headers=auth_headers(admin_user))
    assert r.status_code == 404


def test_delete_site_forbidden_for_non_admin(client, db_session, operator_user, viewer_user):
    s = make_site(db_session, "Keep")
    for u in (operator_user, viewer_user):
        r = client.delete(f"/api/sites/{s.id}", headers=auth_headers(u))
        assert r.status_code == 403
    assert db_session.query(Site).filter(Site.id == s.id).first() is not None
