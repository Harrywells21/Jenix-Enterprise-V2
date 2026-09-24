import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from db import Base, get_db, User
from auth import hash_password
from main import app

TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def _live_app():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(db_session, _live_app):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield _live_app
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session):
    user = User(name="Admin", email="admin@jenix.test",
                password_hash=hash_password("adminpass123"),
                role="admin", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def viewer_user(db_session):
    user = User(name="Viewer", email="viewer@jenix.test",
                password_hash=hash_password("viewerpass123"),
                role="viewer", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client, email, password):
    return client.post("/api/auth/login", data={"username": email, "password": password})


# ── Additions for agents/commands/metrics test suites ──────────────────────
# Not part of the original auth-flow conftest.py (85b80e1). Adds an
# operator-role fixture (require_operator gates commands.py's run_command)
# and a direct-token header helper so these suites don't need to depend on
# routes/auth.py's login endpoint at all -- they authenticate the same way
# any API client would, via a real auth.create_token() bearer token.
from auth import create_token

@pytest.fixture()
def operator_user(db_session):
    user = User(name="Operator", email="operator@jenix.test",
                password_hash=hash_password("operatorpass123"),
                role="operator", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user):
    token = create_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}
