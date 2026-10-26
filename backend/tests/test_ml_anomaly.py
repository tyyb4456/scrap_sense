from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.ml_anomaly import assess_ml_readiness, evaluate_ml_check


def test_ml_is_disabled_by_default() -> None:
    result = evaluate_ml_check(Settings(anomaly_ml_enabled=False))

    assert result.outcome == "disabled"
    assert result.is_anomalous is False


def test_enabled_ml_without_artifact_falls_back_safely(tmp_path: Path) -> None:
    result = evaluate_ml_check(
        Settings(
            anomaly_ml_enabled=True,
            anomaly_ml_artifact_path=tmp_path / "missing.joblib",
        )
    )

    assert result.outcome == "unavailable"
    assert result.is_anomalous is False


def test_readiness_requires_volume_and_diversity() -> None:
    too_small = assess_ml_readiness(
        report_count=10,
        distinct_materials=4,
        distinct_cities=3,
        min_reports=200,
    )
    assert too_small.ready is False

    one_material = assess_ml_readiness(
        report_count=500,
        distinct_materials=2,
        distinct_cities=3,
        min_reports=200,
    )
    assert one_material.ready is False

    one_city = assess_ml_readiness(
        report_count=500,
        distinct_materials=4,
        distinct_cities=1,
        min_reports=200,
    )
    assert one_city.ready is False

    ready = assess_ml_readiness(
        report_count=500,
        distinct_materials=4,
        distinct_cities=3,
        min_reports=200,
    )
    assert ready.ready is True
