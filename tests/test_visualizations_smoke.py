import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from config import Instruction
from visualizations import generate_visualizations


class VisualizationSmokeTest(unittest.TestCase):
    def test_visualization_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            dashboard_path = os.path.join(directory, "dashboard_data.json")
            with open(dashboard_path, "w", encoding="utf-8") as handle:
                handle.write('{"issues": [{"canonical_issue_id": "ISSUE-0001", "normalized_problem_statement": "Broken checkout after release", "priority_score": 82.0, "opportunity_score": 88.0, "confidence_score": 77.0, "evidence_count": 3, "independent_source_count": 2, "freshness_score": 69.0, "flags": ["corroborated"], "source_mix": {"community": 2, "github": 1}, "score_breakdown": {"opportunity": {"severity": 90}, "confidence": {"source_quality": 80}, "penalties": {}}, "supporting_evidence": []}], "source_mix": {"community": 2, "github": 1}, "time_trend": [{"period": "2026-03", "count": 3}], "heatmap": {"rows": ["OPS"], "cols": ["SEG1"], "values": {"OPS": {"SEG1": 3}}}}')
            outputs = generate_visualizations({"dashboard_data_json": dashboard_path}, directory, Instruction())
            self.assertTrue(os.path.exists(outputs["executive_dashboard_html"]))
            self.assertTrue(os.path.exists(outputs["analyst_drilldown_html"]))
            with open(outputs["executive_dashboard_html"], "r", encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn("Impact vs confidence", html)
            self.assertIn("Category by segment heatmap", html)


if __name__ == "__main__":
    unittest.main()
