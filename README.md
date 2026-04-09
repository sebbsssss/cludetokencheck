<div align="center">

<img src="https://raw.githubusercontent.com/sebbsssss/cludebot/main/assets/clude-icon.svg" alt="Clude" width="80" height="80">

<h1>Clude Token Check</h1>

<strong>Track your Claude Code token usage and see what Clude saves you.</strong>

<br>

![Python](https://img.shields.io/badge/python-3.8+-2244FF?style=flat&logo=python&logoColor=white)
![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-4ade80?style=flat)
![License](https://img.shields.io/badge/license-MIT-F5F5F0?style=flat)

</div>

---

A local dashboard that parses your Claude Code session transcripts and shows detailed token usage, costs, and **estimated savings from [Clude](https://github.com/sebbsssss/cludebot)'s cognitive memory system**.

Built on top of the Claude Code usage tracking concept, enhanced with Clude's efficiency dimension — so you can see not just what you're spending, but what you *could* save with intelligent memory.

## Features

- **Token Usage Dashboard** — Input, output, cache read, cache creation tokens with daily charts
- **Cost Estimation** — Real Anthropic API pricing (April 2026) across all Claude models
- **Clude Savings Layer** — Estimated token and cost savings from Clude's memory system
  - Memory Recall Savings (progressive disclosure)
  - Compaction Savings (dream cycle compression)
  - Cache Efficiency Boost (hybrid scoring optimization)
- **Configurable Efficiency Factors** — Adjust savings estimates via dashboard sliders or env vars
- **Model & Time Range Filters** — Filter by model, 7d/30d/90d/all time ranges
- **Per-Session Breakdown** — See savings for every coding session
- **CLI Reports** — Terminal-based usage summaries with Clude savings
- **Incremental Scanning** — Only processes new or modified transcript files
- **Zero Dependencies** — Pure Python standard library, nothing to install

## Quick Start

```bash
# Clone the repo
git clone https://github.com/sebbsssss/cludetokencheck.git
cd cludetokencheck

# Launch the dashboard (scans + opens browser)
python cli.py dashboard
```

That's it. No pip install, no virtualenv, no build step.

## Usage

```bash
# Scan transcript files and update the database
python cli.py scan

# Show today's usage with Clude savings estimate
python cli.py today

# Show all-time statistics with Clude savings
python cli.py stats

# Launch the web dashboard
python cli.py dashboard

# Scan a custom projects directory
python cli.py dashboard --projects-dir /path/to/projects
```

## Clude Savings Model

The dashboard estimates how much you'd save using [Clude](https://github.com/sebbsssss/cludebot)'s cognitive memory system. Three efficiency factors are applied to your actual usage data:

| Factor | Default | What It Models |
|--------|---------|---------------|
| **Memory Recall** | 40% | Progressive disclosure — `recallSummaries()` + `hydrate()` reduces context tokens |
| **Compaction** | 25% | Dream cycle compression — old memories consolidated into compact summaries |
| **Cache Efficiency** | 15% | Hybrid scoring — better retrieval means fewer wasted tokens on irrelevant context |

### Adjusting Factors

**Via the dashboard:** Click "Settings" in the filter bar and use the sliders.

**Via environment variables:**

```bash
CLUDE_MEMORY_SAVINGS=0.40 CLUDE_COMPACTION_SAVINGS=0.25 CLUDE_CACHE_EFFICIENCY=0.15 python cli.py dashboard
```

Set these based on your observed savings when using Clude in production.

## How It Works

1. **Scans** Claude Code's JSONL transcript files from `~/.claude/projects/`
2. **Stores** session and turn data in a local SQLite database (`~/.claude/usage.db`)
3. **Serves** an interactive dashboard on `localhost:8080`
4. **Calculates** estimated Clude savings based on your configurable efficiency factors

## Dashboard Sections

- **Clude Savings Banner** — Total tokens saved, cost saved, and efficiency percentage
- **Summary Stats** — Sessions, turns, token counts, and estimated cost
- **Daily Token Usage** — Stacked bar chart with Clude savings overlay
- **By Model** — Doughnut chart of token distribution
- **Clude Impact** — Visual comparison of actual vs. with-Clude usage
- **Savings Breakdown** — Per-factor contribution (memory, compaction, cache)
- **Top Projects** — Horizontal bar chart ranked by token usage
- **Recent Sessions** — Table with per-session Clude savings column
- **Cost by Model** — Aggregated costs with "With Clude" comparison column

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `HOST` | `localhost` | Dashboard server host |
| `PORT` | `8080` | Dashboard server port |
| `CLUDE_MEMORY_SAVINGS` | `0.40` | Memory recall savings factor (0-1) |
| `CLUDE_COMPACTION_SAVINGS` | `0.25` | Compaction savings factor (0-1) |
| `CLUDE_CACHE_EFFICIENCY` | `0.15` | Cache efficiency factor (0-1) |

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built by **Seb** · Powered by [Clude](https://github.com/sebbsssss/cludebot)

</div>
