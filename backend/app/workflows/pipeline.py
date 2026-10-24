"""
Report-to-final-report pipeline workflow for ScrapSense.

Graph structure:

    START -> report_draft -> validate_and_build --+--> deterministic_check
                                                  |            |
                                                  |            v
                                                  |         ml_check
                                                  |            |
                                                  |      +-----+-----+
                                                  |      |           |
                                                  |      v           v
                                                  |   llm_check    accept
                                                  |      |           |
                                                  |      +-----+-----+
                                                  |            |
                                                  |            v
                                                  +-->    finalize_report -> END
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.schemas.report import AnomalyVerdict, LLMJudgment, ReportDraft
from app.services.reports import save_report
from app.workflows.state import PipelineState

logger = logging.getLogger(__name__)

settings = get_settings()
model = init_chat_model(settings.ai_model)

_structured_extraction_model = None
_structured_llm_judge = None

EXTRACTION_PROMPT = """
Extract the scrap sale details from the picker's message below.

Return only details supported by the message. Use PKR unless another currency is
stated. Leave missing fields null and ask one short clarification question when a
required detail is missing.

Message:
{raw_text}
""".strip()

LLM_JUDGE_PROMPT = """
A scrap sale report was flagged as a possible anomaly. Decide whether it is a
legitimate outlier or bad data.

Material: {material}
Price per kg: {price_per_kg}
Quantity kg: {quantity_kg}
Location: {location}

Give a short reason and a confidence between 0 and 1.
""".strip()


def _extraction_model():
    global _structured_extraction_model
    if _structured_extraction_model is None:
        _structured_extraction_model = model.with_structured_output(ReportDraft)
    return _structured_extraction_model


def _judge_model():
    global _structured_llm_judge
    if _structured_llm_judge is None:
        _structured_llm_judge = model.with_structured_output(LLMJudgment)
    return _structured_llm_judge


def _neutral_verdict(method: str) -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=False,
        reason="Not enough data to evaluate.",
        method=method,
        confidence=0.0,
    )


def _missing_fields(draft: ReportDraft) -> list[str]:
    missing = []
    if not draft.material:
        missing.append("material")
    if draft.price_per_kg is None:
        missing.append("price per kg")
    if draft.quantity_kg is None:
        missing.append("quantity in kg")
    return missing


def report_draft(state: PipelineState) -> dict[str, Any]:
    """Single LLM call: raw text -> structured fields."""
    messages = state.get("messages") or []
    raw_text = str(messages[-1].content) if messages else ""
    logger.info("Extracting report (message length=%d)", len(raw_text))

    prompt = EXTRACTION_PROMPT.format(raw_text=raw_text)

    try:
        draft = _extraction_model().invoke([{"role": "user", "content": prompt}])
        if draft is None:
            raise ValueError("model returned no structured output (None)")
        logger.info(
            "Extraction succeeded: material=%s quantity_kg=%s price_per_kg=%s",
            draft.material,
            draft.quantity_kg,
            draft.price_per_kg,
        )
    except Exception:
        logger.exception("Extraction failed, falling back to unclear report")
        draft = ReportDraft(
            material=None,
            price_per_kg=None,
            quantity_kg=None,
            currency="PKR",
            city=None,
            area=None,
            confidence=None,
            needs_clarification=True,
            clarification_question="Could you clarify the material type, quantity, and price?",
        )

    return {"report_draft": draft}


def validate_and_build(state: PipelineState) -> dict[str, Any]:
    draft = state.get("report_draft")
    if draft is None:
        return {
            "messages": [
                AIMessage(content="Could not extract report details. Please try again.")
            ]
        }

    missing = _missing_fields(draft)
    if missing or draft.needs_clarification:
        question = draft.clarification_question or (
            f"Could you clarify the {', '.join(missing)}?"
            if missing
            else "Could you clarify the sale details?"
        )
        logger.info("Report needs confirmation: missing=%s", missing)
        return {"messages": [AIMessage(content=question)]}

    return {}


def route_after_validation(state: PipelineState) -> str:
    draft = state.get("report_draft")
    if draft is None:
        return "end"
    if _missing_fields(draft) or draft.needs_clarification:
        return "end"
    logger.info("Routing after validation -> 'deterministic_check'")
    return "deterministic_check"


def deterministic_check_node(state: PipelineState) -> dict[str, Any]:
    verdict = _neutral_verdict("deterministic")
    logger.info("Deterministic check: no baseline available")
    return {"deterministic_result": verdict}


def ml_check_node(state: PipelineState) -> dict[str, Any]:
    verdict = _neutral_verdict("ml")
    logger.info("ML check: no trained model available")
    return {"ml_result": verdict}


def llm_check_node(state: PipelineState) -> dict[str, Any]:
    draft = state.get("report_draft")
    if draft is None:
        return {"verdict": _neutral_verdict("llm")}

    prompt = LLM_JUDGE_PROMPT.format(
        material=draft.material,
        price_per_kg=draft.price_per_kg,
        quantity_kg=draft.quantity_kg,
        location=", ".join(
            part for part in (draft.area, draft.city) if part
        )
        or "unknown",
    )

    try:
        judgment = _judge_model().invoke([{"role": "user", "content": prompt}])
        verdict = AnomalyVerdict(
            is_anomalous=judgment.is_anomalous,
            reason=judgment.reason,
            method="llm",
            confidence=judgment.confidence,
        )
    except Exception:
        logger.exception("LLM anomaly check failed")
        verdict = _neutral_verdict("llm")

    return {"verdict": verdict}


def _picker_id_from_config(config: RunnableConfig) -> str:
    """Prefer the authenticated picker id over the conversation thread id."""
    configurable = config.get("configurable") or {}
    picker_id = configurable.get("picker_id")
    if isinstance(picker_id, str) and picker_id:
        return picker_id

    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) and thread_id else "unknown"


def _resolve_verdict(state: PipelineState) -> AnomalyVerdict:
    verdict = state.get("verdict")
    if verdict is not None:
        return verdict

    deterministic = state.get("deterministic_result")
    ml = state.get("ml_result")
    flagged = next(
        (
            result
            for result in (deterministic, ml)
            if result is not None and result.is_anomalous
        ),
        None,
    )
    return flagged or _neutral_verdict("deterministic")


def accept_node(state: PipelineState) -> dict[str, Any]:
    verdict = _resolve_verdict(state)
    draft = state.get("report_draft")
    summary = (
        f"Report accepted for {draft.material}."
        if draft is not None
        else "Report accepted."
    )
    if verdict.is_anomalous:
        summary = f"Report flagged: {verdict.reason}"

    logger.info("Accepting report with verdict=%s", verdict.model_dump())
    return {
        "verdict": verdict,
        "messages": [AIMessage(content=summary)],
    }


async def finalize_report_node(
    state: PipelineState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Build and persist the final report, then expose it to the parent agent."""
    draft = state.get("report_draft")
    if draft is None or _missing_fields(draft):
        return {
            "messages": [AIMessage(content="Could not build a final report.")]
        }

    verdict = _resolve_verdict(state)
    messages = state.get("messages") or []
    raw_text = next(
        (
            str(message.content)
            for message in messages
            if isinstance(message, HumanMessage) and message.content
        ),
        "",
    )
    picker_id = _picker_id_from_config(config)

    try:
        final_report = await save_report(
            picker_id=picker_id,
            raw_text=raw_text,
            draft=draft,
            verdict=verdict,
        )
    except Exception:
        logger.exception("Failed to persist final report")
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I extracted the sale details but could not save the report. "
                        "Please try again."
                    )
                )
            ]
        }

    summary = (
        f"Final report saved for {final_report.material}: "
        f"{final_report.quantity_kg} kg at "
        f"{final_report.price_per_kg} {final_report.currency}/kg."
    )
    if final_report.is_anomalous:
        summary = f"{summary} Flagged: {final_report.anomaly_reason}"

    logger.info("Saved final report %s for picker %s", final_report.id, picker_id)
    return {
        "verdict": verdict,
        "final_report": final_report,
        "structured_response": final_report,
        "messages": [AIMessage(content=summary)],
    }


