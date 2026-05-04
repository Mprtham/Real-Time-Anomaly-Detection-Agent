"""
FastAPI application entry point.
Starts all background threads on lifespan startup.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from queue import Queue

from confluent_kafka import Producer
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.runner import AgentRunner
from api.routers import anomalies as anomalies_router
from api.routers import events as events_router
from api.routers import metrics as metrics_router
from api.routers import rca as rca_router
from api.db.sqlite import SQLiteStore
from integrations.slack import SlackIntegration
from pipeline.consumer import PipelineConsumer
from pipeline.processor import StreamProcessor
from simulator.anomaly_injector import AnomalyInjector
from simulator.event_generator import EventGenerator

load_dotenv()

BROKERS = os.getenv("REDPANDA_BROKERS", "localhost:9092")

# WebSocket connection manager
class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


ws_manager = WSManager()

# Populated at lifespan startup so callbacks can use it
_main_loop: asyncio.AbstractEventLoop | None = None
_store_ref = None

# Global references so routes can access them
_generator = None
_injector  = None
_consumer_obj = None
_processor_obj = None


async def _broadcast_processed_anomaly(anomaly: dict):
    """Fetch the saved anomaly from SQLite and push to all WS clients."""
    if not _store_ref:
        return
    saved = _store_ref.get_anomaly(anomaly.get("anomaly_id", ""))
    if saved:
        saved["has_rca"] = bool(_store_ref.get_rca(saved["anomaly_id"]))
        await ws_manager.broadcast({"type": "anomaly", "data": saved})


def _on_anomaly_processed(anomaly: dict):
    """Thread-safe callback: schedules WS broadcast from agent thread."""
    if _main_loop and not _main_loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            _broadcast_processed_anomaly(anomaly), _main_loop
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _generator, _injector, _consumer_obj, _processor_obj, _main_loop, _store_ref

    _main_loop = asyncio.get_event_loop()

    anomaly_queue = Queue()
    store         = SQLiteStore()
    _store_ref    = store
    slack         = SlackIntegration()

    rca_producer = Producer({"bootstrap.servers": BROKERS})

    processor = StreamProcessor(anomaly_queue=anomaly_queue, tick_interval=30.0)
    _processor_obj = processor

    # Wrap ingest so events also get pushed to SSE buffer + WS
    original_ingest = processor.ingest

    def patched_ingest(event: dict):
        original_ingest(event)
        events_router.push_event(event)

    processor.ingest = patched_ingest

    consumer = PipelineConsumer(processor=processor)
    _consumer_obj = consumer

    generator = EventGenerator(rate=100)
    injector  = AnomalyInjector(generator=generator, chaos_mode=False)
    _generator = generator
    _injector  = injector

    agent_runner = AgentRunner(
        processor=processor,
        sqlite_store=store,
        slack=slack,
        rca_producer=rca_producer,
        on_anomaly_processed=_on_anomaly_processed,
    )

    # Wire dependencies into routers
    anomalies_router.set_store(store)
    rca_router.set_store(store)
    metrics_router.set_deps(consumer, processor, store, agent_runner)

    # Start background threads
    processor.start()
    consumer.start()
    generator_thread = __import__("threading").Thread(target=generator.run, daemon=True)
    generator_thread.start()
    injector.start()
    agent_runner.start()

    print("[sentinel] all systems running")
    yield

    generator.stop()
    consumer.stop()
    processor.stop()
    agent_runner.stop()
    print("[sentinel] shutdown complete")


app = FastAPI(
    title="sentinel",
    description="Real-time anomaly detection agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=json.loads(os.getenv("CORS_ORIGINS", '["*"]')),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router.router)
app.include_router(anomalies_router.router)
app.include_router(rca_router.router)
app.include_router(metrics_router.router)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/inject/{anomaly_type}")
def inject_anomaly(anomaly_type: str):
    if not _injector:
        return {"error": "injector not ready"}
    try:
        _injector.inject_now(anomaly_type)
        return {"status": "injected", "anomaly_type": anomaly_type}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve frontend
import os
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("API_PORT", 8000)), reload=False)
