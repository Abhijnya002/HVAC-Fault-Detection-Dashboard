"""Build a self-contained, interactive HTML dashboard summarizing AHU
sensor trends and fault detection results.

Reads the CSVs produced by fault_detection.py / generate_data.py and emits
output/dashboard.html — a single file with embedded data, vanilla SVG
charts, hover tooltips, legends, a light/dark toggle, and a table-view
fallback for each chart. No external JS/CSS dependencies, so it opens
directly from disk or renders as a GitHub Pages static file.
"""

import json

import pandas as pd

# Categorical slots from the validated reference palette (see dataviz skill
# references/palette.md), assigned in a fixed order per context.
SERIES_COLORS = {
    "supply_air_temp": {"light": "#2a78d6", "dark": "#3987e5", "label": "Supply Air Temp"},
    "mixed_air_temp": {"light": "#1baf7a", "dark": "#199e70", "label": "Mixed Air Temp"},
    "precision": {"light": "#2a78d6", "dark": "#3987e5", "label": "Precision"},
    "recall": {"light": "#1baf7a", "dark": "#199e70", "label": "Recall"},
}

FAULT_COLORS = {
    "stuck_damper": {"light": "#eda100", "dark": "#c98500", "label": "Stuck damper"},
    "sat_sensor_drift": {"light": "#008300", "dark": "#008300", "label": "SAT sensor drift"},
    "low_delta_t_cooling_fault": {"light": "#4a3aa7", "dark": "#9085e9", "label": "Low delta-T cooling fault"},
    "fan_performance_fault": {"light": "#e34948", "dark": "#e66767", "label": "Fan performance fault"},
}


def _fault_windows(df):
    """Collapse consecutive rows sharing a fault label into start/end windows."""
    blocks = (df["fault_label"] != df["fault_label"].shift()).cumsum()
    windows = []
    for _, group in df.groupby(blocks):
        label = group["fault_label"].iloc[0]
        if label == "none":
            continue
        windows.append(
            {
                "type": label,
                "label": FAULT_COLORS[label]["label"],
                "start": int(group["timestamp"].iloc[0].timestamp() * 1000),
                "end": int(group["timestamp"].iloc[-1].timestamp() * 1000),
            }
        )
    return windows


