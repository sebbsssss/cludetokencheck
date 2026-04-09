<div align="center">

<img src="assets/clude-icon.svg" alt="Clude" width="80" height="80">

<h1>Token Check</h1>

<strong>Know exactly how many tokens and dollars your Claude Code sessions cost.</strong>

<br>

![Python](https://img.shields.io/badge/python-3.8+-2244FF?style=flat&logo=python&logoColor=white)
![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-4ade80?style=flat)
![License](https://img.shields.io/badge/license-MIT-F5F5F0?style=flat)

</div>

---

## What is this?

A local dashboard that reads your Claude Code session files and tells you what you're actually spending. Everything runs on your machine — no data leaves, no accounts, no API keys needed.

```bash
git clone https://github.com/sebbsssss/cludetokencheck.git
cd cludetokencheck
python cli.py dashboard
```

No pip install. No dependencies. Just Python 3.8+.

## What You'll See

- **Total cost** — calculated from real Anthropic API pricing per model
- **Token breakdown** — input, output, cache read, and cache creation tokens
- **Daily usage chart** — stacked bars showing your usage over time
- **Model breakdown** — which Claude models (Opus, Sonnet, Haiku) you use most
- **Top projects** — which codebases are eating the most tokens
- **Session history** — every session with model, duration, turns, tokens, and cost
- **Cost by model** — see exactly how much each model tier costs you

Filter by model and time range (7d / 30d / 90d / all).

## CLI

```bash
python cli.py dashboard                     # Launch web dashboard
python cli.py today                         # Today's usage in terminal
python cli.py stats                         # All-time stats in terminal
python cli.py scan                          # Just scan, don't start server
python cli.py scan --projects-dir PATH      # Custom transcript location
```

## How It Works

Claude Code writes a JSONL file for every session in `~/.claude/projects/`. Token Check scans those files, stores the data in a local SQLite database, and serves a dashboard on `localhost:8080`.

- **Incremental** — only processes new or changed files
- **Auto-refresh** — dashboard updates every 30 seconds
- **Zero dependencies** — pure Python standard library

## Pricing

Costs are calculated using Anthropic's published API rates:

| Model | Input | Output | Cache Write | Cache Read |
|-------|-------|--------|-------------|------------|
| Opus 4.5/4.6 | $5/MTok | $25/MTok | $6.25/MTok | $0.50/MTok |
| Sonnet 4.5/4.6 | $3/MTok | $15/MTok | $3.75/MTok | $0.30/MTok |
| Haiku 4.5/4.6 | $1/MTok | $5/MTok | $1.25/MTok | $0.10/MTok |

> Note: If you're on a Max or Pro subscription, your actual costs differ from API pricing.

## Clude Savings

If you use [Clude](https://github.com/sebbsssss/cludebot) as a memory layer for your AI agents, Token Check can show you how much it saves.

Toggle **"Clude Savings"** in the top bar to see:

- **Dollars saved** — what your Clude sessions would have cost at Native rates
- **Why it's cheaper** — shorter sessions, smarter model use, less repeated context
- **Side-by-side comparison** — Native Claude Code vs With Clude

This uses real data, not estimates. The scanner detects Clude's MCP memory tools (`store_memory`, `recall_memories`, etc.) in your transcripts and compares sessions with and without them.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `localhost` | Server address |
| `PORT` | `8080` | Server port |

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built by **Seb** · Powered by [Clude](https://github.com/sebbsssss/cludebot)

</div>
