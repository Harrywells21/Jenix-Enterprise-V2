import sys
from pathlib import Path

# main.py / db.py / auth.py use non-package-relative imports (from db import ...),
# so pytest needs server/ on sys.path -- same as how uvicorn is run from server/.
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

# StaticPool is required for in-memory sqlite under a real multi-route app --
# without it each new connection gets a separate empty DB (verified in sandbox
# testing: this caused "no such table: users" on the very first run).
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


# Session-scoped: main.py's lifespan starts a real APScheduler singleton
# that is never torn down between re-entries, so re-triggering lifespan
# per-test raises SchedulerAlreadyRunningError on the 2nd+ test. Enter the
# real app's lifespan exactly once for the whole test run instead.
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
