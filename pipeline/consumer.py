"""
Redpanda consumer. Reads from 'raw_events', deserializes JSON,
hands each event to StreamProcessor.ingest(), and optionally
re-publishes processed anomaly alerts to 'anomaly_alerts'.
"""

import json
import os
import threading
import time

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from dotenv import load_dotenv

from pipeline.processor import StreamProcessor

load_dotenv()

BROKERS           = os.getenv("REDPANDA_BROKERS", "localhost:9092")
GROUP_ID          = os.getenv("CONSUMER_GROUP_ID", "sentinel-processor")
RAW_TOPIC         = "raw_events"
ALERT_TOPIC       = "anomaly_alerts"
RCA_TOPIC         = "rca_reports"


class PipelineConsumer:
    def __init__(self, processor: StreamProcessor):
        self.processor = processor
        self._running  = False
        self._thread: threading.Thread | None = None

        self.consumer = Consumer({
            "bootstrap.servers":        BROKERS,
            "group.id":                 GROUP_ID,
            "auto.offset.reset":        "latest",
            "enable.auto.commit":       True,
            "session.timeout.ms":       10000,
            "max.poll.interval.ms":     30000,
        })

        self.alert_producer = Producer({"bootstrap.servers": BROKERS})
        self._event_count = 0
        self._start_time  = None

    def _publish_alert(self, alert: dict):
        self.alert_producer.produce(
            ALERT_TOPIC,
            key=alert["anomaly_type"],
            value=json.dumps(alert),
        )
        self.alert_producer.poll(0)
        print(f"[consumer] published alert → {ALERT_TOPIC}: {alert['anomaly_id']}")

    def _drain_anomaly_queue(self):
        """Push any pending anomaly alerts from processor queue to Redpanda."""
        q = self.processor.anomaly_queue
        while not q.empty():
            try:
                alert = q.get_nowait()
                self._publish_alert(alert)
            except Exception:
                pass

    def _loop(self):
        self._running   = True
        self._start_time = time.time()
        self.consumer.subscribe([RAW_TOPIC])
        print(f"[consumer] subscribed to '{RAW_TOPIC}'")

        while self._running:
            msg = self.consumer.poll(timeout=0.1)

            if msg is None:
                self._drain_anomaly_queue()
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(msg.error())

            try:
                event = json.loads(msg.value().decode("utf-8"))
                self.processor.ingest(event)
                self._event_count += 1

                if self._event_count % 500 == 0:
                    elapsed = time.time() - self._start_time
                    rate    = self._event_count / elapsed
                    print(f"[consumer] {self._event_count} events  ({rate:.1f}/s)")

            except Exception as e:
                print(f"[consumer] parse error: {e}")

            self._drain_anomaly_queue()

        self.consumer.close()
        self.alert_producer.flush()
        print("[consumer] stopped")

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    @property
    def events_per_sec(self) -> float:
        if not self._start_time or self._event_count == 0:
            return 0.0
        return self._event_count / (time.time() - self._start_time)
