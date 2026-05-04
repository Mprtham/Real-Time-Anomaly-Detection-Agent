const MAX_ROWS = 200;
let paused = false;
let pendingRows = [];

const ticker = document.getElementById('ticker');
const tickerWrap = document.getElementById('ticker-wrap');

tickerWrap.addEventListener('mouseenter', () => { paused = true; });
tickerWrap.addEventListener('mouseleave', () => {
  paused = false;
  flushPending();
});

function flushPending() {
  for (const row of pendingRows) prependRow(row);
  pendingRows = [];
}

function fmtTime(ts) {
  try {
    const d = new Date(ts);
    return d.toISOString().substring(11, 19);
  } catch { return '--:--:--'; }
}

function fmtDetail(event) {
  if (event.amount_usd) return `$${event.amount_usd.toFixed(2)}`;
  if (event.page)       return event.page;
  if (event.product_id) return event.product_id;
  return '-';
}

function prependRow(event) {
  const row = document.createElement('div');
  row.className = `ticker-row etype-${event.event_type || 'unknown'}`;
  row.innerHTML = `
    <span class="ts">${fmtTime(event.timestamp)}</span>
    <span class="etype">${event.event_type || '-'}</span>
    <span class="detail">${fmtDetail(event)}</span>
    <span class="country">${event.country || '-'}</span>
  `;
  ticker.prepend(row);

  // Trim old rows
  while (ticker.children.length > MAX_ROWS) {
    ticker.removeChild(ticker.lastChild);
  }
}

export function pushTickerEvent(event) {
  if (paused) {
    pendingRows.unshift(event);
    if (pendingRows.length > 50) pendingRows.pop();
    return;
  }
  prependRow(event);
}
