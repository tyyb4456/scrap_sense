from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_session
from app.main import app


class HealthySession:
    async def execute(self, _statement: object) -> None:
        return None


class UnavailableSession:
    async def execute(self, _statement: object) -> None:
        raise SQLAlchemyError("connection failed for user scrapsense")


async def healthy_session() -> AsyncIterator[HealthySession]:
    yield HealthySession()


async def unavailable_session() -> AsyncIterator[UnavailableSession]:
    yield UnavailableSession()


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_when_database_is_available() -> None:
    app.dependency_overrides[get_session] = healthy_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "version": "0.1.0",
    }


def test_readiness_when_database_is_unavailable() -> None:
    app.dependency_overrides[get_session] = unavailable_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "unavailable",
        "version": "0.1.0",
    }
    assert "scrapsense" not in response.text
