from collections import Counter, defaultdict
from typing import Dict, List, Optional


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _history_index(history_data: Optional[dict]) -> Dict[str, dict]:
    if not isinstance(history_data, dict):
        return {}
    return {
        row.get("canonical_issue_id", ""): row
        for row in history_data.get("issues", []) or []
        if row.get("canonical_issue_id")
    }


def _links_by_issue(entity_layer: dict) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for link in entity_layer.get("issue_entity_links", []) or []:
        buckets[link.get("canonical_issue_id", "")].append(link)
    return buckets


def _contradictions_by_issue(benchmark_pack: dict) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for row in benchmark_pack.get("contradictions", []) or []:
        buckets[row.get("canonical_issue_id", "")].append(row)
    return buckets


def _pick_targets(issue, links: List[dict]) -> dict:
    workflow = next((row for row in links if row.get("entity_type") == "workflow"), None)
    entity = next(
        (
            row
            for row in links
            if row.get("entity_type") in {"company", "product", "competitor", "role", "geography"}
        ),
        None,
    )
    return {
        "target_workflow": workflow.get("canonical_name", "") if workflow else "",
        "target_entity": entity.get("canonical_name", "") if entity else "",
    }


def _segment_distribution(issue, posts_by_id: Dict[str, object]) -> Dict[str, int]:
    counts: Counter = Counter()
    for post_id in issue.post_ids:
        post = posts_by_id.get(post_id)
        if not post:
            continue
        segments = getattr(post, "segments", []) or []
        if not segments:
            counts["unassigned"] += 1
        for segment in segments:
            counts[segment] += 1
    if not counts:
        for segment in issue.segment_codes or []:
            counts[segment] += 1
    return dict(counts)


def _score_dimensions(issue, links: List[dict], contradictions: List[dict], history_row: Optional[dict], posts_by_id: Dict[str, object]) -> dict:
    breakdown = issue.score_breakdown or {}
    opportunity_components = (breakdown.get("opportunity") or {}).get("components", {})
    confidence_components = (breakdown.get("confidence") or {}).get("components", {})
    penalties = (breakdown.get("penalties") or {}).get("items", {})
    segment_distribution = _segment_distribution(issue, posts_by_id)
    distribution_values = list(segment_distribution.values())
    total_segment_mentions = sum(distribution_values) or 1
    segment_concentration = 100.0 * max(distribution_values or [1]) / total_segment_mentions

    contradiction_types = {row.get("contradiction_type", "") for row in contradictions}
    benchmark_gap = 25.0
    if "complaint_vs_benchmark_claim" in contradiction_types:
        benchmark_gap += 35.0
    if "alternative_positive_signal" in contradiction_types:
        benchmark_gap += 25.0
    if "segment_severity_gap" in contradiction_types:
        benchmark_gap += 10.0

    competitor_signal = any(row.get("entity_type") == "competitor" for row in links)
    switching_friction = 45.0 if competitor_signal else 70.0
    if "alternative_positive_signal" in contradiction_types:
        switching_friction = max(30.0, switching_friction - 15.0)

    trend_direction = (history_row or {}).get("status_label", "no_history") or "no_history"
    trend_score_map = {
        "new": 75.0,
        "rising": 90.0,
        "stable": 55.0,
        "declining": 25.0,
        "disappeared": 0.0,
        "no_history": 50.0,
    }

    pain_intensity = (
        float(opportunity_components.get("severity", 0.0))
        + float(opportunity_components.get("business_impact", 0.0))
    ) / 2.0
    breadth_reach = _clamp(10.0 + issue.evidence_count * 8.0 + issue.independent_source_count * 14.0)
    urgency = float(opportunity_components.get("urgency", 0.0))
    evidence_quality = (
        float(confidence_components.get("source_quality", 0.0))
        + float(confidence_components.get("corroboration", 0.0))
        + float(confidence_components.get("specificity", 0.0))
        + float(confidence_components.get("extraction_quality", 0.0))
    ) / 4.0

    decision_score = _clamp(
        pain_intensity * 0.24
        + breadth_reach * 0.16
        + benchmark_gap * 0.14
        + (100.0 - switching_friction) * 0.10
        + urgency * 0.12
        + evidence_quality * 0.12
        + segment_concentration * 0.06
        + trend_score_map.get(trend_direction, 50.0) * 0.06
        + float(issue.priority_score) * 0.10
        - min(sum(float(value) for value in penalties.values()), 30.0) * 0.15
    )

    return {
        "pain_intensity": round(_clamp(pain_intensity), 2),
        "breadth_reach": round(_clamp(breadth_reach), 2),
        "benchmark_gap": round(_clamp(benchmark_gap), 2),
        "switching_friction": round(_clamp(switching_friction), 2),
        "urgency": round(_clamp(urgency), 2),
        "evidence_quality": round(_clamp(evidence_quality), 2),
        "segment_concentration": round(_clamp(segment_concentration), 2),
        "trend_direction": trend_direction,
        "trend_score": round(trend_score_map.get(trend_direction, 50.0), 2),
        "decision_score": round(decision_score, 2),
        "segment_distribution": segment_distribution,
    }


