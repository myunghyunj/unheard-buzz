import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from config import Instruction, SocialPost
from issue_intelligence import apply_source_policy, build_issue_intelligence


def _post(post_id: str, platform: str, source_id: str, text: str, metadata=None) -> SocialPost:
    return SocialPost(
        post_id=post_id,
        platform=platform,
        source_id=source_id,
        source_title=source_id,
        author="user",
        text=text,
        categories=["OPS"],
        metadata=metadata or {},
    )


class SourcePolicyTest(unittest.TestCase):
    def test_defaults(self):
        instruction = Instruction()
        post = SocialPost(post_id="1", platform="reddit", source_id="s", source_title="t", author="a", text="x")
        apply_source_policy(post, instruction)
        self.assertEqual(post.source_tier, 4)
        self.assertTrue(post.independence_key)

    def test_reddit_threads_are_counted_as_distinct_independent_sources(self):
        instruction = Instruction()
        posts = [
            _post("1", "reddit", "thread-a", "Queue is broken in this workflow", {"subreddit": "saas"}),
            _post("2", "reddit", "thread-b", "Queue is broken in this workflow", {"subreddit": "saas"}),
        ]
        layer = build_issue_intelligence(posts, instruction)
        issue = layer["issues"][0]
        self.assertEqual(issue.independent_source_count, 2)
        self.assertEqual(layer["evidence"][0].independence_key, "reddit:saas:thread:thread-a")
        self.assertEqual(layer["evidence"][1].independence_key, "reddit:saas:thread:thread-b")

    def test_twitter_conversations_are_counted_as_distinct_independent_sources(self):
        instruction = Instruction()
        posts = [
            _post("1", "twitter", "conv-1", "Billing export is broken again", {"conversation_id": "conv-1"}),
            _post("2", "twitter", "conv-2", "Billing export is broken again", {"conversation_id": "conv-2"}),
        ]
        layer = build_issue_intelligence(posts, instruction)
        issue = layer["issues"][0]
        self.assertEqual(issue.independent_source_count, 2)
        self.assertEqual(layer["evidence"][0].independence_key, "twitter:conversation:conv-1")
        self.assertEqual(layer["evidence"][1].independence_key, "twitter:conversation:conv-2")


if __name__ == "__main__":
    unittest.main()
