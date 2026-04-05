import json
import os
from html import escape
from typing import Dict, List

from config import Instruction


def _empty_state(title: str, body: str) -> str:
    return (
        "<div class='empty-state'>"
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(body)}</p>"
        "</div>"
    )


def _base_styles() -> str:
    return """
    <style>
      :root {
        --bg: #f5f2ea;
        --panel: rgba(255, 255, 255, 0.86);
        --ink: #1f1a14;
        --muted: #6d655d;
        --accent: #0e6b62;
        --accent-soft: #d9efe8;
        --warn: #c1692b;
        --grid: rgba(31, 26, 20, 0.12);
        --border: rgba(31, 26, 20, 0.14);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(14, 107, 98, 0.16), transparent 28%),
          radial-gradient(circle at bottom right, rgba(193, 105, 43, 0.14), transparent 32%),
          linear-gradient(180deg, #f7f3ec 0%, #efe8dc 100%);
        font-family: Georgia, "Avenir Next", "Segoe UI", sans-serif;
      }
      main {
        max-width: 1260px;
        margin: 0 auto;
        padding: 32px 24px 48px;
      }
      h1, h2, h3 { margin: 0 0 12px; }
      h1 { font-size: 2.4rem; line-height: 1.05; }
      h2 { font-size: 1.25rem; }
      p, li, td, th, label, input, select, button {
        font-family: "Avenir Next", "Segoe UI", sans-serif;
      }
      p { color: var(--muted); line-height: 1.5; }
      .hero {
        display: grid;
        grid-template-columns: 2.1fr 1fr;
        gap: 20px;
        align-items: stretch;
        margin-bottom: 24px;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 18px;
        box-shadow: 0 12px 36px rgba(31, 26, 20, 0.08);
        padding: 20px;
        backdrop-filter: blur(8px);
      }
      .statline {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 16px;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 0.85rem;
        font-weight: 600;
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
      }
      .card {
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 16px;
        background: rgba(255, 255, 255, 0.7);
      }
      .card h3 {
        font-size: 1rem;
        margin-bottom: 8px;
      }
      .card p {
        margin: 0 0 12px;
        min-height: 48px;
      }
      .score-row, .mini-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      .score-row span, .mini-meta span {
        font-size: 0.9rem;
        color: var(--muted);
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 20px;
        margin-top: 20px;
      }
      .full-width { grid-column: 1 / -1; }
      .chart-frame {
        width: 100%;
        overflow-x: auto;
      }
      svg {
        width: 100%;
        height: auto;
        display: block;
      }
      .empty-state {
        border: 1px dashed var(--border);
        border-radius: 16px;
        padding: 24px;
        background: rgba(255, 255, 255, 0.55);
      }
      .empty-state h3 { margin-bottom: 6px; }
      .controls {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        align-items: end;
        margin-bottom: 16px;
      }
      .control {
        min-width: 180px;
      }
      .control label {
        display: block;
        margin-bottom: 6px;
        color: var(--muted);
        font-size: 0.92rem;
      }
      select, input[type="range"] {
        width: 100%;
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      th, td {
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        vertical-align: top;
        font-size: 0.95rem;
      }
      th {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--muted);
      }
      .table-wrap {
        overflow-x: auto;
      }
      .detail-layout {
        display: grid;
        grid-template-columns: 1.3fr 0.9fr;
        gap: 20px;
        margin-top: 20px;
      }
      .detail-block + .detail-block {
        margin-top: 16px;
      }
      .detail-list {
        margin: 0;
        padding-left: 18px;
      }
      .detail-list li {
        margin-bottom: 10px;
      }
      button.linkish {
        border: 0;
        background: none;
        color: var(--accent);
        padding: 0;
        cursor: pointer;
        font: inherit;
      }
      .muted { color: var(--muted); }
      .pill {
        display: inline-block;
        padding: 5px 9px;
        border-radius: 999px;
        background: rgba(14, 107, 98, 0.1);
        color: var(--accent);
        font-size: 0.82rem;
        margin: 4px 6px 0 0;
      }
      .footer-note {
        margin-top: 24px;
        color: var(--muted);
        font-size: 0.9rem;
      }
      @media (max-width: 900px) {
        .hero, .grid, .detail-layout {
          grid-template-columns: 1fr;
        }
        main {
          padding: 20px 14px 32px;
        }
      }
    </style>
    """


