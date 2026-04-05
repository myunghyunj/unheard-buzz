# Master Gap Matrix

Audit target: the master-program bundle in `/Users/myunghyunjeong/Downloads/unheard-buzz-master-program-bundle.zip`

Repo snapshot reviewed:
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `instruction_template.yaml`
- `docs/ARCHITECTURE.md`
- `docs/README.md`
- `examples/README.md`
- `tools/`
- `tests/`

Status legend:
- `Strong Partial`: substantial implementation exists, but the program contract is still incomplete
- `Partial`: meaningful building blocks exist, but core parts of the domain are still missing
- `Weak Partial`: isolated hooks exist, but the domain is not yet first-class
- `Missing`: the repo does not yet have a first-class implementation or contract for this domain
- `Contract Drift`: the code and the public story materially disagree

## Executive Read

The repo is no longer just a social-listening pipeline. The codebase already contains:
- issue/evidence intelligence
- benchmark and contradiction handling
- decision outputs
- review/eval outputs
- persistent state and run history
- self-contained dashboards

The biggest remaining gap is coherence, not raw capability.

The highest-leverage next moves are:
1. sync the public contract across `README.md`, `AGENTS.md`, `CLAUDE.md`, examples, and the instruction template
2. introduce first-class `case` and `workstream` objects
3. add schema/artifact versioning to all major machine-readable outputs
4. define a machine-readable agent control plane instead of leaving orchestration as prose only
5. harden governance, retention, and source-use policy so the repo can be operated repeatedly and credibly

## Matrix

