import { openSSE, openWS, fetchAnomalies, fetchMetrics } from './api.js';
import { pushTickerEvent } from './ticker.js';
import { renderAnomaly, loadInitialAnomalies } from './anomalyFeed.js';
import { initSparklines, updateSparklines } from './sparklines.js';

// ── sparklines ─────────────────────────────────────────────────────
const sparkStrip = document.getElementById('sparkline-strip');
initSparklines(sparkStrip);

// ── SSE: live events → ticker ──────────────────────────────────────
openSSE(event => pushTickerEvent(event));

// ── WebSocket: real-time anomaly push ─────────────────────────────
openWS(msg => {
  if (msg.type === 'anomaly' && msg.data) {
    renderAnomaly(msg.data);
  }
});

// ── agent node indicator ───────────────────────────────────────────
const nodeSteps = document.querySelectorAll('.node-step');
const nodeMap   = { triage: 0, context_fetch: 1, rca_writer: 2, decision: 3 };

function updateAgentNode(nodeName) {
  nodeSteps.forEach((el, i) => {
    el.classList.toggle('active', i === nodeMap[nodeName]);
  });
}

// ── API connection status ──────────────────────────────────────────
let _apiFailCount = 0;
const _liveDot    = document.querySelector('.live-dot');
const _liveLabel  = document.querySelector('.stat-pill span:not(.live-dot)');

function setConnectionStatus(ok) {
  if (!_liveDot) return;
  if (ok) {
    _liveDot.style.background = 'var(--green)';
    _liveDot.style.animation  = '';
    if (_liveLabel) _liveLabel.textContent = 'LIVE';
  } else {
    _liveDot.style.background = 'var(--red)';
    _liveDot.style.animation  = 'none';
    if (_liveLabel) _liveLabel.textContent = 'OFFLINE';
  }
}

// ── polling: metrics + anomalies ──────────────────────────────────
let _initialAnomalyLoad = true;

async function pollAnomalies() {
  try {
    const { anomalies } = await fetchAnomalies(null, 20);
    if (_initialAnomalyLoad) {
      _initialAnomalyLoad = false;
      loadInitialAnomalies(anomalies);  // reverses list so newest ends up on top
    } else {
      for (const a of anomalies) renderAnomaly(a);
    }
  } catch (e) {
    console.warn('anomaly poll failed', e);
  }
}

async function pollMetrics() {
  try {
    const m = await fetchMetrics();
    _apiFailCount = 0;
    setConnectionStatus(true);

    document.getElementById('stat-eps').textContent   = m.events_per_sec ?? '—';
    document.getElementById('stat-alast').textContent = m.anomalies_last_hour ?? '—';

    updateAgentNode(m.agent_current_node || 'idle');

    const lw = m.latest_window || {};
    setEl('sidebar-latency', lw.p99_latency != null ? `${Math.round(lw.p99_latency)}ms` : '—');
    setEl('sidebar-errrate', lw.error_rate  != null ? `${(lw.error_rate * 100).toFixed(1)}%` : '—');
    setEl('sidebar-orders',  lw.orders      != null ? lw.orders : '—');
    setEl('sidebar-revenue', lw.revenue     != null ? `$${Number(lw.revenue).toFixed(0)}` : '—');

    if (Object.keys(lw).length) updateSparklines(lw);

    const errRate   = lw.error_rate || 0;
    const ringColor = errRate > 0.15 ? 'var(--red)' : errRate > 0.05 ? 'var(--amber)' : 'var(--green)';
    document.getElementById('health-ring')?.setAttribute('stroke', ringColor);
    const healthPct = Math.max(0, 100 - errRate * 500);
    setEl('health-pct', `${Math.round(healthPct)}%`);

  } catch (e) {
    _apiFailCount++;
    if (_apiFailCount >= 2) setConnectionStatus(false);
    console.warn('metrics poll failed', e);
  }
}

function setEl(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// Initial load
pollAnomalies();
pollMetrics();

// Recurring
setInterval(pollMetrics,   5000);
setInterval(pollAnomalies, 10000);
