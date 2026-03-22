# Amputee Sample Output

This folder is a sample output package for **amputee.yaml**.

It was organized from a prior amputee analysis run so future users can see the intended output shape without rerunning the whole pipeline first.

## Layout

- `reports/`
- `data/`
- `visualizations/`
- `checkpoints/`

## Contents

`reports/`

- `summary_report.md` - executive summary, rankings, co-occurrence, and key stats
- `quotable_excerpts.md` - high-signal voice-of-customer excerpts
- `validation_report.md` - literature cross-reference and gap framing

`data/`

- `summary_stats.json` - structured aggregate metrics
- `channel_registry.csv` - sampled YouTube channel registry
- `video_registry.csv` - sampled YouTube video registry
- `coded_comments.csv` - coded comment-level export from the prior run

`visualizations/`

- `wish_intensity_donut_clean.svg` - static preview suitable for README and docs
- `wish_intensity_donut_clean.html` - interactive version visualized via Claude after results were retrieved from the pipeline

`checkpoints/`

- phase snapshots from the prior run
- transcript checkpoints nested under `checkpoints/transcript/`

## Notes

- This package is intentionally preserved as a realistic reference bundle, not a normalized test fixture.
- The included files reflect the prior run's schema and naming, so they may be slightly richer or different from the latest generated outputs.
- If you want to compare against the current pipeline, rerun the amputee example and diff the new output directory against this folder.
