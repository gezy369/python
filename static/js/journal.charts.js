import {
  formatPnL,
  winRate,
  biggestWinLoss,
  maxDrawdown
} from "./journal.utils.js";

let pnlChart;

// Create chart containers dynamically (right side)
export function initCharts() {
  const container = document.getElementById("charts");
  container.innerHTML = `
    <canvas id="pnlChart"></canvas>
    <div id="stats"></div>
  `;
}

export function updateCharts(data) {
  renderPnLChart(data);
  renderStats(data);
}

// ===== PnL over time =====
function renderPnLChart(data) {
  const ctx = document.getElementById("pnlChart");

  const labels = data.map(r =>
    r.boughtTimestamp.toISOString().slice(0, 10)
  );

  let equity = 0;
  const values = data.map(r => {
    equity += Number(r.pnl) || 0;
    return equity;
  });

  if (pnlChart) pnlChart.destroy();

  pnlChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Equity Curve",
        data: values,
        borderWidth: 2,
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false }
      }
    }
  });
}

// ===== Stats =====
function renderStats(data) {
  const stats = document.getElementById("stats");

  const wr = winRate(data).toFixed(1);
  const { maxWin, maxLoss } = biggestWinLoss(data);
  const dd = maxDrawdown(data);

  stats.innerHTML = `
    <p><strong>Win rate:</strong> ${wr}%</p>
    <p><strong>Biggest win:</strong> ${formatPnL(maxWin)}</p>
    <p><strong>Biggest loss:</strong> ${formatPnL(maxLoss)}</p>
    <p><strong>Max drawdown:</strong> ${formatPnL(dd)}</p>
  `;
}
