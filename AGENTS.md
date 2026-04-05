# AGENTS.md - Codex Runtime Instructions

This file is for Codex and similar repo-aware agents.
Use it as the runtime playbook for operating `unheard-buzz`.

Deep technical review material lives in `docs/ARCHITECTURE.md`.
Read that file when you need internals, debugging details, extension guidance, or review context.

## Mission

Help users run evidence-backed consulting cases that turn public signals into issue intelligence, benchmark context, contradictions, recommendations, review packs, and repeatable case memory.

## Default workflow

1. Clarify the case, decision objective, and workstreams.
2. Generate or update `instruction.yaml`.
3. Ensure `.env` contains the required API keys.
4. Run the pipeline with state/history when appropriate.
5. Read the generated issue, benchmark, decision, review, eval, and dashboard artifacts in `output/`.
6. Summarize findings by separating evidence, inference, recommendation, and open questions.

## Parallel agent posture

Once the brief is clear, prefer a small parallel swarm instead of a single monolithic agent.

- `source_scout` agent: expand channels, subreddits, search phrases, and benchmark sources
- `issue_analyst` agent: inspect `issue_registry.csv`, `evidence_registry.csv`, and `dashboard_data.json`
- `benchmark_analyst` agent: inspect `benchmark_coverage.json`, `contradiction_registry.csv`, and alternatives
- `skeptic` agent: challenge recommendation quality, contradiction handling, and evidence sufficiency
- `writer` agent: draft the user-facing memo with clear evidence/inference/recommendation separation
- `reviewer` agent: use `annotation_pack.csv` and review guidelines
- `graphics` agent: optional polish role after built-in dashboards already exist

Keep one orchestrator agent responsible for `instruction.yaml`, `.env`, pipeline execution, case/workstream integrity, and final synthesis.
Start any graphics polish only after the built-in dashboards and decision artifacts already exist.
Prefer the built-in executive and analyst dashboards over bespoke charts unless the user explicitly needs export polish.

## Stage 1 - Interview

Collect these inputs conversationally:

1. What case are we running, and what decision should it support?
2. Which workstreams matter: unmet needs, benchmark comparison, skeptic review, ICP/segment analysis, or follow-up validation?
3. Which platforms and source classes should we search?
4. Which API keys are already available?
5. What unmet-need categories, segments, or benchmark entities should we prioritize?

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

Checkpoint artifacts:

- `output/checkpoints/phase0_trends.json`
- `output/checkpoints/phase1_collection.json`
- `output/checkpoints/phase2_analysis.json`
- `output/checkpoints/phase3_reports.json`

## How to present results

When summarizing for the user:

1. Lead with the strongest real evidence and short quotes.
2. State the top issues and what benchmarks or contradictions say about them.
3. Separate evidence from inference from recommendation.
4. Call out what changed vs prior runs when state/history exists.
5. Call out platform failures, auth problems, quota limits, or weak evidence coverage.
6. Offer the next review or validation loop, not just a new search loop.

## Common failure modes

- Missing `YOUTUBE_API_KEY`: YouTube collection will fail fast
- Missing Reddit subreddits or queries: Reddit will skip with no data
- Twitter 401 or 403: invalid token or insufficient access tier
- Twitter 429 or Google Trends 429: rate limits; retry or rerun later
- Missing `GOOGLE_CLOUD_PROJECT`: TSI is skipped even if the API key is present
- LinkedIn: no public search API; use `input/linkedin_export.csv`
- Empty or noisy results: expand `relevance_keywords`, tighten categories, improve search seeds

## When to open docs/ARCHITECTURE.md

Read `docs/ARCHITECTURE.md` when you need:

- module-by-module responsibilities
- data flow and checkpoint behavior
- schema and dataclass details
- extension guidance for new platforms
- known limitations and edge cases

Read `docs/GRAPHICS_AGENT.md` when you need:

- chart-selection guidance
- Sankey-specific configuration notes
- styling rules for presentation-ready visuals
- output conventions for `output/visualizations/`

Keep this file focused on operation.
Keep deep internals in `docs/ARCHITECTURE.md`.


## v4 Operating update

For consulting-grade runs, default to treating RSS and GitHub Issues as benchmark-strength evidence when configured, and emphasize issue/evidence/benchmark/decision/review outputs in final synthesis.
