# Architecture and Technical Reference

Deep-dive for code review, debugging, and extension.
This is not a runtime instruction file.

## System data flow

```text
instruction.yaml
      |
      v
tools/config.py -> load_instruction()
      |
      v
tools/run.py -> run_pipeline()
      |
      +--> Phase 0: tools/trends.py
      +--> Phase 1: platform runners in parallel
      |      |- tools/youtube.py
      |      |- tools/reddit.py
      |      |- tools/twitter.py
      |      `- tools/linkedin.py
      |
      +--> Phase 2: tools/analyzer.py
      +--> Phase 2b: tools/trends.py (optional TSI anomaly pass)
      |
      +--> Phase 3: tools/reports.py
              |- all_posts.csv
              |- issue_registry.csv
              |- evidence_registry.csv
              |- entity_registry.csv
              |- issue_entity_links.csv
              |- benchmark_coverage.json
              |- contradiction_registry.csv
              |- alternatives_matrix.csv
              |- decision_memo.md
              |- opportunity_map.csv
              |- segment_pain_matrix.csv
              |- hypothesis_backlog.csv
              |- research_questions.md
              |- recommendation_cards.json
              |- annotation_pack.csv
              |- annotation_guidelines.md
              |- eval_report.md
              |- ranking_stability.json
              |- benchmark_leakage_report.json
              |- summary_stats.json
              |- summary_report.md
              |- quotable_excerpts.md
              |- tsi_anomaly_report.md
              `- validation_report.md
      |
      +--> Phase 3a: tools/state_store.py + tools/history.py (optional)
      |       |- state/*.sqlite3|*.duckdb
      |       |- run_manifest.json
      |       |- history_diff.md
      |       `- history_summary.json
      |
      `--> Phase 3b: tools/visualizations.py (optional)
```

## Agent orchestration layer

The Python pipeline is the shared execution backbone.
Agent orchestration is now both:
- a runtime pattern
- a machine-readable contract emitted as `agent_plan.json`

