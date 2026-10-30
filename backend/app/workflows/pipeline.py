"""Report-to-final-report pipeline workflow for ScrapSense.

Execution path:

    START -> report_draft -> validate_and_build
                 |                    |
                 |              invalid / missing
                 |                    v
                 |                   END (clarification, no persistence)
                 |
                 +--> deterministic_check -> ml_check
                                                    |
                                     +--------------+--------------+
                                     |                             |
                              suspicious & LLM on            pass/insufficient
                                     v                             |
                                 llm_check                         |
                                     |                             |
                                     +--------------+--------------+
                                                    v
                                                  accept -> finalize_report -> END

Tier 1 (median/MAD) is deterministic. Tier 2 (ML) is disabled until a trained,
evaluated artifact and enough real data exist. Tier 3 (LLM) is reached only for
statistically suspicious reports and only when `USE_LLM_REASONING` is enabled;
it can add context but never clears the flag or overrides validation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.llm import build_xkiro_llm
from app.schemas.report import AnomalyOutcome, AnomalyVerdict, LLMJudgment, ReportDraft
from app.services.anomaly_detection import evaluate_report_statistical
from app.services.ml_anomaly import evaluate_ml_check
from app.services.report_validation import clarification_question, validate_report_draft
from app.services.reports import save_report
from app.workflows.state import PipelineState

logger = logging.getLogger(__name__)

settings = get_settings()

_model = None
_structured_extraction_model = None
_structured_llm_judge = None


def _chat_model():
    global _model
    if _model is None:
        _model = build_xkiro_llm(settings=settings)
    return _model


EXTRACTION_PROMPT = """
Extract the scrap sale details from the picker's message below.

Return only details supported by the message. Use PKR unless another currency is
stated. Use kg as the unit unless the message clearly uses something else. If the
message states a sale date, include it; otherwise leave it null. A city is
required for price estimation: leave it null when the message does not state a
city, and ask for the city rather than guessing one. Leave missing fields null and
ask one short clarification question when a required detail is missing. Do not
estimate a price that was not stated. Do not infer a precise address from a vague
location.

Message:
{raw_text}
""".strip()

LLM_JUDGE_PROMPT = """
A scrap sale report is statistically unusual compared with other reports. Decide
whether the available context suggests a legitimate outlier or likely bad data.

Report:
- Material: {material}
- Price per kg: {price_per_kg}
- Quantity kg: {quantity_kg}
- Currency/unit: {currency}/{unit}
- Location: {location}
- Reported sale time: {observed_at}

Deterministic comparison:
- Sample size: {sample_size}
- Median price: {median_price_per_kg}
- Median absolute deviation: {mad_price_per_kg}
- Statistical verdict: {statistical_reason}

Rules:
- Do not invent market data or claim fraud.
- An unusual price can be legitimate because of material quality, quantity,
  location, timing, or transaction context.
- Use only the information above. If context is insufficient, say so.
- This assessment cannot approve the report; a human reviewer decides.

Give a short reason and a confidence between 0 and 1.
""".strip()


def _extraction_model():
    global _structured_extraction_model
    if _structured_extraction_model is None:
        _structured_extraction_model = _chat_model().with_structured_output(ReportDraft)
    return _structured_extraction_model


def _judge_model():
    global _structured_llm_judge
    if _structured_llm_judge is None:
        _structured_llm_judge = _chat_model().with_structured_output(LLMJudgment)
    return _structured_llm_judge


def _neutral_verdict(
    method: str,
    *,
    outcome: AnomalyOutcome = "pass",
) -> AnomalyVerdict:
    return AnomalyVerdict(
        is_anomalous=False,
        reason="No anomaly conclusion was drawn.",
        method=method,
        confidence=0.0,
        outcome=outcome,
    )


def _original_message_from_config(config: RunnableConfig | None) -> str | None:
    """Read the picker message carried as trusted run configuration."""
    if not config:
        return None
    configurable = config.get("configurable") or {}
    value = configurable.get("original_message")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _original_message(
    state: PipelineState,
    config: RunnableConfig | None,
) -> str | None:
    """Return the verbatim picker message, never a coordinator description."""
    value = state.get("original_message")
    if isinstance(value, str) and value.strip():
        return value
    return _original_message_from_config(config)


def report_draft(
    state: PipelineState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Single LLM call: original picker message -> structured fields."""
    raw_text = _original_message(state, config)
    if raw_text is None:
        logger.error("No original picker message available; refusing extraction")
        draft = ReportDraft(
            material=None,
            price_per_kg=None,
            quantity_kg=None,
            currency="PKR",
            unit="kg",
            city=None,
            area=None,
            observed_at=None,
            confidence=None,
            needs_clarification=True,
            clarification_question=(
                "I couldn't verify the original message, so I didn't save a report. "
                "Please resend your sale details."
            ),
        )
    else:
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
        except Exception as exc:
            logger.warning(
                "Extraction failed (%s), falling back to clarification",
                type(exc).__name__,
            )
            draft = ReportDraft(
                material=None,
                price_per_kg=None,
                quantity_kg=None,
                currency="PKR",
                unit="kg",
                city=None,
                area=None,
                observed_at=None,
                confidence=None,
                needs_clarification=True,
                clarification_question=(
                    "Could you clarify the material type, quantity, and price?"
                ),
            )

    return {
        "report_draft": draft,
        "validation_result": None,
        "deterministic_result": None,
        "ml_result": None,
        "llm_result": None,
        "verdict": None,
        "final_report": None,
        "structured_response": None,
    }


