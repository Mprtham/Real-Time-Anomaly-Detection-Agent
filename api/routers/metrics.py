from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["metrics"])

_consumer    = None
_processor   = None
_store       = None
_agent_runner = None


def set_deps(consumer, processor, store, agent_runner):
    global _consumer, _processor, _store, _agent_runner
    _consumer     = consumer
    _processor    = processor
    _store        = store
    _agent_runner = agent_runner


@router.get("")
def get_metrics():
    eps   = round(_consumer.events_per_sec, 1) if _consumer else 0.0
    stats = _store.get_stats()                  if _store    else {}

    recent_windows = _processor.get_recent_windows(n=1) if _processor else []
    latest_window  = recent_windows[0] if recent_windows else {}

    return {
        "events_per_sec":        eps,
        "anomalies_last_hour":   stats.get("last_hour", 0),
        "anomalies_total":       stats.get("total", 0),
        "rca_reports_total":     stats.get("with_rca", 0),
        "agent_current_node":    _agent_runner.current_node if _agent_runner else "idle",
        "agent_processed_total": _agent_runner.processed_count if _agent_runner else 0,
        "latest_window":         latest_window,
    }
