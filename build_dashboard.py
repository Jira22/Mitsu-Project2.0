import json

with open("dashboard_data.json") as f:
    data_json_str = f.read()
# Defensive: prevent a stray "</script>" substring inside embedded JSON from
# prematurely closing the <script> tag.
data_json_str = data_json_str.replace("</", "<\\/")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Demand Forecasting Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
__CSS__
</style>
</head>
<body>
<div id="app"></div>
<script>
window.__DASHBOARD_DATA__ = __DATA_JSON__;
</script>
<script>
__JS__
</script>
</body>
</html>
"""

CSS = r"""
:root {
  --bg: #F1F3F6;
  --panel: #FFFFFF;
  --panel-alt: #F7F8FA;
  --text: #14161C;
  --text-soft: #5B6270;
  --text-faint: #8A90A0;
  --border: #E1E4EA;
  --border-soft: #ECEEF2;
  --accent: #C8102E;
  --accent-soft: #FCE9EC;
  --actual: #2C5AA0;
  --forecast: #E08E1D;
  --good: #1E8E5A;
  --good-soft: #E5F5ED;
  --warn: #C8102E;
  --warn-soft: #FCE9EC;
  --tier-high: #1E8E5A;
  --tier-medium: #E08E1D;
  --tier-low: #8A90A0;
  --shadow: 0 1px 2px rgba(20,22,28,0.04), 0 1px 12px rgba(20,22,28,0.05);
  --radius: 10px;
  --sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --display: 'Space Grotesk', var(--sans);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14161C;
    --panel: #1B1E27;
    --panel-alt: #21242F;
    --text: #EDEEF2;
    --text-soft: #ABB0BE;
    --text-faint: #6B7080;
    --border: #2C303C;
    --border-soft: #262932;
    --accent: #FF5C72;
    --accent-soft: #3A1620;
    --actual: #6EA3E8;
    --forecast: #F2B24C;
    --good: #4FCB8D;
    --good-soft: #123626;
    --warn: #FF5C72;
    --warn-soft: #3A1620;
    --tier-high: #4FCB8D;
    --tier-medium: #F2B24C;
    --tier-low: #6B7080;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 1px 12px rgba(0,0,0,0.35);
  }
}
:root[data-theme="dark"] {
  --bg: #14161C;
  --panel: #1B1E27;
  --panel-alt: #21242F;
  --text: #EDEEF2;
  --text-soft: #ABB0BE;
  --text-faint: #6B7080;
  --border: #2C303C;
  --border-soft: #262932;
  --accent: #FF5C72;
  --accent-soft: #3A1620;
  --actual: #6EA3E8;
  --forecast: #F2B24C;
  --good: #4FCB8D;
  --good-soft: #123626;
  --warn: #FF5C72;
  --warn-soft: #3A1620;
  --tier-high: #4FCB8D;
  --tier-medium: #F2B24C;
  --tier-low: #6B7080;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 1px 12px rgba(0,0,0,0.35);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
}
#app { display: flex; min-height: 100vh; }

/* ---------- Sidebar ---------- */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 10px 20px;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: 16px;
}
.brand-mark {
  width: 10px; height: 10px; border-radius: 2px;
  background: var(--accent);
  flex-shrink: 0;
  transform: rotate(45deg);
}
.brand-text { font-family: var(--display); font-weight: 700; font-size: 15px; letter-spacing: -0.01em; }
.brand-sub { font-size: 11px; color: var(--text-faint); margin-top: 2px; }

.navitem {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--text-soft);
  cursor: pointer;
  font-size: 13.5px;
  font-weight: 500;
  border: 1px solid transparent;
  transition: background 0.12s ease, color 0.12s ease;
}
.navitem:hover { background: var(--panel-alt); color: var(--text); }
.navitem.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.navitem .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: 0.55; flex-shrink: 0; }

.sidebar-tools {
  display: flex; flex-direction: column; gap: 6px;
  padding: 10px 10px 4px; border-top: 1px solid var(--border-soft);
}
.tool-btn { width: 100%; text-align: left; font-size: 12px; padding: 7px 10px; }

.sidebar-footer {
  margin-top: auto;
  padding: 12px 10px 4px;
  border-top: 1px solid var(--border-soft);
  font-size: 11px;
  color: var(--text-faint);
  line-height: 1.6;
}

/* ---------- Main ---------- */
.main { flex: 1; min-width: 0; padding: 28px 36px 60px; max-width: 1280px; }
.page-header { margin-bottom: 24px; }
.page-title { font-family: var(--display); font-size: 22px; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 4px; }
.page-desc { color: var(--text-soft); font-size: 13.5px; max-width: 640px; }

.view { display: none; }
.view.active { display: block; }

/* ---------- KPI cards ---------- */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
@media (max-width: 980px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi-card {
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; box-shadow: var(--shadow);
}
.kpi-label { font-size: 11.5px; color: var(--text-faint); font-weight: 500; margin-bottom: 8px; }
.kpi-value { font-family: var(--display); font-size: 24px; font-weight: 700; letter-spacing: -0.01em; }
.kpi-sub { font-size: 12px; color: var(--text-soft); margin-top: 4px; }
.kpi-sub.good { color: var(--good); }
.kpi-sub.warn { color: var(--warn); }

/* ---------- Panels ---------- */
.panel {
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px 22px; margin-bottom: 20px; box-shadow: var(--shadow);
}
.panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 4px; flex-wrap: wrap; }
.panel-title { font-family: var(--display); font-size: 15px; font-weight: 600; }
.panel-note { font-size: 12px; color: var(--text-faint); }
.panel-body { margin-top: 14px; }
.chart-wrap { position: relative; height: 320px; }
.chart-wrap.short { height: 240px; }