def build_dashboard_data():
    result = pd.read_csv("output/ahu_fault_detection_results.csv", parse_dates=["timestamp"])
    summary = pd.read_csv("output/fault_detection_summary.csv")

    fault_counts = (
        result.loc[result["detected_fault_type"] != "none", "detected_fault_type"]
        .value_counts()
        .reindex(FAULT_COLORS.keys(), fill_value=0)
    )

    # Table view uses hourly samples (every 12th row at 5-min resolution) so
    # the fallback table stays readable; full-resolution data lives in the
    # committed CSVs.
    hourly = result.iloc[::12]

    data = {
        "generatedFrom": {
            "rows": int(len(result)),
            "startDate": result["timestamp"].iloc[0].strftime("%Y-%m-%d"),
            "endDate": result["timestamp"].iloc[-1].strftime("%Y-%m-%d"),
        },
        "kpis": {
            "totalRows": int(len(result)),
            "flaggedIntervals": int(result["any_fault_detected"].sum()),
            "avgPrecision": round(float(summary["precision"].mean()), 3),
            "avgRecall": round(float(summary["recall"].mean()), 3),
        },
        "timeseries": {
            "timestampsMs": (result["timestamp"].astype("int64") // 10**6).tolist(),
            "series": [
                {
                    "key": "supply_air_temp",
                    "name": SERIES_COLORS["supply_air_temp"]["label"],
                    "values": result["supply_air_temp"].round(2).tolist(),
                },
                {
                    "key": "mixed_air_temp",
                    "name": SERIES_COLORS["mixed_air_temp"]["label"],
                    "values": result["mixed_air_temp"].round(2).tolist(),
                },
            ],
            "faultWindows": _fault_windows(result),
        },
        "faultCounts": [
            {"type": t, "label": FAULT_COLORS[t]["label"], "count": int(c)}
            for t, c in fault_counts.items()
        ],
        "precisionRecall": [
            {
                "type": row["fault_type"],
                "label": FAULT_COLORS[row["fault_type"]]["label"],
                "precision": float(row["precision"]),
                "recall": float(row["recall"]),
            }
            for _, row in summary.iterrows()
        ],
        "table": {
            "timestamps": hourly["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
            "supplyAirTemp": hourly["supply_air_temp"].round(2).tolist(),
            "mixedAirTemp": hourly["mixed_air_temp"].round(2).tolist(),
            "faultLabel": hourly["fault_label"].tolist(),
        },
        "colors": {
            "series": SERIES_COLORS,
            "faults": FAULT_COLORS,
        },
    }
    return data


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HVAC Fault Detection Dashboard</title>
<style>
  .viz-root {
    --surface-1:      #fcfcfb;
    --page-plane:      #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:       #e1e0d9;
    --baseline:       #c3c2b7;
    --border:         rgba(11,11,11,0.10);
  }
  .viz-root[data-theme="dark"] {
    --surface-1:      #1a1a19;
    --page-plane:      #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --gridline:       #2c2c2a;
    --baseline:       #383835;
    --border:         rgba(255,255,255,0.10);
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body.viz-root {
    background: var(--page-plane);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }
  header.dash-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 16px; margin-bottom: 28px;
  }
  header.dash-header h1 { font-size: 22px; margin: 0 0 6px; font-weight: 600; }
  header.dash-header p { margin: 0; color: var(--text-secondary); font-size: 14px; max-width: 640px; }
  #theme-toggle {
    flex: none; border: 1px solid var(--border); background: var(--surface-1);
    color: var(--text-primary); border-radius: 8px; padding: 8px 14px;
    font-size: 13px; cursor: pointer; font-family: inherit;
  }
  #theme-toggle:hover { border-color: var(--text-muted); }

  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
  .kpi-tile {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 18px;
  }
  .kpi-tile .kpi-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
  .kpi-tile .kpi-value { font-size: 28px; font-weight: 600; color: var(--text-primary); }

  .card {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 20px 12px; margin-bottom: 20px;
  }
  .card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; flex-wrap: wrap; gap: 8px;}
  .card h2 { font-size: 15px; margin: 0; font-weight: 600; }
  .card .card-sub { font-size: 12px; color: var(--text-muted); margin: 0 0 12px; }
  .table-toggle {
    font-size: 12px; color: var(--text-secondary); background: none; border: none;
    cursor: pointer; text-decoration: underline; font-family: inherit; padding: 0;
  }
  .table-toggle:hover { color: var(--text-primary); }

  .legend-row { display: flex; flex-wrap: wrap; gap: 14px; margin: 6px 0 14px; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
  .legend-swatch-line { width: 14px; height: 2px; border-radius: 1px; }
  .legend-swatch-box { width: 10px; height: 10px; border-radius: 2px; opacity: 0.55; }

  svg.chart-svg { width: 100%; height: auto; display: block; overflow: visible; }
  .axis-label, .tick-label { fill: var(--text-muted); font-size: 11px; }
  .grid-line { stroke: var(--gridline); stroke-width: 1; }
  .baseline-axis { stroke: var(--baseline); stroke-width: 1; }
  .bar-value-label { fill: var(--text-secondary); font-size: 11px; text-anchor: middle; }

  .tooltip {
    position: fixed; pointer-events: none; background: var(--surface-1);
    border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
    font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); display: none; z-index: 50;
    max-width: 240px;
  }
  .tooltip .tt-title { font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
  .tooltip .tt-row { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); }
  .tooltip .tt-row .tt-value { color: var(--text-primary); font-weight: 600; margin-left: auto; padding-left: 10px; }
  .tooltip .tt-key { width: 10px; height: 2px; border-radius: 1px; flex: none; }

  .data-table { display: none; width: 100%; border-collapse: collapse; font-size: 12px; margin: 10px 0 14px; }
  .data-table.open { display: table; }
  .data-table-wrap { max-height: 260px; overflow: auto; border: 1px solid var(--border); border-radius: 8px; display: none; }
  .data-table-wrap.open { display: block; }
  .data-table th, .data-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--gridline); white-space: nowrap; }
  .data-table th { position: sticky; top: 0; background: var(--surface-1); color: var(--text-secondary); font-weight: 600; }
  .data-table td { color: var(--text-primary); font-variant-numeric: tabular-nums; }

  footer.dash-footer { color: var(--text-muted); font-size: 12px; margin-top: 8px; }

  @media (max-width: 760px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body class="viz-root" data-theme="light">
<div class="wrap">
  <header class="dash-header">
    <div>
      <h1>HVAC Fault Detection Dashboard</h1>
      <p>Simulated AHU sensor trends from __START_DATE__ to __END_DATE__ (__TOTAL_ROWS__ 5-minute
      readings), with rule-based fault detection results overlaid.</p>
    </div>
    <button id="theme-toggle" type="button">Dark mode</button>
  </header>

  <div class="kpi-row">
    <div class="kpi-tile">
      <div class="kpi-label">Sensor rows analyzed</div>
      <div class="kpi-value" id="kpi-rows">—</div>
    </div>
    <div class="kpi-tile">
      <div class="kpi-label">Flagged intervals</div>
      <div class="kpi-value" id="kpi-flagged">—</div>
    </div>
    <div class="kpi-tile">
      <div class="kpi-label">Avg. detection precision</div>
      <div class="kpi-value" id="kpi-precision">—</div>
    </div>
    <div class="kpi-tile">
      <div class="kpi-label">Avg. detection recall</div>
      <div class="kpi-value" id="kpi-recall">—</div>
    </div>
  </div>

  <div class="card">
    <div class="card-head">
      <h2>AHU temperature trends &amp; fault windows</h2>
      <button class="table-toggle" data-target="table-timeseries">View as table</button>
    </div>
    <p class="card-sub">Shaded regions mark ground-truth injected fault windows. Hover the chart for exact values.</p>
    <div class="legend-row" id="legend-timeseries"></div>
    <div id="chart-timeseries"></div>
    <div class="data-table-wrap" id="wrap-table-timeseries">
      <table class="data-table" id="table-timeseries">
        <thead><tr><th>Timestamp</th><th>Supply air temp (C)</th><th>Mixed air temp (C)</th><th>Fault label</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p class="card-sub">Table shows hourly samples for readability; full 5-minute resolution is in output/ahu_sensor_data.csv.</p>
  </div>

  <div class="card">
    <div class="card-head">
      <h2>Detected fault counts by type</h2>
      <button class="table-toggle" data-target="table-counts">View as table</button>
    </div>
    <p class="card-sub">Number of 5-minute intervals each rule flagged.</p>
    <div id="chart-counts"></div>
    <div class="data-table-wrap" id="wrap-table-counts">
      <table class="data-table" id="table-counts">
        <thead><tr><th>Fault type</th><th>Detected intervals</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="card-head">
      <h2>Detection precision &amp; recall by fault type</h2>
      <button class="table-toggle" data-target="table-pr">View as table</button>
    </div>
    <p class="card-sub">Scored against injected ground truth.</p>
    <div class="legend-row" id="legend-pr"></div>
    <div id="chart-pr"></div>
    <div class="data-table-wrap" id="wrap-table-pr">
      <table class="data-table" id="table-pr">
        <thead><tr><th>Fault type</th><th>Precision</th><th>Recall</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <footer class="dash-footer">Generated by dashboard.py from output/ahu_fault_detection_results.csv and output/fault_detection_summary.csv.</footer>
</div>
<div class="tooltip" id="tooltip"></div>
<script>
const DATA = __DATA_JSON__;

function theme() { return document.body.getAttribute('data-theme'); }
function seriesColor(key) { return DATA.colors.series[key][theme()]; }
function faultColor(key) { return DATA.colors.faults[key][theme()]; }

const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  return node;
}

