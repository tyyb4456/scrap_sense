"""PostgreSQL-backed coverage for the reviewer queue and review decisions.

These tests use the configured real database. Each test creates uniquely
identified rows, commits them through the application service, exercises the
HTTP endpoints, and deletes only those rows at the end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_admin, require_auth
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_session
from app.main import app
from app.models.report import Report
from app.schemas.price import PriceEstimate
from app.schemas.report import AnomalyVerdict, FinalReport, ReportDraft
from app.services.prices import PriceService
from app.services.reports import review_report, save_report

REVIEWER = ClerkUser(user_id="reviewer_integration_test", session_id="sess_reviewer", claims={})
PICKER = ClerkUser(user_id="picker_integration_test", session_id="sess_picker", claims={})
OLD = datetime(1900, 1, 1, tzinfo=UTC)


async def _real_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def reviewer_client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[require_admin] = lambda: REVIEWER
    app.dependency_overrides[get_session] = _real_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def picker_client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[require_auth] = lambda: PICKER
    app.dependency_overrides[get_settings] = lambda: Settings(
        admin_user_ids=[REVIEWER.user_id]
    )
    app.dependency_overrides[get_session] = _real_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def anonymous_client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        clerk_secret_key=None,
        clerk_jwt_key=None,
        admin_user_ids=[],
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _draft(
    *,
    city: str,
    area: str,
    price: str,
    observed_at: datetime,
    material: str = "plastic",
    quantity: str = "2",
) -> ReportDraft:
    return ReportDraft(
        material=material,
        price_per_kg=Decimal(price),
        quantity_kg=Decimal(quantity),
        currency="PKR",
        unit="kg",
        city=city,
        area=area,
        observed_at=observed_at,
    )


def _verdict(*, suspicious: bool) -> AnomalyVerdict:
    if suspicious:
        return AnomalyVerdict(
            is_anomalous=True,
            reason="Price is a statistical outlier: test fixture with median/MAD evidence.",
            method="mad",
            confidence=0.75,
            outcome="suspicious",
            sample_size=5,
        )
    return AnomalyVerdict(
        is_anomalous=False,
        reason="No anomaly detected in the integration fixture.",
        method="mad",
        confidence=0.6,
        outcome="pass",
        sample_size=5,
    )


async def _persist(
    *,
    picker_id: str,
    city: str,
    area: str,
    price: str,
    created_at: datetime,
    suspicious: bool,
    observed_at: datetime | None = None,
    material: str = "plastic",
    quantity: str = "2",
) -> FinalReport:
    saved = await save_report(
        picker_id=picker_id,
        raw_text="integration fixture raw text",
        draft=_draft(
            city=city,
            area=area,
            price=price,
            observed_at=observed_at or (datetime.now(UTC) - timedelta(days=1)),
            material=material,
            quantity=quantity,
        ),
        verdict=_verdict(suspicious=suspicious),
    )

    async with SessionLocal() as session:
        stored = await session.get(Report, saved.id)
        assert stored is not None
        stored.created_at = created_at
        await session.commit()
    return saved


async def _delete_reports(report_ids: list[UUID]) -> None:
    if not report_ids:
        return
    async with SessionLocal() as session:
        await session.execute(delete(Report).where(Report.id.in_(report_ids)))
        await session.commit()


async def _estimate(
    *,
    city: str,
    area: str | None,
    material: str = "plastic",
    min_observations: int = 2,
) -> PriceEstimate:
    async with SessionLocal() as session:
        service = PriceService(
            session=session,
            settings=Settings(price_min_observations=min_observations),
        )
        return await service.estimate(material=material, location=city, area=area)


async def _all_flagged_ids(client: AsyncClient) -> set[str]:
    ids: set[str] = set()
    page = 1
    while True:
        response = await client.get(
            "/api/v1/reports",
            params={"status": "flagged", "page": page, "page_size": 100},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        ids.update(item["id"] for item in body["items"])
        if not body["has_more"]:
            return ids
        page += 1


async def test_queue_requires_reviewer_authorization(postgres_db: None) -> None:
    async with anonymous_client() as client:
        unauthenticated = await client.get("/api/v1/reports")
    assert unauthenticated.status_code == 401

    async with picker_client() as client:
        picker = await client.get("/api/v1/reports")
    assert picker.status_code == 403

    async with reviewer_client() as client:
        reviewer = await client.get("/api/v1/reports")
    assert reviewer.status_code == 200
    body = reviewer.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] >= 0
    assert isinstance(body["items"], list)
    assert body["has_more"] is False or body["pages"] > 1


async def test_queue_filters_status_and_paginates_oldest_first(postgres_db: None) -> None:
    unique = uuid4().hex
    city = f"Queue City {unique}"
    area = f"Queue Area {unique}"
    created: list[UUID] = []
    try:
        flagged_one = await _persist(
            picker_id=f"queue-picker-{unique}-1",
            city=city,
            area=area,
            price="5000",
            created_at=OLD,
            suspicious=True,
        )
        created.append(flagged_one.id)
        flagged_two = await _persist(
            picker_id=f"queue-picker-{unique}-2",
            city=city,
            area=area,
            price="6000",
            created_at=OLD + timedelta(days=1),
            suspicious=True,
        )
        created.append(flagged_two.id)
        flagged_three = await _persist(
            picker_id=f"queue-picker-{unique}-3",
            city=city,
            area=area,
            price="7000",
            created_at=OLD + timedelta(days=2),
            suspicious=True,
        )
        created.append(flagged_three.id)
        accepted = await _persist(
            picker_id=f"queue-picker-{unique}-4",
            city=city,
            area=area,
            price="100",
            created_at=OLD + timedelta(days=3),
            suspicious=False,
        )
        created.append(accepted.id)
        rejected = await _persist(
            picker_id=f"queue-picker-{unique}-5",
            city=city,
            area=area,
            price="8000",
            created_at=OLD + timedelta(days=4),
            suspicious=True,
        )
        created.append(rejected.id)

        async with SessionLocal() as session:
            await review_report(
                session,
                report_id=rejected.id,
                reviewer_id=REVIEWER.user_id,
                status="rejected",
            )

        async with reviewer_client() as client:
            first_page = await client.get(
                "/api/v1/reports",
                params={"status": "flagged", "page": 1, "page_size": 2},
            )
            second_page = await client.get(
                "/api/v1/reports",
                params={"status": "flagged", "page": 2, "page_size": 2},
            )
            all_flagged = await _all_flagged_ids(client)

        assert first_page.status_code == 200
        first = first_page.json()
        assert [item["id"] for item in first["items"]] == [
            str(flagged_one.id),
            str(flagged_two.id),
        ]
        assert first["page"] == 1
        assert first["page_size"] == 2
        assert first["total"] >= 3
        assert first["pages"] >= 2
        assert first["has_more"] is True

        second = second_page.json()
        assert second["page"] == 2
        assert second["items"][0]["id"] == str(flagged_three.id)

        assert str(flagged_one.id) in all_flagged
        assert str(flagged_two.id) in all_flagged
        assert str(flagged_three.id) in all_flagged
        assert str(accepted.id) not in all_flagged
        assert str(rejected.id) not in all_flagged
    finally:
        await _delete_reports(created)


async def test_approval_persists_and_makes_a_flagged_report_eligible(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Approval City {unique}"
    area = f"Approval Area {unique}"
    created: list[UUID] = []
    try:
        baseline_a = await _persist(
            picker_id=f"approval-picker-{unique}-1",
            city=city,
            area=area,
            price="100",
            created_at=OLD + timedelta(days=1),
            suspicious=False,
        )
        created.append(baseline_a.id)
        baseline_b = await _persist(
            picker_id=f"approval-picker-{unique}-2",
            city=city,
            area=area,
            price="200",
            created_at=OLD + timedelta(days=2),
            suspicious=False,
        )
        created.append(baseline_b.id)
        flagged = await _persist(
            picker_id=f"approval-picker-{unique}-3",
            city=city,
            area=area,
            price="5000",
            created_at=OLD,
            suspicious=True,
            material="PET",
            quantity="3.5",
        )
        created.append(flagged.id)

        before = await _estimate(city=city, area=area)
        assert before.source == "local_reports"
        assert before.estimated_price_per_kg == 150.0
        assert before.observation_count == 2

        async with reviewer_client() as client:
            queue = await client.get(
                "/api/v1/reports",
                params={"status": "flagged", "page": 1, "page_size": 20},
            )
            assert queue.status_code == 200
            assert str(flagged.id) in [item["id"] for item in queue.json()["items"]]

            response = await client.patch(
                f"/api/v1/reports/{flagged.id}/review",
                json={"status": "accepted"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "accepted"
            assert body["is_anomalous"] is False
            assert body["reviewed_by"] == REVIEWER.user_id

            still_flagged = await _all_flagged_ids(client)
            assert str(flagged.id) not in still_flagged

        async with SessionLocal() as session:
            stored = await session.get(Report, flagged.id)
            assert stored is not None
            assert stored.status == "accepted"
            assert stored.is_anomalous is False
            assert stored.reviewed_at is not None
            assert stored.reviewed_by == REVIEWER.user_id
            assert stored.price_per_kg == Decimal("5000.00")
            assert stored.quantity_kg == Decimal("3.500")

        after = await _estimate(city=city, area=area)
        assert after.source == "local_reports"
        assert after.observation_count == 3
        assert after.estimated_price_per_kg == 200.0
        assert after.observed_max_price_per_kg == 5000.0
    finally:
        await _delete_reports(created)


async def test_rejection_persists_and_keeps_the_report_ineligible(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Rejection City {unique}"
    area = f"Rejection Area {unique}"
    created: list[UUID] = []
    try:
        baseline_a = await _persist(
            picker_id=f"rejection-picker-{unique}-1",
            city=city,
            area=area,
            price="100",
            created_at=OLD + timedelta(days=1),
            suspicious=False,
        )
        created.append(baseline_a.id)
        baseline_b = await _persist(
            picker_id=f"rejection-picker-{unique}-2",
            city=city,
            area=area,
            price="200",
            created_at=OLD + timedelta(days=2),
            suspicious=False,
        )
        created.append(baseline_b.id)
        flagged = await _persist(
            picker_id=f"rejection-picker-{unique}-3",
            city=city,
            area=area,
            price="9000",
            created_at=OLD,
            suspicious=True,
        )
        created.append(flagged.id)

        before = await _estimate(city=city, area=area)
        assert before.estimated_price_per_kg == 150.0

        async with reviewer_client() as client:
            response = await client.patch(
                f"/api/v1/reports/{flagged.id}/review",
                json={"status": "rejected"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "rejected"
            assert body["is_anomalous"] is True

        async with SessionLocal() as session:
            stored = await session.get(Report, flagged.id)
            assert stored is not None
            assert stored.status == "rejected"
            assert stored.is_anomalous is True
            assert stored.reviewed_at is not None
            assert stored.reviewed_by == REVIEWER.user_id
            assert stored.price_per_kg == Decimal("9000.00")
            assert stored.quantity_kg == Decimal("2.000")

        after = await _estimate(city=city, area=area)
        assert after.source == "local_reports"
        assert after.estimated_price_per_kg == 150.0
        assert after.observation_count == 2
        assert after.observed_max_price_per_kg == 200.0
    finally:
        await _delete_reports(created)


async def test_cityless_flagged_report_cannot_be_approved(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    area = f"Cityless Area {unique}"
    created: list[UUID] = []
    try:
        async with SessionLocal() as session:
            cityless = Report(
                picker_id=f"cityless-picker-{unique}",
                raw_text="integration fixture without a city",
                material="plastic",
                price_per_kg=Decimal("5000"),
                quantity_kg=Decimal("2"),
                currency="PKR",
                city=None,
                area=area,
                observed_at=datetime.now(UTC) - timedelta(days=1),
                confidence=0.8,
                is_anomalous=True,
                anomaly_reason="Price is a statistical outlier.",
                anomaly_method="mad",
                status="flagged",
            )
            session.add(cityless)
            await session.commit()
            await session.refresh(cityless)
            created.append(cityless.id)

        async with reviewer_client() as client:
            approval = await client.patch(
                f"/api/v1/reports/{cityless.id}/review",
                json={"status": "accepted"},
            )
            assert approval.status_code == 409
            assert "city" in approval.json()["detail"]

        async with SessionLocal() as session:
            stored = await session.get(Report, cityless.id)
            assert stored is not None
            assert stored.status == "flagged"
            assert stored.is_anomalous is True
            assert stored.reviewed_at is None

        async with reviewer_client() as client:
            rejection = await client.patch(
                f"/api/v1/reports/{cityless.id}/review",
                json={"status": "rejected"},
            )
            assert rejection.status_code == 200
            assert rejection.json()["status"] == "rejected"
    finally:
        await _delete_reports(created)


async def test_invalid_transitions_and_missing_reports_are_rejected(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Transition City {unique}"
    area = f"Transition Area {unique}"
    created: list[UUID] = []
    try:
        flagged = await _persist(
            picker_id=f"transition-picker-{unique}-1",
            city=city,
            area=area,
            price="5000",
            created_at=OLD,
            suspicious=True,
        )
        created.append(flagged.id)
        accepted = await _persist(
            picker_id=f"transition-picker-{unique}-2",
            city=city,
            area=area,
            price="100",
            created_at=OLD + timedelta(days=1),
            suspicious=False,
        )
        created.append(accepted.id)

        async with reviewer_client() as client:
            missing = await client.patch(
                f"/api/v1/reports/{uuid4()}/review",
                json={"status": "accepted"},
            )
            assert missing.status_code == 404
            assert missing.json()["detail"] == "Report not found"

            invalid = await client.patch(
                f"/api/v1/reports/{flagged.id}/review",
                json={"status": "approved"},
            )
            assert invalid.status_code == 422

            first = await client.patch(
                f"/api/v1/reports/{flagged.id}/review",
                json={"status": "accepted"},
            )
            assert first.status_code == 200

            repeated = await client.patch(
                f"/api/v1/reports/{flagged.id}/review",
                json={"status": "rejected"},
            )
            assert repeated.status_code == 409

            not_flagged = await client.patch(
                f"/api/v1/reports/{accepted.id}/review",
                json={"status": "rejected"},
            )
            assert not_flagged.status_code == 409

        async with picker_client() as client:
            forbidden = await client.patch(
                f"/api/v1/reports/{accepted.id}/review",
                json={"status": "accepted"},
            )
            assert forbidden.status_code == 403

        async with SessionLocal() as session:
            stored = await session.get(Report, flagged.id)
            assert stored is not None
            assert stored.status == "accepted"
            assert stored.reviewed_by == REVIEWER.user_id
    finally:
        await _delete_reports(created)


async def test_approval_does_not_bypass_observation_age(postgres_db: None) -> None:
    unique = uuid4().hex
    city = f"Age City {unique}"
    area = f"Age Area {unique}"
    created: list[UUID] = []
    try:
        stale = await _persist(
            picker_id=f"age-picker-{unique}",
            city=city,
            area=area,
            price="5000",
            created_at=OLD,
            suspicious=True,
            observed_at=datetime.now(UTC) - timedelta(days=200),
        )
        created.append(stale.id)

        async with reviewer_client() as client:
            response = await client.patch(
                f"/api/v1/reports/{stale.id}/review",
                json={"status": "accepted"},
            )
            assert response.status_code == 200

        estimate = await _estimate(city=city, area=area, min_observations=1)
        assert estimate.source == "unavailable"
        assert estimate.estimated_price_per_kg is None
    finally:
        await _delete_reports(created)


async def test_approval_does_not_bypass_duplicate_suppression(
    postgres_db: None,
) -> None:
    unique = uuid4().hex
    city = f"Duplicate City {unique}"
    area = f"Duplicate Area {unique}"
    now = datetime.now(UTC)
    created: list[UUID] = []
    try:
        first = await _persist(
            picker_id=f"duplicate-picker-{unique}",
            city=city,
            area=area,
            price="100",
            created_at=OLD + timedelta(days=1),
            suspicious=False,
            observed_at=now - timedelta(days=1),
            material="plastic",
            quantity="2",
        )
        created.append(first.id)
        second = await _persist(
            picker_id=f"duplicate-picker-{unique}-other",
            city=city,
            area=area,
            price="200",
            created_at=OLD + timedelta(days=2),
            suspicious=False,
            observed_at=now - timedelta(days=1),
            material="plastic",
            quantity="2",
        )
        created.append(second.id)
        duplicate = await _persist(
            picker_id=f"duplicate-picker-{unique}",
            city=city,
            area=area,
            price="100",
            created_at=OLD,
            suspicious=True,
            observed_at=now - timedelta(days=1) + timedelta(minutes=5),
            material="PET",
            quantity="2",
        )
        created.append(duplicate.id)

        before = await _estimate(city=city, area=area)
        assert before.estimated_price_per_kg == 150.0
        assert before.observation_count == 2

        async with reviewer_client() as client:
            response = await client.patch(
                f"/api/v1/reports/{duplicate.id}/review",
                json={"status": "accepted"},
            )
            assert response.status_code == 200

        after = await _estimate(city=city, area=area)
        assert after.source == "local_reports"
        assert after.estimated_price_per_kg == 150.0
        assert after.observation_count == 2
    finally:
        await _delete_reports(created)
