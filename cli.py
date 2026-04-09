"""
cli.py - Command-line interface for Clude Token Check.

Commands:
  scan      - Scan JSONL files and update the database
  today     - Print today's usage summary with Clude savings estimate
  stats     - Print all-time usage statistics with Clude savings
  dashboard - Scan + open browser + start dashboard server
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path.home() / ".claude" / "usage.db"

PRICING = {
    "claude-opus-4-6":   {"input":  5.00, "output": 25.00},
    "claude-opus-4-5":   {"input":  5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input":  1.00, "output":  5.00},
    "claude-haiku-4-6":  {"input":  1.00, "output":  5.00},
}

# Clude efficiency factors (configurable via env vars)
CLUDE_MEMORY_RECALL_SAVINGS = float(os.environ.get("CLUDE_MEMORY_SAVINGS", "0.40"))
CLUDE_COMPACTION_SAVINGS = float(os.environ.get("CLUDE_COMPACTION_SAVINGS", "0.25"))
CLUDE_CACHE_EFFICIENCY = float(os.environ.get("CLUDE_CACHE_EFFICIENCY", "0.15"))


def get_pricing(model):
    if not model:
        return None
    if model in PRICING:
        return PRICING[model]
    for key in PRICING:
        if model.startswith(key):
            return PRICING[key]
    m = model.lower()
    if "opus" in m:
        return PRICING["claude-opus-4-6"]
    if "sonnet" in m:
        return PRICING["claude-sonnet-4-6"]
    if "haiku" in m:
        return PRICING["claude-haiku-4-5"]
    return None


def calc_cost(model, inp, out, cache_read, cache_creation):
    p = get_pricing(model)
    if not p:
        return 0.0
    return (
        inp          * p["input"]  / 1_000_000 +
        out          * p["output"] / 1_000_000 +
        cache_read   * p["input"]  * 0.10 / 1_000_000 +
        cache_creation * p["input"] * 1.25 / 1_000_000
    )


def calc_clude_savings(inp, out, cache_read):
    """Estimate token savings from Clude's memory system."""
    input_saved = inp * CLUDE_MEMORY_RECALL_SAVINGS
    output_saved = out * CLUDE_COMPACTION_SAVINGS
    cache_saved = cache_read * CLUDE_CACHE_EFFICIENCY
    return int(input_saved + output_saved + cache_saved)


def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fmt_cost(c):
    return f"${c:.4f}"


def hr(char="-", width=60):
    print(char * width)


def require_db():
    if not DB_PATH.exists():
        print("Database not found. Run: python cli.py scan")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


# -- Commands ------------------------------------------------------------------

def cmd_scan(projects_dir=None):
    from scanner import scan
    scan(projects_dir=Path(projects_dir) if projects_dir else None)


def cmd_today():
    conn = require_db()
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()

    rows = conn.execute("""
        SELECT
            COALESCE(model, 'unknown') as model,
            SUM(input_tokens)          as inp,
            SUM(output_tokens)         as out,
            SUM(cache_read_tokens)     as cr,
            SUM(cache_creation_tokens) as cc,
            COUNT(*)                   as turns
        FROM turns
        WHERE substr(timestamp, 1, 10) = ?
        GROUP BY model
        ORDER BY inp + out DESC
    """, (today,)).fetchall()

    sessions = conn.execute("""
        SELECT COUNT(DISTINCT session_id) as cnt
        FROM turns
        WHERE substr(timestamp, 1, 10) = ?
    """, (today,)).fetchone()

    print()
    hr("=")
    print(f"  Clude Token Check  |  Today's Usage  ({today})")
    hr("=")

    if not rows:
        print("  No usage recorded today.")
        print()
        return

    total_inp = total_out = total_cr = total_cc = total_turns = 0
    total_cost = 0.0

    for r in rows:
        cost = calc_cost(r["model"], r["inp"] or 0, r["out"] or 0, r["cr"] or 0, r["cc"] or 0)
        total_cost += cost
        total_inp += r["inp"] or 0
        total_out += r["out"] or 0
        total_cr  += r["cr"]  or 0
        total_cc  += r["cc"]  or 0
        total_turns += r["turns"]
        print(f"  {r['model']:<30}  turns={r['turns']:<4}  in={fmt(r['inp'] or 0):<8}  out={fmt(r['out'] or 0):<8}  cost={fmt_cost(cost)}")

    hr()
    print(f"  {'TOTAL':<30}  turns={total_turns:<4}  in={fmt(total_inp):<8}  out={fmt(total_out):<8}  cost={fmt_cost(total_cost)}")
    print()
    print(f"  Sessions today:   {sessions['cnt']}")
    print(f"  Cache read:       {fmt(total_cr)}")
    print(f"  Cache creation:   {fmt(total_cc)}")

    # Clude savings estimate
    tokens_saved = calc_clude_savings(total_inp, total_out, total_cr)
    savings_pct = (tokens_saved / max(total_inp + total_out + total_cr, 1)) * 100
    hr()
    print(f"  \033[34mClude Savings Estimate:\033[0m")
    print(f"    Tokens saved:   ~{fmt(tokens_saved)}")
    print(f"    Efficiency:     ~{savings_pct:.1f}% reduction")
    hr("=")
    print()
    conn.close()