function fmtDate(ms) {
  const d = new Date(ms);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
function fmtDateTime(ms) {
  const d = new Date(ms);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
function fmtPct(x) { return Math.round(x * 100) + '%'; }
function fmtNum(x) { return x.toLocaleString(); }

const tooltip = document.getElementById('tooltip');
function showTooltip(x, y, titleText, rows) {
  tooltip.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'tt-title';
  title.textContent = titleText;
  tooltip.appendChild(title);
  rows.forEach(r => {
    const row = document.createElement('div');
    row.className = 'tt-row';
    if (r.color) {
      const key = document.createElement('span');
      key.className = 'tt-key';
      key.style.background = r.color;
      row.appendChild(key);
    }
    const label = document.createElement('span');
    label.textContent = r.label;
    row.appendChild(label);
    const value = document.createElement('span');
    value.className = 'tt-value';
    value.textContent = r.value;
    row.appendChild(value);
    tooltip.appendChild(row);
  });
  tooltip.style.display = 'block';
  const pad = 14;
  let left = x + pad, top = y + pad;
  if (left + 240 > window.innerWidth) left = x - 240 - pad;
  if (top + 120 > window.innerHeight) top = y - 120 - pad;
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}
function hideTooltip() { tooltip.style.display = 'none'; }

function legendItem(container, colorBoxClass, color, label) {
  const item = document.createElement('div');
  item.className = 'legend-item';
  const swatch = document.createElement('span');
  swatch.className = colorBoxClass;
  swatch.style.background = color;
  item.appendChild(swatch);
  const text = document.createElement('span');
  text.textContent = label;
  item.appendChild(text);
  container.appendChild(item);
}

function niceTicks(min, max, count) {
  const range = max - min || 1;
  const step = range / count;
  const ticks = [];
  for (let i = 0; i <= count; i++) ticks.push(min + step * i);
  return ticks;
}

// ---------- Line chart (temperature trends + fault windows) ----------
function renderTimeseries() {
  const W = 1100, H = 340;
  const marginLeft = 44, marginRight = 16, marginTop = 16, marginBottom = 28;
  const plotW = W - marginLeft - marginRight, plotH = H - marginTop - marginBottom;

  const ts = DATA.timeseries.timestampsMs;
  const seriesList = DATA.timeseries.series;
  const minTs = ts[0], maxTs = ts[ts.length - 1];

  let minVal = Infinity, maxVal = -Infinity;
  seriesList.forEach(s => s.values.forEach(v => { if (v < minVal) minVal = v; if (v > maxVal) maxVal = v; }));
  const pad = (maxVal - minVal) * 0.08;
  minVal -= pad; maxVal += pad;

  const xScale = t => marginLeft + ((t - minTs) / (maxTs - minTs)) * plotW;
  const yScale = v => marginTop + plotH - ((v - minVal) / (maxVal - minVal)) * plotH;

  const svg = el('svg', { class: 'chart-svg', viewBox: `0 0 ${W} ${H}` });

  // Fault window shading (behind everything)
  DATA.timeseries.faultWindows.forEach(w => {
    const x0 = xScale(w.start), x1 = xScale(w.end);
    svg.appendChild(el('rect', {
      x: x0, y: marginTop, width: Math.max(x1 - x0, 1), height: plotH,
      fill: faultColor(w.type), opacity: 0.16,
    }));
  });

  // Y gridlines + tick labels
  const yTicks = niceTicks(minVal, maxVal, 4);
  yTicks.forEach(v => {
    const y = yScale(v);
    svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: y, y2: y, class: 'grid-line' }));
    const label = el('text', { x: marginLeft - 8, y: y + 4, class: 'tick-label', 'text-anchor': 'end' });
    label.textContent = Math.round(v) + '°C';
    svg.appendChild(label);
  });

  // X tick labels (weekly-ish)
  const xTickCount = 6;
  for (let i = 0; i <= xTickCount; i++) {
    const t = minTs + (i / xTickCount) * (maxTs - minTs);
    const x = xScale(t);
    const label = el('text', { x, y: H - 8, class: 'tick-label', 'text-anchor': 'middle' });
    label.textContent = fmtDate(t);
    svg.appendChild(label);
  }

  svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: marginTop + plotH, y2: marginTop + plotH, class: 'baseline-axis' }));

  // Series lines
  seriesList.forEach(s => {
    let d = '';
    ts.forEach((t, i) => {
      const x = xScale(t), y = yScale(s.values[i]);
      d += (i === 0 ? 'M' : 'L') + x.toFixed(2) + ',' + y.toFixed(2) + ' ';
    });
    svg.appendChild(el('path', { d, fill: 'none', stroke: seriesColor(s.key), 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  });

  // Crosshair + hit layer
  const crosshair = el('line', { x1: 0, x2: 0, y1: marginTop, y2: marginTop + plotH, stroke: 'var(--baseline)', 'stroke-width': 1, style: 'display:none' });
  svg.appendChild(crosshair);
  const hit = el('rect', { x: marginLeft, y: marginTop, width: plotW, height: plotH, fill: 'transparent' });
  svg.appendChild(hit);

  function nearestIndex(mx) {
    const t = minTs + ((mx - marginLeft) / plotW) * (maxTs - minTs);
    let lo = 0, hi = ts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (ts[mid] < t) lo = mid + 1; else hi = mid;
    }
    return Math.max(0, Math.min(ts.length - 1, lo));
  }

  hit.addEventListener('pointermove', ev => {
    const rect = svg.getBoundingClientRect();
    const mx = ((ev.clientX - rect.left) / rect.width) * W;
    const idx = nearestIndex(mx);
    const x = xScale(ts[idx]);
    crosshair.setAttribute('x1', x); crosshair.setAttribute('x2', x);
    crosshair.style.display = 'block';
    const rows = seriesList.map(s => ({ color: seriesColor(s.key), label: s.name, value: s.values[idx].toFixed(1) + '°C' }));
    const win = DATA.timeseries.faultWindows.find(w => ts[idx] >= w.start && ts[idx] <= w.end);
    if (win) rows.push({ color: faultColor(win.type), label: 'Fault', value: win.label });
    showTooltip(ev.clientX, ev.clientY, fmtDateTime(ts[idx]), rows);
  });
  hit.addEventListener('pointerleave', () => { crosshair.style.display = 'none'; hideTooltip(); });

  document.getElementById('chart-timeseries').innerHTML = '';
  document.getElementById('chart-timeseries').appendChild(svg);

  const legend = document.getElementById('legend-timeseries');
  legend.innerHTML = '';
  seriesList.forEach(s => legendItem(legend, 'legend-swatch-line', seriesColor(s.key), s.name));
  const faultTypesPresent = [...new Set(DATA.timeseries.faultWindows.map(w => w.type))];
  faultTypesPresent.forEach(t => legendItem(legend, 'legend-swatch-box', faultColor(t), DATA.colors.faults[t].label));
}

// ---------- Bar chart (fault counts) ----------
function renderFaultCounts() {
  const W = 1100, H = 260;
  const marginLeft = 44, marginRight = 16, marginTop = 24, marginBottom = 36;
  const plotW = W - marginLeft - marginRight, plotH = H - marginTop - marginBottom;
  const items = DATA.faultCounts;
  const maxCount = Math.max(...items.map(d => d.count), 1);

  const bandW = plotW / items.length;
  const barW = Math.min(24, bandW * 0.5);

  const svg = el('svg', { class: 'chart-svg', viewBox: `0 0 ${W} ${H}` });

  const yTicks = niceTicks(0, maxCount, 4);
  yTicks.forEach(v => {
    const y = marginTop + plotH - (v / maxCount) * plotH;
    svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: y, y2: y, class: 'grid-line' }));
    const label = el('text', { x: marginLeft - 8, y: y + 4, class: 'tick-label', 'text-anchor': 'end' });
    label.textContent = Math.round(v);
    svg.appendChild(label);
  });
  svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: marginTop + plotH, y2: marginTop + plotH, class: 'baseline-axis' }));

  items.forEach((d, i) => {
    const cx = marginLeft + bandW * (i + 0.5);
    const barH = (d.count / maxCount) * plotH;
    const y = marginTop + plotH - barH;
    const color = faultColor(d.type);

    const hitArea = el('rect', { x: cx - bandW / 2, y: marginTop, width: bandW, height: plotH, fill: 'transparent' });
    const bar = el('rect', { x: cx - barW / 2, y, width: barW, height: Math.max(barH, 1), rx: 4, ry: 4, fill: color });
    svg.appendChild(bar);
    svg.appendChild(hitArea);

    const valueLabel = el('text', { x: cx, y: y - 8, class: 'bar-value-label' });
    valueLabel.textContent = fmtNum(d.count);
    svg.appendChild(valueLabel);

    const catLabel = el('text', { x: cx, y: H - 12, class: 'tick-label', 'text-anchor': 'middle' });
    catLabel.textContent = d.label;
    svg.appendChild(catLabel);

    hitArea.addEventListener('pointermove', ev => {
      bar.setAttribute('opacity', 0.8);
      showTooltip(ev.clientX, ev.clientY, d.label, [{ color, label: 'Detected intervals', value: fmtNum(d.count) }]);
    });
    hitArea.addEventListener('pointerleave', () => { bar.setAttribute('opacity', 1); hideTooltip(); });
  });

  document.getElementById('chart-counts').innerHTML = '';
  document.getElementById('chart-counts').appendChild(svg);
}

