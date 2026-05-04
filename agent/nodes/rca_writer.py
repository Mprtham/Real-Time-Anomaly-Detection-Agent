"""
RCA writer node: calls Groq to generate a structured root cause analysis.
"""

from __future__ import annotations

import os
import time

from groq import Groq

from agent.prompts import RCA_HUMAN, RCA_SYSTEM

_groq = None


def _get_groq() -> Groq:
    global _groq
    if _groq is None:
        _groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq


def rca_writer_node(state: dict) -> dict:
    anomaly = state["anomaly_event"]
    ctx     = state.get("context", {})

    prompt = RCA_HUMAN.format(
        anomaly_type=anomaly.get("anomaly_type", "unknown"),
        metric=anomaly.get("metric", ""),
        metric_value=anomaly.get("metric_value", "N/A"),
        baseline_mean=anomaly.get("baseline_mean", "N/A"),
        baseline_std=anomaly.get("baseline_std", "N/A"),
        z_score=anomaly.get("z_score", "N/A"),
        detected_at=anomaly.get("detected_at", ""),
        window_start=anomaly.get("window_start", ""),
        recent_windows_table=ctx.get("recent_windows", "(no data)"),
        baseline_stats=ctx.get("baseline_stats", "(no data)"),
        adjacent_metrics=ctx.get("adjacent_metrics", "(no data)"),
    )

    t0 = time.time()
    try:
        resp = _get_groq().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": RCA_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=512,
        )
        rca_text  = resp.choices[0].message.content.strip()
        latency_s = round(time.time() - t0, 2)
        print(f"[rca_writer] generated in {latency_s}s ({len(rca_text)} chars)")
    except Exception as e:
        rca_text  = f"RCA generation failed: {e}"
        latency_s = round(time.time() - t0, 2)
        print(f"[rca_writer] error: {e}")

    return {**state, "rca_report": rca_text, "rca_latency_s": latency_s}
