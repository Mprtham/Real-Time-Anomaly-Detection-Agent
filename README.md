# sentinel

> **Real-time anomaly detection and AI-powered root cause analysis for e-commerce event streams.**

---

## What does Sentinel do?

Imagine your online store is processing thousands of orders every minute. Suddenly, revenue drops to zero. Or checkout pages start timing out. Or your error rate triples. By the time a human notices and opens a dashboard, you've already lost thousands of dollars.

**Sentinel catches this in real time — and figures out why — automatically.**

Here is the full flow, in plain English:

1. **Every user action** — page views, add-to-cart, purchases, errors — streams in as a live event at ~80–100 events/sec.
2. **Every 30 seconds**, Sentinel aggregates those events into 1-minute windows and computes key metrics: revenue, order count, p99 latency, and error rate.
3. **A statistical check** (z-score) compares the latest window against the rolling baseline. If a metric is more than 3 standard deviations from normal, an anomaly is flagged.
4. **A LangGraph AI agent** picks up the anomaly and runs a 4-step investigation:
   - **Triage** — is this real or just noise? Low-confidence signals are discarded immediately.
   - **Context fetch** — pull the last 10 minutes of metric history and the 24-hour baseline.
   - **RCA writer** — generate a structured root cause analysis report: what happened, likely causes, business impact, and recommended actions.
   - **Decision** — escalate to Slack if critical; persist to database for all real anomalies.
5. **The full report** appears in the live web UI and optionally in Slack within 2 minutes of the anomaly occurring.

Think of it as an on-call engineer who never sleeps and can already explain the problem by the time you open your laptop.

---

## Architecture

```
Event Simulator ──► Redpanda (Kafka) ──► DuckDB Processor ──► LangGraph Agent ──► SQLite / Slack
                                                                                        │
                                                                              FastAPI + WebSocket
                                                                                        │
                                                                             Frontend (Vanilla JS)
```

**In local mode** (no Docker/Redpanda required), the Kafka layer is bypassed entirely — everything runs in-process via Python queues and threads.

---

## Tech Stack

| Layer              | Technology                                      |
|--------------------|-------------------------------------------------|
| Event broker       | Redpanda (Kafka-compatible, single binary)      |
| Stream processing  | DuckDB — in-process SQL + z-score detection     |
| Agent framework    | LangGraph — multi-node stateful agent           |
| LLM                | Groq — Llama 3.3 70B (< 2 s RCA generation)    |
| Backend            | FastAPI — SSE + WebSocket + REST                |
| Storage            | SQLite — anomaly and RCA history                |
| Frontend           | Vanilla JS / CSS — zero build step              |
| Alerts             | Slack incoming webhooks                         |
| Containerisation   | Docker + Docker Compose                         |

---

## Quickstart

### Option 1 — Local mode (no Docker, no Redpanda)

The fastest way to run Sentinel. Everything runs in a single Python process.

```bash
# 1. Clone and enter the project
git clone https://github.com/Mprtham/Real-Time-Anomaly-Detection-Agent.git
cd Real-Time-Anomaly-Detection-Agent

# 2. Install dependencies (Python 3.10+)
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Open .env and set GROQ_API_KEY (free at https://console.groq.com)

# 4. Start everything
python run_local.py
```

Open **http://localhost:8000** in your browser. The live event stream, anomaly feed, and sparklines will all be active within seconds.

### Option 2 — Docker Compose (full stack with Redpanda)

```bash
cp .env.example .env
# Add your GROQ_API_KEY to .env

docker-compose up
```

This starts Redpanda, creates the required topics, and launches the API — all wired together.

---

## Inject an Anomaly (Demo)

The sidebar has one-click injection buttons. You can also call the API directly:

```bash
# Revenue crash — orders drop to 0, triggers immediate agent investigation
curl -X POST http://localhost:8000/inject/revenue_crash

# Other types
curl -X POST http://localhost:8000/inject/revenue_spike
curl -X POST http://localhost:8000/inject/latency_burst
curl -X POST http://localhost:8000/inject/error_rate_spike
curl -X POST http://localhost:8000/inject/cart_abandonment
```

After ~30–90 seconds you will see the anomaly card appear in the feed. Click it to read the full AI-generated RCA report.

To reset the database between demos:

```bash
curl -X POST http://localhost:8000/demo/reset
```

---

## Anomaly Types

| Anomaly             | Detection method              | Real-world analog                    |
|---------------------|-------------------------------|--------------------------------------|
| `revenue_crash`     | Orders drop to 0 (z < −3)    | Payment gateway down                 |
| `revenue_spike`     | 5× order volume (z > 3)      | Flash sale, bot orders               |
| `latency_burst`     | p99 > 2500ms sustained        | DB regression, infrastructure issue  |
| `error_rate_spike`  | 5xx rate > 15%                | Deployment bug, downstream outage    |
| `cart_abandonment`  | Purchases suppressed          | Checkout UX bug, pricing error       |
| `order_crash`       | Order count → 0 (z < −3)     | Site outage                          |

---

## How the Agent Works

The LangGraph agent runs as a directed graph with conditional routing:

```
triage ──► (noise) ──► END
       └──► (real/uncertain) ──► context_fetch ──► rca_writer ──► decision ──► END
```

**Triage node** uses a two-layer filter:
- Rule layer: hard z-score cutoff (< 3.2 → noise) and alert fatigue guard (≥ 3 fires in 30 min → skip)
- LLM layer: Llama 3.3 70B classifies borderline cases, returns `{verdict, confidence, reason}`

