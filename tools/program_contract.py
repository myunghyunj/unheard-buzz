import json
import os
import re
from typing import Dict, List, Optional

from config import Instruction
from schema_versions import PROGRAM_CONTRACT_VERSION, SCHEMA_VERSIONS, schema_version


DEFAULT_AGENT_ROLES = {
    "orchestrator": {
        "reads": ["instruction.yaml", "run_manifest.json", "workstream_registry.json"],
        "writes": ["case_plan.md", "workstream_status.md", "artifact_inventory.json"],
        "permissions": ["local_files", "pipeline_execution", "state_store"],
        "may_call_external_search": True,
        "default_outputs": ["summary_report.md", "decision_memo.md"],
    },
    "source_scout": {
        "reads": ["instruction.yaml", "history_summary.json", "benchmark_coverage.json"],
        "writes": ["source expansion notes", "benchmark source suggestions"],
        "permissions": ["connectors", "external_search_if_allowed"],
        "may_call_external_search": True,
        "default_outputs": ["source_registry_enriched.csv"],
    },
    "issue_analyst": {
        "reads": ["issue_registry.csv", "evidence_registry.csv", "dashboard_data.json"],
        "writes": ["issue summaries", "ranking notes"],
        "permissions": ["local_files"],
        "may_call_external_search": False,
        "default_outputs": ["issue_registry.csv", "dashboard_data.json"],
    },
    "benchmark_analyst": {
        "reads": ["benchmark_coverage.json", "contradiction_registry.csv", "alternatives_matrix.csv"],
        "writes": ["benchmark notes", "contradiction review"],
        "permissions": ["local_files", "external_search_if_allowed"],
        "may_call_external_search": True,
        "default_outputs": ["benchmark_coverage.json", "contradiction_registry.csv"],
    },
    "skeptic": {
        "reads": ["decision_memo.md", "recommendation_cards.json", "eval_report.md"],
        "writes": ["risk notes", "blocked recommendation review"],
        "permissions": ["local_files"],
        "may_call_external_search": False,
        "default_outputs": ["eval_report.md"],
    },
    "operator": {
        "reads": ["hypothesis_backlog.csv", "segment_pain_matrix.csv", "workstream_registry.json"],
        "writes": ["execution notes", "dependency notes"],
        "permissions": ["local_files"],
        "may_call_external_search": False,
        "default_outputs": ["hypothesis_backlog.csv"],
    },
    "writer": {
        "reads": ["decision_memo.md", "summary_report.md", "quotable_excerpts.md"],
        "writes": ["client-ready narrative", "briefs"],
        "permissions": ["local_files"],
        "may_call_external_search": False,
        "default_outputs": ["decision_memo.md", "summary_report.md"],
    },
    "graphics": {
        "reads": ["dashboard_data.json", "executive_dashboard.html", "analyst_drilldown.html"],
        "writes": ["presentation exports", "visual refinements"],
        "permissions": ["local_files"],
        "may_call_external_search": False,
        "default_outputs": ["output/visualizations/executive_dashboard.html", "output/visualizations/analyst_drilldown.html"],
    },
    "reviewer": {
        "reads": ["annotation_pack.csv", "annotation_guidelines.md", "eval_report.md"],
        "writes": ["reviewer_annotations.csv", "override notes"],
        "permissions": ["local_files", "manual_override"],
        "may_call_external_search": False,
        "default_outputs": ["annotation_pack.csv", "eval_report.md"],
    },
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def case_identity(instruction: Instruction) -> dict:
    case_id = instruction.case.case_id or _slug(instruction.project_name) or "default_case"
    case_name = instruction.case.case_name or instruction.project_name or case_id
    return {
        "case_id": case_id,
        "case_name": case_name,
    }


def normalized_workstreams(instruction: Instruction) -> List[dict]:
    workstreams = []
    for row in instruction.workstreams:
        if not row.enabled:
            continue
        workstream_id = row.workstream_id or _slug(row.name or row.objective or row.primary_agent_role) or "workstream"
        workstreams.append(
            {
                "schema_version": schema_version("workstream_registry"),
                "workstream_id": workstream_id,
                "name": row.name or workstream_id.replace("_", " ").title(),
                "objective": row.objective or "Undocumented workstream objective",
                "primary_agent_role": row.primary_agent_role or "issue_analyst",
                "fallback_role": row.fallback_role or "orchestrator",
                "handoff_inputs": list(row.handoff_inputs),
                "handoff_outputs": list(row.handoff_outputs),
                "stop_conditions": list(row.stop_conditions),
                "status": row.status or "planned",
            }
        )
    if workstreams:
        return workstreams
    return [
        {
            "schema_version": schema_version("workstream_registry"),
            "workstream_id": "unmet_needs",
            "name": "Unmet Needs",
            "objective": instruction.case.decision_objective or "Identify evidence-backed unmet needs and recommendation options.",
            "primary_agent_role": "issue_analyst",
            "fallback_role": "orchestrator",
            "handoff_inputs": ["issue_registry.csv", "evidence_registry.csv", "benchmark_coverage.json"],
            "handoff_outputs": ["decision_memo.md", "opportunity_map.csv"],
            "stop_conditions": ["Top issues have recommendation and evidence coverage."],
            "status": "planned",
        }
    ]


def build_case_payload(instruction: Instruction) -> dict:
    identity = case_identity(instruction)
    return {
        "schema_version": schema_version("case_plan"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        **identity,
        "client": instruction.case.client,
        "market_scope": instruction.case.market_scope or instruction.project_description,
        "geography": instruction.case.geography,
        "time_horizon": instruction.case.time_horizon,
        "decision_objective": instruction.case.decision_objective or ", ".join(instruction.project_decision_uses),
        "target_deliverables": list(instruction.case.target_deliverables or ["summary_report.md", "decision_memo.md"]),
        "allowed_sources": list(instruction.case.allowed_sources),
        "excluded_sources": list(instruction.case.excluded_sources),
        "risk_notes": list(instruction.case.risk_notes),
    }


def _resolve_artifact_specs(expected_names: List[str], generated_files: Dict[str, str]) -> List[dict]:
    resolved = []
    for name in expected_names:
        matched = []
        for artifact_key, path in generated_files.items():
            if name == artifact_key or name == os.path.basename(path):
                matched.append({"artifact_key": artifact_key, "path": path})
        resolved.append(
            {
                "requested_name": name,
                "matches": matched,
                "status": "available" if matched else "missing",
            }
        )
    return resolved


def write_contract_artifacts(
    instruction: Instruction,
    generated_files: Dict[str, str],
    output_dir: str,
    run_record: Optional[dict] = None,
) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    outputs: Dict[str, str] = {}
    case_payload = build_case_payload(instruction)
    workstreams = normalized_workstreams(instruction)

    case_lines = [
        f"# Case Plan — {case_payload['case_name']}",
        "",
        f"- Case ID: `{case_payload['case_id']}`",
        f"- Schema version: `{case_payload['schema_version']}`",
        f"- Program contract: `{case_payload['program_contract_version']}`",
        f"- Client / stakeholder: {case_payload['client'] or 'n/a'}",
        f"- Market scope: {case_payload['market_scope'] or 'n/a'}",
        f"- Geography: {case_payload['geography'] or 'n/a'}",
        f"- Time horizon: {case_payload['time_horizon'] or 'n/a'}",
        f"- Decision objective: {case_payload['decision_objective'] or 'n/a'}",
        "",
        "## Target Deliverables",
        "",
    ]
    case_lines.extend(f"- {item}" for item in case_payload["target_deliverables"])
    case_lines.extend(["", "## Allowed Sources", ""])
    if case_payload["allowed_sources"]:
        case_lines.extend(f"- {item}" for item in case_payload["allowed_sources"])
    else:
        case_lines.append("- Use the enabled connectors plus configured benchmark sources.")
    case_lines.extend(["", "## Excluded Sources", ""])
    if case_payload["excluded_sources"]:
        case_lines.extend(f"- {item}" for item in case_payload["excluded_sources"])
    else:
        case_lines.append("- No explicit exclusions declared.")
    case_lines.extend(["", "## Risk Notes", ""])
    if case_payload["risk_notes"]:
        case_lines.extend(f"- {item}" for item in case_payload["risk_notes"])
    else:
        case_lines.append("- Confidence should stay bounded by source quality and contradiction coverage.")
    case_lines.extend(["", "## Workstreams", ""])
    for workstream in workstreams:
        case_lines.append(f"### {workstream['workstream_id']} — {workstream['name']}")
        case_lines.append("")
        case_lines.append(f"- Objective: {workstream['objective']}")
        case_lines.append(f"- Primary role: {workstream['primary_agent_role']}")
        case_lines.append(f"- Fallback role: {workstream['fallback_role']}")
        case_lines.append(f"- Stop conditions: {', '.join(workstream['stop_conditions']) or 'n/a'}")
        case_lines.append("")
    case_plan_path = os.path.join(output_dir, "case_plan.md")
    with open(case_plan_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(case_lines))
    outputs["case_plan_md"] = case_plan_path

    workstream_registry = {
        "schema_version": schema_version("workstream_registry"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "case": case_payload,
        "workstreams": workstreams,
    }
    workstream_registry_path = os.path.join(output_dir, "workstream_registry.json")
    with open(workstream_registry_path, "w", encoding="utf-8") as handle:
        json.dump(workstream_registry, handle, indent=2, ensure_ascii=False)
    outputs["workstream_registry_json"] = workstream_registry_path

    status_lines = [
        "# Workstream Status",
        "",
        f"- Case: `{case_payload['case_id']}`",
        f"- Schema version: `{schema_version('workstream_registry')}`",
        "",
        "| Workstream | Primary role | Status | Stop conditions |",
        "|---|---|---|---|",
    ]
    for workstream in workstreams:
        status_lines.append(
            f"| {workstream['workstream_id']} | {workstream['primary_agent_role']} | {workstream['status']} | "
            f"{'; '.join(workstream['stop_conditions']) or 'n/a'} |"
        )
    workstream_status_path = os.path.join(output_dir, "workstream_status.md")
    with open(workstream_status_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(status_lines))
    outputs["workstream_status_md"] = workstream_status_path

    roles = []
    for role_name, role in DEFAULT_AGENT_ROLES.items():
        role_payload = dict(role)
        role_payload["role"] = role_name
        role_payload["schema_version"] = schema_version("agent_plan")
        role_payload["time_budget_minutes"] = instruction.agent_control.default_time_budget_minutes
        role_payload["retry_budget"] = instruction.agent_control.default_retry_budget
        role_payload["confidence_threshold"] = instruction.agent_control.default_confidence_threshold
        role_payload["may_call_external_search"] = bool(role_payload["may_call_external_search"] and instruction.agent_control.allow_external_search)
        role_payload["escalation_triggers"] = list(instruction.agent_control.escalation_triggers)
        roles.append(role_payload)

    agent_plan = {
        "schema_version": schema_version("agent_plan"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "case_id": case_payload["case_id"],
        "max_parallel_roles": instruction.agent_control.max_parallel_roles,
        "roles": roles,
        "workstream_ownership": [
            {
                "workstream_id": workstream["workstream_id"],
                "primary_agent_role": workstream["primary_agent_role"],
                "fallback_role": workstream["fallback_role"],
                "handoff_inputs": workstream["handoff_inputs"],
                "handoff_outputs": workstream["handoff_outputs"],
                "stop_conditions": workstream["stop_conditions"],
            }
            for workstream in workstreams
        ],
    }
    agent_plan_path = os.path.join(output_dir, "agent_plan.json")
    with open(agent_plan_path, "w", encoding="utf-8") as handle:
        json.dump(agent_plan, handle, indent=2, ensure_ascii=False)
    outputs["agent_plan_json"] = agent_plan_path

    role_index = {row["role"]: row for row in roles}
    execution_events = []
    handoff_events = []
    for workstream in workstreams:
        primary_role = workstream["primary_agent_role"]
        role_contract = role_index.get(primary_role, {})
        resolved_inputs = _resolve_artifact_specs(workstream["handoff_inputs"], generated_files)
        resolved_outputs = _resolve_artifact_specs(workstream["handoff_outputs"], generated_files)
        available_outputs = [
            item["requested_name"]
            for item in resolved_outputs
            if item["status"] == "available"
        ]
        missing_outputs = [
            item["requested_name"]
            for item in resolved_outputs
            if item["status"] != "available"
        ]
        status = "completed" if not missing_outputs else ("partial" if available_outputs else "planned")
        execution_events.append(
            {
                "event_id": f"{case_payload['case_id']}:{workstream['workstream_id']}:{primary_role}",
                "schema_version": schema_version("agent_execution_log"),
                "run_id": (run_record or {}).get("run_id", ""),
                "case_id": case_payload["case_id"],
                "workstream_id": workstream["workstream_id"],
                "role": primary_role,
                "status": status,
                "execution_mode": "local_pipeline",
                "time_budget_minutes": role_contract.get("time_budget_minutes"),
                "retry_budget": role_contract.get("retry_budget"),
                "confidence_threshold": role_contract.get("confidence_threshold"),
                "planned_inputs": workstream["handoff_inputs"],
                "resolved_inputs": resolved_inputs,
                "planned_outputs": workstream["handoff_outputs"],
                "resolved_outputs": resolved_outputs,
                "missing_outputs": missing_outputs,
                "stop_conditions": workstream["stop_conditions"],
                "escalation_triggers": role_contract.get("escalation_triggers", []),
            }
        )
        handoff_events.append(
            {
                "handoff_id": f"{case_payload['case_id']}:{workstream['workstream_id']}:orchestrator->{primary_role}",
                "schema_version": schema_version("agent_handoff_log"),
                "run_id": (run_record or {}).get("run_id", ""),
                "case_id": case_payload["case_id"],
                "workstream_id": workstream["workstream_id"],
                "from_role": "orchestrator",
                "to_role": primary_role,
                "input_contract": workstream["handoff_inputs"],
                "resolved_inputs": resolved_inputs,
                "expected_outputs": workstream["handoff_outputs"],
                "resolved_outputs": resolved_outputs,
                "status": status,
                "stop_conditions": workstream["stop_conditions"],
            }
        )

    agent_execution_log = {
        "schema_version": schema_version("agent_execution_log"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "case_id": case_payload["case_id"],
        "run_id": (run_record or {}).get("run_id", ""),
        "events": execution_events,
    }
    agent_execution_path = os.path.join(output_dir, "agent_execution_log.json")
    with open(agent_execution_path, "w", encoding="utf-8") as handle:
        json.dump(agent_execution_log, handle, indent=2, ensure_ascii=False)
    outputs["agent_execution_log_json"] = agent_execution_path

    agent_handoff_log = {
        "schema_version": schema_version("agent_handoff_log"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "case_id": case_payload["case_id"],
        "run_id": (run_record or {}).get("run_id", ""),
        "handoffs": handoff_events,
    }
    agent_handoff_path = os.path.join(output_dir, "agent_handoff_log.json")
    with open(agent_handoff_path, "w", encoding="utf-8") as handle:
        json.dump(agent_handoff_log, handle, indent=2, ensure_ascii=False)
    outputs["agent_handoff_log_json"] = agent_handoff_path

    artifact_inventory = {
        "schema_version": schema_version("artifact_inventory"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "case_id": case_payload["case_id"],
        "artifacts": [
            {
                "artifact_key": key,
                "path": path,
                "schema_version": SCHEMA_VERSIONS.get(key.replace("_json", "").replace("_md", "").replace("_csv", ""), "1.0"),
            }
            for key, path in sorted({**generated_files, **outputs}.items())
        ],
    }
    artifact_inventory_path = os.path.join(output_dir, "artifact_inventory.json")
    artifact_keys = {row["artifact_key"] for row in artifact_inventory["artifacts"]}
    if "artifact_inventory_json" not in artifact_keys:
        artifact_inventory["artifacts"].append(
            {
                "artifact_key": "artifact_inventory_json",
                "path": artifact_inventory_path,
                "schema_version": schema_version("artifact_inventory"),
            }
        )
    with open(artifact_inventory_path, "w", encoding="utf-8") as handle:
        json.dump(artifact_inventory, handle, indent=2, ensure_ascii=False)
    outputs["artifact_inventory_json"] = artifact_inventory_path

    return outputs
