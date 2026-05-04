"""
Decision node: routes the RCA to escalate / monitor / dismiss
and triggers Slack + SQLite persistence.
"""

from __future__ import annotations

import os


ESCALATE_CONFIDENCE = float(os.getenv("ESCALATION_CONFIDENCE", "0.8"))

CRITICAL_ANOMALIES = {"revenue_crash", "error_rate_spike", "order_crash"}
WARNING_ANOMALIES  = {"revenue_spike", "latency_burst", "order_spike", "cart_abandonment"}


def _severity(anomaly_type: str, z_score: float) -> str:
    if anomaly_type in CRITICAL_ANOMALIES or abs(z_score) > 5:
        return "critical"
    if anomaly_type in WARNING_ANOMALIES or abs(z_score) > 3.5:
        return "warning"
    return "info"


def decision_node(state: dict) -> dict:
    anomaly    = state["anomaly_event"]
    confidence = state.get("confidence", 0.5)
    rca_report = state.get("rca_report", "")
    z_score    = anomaly.get("z_score", 0.0) or 0.0
    severity   = _severity(anomaly.get("anomaly_type", ""), z_score)

    if confidence >= ESCALATE_CONFIDENCE and severity == "critical":
        action = "escalate"
    elif confidence >= 0.5:
        action = "monitor"
    else:
        action = "dismiss"

    print(f"[decision] action={action}  severity={severity}  confidence={confidence:.2f}")

    slack_sent = False
    if action == "escalate":
        slack = state.get("_slack")
        if slack:
            try:
                slack.send_alert(anomaly, rca_report, severity, confidence)
                slack_sent = True
            except Exception as e:
                print(f"[decision] slack send failed: {e}")

    sqlite = state.get("_sqlite_store")
    if sqlite and action != "dismiss":
        try:
            sqlite.save_anomaly(anomaly, rca_report, severity, confidence, action)
        except Exception as e:
            print(f"[decision] sqlite save failed: {e}")

    # Also publish RCA to Redpanda if producer is available
    rca_producer = state.get("_rca_producer")
    if rca_producer and action != "dismiss":
        import json
        payload = {
            "anomaly_id":   anomaly.get("anomaly_id"),
            "anomaly_type": anomaly.get("anomaly_type"),
            "severity":     severity,
            "action":       action,
            "confidence":   confidence,
            "rca_report":   rca_report,
            "detected_at":  anomaly.get("detected_at"),
        }
        try:
            rca_producer.produce("rca_reports", value=json.dumps(payload))
            rca_producer.poll(0)
        except Exception as e:
            print(f"[decision] rca_producer failed: {e}")

    return {**state, "action": action, "severity": severity, "slack_sent": slack_sent}
