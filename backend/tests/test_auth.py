from typing import Annotated, Any

import pytest
from clerk_backend_api.security.types import AuthStatus, RequestState
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.auth.dependencies as deps
from app.auth import ClerkUser
from app.core.config import Settings


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    claims: dict[str, object],
    settings: Settings,
) -> TestClient:
    async def fake_authenticate(request: Any, options: Any) -> RequestState:
        assert options.authorized_parties is None
        return RequestState(
            status=AuthStatus.SIGNED_IN,
            token="session-token",
            payload=claims,
        )

    monkeypatch.setattr(deps, "authenticate_request_async", fake_authenticate)

    api = FastAPI()
    api.dependency_overrides[deps.get_settings] = lambda: settings

    @api.get("/me")
    def me(user: Annotated[ClerkUser, Depends(deps.require_auth)]) -> dict[str, str]:
        return {"user_id": user.user_id}

    return TestClient(api)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "clerk_secret_key": "sk_test_example",
        "clerk_authorized_parties": ["http://localhost:5173"],
    }
    values.update(overrides)
    return Settings(**values)


def test_accepts_token_without_azp_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(
        monkeypatch,
        claims={"sub": "user_123", "sid": "sess_123"},
        settings=_settings(),
    )

    response = client.get("/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_123"}


def test_accepts_token_with_authorized_azp(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(
        monkeypatch,
        claims={"sub": "user_123", "azp": "http://localhost:5173"},
        settings=_settings(),
    )

    response = client.get("/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200


def test_rejects_token_with_unknown_azp(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(
        monkeypatch,
        claims={"sub": "user_123", "azp": "https://evil.example.com"},
        settings=_settings(),
    )

    response = client.get("/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 401


def test_rejects_missing_bearer_token() -> None:
    api = FastAPI()
    api.dependency_overrides[deps.get_settings] = lambda: _settings()

    @api.get("/me")
    def me(user: Annotated[ClerkUser, Depends(deps.require_auth)]) -> dict[str, str]:
        return {"user_id": user.user_id}

    response = TestClient(api).get("/me")

    assert response.status_code == 401


def test_returns_503_when_clerk_is_not_configured() -> None:
    api = FastAPI()
    api.dependency_overrides[deps.get_settings] = lambda: Settings(
        clerk_secret_key=None,
        clerk_jwt_key=None,
    )

    @api.get("/me")
    def me(user: Annotated[ClerkUser, Depends(deps.require_auth)]) -> dict[str, str]:
        return {"user_id": user.user_id}

    response = TestClient(api).get(
        "/me",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 503
