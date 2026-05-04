import { fetchRCA, resolveAnomaly } from './api.js';

const overlay = document.getElementById('modal-overlay');
const modal   = document.getElementById('modal');
const btnBack  = document.getElementById('modal-back');
const btnClose = document.getElementById('modal-close');
const modalTitle = document.getElementById('modal-title');
const modalBody  = document.getElementById('modal-body');
const modalFooter = document.getElementById('modal-footer');

let _currentAnomaly = null;
let _typewriterTimer = null;

function closeModal() {
  overlay.classList.remove('open');
  if (_typewriterTimer) clearInterval(_typewriterTimer);
}

btnBack.addEventListener('click', closeModal);
btnClose.addEventListener('click', closeModal);
overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function fmtSev(sev) {
  const colors = { critical: 'var(--red)', warning: 'var(--amber)', info: 'var(--teal)' };
  const bgs    = { critical: 'rgba(255,69,96,.15)', warning: 'rgba(255,184,0,.12)', info: 'rgba(0,229,204,.1)' };
  return `<span class="modal-sev-badge" style="color:${colors[sev]||colors.info};background:${bgs[sev]||bgs.info}">${(sev||'info').toUpperCase()}</span>`;
}

function fmtTitle(type) {
  return (type || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function fmtTs(ts) {
  try { return new Date(ts).toISOString().replace('T', ' ').substring(0, 19) + ' UTC'; }
  catch { return ts || ''; }
}

function buildMetricsGrid(anomaly) {
  const tiles = [
    { label: 'Metric',    val: anomaly.metric || '-',              change: null },
    { label: 'Current',   val: fmt(anomaly.metric_value, anomaly.metric), change: null },
    { label: 'Baseline',  val: fmt(anomaly.baseline_mean, anomaly.metric), change: null },
    { label: 'Z-score',   val: anomaly.z_score != null ? `${Math.abs(anomaly.z_score).toFixed(2)}σ` : '-', change: null },
    { label: 'Severity',  val: (anomaly.severity || '-').toUpperCase(), change: null },
    { label: 'Confidence',val: anomaly.confidence != null ? `${(anomaly.confidence*100).toFixed(0)}%` : '-', change: null },
  ];

  return `<div class="metrics-grid">${tiles.map(t => `
    <div class="metric-tile">
      <div class="tile-label">${t.label}</div>
      <div class="tile-val">${t.val}</div>
    </div>
  `).join('')}</div>`;
}

function fmt(val, metric) {
  if (val == null) return '-';
  if (metric === 'revenue') return `$${Number(val).toFixed(2)}`;
  if (metric === 'error_rate') return `${(val*100).toFixed(1)}%`;
  if (metric === 'p99_latency' || metric === 'avg_latency') return `${Math.round(val)}ms`;
  return Number(val).toFixed(2);
}

function typewrite(el, text, speed = 20) {
  el.textContent = '';
  let i = 0;
  _typewriterTimer = setInterval(() => {
    el.textContent += text[i++];
    if (i >= text.length) clearInterval(_typewriterTimer);
  }, speed);
}

export async function openRCAModal(anomaly) {
  _currentAnomaly = anomaly;
  if (_typewriterTimer) clearInterval(_typewriterTimer);

  const title = fmtTitle(anomaly.anomaly_type);
  modalTitle.textContent = `${title}`;

  modalBody.innerHTML = `
    <div style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);margin-bottom:16px">
      ${fmtTs(anomaly.detected_at)} · Anomaly ID: ${anomaly.anomaly_id || '-'}
    </div>

    <div class="modal-section">
      <div class="modal-section-title">📊 Metrics at Trigger</div>
      ${buildMetricsGrid(anomaly)}
    </div>

    <div class="modal-section">
      <div class="modal-section-title">
        🤖 Root Cause Analysis
        <span class="rca-model-tag">Llama 3.3 70B via Groq</span>
      </div>
      <div class="rca-text" id="rca-content">
        <span style="color:var(--text-muted);font-family:var(--font-mono);font-size:11px">Loading RCA…</span>
      </div>
    </div>
  `;

  // Footer
  modalFooter.innerHTML = `
    <button class="modal-btn" id="btn-copy">Copy RCA</button>
    <button class="modal-btn primary" id="btn-resolve">Mark Resolved</button>
  `;

  overlay.classList.add('open');

  // Fetch RCA
  try {
    const data = await fetchRCA(anomaly.anomaly_id);
    const rcaEl = document.getElementById('rca-content');
    if (data && data.report_text) {
      typewrite(rcaEl, data.report_text, 18);
    } else {
      rcaEl.textContent = 'RCA report not yet available. The agent may still be processing.';
      rcaEl.style.color = 'var(--text-muted)';
    }
  } catch {
    const rcaEl = document.getElementById('rca-content');
    rcaEl.textContent = 'RCA not available for this anomaly.';
    rcaEl.style.color = 'var(--text-muted)';
  }

  document.getElementById('btn-copy')?.addEventListener('click', () => {
    const text = document.getElementById('rca-content')?.textContent || '';
    navigator.clipboard.writeText(text).catch(() => {});
  });

  document.getElementById('btn-resolve')?.addEventListener('click', async () => {
    if (!_currentAnomaly) return;
    await resolveAnomaly(_currentAnomaly.anomaly_id);
    closeModal();
  });
}
