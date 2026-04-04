import os, sys, tempfile, unittest
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from config import Instruction
from visualizations import generate_visualizations

class VisualizationSmokeTest(unittest.TestCase):
    def test_visualization_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "dashboard_data.json")
            with open(fp, "w", encoding="utf-8") as h:
                h.write('{"issues": [], "source_mix": {}}')
            out = generate_visualizations({"dashboard_data_json": fp}, d, Instruction())
            self.assertTrue(os.path.exists(out["executive_dashboard_html"]))
            self.assertTrue(os.path.exists(out["analyst_drilldown_html"]))

if __name__ == "__main__":
    unittest.main()
