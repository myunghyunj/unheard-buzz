import json
import os
from typing import Dict, List, Optional

from schema_versions import PROGRAM_CONTRACT_VERSION, schema_version
from state_store import LocalStateStore


def _classify_issue(current: Optional[dict], previous: Optional[dict]) -> tuple[str, float, str, str]:
    if current and not previous:
        current_independent = int(current.get("independent_source_count", 0) or 0)
        if current_independent >= 2:
            return "new", float(current.get("priority_score", 0.0) or 0.0), "emerging", "new issue with corroborating sources"
        return "new", float(current.get("priority_score", 0.0) or 0.0), "fragile", "new issue with limited corroboration"
    if previous and not current:
        return "disappeared", -float(previous.get("priority_score", 0.0) or 0.0), "dormant", "issue not observed in the current run"

    current_priority = float(current.get("priority_score", 0.0) or 0.0)
    previous_priority = float(previous.get("priority_score", 0.0) or 0.0)
    current_evidence = int(current.get("evidence_count", 0) or 0)
    previous_evidence = int(previous.get("evidence_count", 0) or 0)
    current_independent = int(current.get("independent_source_count", 0) or 0)
    previous_independent = int(previous.get("independent_source_count", 0) or 0)

    delta_priority = round(current_priority - previous_priority, 2)
    delta_evidence = current_evidence - previous_evidence
    delta_independent = current_independent - previous_independent

    if delta_priority >= 5.0 or delta_evidence > 0 or delta_independent > 0:
        if current_independent >= 2 and current_evidence >= 2:
            return "rising", delta_priority, "expanding", "priority or corroboration increased"
        return "rising", delta_priority, "emerging", "priority increased but corroboration is still limited"
    if delta_priority <= -5.0 or delta_evidence < 0 or delta_independent < 0:
        return "declining", delta_priority, "cooling", "priority or corroboration declined"
    if current_independent >= 2:
        return "stable", delta_priority, "sustained", "issue remains corroborated without major movement"
    return "stable", delta_priority, "fragile", "issue is stable but still lightly corroborated"


def _issue_diff_row(issue_id: str, current: Optional[dict], previous: Optional[dict]) -> dict:
    status_label, delta_vs_prev, lifecycle_state, transition_reason = _classify_issue(current, previous)
    source = current or previous or {}
    return {
        "canonical_issue_id": issue_id,
        "normalized_problem_statement": source.get("normalized_problem_statement", ""),
        "status_label": status_label,
        "lifecycle_state": lifecycle_state,
        "transition_reason": transition_reason,
        "delta_vs_prev": round(delta_vs_prev, 2),
        "current_evidence_count": int((current or {}).get("evidence_count", 0) or 0),
        "previous_evidence_count": int((previous or {}).get("evidence_count", 0) or 0),
        "current_independent_source_count": int((current or {}).get("independent_source_count", 0) or 0),
        "previous_independent_source_count": int((previous or {}).get("independent_source_count", 0) or 0),
        "current_priority_score": round(float((current or {}).get("priority_score", 0.0) or 0.0), 2),
        "previous_priority_score": round(float((previous or {}).get("priority_score", 0.0) or 0.0), 2),
    }


