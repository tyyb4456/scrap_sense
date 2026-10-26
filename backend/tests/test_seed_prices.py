from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.core.config import Settings
from app.services.prices import load_seed_prices


def test_shipped_seed_file_contains_no_fabricated_entries() -> None:
    """The repository must not ship pretend market prices."""
    assert load_seed_prices(Settings()) == []


def test_seed_loader_reads_an_audited_entry(tmp_path: Path) -> None:
    path = tmp_path / "seed_prices.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "material": "plastic",
                        "city": "Multan",
                        "price_per_kg": 150,
                        "currency": "pkr",
                        "unit": "kg",
                        "source": "Week 1 dealer visit",
                        "collector": "field team",
                        "collected_at": "2026-10-20",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    entries = load_seed_prices(Settings(price_seed_prices_path=path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.normalized_material == "plastic"
    assert entry.city == "Multan"
    assert entry.price_per_kg == 150
    assert entry.currency == "PKR"
    assert entry.source == "Week 1 dealer visit"
    assert entry.collector == "field team"
    assert entry.collected_at == date(2026, 10, 20)


def test_seed_loader_fails_closed_on_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "seed_prices.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert load_seed_prices(Settings(price_seed_prices_path=path)) == []


def test_seed_loader_fails_closed_on_unsupported_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "seed_prices.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "entries": [
                    {
                        "material": "plastic",
                        "price_per_kg": 150,
                        "currency": "PKR",
                        "unit": "kg",
                        "source": "Week 1 dealer visit",
                        "collected_at": "2026-10-20",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_seed_prices(Settings(price_seed_prices_path=path)) == []


def test_seed_loader_fails_closed_on_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "seed_prices.json"
    path.write_bytes(b"\xff\xfe\x00")

    assert load_seed_prices(Settings(price_seed_prices_path=path)) == []


def test_seed_loader_requires_source_and_positive_price(tmp_path: Path) -> None:
    path = tmp_path / "seed_prices.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "material": "plastic",
                        "price_per_kg": 0,
                        "currency": "PKR",
                        "unit": "kg",
                        "source": "bad",
                        "collected_at": "2026-10-20",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_seed_prices(Settings(price_seed_prices_path=path)) == []
