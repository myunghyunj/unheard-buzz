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
    def test_visualization_outputs_contain_real_dashboard_sections(self):
        dashboard_payload = """
        {
          "issues": [
            {
              "canonical_issue_id": "ISSUE-0001",
              "normalized_problem_statement": "Billing export is broken and blocks finance every day.",
              "priority_score": 82.4,
              "opportunity_score": 88.0,
              "confidence_score": 77.0,
              "evidence_count": 3,
              "independent_source_count": 2,
              "source_family_count": 2,
              "freshness_score": 71.2,
              "source_mix": {"github": 1, "community": 2},
              "score_breakdown": {
                "opportunity": {"components": {"severity": 92.0}},
                "confidence": {"components": {"corroboration": 60.0, "source_quality": 82.0}},
                "penalties": {"items": {}, "total": 0.0}
              },
              "provenance_snippet": "github:github: Billing export is broken and blocks finance every day.",
              "provenance_snippets": ["github:github: Billing export is broken and blocks finance every day."],
              "top_supporting_evidence": [
                {
                  "platform": "github_issues",
                  "source_family": "github",
                  "source_title": "Billing export",
                  "publication_date": "2026-04-01T00:00:00+00:00",
                  "excerpt": "Billing export is broken and blocks finance every day."
                }
              ]
            }
          ],
          "source_mix": {"github": 1, "community": 2},
          "time_trend": [{"period": "2026-04", "evidence_count": 3, "issue_count": 1, "source_mix": {"github": 1, "community": 2}}],
          "heatmap": [{"category_name": "Operations", "segment_name": "Finance", "count": 3}],
          "generated_at": "2026-04-05T12:00:00"
        }
        """
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "dashboard_data.json")
            with open(fp, "w", encoding="utf-8") as handle:
                handle.write(dashboard_payload)
            out = generate_visualizations({"dashboard_data_json": fp}, d, Instruction())
            self.assertTrue(os.path.exists(out["executive_dashboard_html"]))
            self.assertTrue(os.path.exists(out["analyst_drilldown_html"]))
            self.assertTrue(os.path.exists(out["visualizations_dashboard_data_json"]))

            with open(out["executive_dashboard_html"], "r", encoding="utf-8") as handle:
                exec_html = handle.read()
            with open(out["analyst_drilldown_html"], "r", encoding="utf-8") as handle:
                analyst_html = handle.read()

            self.assertIn("Impact vs Confidence", exec_html)
            self.assertIn("Source Mix", exec_html)
            self.assertIn("Time Trend", exec_html)
            self.assertIn("Category by Segment Heatmap", exec_html)
            self.assertIn("Analyst Drilldown", analyst_html)
            self.assertIn("Minimum confidence", analyst_html)
            self.assertIn("Billing export is broken", analyst_html)


if __name__ == "__main__":
    unittest.main()
