"""Route tests for routes/license.py (mounted at /api/license). Admin-only.

routes.license imports validate_license/generate_license BY NAME from the
top-level license module, so they are patched on routes.license. These tests
cover the ROUTE logic (node-limit gate, replace-old-license, response shapes,
auth), not the key format itself.
"""
from conftest import auth_headers
from db import License, Machine
import routes.license as lic_routes


def fake_valid(company="Acme", max_nodes=5, perpetual=True):
    return lambda key: {"valid": True, "company": company,
                        "max_nodes": max_nodes, "perpetual": perpetual,
                        "issued_at": "2026-09-24T00:00:00"}


def fake_invalid(error="Invalid signature"):
    return lambda key: {"valid": False, "error": error}


def add_machines(db, n):
    for i in range(n):
        db.add(Machine(hostname=f"h{i}", ip=f"10.0.3.{i}", token=f"tok-lic-{i}",
                       status="online"))
    db.commit()


def add_license(db, key="JENIX-ABCDEFGHIJKLMNOPQRSTUVWXYZ-1234", **kw):
    row = License(key=key, company_name=kw.get("company_name", "Acme"),
                  max_nodes=kw.get("max_nodes", 5), is_perpetual=True)
    db.add(row); db.commit(); db.refresh(row)
    return row


# ---- auth (every route is admin-only) -------------------------------------

def test_license_routes_require_auth(client):
    assert client.get("/api/license").status_code == 401
    assert client.post("/api/license/activate", json={"key": "k"}).status_code == 401
    assert client.post("/api/license/generate", json={"company_name": "A"}).status_code == 401
    assert client.delete("/api/license").status_code == 401


def test_license_routes_forbidden_for_operator_and_viewer(client, operator_user, viewer_user):
    for u in (operator_user, viewer_user):
        h = auth_headers(u)
        assert client.get("/api/license", headers=h).status_code == 403
        assert client.post("/api/license/activate", json={"key": "k"}, headers=h).status_code == 403
        assert client.post("/api/license/generate", json={"company_name": "A"}, headers=h).status_code == 403
        assert client.delete("/api/license", headers=h).status_code == 403


# ---- get ------------------------------------------------------------------

def test_get_license_when_none(client, admin_user):
    r = client.get("/api/license", headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json() == {"activated": False, "message": "No license activated"}


def test_get_license_when_activated_truncates_key(client, db_session, admin_user):
    row = add_license(db_session)
    r = client.get("/api/license", headers=auth_headers(admin_user))
    body = r.json()
    assert r.status_code == 200
    assert body["activated"] is True
    assert (body["company_name"], body["max_nodes"], body["is_perpetual"]) == ("Acme", 5, True)
    assert body["key_preview"] == row.key[:20] + "..."
    assert row.key not in r.text
    assert isinstance(body["activated_at"], str) and body["activated_at"]


# ---- activate -------------------------------------------------------------

def test_activate_valid_key_stores_license(client, db_session, admin_user, monkeypatch):
    monkeypatch.setattr(lic_routes, "validate_license", fake_valid("Acme", 5))
    r = client.post("/api/license/activate", json={"key": "KEY-1"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "company": "Acme", "max_nodes": 5}
    rows = db_session.query(License).all()
    assert len(rows) == 1 and rows[0].key == "KEY-1" and rows[0].company_name == "Acme"


def test_activate_invalid_key_rejected(client, db_session, admin_user, monkeypatch):
    monkeypatch.setattr(lic_routes, "validate_license", fake_invalid("Bad sig"))
    r = client.post("/api/license/activate", json={"key": "KEY-X"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid license: Bad sig"
    assert db_session.query(License).count() == 0


def test_activate_rejected_when_fleet_exceeds_node_limit(client, db_session, admin_user, monkeypatch):
    add_machines(db_session, 3)
    monkeypatch.setattr(lic_routes, "validate_license", fake_valid(max_nodes=2))
    r = client.post("/api/license/activate", json={"key": "KEY-2"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 400
    assert r.json()["detail"] == "License allows 2 nodes, you have 3"
    assert db_session.query(License).count() == 0


def test_activate_allowed_at_exact_limit_and_when_unlimited(client, db_session, admin_user, monkeypatch):
    add_machines(db_session, 3)
    h = auth_headers(admin_user)
    monkeypatch.setattr(lic_routes, "validate_license", fake_valid(max_nodes=3))
    assert client.post("/api/license/activate", json={"key": "K3"}, headers=h).status_code == 200
    monkeypatch.setattr(lic_routes, "validate_license", fake_valid(max_nodes=-1))
    assert client.post("/api/license/activate", json={"key": "KU"}, headers=h).status_code == 200


def test_activate_replaces_existing_license(client, db_session, admin_user, monkeypatch):
    add_license(db_session, key="OLD-KEY", company_name="OldCo")
    monkeypatch.setattr(lic_routes, "validate_license", fake_valid("NewCo", 10))
    r = client.post("/api/license/activate", json={"key": "NEW-KEY"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 200
    rows = db_session.query(License).all()
    assert len(rows) == 1 and rows[0].key == "NEW-KEY" and rows[0].company_name == "NewCo"


def test_activate_missing_key_is_422(client, admin_user):
    r = client.post("/api/license/activate", json={}, headers=auth_headers(admin_user))
    assert r.status_code == 422


# ---- generate -------------------------------------------------------------

def test_generate_passes_company_and_max_nodes(client, admin_user, monkeypatch):
    seen = {}
    def fake_gen(name, nodes):
        seen["args"] = (name, nodes)
        return "JENIX-FAKE-KEY"
    monkeypatch.setattr(lic_routes, "generate_license", fake_gen)
    r = client.post("/api/license/generate",
                    json={"company_name": "Globex", "max_nodes": 25},
                    headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json() == {"key": "JENIX-FAKE-KEY", "company": "Globex", "max_nodes": 25}
    assert seen["args"] == ("Globex", 25)


def test_generate_default_max_nodes_is_unlimited(client, admin_user, monkeypatch):
    monkeypatch.setattr(lic_routes, "generate_license", lambda n, m: "K")
    r = client.post("/api/license/generate", json={"company_name": "Globex"},
                    headers=auth_headers(admin_user))
    assert r.json()["max_nodes"] == -1


# ---- deactivate -----------------------------------------------------------

def test_deactivate_removes_license(client, db_session, admin_user):
    add_license(db_session)
    h = auth_headers(admin_user)
    r = client.delete("/api/license", headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert db_session.query(License).count() == 0
    assert client.get("/api/license", headers=h).json()["activated"] is False


def test_deactivate_with_no_license_still_ok(client, admin_user):
    r = client.delete("/api/license", headers=auth_headers(admin_user))
    assert r.status_code == 200 and r.json() == {"ok": True}
