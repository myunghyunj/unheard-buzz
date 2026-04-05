import csv
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import filter_posts
from benchmark_pack import build_benchmark_pack
from config import Instruction, ManualSourceConfig, SocialPost
from decision_engine import build_decision_package
from entities import build_entity_layer
from issue_intelligence import build_issue_intelligence
from review_pack import apply_reviewer_overrides, merge_reviewer_annotations, write_review_pack


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Review",
        project_description="Review pack test",
        relevance_keywords=["billing", "export", "broken", "better"],
        min_comment_words=2,
        categories={
            "BILL": {
                "name": "Billing",
                "description": "Billing workflow pain",
                "keywords": ["billing", "export", "broken"],
            }
        },
    )
    instruction.benchmarks.enabled = True
    instruction.benchmarks.alternatives.tracked_entities = ["RivalFlow"]
    instruction.benchmarks.manual_sources = [
        ManualSourceConfig(
            name="Status page",
            kind="status_page",
            url="https://acme.example/status",
            source_family="official",
            source_tier=1,
            entity="Acme",
            entity_type="company",
            excerpt="Billing export is available and stable for finance teams.",
            claims=["Billing export is available and stable for finance teams."],
        )
    ]
    return instruction


class ReviewPackTest(unittest.TestCase):
    def test_review_pack_exports_stable_columns_and_applies_overrides_safely(self):
        instruction = _instruction()
        posts = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and finance is blocked. RivalFlow is better.",
                    metadata={"subreddit": "saas"},
                )
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(posts, instruction)
        entity_layer = build_entity_layer(issue_layer, posts, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, posts, entity_layer, instruction)
        decision_pack = build_decision_package(issue_layer, entity_layer, benchmark_pack, posts=posts)

        contradiction_id = benchmark_pack["contradictions"][0]["contradiction_id"]
        recommendation_id = decision_pack["recommendations"][0]["recommendation_id"]
        annotations = [
            {
                "record_type": "recommendation",
                "record_id": recommendation_id,
                "field": "confidence_label",
                "override_value": "high",
                "notes": "Validated in customer call.",
            },
            {
                "record_type": "contradiction",
                "record_id": contradiction_id,
                "field": "status",
                "override_value": "false_positive",
                "notes": "Bench link was stale.",
            },
        ]

        override_result = apply_reviewer_overrides(
            issue_layer,
            decision_pack,
            entity_layer,
            benchmark_pack,
            annotations,
        )

        self.assertNotEqual(
            decision_pack["recommendations"][0]["confidence_label"],
            override_result["decision_pack"]["recommendations"][0]["confidence_label"],
        )
        self.assertEqual(
            override_result["decision_pack"]["recommendations"][0]["confidence_label"],
            "high",
        )
        self.assertEqual(len(benchmark_pack["contradictions"]), 2)
        self.assertEqual(len(override_result["benchmark_pack"]["contradictions"]), 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = write_review_pack(
                issue_layer,
                entity_layer,
                benchmark_pack,
                override_result["decision_pack"],
                tmpdir,
                annotations,
            )
            with open(outputs["annotation_pack_csv"], "r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        expected_columns = {
            "schema_version",
            "record_type",
            "record_id",
            "canonical_issue_id",
            "recommendation_id",
            "entity_id",
            "contradiction_id",
            "current_value",
            "supporting_evidence_ids",
            "reviewer_override",
            "annotation_origin",
            "notes",
        }
        self.assertEqual(set(rows[0].keys()), expected_columns)
        self.assertTrue(any(row["reviewer_override"] == "high" for row in rows if row["record_type"] == "recommendation"))
        self.assertTrue(any(row["annotation_origin"] == "manual_csv" for row in rows if row["record_type"] == "recommendation"))

    def test_manual_annotations_override_reviewer_memory_for_same_key(self):
        merged = merge_reviewer_annotations(
            [
                {
                    "record_type": "recommendation",
                    "record_id": "rec_1",
                    "field": "confidence_label",
                    "override_value": "high",
                    "notes": "Fresh review",
                    "annotation_origin": "manual_csv",
                }
            ],
            [
                {
                    "record_type": "recommendation",
                    "record_id": "rec_1",
                    "field": "confidence_label",
                    "override_value": "medium",
                    "notes": "Old memory",
                    "annotation_origin": "review_memory",
                }
            ],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["override_value"], "high")
        self.assertEqual(merged[0]["annotation_origin"], "manual_csv")


if __name__ == "__main__":
    unittest.main()
