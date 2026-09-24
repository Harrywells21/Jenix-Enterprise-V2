import pytest

from conftest import auth_headers
import ws.handler as ws_handler
from db import Machine, Site, Command


class _FakeAgentSocket:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    async def send_text(self, text):
        if self.fail:
            raise RuntimeError("simulated send failure")
        self.sent.append(text)


@pytest.fixture(autouse=True)
def _clear_agents():
    ws_handler._agents.clear()
    yield
    ws_handler._agents.clear()


def _make_site(db_session, name="Default Site"):
    site = Site(name=name)
    db_session.add(site)
    db_session.commit()
    db_session.refresh(site)
    return site


def _make_machine(db_session, site_id, token="tok-cmd-1", hostname="cmd-host",
                   status="online"):
    m = Machine(
        site_id=site_id,
        token=token,
        hostname=hostname,
        ip="10.0.0.20",
        status=status,
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def _set_passphrase(client, admin_user, machine_id, passphrase):
    resp = client.post(f"/api/machines/{machine_id}/passphrase",
                        json={"passphrase": passphrase},
                        headers=auth_headers(admin_user))
    assert resp.status_code == 200


class TestRoleGate:
    def test_run_command_requires_operator_or_admin(self, client, db_session,
                                                      viewer_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(viewer_user))
        assert resp.status_code == 403

    def test_run_command_operator_allowed(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200
        assert "cmd_id" in resp.json()

    def test_run_command_admin_allowed(self, client, db_session, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(admin_user))
        assert resp.status_code == 200


class TestTypeValidation:
    def test_unknown_type_rejected(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "not_a_real_type"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400

    def test_exec_requires_script_and_signature(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "exec"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400

    def test_exec_with_script_and_signature_ok(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "exec", "script": "echo hi",
                                  "signature": "sig123"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200

    def test_reassign_server_requires_server_url_and_signature(self, client, db_session,
                                                                 operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "reassign_server"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400

    def test_apply_upgrade_requires_full_params_and_signature(self, client, db_session,
                                                                operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "apply_upgrade",
                                  "params": {"version": "1.2.3"}},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400

    @pytest.mark.parametrize("ctype", ["checkpoint_start", "checkpoint_list"])
    def test_checkpoint_start_list_require_signature(self, client, db_session,
                                                       operator_user, ctype):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": ctype},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400

    @pytest.mark.parametrize("ctype", ["checkpoint_restore", "checkpoint_discard"])
    def test_checkpoint_restore_discard_require_id_and_signature(self, client, db_session,
                                                                   operator_user, ctype):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": ctype},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400


class TestMachineStateGates:
    def test_unknown_machine_404(self, client, operator_user):
        # type validation runs before the machine lookup, so use a plain
        # type ("scan") that needs no extra params to reach the 404 branch.
        resp = client.post("/api/machines/999999/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 404

    def test_non_online_machine_400(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, status="pending")
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 400


class TestPassphraseGate:
    # Only boost/clean/fix/rollback are passphrase-gated (GATED); exec and
    # the signed types are never gated by a node passphrase.
    def test_wrong_passphrase_403(self, client, db_session, operator_user, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        _set_passphrase(client, admin_user, m.id, "correct-pass")
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "clean", "passphrase": "wrong-pass"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 403

    def test_missing_passphrase_403(self, client, db_session, operator_user, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        _set_passphrase(client, admin_user, m.id, "correct-pass")
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "clean"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 403

    def test_correct_passphrase_200(self, client, db_session, operator_user, admin_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        _set_passphrase(client, admin_user, m.id, "correct-pass")
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "clean", "passphrase": "correct-pass"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200

    def test_no_passphrase_configured_bypasses_gate(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)  # action_passphrase_hash left unset
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "clean"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200


class TestWsDelivery:
    def test_agent_not_connected_returns_503_and_marks_failed(self, client, db_session,
                                                                operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 503
        cmd = db_session.query(Command).filter_by(machine_id=m.id).first()
        assert cmd is not None
        assert cmd.status == "failed"

    def test_successful_delivery_sets_running_and_sends_payload(self, client, db_session,
                                                                  operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        fake_socket = _FakeAgentSocket()
        ws_handler._agents[m.token] = fake_socket
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200
        cmd = db_session.query(Command).filter_by(machine_id=m.id).first()
        assert cmd is not None
        assert cmd.status == "running"
        assert len(fake_socket.sent) == 1


class TestReassignServer:
    def test_reassign_server_sets_status_reassigning(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "reassign_server",
                                  "params": {"server_url": "https://floor2.example"},
                                  "signature": "sig123"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200
        db_session.refresh(m)
        assert m.status == "reassigning"


class TestGetCommand:
    def test_get_command_404_when_machine_mismatch(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m1 = _make_machine(db_session, site.id, token="tok-a", hostname="host-a")
        m2 = _make_machine(db_session, site.id, token="tok-b", hostname="host-b")
        ws_handler._agents[m1.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m1.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        assert resp.status_code == 200
        cmd_id = resp.json()["cmd_id"]
        mismatch_resp = client.get(f"/api/machines/{m2.id}/command/{cmd_id}",
                                    headers=auth_headers(operator_user))
        assert mismatch_resp.status_code == 404

    def test_get_command_matching_machine_ok(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id)
        ws_handler._agents[m.token] = _FakeAgentSocket()
        resp = client.post(f"/api/machines/{m.id}/command",
                            json={"type": "scan"},
                            headers=auth_headers(operator_user))
        cmd_id = resp.json()["cmd_id"]
        ok_resp = client.get(f"/api/machines/{m.id}/command/{cmd_id}",
                              headers=auth_headers(operator_user))
        assert ok_resp.status_code == 200


class TestHistory:
    def test_history_all_single_query_hostname_join(self, client, db_session, operator_user):
        site = _make_site(db_session)
        m = _make_machine(db_session, site.id, hostname="joined-host")
        ws_handler._agents[m.token] = _FakeAgentSocket()
        client.post(f"/api/machines/{m.id}/command",
                    json={"type": "scan"},
                    headers=auth_headers(operator_user))
        resp = client.get("/api/machines/history/all",
                           headers=auth_headers(operator_user))
        assert resp.status_code == 200
        rows = resp.json()
        assert any(r.get("hostname") == "joined-host" for r in rows)