def compute_history_delta(
    store: LocalStateStore,
    *,
    project_id: str,
    run_id: str,
    lookback_runs: int,
) -> dict:
    previous_runs = store.recent_runs(project_id, lookback_runs, exclude_run_id=run_id)
    previous_run_id = previous_runs[0]["run_id"] if previous_runs else ""
    current_metrics = store.issue_metrics_for_run(project_id, run_id)
    previous_metrics = store.issue_metrics_for_run(project_id, previous_run_id) if previous_run_id else {}

    diff_rows = []
    issue_ids = sorted(set(current_metrics.keys()) | set(previous_metrics.keys()))
    for issue_id in issue_ids:
        diff_rows.append(
            _issue_diff_row(
                issue_id,
                current_metrics.get(issue_id),
                previous_metrics.get(issue_id),
            )
        )

    store.update_issue_run_metrics(project_id, run_id, diff_rows)

    counts: Dict[str, int] = {}
    lifecycle_counts: Dict[str, int] = {}
    for row in diff_rows:
        counts[row["status_label"]] = counts.get(row["status_label"], 0) + 1
        lifecycle_counts[row["lifecycle_state"]] = lifecycle_counts.get(row["lifecycle_state"], 0) + 1

    gainers = sorted(
        [row for row in diff_rows if row["delta_vs_prev"] > 0],
        key=lambda row: (-row["delta_vs_prev"], row["canonical_issue_id"]),
    )
    losers = sorted(
        [row for row in diff_rows if row["delta_vs_prev"] < 0],
        key=lambda row: (row["delta_vs_prev"], row["canonical_issue_id"]),
    )

    return {
        "schema_version": schema_version("history_snapshot"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "project_id": project_id,
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "lookback_runs": lookback_runs,
        "summary": counts,
        "lifecycle_summary": lifecycle_counts,
        "top_priority_gainers": gainers[:5],
        "top_priority_losers": losers[:5],
        "issues": diff_rows,
    }


def write_history_outputs(history_data: dict, output_dir: str, emit_diff_report: bool = True) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    outputs: Dict[str, str] = {}

    summary_path = os.path.join(output_dir, "history_summary.json")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(history_data, handle, indent=2, ensure_ascii=False)
    outputs["history_summary_json"] = summary_path

    if emit_diff_report:
        diff_path = os.path.join(output_dir, "history_diff.md")
        lines: List[str] = [
            "# History Diff",
            "",
            f"- Project ID: `{history_data.get('project_id', '')}`",
            f"- Current run: `{history_data.get('run_id', '')}`",
            f"- Previous run: `{history_data.get('previous_run_id', 'none') or 'none'}`",
            "",
            "## Summary",
            "",
        ]
        summary = history_data.get("summary", {})
        if summary:
            for label in ("new", "rising", "stable", "declining", "disappeared"):
                if label in summary:
                    lines.append(f"- {label}: {summary[label]}")
        else:
            lines.append("- No historical comparison available.")
        lifecycle_summary = history_data.get("lifecycle_summary", {})
        lines.extend(["", "## Lifecycle", ""])
        if lifecycle_summary:
            for label, count in sorted(lifecycle_summary.items()):
                lines.append(f"- {label}: {count}")
        else:
            lines.append("- No lifecycle transitions recorded.")
        lines.extend(
            [
                "",
                "## Issue Changes",
                "",
                "| Issue | Status | Lifecycle | Delta priority | Evidence now | Evidence prev | Independent now | Independent prev | Reason |",
                "|------|--------|-----------|---------------:|-------------:|--------------:|----------------:|-----------------:|--------|",
            ]
        )
        for issue in history_data.get("issues", []):
            lines.append(
                f"| {issue['canonical_issue_id']} | {issue['status_label']} | {issue.get('lifecycle_state', '')} | {issue['delta_vs_prev']:.2f} | "
                f"{issue['current_evidence_count']} | {issue['previous_evidence_count']} | "
                f"{issue['current_independent_source_count']} | {issue['previous_independent_source_count']} | "
                f"{issue.get('transition_reason', '')} |"
            )
        gainers = history_data.get("top_priority_gainers", []) or []
        if gainers:
            lines.extend(["", "## Top Movers Up", ""])
            for row in gainers:
                lines.append(
                    f"- `{row['canonical_issue_id']}`: +{row['delta_vs_prev']:.2f} ({row.get('lifecycle_state', 'n/a')})"
                )
        losers = history_data.get("top_priority_losers", []) or []
        if losers:
            lines.extend(["", "## Top Movers Down", ""])
            for row in losers:
                lines.append(
                    f"- `{row['canonical_issue_id']}`: {row['delta_vs_prev']:.2f} ({row.get('lifecycle_state', 'n/a')})"
                )
        with open(diff_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        outputs["history_diff_md"] = diff_path

    return outputs
