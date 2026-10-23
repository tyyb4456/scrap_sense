from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes import Extractor, make_extract_node, normalize, validate
from .state import ReportIntakeRequest, ReportIntakeResult, ReportIntakeState


def build_report_intake_graph(extractor: Extractor) -> CompiledStateGraph:
    builder: StateGraph[ReportIntakeState, None, ReportIntakeRequest, ReportIntakeResult] = (
        StateGraph(
            ReportIntakeState,
            input_schema=ReportIntakeRequest,
            output_schema=ReportIntakeResult,
        )
    )
    builder.add_node("normalize", normalize)
    builder.add_node("extract", make_extract_node(extractor))
    builder.add_node("validate", validate)

    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "extract")
    builder.add_edge("extract", "validate")
    builder.add_edge("validate", END)

    return builder.compile(name="report_intake")
