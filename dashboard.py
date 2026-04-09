"""
dashboard.py - Clude Token Check local web dashboard served on localhost:8080.

Tracks Claude Code usage and shows real measured comparison between
Native Claude Code sessions vs sessions With Clude memory active.
"""

import json
import os
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".claude" / "usage.db"


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

    # Daily data split by Clude active vs not
    try:
        daily_clude_rows = conn.execute("""
            SELECT
                substr(t.timestamp, 1, 10) as day,
                s.clude_active,
                SUM(t.input_tokens)        as input,
                SUM(t.output_tokens)       as output,
                SUM(t.cache_read_tokens)   as cache_read,
                SUM(t.cache_creation_tokens) as cache_creation,
                COUNT(*)                   as turns
            FROM turns t
            JOIN sessions s ON t.session_id = s.session_id
            GROUP BY day, s.clude_active
            ORDER BY day
        """).fetchall()

        daily_by_clude = [{
            "day":            r["day"],
            "clude_active":   r["clude_active"] or 0,
            "input":          r["input"] or 0,
            "output":         r["output"] or 0,
            "cache_read":     r["cache_read"] or 0,
            "cache_creation": r["cache_creation"] or 0,
            "turns":          r["turns"] or 0,
        } for r in daily_clude_rows]
    except sqlite3.OperationalError:
        daily_by_clude = []

    # Read clude_active safely (column may not exist in old DBs)
    try:
        session_rows = conn.execute("""
            SELECT
                session_id, project_name, first_timestamp, last_timestamp,
                total_input_tokens, total_output_tokens,
                total_cache_read, total_cache_creation, model, turn_count,
                clude_active, clude_tool_calls
            FROM sessions
            ORDER BY last_timestamp DESC
        """).fetchall()
    except sqlite3.OperationalError:
        session_rows = conn.execute("""
            SELECT
                session_id, project_name, first_timestamp, last_timestamp,
                total_input_tokens, total_output_tokens,
                total_cache_read, total_cache_creation, model, turn_count,
                0 as clude_active, 0 as clude_tool_calls
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
            "session_id":     r["session_id"][:8],
            "project":        r["project_name"] or "unknown",
            "last":           (r["last_timestamp"] or "")[:16].replace("T", " "),
            "last_date":      (r["last_timestamp"] or "")[:10],
            "duration_min":   duration_min,
            "model":          r["model"] or "unknown",
            "turns":          r["turn_count"] or 0,
            "input":          r["total_input_tokens"] or 0,
            "output":         r["total_output_tokens"] or 0,
            "cache_read":     r["total_cache_read"] or 0,
            "cache_creation": r["total_cache_creation"] or 0,
            "clude_active":   r["clude_active"] or 0,
            "clude_tool_calls": r["clude_tool_calls"] or 0,
        })

    conn.close()

    return {
        "all_models":      all_models,
        "daily_by_model":  daily_by_model,
        "daily_by_clude":  daily_by_clude,
        "sessions_all":    sessions_all,
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Token Check — powered by Clude</title>
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
    --native: #d97757;
    --native-bg: rgba(217, 119, 87, 0.12);
    --clude: #2244FF;
    --clude-bg: rgba(34, 68, 255, 0.08);
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

  /* Clude toggle */
  .clude-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
  .clude-toggle-label { font-size: 12px; font-weight: 600; color: var(--muted); font-family: 'Inconsolata', monospace; transition: color 0.2s; }
  .clude-toggle-label.active { color: var(--accent); }
  .toggle-track { width: 36px; height: 20px; border-radius: 10px; background: var(--border); position: relative; transition: background 0.2s; flex-shrink: 0; }
  .toggle-track.on { background: var(--accent); }
  .toggle-thumb { width: 16px; height: 16px; border-radius: 50%; background: var(--text); position: absolute; top: 2px; left: 2px; transition: transform 0.2s; }
  .toggle-track.on .toggle-thumb { transform: translateX(16px); }

  /* Clude sections hidden by default */
  .clude-section { display: none !important; }
  .clude-section.visible { display: block !important; }
  .clude-section.visible.comparison-banner { display: grid !important; }
  .clude-section.visible.chart-card { display: block !important; }

  .range-group { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
  .range-btn { padding: 4px 13px; background: transparent; border: none; border-right: 1px solid var(--border); color: var(--muted); font-size: 12px; cursor: pointer; transition: background 0.15s, color 0.15s; font-family: 'Inconsolata', monospace; }
  .range-btn:last-child { border-right: none; }
  .range-btn:hover { background: rgba(255,255,255,0.04); color: var(--text); }
  .range-btn.active { background: var(--accent-glow); color: var(--accent); font-weight: 600; }

  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

  /* Savings hero */
  .savings-hero { background: linear-gradient(135deg, rgba(34,68,255,0.08) 0%, rgba(74,222,128,0.06) 100%); border: 1px solid rgba(34,68,255,0.2); border-radius: 12px; padding: 28px 32px; margin-bottom: 24px; }
  .savings-hero-top { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
  .savings-hero-title { font-size: 14px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.05em; font-family: 'Inconsolata', monospace; }
  .savings-big { display: flex; gap: 40px; flex-wrap: wrap; }
  .savings-big-item { text-align: center; }
  .savings-big-item .big-val { font-size: 36px; font-weight: 700; font-family: 'Inconsolata', monospace; line-height: 1.1; }
  .savings-big-item .big-val.green { color: var(--green); }
  .savings-big-item .big-val.accent { color: var(--accent); }
  .savings-big-item .big-label { font-size: 12px; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.04em; }

  .savings-why { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; }
  .why-card { background: rgba(0,0,0,0.3); border-radius: 8px; padding: 16px; }
  .why-card .why-icon { font-size: 20px; margin-bottom: 8px; }
  .why-card .why-title { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
  .why-card .why-body { font-size: 12px; color: var(--muted); line-height: 1.5; }
  .why-card .why-num { font-family: 'Inconsolata', monospace; font-weight: 700; }
  .why-card .why-num.native-c { color: var(--native); }
  .why-card .why-num.clude-c { color: var(--accent); }
  .why-card .why-num.green-c { color: var(--green); }

  /* Comparison banner */
  .comparison-banner { display: grid; grid-template-columns: 1fr 50px 1fr; gap: 0; margin-bottom: 24px; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }
  .comp-side { padding: 18px 20px; }
  .comp-native { background: var(--native-bg); border-right: 1px solid var(--border); }
  .comp-clude { background: var(--clude-bg); border-left: 1px solid var(--border); }
  .comp-vs { display: flex; align-items: center; justify-content: center; background: var(--card); font-size: 11px; font-weight: 700; color: var(--muted); font-family: 'Inconsolata', monospace; }
  .comp-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px; font-family: 'Inconsolata', monospace; }
  .comp-native .comp-label { color: var(--native); }
  .comp-clude .comp-label { color: var(--clude); }
  .comp-stats { display: flex; gap: 20px; flex-wrap: wrap; }
  .comp-stat .cv { font-size: 18px; font-weight: 700; font-family: 'Inconsolata', monospace; }
  .comp-stat .cl { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
  .comp-native .cv { color: var(--native); }
  .comp-clude .cv { color: var(--clude); }

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
  .badge-native { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 600; background: var(--native-bg); color: var(--native); font-family: 'Inconsolata', monospace; }
  .badge-clude { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 600; background: var(--clude-bg); color: var(--clude); font-family: 'Inconsolata', monospace; }
  .cost { color: var(--green); font-family: 'Inconsolata', monospace; }
  .cost-na { color: var(--muted); font-family: 'Inconsolata', monospace; font-size: 11px; }
  .num { font-family: 'Inconsolata', monospace; }
  .muted { color: var(--muted); }
  .section-title { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; font-family: 'Inconsolata', monospace; }
  .table-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; overflow-x: auto; }

  footer { border-top: 1px solid var(--border); padding: 20px 24px; margin-top: 8px; }
  .footer-content { max-width: 1400px; margin: 0 auto; }
  .footer-content p { color: var(--muted); font-size: 12px; line-height: 1.7; margin-bottom: 4px; }
  .footer-content p:last-child { margin-bottom: 0; }
  .footer-content a { color: var(--accent); text-decoration: none; }
  .footer-content a:hover { text-decoration: underline; }

  @media (max-width: 768px) {
    .charts-grid { grid-template-columns: 1fr; }
    .chart-card.wide { grid-column: 1; }
    .comparison-banner { grid-template-columns: 1fr; }
    .comp-vs { padding: 8px; }
    .comp-native { border-right: none; border-bottom: 1px solid var(--border); }
    .comp-clude { border-left: none; border-top: 1px solid var(--border); }
    .savings-why { grid-template-columns: 1fr; }
    .savings-big { gap: 24px; }
    .savings-big-item .big-val { font-size: 28px; }
  }
</style>
</head>
<body>
<header>
  <div class="header-left">
    <svg class="header-logo" viewBox="0 0 1080 1080" xmlns="http://www.w3.org/2000/svg">
      <path fill="#2244FF" d="M877.5,295.97V109.03c0-10.51-8.52-19.03-19.03-19.03h-430.97c-10.51,0-19.03,8.52-19.03,19.03v147.53c0,25.23-10.02,49.44-27.87,67.28l-155.81,155.81c-14.28,14.27-22.29,33.64-22.29,53.82v437.5c0,10.51,8.52,19.03,19.03,19.03h636.94c10.51,0,19.03-8.52,19.03-19.03v-186.94c0-10.51-8.52-19.03-19.03-19.03h-421.46c-5.25,0-9.51-4.26-9.51-9.51v-402.43c0-21.02,17.04-38.06,38.06-38.06h392.91c10.51,0,19.03-8.52,19.03-19.03Z"/>
    </svg>
    <h1>Token Check <span style="font-weight:400;color:var(--muted);font-size:14px">powered by</span> <span>Clude</span></h1>
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
  <div class="clude-toggle" onclick="toggleClude()">
    <div class="clude-toggle-label" id="clude-toggle-label">Clude Savings</div>
    <div class="toggle-track" id="clude-toggle-track"><div class="toggle-thumb"></div></div>
  </div>
</div>

<div class="container">
  <!-- Savings Hero (hidden until toggle) -->
  <div class="savings-hero clude-section" id="savings-hero">
    <div class="savings-hero-top">
      <div class="savings-hero-title">Savings with Clude</div>
    </div>
    <div class="savings-big" id="savings-big">
      <div class="savings-big-item">
        <div class="big-val green" id="hero-cost-saved">--</div>
        <div class="big-label">Cost Saved</div>
      </div>
      <div class="savings-big-item">
        <div class="big-val accent" id="hero-tokens-saved">--</div>
        <div class="big-label">Tokens Saved</div>
      </div>
      <div class="savings-big-item">
        <div class="big-val green" id="hero-pct-saved">--</div>
        <div class="big-label">Cheaper per Session</div>
      </div>
    </div>
    <div class="savings-why" id="savings-why">
      <div class="why-card">
        <div class="why-title">Shorter Sessions</div>
        <div class="why-body">Clude's memory means the agent gets context faster and finishes sooner.<br><span class="why-num native-c" id="why-native-turns">--</span> vs <span class="why-num clude-c" id="why-clude-turns">--</span> avg turns/session</div>
      </div>
      <div class="why-card">
        <div class="why-title">Smarter Model Usage</div>
        <div class="why-body">With memory, Clude can use cheaper models effectively for more tasks.<br>Avg cost/session: <span class="why-num native-c" id="why-native-cps">--</span> vs <span class="why-num clude-c" id="why-clude-cps">--</span></div>
      </div>
      <div class="why-card">
        <div class="why-title">Less Repeated Context</div>
        <div class="why-body">Memory reduces how much cached context needs to be re-read each turn.<br>Cache/turn: <span class="why-num native-c" id="why-native-cache">--</span> vs <span class="why-num clude-c" id="why-clude-cache">--</span></div>
      </div>
    </div>
  </div>

  <!-- Side-by-side comparison (hidden until toggle) -->
  <div class="comparison-banner clude-section" id="comparison-banner">
    <div class="comp-side comp-native">
      <div class="comp-label">Native Claude Code</div>
      <div class="comp-stats">
        <div class="comp-stat"><div class="cv" id="native-sessions">--</div><div class="cl">Sessions</div></div>
        <div class="comp-stat"><div class="cv" id="native-tokens">--</div><div class="cl">Tokens/Turn</div></div>
        <div class="comp-stat"><div class="cv" id="native-cost">--</div><div class="cl">Total Cost</div></div>
      </div>
    </div>
    <div class="comp-vs">VS</div>
    <div class="comp-side comp-clude">
      <div class="comp-label">With Clude</div>
      <div class="comp-stats">
        <div class="comp-stat"><div class="cv" id="clude-sessions">--</div><div class="cl">Sessions</div></div>
        <div class="comp-stat"><div class="cv" id="clude-tokens">--</div><div class="cl">Tokens/Turn</div></div>
        <div class="comp-stat"><div class="cv" id="clude-cost">--</div><div class="cl">Total Cost</div></div>
      </div>
    </div>
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
    <div class="chart-card clude-section" id="chart-comparison-card">
      <h2>Native vs Clude — Tokens per Turn</h2>
      <div class="chart-wrap"><canvas id="chart-comparison"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Top Projects by Tokens</h2>
      <div class="chart-wrap"><canvas id="chart-project"></canvas></div>
    </div>
    <div class="chart-card clude-section" id="chart-distribution-card">
      <h2>Session Distribution</h2>
      <div class="chart-wrap"><canvas id="chart-distribution"></canvas></div>
    </div>
  </div>
  <div class="table-card">
    <div class="section-title">Recent Sessions</div>
    <table>
      <thead><tr>
        <th>Session</th><th>Project</th><th>Last Active</th><th>Duration</th>
        <th>Model</th><th class="mode-col" style="display:none">Mode</th><th>Turns</th><th>Input</th><th>Output</th><th>Est. Cost</th>
      </tr></thead>
      <tbody id="sessions-body"></tbody>
    </table>
  </div>
  <div class="table-card">
    <div class="section-title">Cost by Model</div>
    <table>
      <thead><tr>
        <th>Model</th><th>Turns</th><th>Input</th><th>Output</th>
        <th>Cache Read</th><th>Cache Creation</th><th>Est. Cost</th>
      </tr></thead>
      <tbody id="model-cost-body"></tbody>
    </table>
  </div>
</div>

<footer>
  <div class="footer-content">
    <p>Cost estimates based on Anthropic API pricing (<a href="https://claude.com/pricing#api" target="_blank">claude.com/pricing#api</a>) as of April 2026. Sessions are classified as "With Clude" when Clude memory MCP tools are detected in the transcript.</p>
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
let cludeMode = false;

// -- Clude toggle -------------------------------------------------------------
function toggleClude() {
  cludeMode = !cludeMode;
  document.getElementById('clude-toggle-track').classList.toggle('on', cludeMode);
  document.getElementById('clude-toggle-label').classList.toggle('active', cludeMode);

  // Show/hide Clude sections
  document.querySelectorAll('.clude-section').forEach(el => {
    el.classList.toggle('visible', cludeMode);
  });

  // Show/hide Mode column in sessions table
  document.querySelectorAll('.mode-col').forEach(el => {
    el.style.display = cludeMode ? '' : 'none';
  });

  // Re-render charts to fix sizing after show/hide
  if (rawData) applyFilter();
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

// -- Formatting ---------------------------------------------------------------
function fmt(n) {
  return Math.round(n).toLocaleString();
}
function fmtCost(c)    { return '$' + c.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4}); }
function fmtCostBig(c) { return '$' + c.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }

// -- Chart colors -------------------------------------------------------------
const TOKEN_COLORS = {
  input:          'rgba(34, 68, 255, 0.8)',
  output:         'rgba(167, 139, 250, 0.8)',
  cache_read:     'rgba(74, 222, 128, 0.6)',
  cache_creation: 'rgba(251, 191, 36, 0.6)',
};
const MODEL_COLORS = ['#2244FF','#4f8ef7','#4ade80','#a78bfa','#fbbf24','#f472b6','#34d399','#60a5fa'];
const NATIVE_COLOR = 'rgba(217, 119, 87, 0.8)';
const CLUDE_COLOR = 'rgba(34, 68, 255, 0.8)';

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

  // Split sessions into Native vs Clude
  const nativeSessions = filteredSessions.filter(s => !s.clude_active);
  const cludeSessions = filteredSessions.filter(s => s.clude_active);

  const nativeStats = computeGroupStats(nativeSessions);
  const cludeStats = computeGroupStats(cludeSessions);

  document.getElementById('daily-chart-title').textContent = 'Daily Token Usage \u2014 ' + RANGE_LABELS[selectedRange];

  renderSavingsHero(nativeStats, cludeStats);
  renderComparisonBanner(nativeStats, cludeStats);
  renderStats(totals);
  renderDailyChart(daily);
  renderModelChart(byModel);
  renderComparisonChart(nativeStats, cludeStats);
  renderProjectChart(byProject);
  renderDistributionChart(nativeSessions, cludeSessions);
  renderSessionsTable(filteredSessions.slice(0, 20));
  renderModelCostTable(byModel);
}

function computeGroupStats(sessions) {
  let totalInput = 0, totalOutput = 0, totalCR = 0, totalCC = 0, totalTurns = 0, totalCost = 0;
  for (const s of sessions) {
    totalInput  += s.input;
    totalOutput += s.output;
    totalCR     += s.cache_read;
    totalCC     += s.cache_creation;
    totalTurns  += s.turns;
    totalCost   += calcCost(s.model, s.input, s.output, s.cache_read, s.cache_creation);
  }
  const count = sessions.length;
  return {
    count,
    totalInput, totalOutput, totalCR, totalCC, totalTurns, totalCost,
    totalTokens: totalInput + totalOutput,
    tokensPerTurn: totalTurns > 0 ? Math.round((totalInput + totalOutput) / totalTurns) : 0,
    avgTurnsPerSession: count > 0 ? Math.round(totalTurns / count) : 0,
    avgCostPerSession: count > 0 ? totalCost / count : 0,
    cachePerTurn: totalTurns > 0 ? Math.round(totalCR / totalTurns) : 0,
  };
}

// -- Renderers ----------------------------------------------------------------
function renderSavingsHero(native, clude) {
  // Calculate: "If Clude sessions had cost the same per-session as Native, you'd have spent X more"
  const wouldHaveSpent = clude.count > 0 && native.avgCostPerSession > 0
    ? clude.count * native.avgCostPerSession
    : 0;
  const actuallySpent = clude.totalCost;
  const costSaved = Math.max(wouldHaveSpent - actuallySpent, 0);

  const wouldHaveUsedTokens = clude.count > 0 && native.count > 0
    ? clude.count * (native.totalTokens / native.count)
    : 0;
  const tokensSaved = Math.max(Math.round(wouldHaveUsedTokens - clude.totalTokens), 0);

  const pctCheaper = native.avgCostPerSession > 0 && clude.avgCostPerSession > 0
    ? ((native.avgCostPerSession - clude.avgCostPerSession) / native.avgCostPerSession * 100)
    : 0;

  // Hero numbers
  document.getElementById('hero-cost-saved').textContent = costSaved > 0 ? fmtCostBig(costSaved) : '--';
  document.getElementById('hero-tokens-saved').textContent = tokensSaved > 0 ? fmt(tokensSaved) : '--';
  document.getElementById('hero-pct-saved').textContent = pctCheaper > 0 ? pctCheaper.toFixed(0) + '%' : '--';

  // Why cards
  document.getElementById('why-native-turns').textContent = fmt(native.avgTurnsPerSession);
  document.getElementById('why-clude-turns').textContent = fmt(clude.avgTurnsPerSession);
  document.getElementById('why-native-cps').textContent = fmtCostBig(native.avgCostPerSession);
  document.getElementById('why-clude-cps').textContent = fmtCostBig(clude.avgCostPerSession);
  document.getElementById('why-native-cache').textContent = fmt(native.cachePerTurn);
  document.getElementById('why-clude-cache').textContent = fmt(clude.cachePerTurn);

  // Hide hero if no Clude sessions (even when toggle is on)
  if (cludeMode && clude.count === 0) {
    document.getElementById('savings-hero').classList.remove('visible');
  }
}

function renderComparisonBanner(native, clude) {
  document.getElementById('native-sessions').textContent = native.count.toLocaleString();
  document.getElementById('native-tokens').textContent = fmt(native.tokensPerTurn);
  document.getElementById('native-cost').textContent = fmtCostBig(native.totalCost);

  document.getElementById('clude-sessions').textContent = clude.count.toLocaleString();
  document.getElementById('clude-tokens').textContent = fmt(clude.tokensPerTurn);
  document.getElementById('clude-cost').textContent = fmtCostBig(clude.totalCost);
}

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
  charts.daily = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: daily.map(d => d.day),
      datasets: [
        { label: 'Input',          data: daily.map(d => d.input),          backgroundColor: TOKEN_COLORS.input,          stack: 'tokens' },
        { label: 'Output',         data: daily.map(d => d.output),         backgroundColor: TOKEN_COLORS.output,         stack: 'tokens' },
        { label: 'Cache Read',     data: daily.map(d => d.cache_read),     backgroundColor: TOKEN_COLORS.cache_read,     stack: 'tokens' },
        { label: 'Cache Creation', data: daily.map(d => d.cache_creation), backgroundColor: TOKEN_COLORS.cache_creation, stack: 'tokens' },
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

function renderComparisonChart(native, clude) {
  const ctx = document.getElementById('chart-comparison').getContext('2d');
  if (charts.comparison) charts.comparison.destroy();

  charts.comparison = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Tokens/Turn', 'Input/Turn', 'Output/Turn'],
      datasets: [
        {
          label: 'Native',
          data: [
            native.tokensPerTurn,
            native.totalTurns > 0 ? Math.round(native.totalInput / native.totalTurns) : 0,
            native.totalTurns > 0 ? Math.round(native.totalOutput / native.totalTurns) : 0,
          ],
          backgroundColor: NATIVE_COLOR,
          borderRadius: 4,
        },
        {
          label: 'With Clude',
          data: [
            clude.tokensPerTurn,
            clude.totalTurns > 0 ? Math.round(clude.totalInput / clude.totalTurns) : 0,
            clude.totalTurns > 0 ? Math.round(clude.totalOutput / clude.totalTurns) : 0,
          ],
          backgroundColor: CLUDE_COLOR,
          borderRadius: 4,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892a4', boxWidth: 12, font: { family: "'Inconsolata', monospace" } } } },
      scales: {
        x: { ticks: { color: '#8892a4', font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
        y: { ticks: { color: '#8892a4', callback: v => fmt(v), font: { family: "'Inconsolata', monospace" } }, grid: { color: '#1e1e2a' } },
      }
    }
  });
}

function renderDistributionChart(nativeSessions, cludeSessions) {
  const ctx = document.getElementById('chart-distribution').getContext('2d');
  if (charts.distribution) charts.distribution.destroy();

  charts.distribution = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Native Claude Code', 'With Clude'],
      datasets: [{
        data: [nativeSessions.length, cludeSessions.length],
        backgroundColor: [NATIVE_COLOR, CLUDE_COLOR],
        borderWidth: 2,
        borderColor: '#111116'
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8892a4', boxWidth: 12, font: { size: 11, family: "'Inconsolata', monospace" } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} sessions` } }
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
    const costCell = isBillable(s.model)
      ? `<td class="cost">${fmtCost(cost)}</td>`
      : `<td class="cost-na">n/a</td>`;
    const badge = s.clude_active
      ? `<span class="badge-clude">CLUDE</span>`
      : `<span class="badge-native">NATIVE</span>`;
    return `<tr>
      <td class="muted" style="font-family:'Inconsolata',monospace">${esc(s.session_id)}&hellip;</td>
      <td>${esc(s.project)}</td>
      <td class="muted">${esc(s.last)}</td>
      <td class="muted">${esc(s.duration_min)}m</td>
      <td><span class="model-tag">${esc(s.model)}</span></td>
      <td class="mode-col" style="${cludeMode ? '' : 'display:none'}">${badge}</td>
      <td class="num">${s.turns}</td>
      <td class="num">${fmt(s.input)}</td>
      <td class="num">${fmt(s.output)}</td>
      ${costCell}
    </tr>`;
  }).join('');
}

function renderModelCostTable(byModel) {
  document.getElementById('model-cost-body').innerHTML = byModel.map(m => {
    const cost = calcCost(m.model, m.input, m.output, m.cache_read, m.cache_creation);
    const costCell = isBillable(m.model)
      ? `<td class="cost">${fmtCost(cost)}</td>`
      : `<td class="cost-na">n/a</td>`;
    return `<tr>
      <td><span class="model-tag">${esc(m.model)}</span></td>
      <td class="num">${fmt(m.turns)}</td>
      <td class="num">${fmt(m.input)}</td>
      <td class="num">${fmt(m.output)}</td>
      <td class="num">${fmt(m.cache_read)}</td>
      <td class="num">${fmt(m.cache_creation)}</td>
      ${costCell}
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
