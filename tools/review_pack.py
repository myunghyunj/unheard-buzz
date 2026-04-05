import copy
import csv
import os
from collections import Counter, defaultdict
from typing import Dict, List


ANNOTATION_FIELDS = [
    "record_type",
    "record_id",
    "field",
    "override_value",
    "notes",
]


def load_reviewer_annotations(path: str = "input/reviewer_annotations.csv") -> List[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader]


def _annotation_index(annotations: List[dict]) -> Dict[str, List[dict]]:
    indexed: Dict[str, List[dict]] = defaultdict(list)
    for row in annotations:
        indexed[f"{row.get('record_type', '')}:{row.get('record_id', '')}"].append(row)
    return indexed


def apply_reviewer_overrides(
    issue_layer: dict,
    decision_pack: dict,
    entity_layer: dict,
    benchmark_pack: dict,
    annotations: List[dict],
) -> dict:
    overridden_issues = copy.deepcopy(issue_layer)
    overridden_decision = copy.deepcopy(decision_pack)
    overridden_entities = copy.deepcopy(entity_layer)
    overridden_benchmarks = copy.deepcopy(benchmark_pack)
    dismissed_contradictions = set()
    applied_counts: Counter = Counter()

    recommendations_by_id = {
        row.get("recommendation_id", ""): row
        for row in overridden_decision.get("recommendations", []) or []
        if row.get("recommendation_id")
    }
    links_by_key = {
        f"{row.get('canonical_issue_id', '')}|{row.get('entity_id', '')}|{row.get('link_type', '')}": row
        for row in overridden_entities.get("issue_entity_links", []) or []
    }
    issues_by_id = {
        getattr(issue, "canonical_issue_id", ""): issue
        for issue in overridden_issues.get("issues", []) or []
        if getattr(issue, "canonical_issue_id", "")
    }

    for annotation in annotations:
        record_type = annotation.get("record_type", "")
        record_id = annotation.get("record_id", "")
        field = annotation.get("field", "")
        override_value = annotation.get("override_value", "")

        if record_type == "recommendation" and record_id in recommendations_by_id and field == "confidence_label":
            recommendations_by_id[record_id]["confidence_label"] = override_value or recommendations_by_id[record_id]["confidence_label"]
            recommendations_by_id[record_id]["reviewer_override"] = {
                "field": field,
                "override_value": override_value,
                "notes": annotation.get("notes", ""),
            }
            applied_counts["recommendation"] += 1
            continue

        if record_type == "contradiction" and field == "status" and override_value == "false_positive":
            dismissed_contradictions.add(record_id)
            applied_counts["contradiction"] += 1
            continue

        if record_type == "entity_link" and record_id in links_by_key:
            links_by_key[record_id]["reviewer_override"] = {
                "field": field,
                "override_value": override_value,
                "notes": annotation.get("notes", ""),
            }
            if field == "entity_id" and override_value:
                links_by_key[record_id]["reviewed_entity_id"] = override_value
            applied_counts["entity_link"] += 1
            continue

        if record_type == "issue" and record_id in issues_by_id:
            setattr(issues_by_id[record_id], "reviewed_cluster_id", override_value)
            applied_counts["issue"] += 1

    if dismissed_contradictions:
        overridden_benchmarks["contradictions"] = [
            row
            for row in overridden_benchmarks.get("contradictions", []) or []
            if row.get("contradiction_id", "") not in dismissed_contradictions
        ]
        contradictions_by_issue: Dict[str, List[dict]] = defaultdict(list)
        for row in overridden_benchmarks.get("contradictions", []) or []:
            contradictions_by_issue[row.get("canonical_issue_id", "")].append(row)
        for recommendation in overridden_decision.get("recommendations", []) or []:
            issue_ids = recommendation.get("supporting_issue_ids", []) or []
            issue_contradictions = []
            for issue_id in issue_ids:
                issue_contradictions.extend(contradictions_by_issue.get(issue_id, []))
            benchmark_support = recommendation.get("benchmark_support", {}) or {}
            benchmark_support["contradiction_count"] = len(issue_contradictions)
            benchmark_support["summaries"] = [row.get("summary", "") for row in issue_contradictions[:3] if row.get("summary")]
            benchmark_support["right_evidence"] = [row.get("right_evidence", "") for row in issue_contradictions[:3] if row.get("right_evidence")]
            recommendation["benchmark_support"] = benchmark_support

    return {
        "issue_layer": overridden_issues,
        "decision_pack": overridden_decision,
        "entity_layer": overridden_entities,
        "benchmark_pack": overridden_benchmarks,
        "summary": {
            "annotation_count": len(annotations),
            "applied_counts": dict(applied_counts),
            "dismissed_contradictions": sorted(dismissed_contradictions),
            "override_rate": round(sum(applied_counts.values()) / max(1, len(annotations)), 4),
        },
    }


