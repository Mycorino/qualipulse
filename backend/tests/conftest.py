"""
Shared fixtures for all tests.
Each test gets its own fresh in-memory SQLite database via StaticPool,
which ensures all connections within a test share the same in-memory db.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.limiter import limiter
from app.main import app

# Disable rate limiting for the entire test session
limiter.enabled = False


@pytest.fixture(scope="function")
def engine():
    """Fresh in-memory SQLite per test. StaticPool ensures single shared connection."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture(scope="function")
def db_session(engine):
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient wired to the test database session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def registered_company(client):
    """Sign up a company and return tokens + payload."""
    payload = {"name": "Test Co", "email": "test@example.com", "password": "Password123!"}
    resp = client.post("/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    return {"tokens": resp.json(), **payload}


@pytest.fixture
def auth_headers(registered_company):
    """Authorization headers for the registered company."""
    token = registered_company["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def drain_sse():
    """Pull the `done` payload from a streaming /copilot SSE response."""
    import json

    def _drain(resp) -> dict:
        for frame in resp.text.split("\n\n"):
            if frame.startswith("data: "):
                event = json.loads(frame[len("data: ") :])
                if event.get("type") == "done":
                    return event
        raise AssertionError(f"no done event in stream:\n{resp.text}")

    return _drain
