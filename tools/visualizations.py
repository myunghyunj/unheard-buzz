from __future__ import annotations

import json
import os
from html import escape
from typing import Dict, List

from config import Instruction


def _json_blob(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _base_css() -> str:
    return """
    :root {
      --bg: #fafafa;
      --panel: #ffffff;
      --border: #d9d9d9;
      --text: #1f1f1f;
      --muted: #666666;
      --accent: #0f62fe;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }
    header { padding: 24px 28px 12px; }
    header h1 { margin: 0 0 6px; font-size: 28px; }
    header p { margin: 0; color: var(--muted); }
    main { padding: 0 28px 28px; }
    .grid { display: grid; gap: 16px; }
    .grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid.cards { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
    .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
    .panel h2, .panel h3 { margin: 0 0 10px; font-size: 18px; }
    .subtle { color: var(--muted); font-size: 13px; }
    .metric { font-size: 26px; font-weight: 700; margin-top: 8px; }
    .card-title { font-weight: 700; margin-bottom: 8px; }
    .badge { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px; font-size: 12px; margin-right: 6px; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-top: 1px solid var(--border); padding: 8px 6px; vertical-align: top; text-align: left; }
    thead th { border-top: none; color: var(--muted); font-weight: 600; }
    tr:hover { background: #f5f7fa; }
    .chart-wrap { width: 100%; overflow: auto; }
    .bar-row { display: grid; grid-template-columns: 160px 1fr 60px; gap: 10px; align-items: center; margin-bottom: 8px; }
    .bar-track { background: #eef2f7; border-radius: 999px; overflow: hidden; height: 12px; }
    .bar-fill { background: var(--accent); height: 100%; }
    .heat-grid { display: grid; gap: 4px; }
    .heat-row { display: grid; gap: 4px; grid-template-columns: 160px repeat(var(--cols), minmax(48px, 1fr)); align-items: center; }
    .heat-cell { border: 1px solid var(--border); border-radius: 6px; min-height: 34px; display: flex; align-items: center; justify-content: center; font-size: 12px; }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
    .controls input, .controls select { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: #fff; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr); gap: 16px; }
    .clickable tbody tr { cursor: pointer; }
    .evidence-item { border-top: 1px solid var(--border); padding: 10px 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    @media (max-width: 900px) {
      .grid.two, .layout { grid-template-columns: 1fr; }
    }
    """


def _shared_script() -> str:
    return """
    function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
    function svg(tag, attrs = {}, children = '') {
      const attr = Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(' ');
      return `<${tag} ${attr}>${children}</${tag}>`;
    }
    function renderScatter(containerId, issues) {
      const width = 560, height = 320, pad = 40;
      if (!issues.length) { document.getElementById(containerId).innerHTML = '<p class="subtle">No issue data.</p>'; return; }
      const maxEvidence = Math.max(...issues.map(i => i.evidence_count || 1), 1);
      const circles = issues.slice(0, 18).map(issue => {
        const x = pad + (issue.confidence_score / 100) * (width - pad * 2);
        const y = height - pad - (issue.opportunity_score / 100) * (height - pad * 2);
        const r = 5 + ((issue.evidence_count || 1) / maxEvidence) * 9;
        const title = `${issue.canonical_issue_id}: ${issue.normalized_problem_statement}`.replace(/"/g, '&quot;');
        return svg('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: r.toFixed(1), fill: '#0f62fe', opacity: '0.75' }) +
               svg('text', { x: (x + r + 4).toFixed(1), y: (y + 4).toFixed(1), 'font-size': '11', fill: '#333' }, issue.canonical_issue_id) +
               svg('title', {}, title);
      }).join('');
      const axes = [
        svg('line', { x1: pad, y1: height - pad, x2: width - pad, y2: height - pad, stroke: '#666' }),
        svg('line', { x1: pad, y1: pad, x2: pad, y2: height - pad, stroke: '#666' }),
        svg('text', { x: width / 2, y: height - 8, 'text-anchor': 'middle', 'font-size': '12', fill: '#555' }, 'Confidence'),
        svg('text', { x: 14, y: height / 2, transform: `rotate(-90 14 ${height / 2})`, 'text-anchor': 'middle', 'font-size': '12', fill: '#555' }, 'Opportunity'),
      ].join('');
      document.getElementById(containerId).innerHTML = svg('svg', { viewBox: `0 0 ${width} ${height}`, width: '100%', height: '320' }, axes + circles);
    }
    function renderTrend(containerId, points) {
      if (!points || !points.length) { document.getElementById(containerId).innerHTML = '<p class="subtle">No time series data.</p>'; return; }
      const width = 560, height = 250, pad = 34;
      const maxCount = Math.max(...points.map(p => p.count), 1);
      const coords = points.map((point, idx) => {
        const x = pad + idx * ((width - pad * 2) / Math.max(points.length - 1, 1));
        const y = height - pad - (point.count / maxCount) * (height - pad * 2);
        return { x, y, label: point.period, count: point.count };
      });
      const poly = coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
      const labels = coords.map(c => svg('text', { x: c.x.toFixed(1), y: (height - 10).toFixed(1), 'text-anchor': 'middle', 'font-size': '10', fill: '#555' }, c.label)).join('');
      const pointsSvg = coords.map(c => svg('circle', { cx: c.x.toFixed(1), cy: c.y.toFixed(1), r: '4', fill: '#0f62fe' }) + svg('title', {}, `${c.label}: ${c.count}`)).join('');
      const axes = svg('line', { x1: pad, y1: height - pad, x2: width - pad, y2: height - pad, stroke: '#666' }) + svg('line', { x1: pad, y1: pad, x2: pad, y2: height - pad, stroke: '#666' });
      document.getElementById(containerId).innerHTML = svg('svg', { viewBox: `0 0 ${width} ${height}`, width: '100%', height: '250' }, axes + svg('polyline', { fill: 'none', stroke: '#0f62fe', 'stroke-width': '2.5', points: poly }) + pointsSvg + labels);
    }
    function renderSourceMix(containerId, sourceMix) {
      const entries = Object.entries(sourceMix || {}).sort((a, b) => b[1] - a[1]);
      if (!entries.length) { document.getElementById(containerId).innerHTML = '<p class="subtle">No source mix data.</p>'; return; }
      const maxValue = Math.max(...entries.map(([, value]) => value), 1);
      const rows = entries.map(([label, value]) => `<div class="bar-row"><div>${label}</div><div class="bar-track"><div class="bar-fill" style="width:${(value / maxValue) * 100}%"></div></div><div class="mono">${value}</div></div>`).join('');
      document.getElementById(containerId).innerHTML = rows;
    }
    function renderHeatmap(containerId, heatmap) {
      const rows = heatmap?.rows || [];
      const cols = heatmap?.cols || [];
      if (!rows.length || !cols.length) { document.getElementById(containerId).innerHTML = '<p class="subtle">No category/segment matrix.</p>'; return; }
      let maxValue = 0;
      rows.forEach(row => cols.forEach(col => { maxValue = Math.max(maxValue, heatmap.values?.[row]?.[col] || 0); }));
      const header = `<div class="heat-row" style="--cols:${cols.length}"><div></div>${cols.map(col => `<div class="subtle">${col}</div>`).join('')}</div>`;
      const body = rows.map(row => {
        const cells = cols.map(col => {
          const value = heatmap.values?.[row]?.[col] || 0;
          const shade = maxValue ? Math.round(245 - ((value / maxValue) * 120)) : 245;
          return `<div class="heat-cell" style="background:rgb(${shade},${shade},255)">${value}</div>`;
        }).join('');
        return `<div class="heat-row" style="--cols:${cols.length}"><div>${row}</div>${cells}</div>`;
      }).join('');
      document.getElementById(containerId).innerHTML = `<div class="heat-grid">${header}${body}</div>`;
    }
    function renderIssueTable(containerId, issues) {
      const rows = issues.slice(0, 15).map(issue => `<tr><td>${issue.canonical_issue_id}</td><td>${issue.normalized_problem_statement}</td><td>${issue.priority_score}</td><td>${issue.evidence_count}</td><td>${(issue.flags || []).join(', ')}</td></tr>`).join('');
      document.getElementById(containerId).innerHTML = `<table><thead><tr><th>Issue</th><th>Problem statement</th><th>Priority</th><th>Evidence</th><th>Flags</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    function cardHtml(issue) {
      const flags = (issue.flags || []).map(flag => `<span class="badge">${flag}</span>`).join('');
      return `<div class="panel"><div class="card-title">${issue.canonical_issue_id}</div><div>${issue.normalized_problem_statement}</div><div class="metric">${issue.priority_score}</div><div class="subtle">Opportunity ${issue.opportunity_score} · Confidence ${issue.confidence_score}</div><div class="subtle">Evidence ${issue.evidence_count} · Independent ${issue.independent_source_count} · Freshness ${issue.freshness_score || 0}</div><div style="margin-top:8px">${flags}</div></div>`;
    }
    function renderCards(containerId, issues) {
      document.getElementById(containerId).innerHTML = issues.slice(0, 6).map(cardHtml).join('');
    }
    function renderAnalystTable(containerId, issues, onSelect) {
      const tbody = issues.map((issue, idx) => `<tr data-idx="${idx}"><td>${issue.canonical_issue_id}</td><td>${issue.normalized_problem_statement}</td><td>${issue.priority_score}</td><td>${issue.opportunity_score}</td><td>${issue.confidence_score}</td><td>${issue.evidence_count}</td><td>${issue.independent_source_count}</td></tr>`).join('');
      document.getElementById(containerId).innerHTML = `<table class="clickable"><thead><tr><th>Issue</th><th>Problem statement</th><th>Priority</th><th>Opportunity</th><th>Confidence</th><th>Evidence</th><th>Independent</th></tr></thead><tbody>${tbody}</tbody></table>`;
      document.querySelectorAll(`#${containerId} tbody tr`).forEach(row => row.addEventListener('click', () => onSelect(Number(row.dataset.idx))));
    }
    function renderIssueDetails(containerId, issue) {
      if (!issue) { document.getElementById(containerId).innerHTML = '<p class="subtle">Select an issue.</p>'; return; }
      const oppBreak = Object.entries(issue.score_breakdown?.opportunity || {}).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
      const confBreak = Object.entries(issue.score_breakdown?.confidence || {}).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
      const penalties = Object.entries(issue.score_breakdown?.penalties || {}).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('') || '<tr><td colspan="2" class="subtle">No penalties</td></tr>';
      const evidence = (issue.supporting_evidence || []).map(item => `<div class="evidence-item"><div><span class="badge">${item.platform}</span><span class="badge">${item.source_family}</span><span class="badge">tier ${item.source_tier}</span></div><div class="subtle">${item.publication_date || 'undated'} ${item.source_title || ''}</div><div>${item.excerpt || ''}</div><div class="subtle">Consequence: ${item.business_consequence || '-'} · Buyer role: ${item.buyer_role || '-'} · Segment: ${item.segment || '-'}</div></div>`).join('');
      document.getElementById(containerId).innerHTML = `
        <h2>${issue.canonical_issue_id}</h2>
        <p>${issue.normalized_problem_statement}</p>
        <p class="subtle">Priority ${issue.priority_score} · Opportunity ${issue.opportunity_score} · Confidence ${issue.confidence_score} · Freshness ${issue.freshness_score || 0}</p>
        <div>${(issue.flags || []).map(flag => `<span class="badge">${flag}</span>`).join('')}</div>
        <h3 style="margin-top:16px">Score breakdown</h3>
        <div class="grid two">
          <div class="panel"><h3>Opportunity</h3><table><tbody>${oppBreak}</tbody></table></div>
          <div class="panel"><h3>Confidence</h3><table><tbody>${confBreak}</tbody></table></div>
        </div>
        <div class="panel" style="margin-top:12px"><h3>Penalties</h3><table><tbody>${penalties}</tbody></table></div>
        <div class="panel" style="margin-top:12px"><h3>Evidence provenance</h3>${evidence || '<p class="subtle">No evidence attached.</p>'}</div>
      `;
    }
    """


def _render_exec(data: dict) -> str:
    template = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Executive Dashboard</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Executive dashboard</h1>
    <p>Issue-level opportunity, confidence, evidence, freshness, and source mix.</p>
  </header>
  <main>
    <section class='grid cards' id='top-cards'></section>
    <section class='grid two' style='margin-top:16px'>
      <div class='panel'><h2>Impact vs confidence</h2><div class='subtle'>Bubble size reflects evidence count.</div><div class='chart-wrap' id='scatter'></div></div>
      <div class='panel'><h2>Source mix</h2><div class='subtle'>Counts are grouped by source family.</div><div id='source-mix'></div></div>
    </section>
    <section class='grid two' style='margin-top:16px'>
      <div class='panel'><h2>Time trend</h2><div class='subtle'>Monthly count of issue evidence.</div><div class='chart-wrap' id='trend'></div></div>
      <div class='panel'><h2>Category by segment heatmap</h2><div class='subtle'>Cells show issue evidence counts.</div><div id='heatmap'></div></div>
    </section>
    <section class='panel' style='margin-top:16px'><h2>Top issues</h2><div id='issue-table'></div></section>
  </main>
  <script>
    const DATA = __DATA__;
    __SCRIPT__
    renderCards('top-cards', DATA.issues || []);
    renderScatter('scatter', DATA.issues || []);
    renderSourceMix('source-mix', DATA.source_mix || {});
    renderTrend('trend', DATA.time_trend || []);
    renderHeatmap('heatmap', DATA.heatmap || {});
    renderIssueTable('issue-table', DATA.issues || []);
  </script>
</body>
</html>"""
    return template.replace('__CSS__', _base_css()).replace('__DATA__', _json_blob(data)).replace('__SCRIPT__', _shared_script())


def _render_analyst(data: dict) -> str:
    template = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Analyst Drilldown</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Analyst drilldown</h1>
    <p>Filter issues, inspect score components, and trace supporting evidence.</p>
  </header>
  <main>
    <section class='panel'>
      <div class='controls'>
        <input id='search' type='search' placeholder='Search problem statement'>
        <select id='family-filter'><option value=''>All source families</option></select>
        <select id='category-filter'><option value=''>All categories</option></select>
        <select id='segment-filter'><option value=''>All segments</option></select>
        <label class='subtle'>Min confidence <input id='confidence-filter' type='range' min='0' max='100' value='0'></label>
        <span id='confidence-label' class='subtle'>0</span>
      </div>
      <div class='layout'>
        <div class='panel'><div id='analyst-table'></div></div>
        <div class='panel' id='details'><p class='subtle'>Select an issue to inspect evidence and score breakdown.</p></div>
      </div>
    </section>
  </main>
  <script>
    const DATA = __DATA__;
    __SCRIPT__
    const issues = DATA.issues || [];
    const familySelect = document.getElementById('family-filter');
    const categorySelect = document.getElementById('category-filter');
    const segmentSelect = document.getElementById('segment-filter');
    const searchInput = document.getElementById('search');
    const confidenceFilter = document.getElementById('confidence-filter');
    const confidenceLabel = document.getElementById('confidence-label');
    const families = [...new Set(issues.flatMap(issue => Object.keys(issue.source_mix || {})))].sort();
    const categories = [...new Set(issues.flatMap(issue => issue.categories || []))].sort();
    const segments = [...new Set(issues.flatMap(issue => issue.segments || []))].sort();
    families.forEach(family => familySelect.insertAdjacentHTML('beforeend', `<option value="${family}">${family}</option>`));
    categories.forEach(category => categorySelect.insertAdjacentHTML('beforeend', `<option value="${category}">${category}</option>`));
    segments.forEach(segment => segmentSelect.insertAdjacentHTML('beforeend', `<option value="${segment}">${segment}</option>`));
    function filteredIssues() {
      const term = (searchInput.value || '').toLowerCase();
      const family = familySelect.value;
      const category = categorySelect.value;
      const segment = segmentSelect.value;
      const minConfidence = Number(confidenceFilter.value || 0);
      confidenceLabel.textContent = String(minConfidence);
      return issues.filter(issue => {
        if (term && !`${issue.canonical_issue_id} ${issue.normalized_problem_statement}`.toLowerCase().includes(term)) return false;
        if (family && !(issue.source_mix || {}).hasOwnProperty(family)) return false;
        if (category && !(issue.categories || []).includes(category)) return false;
        if (segment && !(issue.segments || []).includes(segment)) return false;
        if ((issue.confidence_score || 0) < minConfidence) return false;
        return true;
      });
    }
    function refresh(selectionIndex = 0) {
      const rows = filteredIssues();
      renderAnalystTable('analyst-table', rows, index => renderIssueDetails('details', rows[index]));
      renderIssueDetails('details', rows[selectionIndex] || null);
    }
    [searchInput, familySelect, categorySelect, segmentSelect, confidenceFilter].forEach(node => node.addEventListener('input', () => refresh(0)));
    refresh();
  </script>
</body>
</html>"""
    return template.replace('__CSS__', _base_css()).replace('__DATA__', _json_blob(data)).replace('__SCRIPT__', _shared_script())


def generate_visualizations(generated_files: Dict[str, str], output_dir: str, instruction: Instruction) -> Dict[str, str]:
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    dashboard_json = generated_files.get("dashboard_data_json") or os.path.join(output_dir, "dashboard_data.json")
    if os.path.exists(dashboard_json):
        with open(dashboard_json, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = {"issues": [], "source_mix": {}, "time_trend": [], "heatmap": {"rows": [], "cols": [], "values": {}}}

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
