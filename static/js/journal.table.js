let originalData = [];
let currentSort = { column: null, direction: null };

// Column display names
const COLUMN_NAMES = {
  id: "ID",
  symbol: "Symbol",
  boughtTimestamp: "Bought",
  soldTimestamp: "Sold",
  //duration: "Duration",
  side: "Side",
  qty: "Qty",
  buyPrice: "Buy Price",
  sellPrice: "Sell Price",
  pnl: "PnL"
};

// Column order
const COLUMN_ORDER = [
  "id",
  "symbol",
  "boughtTimestamp",
  "soldTimestamp",
  //"duration",
  "side",
  "qty",
  "buyPrice",
  "sellPrice",
  "pnl"
];

// Fetch trades and initialize table
fetch("/api/trades")
  .then(res => res.json())
  .then(data => {
    // Convert timestamps to Date objects
    originalData = data.map(row => ({
      ...row,
      boughtTimestamp: new Date(row.boughtTimestamp),
      soldTimestamp: new Date(row.soldTimestamp)
    }));

    buildHeaders(COLUMN_ORDER);
    buildRows(originalData, COLUMN_ORDER);
  });

// ---------------------- Formatting ----------------------
function formatDateTime(d) {
  if (!(d instanceof Date) || isNaN(d)) return "";

  const pad = n => String(n).padStart(2, "0");
  return (
    d.getFullYear() + "/" +
    pad(d.getMonth() + 1) + "/" +
    pad(d.getDate()) + " " +
    pad(d.getHours()) + ":" +
    pad(d.getMinutes()) + ":" +
    pad(d.getSeconds())
  );
}

function formatPnL(value) {
  const num = Number(value);
  if (isNaN(num)) return "";
  const formatted = Math.abs(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return num < 0 ? `($${formatted})` : `$${formatted}`;
}

// ---------------------- Build table ----------------------
function buildHeaders(columns) {
  const thead = document.getElementById("headerRow");
  thead.innerHTML = "";

  columns.forEach(col => {
    const th = document.createElement("th");

    const label = document.createElement("span");
    label.textContent = COLUMN_NAMES[col] || col;
    label.className = "sortable";
    label.addEventListener("click", () => sortTable(col, label));

    const input = document.createElement("input");
    input.placeholder = "Filter";
    input.addEventListener("keyup", filterTable);
    input.addEventListener("click", e => e.stopPropagation());
    input.addEventListener("mousedown", e => e.stopPropagation());

    th.append(label, document.createElement("br"), input);
    thead.appendChild(th);
  });
}

function buildRows(data, columns) {
  const tbody = document.querySelector("#tradeTable tbody");
  tbody.innerHTML = "";

  data.forEach(row => {
    const tr = document.createElement("tr");

    columns.forEach(col => {
      const td = document.createElement("td");

      if (col === "pnl") {
        td.textContent = formatPnL(row[col]);
        td.className = Number(row[col]) >= 0 ? "pnl-positive" : "pnl-negative";
      } else if (col === "boughtTimestamp" || col === "soldTimestamp") {
        td.textContent = formatDateTime(row[col]);
      } else {
        td.textContent = row[col] ?? "";
      }

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
}

// ---------------------- Sorting ----------------------
function sortTable(column, label) {
  document.querySelectorAll(".sortable").forEach(h => h.classList.remove("active"));
  label.classList.add("active");

  const direction = currentSort.column === column && currentSort.direction === "asc" ? "desc" : "asc";
  currentSort = { column, direction };

  const sorted = [...originalData].sort((a, b) => {
    if (a[column] == null) return 1;
    if (b[column] == null) return -1;

    if (a[column] instanceof Date) return direction === "asc" ? a[column] - b[column] : b[column] - a[column];
    if (!isNaN(a[column])) return direction === "asc" ? a[column] - b[column] : b[column] - a[column];
    return direction === "asc" ? String(a[column]).localeCompare(String(b[column])) : String(b[column]).localeCompare(String(a[column]));
  });

  buildRows(sorted, COLUMN_ORDER);
}

// ---------------------- Filtering ----------------------
function filterTable() {
  const inputs = document.querySelectorAll("th input");
  const dateFrom = document.getElementById("dateFrom").value;
  const dateTo = document.getElementById("dateTo").value;

  let filtered = [...originalData];

  // Date filter
  if (dateFrom || dateTo) {
    const from = dateFrom ? new Date(dateFrom) : null;
    const to = dateTo ? new Date(dateTo) : null;

    filtered = filtered.filter(row => {
      const d = row.boughtTimestamp;
      if (from && d < from) return false;
      if (to && d > to) return false;
      return true;
    });
  }

  // Column filters
  inputs.forEach((input, index) => {
    if (!input.value) return;
    const col = COLUMN_ORDER[index];
    filtered = filtered.filter(row => String(row[col] ?? "").toLowerCase().includes(input.value.toLowerCase()));
  });

  buildRows(filtered, COLUMN_ORDER);
}

// ---------------------- Reset ----------------------
function resetSort() {
  currentSort = { column: null, direction: null };
  document.querySelectorAll(".sortable").forEach(h => h.classList.remove("active"));
  document.querySelectorAll("th input").forEach(input => input.value = "");
  document.getElementById("dateFrom").value = "";
  document.getElementById("dateTo").value = "";
  buildRows(originalData, COLUMN_ORDER);
}

// ---------------------- Event listeners for buttons ----------------------
document.getElementById("date-btn").addEventListener("click", filterTable);
document.getElementById("resetSort").addEventListener("click", resetSort);
