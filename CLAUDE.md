# CLAUDE.md - Claude Code Runtime Instructions

This file is for Claude Code and similar chat-first coding agents.
Use it as the runtime playbook for operating `unheard-buzz`.

Deep technical review material lives in `ARCHITECTURE.md`.
Open that file when you need internals, debugging details, data flow, or extension guidance.

## Mission

Help users discover unmet market needs by mining social media platforms and summarizing the findings in a way that is useful for product, GTM, and research decisions.

## Default workflow

1. Interview the user one question at a time.
2. Generate or update `instruction.yaml`.
3. Ensure `.env` contains the required API keys.
4. Run the pipeline.
5. Read the generated reports in `output/`.
6. Summarize findings with real user quotes first, then patterns and next steps.

## Stage 1 — Interview

Collect these inputs conversationally. Ask one question at a time. If the user is unsure, generate sensible defaults and keep moving.

### Q1: What do you want to investigate?

Get a clear description of the market, product, or topic. Probe for specifics:
- Target audience (who are the users?)
- Geography (global, US, specific city?)
- Time frame (recent trends, historical patterns?)

Examples of valid user inputs:
- "I want to know what amputees complain about with prosthetics"
- "I'm opening a restaurant in Manhattan — what are diners saying?"
- "What do EV owners hate about charging infrastructure?"
- "How do parents feel about kids' electric toothbrushes?"

### Q2: Which platforms should we search?

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

## What to inspect after a run

Primary outputs:
- `output/trend_report.md` — Google search interest direction
- `output/tsi_anomaly_report.md` — discussion volume spikes (if TSI enabled)
- `output/summary_report.md` — category rankings, platform comparison
- `output/quotable_excerpts.md` — best verbatim quotes
- `output/summary_stats.json` — machine-readable statistics
- `output/all_posts.csv` — every post collected (anonymized)
- `output/validation_report.md` — academic cross-reference (if enabled)

Checkpoints: `output/checkpoints/phase*.json`

## How to present results

When summarizing for the user:

1. **Lead with quotes.** Open with the 2-3 strongest verbatim quotes from `quotable_excerpts.md`. Real user words are more compelling than statistics.
2. **Trend direction.** "Interest in [topic] is rising/falling/stable, up X% year-over-year."
3. **Ranked categories.** Top 5 unmet-need categories by frequency.
4. **Platform comparison.** "Socket fit complaints appear 3x more on Reddit than YouTube" — which problems surface where?
5. **Anomalies** (if TSI ran). "Discussion about [category] spiked in [month]."
6. **Call out failures.** Be transparent about any platforms that failed, quota limits hit, or thin data.
7. **Offer refinement.** Ask if they want to adjust categories, add search terms, drill deeper into a specific finding, or re-run with different parameters.

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

## When to open ARCHITECTURE.md

Use `ARCHITECTURE.md` for:
- module-by-module responsibilities
- data flow and checkpoint behavior
- SocialPost schema and dataclass details
- extension guidance for new platforms
- known limitations and edge cases

When results are noisy, tune these first before rewriting categories:
- `analysis.min_comment_words`
- `analysis.language_allowlist`
- `analysis.dedup_normalized_text`
- `analysis.dedup_min_chars`
- `analysis.include_irrelevant_in_stats`
