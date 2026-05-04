"""
Slack webhook integration. Formats and sends RCA alerts.
"""

import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

SEVERITY_EMOJI = {
    "critical": "🚨",
    "warning":  "⚠️",
    "info":     "ℹ️",
}

# Track sent anomaly types for duplicate suppression
_sent_log: dict[str, float] = {}
_COOLDOWN = float(os.getenv("ALERT_COOLDOWN_MINUTES", "10")) * 60


def _extract_section(rca: str, header: str) -> str:
    lines = rca.split("\n")
    collecting = False
    out = []
    for line in lines:
        if header.lower() in line.lower():
            collecting = True
            continue
        if collecting:
            if line.startswith("**") and header.lower() not in line.lower():
                break
            if line.strip():
                out.append(line.strip())
    return "\n".join(out[:4]) if out else "(see full report)"


class SlackIntegration:
    def __init__(self, webhook_url: str = WEBHOOK_URL):
        self.webhook_url = webhook_url
        self.enabled     = bool(webhook_url)
        if not self.enabled:
            print("[slack] SLACK_WEBHOOK_URL not set - alerts will be logged only")

    def send_alert(self, anomaly: dict, rca_report: str, severity: str, confidence: float):
        import time
        now  = time.time()
        atype = anomaly.get("anomaly_type", "unknown")

        if now - _sent_log.get(atype, 0) < _COOLDOWN:
            print(f"[slack] duplicate suppressed for {atype}")
            return

        _sent_log[atype] = now

        title   = atype.replace("_", " ").title()
        emoji   = SEVERITY_EMOJI.get(severity, "ℹ️")
        z_score = anomaly.get("z_score", "N/A")
        metric  = anomaly.get("metric", "")
        current = anomaly.get("metric_value", "N/A")
        baseline= anomaly.get("baseline_mean", "N/A")

        detected = anomaly.get("detected_at", "")
        if detected:
            try:
                dt = datetime.fromisoformat(detected)
                detected = dt.strftime("%H:%M UTC")
            except Exception:
                pass

        what    = _extract_section(rca_report, "WHAT HAPPENED")
        causes  = _extract_section(rca_report, "LIKELY CAUSES")
        actions = _extract_section(rca_report, "RECOMMENDED ACTIONS")

        text = (
            f"{emoji} *SENTINEL ALERT — {title}*\n"
            f"Severity: *{severity.upper()}* · Detected: {detected} · "
            f"Z-score: {z_score}σ\n\n"
            f"*Metric:* {metric} changed from {baseline} → {current}\n\n"
            f"*What happened:* {what}\n\n"
            f"*Likely causes:*\n{causes}\n\n"
            f"*Actions:*\n{actions}\n\n"
            f"— sentinel agent · Confidence: {int(confidence * 100)}%"
        )

        if not self.enabled:
            print(f"[slack] (dry run) would send:\n{text}\n")
            return

        try:
            resp = httpx.post(self.webhook_url, json={"text": text}, timeout=5)
            resp.raise_for_status()
            print(f"[slack] alert sent for {atype}")
        except Exception as e:
            print(f"[slack] send failed: {e}")
