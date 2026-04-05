# Master Acceptance Checklist

Use this checklist before calling the repo contract “consultant-ready.”

## Contract coherence

- [ ] `README.md`, `AGENTS.md`, `CLAUDE.md`, examples, and architecture docs tell the same product story
- [ ] scoring docs no longer teach an outdated collector-score-only model

## Stateful operation

- [ ] repeated runs emit `run_manifest.json`
- [ ] repeated runs emit `history_diff.md`
- [ ] issue lifecycle transitions are visible in history outputs
- [ ] reviewer decisions can persist and be reused
- [ ] state/history remains traceable by case and run

## Traceability

- [ ] every top recommendation cites issue IDs
- [ ] every top recommendation cites evidence IDs
- [ ] contradictions remain visible

## Reviewability

- [ ] `annotation_pack.csv` exists
- [ ] `eval_report.md` exists
- [ ] reviewer overrides can be applied safely

## Agent readiness

- [ ] `agent_plan.json` exists
- [ ] `agent_execution_log.json` and `agent_handoff_log.json` exist
- [ ] workstream ownership is machine-readable
- [ ] stop conditions and budgets are documented

## Packaging

- [ ] examples demonstrate the modern workflow
- [ ] artifact guide exists
- [ ] machine-readable and markdown artifacts agree numerically where expected

## Governance

- [ ] source-use policy is documented
- [ ] manual/private input handling is documented
- [ ] confidence limits are communicated clearly
