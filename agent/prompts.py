RCA_SYSTEM = """\
You are an SRE on-call analyst for a high-traffic e-commerce platform. \
Your job is to produce concise, accurate root cause analysis reports from anomaly signals. \
Be specific with numbers. Do not speculate beyond the evidence. Do not use filler phrases.\
"""

RCA_HUMAN = """\
An anomaly was detected in the e-commerce platform.

ANOMALY SUMMARY
  Type:          {anomaly_type}
  Metric:        {metric}
  Current value: {metric_value}
  Baseline mean: {baseline_mean}
  Baseline std:  {baseline_std}
  Z-score:       {z_score}σ
  Detected at:   {detected_at}
  Window start:  {window_start}

RECENT METRIC WINDOWS (last 10 minutes, newest first)
{recent_windows_table}

24-HOUR BASELINE STATISTICS
{baseline_stats}

ADJACENT METRICS AT ANOMALY WINDOW
{adjacent_metrics}

---
Write a concise RCA report in the following structure. Max 300 words total.

**WHAT HAPPENED**
One sentence describing the observable symptom with specific numbers.

**LIKELY CAUSES**
Bulleted list, 2–4 items, ranked by probability. Reference specific metric evidence.

**IMPACT**
Estimated affected sessions and revenue impact (if revenue metric is involved).

**RECOMMENDED ACTIONS**
Numbered list, 3–5 specific actions an on-call engineer should take right now.
"""

TRIAGE_SYSTEM = """\
You are a signal-to-noise classifier for a real-time anomaly detection system. \
Evaluate whether an anomaly signal is real and worth investigating or is noise/transient. \
Return JSON only — no prose.\
"""

TRIAGE_HUMAN = """\
Anomaly signal:
  type:         {anomaly_type}
  metric:       {metric}
  z_score:      {z_score}
  current_val:  {metric_value}
  baseline_mean:{baseline_mean}
  detected_at:  {detected_at}

Recent anomaly history for this type (last 30 min, count): {recent_count}
Time of day (UTC hour): {hour_utc}
Day of week: {weekday}

Respond with this JSON and nothing else:
{{
  "verdict": "real" | "noise" | "uncertain",
  "confidence": 0.0-1.0,
  "reason": "one sentence"
}}
"""
