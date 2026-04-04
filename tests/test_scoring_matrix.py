import os
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from analyzer import filter_posts
from config import SocialPost, load_instruction


class ScoringMatrixTest(unittest.TestCase):
    def test_social_only_issue_does_not_outrank_corroborated_issue(self):
        yaml_text = textwrap.dedent(
            """
            project: {name: "s", description: "d"}
            analysis:
              min_comment_words: 2
              relevance_keywords: ["outage", "broken"]
              categories:
                OPS: {name: "Ops", description: "ops", keywords: ["outage", "broken"]}
            source_policy:
              require_tier4_corroboration: true
              allow_tier4_single_source_top_issues: false
            platforms:
              reddit: {enabled: true, subreddits: ["a"], search_queries: ["b"]}
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            path = handle.name
        try:
            instr = load_instruction(path)
        finally:
            os.unlink(path)

        posts = [
            SocialPost(post_id="1", platform="reddit", source_id="a", source_title="a", author="u", text="broken outage now", metadata={"source_tier": 4}),
            SocialPost(post_id="2", platform="github_issues", source_id="repo", source_title="a", author="u", text="broken outage in production with customer impact", metadata={"source_tier": 2, "source_family": "github"}),
        ]
        analyzed = filter_posts(posts, instr)
        prios = {post.platform: post.issue_priority_score for post in analyzed}
        self.assertGreaterEqual(prios["github_issues"], prios["reddit"])

    def test_tier4_single_source_can_be_allowed_for_specific_issue(self):
        yaml_text = textwrap.dedent(
            """
            project: {name: "s", description: "d"}
            analysis:
              min_comment_words: 2
              relevance_keywords: ["broken", "outage"]
              categories:
                OPS: {name: "Ops", description: "ops", keywords: ["broken", "outage"]}
            source_policy:
              require_tier4_corroboration: true
              allow_tier4_single_source_top_issues: true
            platforms:
              reddit: {enabled: true, subreddits: ["a"], search_queries: ["b"]}
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            path = handle.name
        try:
            instr = load_instruction(path)
        finally:
            os.unlink(path)

        posts = [
            SocialPost(
                post_id="1",
                platform="reddit",
                source_id="thread-a",
                source_title="thread-a",
                author="user",
                text="Broken outage after 2.3.1 update blocks checkout for 47 stores and requires manual spreadsheet reconciliation.",
                metadata={"source_tier": 4},
            )
        ]
        analyzed = filter_posts(posts, instr)
        self.assertGreater(analyzed[0].issue_priority_score, 0)
        self.assertGreater(analyzed[0].issue_confidence_score, 0)


if __name__ == "__main__":
    unittest.main()
