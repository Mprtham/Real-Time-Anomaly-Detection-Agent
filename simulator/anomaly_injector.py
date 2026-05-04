"""
Schedules and injects anomalies into a running EventGenerator.
Supports normal mode (every 3–8 min) and chaos mode (every 30 sec).
"""

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class AnomalySpec:
    name: str
    duration_seconds: int
    apply: Callable
    revert: Callable


def _revenue_spike(gen):
    gen.purchase_rate_multiplier = 5.0
    gen.amount_multiplier = 1.5


def _revenue_crash(gen):
    gen.suppress_purchases = True
    gen.status_override = 500
    gen.force_error = True


def _latency_burst(gen):
    gen.latency_override = random.randint(2500, 4000)


def _error_spike(gen):
    gen.status_override = 503
    gen.force_error = True


def _cart_abandonment(gen):
    # Suppress purchases but keep add_to_cart events flowing
    gen.suppress_purchases = True


def _geo_anomaly(gen):
    # Override happens at event level — we monkey-patch the country sampler
    # by setting a flag the generator checks
    gen._geo_flood = True


def _revert_all(gen):
    gen.purchase_rate_multiplier = 1.0
    gen.amount_multiplier = 1.0
    gen.suppress_purchases = False
    gen.latency_override = None
    gen.status_override = None
    gen.force_error = False
    gen._geo_flood = False


ANOMALY_TYPES = [
    AnomalySpec("revenue_spike",        duration_seconds=120, apply=_revenue_spike,      revert=_revert_all),
    AnomalySpec("revenue_crash",        duration_seconds=180, apply=_revenue_crash,      revert=_revert_all),
    AnomalySpec("latency_burst",        duration_seconds=150, apply=_latency_burst,      revert=_revert_all),
    AnomalySpec("error_rate_spike",     duration_seconds=120, apply=_error_spike,        revert=_revert_all),
    AnomalySpec("cart_abandonment",     duration_seconds=180, apply=_cart_abandonment,   revert=_revert_all),
]


class AnomalyInjector:
    def __init__(self, generator, chaos_mode: bool = False):
        self.generator = generator
        self.chaos_mode = chaos_mode
        self._running = False
        self._thread: threading.Thread | None = None
        self.current_anomaly: str | None = None
        self.injection_log: list[dict] = []

    def _interval(self) -> float:
        if self.chaos_mode:
            return 30.0
        return random.uniform(180, 480)  # 3–8 minutes

    def _inject_one(self):
        spec = random.choice(ANOMALY_TYPES)
        self.current_anomaly = spec.name
        record = {
            "anomaly_type": spec.name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": spec.duration_seconds,
            "ended_at": None,
        }
        self.injection_log.append(record)

        print(f"[injector] → injecting '{spec.name}' for {spec.duration_seconds}s")
        spec.apply(self.generator)
        time.sleep(spec.duration_seconds)
        spec.revert(self.generator)

        record["ended_at"] = datetime.now(timezone.utc).isoformat()
        self.current_anomaly = None
        print(f"[injector] ✓ '{spec.name}' reverted")

    def _loop(self):
        self._running = True
        while self._running:
            wait = self._interval()
            print(f"[injector] next anomaly in {wait:.0f}s")
            for _ in range(int(wait * 10)):
                if not self._running:
                    return
                time.sleep(0.1)
            if self._running:
                self._inject_one()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[injector] started (chaos_mode={self.chaos_mode})")

    def stop(self):
        self._running = False

    def inject_now(self, anomaly_name: str):
        spec = next((s for s in ANOMALY_TYPES if s.name == anomaly_name), None)
        if not spec:
            raise ValueError(f"Unknown anomaly: {anomaly_name}. Options: {[s.name for s in ANOMALY_TYPES]}")
        t = threading.Thread(target=lambda: (
            spec.apply(self.generator),
            time.sleep(spec.duration_seconds),
            spec.revert(self.generator),
        ), daemon=True)
        t.start()
        print(f"[injector] manual injection: '{anomaly_name}'")
