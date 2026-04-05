# unheard-buzz 🐝

Unheard-Buzz is a local, stateful, agent-code hybrid consultant for unmet-need discovery, benchmark triangulation, contradiction review, and recommendation support.

The repo still starts from public evidence, but it no longer stops at "social listening."

The operating split is:

- 🧠 the agent handles scoping, workstream planning, interpretation, and review
- 🖥️ your local machine handles connectors, checkpoints, persistent state, artifact generation, and repeatable execution

That split matters because chat-only environments are weak at filesystem access, long jobs, and run-over-run memory. This repo is designed so the agent can stay conversational while the evidence, decisions, and review artifacts are generated locally and kept traceable over time.

## What this helps you do 🔍

Use it for questions like:

- 🦾 What do amputees actually complain about with prosthetics?
- ⚡ What do EV drivers dislike about public charging?
- 🐾 What frustrates pet owners about tele-vet services?
- 🎮 What unmet needs show up in indie game publishing communities?

You define a case, workstreams, platforms, and analysis schema in `instruction.yaml`, and the pipeline:

1. 📥 collects and normalizes evidence across platforms
2. 🔄 clusters posts into issue and evidence layers
3. 🧭 links issues to entities, benchmarks, and contradictions
4. 🎯 scores opportunity, confidence, and decision relevance
5. 📝 generates decision, review, history, and dashboard artifacts

## Before you start 🛠️

This repo works best on a local Mac terminal.

You should have:

- 🔧 Git
- 🐍 Python 3.9+
- 💻 a terminal app
- 🤖 optionally Claude Code or Codex if you want the repo to be operated conversationally

If Git is missing on macOS, run:

```bash
xcode-select --install
```

If Python 3 is missing and you use Homebrew:

```bash
brew install python
```

## Clone it locally on macOS 💻

```bash
git clone https://github.com/myunghyunj/unheard-buzz.git
cd unheard-buzz
python3 -m pip install -r requirements.txt
cp .env.example .env
cp instruction_template.yaml instruction.yaml
```

At this point the repo is ready for configuration.

## Agent files vs other docs 📂

The root intentionally keeps only the files that agents auto-discover:

- `README.md` for humans
- `AGENTS.md` for Codex and similar repo-aware agents
- `CLAUDE.md` for Claude Code and similar chat-first agents

Those files stay at the repo root on purpose.

Other docs are grouped separately:

- `docs/ARCHITECTURE.md` for deep technical reference
- `.github/CONTRIBUTING.md` for contribution workflow
- `.github/SECURITY.md` for the security policy
- `.github/CODE_OF_CONDUCT.md` for community expectations

## If you want Claude Code or Codex to drive the workflow 🤖

### Claude Code

```bash
claude
```

Then tell Claude what you want to research.

This repo already includes `CLAUDE.md`, so Claude has project instructions available immediately.

If your usual workflow includes `/init`, you can still run it, but it is optional here because the runtime instruction file already exists.

### Codex

```bash
codex
```

Then tell Codex what you want to research. **cf. I prefer using Codex.**

This repo already includes `AGENTS.md`, so Codex can pick up the repo instructions without extra setup.

## What to tell the agent 💬

You do not need to prebuild everything manually. A good starting prompt is enough.

Examples:

- `I want to understand what amputees complain about with prosthetics. Start with YouTube, Reddit, and Google Trends.`
- `I want to research EV charging pain points in the US. Help me generate instruction.yaml and tell me which API keys I need.`
- `I want to look for tele-vet complaints. Use Reddit and YouTube first, and keep the categories simple for the first run.`

Good prompts usually include:

- 🎯 what market or pain point you want to investigate
- 🌍 which geography matters, if any
- 📡 which platforms you want to search
- 🔑 whether you already have API keys
- 🗂️ whether you want the agent to generate categories for you

If you already know you want a multi-agent workflow, say so explicitly. For example:

- `Run this as a stateful consultant case and split into unmet-needs, benchmark, skeptic, and writer workstreams.`
- `After the pipeline finishes, use the built-in dashboards first, then let graphics refine export polish only if needed.`

## Parallel agent pattern 🧩

This repo works best with a small consultant team after the case brief is clear and the core artifacts exist.

- `orchestrator`: owns `instruction.yaml`, case scope, pipeline execution, and final synthesis
- `source_scout`: expands queries, connectors, and benchmark sources
- `issue_analyst`: interprets issue/evidence/entity outputs
- `benchmark_analyst`: inspects benchmark coverage and contradictions
- `skeptic`: stress-tests recommendations and confidence claims
- `writer`: turns the artifact pack into a client-ready memo
- `reviewer`: uses `annotation_pack.csv` and override inputs
- `graphics`: optional export-polish role after built-in dashboards already exist

The pipeline remains the execution backbone. Agents should prefer shared artifacts like `issue_registry.csv`, `benchmark_coverage.json`, `decision_memo.md`, `annotation_pack.csv`, and the built-in dashboards instead of recollecting evidence.
When state is enabled, prior reviewer overrides can also be reused as reviewer memory instead of starting every review loop from zero.

## API keys: what you need and where to get them 🔑

