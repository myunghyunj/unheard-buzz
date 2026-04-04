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
      `--> Phase 3: tools/reports.py
              |- all_posts.csv
              |- summary_stats.json
              |- summary_report.md
              |- quotable_excerpts.md
              |- tsi_anomaly_report.md
              `- validation_report.md
```

## Agent orchestration layer

The Python pipeline is the shared execution backbone.
After phase 3 outputs exist, repo-aware agents are expected to branch into parallel interpretation and presentation work.

```text
phase 3 output artifacts
      |
      +--> search agent -> benchmark lookups, query expansion notes, market context
      +--> analysis agent -> ranked findings, platform deltas, quantitative tables
      +--> writing agent -> brief, memo, summary, or deck-ready narrative
      `--> graphics agent -> output/visualizations/*.html|*.svg|*.png|*.ai
```

This orchestration layer is a runtime pattern, not a first-class Python module.
The graphics pass should be treated as post-processing over shared outputs, not as another collector.

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
7. compute and write `summary_stats.json`
8. write `summary_report.md`
9. optionally write `validation_report.md`

### Phase 3b - Optional graphics handoff

Not yet implemented as a Python module.
This is an agent-driven post-processing step that turns the generated outputs into charts and static presentation assets.

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
- `tools/youtube.py`: channel discovery, video selection, comment extraction, quota tracking
- `tools/reddit.py`: subreddit search plus recursive comment traversal
- `tools/twitter.py`: Twitter recent-search ingestion with bearer-token auth and retry logic
- `tools/linkedin.py`: token check plus fallback to `input/linkedin_export.csv`
- `tools/analyzer.py`: spam filtering, relevance detection, wish tagging, category assignment, cross-platform insights
- `tools/reports.py`: CSV, JSON, markdown reports, quote selection, validation output
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
- There is no dedicated visualization generator in the Python pipeline yet; presentation charts are currently produced by agents from the saved outputs

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
