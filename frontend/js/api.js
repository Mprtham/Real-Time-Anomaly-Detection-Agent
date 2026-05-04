// Resolve API base URL — three cases handled in priority order:
//   1. window.SENTINEL_API set in index.html → use that (GitHub Pages → external backend)
//   2. localhost/127.0.0.1                   → local dev, always port 8000
//   3. everything else                        → same-origin (FastAPI serves this file)
const _loc     = window.location;
const _isLocal = _loc.hostname === 'localhost' || _loc.hostname === '127.0.0.1';
const API_BASE = window.SENTINEL_API
  || (_isLocal ? `${_loc.protocol}//${_loc.hostname}:8000` : _loc.origin);

export async function fetchAnomalies(severity = null, limit = 30) {
  const params = new URLSearchParams({ limit });
  if (severity) params.set('severity', severity);
  const r = await fetch(`${API_BASE}/anomalies?${params}`);
  if (!r.ok) throw new Error(`anomalies fetch failed: ${r.status}`);
  return r.json();
}

export async function fetchRCA(anomalyId) {
  const r = await fetch(`${API_BASE}/rca/${anomalyId}`);
  if (!r.ok) throw new Error(`rca fetch failed: ${r.status}`);
  return r.json();
}

export async function fetchMetrics() {
  const r = await fetch(`${API_BASE}/metrics`);
  if (!r.ok) throw new Error(`metrics fetch failed: ${r.status}`);
  return r.json();
}

export async function resolveAnomaly(anomalyId) {
  const r = await fetch(`${API_BASE}/anomalies/${anomalyId}/resolve`, { method: 'POST' });
  return r.json();
}

export async function injectAnomaly(type) {
  const r = await fetch(`${API_BASE}/inject/${type}`, { method: 'POST' });
  return r.json();
}

export function openSSE(onEvent) {
  const es = new EventSource(`${API_BASE}/events/stream`);
  es.onmessage = e => {
    try { onEvent(JSON.parse(e.data)); } catch (_) {}
  };
  es.onerror = () => { /* browser reconnects automatically */ };
  return es;
}

export function openWS(onMessage, _attempt = 0) {
  const proto = _loc.protocol === 'https:' ? 'wss' : 'ws';
  const host  = _isLocal ? `${_loc.hostname}:8000` : _loc.host;
  const ws    = new WebSocket(`${proto}://${host}/ws/live`);

  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)); } catch (_) {}
  };

  ws.onopen  = () => { _attempt = 0; };  // reset backoff on successful connect

  ws.onclose = () => {
    // Exponential backoff: 2s, 3s, 4.5s … capped at 30s
    const delay = Math.min(30000, 2000 * Math.pow(1.5, _attempt));
    setTimeout(() => openWS(onMessage, _attempt + 1), delay);
  };

  return ws;
}