def route_after_deterministic(state: PipelineState) -> str:
    return "ml_check"


def route_after_ml(state: PipelineState) -> str:
    deterministic = state.get("deterministic_result")
    ml = state.get("ml_result")
    flagged = bool(
        (deterministic is not None and deterministic.is_anomalous)
        or (ml is not None and ml.is_anomalous)
    )
    target = "llm_check" if (settings.use_llm_reasoning and flagged) else "accept"
    logger.info("Routing after ML check (flagged=%s) -> '%s'", flagged, target)
    return target


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("report_draft", report_draft)
    graph.add_node("validate_and_build", validate_and_build)
    graph.add_node("deterministic_check", deterministic_check_node)
    graph.add_node("ml_check", ml_check_node)
    graph.add_node("llm_check", llm_check_node)
    graph.add_node("accept", accept_node)
    graph.add_node("finalize_report", finalize_report_node)

    graph.add_edge(START, "report_draft")
    graph.add_edge("report_draft", "validate_and_build")

    graph.add_conditional_edges(
        "validate_and_build",
        route_after_validation,
        {"deterministic_check": "deterministic_check", "end": END},
    )
    graph.add_conditional_edges(
        "deterministic_check",
        route_after_deterministic,
        {"ml_check": "ml_check"},
    )
    graph.add_conditional_edges(
        "ml_check",
        route_after_ml,
        {"llm_check": "llm_check", "accept": "accept"},
    )
    graph.add_edge("llm_check", "finalize_report")
    graph.add_edge("accept", "finalize_report")
    graph.add_edge("finalize_report", END)

    return graph.compile(name="scrap_report_pipeline")


pipeline = build_pipeline()
