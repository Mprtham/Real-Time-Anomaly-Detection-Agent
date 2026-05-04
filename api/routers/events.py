"""
GET /events/stream — SSE stream of live raw events (last N buffered)
"""

import asyncio
import json
from collections import deque
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/events", tags=["events"])

# Shared ring buffer filled by consumer thread — imported by main.py
_event_buffer: deque = deque(maxlen=500)


def push_event(event: dict):
    _event_buffer.appendleft(event)


async def _event_stream() -> AsyncGenerator[str, None]:
    seen = set()
    while True:
        for event in list(_event_buffer):
            eid = event.get("event_id")
            if eid and eid not in seen:
                seen.add(eid)
                yield f"data: {json.dumps(event)}\n\n"
        # Keep seen set bounded
        if len(seen) > 1000:
            seen = set(list(seen)[-500:])
        await asyncio.sleep(0.1)


@router.get("/stream")
async def event_stream():
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