def _issue_cards(issues: List[dict]) -> str:
    if not issues:
        return _empty_state("No top issues", "Issue scoring produced no rows for the dashboard.")

    cards = []
    for issue in issues[:6]:
        cards.append(
            "<article class='card'>"
            f"<h3>{escape(issue['canonical_issue_id'])}</h3>"
            f"<p>{escape(issue['normalized_problem_statement'])}</p>"
            "<div class='score-row'>"
            f"<span>Priority {issue['priority_score']:.1f}</span>"
            f"<span>Opportunity {issue['opportunity_score']:.1f}</span>"
            f"<span>Confidence {issue['confidence_score']:.1f}</span>"
            "</div>"
            "<div class='mini-meta'>"
            f"<span>Evidence {issue['evidence_count']}</span>"
            f"<span>Independent {issue['independent_source_count']}</span>"
            f"<span>Freshness {issue['freshness_score']:.1f}</span>"
            "</div>"
            "</article>"
        )
    return "<div class='cards'>" + "".join(cards) + "</div>"


def _freshness_badges(issues: List[dict]) -> str:
    if not issues:
        return _empty_state("Freshness badges unavailable", "No issue rows are available to score freshness.")
    items = []
    for issue in issues[:8]:
        items.append(
            f"<span class='badge'>{escape(issue['canonical_issue_id'])}: freshness {issue['freshness_score']:.1f}</span>"
        )
    return "<div class='statline'>" + "".join(items) + "</div>"


def _svg_scatter(issues: List[dict]) -> str:
    if not issues:
        return _empty_state("Impact vs Confidence", "There are no issues to plot.")

    width = 720
    height = 360
    pad_left = 70
    pad_bottom = 48
    pad_top = 20
    pad_right = 20
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Impact vs Confidence scatter plot'>"
    ]
    for step in range(0, 101, 20):
        x = pad_left + plot_w * step / 100.0
        y = pad_top + plot_h - plot_h * step / 100.0
        parts.append(f"<line x1='{x:.1f}' y1='{pad_top}' x2='{x:.1f}' y2='{pad_top + plot_h}' stroke='var(--grid)' />")
        parts.append(f"<line x1='{pad_left}' y1='{y:.1f}' x2='{pad_left + plot_w}' y2='{y:.1f}' stroke='var(--grid)' />")
        parts.append(f"<text x='{x:.1f}' y='{height - 18}' text-anchor='middle' fill='var(--muted)' font-size='12'>{step}</text>")
        parts.append(f"<text x='54' y='{y + 4:.1f}' text-anchor='end' fill='var(--muted)' font-size='12'>{step}</text>")
    parts.append(f"<line x1='{pad_left}' y1='{pad_top + plot_h}' x2='{pad_left + plot_w}' y2='{pad_top + plot_h}' stroke='var(--ink)' />")
    parts.append(f"<line x1='{pad_left}' y1='{pad_top}' x2='{pad_left}' y2='{pad_top + plot_h}' stroke='var(--ink)' />")
    parts.append(f"<text x='{pad_left + plot_w / 2:.1f}' y='{height - 4}' text-anchor='middle' fill='var(--muted)' font-size='13'>Confidence</text>")
    parts.append(
        f"<text x='18' y='{pad_top + plot_h / 2:.1f}' text-anchor='middle' transform='rotate(-90 18 {pad_top + plot_h / 2:.1f})' fill='var(--muted)' font-size='13'>Opportunity</text>"
    )

    for issue in issues[:16]:
        x = pad_left + plot_w * max(0.0, min(issue["confidence_score"], 100.0)) / 100.0
        y = pad_top + plot_h - plot_h * max(0.0, min(issue["opportunity_score"], 100.0)) / 100.0
        radius = 7 + min(issue["evidence_count"], 10) * 1.1
        parts.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{radius:.1f}' fill='rgba(14, 107, 98, 0.26)' stroke='var(--accent)' stroke-width='2' />"
        )
        parts.append(
            f"<text x='{x:.1f}' y='{y - radius - 6:.1f}' text-anchor='middle' fill='var(--ink)' font-size='11'>{escape(issue['canonical_issue_id'])}</text>"
        )
    parts.append("</svg>")
    return "<div class='chart-frame'>" + "".join(parts) + "</div>"


