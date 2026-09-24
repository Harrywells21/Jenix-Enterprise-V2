from conftest import login


def test_login_success(client, viewer_user):
    r = login(client, "viewer@jenix.test", "viewerpass123")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "viewer"
    assert "access_token" in body


def test_login_wrong_password(client, viewer_user):
    r = login(client, "viewer@jenix.test", "wrongpassword")
    assert r.status_code == 401


def test_login_unknown_user(client, db_session):
    r = login(client, "nobody@jenix.test", "whatever123")
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_valid_token(client, viewer_user):
    token = login(client, "viewer@jenix.test", "viewerpass123").json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "viewer@jenix.test"


def test_me_rejects_garbage_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


def test_viewer_cannot_list_users(client, viewer_user):
    token = login(client, "viewer@jenix.test", "viewerpass123").json()["access_token"]
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_can_list_users(client, admin_user, viewer_user):
    token = login(client, "admin@jenix.test", "adminpass123").json()["access_token"]
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {"admin@jenix.test", "viewer@jenix.test"} <= emails


def test_admin_can_deactivate_user(client, admin_user, viewer_user):
    token = login(client, "admin@jenix.test", "adminpass123").json()["access_token"]
    r = client.patch(f"/api/auth/users/{viewer_user.id}/deactivate",
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # authenticate_user() checks is_active, so login itself now rejects this user.
    r2 = login(client, "viewer@jenix.test", "viewerpass123")
    assert r2.status_code == 401


def test_change_password_requires_correct_current(client, viewer_user):
    token = login(client, "viewer@jenix.test", "viewerpass123").json()["access_token"]
    r = client.post("/api/auth/change-password",
                    json={"current_password": "wrongone", "new_password": "newpass1234"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_change_password_enforces_min_length(client, viewer_user):
    token = login(client, "viewer@jenix.test", "viewerpass123").json()["access_token"]
    r = client.post("/api/auth/change-password",
                    json={"current_password": "viewerpass123", "new_password": "short"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_change_password_success_then_old_password_fails(client, viewer_user):
    token = login(client, "viewer@jenix.test", "viewerpass123").json()["access_token"]
    r = client.post("/api/auth/change-password",
                    json={"current_password": "viewerpass123", "new_password": "newpassword1"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    old = login(client, "viewer@jenix.test", "viewerpass123")
    assert old.status_code == 401
    new = login(client, "viewer@jenix.test", "newpassword1")
    assert new.status_code == 200
