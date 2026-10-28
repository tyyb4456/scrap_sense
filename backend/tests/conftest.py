from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from app.db.session import engine


@pytest.fixture
async def postgres_db() -> AsyncIterator[None]:
    """Require the real PostgreSQL database and a migrated reports table."""
    await engine.dispose()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            has_reports = await connection.scalar(text("SELECT to_regclass('public.reports')"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(
            "PostgreSQL integration test unavailable. Start it with "
            f"`docker compose up -d db` and run `uv run alembic upgrade head`: {exc}"
        )
    if has_reports is None:  # pragma: no cover - environment dependent
        pytest.skip("The reports table is missing. Run `uv run alembic upgrade head` first.")

    yield
    await engine.dispose()