def _confidence_label(decision_score: float, confidence_score: float) -> str:
    blended = (decision_score * 0.55) + (confidence_score * 0.45)
    if blended >= 75.0:
        return "high"
    if blended >= 55.0:
        return "medium"
    return "low"


def _recommendation_type(issue, targets: dict, contradictions: List[dict]) -> str:
    contradiction_types = {row.get("contradiction_type", "") for row in contradictions}
    if targets.get("target_workflow"):
        return "workflow_fix"
    if "alternative_positive_signal" in contradiction_types:
        return "competitive_response"
    if "complaint_vs_benchmark_claim" in contradiction_types:
        return "trust_repair"
    return "product_fix"


def _benchmark_support(issue_id: str, contradictions: List[dict]) -> dict:
    relevant = [row for row in contradictions if row.get("canonical_issue_id") == issue_id]
    return {
        "contradiction_count": len(relevant),
        "summaries": [row.get("summary", "") for row in relevant[:3] if row.get("summary")],
        "right_evidence": [row.get("right_evidence", "") for row in relevant[:3] if row.get("right_evidence")],
    }


def _open_questions(issue, contradictions: List[dict], targets: dict, history_row: Optional[dict]) -> List[str]:
    questions = []
    if not issue.segment_codes:
        questions.append("Which buyer segment feels this most acutely?")
    if issue.independent_source_count < 2:
        questions.append("Can we corroborate this beyond the initial source thread?")
    if not contradictions:
        questions.append("What do benchmark sources or official materials claim about this workflow today?")
    if targets.get("target_entity") and not targets.get("target_workflow"):
        questions.append("Is the pain tied to the named entity or to a broader workflow problem?")
    if (history_row or {}).get("status_label") in {"new", "no_history"}:
        questions.append("Is this a new pattern or just newly observed because of current sampling?")
    return questions[:4]


