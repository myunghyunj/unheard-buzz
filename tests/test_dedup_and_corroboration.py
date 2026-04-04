import os, sys, tempfile, textwrap, unittest
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from analyzer import filter_posts
from config import SocialPost, load_instruction

class DedupCorroborationTest(unittest.TestCase):
    def test_exact_duplicate_filtered(self):
        y = textwrap.dedent('''
        project: {name: x, description: x}
        analysis:
          min_comment_words: 2
          relevance_keywords: ["broken"]
          categories:
            C1: {name: C1, description: d, keywords: ["broken"]}
        platforms:
          reddit: {enabled: true, subreddits: [a], search_queries: [b]}
        ''')
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as h:
            h.write(y); p = h.name
        try:
            i = load_instruction(p)
        finally:
            os.unlink(p)
        posts = [
            SocialPost(post_id="1", platform="reddit", source_id="s", source_title="t", author="a", text="broken charger today"),
            SocialPost(post_id="2", platform="reddit", source_id="s", source_title="t", author="a", text="broken charger today"),
        ]
        out = filter_posts(posts, i)
        self.assertEqual(len(out), 1)

if __name__ == "__main__":
    unittest.main()