```text
phase 3 output artifacts
      |
      +--> search agent -> benchmark lookups, query expansion notes, market context
      +--> analysis agent -> ranked findings, platform deltas, quantitative tables
      +--> writing agent -> brief, memo, summary, or deck-ready narrative
      `--> graphics agent -> output/visualizations/*.html|*.svg|*.png|*.ai
```

`tools/program_contract.py` emits the default case, workstream, and role plan so the consultant workflow is inspectable even before agent execution traces exist.
The graphics pass should be treated as optional export polish over shared outputs, not as another collector or as a requirement for useful dashboards.

## Core configuration model

`tools/config.py` defines the typed configuration layer:

- `Instruction` is the top-level parsed YAML object
- `YouTubeConfig`, `RedditConfig`, `TwitterConfig`, and `LinkedInConfig` hold platform-specific settings
- `ReportingConfig` controls quote count and report shaping
- `Instruction.enabled_platforms` is the single source of truth for which runners execute

Validation currently requires:

- `project.name`
- `analysis.relevance_keywords`
- `analysis.categories`
- at least one enabled platform

Each category must define `name`, `description`, and `keywords`.

Optional but high-leverage fields now include:

- `project.objectives`, `project.target_audiences`, `project.key_questions`, `project.decision_uses`
- `case.*` for first-class consulting case scoping
- `workstreams[]` for role ownership and handoff contracts
- `agent_control.*` for budgets, search permission, and escalation defaults
- `analysis.segments` for cross-segment comparison tables
- `reporting.quote_count`, `reporting.max_cooccurrence_pairs`, `reporting.top_category_limit`

## Shared post model

`SocialPost` is the normalized cross-platform record used after ingestion.

Important fields:

- identity: `post_id`, `platform`, `source_id`, `source_title`
- content: `author`, `text`, `timestamp`, `url`
- engagement: `like_count`, `reply_count`
- structure: `is_reply`, `parent_id`
- analysis: `is_relevant`, `categories`, `segments`, `has_wish`, `word_count`
- extras: `metadata`

Everything downstream of collection operates on `SocialPost`.

## Pipeline phases

### Phase 0 - Google Trends

Implemented in `tools/trends.py`.

- Uses up to the first five `relevance_keywords`
- Writes `trend_report.md`
- Returns per-keyword metrics, related queries, and regional data
- `tools/run.py` now passes the active `output_dir` into this phase
- Final pipeline summary derives one aggregate trend label from the per-keyword metrics

### Phase 1 - Collection

Implemented in `tools/run.py` with thin per-platform wrappers.

- Platform runners are loaded lazily
- Enabled runners execute in parallel via `ThreadPoolExecutor`
- Each runner returns `{posts, stats}` and may also return an `error`
- Failures are isolated so one platform can fail while others continue
- Results are checkpointed to `phase1_collection.json`

### Phase 2 - Unified analysis

Implemented in `tools/analyzer.py`.

Main steps:

1. drop short posts using `MIN_COMMENT_WORDS`
2. drop spam using platform-agnostic heuristics
3. mark relevance via literal keyword matching
4. mark wish/need language via regex patterns
5. assign zero or more category codes
6. assign zero or more segment codes

This phase is intentionally simple and config-driven.

### Phase 2b - Timeseries Insights anomaly detection

Implemented in `tools/trends.py`.

- Optional backend gated by `GOOGLE_CLOUD_API_KEY` and `GOOGLE_CLOUD_PROJECT`
- Runs after categorization so category labels are available as event dimensions
- Creates a temporary dataset, uploads timestamped relevant posts, queries anomalies, then deletes the dataset
- Writes `tsi_anomaly_report.md`

### Phase 3 - Report generation

Implemented in `tools/reports.py`.

Order of operations:

1. anonymize authors in-memory
2. write `all_posts.csv`
3. write coded exports (`coded_posts.csv`, legacy alias `coded_comments.csv`)
4. write `source_registry.csv`
5. optionally write YouTube registries (`channel_registry.csv`, `video_registry.csv`)
6. select and write `quotable_excerpts.md`
7. write issue intelligence exports (`issue_registry.csv`, `evidence_registry.csv`)
8. write entity and benchmark exports (`entity_registry.csv`, `issue_entity_links.csv`, `benchmark_coverage.json`, `contradiction_registry.csv`, `alternatives_matrix.csv`)
9. write decision outputs (`decision_memo.md`, `opportunity_map.csv`, `segment_pain_matrix.csv`, `hypothesis_backlog.csv`, `research_questions.md`, `recommendation_cards.json`)
10. write review and eval outputs (`annotation_pack.csv`, `annotation_guidelines.md`, `eval_report.md`, `ranking_stability.json`, `benchmark_leakage_report.json`, optional `reviewer_agreement_summary.json`)
11. write contract artifacts (`case_plan.md`, `workstream_registry.json`, `workstream_status.md`, `agent_plan.json`, `agent_execution_log.json`, `agent_handoff_log.json`, `artifact_inventory.json`)
12. compute and write `summary_stats.json`
13. write `summary_report.md`
14. optionally write `validation_report.md`

### Phase 3a - Optional state store and history

Implemented in `tools/state_store.py` and `tools/history.py`.

- Additive to the existing file-based outputs
- Persists runs, posts, issues, evidence, sources, issue run metrics, entities, issue-entity links, benchmark documents, benchmark claims, contradiction records, and reviewer decisions
- Supports local persistence with SQLite by default and DuckDB when available
- Writes `run_manifest.json`
- Writes `history_diff.md` and `history_summary.json` when history is enabled
- Makes issue lifecycle state explicit and allows prior reviewer overrides to be retrieved on later runs
- Designed so reruns update deduplicated records instead of multiplying identical post/evidence rows

### Decision layer

Implemented by `tools/decision_engine.py` and `tools/opportunity_briefs.py`.

- Turns issue intelligence into evidence-linked recommendations
- Keeps recommendation IDs, supporting issue IDs, supporting evidence IDs, and benchmark context together
- Produces consultant-style artifacts without introducing a frontend build system

### Review and eval layer

Implemented by `tools/review_pack.py` and `tools/eval.py`.

- Exports spreadsheet-friendly annotation packs for issue, entity, contradiction, and recommendation review
- Supports optional reviewer overrides from `input/reviewer_annotations.csv`
- Computes ranking stability, provenance coverage, benchmark leakage, contradiction coverage, recommendation traceability, and reviewer override rate

### Phase 3b - Optional graphics handoff

Implemented in `tools/visualizations.py`.
This is a post-processing step that turns the generated outputs into charts and static presentation assets.

Typical inputs:

- `summary_stats.json`
- `all_posts.csv`
- `coded_posts.csv` or `coded_comments.csv`
- `summary_report.md`
- `quotable_excerpts.md`
- `trend_report.md`

Typical outputs:

- `output/visualizations/*.html`
- `output/visualizations/*.svg`
- `output/visualizations/*.png`
- `output/visualizations/*.ai` when an editable Illustrator master is needed

See `docs/GRAPHICS_AGENT.md` for chart selection and styling conventions.

### Phase 4 - Validation

Validation is lightweight.
It compares detected category rankings against the user-provided references in `instruction.yaml`.

## Module responsibilities

- `tools/config.py`: parse YAML, validate required fields, define dataclasses and constants
- `tools/run.py`: CLI entrypoint, orchestration, checkpoints, final summary
- `tools/program_contract.py`: case/workstream artifacts, role registry, and artifact inventory generation
- `tools/youtube.py`: channel discovery, video selection, comment extraction, quota tracking
- `tools/reddit.py`: subreddit search plus recursive comment traversal
- `tools/twitter.py`: Twitter recent-search ingestion with bearer-token auth and retry logic
- `tools/linkedin.py`: token check plus fallback to `input/linkedin_export.csv`
- `tools/analyzer.py`: spam filtering, relevance detection, wish tagging, category assignment, cross-platform insights
- `tools/reports.py`: CSV, JSON, markdown reports, quote selection, validation output
- `tools/decision_engine.py`: recommendation scoring, opportunity mapping, hypothesis generation
- `tools/opportunity_briefs.py`: memo and research-question rendering for decision outputs
- `tools/review_pack.py`: annotation pack export and reviewer override application
- `tools/eval.py`: review/eval metrics and audit-ready reports
- `tools/state_store.py`: local persistent warehouse for deduplicated run/post/issue/evidence state
- `tools/history.py`: run-over-run issue diffing and history artifact generation
- `tools/trends.py`: Google Trends context report and related-query analysis
- `tools/trends.py`: also hosts the optional Google Timeseries Insights anomaly backend

## Platform-specific notes

### YouTube

- Most complex collector in the repo
- Tracks quota costs internally and warns near the daily limit
- Discovery flow is channels -> videos -> comments
- Honors `priority_channels`, `search_queries`, and per-platform quota caps

### Reddit

- Uses the public JSON API, no OAuth flow here
- Searches each configured subreddit/query pair
- Deduplicates post IDs before fetching comments
- Traverses nested comment trees recursively

### Twitter

- Uses recent-search only
- Free-tier assumptions are built into logging and docs
- Handles 401, 403, and 429 explicitly

### LinkedIn

- Real API support is intentionally minimal
- Standard behavior is fallback to manual CSV import
- Expected CSV columns: `author`, `text`, `likes`, `date`, `url`

## Known limitations and review notes

- Transcript settings are parsed in `tools/config.py`, but there is no active transcript pipeline wired into `tools/youtube.py`
- Filtering uses literal keyword matching, so recall/precision depends heavily on the YAML keyword lists
- Category assignment is multi-label but purely keyword based
- Segment assignment is also keyword based, so segment comparisons are directional rather than canonical
- TSI anomaly quality depends on timestamp coverage and category labeling quality
- Quote selection favors relevant, high-scoring, category-covering posts; it is heuristic, not model-based
- Validation is comparison against user-supplied references, not independent academic retrieval
- Reviewer overrides currently adjust derived decision/eval outputs and audit summaries without mutating the underlying issue/evidence base tables
- Entity extraction and benchmark contradiction detection remain deterministic heuristics, so nuanced semantic matches may still need reviewer cleanup

## Error handling patterns

- platform auth failures are surfaced but non-fatal to the full run
- Google Trends failures degrade to `None` and skip trend reporting
- rate limits retry with waits in YouTube, Reddit, Twitter, and Trends
- missing platform config usually results in a skip rather than a crash

## Extension checklist for a new platform

1. add a new config dataclass in `tools/config.py`
2. extend `Instruction` and `enabled_platforms`
3. parse the new YAML block in `load_instruction()`
4. add a runner wrapper in `tools/run.py`
5. normalize the platform's native objects into `SocialPost`
6. ensure the runner returns `{posts, stats}` and isolates failures
7. update docs, templates, and examples

## Practical review targets

If you are reviewing changes, the highest-leverage places are:

- `tools/run.py` for orchestration and checkpoint behavior
- `tools/config.py` for schema drift and validation
- `tools/analyzer.py` for relevance and categorization changes
- `tools/reports.py` for user-facing output integrity
- platform modules for auth, rate-limit, and parsing edge cases


## v4 Issue intelligence extensions

- Added source policy/scoring/visualization config blocks in `instruction.yaml`.
- Added optional Tier-1/2 evidence collectors: `tools/rss.py` and `tools/github_issues.py`.
- Analyzer now keeps baseline filtering but appends an issue/evidence layer for canonical issue IDs and provenance-backed scoring (`opportunity_score`, `confidence_score`, `priority_score`).
- `final_rank_score` is now a backward-compatible alias of issue priority.
- Report phase still emits legacy CSV/Markdown artifacts, and now also emits `issue_registry.csv`, `evidence_registry.csv`, `dashboard_data.json`, and `source_registry_enriched.csv`.
- Pipeline now includes **Phase 3b Visualizations** via `tools/visualizations.py` after report generation.
