#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

echo "[1/4] Python syntax check"
python3 -m py_compile tools/*.py tests/*.py

echo "[2/4] Full unit suite"
python3 -m unittest \
  tests.test_pipeline_contracts \
  tests.test_scoring_matrix \
  tests.test_source_policy \
  tests.test_issue_clustering \
  tests.test_dedup_and_corroboration \
  tests.test_visualizations_smoke \
  tests.test_state_store \
  tests.test_history_diff \
  tests.test_entities \
  tests.test_benchmark_pack \
  tests.test_contradictions \
  tests.test_decision_engine \
  tests.test_opportunity_briefs \
  tests.test_review_pack \
  tests.test_eval_metrics \
  tests.test_contract_artifacts

echo "[3/4] Dry-run sanity check"
python3 tools/run.py --instruction examples/amputee.yaml --dry-run >/tmp/unheard_buzz_master_dry_run.txt
sed -n '1,80p' /tmp/unheard_buzz_master_dry_run.txt

echo "[4/4] Checklist reminder"
echo "Review docs/MASTER_ACCEPTANCE_CHECKLIST.md before calling the contract ready."
