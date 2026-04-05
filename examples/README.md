# Examples

This folder now contains three kinds of artifacts:

- `*.yaml` instruction briefs that can be executed with `python3 tools/run.py --instruction ...`
- sample-output bundles that show what a completed analysis package can look like
- visualization starter files that the graphics agent can adapt after a run

Current sample-output bundle:

- `amputee_sample_output/` - a curated artifact set corresponding to `amputee.yaml`
- `visualization_starters/google_sankey_template.html` - a reusable general Sankey starter with a prosthetics funnel as the included sample example

Suggested flow:

1. Read `amputee.yaml` to understand the research brief.
2. Open the sample-output README inside `amputee_sample_output/` to see the packaged outputs.
3. Inspect the reports, decision artifacts, registries, dashboards, and checkpoints to understand the expected output shape.
4. Use built-in dashboards first; adapt a visualization starter only if you need additional presentation polish.


## v4 Issue intelligence outputs

New structured outputs are available in addition to legacy exports:
- `issue_registry.csv`
- `evidence_registry.csv`
- `source_registry_enriched.csv`
- `dashboard_data.json`
- `output/visualizations/executive_dashboard.html`
- `output/visualizations/analyst_drilldown.html`

## Modern consultant artifacts

Current example cases should be read as consultant runs, not just collection demos.
Important artifacts now include:

- `decision_memo.md`
- `opportunity_map.csv`
- `recommendation_cards.json`
- `annotation_pack.csv`
- `eval_report.md`
- `run_manifest.json`
- `history_diff.md` when state/history is enabled
