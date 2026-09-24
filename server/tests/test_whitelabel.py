"""Route tests for routes/whitelabel.py (mounted at /api/whitelabel).

WHITELABEL_FILE is a module global read at call time, so it is patched to a
tmp_path: the real server/whitelabel.json is never touched. Read = any
authed user (plus a public subset with no auth); write/reset = admin only.
"""
import json
import pytest
from conftest import auth_headers
import routes.whitelabel as wl


@pytest.fixture()
def wl_file(tmp_path, monkeypatch):
    p = tmp_path / "whitelabel.json"
    monkeypatch.setattr(wl, "WHITELABEL_FILE", str(p))
    return p


# ---- read -----------------------------------------------------------------

def test_get_whitelabel_requires_auth(client, wl_file):
    assert client.get("/api/whitelabel").status_code == 401


def test_get_whitelabel_defaults_when_no_file(client, wl_file, viewer_user):
    r = client.get("/api/whitelabel", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == wl.DEFAULT_CONFIG


def test_get_whitelabel_merges_partial_file_over_defaults(client, wl_file, viewer_user):
    wl_file.write_text(json.dumps({"company_name": "Acme"}))
    body = client.get("/api/whitelabel", headers=auth_headers(viewer_user)).json()
    assert body["company_name"] == "Acme"
    assert body["logo_text"] == wl.DEFAULT_CONFIG["logo_text"]
    assert set(body) == set(wl.DEFAULT_CONFIG)


def test_get_whitelabel_falls_back_to_defaults_on_corrupt_file(client, wl_file, viewer_user):
    wl_file.write_text("{not valid json")
    r = client.get("/api/whitelabel", headers=auth_headers(viewer_user))
    assert r.status_code == 200
    assert r.json() == wl.DEFAULT_CONFIG


def test_public_whitelabel_needs_no_auth_and_hides_private_fields(client, wl_file):
    wl_file.write_text(json.dumps({"company_name": "Acme",
                                   "support_email": "help@acme.io"}))
    r = client.get("/api/whitelabel/public")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"company_name", "logo_text", "logo_subtext",
                         "primary_color", "powered_by", "favicon_emoji"}
    assert body["company_name"] == "Acme"
    assert "help@acme.io" not in r.text


# ---- update ---------------------------------------------------------------

def test_update_whitelabel_saves_file_and_get_reflects_it(client, wl_file, admin_user):
    h = auth_headers(admin_user)
    r = client.post("/api/whitelabel",
                    json={"company_name": "Acme", "primary_color": "#ff0000"},
                    headers=h)
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert r.json()["ok"] is True
    assert cfg["company_name"] == "Acme" and cfg["primary_color"] == "#ff0000"
    assert cfg["logo_text"] == wl.DEFAULT_CONFIG["logo_text"]
    assert json.loads(wl_file.read_text()) == cfg
    assert client.get("/api/whitelabel", headers=h).json() == cfg


def test_update_whitelabel_resets_omitted_fields_to_defaults(client, wl_file, admin_user):
    # Real behavior: POST replaces the whole config from the request body
    # (pydantic defaults fill omitted fields); it does not merge with the
    # previously saved values.
    h = auth_headers(admin_user)
    client.post("/api/whitelabel",
                json={"company_name": "Acme", "support_email": "help@acme.io"}, headers=h)
    r = client.post("/api/whitelabel", json={"company_name": "Globex"}, headers=h)
    assert r.json()["config"]["support_email"] == ""


def test_update_whitelabel_forbidden_for_non_admin(client, wl_file, operator_user, viewer_user):
    for u in (operator_user, viewer_user):
        r = client.post("/api/whitelabel", json={"company_name": "Nope"},
                        headers=auth_headers(u))
        assert r.status_code == 403
    assert not wl_file.exists()


def test_update_whitelabel_requires_auth(client, wl_file):
    assert client.post("/api/whitelabel", json={"company_name": "X"}).status_code == 401


def test_update_whitelabel_rejects_wrong_type(client, wl_file, admin_user):
    r = client.post("/api/whitelabel", json={"powered_by": "not-a-bool"},
                    headers=auth_headers(admin_user))
    assert r.status_code == 422
    assert not wl_file.exists()


# ---- reset ----------------------------------------------------------------

def test_reset_whitelabel_removes_file_and_returns_defaults(client, wl_file, admin_user):
    h = auth_headers(admin_user)
    client.post("/api/whitelabel", json={"company_name": "Acme"}, headers=h)
    assert wl_file.exists()
    r = client.post("/api/whitelabel/reset", headers=h)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "config": wl.DEFAULT_CONFIG}
    assert not wl_file.exists()
    assert client.get("/api/whitelabel", headers=h).json() == wl.DEFAULT_CONFIG


def test_reset_whitelabel_with_no_file_is_ok(client, wl_file, admin_user):
    r = client.post("/api/whitelabel/reset", headers=auth_headers(admin_user))
    assert r.status_code == 200 and r.json()["ok"] is True


def test_reset_whitelabel_forbidden_for_non_admin(client, wl_file, operator_user):
    wl_file.write_text(json.dumps({"company_name": "Keep"}))
    r = client.post("/api/whitelabel/reset", headers=auth_headers(operator_user))
    assert r.status_code == 403
    assert wl_file.exists()
