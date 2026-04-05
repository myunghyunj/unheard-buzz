import json
import os
from typing import Dict, List, Optional


def build_eval_metrics(
    issue_layer: dict,
    benchmark_pack: dict,
    decision_pack: dict,
    history_data: Optional[dict] = None,
    review_summary: Optional[dict] = None,
) -> dict:
    recommendations = decision_pack.get("recommendations", []) or []
    issues = issue_layer.get("issues", []) or []
    contradictions = benchmark_pack.get("contradictions", []) or []
    benchmark_documents = benchmark_pack.get("benchmark_documents", []) or []
    history_rows = (history_data or {}).get("issues", []) or []

    recommendation_traceability = {
        "total_recommendations": len(recommendations),
        "with_issue_ids": sum(1 for row in recommendations if row.get("supporting_issue_ids")),
        "with_evidence_ids": sum(1 for row in recommendations if row.get("supporting_evidence_ids")),
    }
    recommendation_traceability["traceability_rate"] = round(
        min(
            recommendation_traceability["with_issue_ids"],
            recommendation_traceability["with_evidence_ids"],
        ) / max(1, recommendation_traceability["total_recommendations"]),
        4,
    )

    provenance_coverage = {
        "total_issues": len(issues),
        "issues_with_provenance": sum(1 for issue in issues if getattr(issue, "provenance_snippets", [])),
        "total_recommendations": len(recommendations),
        "recommendations_with_benchmark_support": sum(
            1 for row in recommendations if (row.get("benchmark_support") or {}).get("contradiction_count", 0) > 0
        ),
    }
    provenance_coverage["issue_provenance_rate"] = round(
        provenance_coverage["issues_with_provenance"] / max(1, provenance_coverage["total_issues"]),
        4,
    )

    contradiction_coverage = {
        "total_contradictions": len(contradictions),
        "issues_with_contradictions": len({row.get("canonical_issue_id", "") for row in contradictions if row.get("canonical_issue_id")}),
        "recommendations_with_contradictions": sum(
            1 for row in recommendations if (row.get("benchmark_support") or {}).get("contradiction_count", 0) > 0
        ),
    }

    ranking_stability = {
        "history_available": bool(history_rows),
        "compared_issue_count": len(history_rows),
        "rising_or_stable": sum(
            1 for row in history_rows if row.get("status_label") in {"new", "rising", "stable"}
        ),
        "volatile_or_declining": sum(
            1 for row in history_rows if row.get("status_label") in {"declining", "disappeared"}
        ),
        "issue_statuses": history_rows,
    }
    ranking_stability["stability_score"] = round(
        ranking_stability["rising_or_stable"] / max(1, ranking_stability["compared_issue_count"]),
        4,
    )

    leakage_items = [
        {
            "doc_id": row.get("doc_id", ""),
            "source_family": row.get("source_family", ""),
            "title": row.get("title", ""),
            "reason": "community_source_in_benchmark_pack",
        }
        for row in benchmark_documents
        if row.get("source_family") == "community"
    ]
    benchmark_leakage = {
        "total_benchmark_documents": len(benchmark_documents),
        "leakage_count": len(leakage_items),
        "leakage_rate": round(len(leakage_items) / max(1, len(benchmark_documents)), 4),
        "items": leakage_items,
        "dismissed_false_positive_count": len((review_summary or {}).get("dismissed_contradictions", []) or []),
    }

    reviewer_agreement = {
        "annotation_count": int((review_summary or {}).get("annotation_count", 0) or 0),
        "applied_counts": dict((review_summary or {}).get("applied_counts", {}) or {}),
        "override_rate": float((review_summary or {}).get("override_rate", 0.0) or 0.0),
    }

    return {
        "recommendation_traceability": recommendation_traceability,
        "provenance_coverage": provenance_coverage,
        "contradiction_coverage": contradiction_coverage,
        "ranking_stability": ranking_stability,
        "benchmark_leakage": benchmark_leakage,
        "reviewer_agreement": reviewer_agreement,
    }


def write_eval_outputs(
    issue_layer: dict,
    benchmark_pack: dict,
    decision_pack: dict,
    output_dir: str,
    history_data: Optional[dict] = None,
    review_summary: Optional[dict] = None,
) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    metrics = build_eval_metrics(
        issue_layer,
        benchmark_pack,
        decision_pack,
        history_data=history_data,
        review_summary=review_summary,
    )
    outputs: Dict[str, str] = {}

    ranking_stability_path = os.path.join(output_dir, "ranking_stability.json")
    with open(ranking_stability_path, "w", encoding="utf-8") as handle:
        json.dump(metrics["ranking_stability"], handle, indent=2, ensure_ascii=False)
    outputs["ranking_stability_json"] = ranking_stability_path

    benchmark_leakage_path = os.path.join(output_dir, "benchmark_leakage_report.json")
    with open(benchmark_leakage_path, "w", encoding="utf-8") as handle:
        json.dump(metrics["benchmark_leakage"], handle, indent=2, ensure_ascii=False)
    outputs["benchmark_leakage_report_json"] = benchmark_leakage_path

    if metrics["reviewer_agreement"]["annotation_count"] > 0:
        reviewer_agreement_path = os.path.join(output_dir, "reviewer_agreement_summary.json")
        with open(reviewer_agreement_path, "w", encoding="utf-8") as handle:
            json.dump(metrics["reviewer_agreement"], handle, indent=2, ensure_ascii=False)
        outputs["reviewer_agreement_summary_json"] = reviewer_agreement_path

    lines = [
        "# Eval Report",
        "",
        "## Ranking Stability",
        "",
        f"- Stability score: {metrics['ranking_stability']['stability_score']:.2f}",
        f"- Compared issues: {metrics['ranking_stability']['compared_issue_count']}",
        "",
        "## Provenance Coverage",
        "",
        f"- Issue provenance rate: {metrics['provenance_coverage']['issue_provenance_rate']:.2f}",
        f"- Recommendations with benchmark support: {metrics['provenance_coverage']['recommendations_with_benchmark_support']}",
        "",
        "## Recommendation Traceability",
        "",
        f"- Traceability rate: {metrics['recommendation_traceability']['traceability_rate']:.2f}",
        f"- Recommendations with issue IDs: {metrics['recommendation_traceability']['with_issue_ids']}",
        f"- Recommendations with evidence IDs: {metrics['recommendation_traceability']['with_evidence_ids']}",
        "",
        "## Benchmark Leakage",
        "",
        f"- Leakage count: {metrics['benchmark_leakage']['leakage_count']}",
        f"- Leakage rate: {metrics['benchmark_leakage']['leakage_rate']:.2f}",
        "",
        "## Contradiction Coverage",
        "",
        f"- Total contradictions: {metrics['contradiction_coverage']['total_contradictions']}",
        f"- Issues with contradictions: {metrics['contradiction_coverage']['issues_with_contradictions']}",
        "",
        "## Reviewer Overrides",
        "",
        f"- Annotation count: {metrics['reviewer_agreement']['annotation_count']}",
        f"- Override rate: {metrics['reviewer_agreement']['override_rate']:.2f}",
    ]
    eval_report_path = os.path.join(output_dir, "eval_report.md")
    with open(eval_report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    outputs["eval_report_md"] = eval_report_path

    return outputs