### Required for YouTube collection

Environment variable:

- `YOUTUBE_API_KEY`

Where to get it:

- Google Cloud Console credentials page: [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
- YouTube Data API v3 library page: [console.cloud.google.com/apis/library/youtube.googleapis.com](https://console.cloud.google.com/apis/library/youtube.googleapis.com)

Typical steps:

1. Create or select a Google Cloud project
2. Enable YouTube Data API v3
3. Create an API key
4. Paste it into `.env`

Example:

```bash
YOUTUBE_API_KEY=your_key_here
```

### Optional for Google Timeseries Insights anomaly detection

Environment variables:

- `GOOGLE_CLOUD_API_KEY`
- `GOOGLE_CLOUD_PROJECT`

Where to get it:

- Google Cloud Console: [console.cloud.google.com](https://console.cloud.google.com)
- Credentials page: [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)

This enables the optional post-collection anomaly step.

Example:

```bash
GOOGLE_CLOUD_API_KEY=your_google_cloud_key
GOOGLE_CLOUD_PROJECT=your-project-id
```

### Optional for Twitter/X 🐦

Environment variable:

- `TWITTER_BEARER_TOKEN`

Where to get it:

- X Developer portal: [developer.x.com](https://developer.x.com)
- Developer portal dashboard: [developer.x.com/en/portal/dashboard](https://developer.x.com/en/portal/dashboard)

Example:

```bash
TWITTER_BEARER_TOKEN=your_bearer_token
```

### Optional for LinkedIn 💼

Environment variable:

- `LINKEDIN_ACCESS_TOKEN`

Where to get it:

- LinkedIn Developer products: [developer.linkedin.com/product-catalog](https://developer.linkedin.com/product-catalog)

In practice, LinkedIn is often easier to use via manual CSV export rather than a live API flow.

### No key needed 🆓

- Reddit collection
- Google Trends via pytrends

## Put the keys into `.env` 🔐

After you create the keys, open `.env` and paste what you have.

Example:

```bash
YOUTUBE_API_KEY=your_key_here
TWITTER_BEARER_TOKEN=
LINKEDIN_ACCESS_TOKEN=
GOOGLE_CLOUD_API_KEY=
GOOGLE_CLOUD_PROJECT=
```

You can leave optional ones blank.

## First run options 🚀

### Option 1: Let the agent interview you and create `instruction.yaml` 🤖

Best if you are using Claude Code or Codex.

Start the agent inside the repo and say something like:

`I want to research EV charging pain points. Please interview me, generate instruction.yaml, check .env expectations, and prepare a dry run.`

### Option 2: Try the repo immediately with an example ⚡

```bash
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```

If that looks good, run the real pipeline:

```bash
python3 tools/run.py --instruction examples/amputee.yaml
```

### Option 3: Manual custom setup ✏️

Edit `instruction.yaml`, then run:

```bash
python3 tools/run.py --instruction instruction.yaml --dry-run
python3 tools/run.py --instruction instruction.yaml
```

## Useful controls in `instruction.yaml` ⚙️

These settings matter a lot in practice:

- `analysis.min_comment_words`
- `analysis.language_allowlist`
- `analysis.dedup_normalized_text`
- `analysis.dedup_min_chars`
- `analysis.include_irrelevant_in_stats`
- `analysis.segments`
- `reporting.quote_count`
- `reporting.max_cooccurrence_pairs`

They help keep the workflow practical on real, noisy internet data.

## How scoring works 📊

The repo still uses lightweight collector heuristics to keep collection practical, but the main ranking story is now issue-level.

Current scoring layers:

- `collector_score`
  - platform-local triage signal used during collection
  - helpful for quota efficiency, not the final consultant ranking

- `opportunity_score`
  - issue-level weighted score over severity, urgency, independent frequency, buyer intent, business impact, and strategic fit

- `confidence_score`
  - issue-level weighted score over source quality, corroboration, source diversity, recency, specificity, and extraction quality

- `priority_score`
  - final issue priority computed from opportunity and confidence
  - exposed as the backward-compatible alias `final_rank_score`

- `decision_score`
  - recommendation-oriented score that adds benchmark gap, switching friction, segment concentration, and history trend context

The important contract is:
- evidence is not the same as inference
- inference is not the same as recommendation
- recommendation confidence must stay bounded by provenance and contradiction coverage

## Outputs 📁

Typical outputs include:

- 📄 `trend_report.md`
- 📄 `summary_report.md`
- 📄 `decision_memo.md`
- 📄 `case_plan.md`
- 📄 `workstream_status.md`
- 📄 `quotable_excerpts.md`
- 📊 `all_posts.csv`
- 📊 `coded_posts.csv`
- 📊 `coded_comments.csv`
- 📊 `source_registry.csv`
- 📊 `issue_registry.csv`
- 📊 `evidence_registry.csv`
- 📊 `entity_registry.csv`
- 📊 `issue_entity_links.csv`
- 📊 `opportunity_map.csv`
- 📊 `segment_pain_matrix.csv`
- 📊 `hypothesis_backlog.csv`
- 📊 `annotation_pack.csv`
- 📊 `channel_registry.csv` when YouTube collection runs
- 📊 `video_registry.csv` when YouTube collection runs
- 📊 `summary_stats.json`
- 📊 `dashboard_data.json`
- 📊 `benchmark_coverage.json`
- 📊 `recommendation_cards.json`
- 📊 `workstream_registry.json`
- 📊 `agent_plan.json`
- 📊 `agent_execution_log.json`
- 📊 `agent_handoff_log.json`
- 📊 `artifact_inventory.json`
- 📊 `run_manifest.json`
- 📊 `history_summary.json`
- 📄 `history_diff.md`
- 📄 `annotation_guidelines.md`
- 📄 `eval_report.md`
- 📄 `validation_report.md`
- 📄 `tsi_anomaly_report.md` when the optional TSI step is enabled
- 🎨 `visualizations/executive_dashboard.html`
- 🎨 `visualizations/analyst_drilldown.html`

The HTML dashboards are built into the pipeline. Graphics export polish can still happen later, but the repo no longer depends on a placeholder post-run graphics step to have usable dashboards.

These are designed to be easy to inspect, share, and move into research notes, client memos, or slides.

## Sample visualization 📈

Below is a static preview from the amputee sample-output bundle.
The repo now also generates built-in HTML dashboards directly from `dashboard_data.json`.

![Amputee wish intensity donut](examples/amputee_sample_output/visualizations/wish_intensity_donut_clean.svg)

- A static preview is embedded above for quick scanning in the repo.
- The sample bundle also includes an interactive HTML version of the same chart.
- Additional chart guidance and a reusable generic Sankey starter with a concrete prosthetics example live in `docs/GRAPHICS_AGENT.md` and `examples/visualization_starters/`.

## Example topics 🗂️

Ready-made instruction examples live in `examples/`.

Included examples cover:

- 🦾 amputee prosthetic unmet needs
- ⚡ EV charging pain points
- ♿ wheelchair accessibility
- 🏠 smart home privacy
- 🐾 pet telehealth
- 🎮 indie game publishing
- 🐝 urban beekeeping
- 🍞 sourdough baking

There is also a packaged sample-output bundle for the amputee brief, including reports, coded exports, registries, checkpoints, and a standalone visualization. The `examples/visualization_starters/` folder holds reusable chart scaffolds for the graphics agent.

## Operational notes ⚠️

This workflow can be API- and rate-limit-heavy, especially on YouTube and Twitter/X.

Start narrow:

- 🎯 use smaller query sets
- 📉 use smaller collection quotas
- 🧪 run `--dry-run` first
- 💾 use checkpoint/resume when iterating

That usually gives better signal and makes debugging easier.

## Current strengths ✅

Unheard-Buzz is strongest today as a local consultant workbench for evidence-backed unmet-need analysis.

It already does a few things well:

- 🔄 cross-platform normalization into a shared `SocialPost` model
- 🧹 filtering, deduplication, and issue/evidence clustering
- 🧭 entity, benchmark, and contradiction layers
- 🎯 issue-level scoring plus recommendation-oriented decision scoring
- 📝 decision, review, and eval artifact generation
- 💾 persistent state, run manifests, and history diffs
- 📊 built-in executive and analyst dashboards

It is especially useful when the value comes from traced public evidence, not polished survey answers.

## What it is not 🚧

This repository is not:

- a fully autonomous strategy consultant
- a truth engine
- legal, compliance, or policy advice
- an unrestricted scraper
- a replacement for expert human review in sensitive domains

Current limitations still include:

- 🌐 multilingual and regional coverage is partial
- 🔌 source coverage is uneven across connector classes
- 🧠 clustering and contradiction handling still rely on deterministic heuristics
- ✏️ outcome quality still depends heavily on good case framing, source mix, and review discipline

## Project structure 🗂️

```text
unheard-buzz/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── ARTIFACT_GUIDE.md
│   ├── AGENT_CONTROL_PLANE.md
│   ├── GOVERNANCE_AND_SOURCE_POLICY.md
│   └── GRAPHICS_AGENT.md
├── .github/
│   ├── CONTRIBUTING.md
│   ├── SECURITY.md
│   ├── CODE_OF_CONDUCT.md
│   └── workflows/
├── instruction_template.yaml
├── examples/
│   └── visualization_starters/
├── scripts/
├── tools/
├── tests/
├── input/
└── output/
```

## Development checks 🧪

```bash
python3 -m py_compile tools/*.py
python3 -m unittest discover -s tests -v
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
bash scripts/run_master_validation.sh .
```

## Future plans 🌍

We are expanding toward broader regional and language coverage across communities in:

- 🇰🇷 Korea
- 🇯🇵 Japan
- 🇨🇳 China
- 🇷🇺 Russia
- 🇺🇸 the United States
- 🇪🇺 Europe

The important distinction is this:

- ✅ current multilingual support exists
- 🚧 production-grade multilingual coverage is still a roadmap item

## One-line summary 💡

Unheard-Buzz is a local, stateful, benchmark-aware consultant operating system for turning messy public evidence into issue intelligence, recommendations, review packs, and repeatable case memory.
