# Graphics Agent Guide

Use this guide when a post-run graphics agent is responsible for turning pipeline outputs into charts, static previews, or presentation-ready visual assets.

Graphics is a fourth agent role alongside search, analysis, and writing.
It is not a platform collector.
It should run after the core outputs exist so it can reuse the same evidence as the analysis and writing agents.

## Inputs

High-value inputs usually include:

- `output/summary_stats.json`
- `output/all_posts.csv`
- `output/coded_posts.csv`
- `output/coded_comments.csv`
- `output/summary_report.md`
- `output/quotable_excerpts.md`
- `output/trend_report.md`
- `output/validation_report.md` when available

## Expected outputs

Write graphics artifacts into `output/visualizations/`.

Preferred deliverables:

- static SVG exports for vector reuse and editing
- static PNG exports for slides, docs, and quick review
- an editable AI master when Illustrator is used for the finishing pass
- interactive HTML charts for exploration when interactivity adds value
- clear filenames such as `prosthetics_category_share_donut.html`
- a title, subtitle, unit note, and source note on every chart

For repo outputs, treat `svg` and `png` as the default export pair.
If an `.ai` file exists, keep it aligned with the exported `svg` and `png` using the same basename.

## Chart selection

Choose the simplest chart that communicates the story.

| Chart type | Best for | Avoid when |
| --- | --- | --- |
| Bar chart | category rankings, platform comparisons, before vs after gaps | there are too many tiny categories |
| Pie or donut | part-to-whole composition with a small number of slices | precise comparison matters more than composition |
| Sankey | multi-stage drop-off, transitions, or source-to-outcome flows | the data contains cycles, self-links, or unclear stage order |
| Bivariate choropleth | geography with two normalized signals, such as poverty vs amputation rate | the geography join is weak or the legend would be hard to read |
| Word cloud | secondary texture for language or phrase recall | it would be the only quantitative visual |

Treat word clouds as supporting visuals, not the lead chart.
For geographic visuals, always show the legend and explain the normalization.

## Sankey benchmark

Benchmark Sankey work against the Google Charts Sankey documentation:

- [Google Charts Sankey](https://developers.google.com/chart/interactive/docs/gallery/sankey?hl=ko)

Key implementation rules from that reference:

- Sankey data is row-based with `From`, `To`, and `Weight` columns.
- Avoid self-links and cycles, or the chart may fail to render.
- Use `google.charts.load('current', {packages: ['sankey']})` and `google.visualization.Sankey(...)`.
- Tune `sankey.iterations` for complex layouts.
- Tune `sankey.node.width`, `sankey.node.nodePadding`, and `sankey.node.labelPadding` for readability.
- Prefer `sankey.link.colorMode: 'gradient'` when stage transitions matter.
- Use `tooltip.isHtml` when richer tooltips improve the interactive version.

The repo starter file at `examples/visualization_starters/google_sankey_template.html` is the default benchmark scaffold.
It stays general on purpose, but includes a prosthetics-funnel sample as one concrete example.
Use it as a starting point for prosthetics funnels, complaint-to-solution flows, or platform-to-category-to-segment flows.

## Style rules

Aim for editorial quality rather than default chart output.

- Start from a clean, light background unless the surrounding deck or site already dictates a different style.
- Use a deliberate color story instead of default chart palettes.
- Keep labels readable in static export, not just on hover.
- Add a short framing subtitle so the chart tells the takeaway, not just the metric.
- Add source provenance and units directly on the visual.
- Prefer one strong chart over a dashboard of weak ones.
- When exporting a deliverable bundle, keep `svg`, `png`, and optional `ai` versions visually matched.

## Suggested workflow

1. Wait for phase 3 outputs to finish.
2. Read the summary and quotable excerpts to understand the core story.
3. Inspect the structured outputs to verify the numbers.
4. Choose one lead chart and one supporting chart.
5. Export `svg` and `png` for every approved chart.
6. Save an `ai` master too when Illustrator or another manual vector pass is part of the workflow.
7. Export an interactive HTML version when practical.
8. Hand the final assets back to the writing agent so captions and narrative stay aligned.
