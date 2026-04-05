# CLAUDE.md - Claude Code Runtime Instructions

This file is for Claude Code and similar chat-first coding agents.
Use it as the runtime playbook for operating `unheard-buzz`.

Deep technical review material lives in `docs/ARCHITECTURE.md`.
Open that file when you need internals, debugging details, data flow, or extension guidance.

## Mission

Help users run evidence-backed consulting cases that turn public signals into issue intelligence, benchmark context, contradictions, recommendations, review packs, and repeatable case memory.

## Default workflow

1. Clarify the case, decision objective, and workstreams.
2. Generate or update `instruction.yaml`.
3. Ensure `.env` contains the required API keys.
4. Run the pipeline with state/history when appropriate.
5. Read the generated issue, benchmark, decision, review, eval, and dashboard artifacts in `output/`.
6. Summarize findings by separating evidence, inference, recommendation, and open questions.

## Parallel-agent posture

Once the brief is stable, prefer a small parallel swarm instead of one giant thread.

- `source_scout` agent: expand channels, subreddits, queries, and benchmark sources
- `issue_analyst` agent: inspect `issue_registry.csv`, `evidence_registry.csv`, and `dashboard_data.json`
- `benchmark_analyst` agent: inspect `benchmark_coverage.json`, `contradiction_registry.csv`, and alternatives
- `skeptic` agent: challenge recommendation quality, contradiction handling, and evidence sufficiency
- `writer` agent: draft the memo with explicit evidence/inference/recommendation separation
- `reviewer` agent: use `annotation_pack.csv` and review guidelines
- `graphics` agent: optional polish role after built-in dashboards already exist

Keep one orchestrator agent responsible for `instruction.yaml`, `.env`, pipeline execution, case/workstream integrity, and final synthesis.
Run any graphics polish only after the built-in dashboards and decision artifacts exist so it can work from shared artifacts instead of recollecting data.
Prefer the built-in executive and analyst dashboards over bespoke charts unless the user explicitly needs export polish.

## Stage 1 — Interview

Collect these inputs conversationally. Ask one question at a time. If the user is unsure, generate sensible defaults and keep moving.

### Q1: What case are we running?

Get a clear description of the market, product, or topic, plus the decision the case should support. Probe for specifics:
- Target audience (who are the users?)
- Geography (global, US, specific city?)
- Time frame (recent trends, historical patterns?)

Examples of valid user inputs:
- "I want to know what amputees complain about with prosthetics"
- "I'm opening a restaurant in Manhattan — what are diners saying?"
- "What do EV owners hate about charging infrastructure?"
- "How do parents feel about kids' electric toothbrushes?"

### Q2: Which workstreams and platforms matter?

Clarify the workstreams first:
- unmet needs
- benchmark comparison
- skeptic review
- ICP/segment analysis
- follow-up validation

Then decide which platforms should be used for those workstreams.

Show what's available and let them pick:
- **YouTube** — longest, most detailed user stories (requires `YOUTUBE_API_KEY`)
- **Reddit** — honest, anonymous, threaded discussions (free, no key)
- **Google Trends** — search interest direction, related queries (free, automatic)
- **Twitter/X** — real-time pulse, short reactive posts (optional, needs `TWITTER_BEARER_TOKEN`)
- **LinkedIn** — professional perspective (manual CSV import recommended)

Default if they don't choose: YouTube + Reddit + Google Trends.

### Q3: API keys

Check what they have in `.env`. At minimum they need `YOUTUBE_API_KEY`.

```
Required:   YOUTUBE_API_KEY
Free:       Reddit (no key), Google Trends via pytrends (no key)
Optional:   TWITTER_BEARER_TOKEN (free tier, 1,500 tweets/month)
Optional:   LINKEDIN_ACCESS_TOKEN (very restricted, CSV import better)
```

**Trend analysis — give them two choices:**

- **Option A (default):** pytrends — free, no key, shows Google search interest trends before collection starts. Always available.
- **Option B (upgrade):** Also enable Google Cloud Timeseries Insights API — after posts are collected, uploads their timestamps and detects anomalies/spikes in discussion volume per category. Richer analysis but requires a Google Cloud project.

If they want Option B:
1. Go to console.cloud.google.com
2. Enable "Timeseries Insights API"
3. Create an API key
4. Set `GOOGLE_CLOUD_API_KEY` and `GOOGLE_CLOUD_PROJECT` in `.env`

New Google Cloud accounts get $300 free credits.

### Q4: What categories of needs do you expect?

