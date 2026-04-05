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
from entities import build_entity_layer
from issue_intelligence import build_issue_intelligence


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Contradictions",
        project_description="Contradiction detection test",
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
            "ENT": {
                "name": "Enterprise",
                "description": "Enterprise finance teams",
                "keywords": ["finance team", "enterprise"],
            },
            "SMB": {
                "name": "SMB",
                "description": "Small teams",
                "keywords": ["small business", "small team"],
            },
        },
    )
    instruction.benchmarks.enabled = True
    instruction.benchmarks.alternatives.tracked_entities = ["RivalFlow"]
    instruction.benchmarks.manual_sources = [
        ManualSourceConfig(
            name="Vendor status page",
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


class ContradictionTest(unittest.TestCase):
    def test_contradiction_outputs_are_created_when_evidence_conflicts(self):
        instruction = _instruction()
        filtered = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Enterprise complaint",
                    author="user1",
                    text="Billing export is broken and blocked every day. The enterprise finance team is offline. RivalFlow is better.",
                    metadata={"subreddit": "saas"},
                ),
                SocialPost(
                    post_id="p2",
                    platform="reddit",
                    source_id="thread_2",
                    source_title="SMB complaint",
                    author="user2",
                    text="Billing export is broken and blocked every day. Our small business has a workaround.",
                    metadata={"subreddit": "saas"},
                ),
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(filtered, instruction)
        entity_layer = build_entity_layer(issue_layer, filtered, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, filtered, entity_layer, instruction)

        contradiction_types = {row["contradiction_type"] for row in benchmark_pack["contradictions"]}
        self.assertIn("complaint_vs_benchmark_claim", contradiction_types)
        self.assertIn("alternative_positive_signal", contradiction_types)
        self.assertIn("segment_severity_gap", contradiction_types)


if __name__ == "__main__":
    unittest.main()