| # | Domain | Status | Current repo evidence | Main gap | Highest-leverage next step |
|---:|---|---|---|---|---|
| 1 | repo contract and public framing | Contract Drift | `README.md`, `AGENTS.md`, `CLAUDE.md` still sell an agent-first social-listening toolkit; `docs/ARCHITECTURE.md` already describes issue/entity/benchmark/decision/review/history outputs | Top-level docs, runtime guidance, and examples still undersell the actual product boundary | Rewrite root docs and examples around the "agent-code hybrid consultant" contract |
| 2 | case / workstream model | Missing | `instruction_template.yaml` has a strong `project` brief, but there is no case object, workstream registry, or workstream status model in `tools/config.py` or `tools/run.py` | No first-class way to scope one consulting case into multiple tracked workstreams | Add `case` and `workstreams` config plus `case_plan.md`, `workstream_registry.json`, and `workstream_status.md` |
| 3 | schema / artifact versioning | Missing | Deterministic IDs and `run_manifest.json` exist in `tools/issue_intelligence.py`, `tools/state_store.py`, and `tools/run.py` | No `schema_version` fields, compatibility policy, or migration notes for artifact evolution | Version the core objects and emit schema versions in manifests and key JSON/CSV artifacts |
| 4 | persistent state and longitudinal memory | Strong Partial | `tools/state_store.py`, `tools/history.py`, `tests/test_state_store.py`, `tests/test_history_diff.py` | State is still optional, lifecycle states are not explicit, reviewer decisions do not persist back into memory, and retention/compaction rules are undocumented | Promote stateful runs to the default consultant path and add lifecycle labels plus retention policy |
| 5 | source system and provenance hardening | Partial | `tools/config.py` source policy, collector independence keys, `source_registry_enriched.csv`, `tools/benchmark_pack.py`, `tests/test_source_policy.py` | No uniform connector contract for provenance fingerprint, collection timestamp, extraction notes, or allowed-use policy; high-value source classes are still incomplete | Standardize a connector output contract and document allowed discovery/corroboration/final-support source use |
| 6 | extraction / clustering quality | Partial | `tools/issue_intelligence.py` extracts problem statements, business consequences, specificity, extraction quality, and score penalties | Clustering is still deterministic heuristic grouping; merge/split review and explicit uncertainty tags are not first-class | Add extraction flags and a reviewer-facing merge/split workflow on top of current deterministic clustering |
| 7 | scoring / ranking redesign | Strong Partial | Config-driven issue scoring in `tools/issue_intelligence.py`, decision scoring in `tools/decision_engine.py`, tests in `tests/test_scoring_matrix.py` | Public docs still teach a stale score story; counterfactual ranking tests and recommendation-burden scoring are still missing | Sync scoring docs and add sensitivity/counterfactual tests plus recommendation-feasibility dimensions |
| 8 | entity / market map layer | Partial | `tools/entities.py`, `entity_registry.csv`, `issue_entity_links.csv`, `alternatives_matrix.csv`, `segment_pain_matrix.csv`, `tests/test_entities.py` | Entity taxonomy is still narrow and no whitespace map or competitor concentration view exists | Expand entity coverage and add market-map outputs such as whitespace and competitor concentration matrices |
| 9 | contradiction / evidence courtroom | Partial | `tools/benchmark_pack.py`, `contradiction_registry.csv`, `tests/test_contradictions.py` | Contradictions are surfaced, but there is no prosecution/defense/operator brief, claim graph, or veto logic for blocked recommendations | Add an evidence-courtroom artifact and claim graph with contradiction-based confidence veto rules |
| 10 | decision engine 2.0 | Partial | `tools/decision_engine.py`, `tools/opportunity_briefs.py`, `decision_memo.md`, `opportunity_map.csv`, `recommendation_cards.json`, `tests/test_decision_engine.py` | The repo now recommends, but it does not yet produce conservative/balanced/high-upside portfolios or strong alternatives/tradeoff structures | Extend recommendation generation into scenario portfolios and explicit tradeoff matrices |
| 11 | opportunity briefs and deliverables | Partial | `decision_memo.md`, `opportunity_map.csv`, `hypothesis_backlog.csv`, `research_questions.md`, `recommendation_cards.json` | No dedicated issue brief or opportunity brief artifacts and no slide-ready packaging contract | Add per-issue and per-opportunity brief artifacts in both Markdown and JSON |
| 12 | research frontier / active-learning loop | Weak Partial | `research_questions.md`, `annotation_pack.csv`, reviewer overrides in `tools/review_pack.py` | There is no frontier map, no query/backfill suggestions, and reviewer override memory is not reused in future runs | Add a frontier artifact for weak coverage and persist reviewer corrections for future clustering/ranking |
| 13 | evaluation / annotation / regression discipline | Strong Partial | `tools/eval.py`, `tools/review_pack.py`, `tests/test_eval_metrics.py`, `tests/test_review_pack.py`, targeted unit tests across scoring/state/contradictions | Good unit-level coverage exists, but curated gold fixtures and artifact completeness scoring are still missing | Add snapshot fixtures and regression comparisons for key artifact packs and ranking shifts |
| 14 | multilingual / regional expansion | Weak Partial | `analysis.language_allowlist` in `instruction_template.yaml`, some README caveats, limited language hooks in collectors | No locale-aware query generation, multilingual alias routing, or region-specific evaluation fixtures | Add locale config, alias routing, and region-specific fixture packs before expanding claims |
| 15 | visualization / analyst UI | Partial | `tools/visualizations.py`, `output/visualizations/executive_dashboard.html`, `output/visualizations/analyst_drilldown.html`, `tests/test_visualizations_smoke.py` | Useful dashboards exist, but contradiction-specific views, consistency checks, and cleaner export discipline are still thin | Add a benchmark-contradiction analyst view and numerical consistency checks across memo/dashboard exports |
| 16 | first-class agent control plane | Missing | `AGENTS.md` and `CLAUDE.md` define role ideas, but only as prose | No machine-readable role registry, handoff schema, budgets, stop conditions, permissions, or audit trail | Introduce a machine-readable agent plan with role contracts, budgets, and handoff rules |
| 17 | developer ergonomics / ops | Partial | `tools/run.py` supports `--dry-run` and `--resume`; validation scripts exist; tests are broad | No dedicated config lint, no migration/changelog discipline, and the dry-run contract does not fully preview coverage risk | Add a config-lint command and richer dry-run warnings for missing evidence classes, weak source mix, and contract gaps |
| 18 | governance / safety / compliance hygiene | Weak Partial | `source_policy` exists in config and README has some caveats | No explicit source-terms matrix, sensitive-data policy for manual imports, use-case restrictions, or confidence communication guide | Add governance docs for source terms, manual/private inputs, sensitive data, and high-risk recommendation gating |
| 19 | packaging / examples / user guide | Partial | `examples/README.md`, sample YAMLs, sample output bundle, `docs/README.md` | Examples still read like the older workflow and there is no single artifact guide or consultant-mode preset set | Add a user-facing artifact guide and modern example cases that demonstrate state/history/benchmark/decision/review loops |
| 20 | master acceptance criteria | Missing | The bundle contains acceptance criteria, but the repo does not track them locally | No repo-local release gate that says when the modern contract is actually complete | Add a tracked master readiness checklist and make validation scripts map to those gates |

## Domain Notes

### Strong footing already exists

These domains already have meaningful implementation and should be treated as foundations rather than greenfield work:
- persistent state and longitudinal memory
- scoring and ranking redesign
- evaluation / annotation / regression discipline

### Most urgent contract drift

These domains are the most urgent because they currently make the repo harder to understand than it needs to be:
- repo contract and public framing
- schema / artifact versioning
- first-class agent control plane
- packaging / examples / user guide

### Best next implementation sequence

If the goal is maximum leverage with minimal repo churn, the next sequence should be:
1. contract sync across `README.md`, `AGENTS.md`, `CLAUDE.md`, `instruction_template.yaml`, and examples
2. case/workstream schema
3. schema versioning and manifest hardening
4. agent control plane
5. governance + retention + source-use documentation

## Suggested Follow-On Deliverables

After this matrix, the next reviewable artifacts should be:
- `docs/CONTRACT_SYNC_PLAN.md`
- `docs/CASE_AND_WORKSTREAM_SCHEMA.md`
- `docs/ARTIFACT_VERSIONING_POLICY.md`
- `docs/AGENT_CONTROL_PLANE.md`
- `docs/GOVERNANCE_AND_SOURCE_POLICY.md`
