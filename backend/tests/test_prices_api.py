from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.prices import get_price_service
from app.auth import ClerkUser, require_auth
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.price import PriceEstimate

USER = ClerkUser(user_id="user_price", session_id="sess_price", claims={})
NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def price_estimate(
    *,
    source: str = "local_reports",
    price: float | None = 150.0,
    scope: str = "area",
) -> PriceEstimate:
    available = source != "unavailable"
    return PriceEstimate(
        material="plastic",
        material_label="Plastic",
        location="Multan",
        area="Shah Rizwan",
        currency="PKR",
        estimated_price_per_kg=price,
        source=source,  # type: ignore[arg-type]
        geographic_scope=scope,  # type: ignore[arg-type]
        observation_count=3 if available else 0,
        local_observation_count=3 if source == "local_reports" else 0,
        city_observation_count=3 if available else 0,
        observed_min_price_per_kg=120.0 if available else None,
        observed_max_price_per_kg=180.0 if available else None,
        oldest_observation_at=NOW if available else None,
        newest_observation_at=NOW if available else None,
        freshness_days=1.0 if available else None,
        evidence_quality="medium" if available else "none",
        confidence=0.65 if available else 0.0,
        message="Based on 3 checked picker reports.",
        limitations=["Observed range is not a market boundary."],
        generated_at=NOW,
    )


class FakePriceService:
    def __init__(
        self,
        *,
        result: PriceEstimate | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or price_estimate()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def estimate(
        self,
        *,
        material: str,
        location: str | None = None,
        area: str | None = None,
    ) -> PriceEstimate:
        self.calls.append({"material": material, "location": location, "area": area})
        if self.error is not None:
            raise self.error
        return self.result


def price_client(service: FakePriceService):
    app.dependency_overrides[require_auth] = lambda: USER
    app.dependency_overrides[get_price_service] = lambda: service
    return TestClient(app)


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_price_estimate_returns_the_service_result() -> None:
    service = FakePriceService(result=price_estimate())
    try:
        with price_client(service) as client:
            response = client.get(
                "/api/v1/prices/estimate",
                params={"material": " plastic ", "location": "Multan", "area": "Shah Rizwan"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local_reports"
    assert body["estimated_price_per_kg"] == 150.0
    assert body["observation_count"] == 3
    assert body["currency"] == "PKR"
    assert service.calls == [
        {"material": "plastic", "location": "Multan", "area": "Shah Rizwan"}
    ]


def test_price_estimate_returns_unavailable_without_a_fake_number() -> None:
    service = FakePriceService(
        result=price_estimate(source="unavailable", price=None, scope="none")
    )
    try:
        with price_client(service) as client:
            response = client.get("/api/v1/prices/estimate", params={"material": "plastic"})
    finally:
        clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "unavailable"
    assert body["estimated_price_per_kg"] is None
    assert body["observation_count"] == 0


def test_price_estimate_rejects_blank_material() -> None:
    service = FakePriceService()
    try:
        with price_client(service) as client:
            blank = client.get("/api/v1/prices/estimate", params={"material": "   "})
            missing = client.get("/api/v1/prices/estimate")
            too_long = client.get(
                "/api/v1/prices/estimate",
                params={"material": "x" * 101},
            )
    finally:
        clear_overrides()

    assert blank.status_code == 422
    assert missing.status_code == 422
    assert too_long.status_code == 422
    assert service.calls == []


def test_price_estimate_requires_location_when_area_is_supplied() -> None:
    service = FakePriceService()
    try:
        with price_client(service) as client:
            response = client.get(
                "/api/v1/prices/estimate",
                params={"material": "plastic", "area": "Shah Rizwan"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 422
    assert response.json()["detail"] == "area requires location"
    assert service.calls == []


def test_price_estimate_requires_authentication() -> None:
    service = FakePriceService()
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_secret_key=None, clerk_jwt_key=None
    )
    app.dependency_overrides[get_price_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/prices/estimate",
                params={"material": "plastic", "location": "Multan"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 401
    assert service.calls == []


def test_price_estimate_database_failure_is_not_an_unavailable_result() -> None:
    service = FakePriceService(error=SQLAlchemyError("database is down"))
    try:
        with price_client(service) as client:
            response = client.get(
                "/api/v1/prices/estimate",
                params={"material": "plastic", "location": "Multan"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 503
    assert response.json()["detail"] == "Price data is unavailable"


def test_price_response_never_exposes_picker_identity() -> None:
    service = FakePriceService()
    try:
        with price_client(service) as client:
            response = client.get(
                "/api/v1/prices/estimate",
                params={"material": "plastic", "location": "Multan"},
            )
    finally:
        clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert "picker_id" not in body
    assert "raw_text" not in body


def test_price_endpoint_is_registered_under_api_v1() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/prices/estimate" in paths