def _svg_source_mix(source_mix: Dict[str, int]) -> str:
    items = [(key, value) for key, value in source_mix.items() if value]
    if not items:
        return _empty_state("Source Mix", "No source-family mix is available.")

    width = 520
    bar_h = 34
    pad = 18
    label_w = 120
    max_value = max(value for _, value in items)
    height = pad * 2 + len(items) * (bar_h + 10)
    parts = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Source mix bar chart'>"]
    for index, (label, value) in enumerate(items):
        y = pad + index * (bar_h + 10)
        bar_w = ((width - label_w - pad * 3) * value / max_value) if max_value else 0
        parts.append(f"<text x='{pad}' y='{y + 21}' fill='var(--muted)' font-size='13'>{escape(label)}</text>")
        parts.append(f"<rect x='{label_w}' y='{y}' width='{bar_w:.1f}' height='{bar_h}' rx='10' fill='rgba(193, 105, 43, 0.22)' />")
        parts.append(f"<text x='{label_w + bar_w + 8:.1f}' y='{y + 21}' fill='var(--ink)' font-size='13'>{value}</text>")
    parts.append("</svg>")
    return "<div class='chart-frame'>" + "".join(parts) + "</div>"


def _svg_time_trend(time_trend: List[dict]) -> str:
    if not time_trend:
        return _empty_state("Time Trend", "No dated evidence was available to build a trend line.")

    width = 720
    height = 280
    pad_left = 56
    pad_right = 20
    pad_top = 16
    pad_bottom = 42
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    max_value = max(item.get("evidence_count", 0) for item in time_trend) or 1
    step_x = plot_w / max(1, len(time_trend) - 1)
    points = []
    labels = []
    for index, item in enumerate(time_trend):
        x = pad_left + (index * step_x if len(time_trend) > 1 else plot_w / 2)
        y = pad_top + plot_h - (plot_h * item.get("evidence_count", 0) / max_value)
        points.append(f"{x:.1f},{y:.1f}")
        labels.append(
            f"<text x='{x:.1f}' y='{height - 12}' text-anchor='middle' fill='var(--muted)' font-size='11'>{escape(item['period'])}</text>"
        )

    parts = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Evidence count over time'>"]
    for step in range(0, max_value + 1, max(1, max_value // 4 or 1)):
        y = pad_top + plot_h - (plot_h * step / max_value)
        parts.append(f"<line x1='{pad_left}' y1='{y:.1f}' x2='{pad_left + plot_w}' y2='{y:.1f}' stroke='var(--grid)' />")
        parts.append(f"<text x='46' y='{y + 4:.1f}' text-anchor='end' fill='var(--muted)' font-size='12'>{step}</text>")
    parts.append(f"<polyline fill='none' stroke='var(--accent)' stroke-width='3' points='{' '.join(points)}' />")
    for point in points:
        x, y = point.split(",")
        parts.append(f"<circle cx='{x}' cy='{y}' r='4.5' fill='var(--accent)' />")
    parts.extend(labels)
    parts.append("</svg>")
    return "<div class='chart-frame'>" + "".join(parts) + "</div>"


def _svg_heatmap(heatmap: List[dict]) -> str:
    if not heatmap:
        return _empty_state("Category by Segment Heatmap", "No category and segment overlap data was available.")

    categories = []
    segments = []
    counts = {}
    for entry in heatmap:
        cat = entry["category_name"]
        seg = entry["segment_name"]
        counts[(cat, seg)] = entry["count"]
        if cat not in categories:
            categories.append(cat)
        if seg not in segments:
            segments.append(seg)

    cell_w = 120
    cell_h = 42
    left_w = 150
    top_h = 56
    width = left_w + len(segments) * cell_w + 10
    height = top_h + len(categories) * cell_h + 10
    max_count = max(counts.values()) or 1
    parts = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Category by segment heatmap'>"]
    for col, seg in enumerate(segments):
        x = left_w + col * cell_w + cell_w / 2
        parts.append(f"<text x='{x:.1f}' y='28' text-anchor='middle' fill='var(--muted)' font-size='12'>{escape(seg)}</text>")
    for row, cat in enumerate(categories):
        y = top_h + row * cell_h
        parts.append(f"<text x='{left_w - 10}' y='{y + 25}' text-anchor='end' fill='var(--muted)' font-size='12'>{escape(cat)}</text>")
        for col, seg in enumerate(segments):
            x = left_w + col * cell_w
            count = counts.get((cat, seg), 0)
            opacity = 0.12 + (0.78 * count / max_count if max_count else 0.0)
            parts.append(
                f"<rect x='{x}' y='{y}' width='{cell_w - 8}' height='{cell_h - 8}' rx='10' fill='rgba(14, 107, 98, {opacity:.3f})' stroke='var(--border)' />"
            )
            parts.append(
                f"<text x='{x + (cell_w - 8) / 2:.1f}' y='{y + 24}' text-anchor='middle' fill='var(--ink)' font-size='14'>{count}</text>"
            )
    parts.append("</svg>")
    return "<div class='chart-frame'>" + "".join(parts) + "</div>"


def _render_exec(data: dict) -> str:
    issues = data.get("issues", [])
    source_mix = data.get("source_mix", {})
    time_trend = data.get("time_trend", [])
    heatmap = data.get("heatmap", [])
    generated_at = escape(str(data.get("generated_at", "")))

    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Executive Dashboard</title>
  {_base_styles()}
</head>
<body>
  <main>
    <section class='hero'>
      <div class='panel'>
        <h1>Executive Dashboard</h1>
        <p>Issue priorities are rendered directly from <code>dashboard_data.json</code>, with score breakdowns and evidence counts carried through from Phase 3.</p>
        <div class='statline'>
          <span class='badge'>Generated {generated_at or 'n/a'}</span>
          <span class='badge'>Issues {len(issues)}</span>
          <span class='badge'>Source families {len(source_mix)}</span>
          <span class='badge'>Trend buckets {len(time_trend)}</span>
        </div>
      </div>
      <div class='panel'>
        <h2>Freshness Badges</h2>
        {_freshness_badges(issues)}
      </div>
    </section>

    <section class='panel'>
      <h2>Top Opportunity Cards</h2>
      <p>The top-ranked issues with confidence, evidence, and freshness context.</p>
      {_issue_cards(issues)}
    </section>

    <section class='grid'>
      <div class='panel'>
        <h2>Impact vs Confidence</h2>
        <p>Opportunity is on the vertical axis, confidence is on the horizontal axis, and bubble size reflects supporting evidence volume.</p>
        {_svg_scatter(issues)}
      </div>
      <div class='panel'>
        <h2>Source Mix</h2>
        <p>Source-family contribution across the scored evidence registry.</p>
        {_svg_source_mix(source_mix)}
      </div>
      <div class='panel'>
        <h2>Time Trend</h2>
        <p>Evidence volume over time, grouped by publication month.</p>
        {_svg_time_trend(time_trend)}
      </div>
      <div class='panel'>
        <h2>Category by Segment Heatmap</h2>
        <p>Cross-tab of categorized issues by detected segment.</p>
        {_svg_heatmap(heatmap)}
      </div>
    </section>

    <p class='footer-note'>This dashboard is self-contained HTML with inline SVG and no external runtime dependencies.</p>
  </main>
</body>
</html>"""


def _render_analyst(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    source_mix = data.get("source_mix", {})
    issues = data.get("issues", [])
    has_issues = bool(issues)
    empty_message = "" if has_issues else _empty_state(
        "No ranked issues",
        "There are no issues to drill into. Check the Phase 3 outputs and confirm the issue registry was populated.",
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Analyst Drilldown</title>
  {_base_styles()}
</head>
<body>
  <main>
    <section class='hero'>
      <div class='panel'>
        <h1>Analyst Drilldown</h1>
        <p>Ranked issue table, visible score breakdown columns, and supporting evidence detail sourced from the exported dashboard JSON.</p>
      </div>
      <div class='panel'>
        <h2>Source Families</h2>
        <div class='statline'>
          {"".join(f"<span class='badge'>{escape(k)} {v}</span>" for k, v in source_mix.items()) or "<span class='muted'>No source mix available.</span>"}
        </div>
      </div>
    </section>

    <section class='panel'>
      <div class='controls'>
        <div class='control'>
          <label for='family-filter'>Source family</label>
          <select id='family-filter'></select>
        </div>
        <div class='control'>
          <label for='confidence-filter'>Minimum confidence: <span id='confidence-value'>0</span></label>
          <input id='confidence-filter' type='range' min='0' max='100' value='0'>
        </div>
      </div>
      {empty_message}
      <div class='table-wrap'>
        <table>
          <thead>
            <tr>
              <th>Issue</th>
              <th>Problem</th>
              <th>Priority</th>
              <th>Opportunity</th>
              <th>Confidence</th>
              <th>Evidence</th>
              <th>Severity</th>
              <th>Corroboration</th>
              <th>Source quality</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id='issue-table-body'></tbody>
        </table>
      </div>
    </section>

    <section class='detail-layout'>
      <div class='panel' id='issue-detail-panel'></div>
      <div class='panel'>
        <div class='detail-block'>
          <h2>Filter Notes</h2>
          <p>Use the source-family filter to narrow by evidence mix and the confidence slider to focus on stronger corroboration.</p>
        </div>
        <div class='detail-block'>
          <h2>Current Dataset</h2>
          <p class='muted' id='dataset-summary'>{len(issues)} issues available.</p>
        </div>
      </div>
    </section>
  </main>

  <script>
    const DASHBOARD_DATA = {payload};
    const issues = Array.isArray(DASHBOARD_DATA.issues) ? DASHBOARD_DATA.issues : [];
    const familyFilter = document.getElementById('family-filter');
    const confidenceFilter = document.getElementById('confidence-filter');
    const confidenceValue = document.getElementById('confidence-value');
    const tableBody = document.getElementById('issue-table-body');
    const detailPanel = document.getElementById('issue-detail-panel');
    const datasetSummary = document.getElementById('dataset-summary');

    function esc(value) {{
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }}

    function familiesForIssue(issue) {{
      const mix = issue.source_mix || {{}};
      return Object.keys(mix);
    }}

    function component(issue, section, key) {{
      return (((issue.score_breakdown || {{}})[section] || {{}}).components || {{}})[key] || 0;
    }}

    function populateFilters() {{
      const families = new Set(['all']);
      issues.forEach(issue => familiesForIssue(issue).forEach(family => families.add(family)));
      familyFilter.innerHTML = Array.from(families)
        .map(family => `<option value="${{esc(family)}}">${{family === 'all' ? 'All families' : esc(family)}}</option>`)
        .join('');
    }}

    function filteredIssues() {{
      const family = familyFilter.value || 'all';
      const minConfidence = Number(confidenceFilter.value || 0);
      return issues.filter(issue => {{
        const familyMatch = family === 'all' || familiesForIssue(issue).includes(family);
        const confidenceMatch = Number(issue.confidence_score || 0) >= minConfidence;
        return familyMatch && confidenceMatch;
      }});
    }}

    function renderDetail(issue) {{
      if (!issue) {{
        detailPanel.innerHTML = `{_empty_state("No issue selected", "Adjust the filters or choose a row to inspect the score breakdown and evidence.")}`;
        return;
      }}
      const opportunity = (issue.score_breakdown || {{}}).opportunity || {{}};
      const confidence = (issue.score_breakdown || {{}}).confidence || {{}};
      const penalties = ((issue.score_breakdown || {{}}).penalties || {{}}).items || {{}};
      const evidence = Array.isArray(issue.top_supporting_evidence) ? issue.top_supporting_evidence : [];
      const penaltyItems = Object.keys(penalties).length
        ? Object.entries(penalties).map(([name, value]) => `<li><strong>${{esc(name)}}</strong>: ${{Number(value).toFixed(1)}}</li>`).join('')
        : '<li>No penalties applied.</li>';
      const evidenceItems = evidence.length
        ? evidence.map(item => `
            <li>
              <strong>${{esc(item.platform || 'unknown')}} / ${{esc(item.source_family || 'unknown')}}</strong><br>
              <span class="muted">${{esc(item.source_title || 'Untitled source')}}${{item.publication_date ? ' | ' + esc(item.publication_date) : ''}}</span><br>
              ${{esc(item.excerpt || '')}}
            </li>
          `).join('')
        : '<li>No supporting evidence available.</li>';
      const provenance = Array.isArray(issue.provenance_snippets) && issue.provenance_snippets.length
        ? issue.provenance_snippets.map(item => `<li>${{esc(item)}}</li>`).join('')
        : '<li>No provenance snippets available.</li>';

      detailPanel.innerHTML = `
        <h2>${{esc(issue.canonical_issue_id)}}${{issue.normalized_problem_statement ? ' - ' + esc(issue.normalized_problem_statement) : ''}}</h2>
        <div class="detail-block">
          <span class="pill">Priority ${{Number(issue.priority_score || 0).toFixed(1)}}</span>
          <span class="pill">Opportunity ${{Number(issue.opportunity_score || 0).toFixed(1)}}</span>
          <span class="pill">Confidence ${{Number(issue.confidence_score || 0).toFixed(1)}}</span>
          <span class="pill">Evidence ${{Number(issue.evidence_count || 0)}}</span>
          <span class="pill">Freshness ${{Number(issue.freshness_score || 0).toFixed(1)}}</span>
        </div>
        <div class="detail-block">
          <h3>Score Breakdown</h3>
          <p class="muted">Opportunity weighted score ${{Number(opportunity.weighted_score || 0).toFixed(1)}}. Confidence weighted score ${{Number(confidence.weighted_score || 0).toFixed(1)}}.</p>
          <div>
            <span class="pill">Severity ${{Number(component(issue, 'opportunity', 'severity')).toFixed(1)}}</span>
            <span class="pill">Urgency ${{Number(component(issue, 'opportunity', 'urgency')).toFixed(1)}}</span>
            <span class="pill">Independent frequency ${{Number(component(issue, 'opportunity', 'independent_frequency')).toFixed(1)}}</span>
            <span class="pill">Buyer intent ${{Number(component(issue, 'opportunity', 'buyer_intent')).toFixed(1)}}</span>
            <span class="pill">Business impact ${{Number(component(issue, 'opportunity', 'business_impact')).toFixed(1)}}</span>
            <span class="pill">Strategic fit ${{Number(component(issue, 'opportunity', 'strategic_fit')).toFixed(1)}}</span>
            <span class="pill">Source quality ${{Number(component(issue, 'confidence', 'source_quality')).toFixed(1)}}</span>
            <span class="pill">Corroboration ${{Number(component(issue, 'confidence', 'corroboration')).toFixed(1)}}</span>
            <span class="pill">Source diversity ${{Number(component(issue, 'confidence', 'source_diversity')).toFixed(1)}}</span>
            <span class="pill">Recency ${{Number(component(issue, 'confidence', 'recency')).toFixed(1)}}</span>
            <span class="pill">Specificity ${{Number(component(issue, 'confidence', 'specificity')).toFixed(1)}}</span>
            <span class="pill">Extraction quality ${{Number(component(issue, 'confidence', 'extraction_quality')).toFixed(1)}}</span>
          </div>
        </div>
        <div class="detail-block">
          <h3>Penalty Audit</h3>
          <ul class="detail-list">${{penaltyItems}}</ul>
        </div>
        <div class="detail-block">
          <h3>Provenance</h3>
          <ul class="detail-list">${{provenance}}</ul>
        </div>
        <div class="detail-block">
          <h3>Supporting Evidence</h3>
          <ul class="detail-list">${{evidenceItems}}</ul>
        </div>
      `;
    }}

    function renderTable() {{
      const rows = filteredIssues();
      datasetSummary.textContent = `${{rows.length}} issues after filters.`;
      if (!rows.length) {{
        tableBody.innerHTML = "<tr><td colspan='10'>No issues match the current filters.</td></tr>";
        renderDetail(null);
        return;
      }}
      tableBody.innerHTML = rows.map(issue => `
        <tr>
          <td>${{esc(issue.canonical_issue_id)}}</td>
          <td>${{esc(issue.normalized_problem_statement || '')}}</td>
          <td>${{Number(issue.priority_score || 0).toFixed(1)}}</td>
          <td>${{Number(issue.opportunity_score || 0).toFixed(1)}}</td>
          <td>${{Number(issue.confidence_score || 0).toFixed(1)}}</td>
          <td>${{Number(issue.evidence_count || 0)}}</td>
          <td>${{Number(component(issue, 'opportunity', 'severity')).toFixed(1)}}</td>
          <td>${{Number(component(issue, 'confidence', 'corroboration')).toFixed(1)}}</td>
          <td>${{Number(component(issue, 'confidence', 'source_quality')).toFixed(1)}}</td>
          <td><button class='linkish' type='button' data-issue-id='${{esc(issue.canonical_issue_id)}}'>Open</button></td>
        </tr>
      `).join('');

      tableBody.querySelectorAll('button[data-issue-id]').forEach(button => {{
        button.addEventListener('click', () => {{
          const issue = rows.find(item => item.canonical_issue_id === button.dataset.issueId);
          renderDetail(issue);
        }});
      }});

      renderDetail(rows[0]);
    }}

    confidenceFilter.addEventListener('input', () => {{
      confidenceValue.textContent = confidenceFilter.value;
      renderTable();
    }});
    familyFilter.addEventListener('change', renderTable);

    populateFilters();
    confidenceValue.textContent = confidenceFilter.value;
    renderTable();
  </script>
</body>
</html>"""


def generate_visualizations(generated_files: Dict[str, str], output_dir: str, instruction: Instruction) -> Dict[str, str]:
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    dashboard_json = generated_files.get("dashboard_data_json") or os.path.join(output_dir, "dashboard_data.json")
    if os.path.exists(dashboard_json):
        with open(dashboard_json, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = {
            "issues": [],
            "source_mix": {},
            "time_trend": [],
            "heatmap": [],
            "generated_at": "",
        }

    outputs: Dict[str, str] = {}
    json_out = os.path.join(viz_dir, "dashboard_data.json")
    with open(json_out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    outputs["visualizations_dashboard_data_json"] = json_out

    if instruction.visualization.executive_dashboard:
        exec_html = os.path.join(viz_dir, "executive_dashboard.html")
        with open(exec_html, "w", encoding="utf-8") as handle:
            handle.write(_render_exec(data))
        outputs["executive_dashboard_html"] = exec_html

    if instruction.visualization.analyst_drilldown:
        analyst_html = os.path.join(viz_dir, "analyst_drilldown.html")
        with open(analyst_html, "w", encoding="utf-8") as handle:
            handle.write(_render_analyst(data))
        outputs["analyst_drilldown_html"] = analyst_html

    return outputs
