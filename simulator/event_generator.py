"""
Generates a Poisson-distributed stream of e-commerce events and publishes
them to the Redpanda 'raw_events' topic.
"""

import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from dotenv import load_dotenv

from simulator.schema import COUNTRIES, DEVICES, EVENT_TYPES, PAGES, PRODUCTS, REFERRERS, Event

load_dotenv()

BROKERS = os.getenv("REDPANDA_BROKERS", "localhost:9092")
TOPIC = "raw_events"

# Approximate rates (events/sec) per event type — weights for random.choices
EVENT_WEIGHTS = {
    "page_view":       50,
    "add_to_cart":     20,
    "checkout_start":  10,
    "purchase":        10,
    "error":            5,
}

PRICE_RANGE = {
    "sneaker_001": (89.99, 149.99),
    "tshirt_002":  (19.99,  49.99),
    "jacket_003":  (99.99, 249.99),
    "bag_004":     (59.99, 129.99),
    "watch_005":  (199.99, 499.99),
    "shoes_006":   (79.99, 139.99),
    "pants_007":   (39.99,  89.99),
    "hat_008":     (14.99,  34.99),
    "belt_009":    (24.99,  59.99),
    "scarf_010":   (19.99,  44.99),
}


def _delivery_report(err, msg):
    if err:
        print(f"[producer] delivery failed: {err}")


def _make_event(
    latency_override: int | None = None,
    status_override: int | None = None,
    amount_multiplier: float = 1.0,
    force_error: bool = False,
) -> Event:
    event_type = random.choices(
        list(EVENT_WEIGHTS.keys()),
        weights=list(EVENT_WEIGHTS.values()),
    )[0]

    if force_error:
        event_type = "error"

    product_id = random.choice(PRODUCTS) if event_type in ("purchase", "add_to_cart") else None
    amount_usd = None
    if event_type == "purchase" and product_id:
        lo, hi = PRICE_RANGE[product_id.replace("prod_", "")]
        amount_usd = round(random.uniform(lo, hi) * amount_multiplier, 2)

    page = "/api/pay" if event_type == "error" else random.choice(PAGES)
    latency_ms = latency_override if latency_override is not None else int(random.lognormvariate(4.8, 0.4))
    status_code = status_override if status_override is not None else (
        random.choices([200, 500, 503], weights=[95, 3, 2])[0]
        if force_error else
        random.choices([200, 404, 500], weights=[97, 2, 1])[0]
    )

    return Event(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        session_id=f"sess_{uuid.uuid4().hex[:6]}",
        user_id=f"usr_{uuid.uuid4().hex[:5]}",
        page=page,
        product_id=product_id,
        amount_usd=amount_usd,
        latency_ms=max(10, latency_ms),
        status_code=status_code,
        country=random.choice(COUNTRIES),
        device=random.choice(["mobile", "desktop", "tablet"]),
        referrer=random.choice(["organic", "paid", "email", "direct"]),
    )


class EventGenerator:
    def __init__(self, rate: float = 100.0, local_mode: bool = False):
        """
        rate: target events/sec (Poisson mean)
        local_mode: skip Kafka producer (use direct ingest callback instead)
        """
        self.rate = rate
        self.local_mode = local_mode
        self.producer = None if local_mode else Producer({"bootstrap.servers": BROKERS})
        self._running = False

        # Overrides set by anomaly injector
        self.latency_override: int | None = None
        self.status_override: int | None = None
        self.amount_multiplier: float = 1.0
        self.force_error: bool = False
        self.purchase_rate_multiplier: float = 1.0
        self.suppress_purchases: bool = False

    def _adjusted_weights(self) -> list[int]:
        weights = list(EVENT_WEIGHTS.values())
        # purchase weight is index 3
        if self.suppress_purchases:
            weights[3] = 0
        else:
            weights[3] = max(1, int(EVENT_WEIGHTS["purchase"] * self.purchase_rate_multiplier))
        return weights

    def _next_interval(self) -> float:
        return random.expovariate(self.rate)

    def run(self):
        self._running = True
        print(f"[generator] starting at ~{self.rate} events/sec -> topic '{TOPIC}'")
        while self._running:
            event = _make_event(
                latency_override=self.latency_override,
                status_override=self.status_override,
                amount_multiplier=self.amount_multiplier,
                force_error=self.force_error,
            )
            if self.producer:
                self.producer.produce(
                    TOPIC,
                    key=event.session_id,
                    value=json.dumps(event.to_dict()),
                    callback=_delivery_report,
                )
                self.producer.poll(0)
            time.sleep(self._next_interval())

        if self.producer:
            self.producer.flush()
        print("[generator] stopped")

    def stop(self):
        self._running = False


if __name__ == "__main__":
    gen = EventGenerator(rate=100)
    try:
        gen.run()
    except KeyboardInterrupt:
        gen.stop()