def _report_draft_node(
    state: PipelineState,
    config: RunnableConfig,
) -> dict[str, Any]:
    return report_draft(state, config)


def validate_and_build(state: PipelineState) -> dict[str, Any]:
    """Run deterministic validation before any anomaly or LLM tier."""
    draft = state.get("report_draft")
    result = validate_report_draft(draft)

    if draft is None or not result.is_valid:
        question = clarification_question(result, draft)
        logger.info("Report invalid; codes=%s", sorted(result.codes))
        return {
            "validation_result": result,
            "messages": [AIMessage(content=question)],
        }

    return {"validation_result": result}


def route_after_validation(state: PipelineState) -> str:
    result = state.get("validation_result")
    if result is None or not result.is_valid:
        return "end"
    logger.info("Routing after validation -> 'deterministic_check'")
    return "deterministic_check"


async def deterministic_check_node(state: PipelineState) -> dict[str, Any]:
    """Tier 1: compare with comparable, recent, accepted reports using MAD."""
    draft = state.get("report_draft")
    if draft is None:
        return {"deterministic_result": _neutral_verdict("mad", outcome="unavailable")}

    try:
        verdict = await evaluate_report_statistical(draft, settings=settings)
    except Exception as exc:
        logger.warning(
            "Deterministic anomaly comparison failed (%s); continuing",
            type(exc).__name__,
        )
        verdict = AnomalyVerdict(
            is_anomalous=False,
            reason="Historical comparison was unavailable; no anomaly conclusion was drawn.",
            method="mad",
            confidence=0.0,
            outcome="unavailable",
        )

    logger.info(
        "Deterministic check: outcome=%s sample=%d anomalous=%s",
        verdict.outcome,
        verdict.sample_size,
        verdict.is_anomalous,
    )
    return {"deterministic_result": verdict}


def ml_check_node(state: PipelineState) -> dict[str, Any]:
    """Tier 2: explicit disabled/unavailable fallback for model-based detection."""
    verdict = evaluate_ml_check(settings)
    logger.info("ML check: outcome=%s", verdict.outcome)
    return {"ml_result": verdict}


def _suspicious_verdicts(state: PipelineState) -> list[AnomalyVerdict]:
    results = [
        state.get("deterministic_result"),
        state.get("ml_result"),
        state.get("llm_result"),
        state.get("verdict"),
    ]
    return [result for result in results if result is not None and result.is_anomalous]


def _retain_suspicion(state: PipelineState, note: str) -> AnomalyVerdict:
    suspicious = _suspicious_verdicts(state)
    if not suspicious:
        return AnomalyVerdict(
            is_anomalous=False,
            reason=note,
            method="llm",
            confidence=0.0,
            outcome="error",
        )

    primary = suspicious[0]
    return AnomalyVerdict(
        is_anomalous=True,
        reason=f"{primary.reason} {note}".strip(),
        method="llm",
        confidence=primary.confidence,
        outcome="suspicious",
        sample_size=primary.sample_size,
        median_price_per_kg=primary.median_price_per_kg,
        mad_price_per_kg=primary.mad_price_per_kg,
    )


async def llm_check_node(state: PipelineState) -> dict[str, Any]:
    """Tier 3: contextual review of an already-suspicious report.

    The LLM can explain or strengthen a flag, but a statistical flag is never
    cleared automatically and structural validation is never revisited.
    """
    draft = state.get("report_draft")
    suspicious = _suspicious_verdicts(state)
    if draft is None or not suspicious:
        return {"llm_result": _neutral_verdict("llm", outcome="pass")}

    primary = suspicious[0]
    prompt = LLM_JUDGE_PROMPT.format(
        material=draft.material,
        price_per_kg=draft.price_per_kg,
        quantity_kg=draft.quantity_kg,
        currency=draft.currency,
        unit=draft.unit,
        location=", ".join(part for part in (draft.area, draft.city) if part) or "unknown",
        observed_at=draft.observed_at or "not stated",
        sample_size=primary.sample_size,
        median_price_per_kg=primary.median_price_per_kg,
        mad_price_per_kg=primary.mad_price_per_kg,
        statistical_reason=primary.reason,
    )

    try:
        judgment = await asyncio.wait_for(
            _judge_model().ainvoke([{"role": "user", "content": prompt}]),
            timeout=settings.anomaly_llm_timeout_seconds,
        )
        if not isinstance(judgment, LLMJudgment):
            judgment = LLMJudgment.model_validate(judgment)
    except TimeoutError:
        logger.warning("LLM anomaly review timed out; retaining the statistical flag")
        return {"llm_result": _retain_suspicion(state, "LLM review timed out.")}
    except Exception as exc:
        logger.warning(
            "LLM anomaly review failed (%s); retaining the statistical flag",
            type(exc).__name__,
        )
        return {"llm_result": _retain_suspicion(state, "LLM review was unavailable.")}

    reason = (
        f"Statistical flag retained for review ({judgment.assessment}). "
        f"Contextual assessment: {judgment.reason}"
    )
    verdict = AnomalyVerdict(
        is_anomalous=True,
        reason=reason,
        method="llm",
        confidence=max(primary.confidence, judgment.confidence),
        outcome="suspicious",
        sample_size=primary.sample_size,
        median_price_per_kg=primary.median_price_per_kg,
        mad_price_per_kg=primary.mad_price_per_kg,
    )
    return {"llm_result": verdict}


