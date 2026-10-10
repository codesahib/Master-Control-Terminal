import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app

ORIGIN = "http://localhost:5173"


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    # No `with`: skip the lifespan so startup seeding never touches a real database.
    yield TestClient(app, base_url="http://localhost")
    app.dependency_overrides.clear()


def test_health_needs_no_header(client):
    assert client.get("/health").status_code == 200


def test_requested_with_header_required_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "api_token", None)
    assert client.get("/platforms").status_code == 403
    assert client.get("/platforms", headers={"X-Requested-With": "nope"}).status_code == 403
    assert client.get("/platforms", headers={"X-Requested-With": "master-terminal"}).status_code == 200


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_token", "s3cret")
    assert client.get("/platforms", headers={"X-Requested-With": "master-terminal"}).status_code == 401
    assert client.get("/platforms", headers={"X-API-Token": "wrong"}).status_code == 401
    assert client.get("/platforms", headers={"X-API-Token": "s3cret"}).status_code == 200


def test_mutation_blocked_without_header(client, monkeypatch):
    monkeypatch.setattr(settings, "api_token", None)
    files = {"file": ("backup.json", b"{}", "application/json")}
    assert client.post("/import-backup", files=files).status_code == 403


def test_unknown_host_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "api_token", None)
    headers = {"X-Requested-With": "master-terminal"}
    assert client.get("/export", headers={**headers, "Host": "evil.example"}).status_code == 400
    assert client.get("/health", headers={"Host": "evil.example:8000"}).status_code == 400
    assert client.get("/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200
    assert client.get("/platforms", headers={**headers, "Host": "localhost:8000"}).status_code == 200


def test_preflight_allowed_for_frontend_origin(client):
    response = client.options(
        "/platforms",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-token,x-requested-with",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_rejected_for_other_origin(client):
    response = client.options(
        "/platforms",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-requested-with",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
