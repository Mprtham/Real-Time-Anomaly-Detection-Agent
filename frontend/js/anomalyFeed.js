import { openRCAModal } from './rca.js';

const list        = document.getElementById('anomaly-list');
const emptyEl     = document.getElementById('anomaly-empty');
const renderedIds = new Set();

const SEV_LABEL = { critical: 'CRIT', warning: 'WARN', info: 'INFO' };

function fmtTime(ts) {
  try {
    const d = new Date(ts);
    return d.toISOString().substring(11, 16) + ' UTC';
  } catch { return ''; }
}

function fmtTitle(type) {
  return (type || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function _updateEmptyState() {
  if (emptyEl) emptyEl.style.display = renderedIds.size === 0 ? 'flex' : 'none';
}

function _pruneList() {
  // Keep DOM bounded to 50 cards; evict oldest and remove their IDs from the dedup set
  while (list.children.length > 50) {
    const removed = list.lastChild;
    if (removed?.dataset?.id) renderedIds.delete(removed.dataset.id);
    list.removeChild(removed);
  }
}

export function renderAnomaly(anomaly, { animate = true } = {}) {
  if (renderedIds.has(anomaly.anomaly_id)) return;
  renderedIds.add(anomaly.anomaly_id);

  const sev  = anomaly.severity || 'info';
  const card = document.createElement('div');

  const animClass  = animate ? ' anomaly-card-new' : '';
  const pulseClass = sev === 'critical' && animate ? ' active-pulse' : '';
  card.className   = `anomaly-card sev-${sev}${animClass}${pulseClass}`;
  card.dataset.id  = anomaly.anomaly_id;

  const zBadge = anomaly.z_score != null
    ? `<span class="z-badge">${Math.abs(anomaly.z_score).toFixed(1)}σ</span>`
    : '';

  const rcaStatus = anomaly.has_rca
    ? '<span style="color:var(--teal);font-size:10px;font-family:var(--font-mono)">RCA ready →</span>'
    : '<span style="color:var(--text-muted);font-size:10px;font-family:var(--font-mono)">Investigating…</span>';

  card.innerHTML = `
    <div class="card-top">
      <span class="sev-badge ${sev}">${SEV_LABEL[sev] || sev}</span>
      <span class="card-ts">${fmtTime(anomaly.detected_at)}</span>
    </div>
    <div class="card-title">${fmtTitle(anomaly.anomaly_type)}</div>
    <div class="card-meta">
      ${zBadge}
      <span>${anomaly.metric || ''}</span>
    </div>
    <div style="margin-top:6px">${rcaStatus}</div>
  `;

  card.addEventListener('click', () => {
    card.classList.remove('active-pulse');
    openRCAModal(anomaly);
  });

  list.prepend(card);
  _pruneList();
  _updateEmptyState();
}

export function loadInitialAnomalies(anomalies) {
  // Render oldest first so newest ends up on top after prepend; no animation for historical cards
  for (const a of [...anomalies].reverse()) renderAnomaly(a, { animate: false });
}