// ---------- Grouped bar chart (precision & recall) ----------
function renderPrecisionRecall() {
  const W = 1100, H = 260;
  const marginLeft = 40, marginRight = 16, marginTop = 24, marginBottom = 36;
  const plotW = W - marginLeft - marginRight, plotH = H - marginTop - marginBottom;
  const items = DATA.precisionRecall;
  const bandW = plotW / items.length;
  const barW = Math.min(22, bandW * 0.28);
  const gap = 4;

  const svg = el('svg', { class: 'chart-svg', viewBox: `0 0 ${W} ${H}` });

  [0, 0.25, 0.5, 0.75, 1].forEach(v => {
    const y = marginTop + plotH - v * plotH;
    svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: y, y2: y, class: 'grid-line' }));
    const label = el('text', { x: marginLeft - 8, y: y + 4, class: 'tick-label', 'text-anchor': 'end' });
    label.textContent = fmtPct(v);
    svg.appendChild(label);
  });
  svg.appendChild(el('line', { x1: marginLeft, x2: W - marginRight, y1: marginTop + plotH, y2: marginTop + plotH, class: 'baseline-axis' }));

  items.forEach((d, i) => {
    const cx = marginLeft + bandW * (i + 0.5);
    [['precision', d.precision], ['recall', d.recall]].forEach(([key, val], j) => {
      const barH = val * plotH;
      const y = marginTop + plotH - barH;
      const x = cx - barW - gap / 2 + j * (barW + gap);
      const color = seriesColor(key);

      const hitArea = el('rect', { x: x - 3, y: marginTop, width: barW + 6, height: plotH, fill: 'transparent' });
      const bar = el('rect', { x, y, width: barW, height: Math.max(barH, 1), rx: 4, ry: 4, fill: color });
      svg.appendChild(bar);
      svg.appendChild(hitArea);

      const valueLabel = el('text', { x: x + barW / 2, y: y - 6, class: 'bar-value-label' });
      valueLabel.textContent = fmtPct(val);
      svg.appendChild(valueLabel);

      hitArea.addEventListener('pointermove', ev => {
        bar.setAttribute('opacity', 0.8);
        showTooltip(ev.clientX, ev.clientY, d.label, [{ color, label: key === 'precision' ? 'Precision' : 'Recall', value: fmtPct(val) }]);
      });
      hitArea.addEventListener('pointerleave', () => { bar.setAttribute('opacity', 1); hideTooltip(); });
    });

    const catLabel = el('text', { x: cx, y: H - 12, class: 'tick-label', 'text-anchor': 'middle' });
    catLabel.textContent = d.label;
    svg.appendChild(catLabel);
  });

  document.getElementById('chart-pr').innerHTML = '';
  document.getElementById('chart-pr').appendChild(svg);

  const legend = document.getElementById('legend-pr');
  legend.innerHTML = '';
  legendItem(legend, 'legend-swatch-line', seriesColor('precision'), 'Precision');
  legendItem(legend, 'legend-swatch-line', seriesColor('recall'), 'Recall');
}

