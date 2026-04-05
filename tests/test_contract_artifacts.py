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
from config import Instruction, SocialPost
from reports import generate_all


def _instruction() -> Instruction:
    instruction = Instruction(
        project_name="Contracted",
        project_description="Contract artifact test",
        relevance_keywords=["billing", "broken"],
        min_comment_words=2,
        categories={
            "OPS": {
                "name": "Operations",
                "description": "Operational pain",
                "keywords": ["billing", "broken"],
            }
        },
    )
    instruction.case.case_id = "case_contract"
    instruction.case.case_name = "Contract Test Case"
    instruction.case.decision_objective = "Produce consultant-grade outputs"
    instruction.case.target_deliverables = ["decision_memo.md", "eval_report.md"]
    instruction.workstreams = []
    return instruction


class ContractArtifactsTest(unittest.TestCase):
    def test_contract_artifacts_are_emitted_with_schema_metadata(self):
        instruction = _instruction()
        posts = filter_posts(
            [
                SocialPost(
                    post_id="p1",
                    platform="reddit",
                    source_id="thread_1",
                    source_title="Complaint",
                    author="user1",
                    text="Billing export is broken and blocks finance.",
                    metadata={"subreddit": "saas"},
                )
            ],
            instruction,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            generated = generate_all(posts, instruction, tmpdir)
            with open(generated["workstream_registry_json"], "r", encoding="utf-8") as handle:
                workstream_registry = json.load(handle)
            with open(generated["agent_plan_json"], "r", encoding="utf-8") as handle:
                agent_plan = json.load(handle)
            with open(generated["agent_execution_log_json"], "r", encoding="utf-8") as handle:
                execution_log = json.load(handle)
            with open(generated["agent_handoff_log_json"], "r", encoding="utf-8") as handle:
                handoff_log = json.load(handle)
            with open(generated["artifact_inventory_json"], "r", encoding="utf-8") as handle:
                artifact_inventory = json.load(handle)

        self.assertEqual(workstream_registry["schema_version"], "1.0")
        self.assertEqual(workstream_registry["case"]["case_id"], "case_contract")
        self.assertEqual(agent_plan["schema_version"], "1.0")
        self.assertEqual(execution_log["schema_version"], "1.0")
        self.assertTrue(execution_log["events"])
        self.assertEqual(handoff_log["schema_version"], "1.0")
        self.assertTrue(handoff_log["handoffs"])
        self.assertTrue(any(row["artifact_key"] == "case_plan_md" for row in artifact_inventory["artifacts"]))
        self.assertTrue(any(row["artifact_key"] == "agent_plan_json" for row in artifact_inventory["artifacts"]))
        self.assertTrue(any(row["artifact_key"] == "agent_execution_log_json" for row in artifact_inventory["artifacts"]))
        self.assertTrue(any(row["artifact_key"] == "agent_handoff_log_json" for row in artifact_inventory["artifacts"]))


if __name__ == "__main__":
    unittest.main()
