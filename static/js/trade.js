// static/js/trade.js

function normalizeTrades(trades) {
  return trades.map(t => ({
    ...t,
    entryTimestamp: new Date(t.entryTimestamp),
    exitTimestamp: new Date(t.exitTimestamp),
    setups: t.setups || []
  }));
}

async function fetchFilteredTrades(filters = {}) {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, val]) => {
    if (val == null || val === "") return;

    if (Array.isArray(val)) {
      val.forEach(v => params.append(key, v));
    } else {
      params.append(key, val);
    }
  });

  const res = await fetch(`/api/trades?${params.toString()}`);
  return await res.json();
}

// expose globally (important)
window.fetchFilteredTrades = fetchFilteredTrades;