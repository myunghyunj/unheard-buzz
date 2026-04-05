PROGRAM_CONTRACT_VERSION = "consultant-os.v1"

SCHEMA_VERSIONS = {
    "social_post": "1.0",
    "evidence_item": "1.0",
    "issue_cluster": "1.0",
    "entity_record": "1.0",
    "benchmark_record": "1.0",
    "recommendation": "1.0",
    "review_decision": "1.0",
    "history_snapshot": "1.0",
    "run_manifest": "1.0",
    "case_plan": "1.0",
    "workstream_registry": "1.0",
    "workstream_status": "1.0",
    "agent_plan": "1.0",
    "agent_execution_log": "1.0",
    "agent_handoff_log": "1.0",
    "artifact_inventory": "1.0",
    "recommendation_cards": "1.0",
    "opportunity_map": "1.0",
    "segment_pain_matrix": "1.0",
    "hypothesis_backlog": "1.0",
    "annotation_pack": "1.0",
    "reviewer_memory": "1.0",
    "summary_stats": "1.0",
    "dashboard_data": "1.0",
    "benchmark_coverage": "1.0",
    "ranking_stability": "1.0",
    "benchmark_leakage": "1.0",
    "reviewer_agreement": "1.0",
}


def schema_version(name: str, default: str = "1.0") -> str:
    return SCHEMA_VERSIONS.get(name, default)
