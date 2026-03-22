# AGENTS.md - Codex Runtime Instructions

This file is for Codex and similar repo-aware agents.
Use it as the runtime playbook for operating `unheard-buzz`.

Deep technical review material lives in `ARCHITECTURE.md`.
Read that file when you need internals, debugging details, extension guidance, or review context.

## Mission

Help users discover unmet market needs by mining social media platforms and summarizing the findings in a way that is useful for product, GTM, and research decisions.

## Default workflow

1. Interview the user one question at a time.
2. Generate or update `instruction.yaml`.
3. Ensure `.env` contains the required API keys.
4. Run the pipeline.
5. Read the generated reports in `output/`.
6. Summarize findings with real user quotes first, then patterns and next steps.

## Stage 1 - Interview

Collect these inputs conversationally:

1. What market, product, audience, or pain point should we investigate?
2. Which platforms should we search?
3. Which API keys are already available?
4. What unmet-need categories should we classify into?
5. Are there specific subreddits, channels, hashtags, or search phrases to prioritize?

Ask one question at a time.
If the user is unsure, generate sensible defaults and keep moving.

## Platform defaults

- Default platform mix: YouTube + Reddit + Google Trends
- YouTube: longest, most detailed user stories; requires `YOUTUBE_API_KEY`
- Reddit: free, honest, threaded discussion; no key required
- Google Trends: free market-context signal; no key required
- Twitter/X: optional, recent search only, token required
- LinkedIn: optional, manual CSV import is the practical path

## API keys and local files

Environment variables:

- `YOUTUBE_API_KEY` - required for YouTube collection
- `TWITTER_BEARER_TOKEN` - optional
- `LINKEDIN_ACCESS_TOKEN` - optional and usually less useful than CSV import
- `GOOGLE_CLOUD_API_KEY` - optional, enables Timeseries Insights anomaly detection
- `GOOGLE_CLOUD_PROJECT` - required alongside `GOOGLE_CLOUD_API_KEY`

Support files:

- `.env.example` contains the expected environment variable names
- `.env` is local-only and should hold real secrets
- `instruction_template.yaml` is the manual starting point for new instruction files
- `input/linkedin_export.csv` is the expected LinkedIn CSV import path

## Instruction file requirements

The loader in `tools/config.py` requires:

- `project.name`
- `analysis.relevance_keywords`
- `analysis.categories`
- at least one enabled platform

Each category must include:

- `name`
- `description`
- `keywords`

Practical authoring notes:

- `priority_channels` entries for YouTube should be objects with `handle` and/or `name`
- Reddit is only useful when both `subreddits` and `search_queries` are populated
- Twitter search uses the provided `search_queries` plus `search_operators`
- Validation is optional and only produces `validation_report.md` when enabled

## Stage 2 - Run the pipeline

Typical commands:

```bash
python3 -m pip install -r requirements.txt
python3 tools/run.py --instruction instruction.yaml
```

Useful flags:

- `--dry-run` to inspect the execution plan
- `--platforms youtube,reddit` to override enabled platforms
- `--resume` to reuse checkpoints
- `--output-dir output_v2` to write into a different output directory
- `--skip-trends` to skip Google Trends

## What to inspect after a run

Primary outputs:

- `output/trend_report.md`
- `output/tsi_anomaly_report.md` when Timeseries Insights is enabled
- `output/summary_report.md`
- `output/quotable_excerpts.md`
- `output/summary_stats.json`
- `output/all_posts.csv`
- `output/validation_report.md` when validation is enabled

Checkpoint artifacts:

- `output/checkpoints/phase0_trends.json`
- `output/checkpoints/phase1_collection.json`
- `output/checkpoints/phase2_analysis.json`
- `output/checkpoints/phase3_reports.json`

## How to present results

When summarizing for the user:

1. Lead with the strongest real quotes from `quotable_excerpts.md`
2. Give the trend direction from Google Trends when available
3. Rank the top unmet-need categories by frequency
4. Compare which issues show up disproportionately on each platform
5. Call out any platform failures, auth problems, or quota limits
6. Offer a refinement loop: tighter categories, new queries, or deeper drilling

## Common failure modes

- Missing `YOUTUBE_API_KEY`: YouTube collection will fail fast
- Missing Reddit subreddits or queries: Reddit will skip with no data
- Twitter 401 or 403: invalid token or insufficient access tier
- Twitter 429 or Google Trends 429: rate limits; retry or rerun later
- Missing `GOOGLE_CLOUD_PROJECT`: TSI is skipped even if the API key is present
- LinkedIn: no public search API; use `input/linkedin_export.csv`
- Empty or noisy results: expand `relevance_keywords`, tighten categories, improve search seeds

## When to open ARCHITECTURE.md

Read `ARCHITECTURE.md` when you need:

- module-by-module responsibilities
- data flow and checkpoint behavior
- schema and dataclass details
- extension guidance for new platforms
- known limitations and edge cases

Keep this file focused on operation.
Keep deep internals in `ARCHITECTURE.md`.
