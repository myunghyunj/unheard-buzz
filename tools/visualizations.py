import json
import os
from typing import Dict

from config import Instruction


def _render_exec(data: dict) -> str:
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Executive Dashboard</title>
<style>body{{font-family:Arial;margin:24px}} .cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}} .card{{border:1px solid #ddd;padding:12px;border-radius:8px}} table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:6px}}</style>
</head><body>
<h1>Executive Dashboard</h1>
<p>Top opportunity cards and impact vs confidence framing.</p>
<div class='cards'>{''.join([f"<div class='card'><b>{i['canonical_issue_id']}</b><br/>Priority {i['priority_score']}<br/>Confidence {i['confidence_score']}<br/>Evidence {i['evidence_count']}</div>" for i in data.get('issues',[])[:6]])}</div>
<h2>Source Mix</h2>
<table><tr><th>Source family</th><th>Count</th></tr>{''.join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k,v in data.get('source_mix',{}).items()])}</table>
<h2>Impact vs Confidence</h2><p>Frequency is shown separately via evidence counts in cards/table.</p>
</body></html>"""


def _render_analyst(data: dict) -> str:
    rows = ''.join([f"<tr><td>{i['canonical_issue_id']}</td><td>{i['normalized_problem_statement']}</td><td>{i['priority_score']}</td><td>{i['opportunity_score']}</td><td>{i['confidence_score']}</td><td>{i['evidence_count']}</td><td>{i.get('provenance_snippet','')}</td></tr>" for i in data.get('issues',[])])
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Analyst Drilldown</title><style>body{{font-family:Arial;margin:24px}} table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:6px}}</style></head><body>
<h1>Analyst Drilldown</h1>
<p>Ranked issue table with provenance and score breakdown columns.</p>
<table><tr><th>Issue</th><th>Problem statement</th><th>Priority</th><th>Opportunity</th><th>Confidence</th><th>Evidence</th><th>Provenance</th></tr>{rows}</table>
</body></html>"""


def generate_visualizations(generated_files: Dict[str, str], output_dir: str, instruction: Instruction) -> Dict[str, str]:
    viz_dir = os.path.join(output_dir, "visualizations")
    os.makedirs(viz_dir, exist_ok=True)

    dashboard_json = generated_files.get("dashboard_data_json") or os.path.join(output_dir, "dashboard_data.json")
    if os.path.exists(dashboard_json):
        with open(dashboard_json, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = {"issues": [], "source_mix": {}}

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
