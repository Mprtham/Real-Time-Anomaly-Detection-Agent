"""
Triage node: rule-based pre-filter + optional LLM classification.
Short-circuits to END if verdict == 'noise'.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from groq import Groq

from agent.prompts import TRIAGE_HUMAN, TRIAGE_SYSTEM
from agent.tools import get_recent_anomaly_count

_groq = None


def _get_groq() -> Groq:
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq


def triage_node(state: dict) -> dict:
    anomaly = state["anomaly_event"]
    sqlite  = state.get("_sqlite_store")

    z_score      = anomaly.get("z_score", 0.0) or 0.0
    anomaly_type = anomaly.get("anomaly_type", "unknown")
    detected_at  = anomaly.get("detected_at", "")

    # --- Rule 1: very weak z-score → noise ---
    if abs(z_score) < 3.2:
        return {**state, "triage_verdict": "noise", "confidence": 0.9,
                "triage_reason": f"z_score {z_score:.2f} below hard threshold"}

    # --- Rule 2: alert fatigue guard ---
    recent_count = get_recent_anomaly_count(sqlite, anomaly_type, minutes=30) if sqlite else 0
    if recent_count >= 3:
        return {**state, "triage_verdict": "noise", "confidence": 0.75,
                "triage_reason": f"fired {recent_count}x in last 30 min (fatigue guard)"}

    # --- LLM classification for borderline cases ---
    dt = datetime.fromisoformat(detected_at) if detected_at else datetime.now(timezone.utc)
    prompt = TRIAGE_HUMAN.format(
        anomaly_type=anomaly_type,
        metric=anomaly.get("metric", ""),
        z_score=z_score,
        metric_value=anomaly.get("metric_value", ""),
        baseline_mean=anomaly.get("baseline_mean", ""),
        detected_at=detected_at,
        recent_count=recent_count,
        hour_utc=dt.hour,
        weekday=dt.strftime("%A"),
    )

    try:
        resp = _get_groq().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system",  "content": TRIAGE_SYSTEM},
                {"role": "user",    "content": prompt},
            ],
            temperature=0.0,
            max_tokens=128,
        )
        raw = resp.choices[0].message.content.strip()
        result = json.loads(raw)
        verdict    = result.get("verdict", "uncertain")
        confidence = float(result.get("confidence", 0.5))
        reason     = result.get("reason", "")
    except Exception as e:
        print(f"[triage] LLM call failed ({e}), defaulting to uncertain")
        verdict, confidence, reason = "uncertain", 0.5, "llm_error"

    # Hard cutoff from config
    cutoff = float(os.getenv("TRIAGE_CONFIDENCE_CUTOFF", "0.4"))
    if verdict == "noise" and confidence < cutoff:
        verdict = "uncertain"

    print(f"[triage] verdict={verdict} confidence={confidence:.2f} reason={reason}")
    return {**state, "triage_verdict": verdict, "confidence": confidence, "triage_reason": reason}
