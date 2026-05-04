"""
DuckDB stream processor.

Runs on a 30-second tick:
  1. Upserts 1-minute window aggregates from raw_events
  2. Runs z-score checks on key metrics
  3. Publishes anomaly_alert payloads to a queue consumed by the agent
"""

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from queue import Queue
from typing import Any

import duckdb
from dotenv import load_dotenv

from pipeline.queries import (
    BASELINE_SUMMARY,
    CREATE_RAW_EVENTS,
    CREATE_WINDOWED_METRICS,
    METRIC_HISTORY_TEMPLATE,
    PRUNE_RAW_EVENTS,
    RECENT_WINDOWS,
    UPSERT_WINDOWED_METRICS,
    ZSCORE_QUERY_TEMPLATE,
)

load_dotenv()

Z_THRESHOLD = float(os.getenv("ANOMALY_Z_THRESHOLD", "3.0"))

# (metric_column, anomaly_type, direction)
# direction: "high" | "low" | "both"
MONITORED_METRICS = [
    ("revenue",     "revenue_crash",     "low"),
    ("revenue",     "revenue_spike",     "high"),
    ("p99_latency", "latency_burst",     "high"),
    ("error_rate",  "error_rate_spike",  "high"),
    ("orders",      "order_crash",       "low"),
    ("orders",      "order_spike",       "high"),
]


class StreamProcessor:
    def __init__(self, anomaly_queue: Queue, tick_interval: float = 30.0):
        self.anomaly_queue = anomaly_queue
        self.tick_interval = tick_interval
        self._running = False
        self._thread: threading.Thread | None = None

        # Shared DuckDB in-memory connection (thread-safe via lock)
        self.con = duckdb.connect(database=":memory:")
        self._lock = threading.Lock()
        self._init_schema()

        # Track last-fired anomaly per type to avoid duplicate bursts
        self._last_alert: dict[str, float] = {}
        self._alert_cooldown = float(os.getenv("ALERT_COOLDOWN_MINUTES", "10")) * 60

    def _init_schema(self):
        with self._lock:
            self.con.execute(CREATE_RAW_EVENTS)
            self.con.execute(CREATE_WINDOWED_METRICS)

    def ingest(self, event: dict):
        with self._lock:
            self.con.execute("""
                INSERT OR IGNORE INTO raw_events VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, [
                event["event_id"],
                event["timestamp"],
                event["event_type"],
                event.get("session_id"),
                event.get("user_id"),
                event.get("page"),
                event.get("product_id"),
                event.get("amount_usd"),
                event.get("latency_ms"),
                event.get("status_code"),
                event.get("country"),
                event.get("device"),
                event.get("referrer"),
            ])

    def _tick(self):
        with self._lock:
            self.con.execute(PRUNE_RAW_EVENTS)
            self.con.execute(UPSERT_WINDOWED_METRICS)
            row_count = self.con.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
            window_count = self.con.execute("SELECT COUNT(*) FROM windowed_metrics").fetchone()[0]

        print(f"[processor] tick — raw_events={row_count}, windows={window_count}")

        if window_count < 3:
            print("[processor] insufficient windows for z-score baseline, skipping anomaly check")
            return

        fired: set[str] = set()

        for col, anomaly_type, direction in MONITORED_METRICS:
            if anomaly_type in fired:
                continue

            q = ZSCORE_QUERY_TEMPLATE.format(col=col, threshold=Z_THRESHOLD)
            with self._lock:
                rows = self.con.execute(q).fetchall()

            if not rows:
                continue

            window_start, metric_value, mean_val, std_val, z_score, is_anomaly = rows[0]

            if not is_anomaly or z_score is None:
                continue

            # Direction filter
            if direction == "high" and z_score < 0:
                continue
            if direction == "low" and z_score > 0:
                continue

            # Cooldown check
            now = time.time()
            last = self._last_alert.get(anomaly_type, 0)
            if now - last < self._alert_cooldown:
                print(f"[processor] {anomaly_type} in cooldown, skipping")
                continue

            self._last_alert[anomaly_type] = now
            fired.add(anomaly_type)

            alert = {
                "anomaly_id":    f"anm_{int(now)}_{anomaly_type[:4]}",
                "anomaly_type":  anomaly_type,
                "metric":        col,
                "window_start":  window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start),
                "metric_value":  round(metric_value, 4) if metric_value is not None else None,
                "baseline_mean": round(mean_val, 4)     if mean_val    is not None else None,
                "baseline_std":  round(std_val, 4)      if std_val     is not None else None,
                "z_score":       round(z_score, 2)      if z_score     is not None else None,
                "detected_at":   datetime.now(timezone.utc).isoformat(),
            }

            print(f"[processor] ANOMALY DETECTED → {anomaly_type}  z={z_score:.2f}")
            self.anomaly_queue.put(alert)

    def _loop(self):
        self._running = True
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"[processor] tick error: {e}")
            time.sleep(self.tick_interval)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[processor] started (tick={self.tick_interval}s, z_threshold={Z_THRESHOLD})")

    def stop(self):
        self._running = False

    # --- Query helpers used by the agent ---

    def get_baseline_summary(self) -> dict:
        with self._lock:
            row = self.con.execute(BASELINE_SUMMARY).fetchone()
        if not row:
            return {}
        cols = ["mean_orders", "std_orders", "mean_revenue", "std_revenue",
                "mean_latency", "std_latency", "mean_error_rate", "std_error_rate", "window_count"]
        return dict(zip(cols, row))

    def get_recent_windows(self, n: int = 10) -> list[dict]:
        q = RECENT_WINDOWS.format(n=n)
        with self._lock:
            rows = self.con.execute(q).fetchall()
        cols = ["window_start", "orders", "revenue", "avg_latency", "p99_latency", "error_rate", "total_events"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if hasattr(d["window_start"], "isoformat"):
                d["window_start"] = d["window_start"].isoformat()
            result.append(d)
        return result

    def get_metric_history(self, col: str, n: int = 60) -> list[dict]:
        q = METRIC_HISTORY_TEMPLATE.format(col=col, n=n)
        with self._lock:
            rows = self.con.execute(q).fetchall()
        result = []
        for window_start, metric_value in rows:
            result.append({
                "window_start": window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start),
                "value": metric_value,
            })
        return result

    def raw_query(self, sql: str) -> list[dict]:
        with self._lock:
            cursor = self.con.execute(sql)
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]
