import os
import sys
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


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Decision",
        project_description="Decision engine test",
        relevance_keywords=["billing", "export", "broken", "better"],
        min_comment_words=2,
        categories={
            "BILL": {
                "name": "Billing",
                "description": "Billing workflow pain",
                "keywords": ["billing", "export", "broken"],
            }
        },
        segments={
            "FIN": {
                "name": "Finance",
                "description": "Finance teams",
                "keywords": ["finance team", "controller"],
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


class DecisionEngineTest(unittest.TestCase):
    def test_recommendations_cite_issue_and_evidence_ids(self):
        instruction = _instruction()
        posts = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and finance team is blocked. RivalFlow is better.",
                    metadata={"subreddit": "saas"},
                ),
                SocialPost(
                    post_id="p2",
                    platform="github_issues",
                    source_id="issue_2",
                    source_title="GitHub report",
                    author="user2",
                    text="Billing export is broken for finance team and blocks monthly close.",
                    metadata={"repo": "acme/billing", "source_family": "github", "source_tier": 2, "trust_weight": 0.85},
                ),
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(posts, instruction)
        entity_layer = build_entity_layer(issue_layer, posts, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, posts, entity_layer, instruction)
        history_data = {
            "issues": [
                {
                    "canonical_issue_id": issue_layer["issues"][0].canonical_issue_id,
                    "status_label": "rising",
                    "delta_vs_prev": 12.0,
                }
            ]
        }

        decision_pack = build_decision_package(
            issue_layer,
            entity_layer,
            benchmark_pack,
            posts=posts,
            history_data=history_data,
        )

        self.assertTrue(decision_pack["recommendations"])
        recommendation = decision_pack["recommendations"][0]
        self.assertTrue(recommendation["supporting_issue_ids"])
        self.assertTrue(recommendation["supporting_evidence_ids"])
        self.assertIn("decision_score", recommendation)
        self.assertIn("pain_intensity", recommendation["inference"]["scoring_dimensions"])
        self.assertEqual(recommendation["inference"]["scoring_dimensions"]["trend_direction"], "rising")


if __name__ == "__main__":
    unittest.main()
