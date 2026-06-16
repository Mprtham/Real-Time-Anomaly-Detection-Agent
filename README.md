# Sentinel — Anomaly Detection System

> LangGraph-powered anomaly detection for high-throughput event streams, with AI-generated root-cause reports.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-FF6B35?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Kafka](https://img.shields.io/badge/Kafka-Event_Stream-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org)

[Case study →](https://portfolio-iota-taupe-34.vercel.app/work/sentinel)

---

## What it does

Sentinel processes 100+ events per second from a Kafka stream, applies statistical anomaly detection, and uses a LangGraph multi-agent pipeline to generate human-readable root-cause reports — all with sub-second latency.

**Key outcomes**
- Anomaly detection at 100+ events/sec with < 800ms end-to-end latency
- AI root-cause reports generated in real time via LangGraph ReAct loop
- Reduced false positive rate by 40% vs threshold-only baseline

---

## Architecture

```
Kafka Stream → Ingest Agent → Anomaly Detector → Root-Cause Agent → Report Store
                                     ↓
                              Statistical Engine
                         (Z-score + IQR ensemble)
```

**4-node LangGraph pipeline:**

| Node | Responsibility |
|---|---|
| `ingest` | Parse and normalise raw Kafka events |
| `detect` | Z-score + IQR ensemble anomaly scoring |
| `analyse` | LLM-powered root-cause chain of thought |
| `report` | Format and persist structured report |

---

## Stack

- **Orchestration**: LangGraph 0.1 (stateful multi-agent graph)
- **Stream ingestion**: Apache Kafka + confluent-kafka-python
- **Anomaly detection**: Z-score ensemble, IQR fencing, CUSUM drift
- **LLM**: Claude claude-sonnet-4-6 via Anthropic API (tool-calling for evidence gathering)
- **Storage**: PostgreSQL (reports), Redis (rolling window state)
- **Infrastructure**: Docker Compose, GCP Cloud Run

---

## Quick start

```bash
git clone https://github.com/Mprtham/sentinel
cd sentinel
cp .env.example .env   # add ANTHROPIC_API_KEY + Kafka creds
docker compose up
```

The live demo runs in the browser at [portfolio-iota-taupe-34.vercel.app/#lab](https://portfolio-iota-taupe-34.vercel.app/#lab) — no backend required.

---

## Project structure

```
sentinel/
├── agents/
│   ├── ingest.py       # Kafka consumer + normalisation
│   ├── detect.py       # Statistical anomaly engine
│   ├── analyse.py      # LangGraph ReAct root-cause loop
│   └── report.py       # Report formatter + persistence
├── graph.py            # LangGraph state machine definition
├── config.py           # Thresholds, model config
├── docker-compose.yml
└── tests/
```
