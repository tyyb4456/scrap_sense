from decimal import Decimal

from app.schemas.report import ReportDraft
from app.workflows.report_intake.graph import build_report_intake_graph
from app.workflows.report_intake.state import ReportIntakeResult


async def test_valid_report_is_accepted() -> None:
    seen: dict[str, str] = {}

    async def extractor(raw_text: str) -> ReportDraft:
        seen["raw_text"] = raw_text
        return ReportDraft(
            material="copper",
            price_per_kg=Decimal("500"),
            quantity_kg=Decimal("2"),
            city="Multan",
        )

    graph = build_report_intake_graph(extractor)
    result = await graph.ainvoke(
        {
            "reporter_id": "reporter-1",
            "raw_text": "  sold   2kg copper at 500 per kg  ",
        }
    )

    parsed = ReportIntakeResult.model_validate(result)
    assert seen["raw_text"] == "sold 2kg copper at 500 per kg"
    assert parsed.status == "accepted"
    assert parsed.errors == []
    assert parsed.draft is not None
    assert parsed.draft.material == "copper"


async def test_missing_price_requests_clarification() -> None:
    async def extractor(_raw_text: str) -> ReportDraft:
        return ReportDraft(material="copper", quantity_kg=Decimal("2"))

    graph = build_report_intake_graph(extractor)
    result = await graph.ainvoke({"reporter_id": "reporter-1", "raw_text": "sold 2 kg of copper"})

    parsed = ReportIntakeResult.model_validate(result)
    assert parsed.status == "needs_clarification"
    assert parsed.errors == ["Missing price per kg."]
    assert parsed.clarification_question


async def test_extractor_clarification_is_preserved() -> None:
    async def extractor(_raw_text: str) -> ReportDraft:
        return ReportDraft(
            material="plastic",
            price_per_kg=Decimal("40"),
            quantity_kg=Decimal("3"),
            needs_clarification=True,
            clarification_question="Was that 40 rupees per kilogram?",
        )

    graph = build_report_intake_graph(extractor)
    result = await graph.ainvoke(
        {"reporter_id": "reporter-1", "raw_text": "sold 3 kg plastic for 40"}
    )

    parsed = ReportIntakeResult.model_validate(result)
    assert parsed.status == "needs_clarification"
    assert parsed.clarification_question == "Was that 40 rupees per kilogram?"


async def test_extractor_failure_is_rejected_without_leaking_details() -> None:
    async def extractor(_raw_text: str) -> ReportDraft:
        raise RuntimeError("provider secret")

    graph = build_report_intake_graph(extractor)
    result = await graph.ainvoke({"reporter_id": "reporter-1", "raw_text": "sold 2 kg copper"})

    parsed = ReportIntakeResult.model_validate(result)
    assert parsed.status == "rejected"
    assert parsed.errors == ["Could not extract report details."]
    assert "provider secret" not in parsed.model_dump_json()
