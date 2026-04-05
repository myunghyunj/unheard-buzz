import csv
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List


def _write_csv(path: str, rows: List[dict], fallback_fields: List[str]) -> str:
    fieldnames = list(rows[0].keys()) if rows else fallback_fields
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _evidence_rows(issue_layer: dict) -> Dict[str, List[dict]]:
    rows: Dict[str, List[dict]] = defaultdict(list)
    for evidence in issue_layer.get("evidence", []) or []:
        rows[getattr(evidence, "canonical_issue_id", "")].append(
            {
                "evidence_id": getattr(evidence, "evidence_id", ""),
                "source_family": getattr(evidence, "source_family", ""),
                "source_tier": getattr(evidence, "source_tier", 0),
                "excerpt": getattr(evidence, "excerpt", ""),
                "url": getattr(evidence, "url", ""),
            }
        )
    return rows


def _issue_map(issue_layer: dict) -> Dict[str, object]:
    return {
        getattr(issue, "canonical_issue_id", ""): issue
        for issue in issue_layer.get("issues", []) or []
        if getattr(issue, "canonical_issue_id", "")
    }


def write_decision_outputs(
    decision_pack: dict,
    issue_layer: dict,
    benchmark_pack: dict,
    output_dir: str,
) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    outputs: Dict[str, str] = {}
    issues_by_id = _issue_map(issue_layer)
    evidence_by_issue = _evidence_rows(issue_layer)

    outputs["opportunity_map_csv"] = _write_csv(
        os.path.join(output_dir, "opportunity_map.csv"),
        decision_pack.get("opportunity_map", []),
        [
            "recommendation_id", "canonical_issue_id", "problem_statement", "target_segment",
            "target_entity", "target_workflow", "recommendation_type", "priority_score",
            "decision_score", "pain_intensity", "breadth_reach", "benchmark_gap",
            "switching_friction", "urgency", "evidence_quality", "segment_concentration",
            "trend_direction", "supporting_issue_ids", "supporting_evidence_ids", "confidence_label",
        ],
    )
    outputs["segment_pain_matrix_csv"] = _write_csv(
        os.path.join(output_dir, "segment_pain_matrix.csv"),
        decision_pack.get("segment_pain_matrix", []),
        [
            "segment_code", "canonical_issue_id", "problem_statement", "priority_score",
            "decision_score", "evidence_count", "recommendation_id",
        ],
    )
    outputs["hypothesis_backlog_csv"] = _write_csv(
        os.path.join(output_dir, "hypothesis_backlog.csv"),
        decision_pack.get("hypothesis_backlog", []),
        [
            "hypothesis_id", "recommendation_id", "canonical_issue_id", "hypothesis_statement",
            "test_type", "priority_score", "decision_score", "supporting_issue_ids",
            "supporting_evidence_ids", "success_metric",
        ],
    )

    recommendation_cards_path = os.path.join(output_dir, "recommendation_cards.json")
    with open(recommendation_cards_path, "w", encoding="utf-8") as handle:
        json.dump(decision_pack.get("recommendations", []), handle, indent=2, ensure_ascii=False)
    outputs["recommendation_cards_json"] = recommendation_cards_path

    question_lines = ["# Research Questions", ""]
    grouped_questions: Dict[str, List[str]] = defaultdict(list)
    for item in decision_pack.get("research_questions", []):
        grouped_questions[item.get("recommendation_id", "unassigned")].append(item.get("question", ""))
    for recommendation in decision_pack.get("recommendations", [])[:10]:
        rec_id = recommendation.get("recommendation_id", "")
        question_lines.append(f"## {rec_id} — {recommendation.get('title', '')}")
        question_lines.append("")
        for question in grouped_questions.get(rec_id, []) or recommendation.get("open_questions", []):
            if question:
                question_lines.append(f"- {question}")
        question_lines.append("")
    research_questions_path = os.path.join(output_dir, "research_questions.md")
    with open(research_questions_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(question_lines))
    outputs["research_questions_md"] = research_questions_path

    segment_mix = Counter()
    for recommendation in decision_pack.get("recommendations", []):
        segment_mix[recommendation.get("target_segment", "all_segments")] += 1

    memo_lines = [
        "# Decision Memo",
        "",
        "## Thesis Summary",
        "",
    ]
    if decision_pack.get("recommendations"):
        top = decision_pack["recommendations"][0]
        memo_lines.append(
            f"The strongest near-term opportunity is `{top.get('recommendation_id', '')}` around "
            f"'{top.get('title', '')}', anchored in issue IDs `{', '.join(top.get('supporting_issue_ids', []))}`."
        )
    else:
        memo_lines.append("No opportunities were prioritized for this run.")
    memo_lines.extend(["", "## Top Opportunities", ""])
    for recommendation in decision_pack.get("recommendations", [])[:5]:
        memo_lines.append(
            f"- `{recommendation['recommendation_id']}` [{recommendation['recommendation_type']}] "
            f"{recommendation['title']} | segment: {recommendation['target_segment']} | "
            f"confidence: {recommendation['confidence_label']} | decision score: {recommendation['decision_score']:.1f}"
        )
    memo_lines.extend(["", "## Affected Segments", ""])
    for segment, count in sorted(segment_mix.items(), key=lambda item: (-item[1], item[0])):
        memo_lines.append(f"- `{segment}` appears in {count} top recommendations")

    memo_lines.extend(["", "## Alternatives / Benchmark Context", ""])
    contradictions = benchmark_pack.get("contradictions", []) or []
    if contradictions:
        for row in contradictions[:6]:
            memo_lines.append(
                f"- `{row.get('canonical_issue_id', '')}`: {row.get('summary', '')}"
            )
    else:
        memo_lines.append("- No benchmark contradictions were detected in this run.")

    memo_lines.extend(["", "## Evidence", ""])
    for recommendation in decision_pack.get("recommendations", [])[:5]:
        issue_id = recommendation.get("supporting_issue_ids", [""])[0]
        issue = issues_by_id.get(issue_id)
        memo_lines.append(f"### {recommendation['recommendation_id']} Evidence")
        memo_lines.append("")
        memo_lines.append(
            f"- Issue: `{issue_id}` — {getattr(issue, 'normalized_problem_statement', recommendation.get('title', ''))}"
        )
        memo_lines.append(
            f"- Supporting evidence IDs: {', '.join(recommendation.get('supporting_evidence_ids', [])) or 'none'}"
        )
        for evidence in evidence_by_issue.get(issue_id, [])[:3]:
            memo_lines.append(
                f"- {evidence['evidence_id']} [{evidence['source_family']}/tier {evidence['source_tier']}]: "
                f"{evidence['excerpt'][:140]}"
            )
        memo_lines.append("")

    memo_lines.extend(["## Inference", ""])
    for recommendation in decision_pack.get("recommendations", [])[:5]:
        inference = recommendation.get("inference", {})
        scoring_dimensions = inference.get("scoring_dimensions", {})
        memo_lines.append(f"### {recommendation['recommendation_id']} Inference")
        memo_lines.append("")
        memo_lines.append(
            f"- We infer this is decision-worthy because pain intensity is {scoring_dimensions.get('pain_intensity', 0):.1f}, "
            f"benchmark gap is {scoring_dimensions.get('benchmark_gap', 0):.1f}, and trend is {scoring_dimensions.get('trend_direction', 'no_history')}."
        )
        memo_lines.append("")

    memo_lines.extend(["## Contradictions and Risks", ""])
    if contradictions:
        for row in contradictions[:8]:
            memo_lines.append(
                f"- Risk: `{row.get('contradiction_type', '')}` on `{row.get('canonical_issue_id', '')}` — {row.get('summary', '')}"
            )
    else:
        memo_lines.append("- No contradiction risk flags were emitted.")

    memo_lines.extend(["", "## Recommendation", ""])
    for recommendation in decision_pack.get("recommendations", [])[:5]:
        action = (recommendation.get("recommendation") or {}).get("next_action", "")
        memo_lines.append(f"- `{recommendation['recommendation_id']}`: {action}")

    memo_lines.extend(["", "## Recommended Next Actions", ""])
    for hypothesis in decision_pack.get("hypothesis_backlog", [])[:5]:
        memo_lines.append(f"- `{hypothesis['hypothesis_id']}`: {hypothesis['hypothesis_statement']}")

    memo_lines.extend(["", "## Interview Targets", ""])
    for recommendation in decision_pack.get("recommendations", [])[:5]:
        target = recommendation.get("target_segment", "all_segments")
        memo_lines.append(f"- Interview {target} users affected by `{recommendation['recommendation_id']}`")

    memo_lines.extend(["", "## Measurement Ideas", ""])
    memo_lines.extend(
        [
            "- Track complaint recurrence by canonical issue ID across future runs.",
            "- Measure whether benchmark contradictions shrink after shipping a fix or message change.",
            "- Record which hypotheses convert into validated opportunities with evidence-linked updates.",
        ]
    )

    decision_memo_path = os.path.join(output_dir, "decision_memo.md")
    with open(decision_memo_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(memo_lines))
    outputs["decision_memo_md"] = decision_memo_path

    return outputs
