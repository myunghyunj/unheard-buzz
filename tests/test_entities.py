import json
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import filter_posts
from config import Instruction, SocialPost
from entities import build_entity_layer
from issue_intelligence import build_issue_intelligence


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Entities",
        project_description="Entity extraction test",
        relevance_keywords=["billing", "dashboard", "queue", "better"],
        min_comment_words=2,
        categories={
            "OPS": {
                "name": "Operations",
                "description": "Operational pain",
                "keywords": ["billing", "queue", "dashboard", "broken"],
            }
        },
        segments={
            "FIN": {
                "name": "Finance",
                "description": "Finance team workflows",
                "keywords": ["finance team", "accountant", "controller"],
            }
        },
    )
    instruction.benchmarks.enabled = True
    instruction.benchmarks.alternatives.tracked_entities = ["ChargePoint"]
    instruction.benchmarks.entity_aliases = {"ChargePoint": ["cp"]}
    return instruction


def _posts() -> list:
    return [
        SocialPost(
            post_id="p1",
            platform="reddit",
            source_id="thread_1",
            source_title="Billing thread",
            author="user1",
            text="The finance team says billing dashboard exports are broken in Europe and cp is better.",
            metadata={"subreddit": "saas"},
        ),
        SocialPost(
            post_id="p2",
            platform="reddit",
            source_id="thread_2",
            source_title="Workflow thread",
            author="user2",
            text="Our accountant is stuck in the billing workflow because the dashboard queue is broken again.",
            metadata={"subreddit": "saas"},
        ),
    ]


class EntityLayerTest(unittest.TestCase):
    def test_entity_extraction_is_deterministic(self):
        instruction = _instruction()
        filtered = filter_posts(_posts(), instruction)
        issue_layer = build_issue_intelligence(filtered, instruction)

        layer_one = build_entity_layer(issue_layer, filtered, instruction)
        layer_two = build_entity_layer(issue_layer, filtered, instruction)

        self.assertEqual(
            json.dumps(layer_one, ensure_ascii=False, sort_keys=True),
            json.dumps(layer_two, ensure_ascii=False, sort_keys=True),
        )

        entity_types = {row["entity_type"] for row in layer_one["entities"]}
        self.assertIn("competitor", entity_types)
        self.assertIn("role", entity_types)
        self.assertIn("workflow", entity_types)
        self.assertIn("geography", entity_types)

        competitor_links = [
            row for row in layer_one["issue_entity_links"] if row["entity_type"] == "competitor"
        ]
        self.assertTrue(competitor_links)
        self.assertEqual(competitor_links[0]["entity_id"], "competitor:chargepoint")


if __name__ == "__main__":
    unittest.main()
