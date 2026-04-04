import os, sys, unittest
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from config import Instruction, SocialPost
from issue_intelligence import build_issue_intelligence

class IssueClusterTest(unittest.TestCase):
    def test_cluster_creation(self):
        instr = Instruction(relevance_keywords=["broken"])
        posts = [
            SocialPost(post_id="1", platform="reddit", source_id="s", source_title="t", author="a", text="broken charger issue"),
            SocialPost(post_id="2", platform="reddit", source_id="s", source_title="t", author="a", text="broken charger issue again"),
        ]
        out = build_issue_intelligence(posts, instr)
        self.assertGreaterEqual(len(out["issues"]), 1)

if __name__ == "__main__":
    unittest.main()