def _picker_id_from_config(config: RunnableConfig) -> str:
    """Prefer the authenticated picker id over the conversation thread id."""
    configurable = config.get("configurable") or {}
    picker_id = configurable.get("picker_id")
    if isinstance(picker_id, str) and picker_id:
        return picker_id

    thread_id = configurable.get("thread_id")
    return thread_id if isinstance(thread_id, str) and thread_id else "unknown"


def _resolve_verdict(state: PipelineState) -> AnomalyVerdict:
    """Merge tier results. Any suspicious result keeps the report flagged."""
    results = [
        state.get("deterministic_result"),
        state.get("ml_result"),
        state.get("llm_result"),
        state.get("verdict"),
    ]
    present = [result for result in results if result is not None]
    suspicious = [result for result in present if result.is_anomalous]

    if suspicious:
        primary = suspicious[0]
        reasons: list[str] = []
        for result in suspicious:
            if result.reason and result.reason not in reasons:
                reasons.append(result.reason)
        method = "llm" if state.get("llm_result") is not None else primary.method
        return AnomalyVerdict(
            is_anomalous=True,
            reason=" ".join(reasons),
            method=method,
            confidence=max(result.confidence for result in suspicious),
            outcome="suspicious",
            sample_size=primary.sample_size,
            median_price_per_kg=primary.median_price_per_kg,
            mad_price_per_kg=primary.mad_price_per_kg,
        )

    deterministic = state.get("deterministic_result")
    if deterministic is not None:
        return deterministic
    if state.get("verdict") is not None:
        return state["verdict"]  # type: ignore[return-value]
    ml = state.get("ml_result")
    if ml is not None:
        return ml
    return _neutral_verdict("mad", outcome="unavailable")


def accept_node(state: PipelineState) -> dict[str, Any]:
    verdict = _resolve_verdict(state)
    draft = state.get("report_draft")
    material = draft.material if draft is not None else "this material"

    if verdict.is_anomalous:
        summary = (
            f"Report flagged for review: {verdict.reason} "
            "It may be legitimate, but it will not affect prices until reviewed."
        )
    elif verdict.outcome == "insufficient_evidence":
        summary = (
            f"Report accepted for {material}. There was not enough comparable "
            "history to run a statistical check."
        )
    elif verdict.outcome == "unavailable":
        summary = (
            f"Report accepted for {material}. Anomaly checks were unavailable, so "
            "no statistical conclusion was drawn."
        )
    else:
        summary = f"Report accepted for {material}."

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
    validation = validate_report_draft(draft)
    if draft is None or not validation.is_valid:
        return {
            "messages": [AIMessage(content="Could not build a final report.")]
        }

    verdict = _resolve_verdict(state)
    raw_text = _original_message(state, config)
    if raw_text is None:
        logger.error(
            "Refusing to persist a report without the original picker message"
        )
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I couldn't verify the original message, so the report was "
                        "not saved. Please resend your sale details."
                    )
                )
            ]
        }
    picker_id = _picker_id_from_config(config)

    try:
        final_report = await save_report(
            picker_id=picker_id,
            raw_text=raw_text,
            draft=draft,
            verdict=verdict,
        )
    except Exception as exc:
        logger.warning("Failed to persist final report (%s)", type(exc).__name__)
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
        summary = f"{summary} It is excluded from price estimates pending review."

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
    flagged = bool(_suspicious_verdicts(state))
    target = "llm_check" if (settings.use_llm_reasoning and flagged) else "accept"
    logger.info("Routing after ML check (flagged=%s) -> '%s'", flagged, target)
    return target


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("report_draft", _report_draft_node)
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
    graph.add_edge("llm_check", "accept")
    graph.add_edge("accept", "finalize_report")
    graph.add_edge("finalize_report", END)

    return graph.compile(name="scrap_report_pipeline")


pipeline = build_pipeline()
