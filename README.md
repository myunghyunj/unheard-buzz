# unheard-buzz 🐝

Unheard-Buzz is an agent-first social listening toolkit for mining unmet needs from public online conversations.

Most people expect an LLM to do everything inside the chat window.

This repository takes a different approach:

- **The LLM handles planning and orchestration**
- **Your machine handles internet access, API calls, local files, retries, and checkpoints**

That design is the point.

Online chat environments are often restricted. They may have limited network access, weak long-running execution, limited filesystem access, and poor recovery from rate limits or partial failures. Unheard-Buzz is built to run where those constraints are much weaker: **the user's own laptop or workstation**.

The result is a workflow where an agent can still feel conversational, while the real collection and processing happen in a local environment that can actually do the work.

## What it is

Unheard-Buzz helps you answer questions like:

- What do amputees actually complain about with prosthetics?
- What do EV drivers dislike about public charging?
- What frustrates pet owners about tele-vet services?
- What unmet needs show up in indie game publishing communities?

You define a topic, keywords, platforms, and category schema in `instruction.yaml`.

The pipeline then:

1. collects posts across platforms
2. normalizes them into a shared format
3. filters low-signal and near-duplicate content
4. scores relevance and category fit
5. generates report-ready outputs

## Why this repo is different

The special advantage of this codebase is not that the model is magically smarter.

The advantage is that it exploits the difference between:

- **what is blocked or constrained in an online LLM environment**
- **what is possible on the user's own machine**

That means the system can rely on capabilities that are hard to do well inside a normal chat interface:

- persistent API keys
- multi-step platform collection
- local caching and checkpoints
- rate-limit-aware retries
- CSV and Markdown artifact generation
- long-running collection jobs
- partial recovery after failures

In other words:

> **The LLM is the operator.**
>
> **The user's machine is the execution environment.**

That separation is the core product idea.

## How it works

The workflow is intentionally split in two layers.

### 1. Agent layer

Claude Code or Codex handles:

- topic clarification
- category design
- query planning
- instruction file generation
- orchestration of the pipeline
- interpretation of the results

### 2. Local execution layer

Your machine handles:

- platform API access
- internet requests
- retries and backoff
- checkpoint save/resume
- CSV and Markdown output
- local configuration and environment variables

This is why the repo works well as an **agent-operated toolkit**, not just a static Python script collection.

## Current strengths

Unheard-Buzz is strongest today as a **configurable workflow engine for unmet-need discovery**.

It already does a few things well:

- cross-platform normalization into a shared `SocialPost` model
- collector-level filtering and deduplication
- configurable category schemas
- relevance and category scoring
- report generation for summaries, quotes, and stats
- checkpoint-aware execution

It is especially useful when the value comes from **real user language**, not polished survey answers.

## What it is not yet

This repository is **not yet a full semantic intelligence stack**.

That means:

- multilingual understanding is still partial
- language handling is improving but not fully production-grade
- ranking is better than before, but still heuristic-heavy
- some platform adapters are stronger than others
- the system still depends heavily on good query design and category design

That is fine. The repo is already useful because the workflow is strong, even before every modeling layer is perfect.

## Outputs

The pipeline produces report-ready artifacts such as:

- `trend_report.md`
- `summary_report.md`
- `quotable_excerpts.md`
- `all_posts.csv`
- `summary_stats.json`
- `validation_report.md`
- `tsi_anomaly_report.md` (optional)

These outputs are designed to be easy to inspect, share, and move into research notes or slides.

## Example topics

Ready-made instruction examples live in `examples/`.

Included examples cover:

- amputee prosthetic unmet needs
- EV charging pain points
- wheelchair accessibility
- smart home privacy
- pet telehealth
- indie game publishing
- urban beekeeping
- sourdough baking

They are intentionally different from each other to show that the framework is general.

## Quick start

### With Claude Code

```bash
claude
# Then say what you want to research.
# Claude reads CLAUDE.md and drives the workflow.
```

### With Codex

```bash
codex
# Then say what you want to research.
# Codex reads AGENTS.md and drives the workflow.
```

### Manual run

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
cp instruction_template.yaml instruction.yaml
python3 tools/run.py --instruction instruction.yaml --dry-run
```

Then edit `instruction.yaml` and run the full pipeline.

## Useful analysis controls

A few settings matter a lot in practice:

- `analysis.min_comment_words`
- `analysis.language_allowlist`
- `analysis.dedup_normalized_text`
- `analysis.dedup_min_chars`
- `analysis.include_irrelevant_in_stats`

These controls help keep the workflow practical on real, noisy internet data.

## Operational notes

This workflow can be API- and rate-limit-heavy, especially on YouTube and Twitter/X.

Start narrow:

- smaller query sets
- smaller collection quotas
- `--dry-run` first
- checkpoint/resume when iterating

This usually gives better signal and makes debugging easier.

## Project structure

```text
unheard-buzz/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── ARCHITECTURE.md
├── instruction_template.yaml
├── examples/
├── tools/
│   ├── run.py
│   ├── config.py
│   ├── analyzer.py
│   ├── reports.py
│   ├── language.py
│   ├── trends.py
│   ├── youtube.py
│   ├── reddit.py
│   ├── twitter.py
│   └── linkedin.py
├── input/
└── output/
```

## Future plans 🌍

We are expanding toward broader regional and language coverage across communities in:

- Korea
- Japan
- China
- Russia
- the United States
- Europe

The important distinction is this:

- **current multilingual support exists**
- **production-grade multilingual coverage is still a roadmap item**

That line should stay clear.

## One-line summary

**Unheard-Buzz is not “an LLM that magically browses everything.”**
**It is an agent-driven research workflow that uses the user's own machine to do the internet-facing work that chat-only environments often cannot do well.**