**Context fetch node** pulls three data sources from DuckDB:
- Last 10 one-minute windows (tabular)
- 24-hour baseline statistics (mean/std for all metrics)
- Adjacent metric snapshot at the anomaly window

**RCA writer node** sends all context to Llama 3.3 70B with a structured prompt. The output follows a fixed format: `WHAT HAPPENED`, `LIKELY CAUSES`, `IMPACT`, `RECOMMENDED ACTIONS`.

**Decision node** routes based on confidence and severity:
- `escalate` → saves to SQLite + sends to Slack
- `monitor` → saves to SQLite only
- `dismiss` → no-op

---

## API Reference

| Method | Endpoint               | Description                                        |
|--------|------------------------|----------------------------------------------------|
| `GET`  | `/events/stream`       | SSE stream of raw events (live ticker)             |
| `GET`  | `/anomalies`           | Paginated anomaly history (`?severity=critical`)   |
| `GET`  | `/anomalies/{id}`      | Single anomaly detail                              |
| `POST` | `/anomalies/{id}/resolve` | Mark anomaly as resolved                        |
| `GET`  | `/rca/{id}`            | Full RCA report text for an anomaly                |
| `GET`  | `/metrics`             | System health, throughput stats, agent state       |
| `WS`   | `/ws/live`             | WebSocket — real-time anomaly push to frontend     |
| `POST` | `/inject/{type}`       | Manually inject an anomaly (demo)                  |
| `POST` | `/demo/reset`          | Clear all anomaly and RCA history                  |
| `GET`  | `/health`              | Health check                                       |

Interactive docs are available at **http://localhost:8000/docs**.

---

## Environment Variables

| Variable                  | Default          | Description                                         |
|---------------------------|------------------|-----------------------------------------------------|
| `GROQ_API_KEY`            | —                | **Required.** Get free at console.groq.com          |
| `REDPANDA_BROKERS`        | `localhost:9092` | Redpanda broker address (full-stack mode only)      |
| `SLACK_WEBHOOK_URL`       | —                | Optional. Incoming webhook for critical alerts      |
| `ANOMALY_Z_THRESHOLD`     | `3.0`            | Z-score threshold to flag an anomaly                |
| `TRIAGE_CONFIDENCE_CUTOFF`| `0.4`            | Below this confidence → dismiss                     |
| `ESCALATION_CONFIDENCE`   | `0.8`            | Above this + critical severity → Slack              |
| `ALERT_COOLDOWN_MINUTES`  | `10`             | Duplicate suppression window per anomaly type       |
| `API_PORT`                | `8000`           | FastAPI server port                                 |

---

## Performance Targets

| Metric                              | Target      |
|-------------------------------------|-------------|
| Detection latency (injection → alert) | < 90 s    |
| RCA generation (Groq / Llama 3.3)   | < 3 s       |
| End-to-end (injection → Slack)      | < 120 s     |
| Triage false-positive rate          | < 10%       |
| Event throughput                    | > 100 events/s |
| Frontend load time                  | < 1 s       |

---

## Project Structure

```
sentinel/
├── simulator/              # Event generator and anomaly injector
│   ├── event_generator.py  # Poisson-distributed e-commerce event stream
│   ├── anomaly_injector.py # Schedules and applies anomaly overrides
│   └── schema.py           # Event dataclass and field constants
│
├── pipeline/               # Stream ingestion and anomaly detection
│   ├── consumer.py         # Redpanda consumer (full-stack mode)
│   ├── processor.py        # DuckDB aggregation + z-score detection
│   └── queries.py          # All SQL query templates
│
├── agent/                  # LangGraph AI agent
│   ├── graph.py            # StateGraph definition and routing logic
│   ├── runner.py           # Redpanda-backed agent runner (full-stack)
│   ├── prompts.py          # System and user prompts for Groq
│   ├── tools.py            # Context formatting helpers
│   └── nodes/
│       ├── triage.py       # Rule-based + LLM signal classification
│       ├── context_fetch.py# Pulls metric history from DuckDB
│       ├── rca_writer.py   # Calls Groq to generate the RCA report
│       └── decision.py     # Routes to escalate / monitor / dismiss
│
├── api/                    # FastAPI application
│   ├── main.py             # App entry point, lifespan, WebSocket manager
│   ├── config.py           # Pydantic settings
│   ├── db/sqlite.py        # SQLite store (anomalies + RCA reports)
│   └── routers/            # events, anomalies, rca, metrics endpoints
│
├── integrations/
│   └── slack.py            # Slack webhook client with duplicate suppression
│
├── frontend/               # Static web UI (zero build step)
│   ├── index.html
│   ├── css/                # tokens, reset, layout, components, animations
│   └── js/                 # api, ticker, anomalyFeed, rca, sparklines, main
│
├── configs/                # Redpanda topic and agent configuration
├── run_local.py            # Single-process local runner (no Kafka needed)
├── docker-compose.yml      # Full-stack: Redpanda + API
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Running Tests

The project is designed for live integration testing. To verify the full pipeline:

1. Start the server: `python run_local.py`
2. Inject an anomaly: `curl -X POST http://localhost:8000/inject/revenue_crash`
3. Watch the terminal — you should see `[processor] ANOMALY DETECTED` within ~30 s, followed by `[agent] ▶ triage`, `[agent] ▶ context_fetch`, `[agent] ▶ rca_writer`, `[agent] ▶ decision`
4. Open the UI at http://localhost:8000 and click the anomaly card to read the RCA report

---

*Built by Prathamesh Mishra*