Help them brainstorm 5-15 categories for classifying complaints and wishes. Each needs:
- A short code (e.g., `PRICE`, `QUALITY`, `SF`)
- A name (e.g., "Price concerns")
- A description (e.g., "Value, affordability, worth it")
- Keywords (e.g., ["expensive", "overpriced", "affordable"])

If they're unsure, generate reasonable defaults from their topic and refine after the first run.

### Q5: Specific search terms or channels?

Optional but helpful:
- YouTube channels to prioritize (handle + name)
- Subreddits to search
- Hashtags to track on Twitter
- Specific search phrases

If they don't know, generate sensible defaults from the topic description.

### Generate instruction.yaml

After collecting answers, generate `instruction.yaml` and save it at the repo root. Use `instruction_template.yaml` as the schema reference.

## Stage 2 — Run the pipeline

```bash
python3 -m pip install -r requirements.txt   # first time only
python3 tools/run.py --instruction instruction.yaml
```

Useful flags:
- `--dry-run` to inspect the execution plan without API calls
- `--platforms youtube,reddit` to override enabled platforms
- `--resume` to reuse checkpoints after a failure or quota hit
- `--output-dir output_v2` to write into a different directory
- `--skip-trends` to skip Google Trends analysis

## Pipeline phases

| Phase | What happens | Can fail independently? |
|-------|-------------|----------------------|
| 0 | Google Trends (pytrends) | Yes — pipeline continues |
| 1 | Platform agents in parallel (YouTube, Reddit, Twitter, LinkedIn) | Yes — per platform |
| 2 | Unified analysis: filter, score relevance, categorize | No — critical |
| 2b | Timeseries Insights API anomaly detection (if Google Cloud key set) | Yes — optional |
| 3 | Report generation: CSV, JSON, Markdown | No — critical |
| 4 | Validation against academic references (if enabled) | Yes — optional |

After phase 3, the `analysis`, `writing`, and `graphics` agents can work in parallel from the same output artifacts.

## What to inspect after a run

Primary outputs:
- `output/summary_report.md`
- `output/decision_memo.md`
- `output/issue_registry.csv`
- `output/evidence_registry.csv`
- `output/entity_registry.csv`
- `output/benchmark_coverage.json`
- `output/contradiction_registry.csv`
- `output/opportunity_map.csv`
- `output/recommendation_cards.json`
- `output/annotation_pack.csv`
- `output/eval_report.md`
- `output/agent_plan.json`
- `output/agent_execution_log.json`
- `output/agent_handoff_log.json`
- `output/run_manifest.json`
- `output/history_diff.md` when history is enabled
- `output/visualizations/` for built-in dashboards

Checkpoints: `output/checkpoints/phase*.json`

## How to present results

When summarizing for the user:

1. **Lead with evidence.** Open with short quotes or excerpts that anchor the top issues.
2. **Surface benchmark context.** Say what benchmark sources and contradictions imply.
3. **Separate evidence, inference, and recommendation.**
4. **Use history when available.** Call out what is new, rising, or declining across runs.
5. **Call out failures and thin evidence.** Be transparent about weak source mix, auth failures, or quota limits.
6. **Offer the next validation loop.** Suggest benchmark, review, or hypothesis follow-up instead of only more collection.

## Common failure modes

- Missing `YOUTUBE_API_KEY`: YouTube collection fails fast
- Missing Reddit subreddits or queries: Reddit skips with no data
- Twitter 401/403: invalid token or insufficient tier
- Twitter/Google Trends 429: rate limits; retry or rerun later
- LinkedIn: no public search API; use `input/linkedin_export.csv`
- Empty results: expand `relevance_keywords`, tighten categories, improve search queries

## Support files

- `.env.example` — expected environment variable names
- `.env` — local-only, holds real secrets (gitignored)
- `instruction_template.yaml` — starting point for new instruction files, including analysis quality controls
- `input/linkedin_export.csv` — expected LinkedIn CSV import path
- `examples/*.yaml` — worked example instructions for multiple markets

## When to open docs/ARCHITECTURE.md

Use `docs/ARCHITECTURE.md` for:
- module-by-module responsibilities
- data flow and checkpoint behavior
- SocialPost schema and dataclass details
- extension guidance for new platforms
- known limitations and edge cases

Use `docs/GRAPHICS_AGENT.md` for:
- chart-selection guidance
- Sankey configuration notes
- styling expectations for presentation-ready visuals
- `output/visualizations/` conventions

When results are noisy, tune these first before rewriting categories:
- `analysis.min_comment_words`
- `analysis.language_allowlist`
- `analysis.dedup_normalized_text`
- `analysis.dedup_min_chars`
- `analysis.include_irrelevant_in_stats`
