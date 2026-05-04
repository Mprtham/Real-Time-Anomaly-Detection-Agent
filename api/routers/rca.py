from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/rca", tags=["rca"])

_store = None


def set_store(store):
    global _store
    _store = store


@router.get("/{anomaly_id}")
def get_rca(anomaly_id: str):
    if not _store:
        raise HTTPException(503, "Store not initialised")
    rca = _store.get_rca(anomaly_id)
    if not rca:
        raise HTTPException(404, f"RCA for anomaly {anomaly_id} not found")
    return rca
