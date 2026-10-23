"""
Subagent definitions for ScrapSense workflows.
"""

from __future__ import annotations

from deepagents import CompiledSubAgent

from app.workflows.pipeline import pipeline

scrap_pipeline_agent = CompiledSubAgent(
    name="scrap_report_pipeline",
    description=(
        "Takes a picker's raw sale message and returns a validated price "
        "report plus an anomaly verdict, in one call. Flags reports that "
        "need the picker's confirmation instead of guessing."
    ),
    runnable=pipeline,
)