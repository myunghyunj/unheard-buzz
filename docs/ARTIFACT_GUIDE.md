# Artifact Guide

This guide explains the main artifact pack emitted by the modern consultant workflow.

## Core narrative artifacts

- `summary_report.md`
  - broad cross-platform narrative
  - best for quick human readout

- `decision_memo.md`
  - recommendation-focused memo
  - best for decision-makers and operators

- `research_questions.md`
  - unresolved questions and next evidence gaps
  - best for follow-up fieldwork

## Evidence and issue artifacts

- `issue_registry.csv`
  - canonical issue rows with scores and provenance snippets

- `evidence_registry.csv`
  - supporting evidence rows linked to issue IDs

- `source_registry_enriched.csv`
  - source family, tier, independence, and trust metadata

## Entity / benchmark artifacts

- `entity_registry.csv`
  - canonical entities extracted from issue context

- `issue_entity_links.csv`
  - typed issue-to-entity relationships

- `benchmark_coverage.json`
  - benchmark document and claim coverage summary

- `contradiction_registry.csv`
  - visible evidence conflicts

## Decision artifacts

- `opportunity_map.csv`
  - ranked recommendation-oriented opportunity rows

- `segment_pain_matrix.csv`
  - issue concentration by segment

- `hypothesis_backlog.csv`
  - validation-ready hypotheses linked to issue and evidence IDs

- `recommendation_cards.json`
  - machine-readable recommendation objects

## Review / eval artifacts

- `annotation_pack.csv`
  - spreadsheet-friendly review surface

- `annotation_guidelines.md`
  - override instructions for reviewers

- `eval_report.md`
  - compact quality and risk summary

- `ranking_stability.json`
  - run-over-run ranking movement

- `benchmark_leakage_report.json`
  - checks for benchmark contamination or misuse

- reviewer memory
  - persisted through the state store when reviewer overrides are supplied across repeated runs

## State / history artifacts

- `run_manifest.json`
  - execution and artifact manifest

- `artifact_inventory.json`
  - machine-readable list of emitted artifacts and versions

- `history_diff.md`
  - visible run-to-run issue changes

- `history_summary.json`
  - structured history change summary
  - includes lifecycle summaries and top movers

## Agent control artifacts

- `agent_plan.json`
  - machine-readable role and workstream contract

- `agent_execution_log.json`
  - lightweight execution trace of workstream ownership and completion status

- `agent_handoff_log.json`
  - machine-readable handoff record between orchestrator and role owners

## Visualization artifacts

- `output/visualizations/executive_dashboard.html`
- `output/visualizations/analyst_drilldown.html`

These are built-in dashboards, not placeholder post-processing scaffolds.
