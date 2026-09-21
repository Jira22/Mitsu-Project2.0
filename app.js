(function () {
  "use strict";
  const DATA = window.__DASHBOARD_DATA__;
  const CATS = DATA.categories;
  const COLORS = {
    actual: getVar("--actual"), forecast: getVar("--forecast"),
    accent: getVar("--accent"), good: getVar("--good"), text: getVar("--text-soft"),
  };

  function getVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  }

  // ---------------- number formatting ----------------
  function fmtCompact(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return n.toFixed(0);
  }
  function fmtCurrency(n) { return "\u0e3f" + fmtCompact(n); }
  function fmtInt(n) { return Math.round(n).toLocaleString(); }
  function fmtPct(n) { return n === null || n === undefined ? "—" : (n * 100).toFixed(1) + "%"; }
  function monthLabel(m) {
    const [y, mo] = m.split("-");
    const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return names[parseInt(mo, 10) - 1] + " '" + y.slice(2);
  }
  function fiscalQuarterOf(m) {
    const mo = parseInt(m.split("-")[1], 10);
    if (mo >= 4 && mo <= 6) return "Q1 (Apr\u2013Jun)";
    if (mo >= 7 && mo <= 9) return "Q2 (Jul\u2013Sep)";
    if (mo >= 10 && mo <= 12) return "Q3 (Oct\u2013Dec)";
    return "Q4 (Jan\u2013Mar)";
  }

  // ---------------- local storage (per-viewer only) ----------------
  const LS_TARGET = "mitsu_fy2025_revenue_target";
  const LS_PARAMS = "mitsu_inventory_params_v1";
  const LS_NOTES = "mitsu_review_notes_v1";
  const LS_THEME = "mitsu_theme_pref";
  function loadTarget() {
    try { const v = localStorage.getItem(LS_TARGET); return v ? parseFloat(v) : null; } catch (e) { return null; }
  }
  function saveTarget(v) {
    try { localStorage.setItem(LS_TARGET, String(v)); } catch (e) {}
  }
  function loadParams() {
    try { const v = localStorage.getItem(LS_PARAMS); return v ? JSON.parse(v) : {}; } catch (e) { return {}; }
  }
  function saveParams(obj) {
    try { localStorage.setItem(LS_PARAMS, JSON.stringify(obj)); } catch (e) {}
  }
  function loadNotes() {
    try { const v = localStorage.getItem(LS_NOTES); return v ? JSON.parse(v) : {}; } catch (e) { return {}; }
  }
  function saveNotes(obj) {
    try { localStorage.setItem(LS_NOTES, JSON.stringify(obj)); } catch (e) {}
  }
  function loadTheme() {
    try { return localStorage.getItem(LS_THEME) || "auto"; } catch (e) { return "auto"; }
  }
  function saveTheme(t) {
    try { localStorage.setItem(LS_THEME, t); } catch (e) {}
  }
  function applyTheme(t) {
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
  }

  // ---------------- CSV export ----------------
  function csvEscape(v) {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function downloadCSV(filename, rows) {
    const csv = rows.map(r => r.map(csvEscape).join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function csvButton(id, label) {
    return `<button class="btn" id="${id}">${label || "Export CSV"}</button>`;
  }

  // ---------------- sortable tables ----------------
  // colDefs: [{ key, label, numeric }]; data: array of row objects; render(rowObj) -> array of cell values (for both display + CSV use elsewhere)
  function makeSortState(defaultKey, defaultDir) {
    return { key: defaultKey, dir: defaultDir || "desc" };
  }
  function sortRows(rows, colDefs, state) {
    const col = colDefs.find(c => c.key === state.key);
    if (!col) return rows;
    const sorted = rows.slice().sort((a, b) => {
      let av = col.get(a), bv = col.get(b);
      if (col.numeric) { av = av || 0; bv = bv || 0; return av - bv; }
      av = String(av || ""); bv = String(bv || "");
      return av.localeCompare(bv);
    });
    if (state.dir === "desc") sorted.reverse();
    return sorted;
  }
  function sortableHeaderHtml(colDefs, state) {
    return colDefs.map(c => {
      const arrow = state.key === c.key ? (state.dir === "asc" ? " \u2191" : " \u2193") : "";
      return `<th class="${c.numeric ? "num" : ""} sortable" data-sort-key="${c.key}">${c.label}${arrow}</th>`;
    }).join("");
  }
  function attachSortHandlers(theadEl, colDefs, state, onChange) {
    theadEl.querySelectorAll("th[data-sort-key]").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sortKey;
        if (state.key === key) state.dir = state.dir === "asc" ? "desc" : "asc";
        else { state.key = key; state.dir = "desc"; }
        onChange();
      });
    });
  }

  // ---------------- derived aggregates ----------------
  function companySeries() {
    const actual = DATA.company_monthly_actual.map(r => ({ month: r.month, units: r.units, revenue: r.revenue }));
    const forecast = DATA.company_monthly_forecast.map(r => ({ month: r.month, units: r.units_forecast, revenue: r.revenue_forecast }));
    return { actual, forecast };
  }

  function categorySeries(cat) {
    const actual = DATA.monthly_actuals_by_category.filter(r => r.category === cat)
      .map(r => ({ month: r.month, units: r.units, revenue: r.revenue }));
    const forecast = DATA.monthly_forecast_by_category.filter(r => r.category === cat)
      .map(r => ({ month: r.month, units: r.units_forecast, revenue: r.revenue_forecast }));
    return { actual, forecast };
  }

  function fy2025ByCategory(metric) {
    const key = metric === "units" ? "units_forecast" : "revenue_forecast";
    const totals = {};
    CATS.forEach(c => totals[c] = 0);
    DATA.monthly_forecast_by_category.forEach(r => { totals[r.category] += r[key]; });
    return totals;
  }

  // ================================================================
  // Chart helpers
  // ================================================================
  function buildActualForecastChart(ctx, actual, forecast, metric, opts) {
    opts = opts || {};
    const labels = actual.map(r => r.month).concat(forecast.map(r => r.month));
    const actualData = actual.map(r => r[metric]).concat(forecast.map(() => null));
    // bridge: connect the last actual point into the forecast line
    const bridgeVal = actual.length ? actual[actual.length - 1][metric] : null;
    const forecastData = actual.map(() => null);
    forecastData[forecastData.length - 1] = bridgeVal;
    forecast.forEach(r => forecastData.push(r[metric]));

    return new Chart(ctx, {
      type: "line",
      data: {
        labels: labels.map(monthLabel),
        datasets: [
          {
            label: "Actual", data: actualData, borderColor: COLORS.actual,
            backgroundColor: COLORS.actual + "22", borderWidth: 2, pointRadius: 0,
            tension: 0.25, fill: opts.fill ? "origin" : false, spanGaps: false,
          },
          {
            label: "FY2025 Forecast", data: forecastData, borderColor: COLORS.forecast,
            borderDash: [6, 4], borderWidth: 2, pointRadius: 0, tension: 0.25, fill: false, spanGaps: false,
          },
        ],
      },
      options: chartBaseOptions(metric),
    });
  }

  function chartBaseOptions(metric) {
    return {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              if (c.raw === null) return null;
              const v = metric === "revenue" ? fmtCurrency(c.raw) : fmtInt(c.raw) + " units";
              return c.dataset.label + ": " + v;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: getVar("--text-faint"), maxRotation: 0, autoSkip: true, font: { size: 10.5 } } },
        y: {
          grid: { color: getVar("--border-soft") },
          ticks: {
            color: getVar("--text-faint"), font: { size: 10.5 },
            callback: (v) => metric === "revenue" ? fmtCurrency(v) : fmtCompact(v),
          },
        },
      },
    };
  }

  function buildBacktestChart(ctx, metric) {
    const rows = DATA.backtest_company_monthly;
    const labels = rows.map(r => monthLabel(r.month));
    const actualKey = metric + "_actual", predKey = metric + "_predicted";
    return new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Actual (FY2024)", data: rows.map(r => r[actualKey]), borderColor: COLORS.actual, borderWidth: 2, pointRadius: 2, tension: 0.2 },
          { label: "Predicted", data: rows.map(r => r[predKey]), borderColor: COLORS.forecast, borderDash: [6, 4], borderWidth: 2, pointRadius: 2, tension: 0.2 },
        ],
      },
      options: chartBaseOptions(metric),
    });
  }

  // ================================================================
  // Views
  // ================================================================
  const app = document.getElementById("app");

  const NAV = [
    { id: "overview", label: "Overview" },
    { id: "revenue", label: "Revenue Forecast" },
    { id: "units", label: "Unit Sales Forecast" },
    { id: "items", label: "SKU-Level Detail" },
    { id: "performance", label: "Model Performance" },
    { id: "insights", label: "Customer & Industry" },
  ];

  function renderShell() {
    const nav = NAV.map(n =>
      `<div class="navitem" data-nav="${n.id}"><span class="dot"></span>${n.label}</div>`
    ).join("");
    app.innerHTML = `
      <div class="sidebar">
        <div class="brand">
          <span class="brand-mark"></span>
          <div>
            <div class="brand-text">Demand Console</div>
            <div class="brand-sub">Sales & Inventory Forecasting</div>
          </div>
        </div>
        ${nav}
        <div class="sidebar-tools">
          <button class="btn tool-btn" id="theme-toggle" title="Toggle color theme"></button>
          <button class="btn tool-btn" id="print-btn" title="Print or export this view as PDF">Print / PDF</button>
        </div>
        <div class="sidebar-footer">
          Data through ${DATA.meta.data_through}<br>
          Forecast: ${DATA.meta.forecast_horizon}
        </div>
      </div>
      <div class="main">
        <div id="view-overview" class="view"></div>
        <div id="view-revenue" class="view"></div>
        <div id="view-units" class="view"></div>
        <div id="view-items" class="view"></div>
        <div id="view-performance" class="view"></div>
        <div id="view-insights" class="view"></div>
      </div>
    `;
    document.querySelectorAll(".navitem").forEach(el => {
      el.addEventListener("click", () => switchView(el.dataset.nav));
    });

    const themeBtn = document.getElementById("theme-toggle");
    const THEME_LABELS = { auto: "\u25d0 Theme: Auto", light: "\u2600 Theme: Light", dark: "\u25cf Theme: Dark" };
    function refreshThemeBtn() { themeBtn.textContent = THEME_LABELS[loadTheme()]; }
    applyTheme(loadTheme());
    refreshThemeBtn();
    themeBtn.addEventListener("click", () => {
      const order = ["auto", "light", "dark"];
      const next = order[(order.indexOf(loadTheme()) + 1) % order.length];
      saveTheme(next); applyTheme(next); refreshThemeBtn();
    });

    document.getElementById("print-btn").addEventListener("click", () => window.print());
  }

  function switchView(id) {
    document.querySelectorAll(".navitem").forEach(el => el.classList.toggle("active", el.dataset.nav === id));
    document.querySelectorAll(".view").forEach(el => el.classList.toggle("active", el.id === "view-" + id));
    const renderers = { overview: renderOverview, revenue: renderRevenue, units: renderUnits, items: renderItems, performance: renderPerformance, insights: renderInsights };
    const el = document.getElementById("view-" + id);
    if (!el.dataset.rendered) {
      renderers[id](el);
      el.dataset.rendered = "1";
    }
  }

  // ---------------- Overview ----------------
  function renderOverview(el) {
    const m = DATA.backtest_metrics_summary;
    const fy = DATA.fy2025_totals;
    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Overview</h1>
        <div class="page-desc">Company-wide sales performance and the FY2025 forecast, generated from four years of order history (${DATA.meta.generated_from}).</div>
      </div>
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-label">FY2025 Forecast Revenue</div>
          <div class="kpi-value">${fmtCurrency(fy.revenue)}</div>
          <div class="kpi-sub">Apr 2025 \u2013 Mar 2026</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">FY2025 Forecast Units</div>
          <div class="kpi-value">${fmtInt(fy.units)}</div>
          <div class="kpi-sub">Across ${CATS.length} product categories</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Backtest Accuracy \u2014 Revenue</div>
          <div class="kpi-value">${fmtPct(1 - m.revenue.fy24_test_wape_macro)}</div>
          <div class="kpi-sub">Company-total WAPE on FY2024 holdout</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Backtest Accuracy \u2014 Units</div>
          <div class="kpi-value">${fmtPct(1 - m.units.fy24_test_wape_macro)}</div>
          <div class="kpi-sub">Company-total WAPE on FY2024 holdout</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Company-wide monthly revenue: actual vs. FY2025 forecast</div>
          <div class="field-row">
            <select id="ov-metric">
              <option value="revenue">Revenue</option>
              <option value="units">Units</option>
            </select>
          </div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap"><canvas id="ov-chart"></canvas></div>
          <div class="legend-row">
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.actual}"></span>Actual (FY2021\u2013FY2024)</div>
            <div class="legend-item" style="color:${COLORS.forecast}"><span class="legend-swatch dashed"></span>FY2025 forecast</div>
          </div>
        </div>
        <div class="callout">
          <div><strong>Note on the FY2023 shift:</strong> ${DATA.meta.note_regime_shift}</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">Methodology</div>
        <div class="panel-body" style="font-size:13px; color:var(--text-soft); line-height:1.7;">
          <p style="margin:0 0 10px;">${DATA.meta.model}. ${DATA.meta.note_lightgbm}</p>
          <p style="margin:0;">${DATA.meta.note_hybrid_model}</p>
        </div>
      </div>
    `;
    const cs = companySeries();
    let chart = buildActualForecastChart(document.getElementById("ov-chart").getContext("2d"), cs.actual, cs.forecast, "revenue");
    document.getElementById("ov-metric").addEventListener("change", (e) => {
      chart.destroy();
      chart = buildActualForecastChart(document.getElementById("ov-chart").getContext("2d"), cs.actual, cs.forecast, e.target.value);
    });
  }

  // ---------------- Revenue Forecast ----------------
  function renderRevenue(el) {
    const totalsRev = fy2025ByCategory("revenue");
    const totalForecast = Object.values(totalsRev).reduce((a, b) => a + b, 0);
    const savedTarget = loadTarget();

    const catOptions = `<option value="__all__">All categories (company total)</option>` +
      CATS.map(c => `<option value="${c}">${c}</option>`).join("");

    const revColDefs = [
      { key: "category", label: "Category", get: r => r.category },
      { key: "revenue", label: "FY2025 forecast revenue", numeric: true, get: r => r.revenue },
      { key: "tier", label: "Confidence", get: r => r.tier },
    ];
    const revSortState = makeSortState("revenue", "desc");
    const revRowData = CATS.map(c => ({ category: c, revenue: totalsRev[c], tier: DATA.category_volume_tier[c] }));

    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Revenue Forecast</h1>
        <div class="page-desc">FY2025 sales revenue forecast by category, for strategic planning and performance tracking against target.</div>
      </div>

      <div class="two-col">
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">Monthly revenue: actual vs. forecast</div>
            <div class="field-row">
              <select id="rev-cat">${catOptions}</select>
            </div>
          </div>
          <div class="panel-body">
            <div class="chart-wrap"><canvas id="rev-chart"></canvas></div>
            <div class="legend-row">
              <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.actual}"></span>Actual</div>
              <div class="legend-item" style="color:${COLORS.forecast}"><span class="legend-swatch dashed"></span>FY2025 forecast</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">FY2025 revenue target</div>
          <div class="panel-body">
            <div class="field-row" style="margin-bottom:14px;">
              <span class="field-label">Target (\u0e3f)</span>
              <input type="number" id="target-input" placeholder="e.g. 2200000000" value="${savedTarget !== null ? savedTarget : ""}">
              <button class="btn primary" id="save-target">Save</button>
            </div>
            <div id="target-callout"></div>
            <div class="editable-note">Saved to this browser only \u2014 not shared with other viewers. Enter your confirmed FY2025 target once available.</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">FY2025 forecast revenue by category</div>
          ${csvButton("rev-export", "Export CSV")}
        </div>
        <div class="panel-body table-scroll">
          <table id="rev-table">
            <thead><tr></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    `;

    function renderRevTable() {
      const sorted = sortRows(revRowData, revColDefs, revSortState);
      const thead = document.querySelector("#rev-table thead tr");
      thead.innerHTML = sortableHeaderHtml(revColDefs, revSortState);
      document.querySelector("#rev-table tbody").innerHTML = sorted.map(r => `
        <tr>
          <td>${r.category}</td>
          <td class="num">${fmtCurrency(r.revenue)}</td>
          <td><span class="tier-badge ${r.tier}">${r.tier.replace("_", " ")}</span></td>
        </tr>`).join("");
      attachSortHandlers(thead, revColDefs, revSortState, renderRevTable);
    }
    renderRevTable();

    document.getElementById("rev-export").addEventListener("click", () => {
      const sorted = sortRows(revRowData, revColDefs, revSortState);
      const rows = [["Category", "FY2025 Forecast Revenue (THB)", "Confidence Tier"]];
      sorted.forEach(r => rows.push([r.category, r.revenue.toFixed(2), r.tier]));
      downloadCSV("fy2025_revenue_by_category.csv", rows);
    });

    let chart;
    function drawRevChart(cat) {
      if (chart) chart.destroy();
      const s = cat === "__all__" ? companySeries() : categorySeries(cat);
      chart = buildActualForecastChart(document.getElementById("rev-chart").getContext("2d"), s.actual, s.forecast, "revenue");
    }
    drawRevChart("__all__");
    document.getElementById("rev-cat").addEventListener("change", (e) => drawRevChart(e.target.value));

    function renderTargetCallout() {
      const t = loadTarget();
      const box = document.getElementById("target-callout");
      if (t === null || isNaN(t) || t <= 0) {
        box.innerHTML = `<div class="callout">No target saved yet \u2014 enter the FY2025 revenue target to see forecast-vs-target variance.</div>`;
        return;
      }
      const variance = totalForecast - t;
      const variancePct = variance / t;
      const cls = variance >= 0 ? "good" : "warn";
      box.innerHTML = `
        <div class="callout ${cls === "warn" ? "warn" : ""}">
          <div>
            Forecast <strong>${fmtCurrency(totalForecast)}</strong> vs. target <strong>${fmtCurrency(t)}</strong>
            \u2014 <strong>${variance >= 0 ? "+" : ""}${fmtCurrency(variance)} (${(variancePct * 100).toFixed(1)}%)</strong>
            ${variance >= 0 ? "above target" : "below target"}.
          </div>
        </div>`;
    }
    renderTargetCallout();
    document.getElementById("save-target").addEventListener("click", () => {
      const v = parseFloat(document.getElementById("target-input").value);
      if (!isNaN(v) && v > 0) { saveTarget(v); renderTargetCallout(); }
    });
  }

  // ---------------- Unit Sales Forecast ----------------
  function renderUnits(el) {
    const totalsUnits = fy2025ByCategory("units");
    const params = loadParams();
    const notes = loadNotes();

    // Build quarterly pivot: category -> {Q1..Q4}
    const quarters = ["Q1 (Apr\u2013Jun)", "Q2 (Jul\u2013Sep)", "Q3 (Oct\u2013Dec)", "Q4 (Jan\u2013Mar)"];
    const pivot = {};
    CATS.forEach(c => pivot[c] = { "Q1 (Apr\u2013Jun)": 0, "Q2 (Jul\u2013Sep)": 0, "Q3 (Oct\u2013Dec)": 0, "Q4 (Jan\u2013Mar)": 0 });
    DATA.monthly_forecast_by_category.forEach(r => {
      pivot[r.category][fiscalQuarterOf(r.month)] += r.units_forecast;
    });

    const sortedCats = CATS.slice().sort((a, b) => totalsUnits[b] - totalsUnits[a]);

    const rows = sortedCats.map(c => {
      const p = params[c] || {};
      const tier = DATA.category_volume_tier[c];
      return `<tr data-cat="${c}">
        <td>${c} <span class="tier-badge ${tier}" style="margin-left:6px;">${tier.replace("_", " ")}</span></td>
        ${quarters.map(q => `<td class="num">${fmtInt(pivot[c][q])}</td>`).join("")}
        <td class="num" style="font-weight:600;">${fmtInt(totalsUnits[c])}</td>
        <td><input type="number" class="param-input safety" data-cat="${c}" placeholder="\u2014" value="${p.safety !== undefined ? p.safety : ""}"></td>
        <td><input type="number" class="param-input reorder" data-cat="${c}" placeholder="\u2014" value="${p.reorder !== undefined ? p.reorder : ""}"></td>
        <td><input type="text" class="param-input notes-input" data-cat="${c}" placeholder="e.g. reviewed, on track" value="${notes[c] ? notes[c].replace(/"/g, "&quot;") : ""}"></td>
      </tr>`;
    }).join("");

    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Unit Sales Forecast</h1>
        <div class="page-desc">Monthly unit-volume forecast by product category, laid out by fiscal quarter to match the quarterly purchasing review cycle. Safety stock and reorder point are left for the Purchasing team to set based on lead times \u2014 they are not auto-calculated.</div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Monthly units: actual vs. forecast</div>
          <div class="field-row">
            <select id="units-cat">
              <option value="__all__">All categories (company total)</option>
              ${sortedCats.map(c => `<option value="${c}">${c}</option>`).join("")}
            </select>
          </div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap"><canvas id="units-chart"></canvas></div>
          <div class="legend-row">
            <div class="legend-item"><span class="legend-swatch" style="background:${COLORS.actual}"></span>Actual</div>
            <div class="legend-item" style="color:${COLORS.forecast}"><span class="legend-swatch dashed"></span>FY2025 forecast</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">FY2025 quarterly unit forecast &amp; inventory parameters</div>
          <div class="field-row">
            ${csvButton("units-export", "Export CSV")}
            <button class="btn primary" id="save-params">Save parameters &amp; notes</button>
          </div>
        </div>
        <div class="panel-body table-scroll">
          <table>
            <thead><tr>
              <th>Category</th>
              ${quarters.map(q => `<th class="num">${q}</th>`).join("")}
              <th class="num">FY2025 total</th>
              <th>Safety stock</th>
              <th>Reorder point</th>
              <th>Quarterly review notes</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="editable-note">Safety stock, reorder point, and notes are saved to this browser only. Review each quarter and adjust as new actuals come in.</div>
      </div>
    `;

    let chart;
    function drawUnitsChart(cat) {
      if (chart) chart.destroy();
      const s = cat === "__all__" ? companySeries() : categorySeries(cat);
      chart = buildActualForecastChart(document.getElementById("units-chart").getContext("2d"), s.actual, s.forecast, "units");
    }
    drawUnitsChart("__all__");
    document.getElementById("units-cat").addEventListener("change", (e) => drawUnitsChart(e.target.value));

    document.getElementById("units-export").addEventListener("click", () => {
      const header = ["Category", ...quarters, "FY2025 Total Units", "Safety Stock", "Reorder Point", "Notes"];
      const csvRows = [header];
      const currentParams = loadParams(), currentNotes = loadNotes();
      sortedCats.forEach(c => {
        const p = currentParams[c] || {};
        csvRows.push([
          c, ...quarters.map(q => Math.round(pivot[c][q])), Math.round(totalsUnits[c]),
          p.safety !== undefined ? p.safety : "", p.reorder !== undefined ? p.reorder : "",
          currentNotes[c] || "",
        ]);
      });
      downloadCSV("fy2025_units_by_category.csv", csvRows);
    });

    document.getElementById("save-params").addEventListener("click", () => {
      const out = {};
      document.querySelectorAll(".param-input.safety").forEach(inp => {
        const c = inp.dataset.cat;
        out[c] = out[c] || {};
        if (inp.value !== "") out[c].safety = parseFloat(inp.value);
      });
      document.querySelectorAll(".param-input.reorder").forEach(inp => {
        const c = inp.dataset.cat;
        out[c] = out[c] || {};
        if (inp.value !== "") out[c].reorder = parseFloat(inp.value);
      });
      saveParams(out);

      const outNotes = {};
      document.querySelectorAll(".notes-input").forEach(inp => {
        if (inp.value.trim() !== "") outNotes[inp.dataset.cat] = inp.value.trim();
      });
      saveNotes(outNotes);

      const btn = document.getElementById("save-params");
      const original = btn.textContent;
      btn.textContent = "Saved";
      setTimeout(() => { btn.textContent = original; }, 1200);
    });
  }

  // ---------------- SKU-Level Detail ----------------
  function renderItems(el) {
    const items = DATA.item_forecast_fy2025;
    const longTail = DATA.item_long_tail_summary;
    const nQual = DATA.n_qualifying_items;
    const nTail = DATA.n_long_tail_items;
    const cmp = DATA.hybrid_vs_direct_comparison;

    const byCategory = {};
    items.forEach(it => { (byCategory[it.category] = byCategory[it.category] || []).push(it); });
    Object.values(byCategory).forEach(arr => arr.sort((a, b) => b.fy2025_revenue - a.fy2025_revenue));

    const catsWithItems = Object.keys(byCategory).sort((a, b) => {
      const totA = byCategory[a].reduce((s, i) => s + i.fy2025_revenue, 0);
      const totB = byCategory[b].reduce((s, i) => s + i.fy2025_revenue, 0);
      return totB - totA;
    });

    const itemColDefs = [
      { key: "item", label: "Item", get: r => r.item },
      { key: "q1", label: "Q1", numeric: true, get: r => r.quarters.Q1.units },
      { key: "q2", label: "Q2", numeric: true, get: r => r.quarters.Q2.units },
      { key: "q3", label: "Q3", numeric: true, get: r => r.quarters.Q3.units },
      { key: "q4", label: "Q4", numeric: true, get: r => r.quarters.Q4.units },
      { key: "fy2025_units", label: "FY2025 units", numeric: true, get: r => r.fy2025_units },
      { key: "fy2025_revenue", label: "FY2025 revenue", numeric: true, get: r => r.fy2025_revenue },
    ];
    const itemSortState = makeSortState("fy2025_revenue", "desc");

    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">SKU-Level Detail</h1>
        <div class="page-desc">Item-level FY2025 forecast for the ${nQual} highest-volume items (\u226524 months of sales history \u2014 these cover the large majority of revenue). The remaining ${nTail} long-tail items don't have enough individual history to forecast reliably, so they're shown as a single allocated total per category.</div>
      </div>

      <div class="callout">
        <div><strong>Why item-level forecasts exist alongside category forecasts:</strong> a hybrid approach (item-level model for high-volume SKUs + proportional allocation for the long tail) was tested against a pure category-level model on the FY2024 holdout and found to modestly improve accuracy \u2014
        units WAPE ${(cmp.units.hybrid_item_plus_longtail_wape*100).toFixed(1)}% vs ${(cmp.units.direct_category_model_wape*100).toFixed(1)}%,
        revenue WAPE ${(cmp.revenue.hybrid_item_plus_longtail_wape*100).toFixed(1)}% vs ${(cmp.revenue.direct_category_model_wape*100).toFixed(1)}%.
        That's why the hybrid forecast is used as the primary FY2025 number throughout this dashboard.</div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Browse or search items</div>
          <div class="field-row">
            <input type="text" id="item-search" placeholder="Search item code (all categories)\u2026" style="width:200px;">
            <select id="item-cat-select">
              ${catsWithItems.map(c => `<option value="${c}">${c} (${byCategory[c].length} items)</option>`).join("")}
            </select>
            ${csvButton("item-export", "Export CSV")}
          </div>
        </div>
        <div class="panel-body table-scroll" id="item-table-wrap"></div>
      </div>
    `;

    let currentRows = [];
    let currentTail = null;
    let currentLabel = "";

    function renderTable() {
      const searchTerm = document.getElementById("item-search").value.trim().toLowerCase();
      let arr, tail, label;
      if (searchTerm) {
        arr = items.filter(it => it.item.toLowerCase().includes(searchTerm));
        tail = null;
        label = `search results for "${searchTerm}"`;
      } else {
        const cat = document.getElementById("item-cat-select").value;
        arr = byCategory[cat] || [];
        tail = longTail[cat];
        label = cat;
      }
      const sorted = sortRows(arr, itemColDefs, itemSortState);
      currentRows = sorted; currentTail = tail; currentLabel = label;

      const showCatCol = !!searchTerm;
      const rows = sorted.map(it => `
        <tr>
          <td>${it.item}${showCatCol ? ` <span class="tag" style="margin-left:6px;">${it.category}</span>` : ""}</td>
          <td class="num">${fmtInt(it.quarters.Q1.units)}</td>
          <td class="num">${fmtInt(it.quarters.Q2.units)}</td>
          <td class="num">${fmtInt(it.quarters.Q3.units)}</td>
          <td class="num">${fmtInt(it.quarters.Q4.units)}</td>
          <td class="num" style="font-weight:600;">${fmtInt(it.fy2025_units)}</td>
          <td class="num">${fmtCurrency(it.fy2025_revenue)}</td>
        </tr>`).join("");
      const tailRow = tail ? `
        <tr style="color:var(--text-faint); font-style:italic;">
          <td>Other items (long-tail, allocated)</td>
          <td class="num" colspan="4">\u2014</td>
          <td class="num">${fmtInt(tail.units)}</td>
          <td class="num">${fmtCurrency(tail.revenue)}</td>
        </tr>` : "";
      const emptyRow = sorted.length === 0 ? `<tr><td colspan="7" style="color:var(--text-faint);">No items match that search.</td></tr>` : "";

      document.getElementById("item-table-wrap").innerHTML = `
        <table id="item-table">
          <thead><tr>${sortableHeaderHtml(itemColDefs, itemSortState)}</tr></thead>
          <tbody>${rows}${tailRow}${emptyRow}</tbody>
        </table>
        <div class="editable-note">Quarters follow the fiscal year (Q1 = Apr\u2013Jun 2025 ... Q4 = Jan\u2013Mar 2026).</div>
      `;
      attachSortHandlers(document.querySelector("#item-table thead"), itemColDefs, itemSortState, renderTable);
    }

    renderTable();
    document.getElementById("item-cat-select").addEventListener("change", renderTable);
    document.getElementById("item-search").addEventListener("input", renderTable);

    document.getElementById("item-export").addEventListener("click", () => {
      const header = ["Item", "Category", "Q1 units", "Q2 units", "Q3 units", "Q4 units", "FY2025 units", "FY2025 revenue (THB)"];
      const csvRows = [header];
      currentRows.forEach(it => csvRows.push([
        it.item, it.category, Math.round(it.quarters.Q1.units), Math.round(it.quarters.Q2.units),
        Math.round(it.quarters.Q3.units), Math.round(it.quarters.Q4.units),
        Math.round(it.fy2025_units), it.fy2025_revenue.toFixed(2),
      ]));
      if (currentTail) csvRows.push(["Other items (long-tail, allocated)", currentLabel, "", "", "", "", Math.round(currentTail.units), currentTail.revenue.toFixed(2)]);
      downloadCSV(`fy2025_items_${currentLabel.replace(/[^a-z0-9]+/gi, "_")}.csv`, csvRows);
    });
  }

  // ---------------- Model Performance ----------------
  function renderPerformance(el) {
    const m = DATA.backtest_metrics_summary;
    const byCatRev = DATA.backtest_by_category.filter(r => r.target === "revenue").sort((a, b) => (b.wape || 0) - (a.wape || 0));
    const byCatUnits = DATA.backtest_by_category.filter(r => r.target === "units");
    const unitsMap = {}; byCatUnits.forEach(r => unitsMap[r.category] = r.wape);

    const rows = byCatRev.map(r => {
      const tier = DATA.category_volume_tier[r.category];
      return `<tr>
        <td>${r.category} <span class="tier-badge ${tier}" style="margin-left:6px;">${tier.replace("_", " ")}</span></td>
        <td class="num">${fmtPct(r.wape)}</td>
        <td class="num">${fmtPct(unitsMap[r.category])}</td>
      </tr>`;
    }).join("");

    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Model Performance</h1>
        <div class="page-desc">Out-of-time backtest: the model is trained on data before FY2024 and evaluated against FY2024 actuals it never saw during training.</div>
      </div>

      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-label">Revenue WAPE \u2014 company total</div>
          <div class="kpi-value">${fmtPct(m.revenue.fy24_test_wape_macro)}</div>
          <div class="kpi-sub">Lower is better</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Revenue WAPE \u2014 by category</div>
          <div class="kpi-value">${fmtPct(m.revenue.fy24_test_wape_granular)}</div>
          <div class="kpi-sub">Granular, harder than company total</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Units WAPE \u2014 company total</div>
          <div class="kpi-value">${fmtPct(m.units.fy24_test_wape_macro)}</div>
          <div class="kpi-sub">Lower is better</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Units WAPE \u2014 by category</div>
          <div class="kpi-value">${fmtPct(m.units.fy24_test_wape_granular)}</div>
          <div class="kpi-sub">Granular, harder than company total</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">FY2024 holdout: actual vs. predicted (company total)</div>
          <div class="field-row">
            <select id="perf-metric">
              <option value="revenue">Revenue</option>
              <option value="units">Units</option>
            </select>
          </div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap"><canvas id="perf-chart"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Accuracy by category (FY2024 holdout)</div>
          ${csvButton("perf-export", "Export CSV")}
        </div>
        <div class="panel-body table-scroll">
          <table id="perf-table">
            <thead><tr><th>Category</th><th class="num">Revenue WAPE</th><th class="num">Units WAPE</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="callout">
          Low-volume / intermittent categories (marked <span class="tier-badge low_volume" style="margin:0 2px;">low volume</span>) naturally show higher error \u2014 there are too few historical transactions for the model to learn a stable pattern. Forecasts for these categories should be treated as directional, not precise.
        </div>
      </div>
    `;

    document.getElementById("perf-export").addEventListener("click", () => {
      const header = ["Category", "Revenue WAPE", "Units WAPE", "Confidence Tier"];
      const csvRows = [header];
      byCatRev.forEach(r => csvRows.push([
        r.category, r.wape !== null ? (r.wape * 100).toFixed(2) + "%" : "",
        unitsMap[r.category] !== undefined && unitsMap[r.category] !== null ? (unitsMap[r.category] * 100).toFixed(2) + "%" : "",
        DATA.category_volume_tier[r.category],
      ]));
      downloadCSV("fy2024_backtest_by_category.csv", csvRows);
    });

    let chart = buildBacktestChart(document.getElementById("perf-chart").getContext("2d"), "revenue");
    document.getElementById("perf-metric").addEventListener("change", (e) => {
      chart.destroy();
      chart = buildBacktestChart(document.getElementById("perf-chart").getContext("2d"), e.target.value);
    });
  }

  // ---------------- Customer & Industry Insights ----------------
  function renderInsights(el) {
    const byType = DATA.revenue_by_customer_type;
    const totalRev = byType.reduce((a, b) => a + b.revenue, 0);
    const maxCust = Math.max(...DATA.top_customers.map(c => c.revenue));
    const maxInd = Math.max(...DATA.top_industries.map(c => c.revenue));

    el.innerHTML = `
      <div class="page-header">
        <h1 class="page-title">Customer &amp; Industry Insights</h1>
        <div class="page-desc">Where the revenue actually comes from \u2014 useful context alongside the forecast when prioritizing accounts and industries.</div>
      </div>

      <div class="two-col">
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">Top 10 customers by total revenue (FY2021\u2013FY2024)</div>
            ${csvButton("cust-export", "Export CSV")}
          </div>
          <div class="panel-body stat-list">
            ${DATA.top_customers.map(c => `
              <div class="stat-row">
                <div class="stat-name">${c.company}</div>
                <div class="stat-bar-wrap"><div class="stat-bar" style="width:${(c.revenue / maxCust * 100).toFixed(1)}%"></div></div>
                <div class="stat-val">${fmtCurrency(c.revenue)}</div>
              </div>`).join("")}
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">Revenue by customer type</div>
          <div class="panel-body">
            <div class="chart-wrap short"><canvas id="cust-type-chart"></canvas></div>
            <div class="tag-row">
              ${byType.map(t => `<span class="tag">${t.customer_type}: ${((t.revenue / totalRev) * 100).toFixed(0)}%</span>`).join("")}
            </div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">Top industries by total revenue (FY2021\u2013FY2024)</div>
          ${csvButton("ind-export", "Export CSV")}
        </div>
        <div class="panel-body stat-list">
          ${DATA.top_industries.map(c => `
            <div class="stat-row">
              <div class="stat-name">${c.industry}</div>
              <div class="stat-bar-wrap"><div class="stat-bar" style="width:${(c.revenue / maxInd * 100).toFixed(1)}%; background:${COLORS.forecast}"></div></div>
              <div class="stat-val">${fmtCurrency(c.revenue)}</div>
            </div>`).join("")}
        </div>
      </div>
    `;

    document.getElementById("cust-export").addEventListener("click", () => {
      downloadCSV("top_customers.csv", [["Company", "Total Revenue (THB)"], ...DATA.top_customers.map(c => [c.company, c.revenue.toFixed(2)])]);
    });
    document.getElementById("ind-export").addEventListener("click", () => {
      downloadCSV("top_industries.csv", [["Industry", "Total Revenue (THB)"], ...DATA.top_industries.map(c => [c.industry, c.revenue.toFixed(2)])]);
    });

    new Chart(document.getElementById("cust-type-chart").getContext("2d"), {
      type: "doughnut",
      data: {
        labels: byType.map(t => t.customer_type),
        datasets: [{ data: byType.map(t => t.revenue), backgroundColor: [COLORS.actual, COLORS.forecast, COLORS.accent, "#8A90A0"], borderWidth: 0 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { color: getVar("--text-soft"), boxWidth: 10, font: { size: 11.5 } } },
          tooltip: { callbacks: { label: (c) => c.label + ": " + fmtCurrency(c.raw) } },
        },
        cutout: "62%",
      },
    });
  }

  // ---------------- init ----------------
  renderShell();
  switchView("overview");
})();
