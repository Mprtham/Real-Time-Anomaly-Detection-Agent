const API_BASE = window.location.hostname === 'localhost'
  ? 'http://localhost:8000'
  : `${window.location.protocol}//${window.location.hostname}:8000`;

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
  es.onerror = () => { /* reconnects automatically */ };
  return es;
}

export function openWS(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host  = API_BASE.replace(/^https?:\/\//, '');
  const ws    = new WebSocket(`${proto}://${host}/ws/live`);
  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)); } catch (_) {}
  };
  ws.onclose = () => setTimeout(() => openWS(onMessage), 2000);
  return ws;
}
