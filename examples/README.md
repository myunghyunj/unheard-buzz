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
3. Inspect the reports, CSV exports, and checkpoints to understand the expected output shape.
4. Adapt a visualization starter once you know which story the graphics agent should tell.
