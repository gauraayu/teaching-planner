"""Integration-test fixtures: the real application, with an in-process stand-in for MongoDB (mongomock).

Every commit in a test goes through the same write-through path as production, so the documents in the
stand-in are checked against what the application holds.
"""
import os

os.environ["MONGODB_URI"] = "mongomock://test"  # must happen before the app (and its store) is imported
os.environ["MONGODB_DB"] = "teaching_portal_test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def db_engine():
    from app.db.session import SessionLocal, engine
    from scripts.seed import seed

    db = SessionLocal()
    seed(db)
    db.close()
    yield engine


@pytest.fixture()
def db(db_engine):
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="session")
def client(db_engine):
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def tokens(client):
    """Real sign-in for each seeded demo account - there is no role-selection shortcut any more."""
    out = {}
    for role, username in (("ADMIN", "admin.demo"), ("PROFESSOR", "professor.demo"), ("CL_CH", "clch.demo"), ("OM", "om.demo")):
        r = client.post("/api/auth/login", json={"identifier": username, "password": "Demo@1234"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == role
        out[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return out
