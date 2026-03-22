# unheard-buzz

Unheard-Buzz is an agent-first social listening toolkit for mining unmet needs from public online conversations.

You define a topic, keywords, platforms, and category schema in `instruction.yaml`. The pipeline collects posts across supported platforms, normalizes them into a shared `SocialPost` structure, applies configurable filtering and category assignment, and produces report-ready outputs.

## What this repository is good at

- Configurable unmet-need discovery workflows
- Cross-platform normalization into one post model
- Keyword- and rule-driven relevance and category tagging
- Quote extraction and report artifact generation
- Agent-friendly operation through `CLAUDE.md` and `AGENTS.md`

## What it is not yet

This repository is not yet a full semantic intelligence stack. Multilingual handling is still heuristic, and inference quality still depends strongly on query design, keyword coverage, and platform API constraints.

## Good example topics

- Amputee prosthetic unmet needs
- EV charging frustrations
- Smart home privacy concerns
- Pet telehealth pain points
- Indie game developer publishing bottlenecks

Ready-made instruction examples live in `examples/`.

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```

Use `claude` or `codex` if you want an agent to drive the interview and execution flow using `CLAUDE.md` or `AGENTS.md`.

## Operational notes

This workflow can be API- and rate-limit-heavy, especially on YouTube and Twitter/X. Start with narrow queries, small quotas, and `--dry-run` before scaling collection.

Useful analysis controls in `instruction.yaml`:

- `analysis.min_comment_words`
- `analysis.language_allowlist`
- `analysis.dedup_normalized_text`
- `analysis.dedup_min_chars`
- `analysis.include_irrelevant_in_stats`

## Core outputs

```text
output/
├── trend_report.md
├── tsi_anomaly_report.md
├── summary_report.md
├── all_posts.csv
├── summary_stats.json
├── quotable_excerpts.md
└── validation_report.md
```

## Repository notes

- Deep implementation details, debugging notes, and extension guidance live in `ARCHITECTURE.md`.
- Transcript settings exist in the schema, but transcript ingestion is not active in the current public release.
- Reddit and Google Trends require no API keys. Twitter/X and LinkedIn are optional. `GOOGLE_CLOUD_API_KEY` and `GOOGLE_CLOUD_PROJECT` enable the optional Timeseries Insights step.

## Future plans

We are expanding toward broader regional and language coverage, including communities in Korea, Japan, China, Russia, the United States, and Europe.

Current multilingual handling is still heuristic. Broader multilingual support is planned, but not yet production-grade.

## Development

```bash
python3 -m py_compile tools/*.py
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```
