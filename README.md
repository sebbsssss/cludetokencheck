<div align="center">

<img src="https://raw.githubusercontent.com/sebbsssss/cludebot/main/assets/clude-icon.svg" alt="Clude" width="80" height="80">

<h1>Token Check</h1>

<strong>See exactly what Claude Code costs you — and how much Clude saves.</strong>

<br>

![Python](https://img.shields.io/badge/python-3.8+-2244FF?style=flat&logo=python&logoColor=white)
![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-4ade80?style=flat)
![License](https://img.shields.io/badge/license-MIT-F5F5F0?style=flat)

</div>

---

## What is this?

A local dashboard that reads your Claude Code session files and shows you:

1. **How many tokens you're using** — broken down by model, day, and project
2. **How much it costs** — calculated from real Anthropic API pricing
3. **How much Clude saves you** — by comparing sessions with and without [Clude](https://github.com/sebbsssss/cludebot) memory

Everything runs locally. Your data never leaves your machine.

## Quick Start

```bash
git clone https://github.com/sebbsssss/cludetokencheck.git
cd cludetokencheck
python cli.py dashboard
```

That's it. No pip install. No dependencies. Just Python 3.8+.

Your browser opens to `localhost:8080` with your full usage dashboard.

## What You'll See

### Default View — Your Claude Code Usage

- **Summary cards** — total sessions, turns, tokens, and estimated cost
- **Daily token chart** — stacked bars showing input, output, and cache usage over time
- **Model breakdown** — which Claude models you're using most
- **Top projects** — ranked by token consumption
- **Session table** — every session with model, duration, tokens, and cost
- **Cost by model** — how much each model is costing you

### Toggle "Clude Savings" — See the Difference

Flip the toggle in the top bar to reveal:

- **Savings hero** — total dollars saved, tokens saved, and % cheaper per session
- **Why it's cheaper** — three clear reasons with your real numbers:
  - Sessions finish faster (fewer turns needed)
  - Smarter model usage (memory lets cheaper models do more)
  - Less repeated context (memory replaces re-reading cached data)
- **Side-by-side comparison** — Native Claude Code vs With Clude stats
- **Tokens per turn chart** — bar chart comparing both modes
- **Session distribution** — how many sessions used Clude vs didn't

### How Savings Are Calculated

No estimates. No projections. **Real measured data.**

The scanner detects when [Clude](https://github.com/sebbsssss/cludebot)'s memory tools (`store_memory`, `recall_memories`, etc.) appear in your session transcripts. Sessions with these tools are tagged "With Clude" — everything else is "Native."

Then it's simple math:
- Your Clude sessions averaged **$X per session**
- Your Native sessions averaged **$Y per session**
- If those Clude sessions had run at Native rates, you'd have spent **$Z more**

That difference is your real savings.

## CLI Commands

```bash
python cli.py scan                          # Scan transcripts, update database
python cli.py today                         # Today's usage (terminal)
python cli.py stats                         # All-time stats (terminal)
python cli.py dashboard                     # Launch web dashboard
python cli.py dashboard --projects-dir PATH # Custom transcript location
```

## How It Works

```
~/.claude/projects/**/*.jsonl     Claude Code writes these automatically
         │
         ▼
    scanner.py                    Parses JSONL, detects Clude tools, stores in SQLite
         │
         ▼
    ~/.claude/usage.db            Local database (sessions, turns, Clude flags)
         │
         ▼
    dashboard.py                  Serves interactive dashboard on localhost:8080
```

- **Incremental** — only processes new or changed files
- **Zero dependencies** — pure Python standard library
- **Auto-refresh** — dashboard updates every 30 seconds

## Configuration

| Variable | Default | What it does |
|----------|---------|-------------|
| `HOST` | `localhost` | Server address |
| `PORT` | `8080` | Server port |

## Tests

```bash
python -m unittest discover -s tests -v
```

72 tests covering pricing, scanning, parsing, database operations, HTTP endpoints, and template validation.

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built by **Seb** · Powered by [Clude](https://github.com/sebbsssss/cludebot)

</div>
