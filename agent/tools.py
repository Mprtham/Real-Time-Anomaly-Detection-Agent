"""
LangGraph tool functions. Each wraps a StreamProcessor query
and formats the result for the agent's context window.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.processor import StreamProcessor


def fmt_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "(no data)"
    lines = ["  " + "  ".join(f"{c:<18}" for c in cols)]
    for row in rows:
        lines.append("  " + "  ".join(f"{str(row.get(c, '')):<18}" for c in cols))
    return "\n".join(lines)


def get_baseline_stats(processor: "StreamProcessor") -> str:
    stats = processor.get_baseline_summary()
    if not stats:
        return "(no baseline data)"
    return textwrap.dedent(f"""\
        orders:      mean={stats.get('mean_orders', 'N/A'):.1f}  std={stats.get('std_orders', 'N/A'):.1f}
        revenue:     mean=${stats.get('mean_revenue', 0):.2f}  std=${stats.get('std_revenue', 0):.2f}
        latency:     mean={stats.get('mean_latency', 'N/A'):.1f}ms  std={stats.get('std_latency', 'N/A'):.1f}ms
        error_rate:  mean={stats.get('mean_error_rate', 0)*100:.2f}%  std={stats.get('std_error_rate', 0)*100:.2f}%
        windows:     {stats.get('window_count', 0)} (last 24h)
    """)


def get_recent_windows_table(processor: "StreamProcessor", n: int = 10) -> str:
    rows = processor.get_recent_windows(n=n)
    cols = ["window_start", "orders", "revenue", "avg_latency", "p99_latency", "error_rate"]
    # Round floats for readability
    for row in rows:
        row["revenue"]     = f"${row['revenue']:.2f}"     if row.get("revenue")     is not None else "-"
        row["avg_latency"] = f"{row['avg_latency']:.0f}ms" if row.get("avg_latency") is not None else "-"
        row["p99_latency"] = f"{row['p99_latency']:.0f}ms" if row.get("p99_latency") is not None else "-"
        row["error_rate"]  = f"{row['error_rate']*100:.1f}%" if row.get("error_rate") is not None else "-"
    return fmt_table(rows, cols)


def get_adjacent_metrics(processor: "StreamProcessor", anomaly_type: str) -> str:
    windows = processor.get_recent_windows(n=3)
    if not windows:
        return "(no adjacent metrics)"
    latest = windows[0]
    lines = []
    for k, v in latest.items():
        if k != "window_start":
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def get_recent_anomaly_count(sqlite_store, anomaly_type: str, minutes: int = 30) -> int:
    try:
        return sqlite_store.count_recent_anomalies(anomaly_type, minutes)
    except Exception:
        return 0
