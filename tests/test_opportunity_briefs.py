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
from opportunity_briefs import write_decision_outputs


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Briefs",
        project_description="Opportunity brief test",
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
            name="Release note",
            kind="release_note",
            url="https://acme.example/releases/billing",
            source_family="official",
            source_tier=1,
            entity="Acme",
            entity_type="company",
            excerpt="Billing export is available and stable for finance teams.",
            claims=["Billing export is available and stable for finance teams."],
        )
    ]
    return instruction


class OpportunityBriefsTest(unittest.TestCase):
    def test_memo_distinguishes_evidence_inference_and_recommendation(self):
        instruction = _instruction()
        posts = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and blocks month-end close for finance.",
                    metadata={"subreddit": "saas"},
                )
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(posts, instruction)
        entity_layer = build_entity_layer(issue_layer, posts, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, posts, entity_layer, instruction)
        decision_pack = build_decision_package(issue_layer, entity_layer, benchmark_pack, posts=posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = write_decision_outputs(decision_pack, issue_layer, benchmark_pack, tmpdir)
            with open(outputs["decision_memo_md"], "r", encoding="utf-8") as handle:
                memo_text = handle.read()
            with open(outputs["opportunity_map_csv"], "r", encoding="utf-8") as handle:
                opportunity_rows = list(csv.DictReader(handle))
            with open(outputs["hypothesis_backlog_csv"], "r", encoding="utf-8") as handle:
                hypothesis_rows = list(csv.DictReader(handle))

        self.assertIn("## Evidence", memo_text)
        self.assertIn("## Inference", memo_text)
        self.assertIn("## Recommendation", memo_text)
        self.assertTrue(opportunity_rows)
        self.assertTrue(hypothesis_rows)


if __name__ == "__main__":
    unittest.main()
