"""
Context fetch node: pulls baseline stats, recent windows, and adjacent
metrics so the RCA writer has concrete numbers to work with.
"""

from __future__ import annotations

from agent.tools import (
    get_adjacent_metrics,
    get_baseline_stats,
    get_recent_windows_table,
)


def context_fetch_node(state: dict) -> dict:
    processor = state.get("_processor")
    anomaly   = state["anomaly_event"]

    context = {}

    if processor:
        context["baseline_stats"]     = get_baseline_stats(processor)
        context["recent_windows"]     = get_recent_windows_table(processor, n=10)
        context["adjacent_metrics"]   = get_adjacent_metrics(processor, anomaly.get("anomaly_type", ""))
    else:
        context["baseline_stats"]   = "(processor unavailable)"
        context["recent_windows"]   = "(processor unavailable)"
        context["adjacent_metrics"] = "(processor unavailable)"

    print(f"[context_fetch] context assembled for anomaly {anomaly.get('anomaly_id')}")
    return {**state, "context": context}
