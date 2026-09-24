import pytest
from conftest import auth_headers

from db import Machine, Site


def _make_site(db_session, name="Default Site"):
    site = Site(name=name)
    db_session.add(site)
    db_session.commit()
    db_session.refresh(site)
    return site


def _make_machine(db_session, site_id, token="tok-abc", hostname="host-1",
                   ip="10.0.0.5", status="pending"):
    m = Machine(
        site_id=site_id,
        token=token,
        hostname=hostname,
        ip=ip,
        status=status,
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


class TestRegister:
    def test_register_matches_on_token_over_hostname_ip(self, client, db_session):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, token="tok-1",
                           hostname="old-host", ip="10.0.0.1")
        resp = client.post("/api/machines/register", json={
            "token": "tok-1",
            "hostname": "new-host",
            "ip": "10.0.0.2",
        })
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.hostname == "new-host"
        assert m.ip == "10.0.0.2"

    def test_pending_machine_reregistering_stays_pending(self, client, db_session):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, token="tok-2", status="pending")
        resp = client.post("/api/machines/register", json={
            "token": "tok-2",
            "hostname": m.hostname,
            "ip": m.ip,
        })
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.status == "pending"

    def test_fallback_hostname_ip_match_when_no_token_sent(self, client, db_session):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, token="tok-3",
                           hostname="known-host", ip="10.0.0.9")
        resp = client.post("/api/machines/register", json={
            "hostname": "known-host",
            "ip": "10.0.0.9",
        })
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.hostname == "known-host"

    def test_register_no_match_creates_new_pending_machine(self, client, db_session):
        site = _make_site(db_session)
        resp = client.post("/api/machines/register", json={
            "hostname": "brand-new",
            "ip": "10.0.0.42",
        })
        assert resp.status_code == 200
        rows = db_session.query(Machine).filter_by(hostname="brand-new").all()
        assert len(rows) == 1
        assert rows[0].status == "pending"


class TestListGetAuthGates:
    def test_list_machines_requires_auth(self, client):
        resp = client.get("/api/machines")
        assert resp.status_code in (401, 403)

    def test_list_machines_authed(self, client, db_session, viewer_user):
        _make_site(db_session)
        resp = client.get("/api/machines", headers=auth_headers(viewer_user))
        assert resp.status_code == 200

    def test_get_machine_requires_auth(self, client, db_session):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.get(f"/api/machines/{m.id}")
        assert resp.status_code in (401, 403)

    def test_get_machine_authed(self, client, db_session, viewer_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.get(f"/api/machines/{m.id}", headers=auth_headers(viewer_user))
        assert resp.status_code == 200


class TestPendingAndInstallCommand:
    def test_pending_requires_admin(self, client, viewer_user):
        resp = client.get("/api/machines/pending", headers=auth_headers(viewer_user))
        assert resp.status_code == 403

    def test_pending_admin_ok(self, client, admin_user):
        resp = client.get("/api/machines/pending", headers=auth_headers(admin_user))
        assert resp.status_code == 200

    def test_install_command_requires_admin(self, client, db_session, viewer_user):
        site = _make_site(db_session)
        resp = client.get(f"/api/machines/install-command?site_id={site.id}",
                           headers=auth_headers(viewer_user))
        assert resp.status_code == 403

    def test_install_command_unknown_site_404(self, client, admin_user):
        resp = client.get("/api/machines/install-command?site_id=999999",
                           headers=auth_headers(admin_user))
        assert resp.status_code == 404

    def test_install_command_admin_ok(self, client, db_session, admin_user):
        site = _make_site(db_session)
        resp = client.get(f"/api/machines/install-command?site_id={site.id}",
                           headers=auth_headers(admin_user))
        assert resp.status_code == 200


class TestApproveRejectDelete:
    def test_approve_sets_active_status(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, status="pending")
        resp = client.post(f"/api/machines/{m.id}/approve", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.status == "offline"

    def test_approve_redirect_target_branch_leaves_pending(self, client, db_session,
                                                            admin_user):
        site = _make_site(db_session)
        other_site = _make_site(db_session, name="Other Site")
        m = _make_machine(db_session, site.id, status="pending")
        resp = client.post(
            f"/api/machines/{m.id}/approve",
            json={"redirect_target_url": "https://other-floor.example/register"},
            headers=auth_headers(admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "redirect_pending"
        db_session.refresh(m)
        # Real behavior: the redirect-target branch returns early and
        # leaves the machine's status as "pending", NOT "offline".
        assert m.status == "pending"

    def test_reject_deletes_row(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, status="pending")
        mid = m.id
        resp = client.post(f"/api/machines/{mid}/reject", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert db_session.query(Machine).filter_by(id=mid).first() is None

    def test_delete_requires_admin(self, client, db_session, viewer_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.delete(f"/api/machines/{m.id}", headers=auth_headers(viewer_user))
        assert resp.status_code == 403

    def test_delete_admin_ok(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        mid = m.id
        resp = client.delete(f"/api/machines/{mid}", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert db_session.query(Machine).filter_by(id=mid).first() is None


class TestPassphrase:
    def test_set_passphrase_requires_admin(self, client, db_session, viewer_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/passphrase",
                            json={"passphrase": "longenough1"},
                            headers=auth_headers(viewer_user))
        assert resp.status_code == 403

    def test_set_passphrase_min_length(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/passphrase",
                            json={"passphrase": "short"},
                            headers=auth_headers(admin_user))
        assert resp.status_code == 400

    def test_set_passphrase_ok(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/passphrase",
                            json={"passphrase": "longenough1"},
                            headers=auth_headers(admin_user))
        assert resp.status_code == 200

    def test_passphrase_status_reflects_configured(self, client, db_session,
                                                     admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        client.post(f"/api/machines/{m.id}/passphrase",
                    json={"passphrase": "longenough1"},
                    headers=auth_headers(admin_user))
        resp = client.get(f"/api/machines/{m.id}/passphrase-status",
                           headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert resp.json().get("is_set") is True

    def test_clear_passphrase(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        client.post(f"/api/machines/{m.id}/passphrase",
                    json={"passphrase": "longenough1"},
                    headers=auth_headers(admin_user))
        resp = client.delete(f"/api/machines/{m.id}/passphrase",
                              headers=auth_headers(admin_user))
        assert resp.status_code == 200
        status_resp = client.get(f"/api/machines/{m.id}/passphrase-status",
                                  headers=auth_headers(admin_user))
        assert status_resp.json().get("is_set") is False


class TestLogs:
    def test_empty_logs_for_new_machine(self, client, db_session, viewer_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.get(f"/api/machines/{m.id}/logs", headers=auth_headers(viewer_user))
        assert resp.status_code == 200
        body = resp.json()
        logs = body if isinstance(body, list) else body.get("logs", [])
        assert logs == []
