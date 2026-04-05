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
from history import compute_history_delta, write_history_outputs
from reports import generate_all
from state_store import LocalStateStore, build_run_record


def _instruction(db_path: str) -> Instruction:
    instruction = Instruction(
        project_name="History",
        project_description="History diff test",
        relevance_keywords=["broken", "queue", "billing"],
        min_comment_words=2,
        categories={
            "OPS": {
                "name": "Operations",
                "description": "Operational pain",
                "keywords": ["broken", "queue", "billing"],
            }
        },
    )
    instruction.state_store.enabled = True
    instruction.state_store.backend = "sqlite"
    instruction.state_store.path = db_path
    instruction.state_store.project_id = "history_test"
    instruction.history.enabled = True
    instruction.history.lookback_runs = 5
    return instruction


def _run_one_posts() -> list:
    return [
        SocialPost(
            post_id="run1_a",
            platform="reddit",
            source_id="thread_a",
            source_title="A",
            author="user1",
            text="broken charger issue because queue delays drivers. first account",
            metadata={"subreddit": "evs"},
        ),
        SocialPost(
            post_id="run1_c",
            platform="reddit",
            source_id="thread_c",
            source_title="C",
            author="user2",
            text="billing sync broken issue because queue delays finance. disappearing issue",
            metadata={"subreddit": "saas"},
        ),
    ]


def _run_two_posts() -> list:
    return [
        SocialPost(
            post_id="run2_a1",
            platform="reddit",
            source_id="thread_a2",
            source_title="A2",
            author="user1",
            text="broken charger issue because queue delays drivers. first account",
            metadata={"subreddit": "evs"},
        ),
        SocialPost(
            post_id="run2_a2",
            platform="github_issues",
            source_id="issue_a2",
            source_title="A2 issue",
            author="user3",
            text="broken charger issue because queue delays drivers. second corroborating report",
            metadata={"source_family": "github", "source_tier": 2, "trust_weight": 0.85},
        ),
        SocialPost(
            post_id="run2_b",
            platform="reddit",
            source_id="thread_b",
            source_title="B",
            author="user4",
            text="new broken queue issue because billing exports fail every day. new issue",
            metadata={"subreddit": "saas"},
        ),
    ]


class HistoryDiffTest(unittest.TestCase):
    def test_second_run_produces_new_rising_and_disappeared_issue_diffs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "history.sqlite3")
            instruction = _instruction(db_path)
            store = LocalStateStore(instruction.state_store)

            run_one_dir = os.path.join(tmpdir, "run_one")
            filtered_one = filter_posts(_run_one_posts(), instruction)
            generated_one = generate_all(filtered_one, instruction, run_one_dir)
            run_one = build_run_record(
                instruction=instruction,
                output_dir=run_one_dir,
                started_at="2026-04-05T00:00:00+00:00",
                completed_at="2026-04-05T00:01:00+00:00",
                git_commit="abc",
                run_label="run-one",
            )
            store.ingest_run(run_record=run_one, instruction=instruction, posts=filtered_one, generated_files=generated_one)

            run_two_dir = os.path.join(tmpdir, "run_two")
            filtered_two = filter_posts(_run_two_posts(), instruction)
            generated_two = generate_all(filtered_two, instruction, run_two_dir)
            run_two = build_run_record(
                instruction=instruction,
                output_dir=run_two_dir,
                started_at="2026-04-06T00:00:00+00:00",
                completed_at="2026-04-06T00:01:00+00:00",
                git_commit="abc",
                run_label="run-two",
            )
            store.ingest_run(run_record=run_two, instruction=instruction, posts=filtered_two, generated_files=generated_two)

            history_data = compute_history_delta(
                store,
                project_id=run_two["project_id"],
                run_id=run_two["run_id"],
                lookback_runs=instruction.history.lookback_runs,
            )
            outputs = write_history_outputs(history_data, run_two_dir, emit_diff_report=True)

            self.assertTrue(os.path.exists(outputs["history_summary_json"]))
            self.assertTrue(os.path.exists(outputs["history_diff_md"]))
            self.assertEqual(history_data["previous_run_id"], run_one["run_id"])
            self.assertGreaterEqual(history_data["summary"].get("rising", 0), 1)
            self.assertGreaterEqual(history_data["summary"].get("new", 0), 1)
            self.assertGreaterEqual(history_data["summary"].get("disappeared", 0), 1)

            with open(outputs["history_diff_md"], "r", encoding="utf-8") as handle:
                diff_text = handle.read()
            self.assertIn("History Diff", diff_text)
            self.assertIn("rising", diff_text)
            self.assertIn("disappeared", diff_text)
            store.close()


if __name__ == "__main__":
    unittest.main()
