from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

_store = None  # injected by main.py


def set_store(store):
    global _store
    _store = store


@router.get("")
def list_anomalies(
    severity: str | None = Query(None, description="Filter by severity: critical|warning|info"),
    limit:    int        = Query(20,   ge=1, le=100),
    offset:   int        = Query(0,    ge=0),
):
    if not _store:
        raise HTTPException(503, "Store not initialised")
    return {"anomalies": _store.list_anomalies(severity=severity, limit=limit, offset=offset)}


@router.get("/{anomaly_id}")
def get_anomaly(anomaly_id: str):
    if not _store:
        raise HTTPException(503, "Store not initialised")
    anomaly = _store.get_anomaly(anomaly_id)
    if not anomaly:
        raise HTTPException(404, f"Anomaly {anomaly_id} not found")
    return anomaly


@router.post("/{anomaly_id}/resolve")
def resolve_anomaly(anomaly_id: str):
    if not _store:
        raise HTTPException(503, "Store not initialised")
    _store.resolve_anomaly(anomaly_id)
    return {"status": "resolved", "anomaly_id": anomaly_id}