def write_review_pack(
    issue_layer: dict,
    entity_layer: dict,
    benchmark_pack: dict,
    decision_pack: dict,
    output_dir: str,
    annotations: List[dict],
) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    annotation_index = _annotation_index(annotations)
    rows = []
    evidence_ids_by_issue = {
        getattr(issue, "canonical_issue_id", ""): "|".join(getattr(issue, "evidence_ids", [])[:8])
        for issue in issue_layer.get("issues", []) or []
    }

    for issue in issue_layer.get("issues", []) or []:
        record_id = getattr(issue, "canonical_issue_id", "")
        override_rows = annotation_index.get(f"issue:{record_id}", [])
        rows.append(
            {
                "record_type": "issue",
                "record_id": record_id,
                "canonical_issue_id": record_id,
                "recommendation_id": "",
                "entity_id": "",
                "contradiction_id": "",
                "current_value": getattr(issue, "normalized_problem_statement", ""),
                "supporting_evidence_ids": evidence_ids_by_issue.get(record_id, ""),
                "reviewer_override": override_rows[0].get("override_value", "") if override_rows else "",
                "notes": override_rows[0].get("notes", "") if override_rows else "",
            }
        )

    for link in entity_layer.get("issue_entity_links", []) or []:
        record_id = f"{link.get('canonical_issue_id', '')}|{link.get('entity_id', '')}|{link.get('link_type', '')}"
        override_rows = annotation_index.get(f"entity_link:{record_id}", [])
        rows.append(
            {
                "record_type": "entity_link",
                "record_id": record_id,
                "canonical_issue_id": link.get("canonical_issue_id", ""),
                "recommendation_id": "",
                "entity_id": link.get("entity_id", ""),
                "contradiction_id": "",
                "current_value": link.get("canonical_name", ""),
                "supporting_evidence_ids": evidence_ids_by_issue.get(link.get("canonical_issue_id", ""), ""),
                "reviewer_override": override_rows[0].get("override_value", "") if override_rows else "",
                "notes": override_rows[0].get("notes", "") if override_rows else "",
            }
        )

    for contradiction in benchmark_pack.get("contradictions", []) or []:
        record_id = contradiction.get("contradiction_id", "")
        override_rows = annotation_index.get(f"contradiction:{record_id}", [])
        rows.append(
            {
                "record_type": "contradiction",
                "record_id": record_id,
                "canonical_issue_id": contradiction.get("canonical_issue_id", ""),
                "recommendation_id": "",
                "entity_id": contradiction.get("entity_id", ""),
                "contradiction_id": record_id,
                "current_value": contradiction.get("summary", ""),
                "supporting_evidence_ids": evidence_ids_by_issue.get(contradiction.get("canonical_issue_id", ""), ""),
                "reviewer_override": override_rows[0].get("override_value", "") if override_rows else "",
                "notes": override_rows[0].get("notes", "") if override_rows else "",
            }
        )

    for recommendation in decision_pack.get("recommendations", []) or []:
        record_id = recommendation.get("recommendation_id", "")
        override_rows = annotation_index.get(f"recommendation:{record_id}", [])
        rows.append(
            {
                "record_type": "recommendation",
                "record_id": record_id,
                "canonical_issue_id": "|".join(recommendation.get("supporting_issue_ids", [])),
                "recommendation_id": record_id,
                "entity_id": recommendation.get("target_entity", ""),
                "contradiction_id": "",
                "current_value": recommendation.get("confidence_label", ""),
                "supporting_evidence_ids": "|".join(recommendation.get("supporting_evidence_ids", [])),
                "reviewer_override": override_rows[0].get("override_value", "") if override_rows else "",
                "notes": override_rows[0].get("notes", "") if override_rows else "",
            }
        )

    annotation_pack_path = os.path.join(output_dir, "annotation_pack.csv")
    with open(annotation_pack_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_type",
                "record_id",
                "canonical_issue_id",
                "recommendation_id",
                "entity_id",
                "contradiction_id",
                "current_value",
                "supporting_evidence_ids",
                "reviewer_override",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    guidelines_lines = [
        "# Annotation Guidelines",
        "",
        "Use `record_type`, `record_id`, `field`, and `override_value` in `input/reviewer_annotations.csv`.",
        "",
        "## Supported corrections",
        "",
        "- `issue`: set a reviewer cluster identifier or corrected issue label in `override_value`.",
        "- `entity_link`: correct `entity_id` or mark linkage notes for the row.",
        "- `recommendation`: set `field=confidence_label` to override recommendation confidence.",
        "- `contradiction`: set `field=status` and `override_value=false_positive` to dismiss a benchmark contradiction.",
        "",
        "## Notes",
        "",
        "- Overrides update derived outputs only; base issue/evidence records are preserved.",
        "- Keep notes concise so audit trails remain readable.",
        "- Prefer correcting only the highest-impact rows first.",
    ]
    guidelines_path = os.path.join(output_dir, "annotation_guidelines.md")
    with open(guidelines_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(guidelines_lines))

    return {
        "annotation_pack_csv": annotation_pack_path,
        "annotation_guidelines_md": guidelines_path,
    }
