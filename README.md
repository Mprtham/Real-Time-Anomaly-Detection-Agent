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
   - **RCA writer** — generate a structured root cause analysis: what happened, likely causes, business impact, and recommended actions.
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

Open **http://localhost:8000** in your browser. The live event stream, anomaly feed, and sparklines will be active within seconds.

### Option 2 — Docker Compose (full stack with Redpanda)

```bash
cp .env.example .env
# Add your GROQ_API_KEY to .env

docker-compose up
```

Starts Redpanda, creates the required topics (`raw_events`, `anomaly_alerts`, `rca_reports`), and launches the API — all wired together.

---

## Hosting (Cloud Deployment)

Sentinel is designed to deploy to any platform that supports Docker or Python. The recommended approach is **Railway** — it auto-detects the `Procfile` and deploys in one click.

### GitHub Pages + Railway (frontend public, backend on cloud)

This is the recommended setup if you want a publicly accessible live demo with a permanent URL.

**Step 1 — Deploy the backend to Railway**

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select this repository
3. Set environment variables in the Railway dashboard:
   ```
   GROQ_API_KEY=your_key_here
   ```
4. Railway reads the `Procfile` automatically. Note the URL Railway assigns (e.g. `https://sentinel-production.up.railway.app`)

**Step 2 — Point the frontend at your backend**

Open `frontend/index.html` and set your Railway URL:

```html
<script>
  window.SENTINEL_API = 'https://sentinel-production.up.railway.app';
</script>
```

Commit and push this change.

**Step 3 — Enable GitHub Pages**

1. Go to your repo on GitHub → **Settings** → **Pages**
2. Under **Source**, select **GitHub Actions**
3. The workflow in `.github/workflows/deploy-pages.yml` will deploy automatically on every push to `main`
4. Your frontend will be live at `https://mprtham.github.io/Real-Time-Anomaly-Detection-Agent/`

That's it. The frontend on GitHub Pages talks to your Railway backend. No build step, no CI config to write.

---

### Railway (recommended — free tier available)

1. Push this repo to GitHub (already done if you're reading this)
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Select this repository
4. Set the following environment variables in the Railway dashboard:
   ```
   GROQ_API_KEY=your_key_here
   SLACK_WEBHOOK_URL=optional
   ```
5. Railway will auto-detect the `Procfile` and deploy. Your app will be live at a `*.up.railway.app` URL.

The frontend will automatically connect to the correct API URL — no configuration needed.

### Render

1. New Web Service → connect this GitHub repo
2. **Build command**: `pip install -r requirements.txt`
3. **Start command**: `uvicorn run_local:app --host 0.0.0.0 --port $PORT`
4. Set `GROQ_API_KEY` in environment variables
5. Deploy

### Docker (self-hosted)

```bash
docker build -t sentinel .
docker run -p 8000:8000 -e GROQ_API_KEY=your_key sentinel
```

Or with a custom port:

```bash
docker run -p 3000:3000 -e PORT=3000 -e GROQ_API_KEY=your_key sentinel
```

> **Note:** The deployed app runs in local mode (no Redpanda). The full Docker Compose stack with Redpanda is best suited for local development or self-hosted infrastructure.

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

| Method | Endpoint                     | Description                                        |
|--------|------------------------------|----------------------------------------------------|
| `GET`  | `/events/stream`             | SSE stream of raw events (live ticker)             |
| `GET`  | `/anomalies`                 | Paginated anomaly history (`?severity=critical`)   |
| `GET`  | `/anomalies/{id}`            | Single anomaly detail                              |
| `POST` | `/anomalies/{id}/resolve`    | Mark anomaly as resolved                           |
| `GET`  | `/rca/{id}`                  | Full RCA report text for an anomaly                |
| `GET`  | `/metrics`                   | System health, throughput stats, agent state       |
| `WS`   | `/ws/live`                   | WebSocket — real-time anomaly push to frontend     |
| `POST` | `/inject/{type}`             | Manually inject an anomaly (demo)                  |
| `POST` | `/demo/reset`                | Clear all anomaly and RCA history                  |
| `GET`  | `/health`                    | Health check                                       |

Interactive docs are available at **http://localhost:8000/docs**.

---

## Environment Variables

| Variable                   | Default          | Description                                         |
|----------------------------|------------------|-----------------------------------------------------|
| `GROQ_API_KEY`             | —                | **Required.** Get free at console.groq.com          |
| `REDPANDA_BROKERS`         | `localhost:9092` | Redpanda broker address (full Docker stack only)    |
| `SLACK_WEBHOOK_URL`        | —                | Optional. Incoming webhook for critical alerts      |
| `ANOMALY_Z_THRESHOLD`      | `3.0`            | Z-score threshold to flag an anomaly                |
| `TRIAGE_CONFIDENCE_CUTOFF` | `0.4`            | Below this confidence → dismiss                     |
| `ESCALATION_CONFIDENCE`    | `0.8`            | Above this + critical severity → Slack              |
| `ALERT_COOLDOWN_MINUTES`   | `10`             | Duplicate suppression window per anomaly type       |
| `PORT`                     | `8000`           | Server port (set automatically by cloud platforms)  |

---

## Performance Targets

| Metric                                | Target         |
|---------------------------------------|----------------|
| Detection latency (injection → alert) | < 90 s         |
| RCA generation (Groq / Llama 3.3)    | < 3 s          |
| End-to-end (injection → Slack)       | < 120 s        |
| Triage false-positive rate            | < 10%          |
| Event throughput                      | > 100 events/s |
| Frontend load time                    | < 1 s          |

---

## Project Structure

```
sentinel/
├── simulator/              # Event generator and anomaly injector
│   ├── event_generator.py  # Poisson-distributed e-commerce event stream
│   ├── anomaly_injector.py # Schedules and applies injection overrides
│   └── schema.py           # Event dataclass and field constants
│
├── pipeline/               # Stream ingestion and anomaly detection
│   ├── consumer.py         # Redpanda consumer (full Docker stack)
│   ├── processor.py        # DuckDB aggregation + z-score detection
│   └── queries.py          # All SQL query templates
│
├── agent/                  # LangGraph AI agent
│   ├── graph.py            # StateGraph definition and routing logic
│   ├── runner.py           # Redpanda-backed agent runner (full Docker stack)
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
├── .github/workflows/      # GitHub Actions — auto-deploys frontend to GitHub Pages
├── run_local.py            # Single-process runner — no Kafka needed (use this)
├── Procfile                # Railway / Render one-click deploy
├── docker-compose.yml      # Full stack: Redpanda + API
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Manual Test Walkthrough

1. Start the server: `python run_local.py`
2. Open **http://localhost:8000** — you should see the live event ticker immediately
3. Inject an anomaly: `curl -X POST http://localhost:8000/inject/revenue_crash`
4. Watch the terminal — within ~30 s you'll see:
   ```
   [processor] ANOMALY DETECTED → revenue_crash  z=-4.12
   [agent] ▶ triage
   [agent] ▶ context_fetch
   [agent] ▶ rca_writer
   [agent] ▶ decision
   ```
5. The anomaly card appears in the UI feed in real time (WebSocket push, no page refresh)
6. Click the card to open the RCA modal and read the full report

---

*Built by Prathamesh Mishra*
