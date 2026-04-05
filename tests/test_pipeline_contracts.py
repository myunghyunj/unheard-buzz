import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import compute_final_rank_score, filter_posts, representative_posts_by_category
from config import Instruction, SocialPost, load_instruction
from reports import generate_all, generate_summary_report, generate_summary_stats
from run import run_pipeline
from youtube import _convert_comments_to_posts


class PipelineContractsTest(unittest.TestCase):
    def test_yaml_load_supports_analysis_controls(self):
        yaml_text = textwrap.dedent(
            """
            project:
              name: "Smoke"
              description: "Test"

            analysis:
              min_comment_words: 7
              include_irrelevant_in_stats: false
              language_allowlist: ["en"]
              dedup_normalized_text: true
              dedup_min_chars: 30
              relevance_keywords: ["charger"]
              segments:
                URBAN:
                  name: "Urban"
                  description: "Dense city use cases"
                  keywords: ["city", "urban"]
              categories:
                REL:
                  name: "Reliability"
                  description: "Broken chargers"
                  keywords: ["broken"]

            platforms:
              reddit:
                enabled: true
                subreddits: ["electricvehicles"]
                search_queries: ["broken charger"]
                sort: "relevance"
                time_filter: "year"
                quota:
                  max_posts_per_query: 10
                  max_comments_per_post: 10

            validation:
              enabled: false
              references: []

            reporting:
              quote_count: 12
              max_cooccurrence_pairs: 8
              top_category_limit: 6

            state_store:
              enabled: true
              backend: "sqlite"
              path: "state/test.sqlite3"
              project_id: "smoke_project"
              keep_raw_text: false

            history:
              enabled: true
              lookback_runs: 3
              emit_diff_report: true

            case:
              id: "case_smoke"
              name: "Smoke Case"
              client: "Internal"
              market_scope: "Urban mobility"
              geography: "US"
              time_horizon: "current quarter"
              decision_objective: "Pick the highest-confidence next bet"
              target_deliverables: ["decision_memo.md", "opportunity_map.csv"]
              allowed_sources: ["reddit", "youtube", "github_issues"]
              excluded_sources: ["private_forums"]
              risk_notes: ["Do not overclaim from social-only evidence"]

            workstreams:
              - id: "unmet_needs"
                name: "Unmet Needs"
                objective: "Identify the strongest unmet needs"
                primary_agent_role: "issue_analyst"
                fallback_role: "orchestrator"
                handoff_inputs: ["issue_registry.csv", "evidence_registry.csv"]
                handoff_outputs: ["decision_memo.md"]
                stop_conditions: ["Top recommendations are evidence-linked"]
                status: "planned"

            agent_control:
              enabled: true
              max_parallel_roles: 5
              default_time_budget_minutes: 60
              default_retry_budget: 3
              default_confidence_threshold: 0.7
              allow_external_search: true
              escalation_triggers: ["low_evidence_coverage", "sensitive_recommendation"]

            benchmarks:
              enabled: true
              manual_sources:
                - name: "Vendor status"
                  kind: "status_page"
                  url: "https://vendor.example/status"
                  source_family: "official"
                  source_tier: 1
                  entity: "VendorCo"
                  entity_type: "company"
                  aliases: ["vendor co"]
                  tags: ["status"]
                  excerpt: "Billing export is available."
                  claims: ["Billing export is available."]
              alternatives:
                tracked_entities: ["RivalFlow"]
              entity_aliases:
                VendorCo: ["vendor"]
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            yaml_path = handle.name

        try:
            instruction = load_instruction(yaml_path)
        finally:
            os.unlink(yaml_path)

        self.assertEqual(instruction.min_comment_words, 7)
        self.assertEqual(instruction.language_allowlist, ["en"])
        self.assertTrue(instruction.dedup_normalized_text)
        self.assertEqual(instruction.dedup_min_chars, 30)
        self.assertIn("URBAN", instruction.segments)
        self.assertEqual(instruction.reporting.quote_count, 12)
        self.assertEqual(instruction.reporting.max_cooccurrence_pairs, 8)
        self.assertEqual(instruction.reporting.top_category_limit, 6)
        self.assertTrue(instruction.state_store.enabled)
        self.assertEqual(instruction.state_store.backend, "sqlite")
        self.assertEqual(instruction.state_store.project_id, "smoke_project")
        self.assertFalse(instruction.state_store.keep_raw_text)
        self.assertTrue(instruction.history.enabled)
        self.assertEqual(instruction.history.lookback_runs, 3)
        self.assertEqual(instruction.case.case_id, "case_smoke")
        self.assertEqual(instruction.case.client, "Internal")
        self.assertEqual(len(instruction.workstreams), 1)
        self.assertEqual(instruction.workstreams[0].workstream_id, "unmet_needs")
        self.assertEqual(instruction.agent_control.max_parallel_roles, 5)
        self.assertEqual(instruction.agent_control.default_time_budget_minutes, 60)
        self.assertTrue(instruction.benchmarks.enabled)
        self.assertEqual(len(instruction.benchmarks.manual_sources), 1)
        self.assertEqual(instruction.benchmarks.manual_sources[0].entity, "VendorCo")
        self.assertEqual(instruction.benchmarks.alternatives.tracked_entities, ["RivalFlow"])
        self.assertEqual(instruction.benchmarks.entity_aliases["VendorCo"], ["vendor"])

    def test_final_rank_score_is_deterministic(self):
        post = SocialPost(
            post_id="1",
            platform="reddit",
            source_id="src",
            source_title="Thread",
            author="user",
            text="The charger is broken and the queue is terrible.",
            like_count=10,
            has_wish=True,
            relevance_score=0.8,
            category_scores={"REL": 0.5, "WAIT": 1.0},
            metadata={"collector_score": 2.0},
        )

        score_one = compute_final_rank_score(post)
        score_two = compute_final_rank_score(post)

        self.assertEqual(score_one, score_two)
        self.assertGreater(score_one, 0)

    def test_representative_post_selection_and_summary_stats(self):
        instruction_yaml = textwrap.dedent(
            """
            project:
              name: "Smoke"
              description: "Test"

            analysis:
              min_comment_words: 5
              include_irrelevant_in_stats: false
              relevance_keywords: ["charger", "queue", "broken"]
              categories:
                REL:
                  name: "Reliability"
                  description: "Broken chargers"
                  keywords: ["broken", "offline"]
                WAIT:
                  name: "Wait time"
                  description: "Queues"
                  keywords: ["queue", "waiting"]

            platforms:
              reddit:
                enabled: true
                subreddits: ["electricvehicles"]
                search_queries: ["broken charger"]
                sort: "relevance"
                time_filter: "year"
                quota:
                  max_posts_per_query: 10
                  max_comments_per_post: 10
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(instruction_yaml)
            yaml_path = handle.name

        try:
            instruction = load_instruction(yaml_path)
        finally:
            os.unlink(yaml_path)

        posts = [
            SocialPost(
                post_id="1",
                platform="reddit",
                source_id="a",
                source_title="Thread A",
                author="u1",
                text="The charger is broken and the queue is terrible. I wish there were more stalls nearby.",
                like_count=12,
                metadata={"collector_score": 2.1},
            ),
            SocialPost(
                post_id="2",
                platform="youtube",
                source_id="b",
                source_title="Video B",
                author="u2",
                text="Public charging queue is painful because the charger is broken again today.",
                like_count=4,
                metadata={"collector_score": 1.5},
            ),
        ]

        filtered = filter_posts(posts, instruction)
        reps = representative_posts_by_category(filtered, instruction)

        self.assertIn("REL", reps)
        self.assertEqual(len(reps["REL"]), 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = generate_summary_stats(filtered, instruction, tmpdir)
            report_path = generate_summary_report(stats, instruction, tmpdir)
            with open(report_path, "r", encoding="utf-8") as handle:
                report_text = handle.read()

        self.assertIn("category_exemplars", stats)
        self.assertIn("REL", stats["category_exemplars"])
        self.assertIn("text_excerpt", stats["category_exemplars"]["REL"])
        self.assertTrue(stats["top_issues"])
        self.assertTrue(stats["score_breakdowns"])
        self.assertTrue(stats["dashboard_data"]["issues"])
        self.assertIn("Representative post:", report_text)
        self.assertIn("## Top Issues (Impact vs Confidence)", report_text)
        self.assertIn("### REL — Reliability", report_text)

    def test_generate_all_emits_consulting_artifacts(self):
        instruction_yaml = textwrap.dedent(
            """
            project:
              name: "Mobility"
              description: "Test"
              objectives:
                - "Find operational pain points"

            analysis:
              min_comment_words: 3
              relevance_keywords: ["wheelchair", "accessibility"]
              segments:
                TRANSIT:
                  name: "Transit"
                  description: "Transit contexts"
                  keywords: ["bus", "train"]
              categories:
                ACCESS:
                  name: "Access"
                  description: "Blocked access"
                  keywords: ["ramp", "elevator", "accessibility"]

            platforms:
              reddit:
                enabled: true
                subreddits: ["accessibility"]
                search_queries: ["wheelchair ramp"]
                sort: "relevance"
                time_filter: "year"
                quota:
                  max_posts_per_query: 10
                  max_comments_per_post: 10

            reporting:
              quote_count: 3
              max_cooccurrence_pairs: 5
              top_category_limit: 4

            benchmarks:
              enabled: true
              manual_sources:
                - name: "Access status page"
                  kind: "status_page"
                  url: "https://access.example/status"
                  source_family: "official"
                  source_tier: 1
                  entity: "AccessCo"
                  entity_type: "company"
                  excerpt: "Transit accessibility systems are available."
                  claims: ["Transit accessibility systems are available."]
              alternatives:
                tracked_entities: ["MoveLift"]
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(instruction_yaml)
            yaml_path = handle.name

        try:
            instruction = load_instruction(yaml_path)
        finally:
            os.unlink(yaml_path)

        posts = filter_posts(
            [
                SocialPost(
                    post_id="1",
                    platform="youtube",
                    source_id="vid1",
                    source_title="Transit story",
                    author="user1",
                    text="Wheelchair accessibility on the bus is broken and the ramp fails constantly.",
                    like_count=8,
                    metadata={"channel": "Access Channel", "collector_score": 2.0},
                ),
                SocialPost(
                    post_id="2",
                    platform="reddit",
                    source_id="thread1",
                    source_title="Station elevator issue",
                    author="user2",
                    text="The train station elevator is out and wheelchair accessibility is awful.",
                    like_count=3,
                    metadata={"subreddit": "accessibility", "collector_score": 1.2},
                ),
            ],
            instruction,
        )

        collector_context = {
            "youtube": {
                "channels": [
                    {
                        "channel_id": "ch1",
                        "name": "Access Channel",
                        "subscribers": 1000,
                        "handle": "@accesschannel",
                        "content_style": "vlog",
                    }
                ],
                "videos": [
                    {
                        "videoId": "vid1",
                        "channelName": "Access Channel",
                        "title": "Transit story",
                        "viewCount": 1200,
                        "commentCount": 88,
                        "publishedAt": "2026-03-01T00:00:00Z",
                        "collector_video_score": 6.4,
                        "topic_tags": ["ramp"],
                    }
                ],
                "stats": {"channels_discovered": 1, "videos_selected": 1},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            generated = generate_all(posts, instruction, tmpdir, collector_context=collector_context)

            expected_keys = {
                "all_posts_csv",
                "coded_posts_csv",
                "coded_comments_csv",
                "source_registry_csv",
                "source_registry_enriched_csv",
                "issue_registry_csv",
                "evidence_registry_csv",
                "channel_registry_csv",
                "video_registry_csv",
                "entity_registry_csv",
                "issue_entity_links_csv",
                "alternatives_matrix_csv",
                "contradiction_registry_csv",
                "benchmark_coverage_json",
                "decision_memo_md",
                "opportunity_map_csv",
                "segment_pain_matrix_csv",
                "hypothesis_backlog_csv",
                "research_questions_md",
                "recommendation_cards_json",
                "annotation_pack_csv",
                "annotation_guidelines_md",
                "eval_report_md",
                "ranking_stability_json",
                "benchmark_leakage_report_json",
                "case_plan_md",
                "workstream_registry_json",
                "workstream_status_md",
                "agent_plan_json",
                "agent_execution_log_json",
                "agent_handoff_log_json",
                "artifact_inventory_json",
                "dashboard_data_json",
                "summary_stats_json",
                "summary_report_md",
                "quotable_excerpts_md",
            }
            self.assertTrue(expected_keys.issubset(generated.keys()))
            for key in expected_keys:
                self.assertTrue(os.path.exists(generated[key]), key)

            with open(generated["summary_stats_json"], "r", encoding="utf-8") as handle:
                stats = json.load(handle)
            with open(generated["dashboard_data_json"], "r", encoding="utf-8") as handle:
                dashboard = json.load(handle)
            with open(generated["benchmark_coverage_json"], "r", encoding="utf-8") as handle:
                benchmark_coverage = json.load(handle)
            with open(generated["recommendation_cards_json"], "r", encoding="utf-8") as handle:
                recommendation_cards = json.load(handle)
            with open(generated["workstream_registry_json"], "r", encoding="utf-8") as handle:
                workstream_registry = json.load(handle)
            with open(generated["agent_plan_json"], "r", encoding="utf-8") as handle:
                agent_plan = json.load(handle)
            with open(generated["agent_execution_log_json"], "r", encoding="utf-8") as handle:
                agent_execution = json.load(handle)
            with open(generated["agent_handoff_log_json"], "r", encoding="utf-8") as handle:
                agent_handoff = json.load(handle)
            with open(generated["artifact_inventory_json"], "r", encoding="utf-8") as handle:
                artifact_inventory = json.load(handle)
            with open(generated["ranking_stability_json"], "r", encoding="utf-8") as handle:
                ranking_stability = json.load(handle)
            with open(generated["benchmark_leakage_report_json"], "r", encoding="utf-8") as handle:
                benchmark_leakage = json.load(handle)
            with open(generated["summary_report_md"], "r", encoding="utf-8") as handle:
                report_text = handle.read()
            with open(generated["decision_memo_md"], "r", encoding="utf-8") as handle:
                memo_text = handle.read()
            with open(generated["eval_report_md"], "r", encoding="utf-8") as handle:
                eval_text = handle.read()

            self.assertTrue(stats["top_issues"])
            self.assertTrue(stats["score_breakdowns"])
            self.assertIn("source_mix", stats)
            self.assertIn("freshness_score", stats)
            self.assertTrue(dashboard["issues"])
            self.assertIn("time_trend", dashboard)
            self.assertIn("heatmap", dashboard)
            self.assertIn("document_count", benchmark_coverage)
            self.assertGreaterEqual(benchmark_coverage["document_count"], 1)
            self.assertTrue(recommendation_cards)
            self.assertEqual(workstream_registry["case"]["case_name"], "Mobility")
            self.assertTrue(agent_plan["roles"])
            self.assertTrue(agent_execution["events"])
            self.assertTrue(agent_handoff["handoffs"])
            self.assertTrue(artifact_inventory["artifacts"])
            self.assertIn("history_available", ranking_stability)
            self.assertIn("leakage_count", benchmark_leakage)
            self.assertIn("## Evidence", memo_text)
            self.assertIn("## Inference", memo_text)
            self.assertIn("## Recommendation", memo_text)
            self.assertIn("## Recommendation Traceability", eval_text)
            self.assertIn("## Top Issues (Impact vs Confidence)", report_text)

    def test_language_allowlist_collector_smoke(self):
        instruction_yaml = textwrap.dedent(
            """
            project:
              name: "Smoke"
              description: "Test"

            analysis:
              min_comment_words: 2
              relevance_keywords: ["charger"]
              language_allowlist: ["en"]
              categories:
                REL:
                  name: "Reliability"
                  description: "Broken chargers"
                  keywords: ["charger"]

            platforms:
              youtube:
                enabled: true
                api_key_env: "YOUTUBE_API_KEY"
                search_queries: ["charger review"]
                priority_channels: []
                video_priority_keywords: ["review"]
                quota:
                  max_channels: 1
                  max_videos_per_channel: 1
                  max_comments_per_video: 5
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(instruction_yaml)
            yaml_path = handle.name

        try:
            instruction = load_instruction(yaml_path)
        finally:
            os.unlink(yaml_path)

        videos = [{"videoId": "abc123", "title": "Test video", "viewCount": 10}]
        comments = [
            {
                "comment_id": "c1",
                "video_id": "abc123",
                "channel_name": "Channel",
                "author": "User1",
                "text": "This charger is broken and the queue is bad for drivers",
                "like_count": 1,
                "is_reply": False,
                "parent_id": None,
                "timestamp": "2026-03-22T00:00:00Z",
            },
            {
                "comment_id": "c2",
                "video_id": "abc123",
                "channel_name": "Channel",
                "author": "User2",
                "text": "이 충전기는 또 고장났어요",
                "like_count": 1,
                "is_reply": False,
                "parent_id": None,
                "timestamp": "2026-03-22T00:00:00Z",
            },
        ]

        posts, lang_filtered = _convert_comments_to_posts(comments, videos, instruction)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].metadata["language_guess"], "en")
        self.assertEqual(lang_filtered, 1)

    def test_run_pipeline_always_emits_run_manifest(self):
        instruction = Instruction(
            project_name="Manifest",
            project_description="Run manifest smoke",
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
        instruction.reddit.enabled = True
        instruction.reddit.subreddits = ["saas"]
        instruction.reddit.search_queries = ["broken billing"]
        instruction.visualization.enabled = False
        instruction.validation_enabled = False

        fake_posts = [
            SocialPost(
                post_id="p1",
                platform="reddit",
                source_id="thread_1",
                source_title="Complaint",
                author="user1",
                text="Billing export is broken and blocks finance.",
                metadata={"subreddit": "saas"},
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("run._PLATFORM_RUNNERS", {"reddit": lambda _instruction: {"posts": fake_posts}}, clear=False):
                summary = run_pipeline(
                    instruction,
                    output_dir=tmpdir,
                    skip_trends=True,
                    no_state=True,
                )

            manifest_path = summary["generated_files"]["run_manifest_json"]
            self.assertTrue(os.path.exists(manifest_path))
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)

        self.assertIn("artifact_inventory_path", manifest)
        self.assertTrue(manifest["generated_files"])
        self.assertEqual(manifest["state_store"]["resolved_backend"], "disabled")


if __name__ == "__main__":
    unittest.main()