.legend-row { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 10px; font-size: 12px; color: var(--text-soft); }
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-swatch { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.legend-swatch.dashed { background: repeating-linear-gradient(90deg, currentColor 0 5px, transparent 5px 9px); height: 2px; }

/* ---------- Controls ---------- */
.field-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.field-label { font-size: 12.5px; color: var(--text-soft); font-weight: 500; }
select, input[type="number"], input[type="text"] {
  font-family: var(--sans); font-size: 13px; color: var(--text);
  background: var(--panel-alt); border: 1px solid var(--border); border-radius: 6px;
  padding: 7px 10px; outline: none;
}
select:focus, input[type="number"]:focus, input[type="text"]:focus { border-color: var(--actual); }
input[type="number"] { width: 130px; }

.btn {
  font-family: var(--sans); font-size: 12.5px; font-weight: 600; cursor: pointer;
  border-radius: 7px; padding: 8px 14px; border: 1px solid var(--border);
  background: var(--panel-alt); color: var(--text);
}
.btn:hover { background: var(--border-soft); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { opacity: 0.92; }

/* ---------- Tables ---------- */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border-soft); white-space: nowrap; }
th { color: var(--text-faint); font-weight: 600; font-size: 11.5px; text-transform: none; }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--text); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.table-scroll { overflow-x: auto; }

.tier-badge {
  display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
  padding: 3px 8px; border-radius: 12px;
}
.tier-badge.high_volume { background: var(--good-soft); color: var(--tier-high); }
.tier-badge.medium_volume { background: #FCF1DC; color: var(--tier-medium); }
.tier-badge.low_volume { background: var(--panel-alt); color: var(--tier-low); }
:root[data-theme="dark"] .tier-badge.medium_volume { background: #3A2E14; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .tier-badge.medium_volume { background: #3A2E14; }
}

input.param-input {
  width: 90px; padding: 5px 8px; font-size: 12.5px;
}
.editable-note { font-size: 11.5px; color: var(--text-faint); margin-top: 8px; }

.callout {
  border-radius: 8px; padding: 12px 14px; font-size: 13px; display: flex; gap: 10px; align-items: flex-start;
  border: 1px solid var(--border);
  background: var(--panel-alt);
  color: var(--text-soft);
  margin-top: 14px;
}
.callout strong { color: var(--text); }
.callout.warn { background: var(--warn-soft); border-color: transparent; color: var(--warn); }
.callout.warn strong { color: var(--warn); }

.two-col { display: grid; grid-template-columns: 1.3fr 1fr; gap: 20px; }
@media (max-width: 980px) { .two-col { grid-template-columns: 1fr; } }

.stat-list { display: flex; flex-direction: column; gap: 10px; }
.stat-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-soft); }
.stat-row:last-child { border-bottom: none; }
.stat-name { font-size: 13px; color: var(--text); }
.stat-bar-wrap { flex: 1; height: 6px; background: var(--panel-alt); border-radius: 3px; margin: 0 12px; overflow: hidden; }
.stat-bar { height: 100%; background: var(--actual); border-radius: 3px; }
.stat-val { font-size: 12.5px; color: var(--text-soft); font-variant-numeric: tabular-nums; min-width: 70px; text-align: right; }

.tag-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.tag { font-size: 11.5px; padding: 4px 9px; border-radius: 6px; background: var(--panel-alt); border: 1px solid var(--border-soft); color: var(--text-soft); }

@media (max-width: 760px) {
  #app { flex-direction: column; }
  .sidebar { width: 100%; flex-direction: row; overflow-x: auto; padding: 12px; align-items: center; }
  .brand { display: none; }
  .sidebar-footer { display: none; }
  .sidebar-tools { display: none; }
  .navitem { flex-shrink: 0; }
  .main { padding: 20px 16px 40px; }
  .kpi-row { grid-template-columns: 1fr 1fr; }
}

/* ---------- Print / export as PDF ---------- */
@media print {
  .sidebar { display: none !important; }
  #app { display: block !important; }
  .main { max-width: 100% !important; padding: 0 !important; }
  body { background: #fff !important; color: #000 !important; }
  .panel, .kpi-card { box-shadow: none !important; border: 1px solid #ccc !important; break-inside: avoid; }
  .btn, .field-row select, .field-row input, #item-search { display: none !important; }
  .chart-wrap { height: 260px !important; }
  a { text-decoration: none !important; color: inherit !important; }
}
"""

with open("build.css", "w") as f:
    f.write(CSS)

with open("app.js") as f:
    js_str = f.read()

html = TEMPLATE.replace("__CSS__", CSS).replace("__DATA_JSON__", data_json_str).replace("__JS__", js_str)
with open("dashboard_final.html", "w") as f:
    f.write(html)

print("final html written, length:", len(html))
