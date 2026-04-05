import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import filter_posts
from config import Instruction, ManualSourceConfig, SocialPost
from reports import generate_all
from state_store import LocalStateStore, build_run_record


def _instruction(db_path: str) -> Instruction:
    instruction = Instruction(
        project_name="Warehouse",
        project_description="State store test",
        relevance_keywords=["broken", "queue"],
        min_comment_words=2,
        categories={
            "OPS": {
                "name": "Operations",
                "description": "Operational pain",
                "keywords": ["broken", "queue"],
            }
        },
    )
    instruction.state_store.enabled = True
    instruction.state_store.backend = "sqlite"
    instruction.state_store.path = db_path
    instruction.state_store.project_id = "warehouse_test"
    instruction.history.enabled = True
    instruction.benchmarks.enabled = True
    instruction.benchmarks.alternatives.tracked_entities = ["RivalCharge"]
    instruction.benchmarks.entity_aliases = {"RivalCharge": ["rival charge"]}
    instruction.benchmarks.manual_sources = [
        ManualSourceConfig(
            name="Vendor release note",
            kind="release_note",
            url="https://vendor.example/releases/billing",
            source_family="official",
            source_tier=1,
            entity="Acme Charging",
            entity_type="company",
            claims=["Billing export is available and stable for finance teams."],
            excerpt="Billing export is available and stable for finance teams.",
        )
    ]
    return instruction


def _posts() -> list:
    return [
        SocialPost(
            post_id="reddit_post_1",
            platform="reddit",
            source_id="thread_1",
            source_title="Thread 1",
            author="user1",
            text="broken charger issue because queue delays drivers. first account",
            metadata={"subreddit": "evs"},
        ),
        SocialPost(
            post_id="github_issue_1",
            platform="github_issues",
            source_id="issue_1",
            source_title="Issue 1",
            author="user2",
            text="broken charger issue because queue delays drivers. production report",
            metadata={"source_family": "github", "source_tier": 2, "trust_weight": 0.85},
        ),
    ]


class StateStoreTest(unittest.TestCase):
    def test_reingest_same_project_updates_deduped_records_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "state.sqlite3")
            instruction = _instruction(db_path)
            filtered = filter_posts(_posts(), instruction)
            output_dir = os.path.join(tmpdir, "run")
            generated = generate_all(filtered, instruction, output_dir)

            store = LocalStateStore(instruction.state_store)
            run_one = build_run_record(
                instruction=instruction,
                output_dir=output_dir,
                started_at="2026-04-05T00:00:00+00:00",
                completed_at="2026-04-05T00:01:00+00:00",
                git_commit="abc",
                run_label="run-one",
            )
            run_two = build_run_record(
                instruction=instruction,
                output_dir=output_dir,
                started_at="2026-04-06T00:00:00+00:00",
                completed_at="2026-04-06T00:01:00+00:00",
                git_commit="abc",
                run_label="run-two",
            )

            store.ingest_run(run_record=run_one, instruction=instruction, posts=filtered, generated_files=generated)
            store.ingest_run(run_record=run_two, instruction=instruction, posts=filtered, generated_files=generated)
            store.save_reviewer_annotations(
                project_id=run_one["project_id"],
                case_id=run_one["case_id"],
                run_id=run_one["run_id"],
                annotations=[
                    {
                        "record_type": "recommendation",
                        "record_id": "rec_1",
                        "field": "confidence_label",
                        "override_value": "high",
                        "notes": "Carry forward this decision.",
                    }
                ],
            )
            remembered = store.latest_reviewer_annotations(
                project_id=run_two["project_id"],
                case_id=run_two["case_id"],
                exclude_run_id=run_two["run_id"],
            )

            runs_count = store.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            posts_count = store.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            evidence_count = store.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            issue_metrics_count = store.conn.execute("SELECT COUNT(*) FROM issue_run_metrics").fetchone()[0]
            entity_count = store.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            benchmark_doc_count = store.conn.execute("SELECT COUNT(*) FROM benchmark_documents").fetchone()[0]
            benchmark_claim_count = store.conn.execute("SELECT COUNT(*) FROM benchmark_claims").fetchone()[0]
            review_decision_count = store.conn.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]

            self.assertEqual(runs_count, 2)
            self.assertEqual(posts_count, 2)
            self.assertEqual(evidence_count, 2)
            self.assertEqual(issue_metrics_count, 2)
            self.assertGreaterEqual(entity_count, 1)
            self.assertGreaterEqual(benchmark_doc_count, 1)
            self.assertGreaterEqual(benchmark_claim_count, 1)
            self.assertEqual(review_decision_count, 1)
            self.assertTrue(run_one["run_id"].startswith("run_20260405T000100Z_"))
            self.assertEqual(remembered[0]["annotation_origin"], "review_memory")
            self.assertEqual(remembered[0]["override_value"], "high")
            store.close()


if __name__ == "__main__":
    unittest.main()