// ---------- Tables (accessibility fallback) ----------
function fillTable(id, rows) {
  const tbody = document.querySelector('#' + id + ' tbody');
  tbody.innerHTML = '';
  rows.forEach(cells => {
    const tr = document.createElement('tr');
    cells.forEach(c => {
      const td = document.createElement('td');
      td.textContent = c;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}
function renderTables() {
  const t = DATA.table;
  fillTable('table-timeseries', t.timestamps.map((ts, i) => [ts, t.supplyAirTemp[i], t.mixedAirTemp[i], t.faultLabel[i]]));
  fillTable('table-counts', DATA.faultCounts.map(d => [d.label, fmtNum(d.count)]));
  fillTable('table-pr', DATA.precisionRecall.map(d => [d.label, fmtPct(d.precision), fmtPct(d.recall)]));
}

document.querySelectorAll('.table-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = btn.getAttribute('data-target');
    const wrap = document.getElementById('wrap-' + id);
    const isOpen = wrap.classList.toggle('open');
    document.getElementById(id).classList.toggle('open', isOpen);
    btn.textContent = isOpen ? 'Hide table' : 'View as table';
  });
});

function renderAll() {
  document.getElementById('kpi-rows').textContent = fmtNum(DATA.kpis.totalRows);
  document.getElementById('kpi-flagged').textContent = fmtNum(DATA.kpis.flaggedIntervals);
  document.getElementById('kpi-precision').textContent = fmtPct(DATA.kpis.avgPrecision);
  document.getElementById('kpi-recall').textContent = fmtPct(DATA.kpis.avgRecall);
  renderTimeseries();
  renderFaultCounts();
  renderPrecisionRecall();
}

const themeToggle = document.getElementById('theme-toggle');
function applyTheme(mode) {
  document.body.setAttribute('data-theme', mode);
  themeToggle.textContent = mode === 'dark' ? 'Light mode' : 'Dark mode';
  localStorage.setItem('hvac-dashboard-theme', mode);
  renderAll();
}
themeToggle.addEventListener('click', () => applyTheme(theme() === 'dark' ? 'light' : 'dark'));

renderTables();
applyTheme(localStorage.getItem('hvac-dashboard-theme') || 'light');
</script>
</body>
</html>
"""


def build(out_path="output/dashboard.html"):
    data = build_dashboard_data()
    html = (
        HTML_TEMPLATE.replace("__DATA_JSON__", json.dumps(data))
        .replace("__START_DATE__", data["generatedFrom"]["startDate"])
        .replace("__END_DATE__", data["generatedFrom"]["endDate"])
        .replace("__TOTAL_ROWS__", f"{data['generatedFrom']['rows']:,}")
    )
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")


if __name__ == "__main__":
    build()
