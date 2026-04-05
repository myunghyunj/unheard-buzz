import json
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
from eval import build_eval_metrics, write_eval_outputs
from issue_intelligence import build_issue_intelligence


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Eval",
        project_description="Eval metrics test",
        relevance_keywords=["billing", "export", "broken"],
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


class EvalMetricsTest(unittest.TestCase):
    def test_eval_report_and_traceability_metrics_are_created(self):
        instruction = _instruction()
        posts = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and blocks month-end close.",
                    metadata={"subreddit": "saas"},
                )
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(posts, instruction)
        entity_layer = build_entity_layer(issue_layer, posts, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, posts, entity_layer, instruction)
        decision_pack = build_decision_package(issue_layer, entity_layer, benchmark_pack, posts=posts)
        metrics = build_eval_metrics(
            issue_layer,
            benchmark_pack,
            decision_pack,
            history_data={
                "issues": [
                    {
                        "canonical_issue_id": issue_layer["issues"][0].canonical_issue_id,
                        "status_label": "stable",
                    }
                ]
            },
            review_summary={"annotation_count": 1, "applied_counts": {"recommendation": 1}, "override_rate": 1.0},
        )

        self.assertEqual(metrics["recommendation_traceability"]["traceability_rate"], 1.0)
        self.assertIn("stability_score", metrics["ranking_stability"])

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = write_eval_outputs(
                issue_layer,
                benchmark_pack,
                decision_pack,
                tmpdir,
                history_data={"issues": [{"canonical_issue_id": issue_layer["issues"][0].canonical_issue_id, "status_label": "stable"}]},
                review_summary={"annotation_count": 1, "applied_counts": {"recommendation": 1}, "override_rate": 1.0},
            )
            self.assertTrue(os.path.exists(outputs["eval_report_md"]))
            self.assertTrue(os.path.exists(outputs["ranking_stability_json"]))
            self.assertTrue(os.path.exists(outputs["benchmark_leakage_report_json"]))
            self.assertTrue(os.path.exists(outputs["reviewer_agreement_summary_json"]))
            with open(outputs["ranking_stability_json"], "r", encoding="utf-8") as handle:
                ranking = json.load(handle)

        self.assertIn("stability_score", ranking)


if __name__ == "__main__":
    unittest.main()