def cmd_stats():
    conn = require_db()
    conn.row_factory = sqlite3.Row

    totals = conn.execute("""
        SELECT
            SUM(total_input_tokens)   as inp,
            SUM(total_output_tokens)  as out,
            SUM(total_cache_read)     as cr,
            SUM(total_cache_creation) as cc,
            SUM(turn_count)           as turns,
            COUNT(*)                  as sessions,
            MIN(first_timestamp)      as first,
            MAX(last_timestamp)       as last
        FROM sessions
    """).fetchone()

    by_model = conn.execute("""
        SELECT
            COALESCE(model, 'unknown') as model,
            SUM(total_input_tokens)    as inp,
            SUM(total_output_tokens)   as out,
            SUM(total_cache_read)      as cr,
            SUM(total_cache_creation)  as cc,
            SUM(turn_count)            as turns,
            COUNT(*)                   as sessions
        FROM sessions
        GROUP BY model
        ORDER BY inp + out DESC
    """).fetchall()

    top_projects = conn.execute("""
        SELECT
            project_name,
            SUM(total_input_tokens)  as inp,
            SUM(total_output_tokens) as out,
            SUM(turn_count)          as turns,
            COUNT(*)                 as sessions
        FROM sessions
        GROUP BY project_name
        ORDER BY inp + out DESC
        LIMIT 5
    """).fetchall()

    daily_avg = conn.execute("""
        SELECT
            AVG(daily_inp) as avg_inp,
            AVG(daily_out) as avg_out,
            AVG(daily_cost) as avg_cost
        FROM (
            SELECT
                substr(timestamp, 1, 10) as day,
                SUM(input_tokens) as daily_inp,
                SUM(output_tokens) as daily_out,
                0.0 as daily_cost
            FROM turns
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY day
        )
    """).fetchone()

    total_cost = sum(
        calc_cost(r["model"], r["inp"] or 0, r["out"] or 0, r["cr"] or 0, r["cc"] or 0)
        for r in by_model
    )

    print()
    hr("=")
    print("  Clude Token Check - All-Time Statistics")
    hr("=")

    first_date = (totals["first"] or "")[:10]
    last_date = (totals["last"] or "")[:10]
    print(f"  Period:           {first_date} to {last_date}")
    print(f"  Total sessions:   {totals['sessions'] or 0:,}")
    print(f"  Total turns:      {fmt(totals['turns'] or 0)}")
    print()
    print(f"  Input tokens:     {fmt(totals['inp'] or 0):<12}  (raw prompt tokens)")
    print(f"  Output tokens:    {fmt(totals['out'] or 0):<12}  (generated tokens)")
    print(f"  Cache read:       {fmt(totals['cr'] or 0):<12}  (90% cheaper than input)")
    print(f"  Cache creation:   {fmt(totals['cc'] or 0):<12}  (25% premium on input)")
    print()
    print(f"  Est. total cost:  ${total_cost:.4f}")
    hr()

    print("  By Model:")
    for r in by_model:
        cost = calc_cost(r["model"], r["inp"] or 0, r["out"] or 0, r["cr"] or 0, r["cc"] or 0)
        print(f"    {r['model']:<30}  sessions={r['sessions']:<4}  turns={fmt(r['turns'] or 0):<6}  "
              f"in={fmt(r['inp'] or 0):<8}  out={fmt(r['out'] or 0):<8}  cost={fmt_cost(cost)}")

    hr()
    print("  Top Projects:")
    for r in top_projects:
        print(f"    {(r['project_name'] or 'unknown'):<40}  sessions={r['sessions']:<3}  "
              f"turns={fmt(r['turns'] or 0):<6}  tokens={fmt((r['inp'] or 0)+(r['out'] or 0))}")

    if daily_avg["avg_inp"]:
        hr()
        print("  Daily Average (last 30 days):")
        print(f"    Input:   {fmt(int(daily_avg['avg_inp'] or 0))}")
        print(f"    Output:  {fmt(int(daily_avg['avg_out'] or 0))}")

    # Clude savings
    total_inp = totals['inp'] or 0
    total_out = totals['out'] or 0
    total_cr = totals['cr'] or 0
    tokens_saved = calc_clude_savings(total_inp, total_out, total_cr)
    savings_pct = (tokens_saved / max(total_inp + total_out + total_cr, 1)) * 100

    hr()
    print(f"  \033[34mClude Savings Estimate (All-Time):\033[0m")
    print(f"    Tokens saved:       ~{fmt(tokens_saved)}")
    print(f"    Efficiency gain:    ~{savings_pct:.1f}% reduction")
    print(f"    Memory recall:      {CLUDE_MEMORY_RECALL_SAVINGS*100:.0f}% input reduction")
    print(f"    Compaction:         {CLUDE_COMPACTION_SAVINGS*100:.0f}% output reduction")
    print(f"    Cache efficiency:   {CLUDE_CACHE_EFFICIENCY*100:.0f}% cache optimization")

    hr("=")
    print()
    conn.close()


