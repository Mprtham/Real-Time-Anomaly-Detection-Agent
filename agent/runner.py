"""
Agent runner: consumes anomaly_alerts from Redpanda and runs
each through the LangGraph pipeline. Runs in its own thread.
"""

from __future__ import annotations

import json
import os
import threading

from confluent_kafka import Consumer, KafkaError, KafkaException
from dotenv import load_dotenv

from agent.graph import get_graph

load_dotenv()

BROKERS     = os.getenv("REDPANDA_BROKERS", "localhost:9092")
ALERT_TOPIC = "anomaly_alerts"


class AgentRunner:
    def __init__(self, processor, sqlite_store, slack, rca_producer=None, on_anomaly_processed=None):
        self.processor             = processor
        self.sqlite_store          = sqlite_store
        self.slack                 = slack
        self.rca_producer          = rca_producer
        self._on_anomaly_processed = on_anomaly_processed  # optional callback(anomaly_dict)
        self._running              = False
        self._thread: threading.Thread | None = None
        self.current_node: str    = "idle"
        self.processed_count: int = 0

        self.consumer = Consumer({
            "bootstrap.servers":  BROKERS,
            "group.id":           "sentinel-agent",
            "auto.offset.reset":  "latest",
            "enable.auto.commit": True,
        })

    def _run_agent(self, anomaly: dict):
        graph = get_graph()
        initial_state = {
            "anomaly_event":  anomaly,
            "_processor":     self.processor,
            "_sqlite_store":  self.sqlite_store,
            "_slack":         self.slack,
            "_rca_producer":  self.rca_producer,
        }
        self.current_node = "triage"
        print(f"[agent] processing anomaly {anomaly.get('anomaly_id')} ({anomaly.get('anomaly_type')})")

        for step in graph.stream(initial_state):
            node_name = next(iter(step.keys()), "")
            self.current_node = node_name
            print(f"[agent] ▶ {node_name}")

        self.current_node = "idle"
        self.processed_count += 1

        # Fire callback so callers (e.g. api/main.py) can broadcast via WebSocket
        if self._on_anomaly_processed:
            try:
                self._on_anomaly_processed(anomaly)
            except Exception as e:
                print(f"[agent_runner] on_anomaly_processed callback failed: {e}")

    def _loop(self):
        self._running = True
        self.consumer.subscribe([ALERT_TOPIC])
        print(f"[agent_runner] subscribed to '{ALERT_TOPIC}'")

        while self._running:
            msg = self.consumer.poll(timeout=0.5)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(msg.error())

            try:
                anomaly = json.loads(msg.value().decode("utf-8"))
                self._run_agent(anomaly)
            except Exception as e:
                print(f"[agent_runner] error processing anomaly: {e}")

        self.consumer.close()
        print("[agent_runner] stopped")

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[agent_runner] started")

    def stop(self):
        self._running = False
