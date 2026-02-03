import { formatDateTime, formatPnL } from "./journal.utils.js";
import { initCharts, updateCharts } from "./journal.charts.js";

let originalData = [];
let currentSort = { column: null, direction: null };

const COLUMN_ORDER = [
  "id", "symbol", "boughtTimestamp", "soldTimestamp",
  "duration", "side", "qty",
  "buyPrice", "sellPrice", "pnl"
];

const COLUMN_NAMES = {
  id: "ID",
  symbol: "Symbol",
  boughtTimestamp: "Bought",
  soldTimestamp: "Sold",
  duration: "Duration",
  side: "Side",
  qty: "Qty",
  buyPrice: "Buy Price",
  sellPrice: "Sell Price",
  pnl: "PnL"
};

// ===== Fetch =====
fetch("/api/trades")
  .then(res => res.json())
  .then(data => {
    originalData = data.map(r => ({
      ...r,
      boughtTimestamp: new Date(r.boughtTimestamp),
      soldTimestamp: new Date(r.soldTimestamp)
    }));

    buildHeaders();
    buildRows(originalData);
    initCharts();
    updateCharts(originalData);
  });

// ===== Headers =====
function buildHeaders() {
  const thead = document.getElementById("headerRow");
  thead.innerHTML = "";

  COLUMN_ORDER.forEach(col => {
    const th = document.createElement("th");

    const label = document.createElement("span");
    label.textContent = COLUMN_NAMES[col] || col;
    label.className = "sortable";
    label.onclick = () => sortTable(col, label);

    const input = document.createElement("input");
    input.placeholder = "Filter";
    input.onkeyup = filterTable;
    input.onclick = e => e.stopPropagation();

    th.append(label, document.createElement("br"), input);
    thead.appendChild(th);
  });
}

// ===== Rows =====
function buildRows(data) {
  const tbody = document.querySelector("#tradeTable tbody");
  tbody.innerHTML = "";

  data.forEach(row => {
    const tr = document.createElement("tr");

    COLUMN_ORDER.forEach(col => {
      const td = document.createElement("td");

      if (col === "pnl") {
        td.textContent = formatPnL(row[col]);
        td.className = Number(row[col]) >= 0 ? "pnl-positive" : "pnl-negative";
      } else if (col.includes("Timestamp")) {
        td.textContent = formatDateTime(row[col]);
      } else {
        td.textContent = row[col] ?? "";
      }

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
}

// ===== Sorting =====
function sortTable(column, label) {
  document.querySelectorAll(".sortable")
    .forEach(h => h.classList.remove("active"));

  label.classList.add("active");

  const dir =
    currentSort.column === column && currentSort.direction === "asc"
      ? "desc" : "asc";

  currentSort = { column, direction: dir };

  const sorted = [...originalData].sort((a, b) => {
    const x = a[column];
    const y = b[column];

    if (x == null) return 1;
    if (y == null) return -1;

    if (x instanceof Date) return dir === "asc" ? x - y : y - x;
    if (!isNaN(x)) return dir === "asc" ? x - y : y - x;

    return dir === "asc"
      ? String(x).localeCompare(String(y))
      : String(y).localeCompare(String(x));
  });

  buildRows(sorted);
  updateCharts(sorted);
}

// ===== Filtering =====
function filterTable() {
  const inputs = document.querySelectorAll("th input");
  const dateFrom = document.getElementById("dateFrom").value;
  const dateTo = document.getElementById("dateTo").value;

  let filtered = [...originalData];

  if (dateFrom || dateTo) {
    const from = dateFrom ? new Date(dateFrom) : null;
    const to = dateTo ? new Date(dateTo) : null;

    filtered = filtered.filter(r => {
      if (from && r.boughtTimestamp < from) return false;
      if (to && r.boughtTimestamp > to) return false;
      return true;
    });
  }

  inputs.forEach((input, i) => {
    if (!input.value) return;
    const col = COLUMN_ORDER[i];

    filtered = filtered.filter(r =>
      String(r[col] ?? "")
        .toLowerCase()
        .includes(input.value.toLowerCase())
    );
  });

  buildRows(filtered);
  updateCharts(filtered);
}

window.applyDateFilter = filterTable;
