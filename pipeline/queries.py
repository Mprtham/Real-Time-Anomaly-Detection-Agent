"""
DuckDB SQL query library for the stream processor.
All queries operate on the in-memory 'raw_events' and 'windowed_metrics' tables.
"""

CREATE_RAW_EVENTS = """
CREATE TABLE IF NOT EXISTS raw_events (
    event_id     VARCHAR PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL,
    event_type   VARCHAR NOT NULL,
    session_id   VARCHAR,
    user_id      VARCHAR,
    page         VARCHAR,
    product_id   VARCHAR,
    amount_usd   DOUBLE,
    latency_ms   INTEGER,
    status_code  INTEGER,
    country      VARCHAR,
    device       VARCHAR,
    referrer     VARCHAR
)
"""

CREATE_WINDOWED_METRICS = """
CREATE TABLE IF NOT EXISTS windowed_metrics (
    window_start  TIMESTAMPTZ PRIMARY KEY,
    total_events  INTEGER,
    orders        INTEGER,
    revenue       DOUBLE,
    avg_latency   DOUBLE,
    p99_latency   DOUBLE,
    error_rate    DOUBLE
)
"""

# Prune raw events older than 2 hours to keep memory bounded
PRUNE_RAW_EVENTS = """
DELETE FROM raw_events
WHERE timestamp < NOW() - INTERVAL '2 hours'
"""

# Build 1-minute tumbling window aggregates for the last 10 minutes
UPSERT_WINDOWED_METRICS = """
INSERT OR REPLACE INTO windowed_metrics
SELECT
    time_bucket(INTERVAL '1 minute', timestamp)                                           AS window_start,
    COUNT(*)                                                                              AS total_events,
    COUNT(*) FILTER (WHERE event_type = 'purchase')                                       AS orders,
    COALESCE(SUM(amount_usd) FILTER (WHERE event_type = 'purchase'), 0.0)                 AS revenue,
    AVG(latency_ms)                                                                       AS avg_latency,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)                              AS p99_latency,
    COALESCE(
        COUNT(*) FILTER (WHERE status_code >= 500)::DOUBLE / NULLIF(COUNT(*), 0), 0.0
    )                                                                                     AS error_rate
FROM raw_events
WHERE timestamp >= NOW() - INTERVAL '10 minutes'
  AND timestamp <  time_bucket(INTERVAL '1 minute', NOW())
GROUP BY 1
"""

# Z-score anomaly detection for a given metric column.
# Returns: window_start, metric_value, mean_baseline, std_baseline, z_score, is_anomaly
ZSCORE_QUERY_TEMPLATE = """
WITH baseline AS (
    SELECT
        AVG({col})    AS mean_val,
        STDDEV({col}) AS std_val
    FROM windowed_metrics
    WHERE window_start >= NOW() - INTERVAL '1 hour'
      AND window_start <  NOW() - INTERVAL '2 minutes'
),
latest AS (
    SELECT
        window_start,
        {col} AS metric_value
    FROM windowed_metrics
    ORDER BY window_start DESC
    LIMIT 1
)
SELECT
    latest.window_start,
    latest.metric_value,
    baseline.mean_val,
    baseline.std_val,
    (latest.metric_value - baseline.mean_val) / NULLIF(baseline.std_val, 0) AS z_score,
    ABS((latest.metric_value - baseline.mean_val) / NULLIF(baseline.std_val, 0)) > {threshold} AS is_anomaly
FROM latest, baseline
"""

# Fetch the last N windows for a metric (used by agent context fetch)
METRIC_HISTORY_TEMPLATE = """
SELECT
    window_start,
    {col} AS metric_value
FROM windowed_metrics
ORDER BY window_start DESC
LIMIT {n}
"""

# Summary of last 24h of windowed metrics (for agent context)
BASELINE_SUMMARY = """
SELECT
    AVG(orders)       AS mean_orders,
    STDDEV(orders)    AS std_orders,
    AVG(revenue)      AS mean_revenue,
    STDDEV(revenue)   AS std_revenue,
    AVG(avg_latency)  AS mean_latency,
    STDDEV(avg_latency) AS std_latency,
    AVG(error_rate)   AS mean_error_rate,
    STDDEV(error_rate) AS std_error_rate,
    COUNT(*)          AS window_count
FROM windowed_metrics
WHERE window_start >= NOW() - INTERVAL '24 hours'
"""

RECENT_WINDOWS = """
SELECT
    window_start,
    orders,
    revenue,
    avg_latency,
    p99_latency,
    error_rate,
    total_events
FROM windowed_metrics
ORDER BY window_start DESC
LIMIT {n}
"""
