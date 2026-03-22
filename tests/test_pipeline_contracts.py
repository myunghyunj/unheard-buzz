import os
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import compute_final_rank_score, filter_posts, representative_posts_by_category
from config import SocialPost, load_instruction
from reports import generate_summary_report, generate_summary_stats
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
        self.assertIn("Representative post:", report_text)
        self.assertIn("### REL — Reliability", report_text)

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


if __name__ == "__main__":
    unittest.main()
