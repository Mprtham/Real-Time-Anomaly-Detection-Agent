"""
Local development runner — no Redpanda / Docker required.
Wires everything via in-process queues and threads.

Usage:
    python run_local.py
"""

import asyncio
import contextlib
import dataclasses
import os
import random
import threading
import time
from queue import Queue

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from agent.graph import get_graph
from api.db.sqlite import SQLiteStore
from api.routers import anomalies as anomalies_router
from api.routers import events as events_router
from api.routers import metrics as metrics_router
from api.routers import rca as rca_router
from integrations.slack import SlackIntegration
from pipeline.processor import StreamProcessor
from simulator.anomaly_injector import AnomalyInjector
from simulator.event_generator import EVENT_WEIGHTS, PRICE_RANGE, EventGenerator, _make_event
from simulator.schema import PRODUCTS

# ── shared state ───────────────────────────────────────────────────
anomaly_queue = Queue()
store         = SQLiteStore()
slack         = SlackIntegration()
processor     = StreamProcessor(anomaly_queue=anomaly_queue, tick_interval=10.0)
generator     = EventGenerator(rate=80, local_mode=True)
injector      = AnomalyInjector(generator=generator, chaos_mode=False)

# ── WebSocket state ────────────────────────────────────────────────
_ws_connections: list[WebSocket] = []
_main_loop: asyncio.AbstractEventLoop | None = None


def _schedule_broadcast(payload: dict):
    """Thread-safe: schedule a WS broadcast from agent thread onto the event loop."""
    if _main_loop and not _main_loop.is_closed():
        asyncio.run_coroutine_threadsafe(_ws_broadcast(payload), _main_loop)


async def _ws_broadcast(payload: dict):
    dead = []
    for ws in list(_ws_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_connections:
            _ws_connections.remove(ws)


# ── local event generator (no Kafka) ──────────────────────────────
def _local_run():
    """Generates events and feeds them directly to the processor."""
    event_type_keys = list(EVENT_WEIGHTS.keys())
    generator._running = True
    print(f"[local-generator] starting at ~{generator.rate} events/sec (no Kafka)")

    while generator._running:
        # Pick event_type using adjusted weights so injection overrides work
        if generator.force_error:
            chosen_type = "error"
        else:
            weights = generator._adjusted_weights()
            chosen_type = random.choices(event_type_keys, weights=weights)[0]

        event = _make_event(
            latency_override=generator.latency_override,
            status_override=generator.status_override,
            amount_multiplier=generator.amount_multiplier,
            force_error=generator.force_error,
        )

        # Reconcile event_type with our adjusted-weight choice
        if not generator.force_error and chosen_type != event.event_type:
            if chosen_type == "purchase" and event.event_type != "purchase":
                product_id = random.choice(PRODUCTS)
                key = product_id.replace("prod_", "")
                lo, hi = PRICE_RANGE.get(key, (49.99, 99.99))
                amount = round(random.uniform(lo, hi) * generator.amount_multiplier, 2)
                event = dataclasses.replace(
                    event, event_type="purchase", product_id=product_id, amount_usd=amount
                )
            elif chosen_type != "purchase" and event.event_type == "purchase":
                event = dataclasses.replace(
                    event, event_type=chosen_type, amount_usd=None, product_id=None
                )

        ed = event.to_dict()
        processor.ingest(ed)
        events_router.push_event(ed)
        time.sleep(random.expovariate(generator.rate))

    print("[local-generator] stopped")


generator.run = _local_run


# ── local agent runner (reads queue directly) ──────────────────────
class LocalAgentRunner:
    def __init__(self):
        self._running        = False
        self._thread         = None
        self.current_node    = "idle"
        self.processed_count = 0

    def _run_agent(self, anomaly: dict):
        graph = get_graph()
        initial = {
            "anomaly_event": anomaly,
            "_processor":    processor,
            "_sqlite_store": store,
            "_slack":        slack,
            "_rca_producer": None,
        }
        self.current_node = "triage"
        print(f"[agent] processing {anomaly.get('anomaly_id')} ({anomaly.get('anomaly_type')})")

        final_node_state: dict = {}
        for step in graph.stream(initial):
            node_name = next(iter(step.keys()), "")
            self.current_node = node_name
            final_node_state.update(step.get(node_name, {}))
            print(f"[agent] ▶ {node_name}")

        self.current_node = "idle"
        self.processed_count += 1

        # Push processed anomaly to WebSocket clients (consistent with agent/runner.py:
        # always attempt; dismissed anomalies won't be in SQLite so get_anomaly returns None)
        saved = store.get_anomaly(anomaly.get("anomaly_id", ""))
        if saved:
            saved["has_rca"] = bool(store.get_rca(saved["anomaly_id"]))
            _schedule_broadcast({"type": "anomaly", "data": saved})

    def _loop(self):
        self._running = True
        while self._running:
            try:
                anomaly = anomaly_queue.get(timeout=1.0)
                self._run_agent(anomaly)
            except Exception:
                pass

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[local-agent] started")

    def stop(self):
        self._running = False


agent_runner = LocalAgentRunner()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_event_loop()

    if not os.getenv("GROQ_API_KEY"):
        print("\n[sentinel] WARNING: GROQ_API_KEY is not set.")
        print("[sentinel]   The agent will run but LLM calls (triage + RCA) will fail.")
        print("[sentinel]   Get a free key at https://console.groq.com and add it to .env\n")

    processor.start()
    gen_thread = threading.Thread(target=generator.run, daemon=True)
    gen_thread.start()
    injector.start()
    agent_runner.start()

    print("\n[sentinel] running in LOCAL mode (no Redpanda)")
    print("[sentinel]   API  -> http://localhost:8000")
    print("[sentinel]   UI   -> http://localhost:8000")
    print("[sentinel]   Docs -> http://localhost:8000/docs")
    print("[sentinel]   Reset demo: POST http://localhost:8000/demo/reset\n")

    yield

    generator.stop()
    processor.stop()
    agent_runner.stop()


# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(title="sentinel (local)", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router.router)
app.include_router(anomalies_router.router)
app.include_router(rca_router.router)
app.include_router(metrics_router.router)


class _FakeConsumer:
    """Satisfies metrics_router.set_deps which expects a consumer with events_per_sec."""
    events_per_sec = property(
        lambda self: (
            processor.get_recent_windows(1)[0].get("total_events", 0) / 60
            if processor.get_recent_windows(1)
            else 0.0
        )
    )


_fake_consumer = _FakeConsumer()
anomalies_router.set_store(store)
rca_router.set_store(store)
metrics_router.set_deps(_fake_consumer, processor, store, agent_runner)


@app.post("/inject/{anomaly_type}")
def inject_anomaly(anomaly_type: str):
    try:
        injector.inject_now(anomaly_type)
        return {"status": "injected", "anomaly_type": anomaly_type}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "local"}


@app.post("/demo/reset")
def demo_reset():
    """Wipe all anomaly and RCA history — useful for clean demo restarts."""
    try:
        with store._lock:
            con = store._connect()
            con.execute("DELETE FROM rca_reports")
            con.execute("DELETE FROM anomalies")
            con.commit()
            con.close()
        return {"status": "reset", "message": "Anomaly and RCA history cleared."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)


# Serve frontend
_frontend = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
