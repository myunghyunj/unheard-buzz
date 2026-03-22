# unheard-buzz

Due diligence on mining unmet market needs from social media — what users say when no one's asking.

## What is this?

A social listening toolkit designed to be operated by an AI agent (Claude Code, Codex, etc.). You describe what you want to investigate in plain language, the agent generates the research plan, runs the tools, and delivers a consulting-grade report.

For deep implementation details, debugging notes, and extension guidance, see `ARCHITECTURE.md`.

### Example conversations

> **You:** "I want to know what amputees actually complain about with their prosthetics"
>
> **Agent:** Searches 20+ YouTube channels, 4 Reddit communities, checks Google Trends. Returns: 1,252 relevant comments categorized into 15 unmet-need types, ranked by frequency, with verbatim quotes ready for a presentation deck.

> **You:** "I'm opening a restaurant in Manhattan — what are the current pain points for diners?"
>
> **Agent:** Scans YouTube food vlogs, r/FoodNYC, r/AskNYC, Twitter #NYCFood. Returns: trending cuisines, common complaints (wait times, pricing, reservations), and what diners wish existed.

## How to use

### With Claude Code
```bash
claude
# Then just talk: "I want to research [your topic]"
# Claude reads CLAUDE.md and handles everything from there
```

### With Codex
```bash
codex
# Then just talk: "I want to research [your topic]"
# Codex reads AGENTS.md and handles everything from there
```

### Manual
```bash
python3 -m pip install -r requirements.txt
cp .env.example .env          # add your YouTube API key
cp instruction_template.yaml instruction.yaml
# Edit instruction.yaml for your market/topic
python3 tools/run.py --instruction instruction.yaml
```

## What you need

| Requirement | Notes |
|-------------|-------|
| Python 3.9+ | |
| YouTube API key | Free — [get one here](https://console.cloud.google.com/apis/credentials) (enable YouTube Data API v3) |
| Optional Google Cloud key | `GOOGLE_CLOUD_API_KEY` + `GOOGLE_CLOUD_PROJECT` enable Timeseries Insights anomaly detection |
| Claude Code or Codex | Recommended entry point — reads `CLAUDE.md` (Claude) or `AGENTS.md` (Codex) |

Reddit and Google Trends require no API keys. Twitter and LinkedIn are optional.
Transcript settings exist in the schema, but transcript ingestion is not active in the current public release.

## What you get

```
output/
├── trend_report.md        # "Interest in [topic] is rising 34% YoY..."
├── tsi_anomaly_report.md  # Discussion spikes/anomalies by category (optional)
├── summary_report.md      # Executive report with ranked categories
├── all_posts.csv          # Every comment collected (anonymized)
├── summary_stats.json     # Full statistics, co-occurrence matrix
├── quotable_excerpts.md   # 20-30 best verbatim quotes
└── validation_report.md   # Academic cross-reference (optional)
```

## Architecture

```
You ──→ Codex / Claude Code ──→ AGENTS.md / CLAUDE.md
                                      │
                            Stage 1: Interview
                            (topic, platforms, keys, categories)
                                      │
                            Stage 2: Execute
                                      │
                      ┌───────────────┼───────────────┐
                      │               │               │
                  YouTube          Reddit          Twitter
                   Agent            Agent           Agent     ← parallel
                      │               │               │
                      └───────────────┼───────────────┘
                                      │
                               Unified Analysis
                                      │
                                  Reports
```

## Project structure

```
unheard-buzz/
├── AGENTS.md              # Codex operating instructions
├── ARCHITECTURE.md        # Deep technical reference for review/debugging
├── CLAUDE.md              # Claude Code runtime instructions
├── CONTRIBUTING.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── README.md              # This file
├── instruction_template.yaml
├── requirements.txt
├── .env.example
├── .gitignore
├── tools/                 # Python toolkit
│   ├── run.py             # Main pipeline orchestrator
│   ├── config.py          # Loads instruction.yaml, tracks API quota
│   ├── analyzer.py        # Cross-platform analysis
│   ├── reports.py         # Output generation
│   ├── trends.py          # Google Trends + optional Timeseries Insights API
│   ├── youtube.py         # YouTube Data API v3
│   ├── reddit.py          # Reddit JSON API (free)
│   ├── twitter.py         # Twitter/X API v2
│   └── linkedin.py        # LinkedIn (CSV import)
├── examples/
│   └── amputee.yaml       # Worked example instruction
├── input/                 # Place LinkedIn CSV exports here
└── output/                # Generated reports (gitignored)
```

## Development

Minimal smoke checks:

```bash
python3 -m py_compile tools/*.py
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```

If `GOOGLE_CLOUD_API_KEY` and `GOOGLE_CLOUD_PROJECT` are set, the pipeline also runs a post-collection Timeseries Insights step that looks for category spikes and writes `tsi_anomaly_report.md`.