def cmd_dashboard(projects_dir=None):
    import webbrowser
    import threading
    import time

    print("Running scan first...")
    cmd_scan(projects_dir=projects_dir)

    print("\nStarting Clude Token Check dashboard...")
    from dashboard import serve

    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", "8080"))

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(f"http://{host}:{port}")

    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    serve(host=host, port=port)


# -- Entry point ---------------------------------------------------------------

USAGE = """
Clude Token Check - Track your Claude Code usage and see what Clude saves you.

Usage:
  python cli.py scan [--projects-dir PATH]   Scan JSONL files and update database
  python cli.py today                        Show today's usage with Clude savings
  python cli.py stats                        Show all-time stats with Clude savings
  python cli.py dashboard [--projects-dir PATH]  Scan + start dashboard

Environment variables for Clude efficiency factors:
  CLUDE_MEMORY_SAVINGS      Memory recall savings (default: 0.40)
  CLUDE_COMPACTION_SAVINGS  Compaction savings (default: 0.25)
  CLUDE_CACHE_EFFICIENCY    Cache efficiency boost (default: 0.15)
"""

COMMANDS = {
    "scan": cmd_scan,
    "today": cmd_today,
    "stats": cmd_stats,
    "dashboard": cmd_dashboard,
}

def parse_projects_dir(args):
    """Extract --projects-dir value from argument list."""
    for i, arg in enumerate(args):
        if arg == "--projects-dir" and i + 1 < len(args):
            return args[i + 1]
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        sys.exit(0)

    command = sys.argv[1]
    projects_dir = parse_projects_dir(sys.argv[2:])

    if command in ("scan", "dashboard") and projects_dir:
        COMMANDS[command](projects_dir=projects_dir)
    else:
        COMMANDS[command]()
