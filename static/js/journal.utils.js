// ===== Formatting =====
function pad(n) {
  return String(n).padStart(2, "0");
}

export function formatDateTime(value) {
  if (!value) return "";

  const d = value instanceof Date ? value : new Date(value);
  if (isNaN(d)) return "";

  return (
    d.getFullYear() + "/" +
    pad(d.getMonth() + 1) + "/" +
    pad(d.getDate()) + " " +
    pad(d.getHours()) + ":" +
    pad(d.getMinutes()) + ":" +
    pad(d.getSeconds())
  );
}

export function formatPnL(value) {
  const num = Number(value);
  if (isNaN(num)) return "";

  const formatted = Math.abs(num).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  return num < 0 ? `($${formatted})` : `$${formatted}`;
}

// ===== Analytics helpers =====
export function winRate(data) {
  if (!data.length) return 0;
  const wins = data.filter(r => Number(r.pnl) > 0).length;
  return (wins / data.length) * 100;
}

export function biggestWinLoss(data) {
  let maxWin = null;
  let maxLoss = null;

  data.forEach(r => {
    const pnl = Number(r.pnl);
    if (isNaN(pnl)) return;

    if (maxWin === null || pnl > maxWin) maxWin = pnl;
    if (maxLoss === null || pnl < maxLoss) maxLoss = pnl;
  });

  return { maxWin, maxLoss };
}

export function maxDrawdown(data) {
  let peak = 0;
  let equity = 0;
  let maxDD = 0;

  data.forEach(r => {
    equity += Number(r.pnl) || 0;
    peak = Math.max(peak, equity);
    maxDD = Math.min(maxDD, equity - peak);
  });

  return maxDD;
}
