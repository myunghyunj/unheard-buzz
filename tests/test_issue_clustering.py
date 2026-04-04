import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from config import Instruction, SocialPost
from issue_intelligence import build_issue_intelligence


class IssueClusterTest(unittest.TestCase):
    def test_similar_phrasing_clusters_together(self):
        instr = Instruction(relevance_keywords=["broken", "outage"])
        posts = [
            SocialPost(post_id="1", platform="reddit", source_id="thread-a", source_title="t", author="a", text="The charger is broken and drivers keep waiting in line."),
            SocialPost(post_id="2", platform="github_issues", source_id="repo-a", source_title="t", author="a", text="Broken charger causes a queue and long waiting time for drivers.", metadata={"source_family": "github", "source_tier": 2}),
        ]
        out = build_issue_intelligence(posts, instr)
        self.assertEqual(len(out["issues"]), 1)
        self.assertEqual(out["issues"][0].independent_source_count, 2)


if __name__ == "__main__":
    unittest.main()
