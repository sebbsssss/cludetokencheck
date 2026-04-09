"""
dashboard.py - Clude Token Check local web dashboard served on localhost:8080.

Tracks Claude Code usage and estimates savings from Clude's cognitive memory system.
"""

import json
import os
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".claude" / "usage.db"

# Clude efficiency factors (configurable via env vars)
CLUDE_MEMORY_RECALL_SAVINGS = float(os.environ.get("CLUDE_MEMORY_SAVINGS", "0.40"))
CLUDE_COMPACTION_SAVINGS = float(os.environ.get("CLUDE_COMPACTION_SAVINGS", "0.25"))
CLUDE_CACHE_EFFICIENCY = float(os.environ.get("CLUDE_CACHE_EFFICIENCY", "0.15"))


def get_dashboard_data(db_path=DB_PATH):
    if not db_path.exists():
        return {"error": "Database not found. Run: python cli.py scan"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    model_rows = conn.execute("""
        SELECT COALESCE(model, 'unknown') as model
        FROM turns
        GROUP BY model
        ORDER BY SUM(input_tokens + output_tokens) DESC
    """).fetchall()
    all_models = [r["model"] for r in model_rows]

    daily_rows = conn.execute("""
        SELECT
            substr(timestamp, 1, 10)   as day,
            COALESCE(model, 'unknown') as model,
            SUM(input_tokens)          as input,
            SUM(output_tokens)         as output,
            SUM(cache_read_tokens)     as cache_read,
            SUM(cache_creation_tokens) as cache_creation,
            COUNT(*)                   as turns
        FROM turns
        GROUP BY day, model
        ORDER BY day, model
    """).fetchall()

    daily_by_model = [{
        "day":            r["day"],
        "model":          r["model"],
        "input":          r["input"] or 0,
        "output":         r["output"] or 0,
        "cache_read":     r["cache_read"] or 0,
        "cache_creation": r["cache_creation"] or 0,
        "turns":          r["turns"] or 0,
    } for r in daily_rows]

    session_rows = conn.execute("""
        SELECT
            session_id, project_name, first_timestamp, last_timestamp,
            total_input_tokens, total_output_tokens,
            total_cache_read, total_cache_creation, model, turn_count
        FROM sessions
        ORDER BY last_timestamp DESC
    """).fetchall()

    sessions_all = []
    for r in session_rows:
        try:
            t1 = datetime.fromisoformat(r["first_timestamp"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(r["last_timestamp"].replace("Z", "+00:00"))
            duration_min = round((t2 - t1).total_seconds() / 60, 1)
        except Exception:
            duration_min = 0
        sessions_all.append({
            "session_id":    r["session_id"][:8],
            "project":       r["project_name"] or "unknown",
            "last":          (r["last_timestamp"] or "")[:16].replace("T", " "),
            "last_date":     (r["last_timestamp"] or "")[:10],
            "duration_min":  duration_min,
            "model":         r["model"] or "unknown",
            "turns":         r["turn_count"] or 0,
            "input":         r["total_input_tokens"] or 0,
            "output":        r["total_output_tokens"] or 0,
            "cache_read":    r["total_cache_read"] or 0,
            "cache_creation": r["total_cache_creation"] or 0,
        })

    conn.close()

    return {
        "all_models":     all_models,
        "daily_by_model": daily_by_model,
        "sessions_all":   sessions_all,
        "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "clude_factors": {
            "memory_recall": CLUDE_MEMORY_RECALL_SAVINGS,
            "compaction":    CLUDE_COMPACTION_SAVINGS,
            "cache":         CLUDE_CACHE_EFFICIENCY,
        },
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clude Token Check</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Funnel+Sans:wght@400;600;700&family=Inconsolata:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0a0a0a;
    --card: #111116;
    --border: #1e1e2a;
    --text: #F5F5F0;
    --muted: #8892a4;
    --accent: #2244FF;
    --accent-glow: rgba(34, 68, 255, 0.15);
    --blue: #4f8ef7;
    --green: #4ade80;
    --savings: #2244FF;
    --savings-bg: rgba(34, 68, 255, 0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Funnel Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }

  header { background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .header-logo { width: 32px; height: 32px; }
  header h1 { font-size: 18px; font-weight: 700; color: var(--text); letter-spacing: -0.3px; }
  header h1 span { color: var(--accent); }
  header .meta { color: var(--muted); font-size: 12px; font-family: 'Inconsolata', monospace; }

  #filter-bar { background: var(--card); border-bottom: 1px solid var(--border); padding: 10px 24px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .filter-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); white-space: nowrap; font-family: 'Inconsolata', monospace; }
  .filter-sep { width: 1px; height: 22px; background: var(--border); flex-shrink: 0; }
  #model-checkboxes { display: flex; flex-wrap: wrap; gap: 6px; }
  .model-cb-label { display: flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 20px; border: 1px solid var(--border); cursor: pointer; font-size: 12px; color: var(--muted); transition: border-color 0.15s, color 0.15s, background 0.15s; user-select: none; }
  .model-cb-label:hover { border-color: var(--accent); color: var(--text); }
  .model-cb-label.checked { background: var(--accent-glow); border-color: var(--accent); color: var(--text); }
  .model-cb-label input { display: none; }
  .filter-btn { padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 11px; cursor: pointer; white-space: nowrap; font-family: 'Inconsolata', monospace; }
  .filter-btn:hover { border-color: var(--accent); color: var(--text); }
  .range-group { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
  .range-btn { padding: 4px 13px; background: transparent; border: none; border-right: 1px solid var(--border); color: var(--muted); font-size: 12px; cursor: pointer; transition: background 0.15s, color 0.15s; font-family: 'Inconsolata', monospace; }
  .range-btn:last-child { border-right: none; }
  .range-btn:hover { background: rgba(255,255,255,0.04); color: var(--text); }
  .range-btn.active { background: var(--accent-glow); color: var(--accent); font-weight: 600; }

  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

  /* Savings banner */
  .savings-banner { background: var(--savings-bg); border: 1px solid rgba(34, 68, 255, 0.2); border-radius: 10px; padding: 18px 24px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
  .savings-banner .savings-icon { width: 36px; height: 36px; background: var(--accent); border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .savings-banner .savings-icon svg { width: 20px; height: 20px; }
  .savings-left { display: flex; align-items: center; gap: 14px; }
  .savings-title { font-size: 14px; font-weight: 700; color: var(--accent); }
  .savings-subtitle { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .savings-stats { display: flex; gap: 28px; }
  .savings-stat { text-align: center; }
  .savings-stat .sv { font-size: 22px; font-weight: 700; color: var(--accent); font-family: 'Inconsolata', monospace; }
  .savings-stat .sl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }

  .stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .stat-card .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; font-family: 'Inconsolata', monospace; }
  .stat-card .value { font-size: 22px; font-weight: 700; font-family: 'Inconsolata', monospace; }
  .stat-card .sub { color: var(--muted); font-size: 11px; margin-top: 4px; }

  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
  .chart-card.wide { grid-column: 1 / -1; }
  .chart-card h2 { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; font-family: 'Inconsolata', monospace; }
  .chart-wrap { position: relative; height: 240px; }
  .chart-wrap.tall { height: 300px; }

  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--border); font-family: 'Inconsolata', monospace; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .model-tag { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; background: var(--accent-glow); color: var(--accent); font-family: 'Inconsolata', monospace; }
  .cost { color: var(--green); font-family: 'Inconsolata', monospace; }
  .cost-na { color: var(--muted); font-family: 'Inconsolata', monospace; font-size: 11px; }
  .num { font-family: 'Inconsolata', monospace; }
  .muted { color: var(--muted); }
  .section-title { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; font-family: 'Inconsolata', monospace; }
  .table-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; overflow-x: auto; }

  /* Settings panel */
  .settings-toggle { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; font-family: 'Inconsolata', monospace; transition: all 0.15s; }
  .settings-toggle:hover { border-color: var(--accent); color: var(--text); }
  .settings-panel { display: none; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; }
  .settings-panel.open { display: block; }
  .settings-panel h3 { font-size: 14px; font-weight: 600; color: var(--accent); margin-bottom: 14px; }
  .setting-row { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
  .setting-row label { font-size: 13px; color: var(--muted); min-width: 180px; }
  .setting-row input[type="range"] { flex: 1; max-width: 200px; accent-color: var(--accent); }
  .setting-row .setting-val { font-family: 'Inconsolata', monospace; font-size: 13px; color: var(--accent); min-width: 40px; }

  footer { border-top: 1px solid var(--border); padding: 20px 24px; margin-top: 8px; }
  .footer-content { max-width: 1400px; margin: 0 auto; }
  .footer-content p { color: var(--muted); font-size: 12px; line-height: 1.7; margin-bottom: 4px; }
  .footer-content p:last-child { margin-bottom: 0; }
  .footer-content a { color: var(--accent); text-decoration: none; }
  .footer-content a:hover { text-decoration: underline; }

  @media (max-width: 768px) {
    .charts-grid { grid-template-columns: 1fr; }
    .chart-card.wide { grid-column: 1; }
    .savings-banner { flex-direction: column; align-items: flex-start; }
    .savings-stats { flex-wrap: wrap; }
  }
</style>
</head>
<body>
<header>
  <div class="header-left">
    <svg class="header-logo" viewBox="0 0 1080 1080" xmlns="http://www.w3.org/2000/svg">
      <path fill="#2244FF" d="M877.5,295.97V109.03c0-10.51-8.52-19.03-19.03-19.03h-430.97c-10.51,0-19.03,8.52-19.03,19.03v147.53c0,25.23-10.02,49.44-27.87,67.28l-155.81,155.81c-14.28,14.27-22.29,33.64-22.29,53.82v437.5c0,10.51,8.52,19.03,19.03,19.03h636.94c10.51,0,19.03-8.52,19.03-19.03v-186.94c0-10.51-8.52-19.03-19.03-19.03h-421.46c-5.25,0-9.51-4.26-9.51-9.51v-402.43c0-21.02,17.04-38.06,38.06-38.06h392.91c10.51,0,19.03-8.52,19.03-19.03Z"/>
    </svg>
    <h1><span>Clude</span> Token Check</h1>
  </div>
  <div class="meta" id="meta">Loading...</div>
</header>

<div id="filter-bar">
  <div class="filter-label">Models</div>
  <div id="model-checkboxes"></div>
  <button class="filter-btn" onclick="selectAllModels()">All</button>
  <button class="filter-btn" onclick="clearAllModels()">None</button>
  <div class="filter-sep"></div>
  <div class="filter-label">Range</div>
  <div class="range-group">
    <button class="range-btn" data-range="7d"  onclick="setRange('7d')">7d</button>
    <button class="range-btn" data-range="30d" onclick="setRange('30d')">30d</button>
    <button class="range-btn" data-range="90d" onclick="setRange('90d')">90d</button>
    <button class="range-btn" data-range="all" onclick="setRange('all')">All</button>
  </div>
  <div class="filter-sep"></div>
  <button class="settings-toggle" onclick="toggleSettings()">Settings</button>
</div>

<div class="container">
  <!-- Clude Savings Banner -->
  <div class="savings-banner" id="savings-banner">
    <div class="savings-left">
      <div class="savings-icon">
        <svg viewBox="0 0 20 20" fill="white" xmlns="http://www.w3.org/2000/svg">
          <path d="M10 2L3 7v6l7 5 7-5V7l-7-5zm0 2.18L14.5 7.5 10 10.82 5.5 7.5 10 4.18zM5 8.82l4 2.86v4.5L5 13.32v-4.5zm6 7.36v-4.5l4-2.86v4.5l-4 2.86z"/>
        </svg>
      </div>
      <div>
        <div class="savings-title">Clude Memory Savings</div>
        <div class="savings-subtitle">Estimated savings from Clude's cognitive memory system</div>
      </div>
    </div>
    <div class="savings-stats">
      <div class="savings-stat">
        <div class="sv" id="sv-tokens">--</div>
        <div class="sl">Tokens Saved</div>
      </div>
      <div class="savings-stat">
        <div class="sv" id="sv-cost">--</div>
        <div class="sl">Cost Saved</div>
      </div>
      <div class="savings-stat">
        <div class="sv" id="sv-pct">--</div>
        <div class="sl">Efficiency</div>
      </div>
    </div>
  </div>

  <!-- Settings Panel -->
  <div class="settings-panel" id="settings-panel">
    <h3>Clude Efficiency Factors</h3>
    <div class="setting-row">
      <label>Memory Recall Savings</label>
      <input type="range" id="slider-memory" min="0" max="80" value="40" oninput="updateFactor('memory', this.value)">
      <span class="setting-val" id="val-memory">40%</span>
    </div>
    <div class="setting-row">
      <label>Compaction Savings</label>
      <input type="range" id="slider-compaction" min="0" max="60" value="25" oninput="updateFactor('compaction', this.value)">
      <span class="setting-val" id="val-compaction">25%</span>
    </div>
    <div class="setting-row">
      <label>Cache Efficiency Boost</label>
      <input type="range" id="slider-cache" min="0" max="50" value="15" oninput="updateFactor('cache', this.value)">
      <span class="setting-val" id="val-cache">15%</span>
    </div>
    <p style="color:var(--muted);font-size:12px;margin-top:10px">Adjust these based on your observed Clude savings. Defaults reflect typical efficiency gains from progressive disclosure, memory compaction, and hybrid scoring.</p>
  </div>

  <div class="stats-row" id="stats-row"></div>
  <div class="charts-grid">
    <div class="chart-card wide">
      <h2 id="daily-chart-title">Daily Token Usage</h2>
      <div class="chart-wrap tall"><canvas id="chart-daily"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>By Model</h2>
      <div class="chart-wrap"><canvas id="chart-model"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Clude Impact</h2>
      <div class="chart-wrap"><canvas id="chart-savings"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Top Projects by Tokens</h2>
      <div class="chart-wrap"><canvas id="chart-project"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Savings Breakdown</h2>
      <div class="chart-wrap"><canvas id="chart-savings-breakdown"></canvas></div>
    </div>
  </div>
  <div class="table-card">
    <div class="section-title">Recent Sessions</div>
    <table>
      <thead><tr>
        <th>Session</th><th>Project</th><th>Last Active</th><th>Duration</th>
        <th>Model</th><th>Turns</th><th>Input</th><th>Output</th><th>Est. Cost</th><th style="color:var(--accent)">Clude Saved</th>
      </tr></thead>
      <tbody id="sessions-body"></tbody>
    </table>
  </div>
  <div class="table-card">
    <div class="section-title">Cost by Model</div>
    <table>
      <thead><tr>
        <th>Model</th><th>Turns</th><th>Input</th><th>Output</th>
        <th>Cache Read</th><th>Cache Creation</th><th>Est. Cost</th><th style="color:var(--accent)">With Clude</th>
      </tr></thead>
      <tbody id="model-cost-body"></tbody>
    </table>
  </div>
</div>

<footer>
  <div class="footer-content">
    <p>Cost estimates based on Anthropic API pricing (<a href="https://claude.com/pricing#api" target="_blank">claude.com/pricing#api</a>) as of April 2026. Clude savings are estimated based on configurable efficiency factors. Actual savings depend on your usage patterns.</p>
    <p>
      Built by <strong>Seb</strong>
      &nbsp;&middot;&nbsp;
      Powered by <a href="https://github.com/sebbsssss/cludebot" target="_blank">Clude</a>
      &nbsp;&middot;&nbsp;
      License: MIT
    </p>
  </div>
</footer>

<script>
// -- Helpers ------------------------------------------------------------------
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// -- State --------------------------------------------------------------------
let rawData = null;
let selectedModels = new Set();
let selectedRange = '30d';
let charts = {};
let cludeFactors = { memory: 0.40, compaction: 0.25, cache: 0.15 };

// -- Settings -----------------------------------------------------------------
function toggleSettings() {
  document.getElementById('settings-panel').classList.toggle('open');
}

function updateFactor(type, value) {
  cludeFactors[type] = parseInt(value) / 100;
  document.getElementById('val-' + type).textContent = value + '%';
  applyFilter();
}

// -- Clude Savings Calculation ------------------------------------------------
function calcCludeSavings(inp, out, cacheRead) {
  const inputSaved = inp * cludeFactors.memory;
  const outputSaved = out * cludeFactors.compaction;
  const cacheSaved = cacheRead * cludeFactors.cache;
  return { inputSaved, outputSaved, cacheSaved, total: inputSaved + outputSaved + cacheSaved };
}

// -- Pricing (Anthropic API, April 2026) --------------------------------------
const PRICING = {
  'claude-opus-4-6':   { input:  5.00, output: 25.00, cache_write:  6.25, cache_read: 0.50 },
  'claude-opus-4-5':   { input:  5.00, output: 25.00, cache_write:  6.25, cache_read: 0.50 },
  'claude-sonnet-4-6': { input:  3.00, output: 15.00, cache_write:  3.75, cache_read: 0.30 },
  'claude-sonnet-4-5': { input:  3.00, output: 15.00, cache_write:  3.75, cache_read: 0.30 },
  'claude-haiku-4-5':  { input:  1.00, output:  5.00, cache_write:  1.25, cache_read: 0.10 },
  'claude-haiku-4-6':  { input:  1.00, output:  5.00, cache_write:  1.25, cache_read: 0.10 },
};

function isBillable(model) {
  if (!model) return false;
  const m = model.toLowerCase();
  return m.includes('opus') || m.includes('sonnet') || m.includes('haiku');
}

function getPricing(model) {
  if (!model) return null;
  if (PRICING[model]) return PRICING[model];
  for (const key of Object.keys(PRICING)) {
    if (model.startsWith(key)) return PRICING[key];
  }
  const m = model.toLowerCase();
  if (m.includes('opus'))   return PRICING['claude-opus-4-6'];
  if (m.includes('sonnet')) return PRICING['claude-sonnet-4-6'];
  if (m.includes('haiku'))  return PRICING['claude-haiku-4-5'];
  return null;
}

function calcCost(model, inp, out, cacheRead, cacheCreation) {
  if (!isBillable(model)) return 0;
  const p = getPricing(model);
  if (!p) return 0;
  return (
    inp           * p.input       / 1e6 +
    out           * p.output      / 1e6 +
    cacheRead     * p.cache_read  / 1e6 +
    cacheCreation * p.cache_write / 1e6
  );
}

function calcCostFromTokens(inp, out, cacheRead, cacheCreation, model) {
  const p = getPricing(model);
  if (!p) return 0;
  return (
    inp           * p.input       / 1e6 +
    out           * p.output      / 1e6 +
    cacheRead     * p.cache_read  / 1e6 +
    cacheCreation * p.cache_write / 1e6
  );
}

// -- Formatting ---------------------------------------------------------------
function fmt(n) {
  if (n >= 1e9) return (n/1e9).toFixed(2)+'B';
  if (n >= 1e6) return (n/1e6).toFixed(2)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return n.toLocaleString();
}
function fmtCost(c)    { return '$' + c.toFixed(4); }
function fmtCostBig(c) { return '$' + c.toFixed(2); }

// -- Chart colors -------------------------------------------------------------
const TOKEN_COLORS = {
  input:          'rgba(34, 68, 255, 0.8)',
  output:         'rgba(167, 139, 250, 0.8)',
  cache_read:     'rgba(74, 222, 128, 0.6)',
  cache_creation: 'rgba(251, 191, 36, 0.6)',
};
const SAVINGS_GHOST = 'rgba(34, 68, 255, 0.2)';
const MODEL_COLORS = ['#2244FF','#4f8ef7','#4ade80','#a78bfa','#fbbf24','#f472b6','#34d399','#60a5fa'];

// -- Time range ---------------------------------------------------------------
const RANGE_LABELS = { '7d': 'Last 7 Days', '30d': 'Last 30 Days', '90d': 'Last 90 Days', 'all': 'All Time' };
const RANGE_TICKS  = { '7d': 7, '30d': 15, '90d': 13, 'all': 12 };

function getRangeCutoff(range) {
  if (range === 'all') return null;
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function readURLRange() {
  const p = new URLSearchParams(window.location.search).get('range');
  return ['7d', '30d', '90d', 'all'].includes(p) ? p : '30d';
}

function setRange(range) {
  selectedRange = range;
  document.querySelectorAll('.range-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.range === range)
  );
  updateURL();
  applyFilter();
}

// -- Model filter -------------------------------------------------------------
function modelPriority(m) {
  const ml = m.toLowerCase();
  if (ml.includes('opus'))   return 0;
  if (ml.includes('sonnet')) return 1;
  if (ml.includes('haiku'))  return 2;
  return 3;
}

function readURLModels(allModels) {
  const param = new URLSearchParams(window.location.search).get('models');
  if (!param) return new Set(allModels.filter(m => isBillable(m)));
  const fromURL = new Set(param.split(',').map(s => s.trim()).filter(Boolean));
  return new Set(allModels.filter(m => fromURL.has(m)));
}

function isDefaultModelSelection(allModels) {
  const billable = allModels.filter(m => isBillable(m));
  if (selectedModels.size !== billable.length) return false;
  return billable.every(m => selectedModels.has(m));
}

function buildFilterUI(allModels) {
  const sorted = [...allModels].sort((a, b) => {
    const pa = modelPriority(a), pb = modelPriority(b);
    return pa !== pb ? pa - pb : a.localeCompare(b);
  });
  selectedModels = readURLModels(allModels);
  const container = document.getElementById('model-checkboxes');
  container.innerHTML = sorted.map(m => {
    const checked = selectedModels.has(m);
    return `<label class="model-cb-label ${checked ? 'checked' : ''}" data-model="${esc(m)}">
      <input type="checkbox" value="${esc(m)}" ${checked ? 'checked' : ''} onchange="onModelToggle(this)">
      ${esc(m)}
    </label>`;
  }).join('');
}

function onModelToggle(cb) {
  const label = cb.closest('label');
  if (cb.checked) { selectedModels.add(cb.value);    label.classList.add('checked'); }
  else            { selectedModels.delete(cb.value); label.classList.remove('checked'); }
  updateURL();
  applyFilter();
}

function selectAllModels() {
  document.querySelectorAll('#model-checkboxes input').forEach(cb => {
    cb.checked = true; selectedModels.add(cb.value); cb.closest('label').classList.add('checked');
  });
  updateURL(); applyFilter();
}

function clearAllModels() {
  document.querySelectorAll('#model-checkboxes input').forEach(cb => {
    cb.checked = false; selectedModels.delete(cb.value); cb.closest('label').classList.remove('checked');
  });
  updateURL(); applyFilter();
}

// -- URL persistence ----------------------------------------------------------
function updateURL() {
  const allModels = Array.from(document.querySelectorAll('#model-checkboxes input')).map(cb => cb.value);
  const params = new URLSearchParams();
  if (selectedRange !== '30d') params.set('range', selectedRange);
  if (!isDefaultModelSelection(allModels)) params.set('models', Array.from(selectedModels).join(','));
  const search = params.toString() ? '?' + params.toString() : '';
  history.replaceState(null, '', window.location.pathname + search);
}

// -- Aggregation & filtering --------------------------------------------------
function applyFilter() {
  if (!rawData) return;

  const cutoff = getRangeCutoff(selectedRange);

  const filteredDaily = rawData.daily_by_model.filter(r =>
    selectedModels.has(r.model) && (!cutoff || r.day >= cutoff)
  );

  const dailyMap = {};
  for (const r of filteredDaily) {
    if (!dailyMap[r.day]) dailyMap[r.day] = { day: r.day, input: 0, output: 0, cache_read: 0, cache_creation: 0 };
    const d = dailyMap[r.day];
    d.input          += r.input;
    d.output         += r.output;
    d.cache_read     += r.cache_read;
    d.cache_creation += r.cache_creation;
  }
  const daily = Object.values(dailyMap).sort((a, b) => a.day.localeCompare(b.day));

  const modelMap = {};
  for (const r of filteredDaily) {
    if (!modelMap[r.model]) modelMap[r.model] = { model: r.model, input: 0, output: 0, cache_read: 0, cache_creation: 0, turns: 0, sessions: 0 };
    const m = modelMap[r.model];
    m.input          += r.input;
    m.output         += r.output;
    m.cache_read     += r.cache_read;
    m.cache_creation += r.cache_creation;
    m.turns          += r.turns;
  }

  const filteredSessions = rawData.sessions_all.filter(s =>
    selectedModels.has(s.model) && (!cutoff || s.last_date >= cutoff)
  );

  for (const s of filteredSessions) {
    if (modelMap[s.model]) modelMap[s.model].sessions++;
  }

  const byModel = Object.values(modelMap).sort((a, b) => (b.input + b.output) - (a.input + a.output));

  const projMap = {};
  for (const s of filteredSessions) {
    if (!projMap[s.project]) projMap[s.project] = { project: s.project, input: 0, output: 0, turns: 0 };
    projMap[s.project].input  += s.input;
    projMap[s.project].output += s.output;
    projMap[s.project].turns  += s.turns;
  }
  const byProject = Object.values(projMap).sort((a, b) => (b.input + b.output) - (a.input + a.output));

  const totals = {
    sessions:       filteredSessions.length,
    turns:          byModel.reduce((s, m) => s + m.turns, 0),
    input:          byModel.reduce((s, m) => s + m.input, 0),
    output:         byModel.reduce((s, m) => s + m.output, 0),
    cache_read:     byModel.reduce((s, m) => s + m.cache_read, 0),
    cache_creation: byModel.reduce((s, m) => s + m.cache_creation, 0),
    cost:           byModel.reduce((s, m) => s + calcCost(m.model, m.input, m.output, m.cache_read, m.cache_creation), 0),
  };

  // Calculate Clude savings
  const savings = calcCludeSavings(totals.input, totals.output, totals.cache_read);
  const costSaved = totals.cost > 0 ? totals.cost * (savings.total / Math.max(totals.input + totals.output + totals.cache_read, 1)) : 0;
  const efficiencyPct = totals.input + totals.output + totals.cache_read > 0
    ? (savings.total / (totals.input + totals.output + totals.cache_read) * 100)
    : 0;

  // Update savings banner
  document.getElementById('sv-tokens').textContent = '~' + fmt(Math.round(savings.total));
  document.getElementById('sv-cost').textContent = '~' + fmtCostBig(costSaved);
  document.getElementById('sv-pct').textContent = '~' + efficiencyPct.toFixed(1) + '%';

  document.getElementById('daily-chart-title').textContent = 'Daily Token Usage \u2014 ' + RANGE_LABELS[selectedRange];

  renderStats(totals);
  renderDailyChart(daily);
  renderModelChart(byModel);
  renderProjectChart(byProject);
  renderSavingsChart(totals, savings);
  renderSavingsBreakdown(savings);
  renderSessionsTable(filteredSessions.slice(0, 20));
  renderModelCostTable(byModel);
}

// -- Renderers ----------------------------------------------------------------
function renderStats(t) {
  const rangeLabel = RANGE_LABELS[selectedRange].toLowerCase();
  const stats = [
    { label: 'Sessions',       value: t.sessions.toLocaleString(), sub: rangeLabel },
    { label: 'Turns',          value: fmt(t.turns),                sub: rangeLabel },
    { label: 'Input Tokens',   value: fmt(t.input),                sub: rangeLabel },
    { label: 'Output Tokens',  value: fmt(t.output),               sub: rangeLabel },
    { label: 'Cache Read',     value: fmt(t.cache_read),           sub: 'from prompt cache' },
    { label: 'Cache Creation', value: fmt(t.cache_creation),       sub: 'writes to prompt cache' },
    { label: 'Est. Cost',      value: fmtCostBig(t.cost),          sub: 'API pricing, Apr 2026', color: '#4ade80' },
  ];
  document.getElementById('stats-row').innerHTML = stats.map(s => `
    <div class="stat-card">
      <div class="label">${s.label}</div>
      <div class="value" style="${s.color ? 'color:' + s.color : ''}">${esc(s.value)}</div>
      ${s.sub ? `<div class="sub">${esc(s.sub)}</div>` : ''}
    </div>
  `).join('');
}

function renderDailyChart(daily) {
  const ctx = document.getElementById('chart-daily').getContext('2d');
  if (charts.daily) charts.daily.destroy();

  // Calculate savings ghost data
  const savingsData = daily.map(d => {
    const sv = calcCludeSavings(d.input, d.output, d.cache_read);
    return sv.total;
  });

  charts.daily = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: daily.map(d => d.day),
      datasets: [
        { label: 'Input',          data: daily.map(d => d.input),          backgroundColor: TOKEN_COLORS.input,          stack: 'tokens' },
        { label: 'Output',         data: daily.map(d => d.output),         backgroundColor: TOKEN_COLORS.output,         stack: 'tokens' },
        { label: 'Cache Read',     data: daily.map(d => d.cache_read),     backgroundColor: TOKEN_COLORS.cache_read,     stack: 'tokens' },
        { label: 'Cache Creation', data: daily.map(d => d.cache_creation), backgroundColor: TOKEN_COLORS.cache_creation, stack: 'tokens' },
        { label: 'Clude Savings',  data: savingsData,                      backgroundColor: SAVINGS_GHOST,               stack: 'savings', borderColor: 'rgba(34, 68, 255, 0.5)', borderWidth: 1, borderDash: [4, 2] },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892a4', boxWidth: 12, font: { family: "'Inconsolata', monospace" } } } },
      scales: {
        x: { ticks: { color: '#8892a4', maxTicksLimit: RANGE_TICKS[selectedRange], font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
        y: { ticks: { color: '#8892a4', callback: v => fmt(v), font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
      }
    }
  });
}

function renderModelChart(byModel) {
  const ctx = document.getElementById('chart-model').getContext('2d');
  if (charts.model) charts.model.destroy();
  if (!byModel.length) { charts.model = null; return; }
  charts.model = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: byModel.map(m => m.model),
      datasets: [{ data: byModel.map(m => m.input + m.output), backgroundColor: MODEL_COLORS, borderWidth: 2, borderColor: '#111116' }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8892a4', boxWidth: 12, font: { size: 11, family: "'Inconsolata', monospace" } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${fmt(ctx.raw)} tokens` } }
      }
    }
  });
}

function renderSavingsChart(totals, savings) {
  const ctx = document.getElementById('chart-savings').getContext('2d');
  if (charts.savings) charts.savings.destroy();

  const actualTokens = totals.input + totals.output + totals.cache_read;
  const withClude = Math.max(actualTokens - savings.total, 0);

  charts.savings = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['With Clude', 'Tokens Saved'],
      datasets: [{
        data: [withClude, savings.total],
        backgroundColor: ['rgba(34, 68, 255, 0.6)', 'rgba(74, 222, 128, 0.6)'],
        borderWidth: 2,
        borderColor: '#111116'
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8892a4', boxWidth: 12, font: { size: 11, family: "'Inconsolata', monospace" } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${fmt(Math.round(ctx.raw))} tokens` } }
      }
    }
  });
}

function renderSavingsBreakdown(savings) {
  const ctx = document.getElementById('chart-savings-breakdown').getContext('2d');
  if (charts.savingsBreakdown) charts.savingsBreakdown.destroy();

  charts.savingsBreakdown = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Memory Recall', 'Compaction', 'Cache Efficiency'],
      datasets: [{
        label: 'Tokens Saved',
        data: [Math.round(savings.inputSaved), Math.round(savings.outputSaved), Math.round(savings.cacheSaved)],
        backgroundColor: ['rgba(34, 68, 255, 0.7)', 'rgba(167, 139, 250, 0.7)', 'rgba(74, 222, 128, 0.7)'],
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8892a4', callback: v => fmt(v), font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
        y: { ticks: { color: '#8892a4', font: { size: 11, family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
      }
    }
  });
}

function renderProjectChart(byProject) {
  const top = byProject.slice(0, 10);
  const ctx = document.getElementById('chart-project').getContext('2d');
  if (charts.project) charts.project.destroy();
  if (!top.length) { charts.project = null; return; }
  charts.project = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(p => p.project.length > 22 ? '\u2026' + p.project.slice(-20) : p.project),
      datasets: [
        { label: 'Input',  data: top.map(p => p.input),  backgroundColor: TOKEN_COLORS.input },
        { label: 'Output', data: top.map(p => p.output), backgroundColor: TOKEN_COLORS.output },
      ]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892a4', boxWidth: 12, font: { family: "'Inconsolata', monospace" } } } },
      scales: {
        x: { ticks: { color: '#8892a4', callback: v => fmt(v), font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
        y: { ticks: { color: '#8892a4', font: { size: 11, family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
      }
    }
  });
}

function renderSessionsTable(sessions) {
  document.getElementById('sessions-body').innerHTML = sessions.map(s => {
    const cost = calcCost(s.model, s.input, s.output, s.cache_read, s.cache_creation);
    const sv = calcCludeSavings(s.input, s.output, s.cache_read);
    const costCell = isBillable(s.model)
      ? `<td class="cost">${fmtCost(cost)}</td>`
      : `<td class="cost-na">n/a</td>`;
    const savedTokens = Math.round(sv.total);
    return `<tr>
      <td class="muted" style="font-family:'Inconsolata',monospace">${esc(s.session_id)}&hellip;</td>
      <td>${esc(s.project)}</td>
      <td class="muted">${esc(s.last)}</td>
      <td class="muted">${esc(s.duration_min)}m</td>
      <td><span class="model-tag">${esc(s.model)}</span></td>
      <td class="num">${s.turns}</td>
      <td class="num">${fmt(s.input)}</td>
      <td class="num">${fmt(s.output)}</td>
      ${costCell}
      <td class="num" style="color:var(--accent)">${savedTokens > 0 ? '~' + fmt(savedTokens) : '-'}</td>
    </tr>`;
  }).join('');
}

function renderModelCostTable(byModel) {
  document.getElementById('model-cost-body').innerHTML = byModel.map(m => {
    const cost = calcCost(m.model, m.input, m.output, m.cache_read, m.cache_creation);
    const sv = calcCludeSavings(m.input, m.output, m.cache_read);
    const reducedCost = cost > 0 ? cost * (1 - sv.total / Math.max(m.input + m.output + m.cache_read, 1)) : 0;
    const costCell = isBillable(m.model)
      ? `<td class="cost">${fmtCost(cost)}</td>`
      : `<td class="cost-na">n/a</td>`;
    const cludeCell = isBillable(m.model)
      ? `<td style="color:var(--accent);font-family:'Inconsolata',monospace">~${fmtCost(Math.max(reducedCost, 0))}</td>`
      : `<td class="cost-na">n/a</td>`;
    return `<tr>
      <td><span class="model-tag">${esc(m.model)}</span></td>
      <td class="num">${fmt(m.turns)}</td>
      <td class="num">${fmt(m.input)}</td>
      <td class="num">${fmt(m.output)}</td>
      <td class="num">${fmt(m.cache_read)}</td>
      <td class="num">${fmt(m.cache_creation)}</td>
      ${costCell}
      ${cludeCell}
    </tr>`;
  }).join('');
}

// -- Data loading -------------------------------------------------------------
async function loadData() {
  try {
    const resp = await fetch('/api/data');
    const d = await resp.json();
    if (d.error) {
      document.body.innerHTML = '<div style="padding:40px;color:#f87171;font-family:Inconsolata,monospace">' + esc(d.error) + '</div>';
      return;
    }
    document.getElementById('meta').textContent = 'Updated: ' + d.generated_at + ' \u00b7 Auto-refresh 30s';

    // Load server-side factors on first load
    if (d.clude_factors && rawData === null) {
      cludeFactors.memory = d.clude_factors.memory_recall;
      cludeFactors.compaction = d.clude_factors.compaction;
      cludeFactors.cache = d.clude_factors.cache;
      document.getElementById('slider-memory').value = Math.round(cludeFactors.memory * 100);
      document.getElementById('val-memory').textContent = Math.round(cludeFactors.memory * 100) + '%';
      document.getElementById('slider-compaction').value = Math.round(cludeFactors.compaction * 100);
      document.getElementById('val-compaction').textContent = Math.round(cludeFactors.compaction * 100) + '%';
      document.getElementById('slider-cache').value = Math.round(cludeFactors.cache * 100);
      document.getElementById('val-cache').textContent = Math.round(cludeFactors.cache * 100) + '%';
    }

    const isFirstLoad = rawData === null;
    rawData = d;

    if (isFirstLoad) {
      selectedRange = readURLRange();
      document.querySelectorAll('.range-btn').forEach(btn =>
        btn.classList.toggle('active', btn.dataset.range === selectedRange)
      );
      buildFilterUI(d.all_models);
    }

    applyFilter();
  } catch(e) {
    console.error(e);
  }
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif self.path == "/api/data":
            data = get_dashboard_data()
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()


def serve(host=None, port=None):
    host = host or os.environ.get("HOST", "localhost")
    port = port or int(os.environ.get("PORT", "8080"))
    server = HTTPServer((host, port), DashboardHandler)
    print(f"Clude Token Check running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    serve()
