import os, sys, unittest
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from config import Instruction, SocialPost
from issue_intelligence import apply_source_policy

class SourcePolicyTest(unittest.TestCase):
    def test_defaults(self):
        i = Instruction()
        p = SocialPost(post_id="1", platform="reddit", source_id="s", source_title="t", author="a", text="x")
        apply_source_policy(p, i)
        self.assertEqual(p.source_tier, 4)
        self.assertTrue(p.independence_key)

if __name__ == "__main__":
    unittest.main()
