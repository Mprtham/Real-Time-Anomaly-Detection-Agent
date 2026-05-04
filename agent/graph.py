"""
LangGraph StateGraph definition for sentinel.

State flows:
  triage → (noise → END) | (real/uncertain → context_fetch → rca_writer → decision → END)
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent.nodes.context_fetch import context_fetch_node
from agent.nodes.decision import decision_node
from agent.nodes.rca_writer import rca_writer_node
from agent.nodes.triage import triage_node


class AgentState(TypedDict, total=False):
    # Core event
    anomaly_event:   dict

    # Triage outputs
    triage_verdict:  str        # "real" | "noise" | "uncertain"
    confidence:      float
    triage_reason:   str

    # Context fetch outputs
    context:         dict

    # RCA writer outputs
    rca_report:      str
    rca_latency_s:   float

    # Decision outputs
    action:          str        # "escalate" | "monitor" | "dismiss"
    severity:        str        # "critical" | "warning" | "info"
    slack_sent:      bool

    # Injected dependencies (not serialized)
    _processor:      object
    _sqlite_store:   object
    _slack:          object
    _rca_producer:   object


def _triage_router(state: AgentState) -> str:
    if state.get("triage_verdict") == "noise":
        return END
    return "context_fetch"


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("triage",        triage_node)
    g.add_node("context_fetch", context_fetch_node)
    g.add_node("rca_writer",    rca_writer_node)
    g.add_node("decision",      decision_node)

    g.set_entry_point("triage")

    g.add_conditional_edges(
        "triage",
        _triage_router,
        {"context_fetch": "context_fetch", END: END},
    )
    g.add_edge("context_fetch", "rca_writer")
    g.add_edge("rca_writer",    "decision")
    g.add_edge("decision",      END)

    return g.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
