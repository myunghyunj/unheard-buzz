# Agent Control Plane

This repo now treats agent orchestration as a first-class contract, not just an informal runtime habit.

## Role registry

The default machine-readable role plan is emitted as `agent_plan.json`.
Execution-time traces are emitted as `agent_execution_log.json` and `agent_handoff_log.json`.

Default roles:
- `orchestrator`
- `source_scout`
- `issue_analyst`
- `benchmark_analyst`
- `skeptic`
- `operator`
- `writer`
- `graphics`
- `reviewer`

## Role contract

Each role should define:
- what it reads
- what it writes
- what permissions it has
- whether it may call external search
- time budget
- retry budget
- confidence threshold
- escalation triggers

## Workstream ownership

Workstreams are the handoff unit.

Each workstream should declare:
- `primary_agent_role`
- `fallback_role`
- `handoff_inputs`
- `handoff_outputs`
- `stop_conditions`

## Stop conditions

Typical stop conditions include:
- top issues have recommendation and evidence coverage
- benchmark contradictions are surfaced for the top recommendations
- review pack is ready for manual override
- no new high-confidence recommendation can be generated without additional evidence

## Budget guidance

Use defaults from `agent_control` in `instruction.yaml` unless a case overrides them.

Important budgets:
- time budget
- retry budget
- confidence threshold
- maximum parallel roles

## External search

External search should be allowed only when:
- configured by `agent_control.allow_external_search`
- the workstream role permits it
- the case does not exclude it

## Audit trail

The repo should preserve enough context to explain:
- which roles were planned
- which artifacts they were expected to read and write
- what escalation triggers were active
- which workstream handoffs were completed or still partial

Today the contract is emitted in `agent_plan.json` and paired with lightweight local execution/handoff traces.