def build_decision_package(
    issue_layer: dict,
    entity_layer: dict,
    benchmark_pack: dict,
    posts: Optional[List[object]] = None,
    history_data: Optional[dict] = None,
) -> dict:
    posts_by_id = {
        getattr(post, "post_id", ""): post
        for post in posts or []
        if getattr(post, "post_id", "")
    }
    evidence_by_issue: Dict[str, List[dict]] = defaultdict(list)
    for evidence in issue_layer.get("evidence", []) or []:
        evidence_by_issue[getattr(evidence, "canonical_issue_id", "")].append(
            {
                "evidence_id": getattr(evidence, "evidence_id", ""),
                "excerpt": getattr(evidence, "excerpt", ""),
                "source_family": getattr(evidence, "source_family", ""),
                "source_tier": getattr(evidence, "source_tier", 0),
                "url": getattr(evidence, "url", ""),
            }
        )

    links_by_issue = _links_by_issue(entity_layer)
    contradictions_by_issue = _contradictions_by_issue(benchmark_pack)
    history_index = _history_index(history_data)

    opportunity_rows = []
    segment_rows = []
    hypothesis_rows = []
    recommendations = []
    research_questions = []

    for rank, issue in enumerate(issue_layer.get("issues", []) or [], start=1):
        links = links_by_issue.get(issue.canonical_issue_id, [])
        contradictions = contradictions_by_issue.get(issue.canonical_issue_id, [])
        history_row = history_index.get(issue.canonical_issue_id)
        targets = _pick_targets(issue, links)
        dimensions = _score_dimensions(issue, links, contradictions, history_row, posts_by_id)
        recommendation_type = _recommendation_type(issue, targets, contradictions)
        supporting_evidence_ids = [
            row["evidence_id"]
            for row in evidence_by_issue.get(issue.canonical_issue_id, [])[:8]
            if row.get("evidence_id")
        ]
        benchmark_support = _benchmark_support(issue.canonical_issue_id, contradictions)
        open_questions = _open_questions(issue, contradictions, targets, history_row)
        target_segment = issue.segment_codes[0] if issue.segment_codes else "all_segments"
        confidence_label = _confidence_label(dimensions["decision_score"], float(issue.confidence_score))
        recommendation_id = f"REC-{rank:03d}"

        evidence_section = {
            "supporting_issue_ids": [issue.canonical_issue_id],
            "supporting_evidence_ids": supporting_evidence_ids,
            "provenance_snippets": list(issue.provenance_snippets or [])[:3],
            "benchmark_support": benchmark_support,
        }
        inference_section = {
            "problem_statement": issue.normalized_problem_statement,
            "priority_score": round(float(issue.priority_score), 2),
            "opportunity_score": round(float(issue.opportunity_score), 2),
            "confidence_score": round(float(issue.confidence_score), 2),
            "scoring_dimensions": dimensions,
        }
        recommendation_section = {
            "type": recommendation_type,
            "target_segment": target_segment,
            "target_entity": targets.get("target_entity", ""),
            "target_workflow": targets.get("target_workflow", ""),
            "next_action": (
                f"Prioritize a {recommendation_type.replace('_', ' ')} response for "
                f"{targets.get('target_workflow') or targets.get('target_entity') or issue.category_codes[0] if issue.category_codes else issue.canonical_issue_id}."
            ),
            "open_questions": open_questions,
        }

        recommendation = {
            "recommendation_id": recommendation_id,
            "recommendation_type": recommendation_type,
            "title": issue.normalized_problem_statement[:120],
            "target_segment": target_segment,
            "target_entity": targets.get("target_entity", ""),
            "target_workflow": targets.get("target_workflow", ""),
            "supporting_issue_ids": [issue.canonical_issue_id],
            "supporting_evidence_ids": supporting_evidence_ids,
            "benchmark_support": benchmark_support,
            "confidence_label": confidence_label,
            "open_questions": open_questions,
            "decision_score": dimensions["decision_score"],
            "evidence": evidence_section,
            "inference": inference_section,
            "recommendation": recommendation_section,
        }
        recommendations.append(recommendation)

        opportunity_rows.append(
            {
                "recommendation_id": recommendation_id,
                "canonical_issue_id": issue.canonical_issue_id,
                "problem_statement": issue.normalized_problem_statement,
                "target_segment": target_segment,
                "target_entity": targets.get("target_entity", ""),
                "target_workflow": targets.get("target_workflow", ""),
                "recommendation_type": recommendation_type,
                "priority_score": round(float(issue.priority_score), 2),
                "decision_score": dimensions["decision_score"],
                "pain_intensity": dimensions["pain_intensity"],
                "breadth_reach": dimensions["breadth_reach"],
                "benchmark_gap": dimensions["benchmark_gap"],
                "switching_friction": dimensions["switching_friction"],
                "urgency": dimensions["urgency"],
                "evidence_quality": dimensions["evidence_quality"],
                "segment_concentration": dimensions["segment_concentration"],
                "trend_direction": dimensions["trend_direction"],
                "supporting_issue_ids": "|".join(recommendation["supporting_issue_ids"]),
                "supporting_evidence_ids": "|".join(supporting_evidence_ids),
                "confidence_label": confidence_label,
            }
        )

        for segment_code, count in sorted(dimensions["segment_distribution"].items()):
            segment_rows.append(
                {
                    "segment_code": segment_code,
                    "canonical_issue_id": issue.canonical_issue_id,
                    "problem_statement": issue.normalized_problem_statement,
                    "priority_score": round(float(issue.priority_score), 2),
                    "decision_score": dimensions["decision_score"],
                    "evidence_count": count,
                    "recommendation_id": recommendation_id,
                }
            )

        hypothesis_rows.append(
            {
                "hypothesis_id": f"HYP-{rank:03d}",
                "recommendation_id": recommendation_id,
                "canonical_issue_id": issue.canonical_issue_id,
                "hypothesis_statement": (
                    f"If we address '{issue.normalized_problem_statement[:90]}', "
                    f"then {target_segment} users should see measurable pain reduction."
                ),
                "test_type": "customer_interview" if confidence_label != "high" else "prototype_validation",
                "priority_score": round(float(issue.priority_score), 2),
                "decision_score": dimensions["decision_score"],
                "supporting_issue_ids": "|".join(recommendation["supporting_issue_ids"]),
                "supporting_evidence_ids": "|".join(supporting_evidence_ids),
                "success_metric": "Fewer repeated complaints and stronger benchmark parity signal.",
            }
        )

        for question in open_questions:
            research_questions.append(
                {
                    "recommendation_id": recommendation_id,
                    "canonical_issue_id": issue.canonical_issue_id,
                    "question": question,
                }
            )

    opportunity_rows.sort(key=lambda row: (row["decision_score"], row["priority_score"]), reverse=True)
    recommendations.sort(key=lambda row: row["decision_score"], reverse=True)
    hypothesis_rows.sort(key=lambda row: row["decision_score"], reverse=True)
    segment_rows.sort(key=lambda row: (row["segment_code"], -row["decision_score"], row["canonical_issue_id"]))

    return {
        "recommendations": recommendations,
        "opportunity_map": opportunity_rows,
        "segment_pain_matrix": segment_rows,
        "hypothesis_backlog": hypothesis_rows,
        "research_questions": research_questions,
        "summary": {
            "top_recommendation_ids": [row["recommendation_id"] for row in recommendations[:5]],
            "top_issue_ids": [row["canonical_issue_id"] for row in opportunity_rows[:5]],
        },
    }
