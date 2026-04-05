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
        project_name="Benchmark",
        project_description="Benchmark pack test",
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
            name="Acme release note",
            kind="release_note",
            url="https://acme.example/releases/billing-export",
            source_family="official",
            source_tier=1,
            entity="Acme",
            entity_type="company",
            excerpt="Billing export is available and stable for finance teams.",
            claims=["Billing export is available and stable for finance teams."],
        )
    ]
    return instruction


class BenchmarkPackTest(unittest.TestCase):
    def test_manual_sources_are_ingested_and_separated_from_community_evidence(self):
        instruction = _instruction()
        filtered = filter_posts(
            [
                SocialPost(
                    post_id="r1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and finance is blocked every day.",
                    metadata={"subreddit": "saas"},
                ),
                SocialPost(
                    post_id="rss1",
                    platform="rss",
                    source_id="https://acme.example/blog/billing",
                    source_title="Billing blog",
                    author="Acme",
                    text="Billing export is now faster and stable for finance teams.",
                    url="https://acme.example/blog/billing",
                    metadata={"domain": "acme.example", "source_family": "official", "benchmark_source": True},
                ),
            ],
            instruction,
        )
        issue_layer = build_issue_intelligence(filtered, instruction)
        entity_layer = build_entity_layer(issue_layer, filtered, instruction)
        benchmark_pack = build_benchmark_pack(issue_layer, filtered, entity_layer, instruction)

        self.assertGreaterEqual(len(benchmark_pack["benchmark_documents"]), 1)
        self.assertGreaterEqual(len(benchmark_pack["benchmark_claims"]), 1)
        self.assertIn("official", benchmark_pack["coverage"]["source_mix"])
        self.assertTrue(
            any(doc["provenance"] == "manual_source" for doc in benchmark_pack["benchmark_documents"])
        )
        self.assertTrue(
            all(doc["source_family"] != "community" for doc in benchmark_pack["benchmark_documents"])
        )


if __name__ == "__main__":
    unittest.main()
