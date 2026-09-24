"""Route tests for routes/backup.py (mounted at /api/backup). Admin-only.

The top-level backup module reads BACKUP_DIR / DB_PATH from its own module
globals at call time, so both are patched to a tmp_path: the real
server/jenix.db and server/backups/ are never touched.
"""
import pytest
from conftest import auth_headers
import backup as backup_mod


@pytest.fixture()
def bk(tmp_path, monkeypatch):
    bdir = tmp_path / "backups"
    dbfile = tmp_path / "jenix.db"
    dbfile.write_bytes(b"x" * 2048)
    monkeypatch.setattr(backup_mod, "BACKUP_DIR", bdir)
    monkeypatch.setattr(backup_mod, "DB_PATH", dbfile)
    return {"dir": bdir, "db": dbfile}


def seed(bdir, name, data=b"seed"):
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / name).write_bytes(data)


# ---- auth -----------------------------------------------------------------

def test_backup_routes_require_auth(client, bk):
    assert client.post("/api/backup/create").status_code == 401
    assert client.get("/api/backup/list").status_code == 401
    assert client.post("/api/backup/restore/x.db").status_code == 401


def test_backup_routes_forbidden_for_non_admin(client, bk, operator_user, viewer_user):
    for u in (operator_user, viewer_user):
        h = auth_headers(u)
        assert client.post("/api/backup/create", headers=h).status_code == 403
        assert client.get("/api/backup/list", headers=h).status_code == 403
        assert client.post("/api/backup/restore/x.db", headers=h).status_code == 403
    assert not bk["dir"].exists()


# ---- create ---------------------------------------------------------------

def test_create_backup_copies_db(client, bk, admin_user):
    r = client.post("/api/backup/create", headers=auth_headers(admin_user))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["size_kb"] == 2.0
    files = list(bk["dir"].glob("jenix_*.db"))
    assert len(files) == 1 and body["path"] == str(files[0])
    assert files[0].read_bytes() == b"x" * 2048


def test_create_backup_fails_cleanly_without_database(client, bk, admin_user):
    bk["db"].unlink()
    r = client.post("/api/backup/create", headers=auth_headers(admin_user))
    assert r.status_code == 500
    assert "Backup failed" in r.json()["detail"]
    assert list(bk["dir"].glob("jenix_*.db")) == []


def test_create_backup_prunes_to_seven(client, bk, admin_user):
    old = [f"jenix_2026010{i}_000000.db" for i in range(1, 8)]
    for n in old:
        seed(bk["dir"], n)
    r = client.post("/api/backup/create", headers=auth_headers(admin_user))
    assert r.status_code == 200
    names = sorted(p.name for p in bk["dir"].glob("jenix_*.db"))
    assert len(names) == 7
    assert old[0] not in names and old[1] in names


# ---- list -----------------------------------------------------------------

def test_list_backups_empty_when_dir_missing(client, bk, admin_user):
    r = client.get("/api/backup/list", headers=auth_headers(admin_user))
    assert r.status_code == 200 and r.json() == []


def test_list_backups_newest_first_created_from_filename(client, bk, admin_user):
    seed(bk["dir"], "jenix_20260914_111137.db", b"a" * 1024)
    seed(bk["dir"], "jenix_20260915_080000.db", b"b" * 1024)
    seed(bk["dir"], "notes.txt", b"ignored")
    r = client.get("/api/backup/list", headers=auth_headers(admin_user))
    rows = r.json()
    assert [x["filename"] for x in rows] == ["jenix_20260915_080000.db",
                                              "jenix_20260914_111137.db"]
    assert rows[0]["created"] == "2026-09-15T08:00:00"
    assert rows[1]["created"] == "2026-09-14T11:11:37"
    assert rows[0]["size_kb"] == 1.0


# ---- restore --------------------------------------------------------------

def test_restore_unknown_backup_404_and_db_untouched(client, bk, admin_user):
    r = client.post("/api/backup/restore/jenix_nope.db", headers=auth_headers(admin_user))
    assert r.status_code == 404
    assert bk["db"].read_bytes() == b"x" * 2048


def test_restore_replaces_db_and_snapshots_current_first(client, bk, admin_user):
    name = "jenix_20260101_000000.db"
    seed(bk["dir"], name, b"OLD" * 100)
    r = client.post(f"/api/backup/restore/{name}", headers=auth_headers(admin_user))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "restored": name}
    assert bk["db"].read_bytes() == b"OLD" * 100
    snaps = [p for p in bk["dir"].glob("jenix_*.db") if p.name != name]
    assert len(snaps) == 1 and snaps[0].read_bytes() == b"x" * 2048
