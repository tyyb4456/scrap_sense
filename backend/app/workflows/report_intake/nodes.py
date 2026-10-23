import logging
import re
from collections.abc import Awaitable, Callable

from app.schemas.report import ReportDraft

from .state import ReportIntakeState

logger = logging.getLogger(__name__)

Extractor = Callable[[str], Awaitable[ReportDraft]]

_WHITESPACE_RE = re.compile(r"\s+")


async def normalize(state: ReportIntakeState):
    raw_text = _WHITESPACE_RE.sub(" ", state.get("raw_text", "")).strip()
    return {"raw_text": raw_text}


def make_extract_node(extractor: Extractor):
    async def extract(state: ReportIntakeState):
        try:
            draft = await extractor(state["raw_text"])
        except Exception:
            logger.exception("Report intake extraction failed")
            return {
                "draft": None,
                "errors": ["Could not extract report details."],
                "status": "rejected",
            }
        return {"draft": draft, "errors": []}

    return extract


async def validate(state: ReportIntakeState) -> dict:
    draft = state.get("draft")
    if draft is None:
        return {
            "status": "rejected",
            "errors": state.get("errors") or ["No report details were extracted."],
        }

    missing = []
    if not draft.material:
        missing.append("material")
    if draft.price_per_kg is None:
        missing.append("price per kg")
    if draft.quantity_kg is None:
        missing.append("quantity in kg")

    if missing:
        return {
            "status": "needs_clarification",
            "errors": [f"Missing {field}." for field in missing],
            "clarification_question": draft.clarification_question
            or "What material, quantity, and price per kg did you sell?",
        }

    if draft.needs_clarification:
        return {
            "status": "needs_clarification",
            "errors": [],
            "clarification_question": draft.clarification_question
            or "Could you clarify the sale details?",
        }

    return {"status": "accepted", "errors": [], "clarification_question": None}
