const SPARK_W = 80;
const SPARK_H = 24;
const MAX_PTS = 20;

const series = {
  orders:      { label: 'Orders/min',  data: [], color: 'var(--teal)',  el: null, valEl: null, fmt: v => Math.round(v) },
  revenue:     { label: 'Revenue/min', data: [], color: 'var(--green)', el: null, valEl: null, fmt: v => `$${Number(v).toFixed(0)}` },
  error_rate:  { label: 'Error %',     data: [], color: 'var(--red)',   el: null, valEl: null, fmt: v => `${(v * 100).toFixed(1)}%` },
  p99_latency: { label: 'p99 latency', data: [], color: 'var(--amber)', el: null, valEl: null, fmt: v => `${Math.round(v)}ms` },
};

function makeSVG(data, color) {
  if (data.length < 2) return `<svg width="${SPARK_W}" height="${SPARK_H}"></svg>`;

  const min   = Math.min(...data);
  const max   = Math.max(...data);
  const range = max - min || 1;

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * SPARK_W;
    const y = SPARK_H - ((v - min) / range) * (SPARK_H - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  return `<svg width="${SPARK_W}" height="${SPARK_H}" viewBox="0 0 ${SPARK_W} ${SPARK_H}">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

export function initSparklines(container) {
  for (const [key, s] of Object.entries(series)) {
    const item = document.createElement('div');
    item.className = 'spark-item';

    const valEl = document.createElement('span');
    valEl.className = 'spark-val';
    valEl.id = `spark-val-${key}`;
    s.valEl = valEl;

    const svgEl = document.createElement('span');
    svgEl.id = `spark-${key}`;
    s.el = svgEl;

    item.innerHTML = `<span class="spark-label">${s.label}</span>`;
    item.appendChild(valEl);
    item.appendChild(svgEl);
    container.appendChild(item);
  }
}

export function updateSparklines(window) {
  for (const [key, s] of Object.entries(series)) {
    const val = window[key];
    if (val == null) continue;

    s.data.push(Number(val));
    if (s.data.length > MAX_PTS) s.data.shift();

    if (s.el)    s.el.innerHTML    = makeSVG(s.data, s.color);
    if (s.valEl) s.valEl.textContent = s.fmt(val);
  }
}
