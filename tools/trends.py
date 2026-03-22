"""Google Trends analysis -- provides market context before platform scraping.

Uses pytrends (free, no API key required) to assess search interest,
trend direction, and related queries for the instruction's relevance keywords.
This runs as Phase 0 of the pipeline, producing a trend_report.md before
any platform agents begin collecting data.
"""

import logging
import os
import re
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from pytrends.request import TrendReq
    HAS_PYTRENDS = True
except ImportError:
    HAS_PYTRENDS = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEFRAME = "today 5-y"
_RISING_THRESHOLD = 15    # % YoY change to classify as rising
_FALLING_THRESHOLD = -15  # % YoY change to classify as falling
_RETRY_WAIT_SECONDS = 60
_MAX_RETRIES = 3
_TOP_REGIONS = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_pytrends(retries: int = _MAX_RETRIES) -> Optional["TrendReq"]:
    """Create a TrendReq instance with retry on rate-limit errors."""
    for attempt in range(1, retries + 1):
        try:
            pt = TrendReq(hl="en-US", tz=360)
            return pt
        except Exception as exc:
            if "429" in str(exc) or "Too Many Requests" in str(exc):
                logger.warning(
                    "Rate-limited by Google Trends (attempt %d/%d). "
                    "Retrying in %ds...", attempt, retries, _RETRY_WAIT_SECONDS,
                )
                time.sleep(_RETRY_WAIT_SECONDS)
            else:
                logger.error("Failed to initialize pytrends: %s", exc)
                return None
    logger.error("Exhausted retries for Google Trends connection.")
    return None


def _safe_build_payload(pt: "TrendReq", keywords: List[str],
                        timeframe: str, retries: int = _MAX_RETRIES) -> bool:
    """Build payload with retry on 429 errors. Returns True on success."""
    for attempt in range(1, retries + 1):
        try:
            pt.build_payload(keywords, timeframe=timeframe)
            return True
        except Exception as exc:
            if "429" in str(exc) or "Too Many Requests" in str(exc):
                logger.warning(
                    "Rate-limited during build_payload (attempt %d/%d). "
                    "Retrying in %ds...", attempt, retries, _RETRY_WAIT_SECONDS,
                )
                time.sleep(_RETRY_WAIT_SECONDS)
            else:
                logger.error("build_payload failed: %s", exc)
                return False
    return False


def _calculate_trend_metrics(df) -> dict:
    """Calculate YoY change and trend direction from interest-over-time DataFrame.

    Compares the average of the last 12 months against the previous 12 months.
    Returns dict with trend_direction, yoy_change_pct per keyword.
    """
    metrics = {}
    if df is None or df.empty:
        return metrics

    # Drop isPartial column if present
    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    for col in df.columns:
        series = df[col]
        total_rows = len(series)
        # Need at least 24 data points (monthly) for meaningful YoY
        if total_rows < 24:
            metrics[col] = {
                "trend_direction": "insufficient_data",
                "yoy_change_pct": 0.0,
                "current_avg": float(series.tail(12).mean()) if total_rows >= 12 else 0.0,
            }
            continue

        recent_avg = float(series.tail(12).mean())
        previous_avg = float(series.iloc[-24:-12].mean())

        if previous_avg > 0:
            yoy_change = ((recent_avg - previous_avg) / previous_avg) * 100
        else:
            yoy_change = 0.0

        if yoy_change > _RISING_THRESHOLD:
            direction = "rising"
        elif yoy_change < _FALLING_THRESHOLD:
            direction = "falling"
        else:
            direction = "stable"

        metrics[col] = {
            "trend_direction": direction,
            "yoy_change_pct": round(yoy_change, 1),
            "current_avg": round(recent_avg, 1),
            "previous_avg": round(previous_avg, 1),
        }

    return metrics


def _generate_insight_text(metrics: dict) -> str:
    """Generate a human-readable insight sentence from trend metrics."""
    parts = []
    for keyword, m in metrics.items():
        direction = m.get("trend_direction", "unknown")
        yoy = m.get("yoy_change_pct", 0)
        if direction == "rising":
            parts.append(
                f"Search interest for '{keyword}' has grown {yoy:+.0f}% YoY "
                f"-- a rising trend."
            )
        elif direction == "falling":
            parts.append(
                f"Search interest for '{keyword}' has declined {yoy:+.0f}% YoY "
                f"-- a falling trend."
            )
        elif direction == "stable":
            parts.append(
                f"Search interest for '{keyword}' is stable ({yoy:+.0f}% YoY)."
            )
        else:
            parts.append(
                f"Insufficient data to determine trend for '{keyword}'."
            )
    return " ".join(parts)


def _save_report(output_dir: str, keywords: List[str], metrics: dict,
                 interest_df, related: dict, regions_df,
                 insight_text: str) -> str:
    """Write a markdown trend report to output_dir/trend_report.md."""
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "trend_report.md")

    lines = ["# Google Trends Report\n"]

    # Summary
    lines.append("## Summary\n")
    lines.append(f"Keywords analyzed: {', '.join(keywords)}\n")
    lines.append(f"Timeframe: {_TIMEFRAME}\n")
    lines.append(f"\n{insight_text}\n")

    # Interest Over Time table
    lines.append("\n## Interest Over Time (last 12 monthly averages)\n")
    if interest_df is not None and not interest_df.empty:
        clean_df = interest_df.copy()
        if "isPartial" in clean_df.columns:
            clean_df = clean_df.drop(columns=["isPartial"])
        # Show last 12 rows
        tail = clean_df.tail(12)
        header = "| Date | " + " | ".join(str(c) for c in tail.columns) + " |"
        sep = "|---" * (len(tail.columns) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for idx, row in tail.iterrows():
            date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)
            vals = " | ".join(str(int(v)) for v in row.values)
            lines.append(f"| {date_str} | {vals} |")
    else:
        lines.append("*No interest-over-time data available.*\n")

    # Trend Metrics
    lines.append("\n## Trend Metrics\n")
    lines.append("| Keyword | Direction | YoY Change | Current Avg | Previous Avg |")
    lines.append("|---|---|---|---|---|")
    for kw, m in metrics.items():
        lines.append(
            f"| {kw} | {m.get('trend_direction', 'N/A')} | "
            f"{m.get('yoy_change_pct', 0):+.1f}% | "
            f"{m.get('current_avg', 'N/A')} | "
            f"{m.get('previous_avg', 'N/A')} |"
        )

    # Related Rising Queries
    lines.append("\n## Related Rising Queries\n")
    if related:
        for kw, data in related.items():
            lines.append(f"\n### {kw}\n")
            rising = data.get("rising")
            if rising is not None and not rising.empty:
                lines.append("| Query | Value |")
                lines.append("|---|---|")
                for _, row in rising.head(10).iterrows():
                    lines.append(f"| {row.get('query', '')} | {row.get('value', '')} |")
            else:
                lines.append("*No rising queries found.*\n")
            top = data.get("top")
            if top is not None and not top.empty:
                lines.append("\n**Top queries:**\n")
                lines.append("| Query | Value |")
                lines.append("|---|---|")
                for _, row in top.head(10).iterrows():
                    lines.append(f"| {row.get('query', '')} | {row.get('value', '')} |")
    else:
        lines.append("*No related queries data available.*\n")

    # Regional Interest
    lines.append("\n## Regional Interest (Top Countries)\n")
    if regions_df is not None and not regions_df.empty:
        clean_regions = regions_df.copy()
        if "isPartial" in clean_regions.columns:
            clean_regions = clean_regions.drop(columns=["isPartial"])
        # Sum across all keywords and take top N
        clean_regions["_total"] = clean_regions.sum(axis=1)
        top_regions = clean_regions.nlargest(_TOP_REGIONS, "_total")
        cols = [c for c in top_regions.columns if c != "_total"]
        lines.append("| Country | " + " | ".join(cols) + " |")
        lines.append("|---" * (len(cols) + 1) + "|")
        for region, row in top_regions.iterrows():
            vals = " | ".join(str(int(row[c])) for c in cols)
            lines.append(f"| {region} | {vals} |")
    else:
        lines.append("*No regional data available.*\n")

    report_text = "\n".join(lines) + "\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    logger.info("Trend report saved to %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_trends_analysis(instruction, output_dir: str = "output") -> Optional[dict]:
    """Analyze Google Trends for the instruction's relevance keywords (first 5).

    Returns a dict with:
        - interest_over_time: DataFrame or None
        - metrics: per-keyword trend direction and YoY change
        - related_queries: dict of DataFrames
        - regions: DataFrame or None
        - insight_text: human-readable summary string

    Saves a markdown report to ``output_dir/trend_report.md``.
    Returns None if pytrends is not installed or all requests fail.
    """
    if not HAS_PYTRENDS:
        logger.warning(
            "pytrends is not installed. Run: pip install pytrends. "
            "Skipping Google Trends analysis."
        )
        return None

    keywords = instruction.relevance_keywords[:5]  # pytrends max 5
    if not keywords:
        logger.warning("No relevance_keywords in instruction. Skipping trends.")
        return None

    logger.info("Running Google Trends analysis for: %s", keywords)

    pt = _build_pytrends()
    if pt is None:
        return None

    # --- Interest over time ---
    interest_df = None
    if _safe_build_payload(pt, keywords, _TIMEFRAME):
        try:
            interest_df = pt.interest_over_time()
        except Exception as exc:
            logger.warning("Failed to fetch interest_over_time: %s", exc)

    # --- Trend metrics ---
    metrics = _calculate_trend_metrics(interest_df)

    # --- Related queries ---
    related = {}
    try:
        if _safe_build_payload(pt, keywords, _TIMEFRAME):
            related = pt.related_queries()
    except Exception as exc:
        logger.warning("Failed to fetch related_queries: %s", exc)

    # --- Interest by region ---
    regions_df = None
    try:
        if _safe_build_payload(pt, keywords, _TIMEFRAME):
            regions_df = pt.interest_by_region(resolution="COUNTRY")
    except Exception as exc:
        logger.warning("Failed to fetch interest_by_region: %s", exc)

    # --- Insight text ---
    insight_text = _generate_insight_text(metrics)

    # --- Save report ---
    _save_report(output_dir, keywords, metrics, interest_df, related,
                 regions_df, insight_text)

    result = {
        "interest_over_time": interest_df,
        "metrics": metrics,
        "related_queries": related,
        "regions": regions_df,
        "insight_text": insight_text,
    }

    logger.info("Google Trends analysis complete. %s", insight_text)
    return result


# =========================================================================
# Google Cloud Timeseries Insights API (requires GOOGLE_CLOUD_API_KEY)
# =========================================================================
# If a valid Google Cloud API key is provided, this backend:
#   1. Creates a temporary dataset
#   2. Feeds social media post timestamps as events
#   3. Queries for anomalies/spikes in discussion volume
#   4. Returns richer trend analysis than pytrends alone
#
# Enable: set GOOGLE_CLOUD_API_KEY + GOOGLE_CLOUD_PROJECT in .env
# API: https://timeseriesinsights.googleapis.com/v1/
# Pricing: billed per data ingested, $300 free credits for new accounts
# =========================================================================

_TSI_BASE = "https://timeseriesinsights.googleapis.com/v1"
_TSI_LOCATION = "us-central1"

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def _get_tsi_key() -> Optional[str]:
    """Return Google Cloud API key from environment, or None."""
    return os.environ.get("GOOGLE_CLOUD_API_KEY", "").strip() or None


def _tsi_headers(api_key: str) -> dict:
    return {"Content-Type": "application/json", "x-goog-api-key": api_key}


def _tsi_dataset_name(project_id: str, dataset_id: str) -> str:
    return f"projects/{project_id}/locations/{_TSI_LOCATION}/datasets/{dataset_id}"


def _safe_dataset_id(project_name: str) -> str:
    """Build a short, API-safe temporary dataset id for one run."""
    base = re.sub(r"[^a-z0-9_]+", "_", project_name.lower()).strip("_")
    if not base:
        base = "project"
    suffix = str(int(time.time()))
    return f"unheard_buzz_{base[:24]}_{suffix}"


def create_tsi_dataset(api_key: str, project_id: str, dataset_id: str) -> bool:
    """Create a Timeseries Insights dataset. Returns True on success."""
    if not HAS_REQUESTS:
        logger.error("requests library required for Timeseries Insights API.")
        return False
    url = f"{_TSI_BASE}/projects/{project_id}/locations/{_TSI_LOCATION}/datasets"
    body = {
        "name": _tsi_dataset_name(project_id, dataset_id),
        "ttl": "86400s",
    }
    resp = _requests.post(url, json=body, headers=_tsi_headers(api_key), timeout=30)
    if resp.status_code in (200, 409):
        logger.info("TSI dataset ready: %s", dataset_id)
        return True
    logger.error("TSI create dataset failed (%d): %s", resp.status_code, resp.text[:200])
    return False


def append_tsi_events(api_key: str, project_id: str, dataset_id: str,
                      posts: list) -> int:
    """Upload social media posts as time series events."""
    if not posts:
        return 0
    events = []
    for post in posts:
        if not post.timestamp:
            continue
        dimensions = [{"name": "platform", "stringVal": post.platform}]
        for cat in post.categories:
            dimensions.append({"name": "category", "stringVal": cat})
        if isinstance(post.metadata, dict) and post.metadata.get("subreddit"):
            dimensions.append({"name": "subreddit", "stringVal": post.metadata["subreddit"]})
        events.append({
            "eventTime": post.timestamp,
            "dimensions": dimensions,
            "groupId": post.source_id or post.post_id,
        })
    if not events:
        return 0
    ds_name = _tsi_dataset_name(project_id, dataset_id)
    url = f"{_TSI_BASE}/{ds_name}:appendEvents"
    total = 0
    for i in range(0, len(events), 5000):
        batch = events[i:i + 5000]
        resp = _requests.post(url, json={"events": batch},
                              headers=_tsi_headers(api_key), timeout=60)
        if resp.status_code == 200:
            total += len(batch)
            logger.info("TSI: appended %d/%d events", total, len(events))
        else:
            logger.error("TSI appendEvents failed (%d): %s",
                         resp.status_code, resp.text[:200])
            break
    return total


def query_tsi_anomalies(api_key: str, project_id: str, dataset_id: str,
                        dimension_name: str = "category") -> dict:
    """Query for anomalies in the uploaded data."""
    ds_name = _tsi_dataset_name(project_id, dataset_id)
    url = f"{_TSI_BASE}/{ds_name}:query"
    body = {
        "detectionTime": {},
        "returnTimeseries": True,
        "slicingParams": {"dimensionNames": [dimension_name]},
    }
    resp = _requests.post(url, json=body, headers=_tsi_headers(api_key), timeout=60)
    if resp.status_code != 200:
        logger.error("TSI query failed (%d): %s", resp.status_code, resp.text[:200])
        return {"anomalies": [], "spikes": []}
    data = resp.json()
    anomalies, spikes = [], []
    for s in data.get("slices", []):
        status = s.get("status", "")
        dims = {d["name"]: d.get("stringVal", "") for d in s.get("dimensions", [])}
        entry = {"dimensions": dims, "status": status,
                 "detection_time": s.get("detectionTime", "")}
        if status == "ANOMALY":
            entry["severity"] = s.get("anomalyScore", 0)
            anomalies.append(entry)
        elif status in ("SPIKE", "ANOMALY_HIGH"):
            spikes.append(entry)
    return {"anomalies": anomalies, "spikes": spikes}


def delete_tsi_dataset(api_key: str, project_id: str, dataset_id: str) -> None:
    """Clean up temporary dataset."""
    ds_name = _tsi_dataset_name(project_id, dataset_id)
    _requests.delete(url=f"{_TSI_BASE}/{ds_name}",
                     headers=_tsi_headers(api_key), timeout=30)
    logger.info("TSI dataset deleted: %s", dataset_id)


def run_tsi_analysis(instruction, posts: list, output_dir: str = "output") -> Optional[dict]:
    """Run Timeseries Insights on collected posts. Phase 2b.

    Requires GOOGLE_CLOUD_API_KEY and GOOGLE_CLOUD_PROJECT in environment.
    Returns None if unavailable or insufficient data.
    """
    api_key = _get_tsi_key()
    if not api_key:
        return None
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT not set. Required for TSI API.")
        return None
    if not HAS_REQUESTS:
        logger.error("requests library required. pip install requests")
        return None
    relevant = [p for p in posts if p.is_relevant and p.timestamp]
    if len(relevant) < 10:
        logger.info("TSI: too few timestamped posts (%d).", len(relevant))
        return None
    dataset_id = _safe_dataset_id(instruction.project_name)
    try:
        if not create_tsi_dataset(api_key, project_id, dataset_id):
            return None
        count = append_tsi_events(api_key, project_id, dataset_id, relevant)
        if count == 0:
            return None
        time.sleep(5)  # indexing delay
        cat_res = query_tsi_anomalies(api_key, project_id, dataset_id, "category")
        plat_res = query_tsi_anomalies(api_key, project_id, dataset_id, "platform")
        parts = []
        for a in cat_res["anomalies"][:5]:
            parts.append(f"Anomalous volume for '{a['dimensions'].get('category', '?')}'")
        for s in cat_res["spikes"][:5]:
            parts.append(f"Spike in '{s['dimensions'].get('category', '?')}'")
        insight = "; ".join(parts) if parts else "No significant anomalies detected."
        report_path = _save_tsi_report(output_dir, cat_res, plat_res, insight, count)
        return {"backend": "timeseries_insights_api", "events_uploaded": count,
                "anomalies": cat_res["anomalies"], "spikes": cat_res["spikes"],
                "platform_anomalies": plat_res["anomalies"], "insight_text": insight,
                "report_path": report_path}
    finally:
        try:
            delete_tsi_dataset(api_key, project_id, dataset_id)
        except Exception:
            pass


def _save_tsi_report(output_dir: str, cat_res: dict, plat_res: dict,
                     insight: str, count: int) -> str:
    """Save TSI anomaly report as markdown."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "tsi_anomaly_report.md")
    lines = ["# Timeseries Insights — Discussion Anomaly Report", "",
             f"Analyzed **{count}** posts for volume anomalies.", "",
             "## Summary", "", insight, ""]
    if cat_res["anomalies"]:
        lines += ["## Category Anomalies", "",
                  "| Category | Status | Severity |",
                  "|----------|--------|----------|"]
        for a in cat_res["anomalies"]:
            c = a["dimensions"].get("category", "?")
            lines.append(f"| {c} | {a['status']} | {a.get('severity', 'N/A')} |")
        lines.append("")
    if cat_res["spikes"]:
        lines += ["## Discussion Spikes", ""]
        for s in cat_res["spikes"]:
            c = s["dimensions"].get("category", "?")
            lines.append(f"- **{c}**: spike at {s.get('detection_time', 'N/A')}")
        lines.append("")
    if plat_res["anomalies"]:
        lines += ["## Platform Anomalies", ""]
        for a in plat_res["anomalies"]:
            lines.append(f"- **{a['dimensions'].get('platform', '?')}**: {a['status']}")
        lines.append("")
    if not (cat_res["anomalies"] or cat_res["spikes"]):
        lines.append("Discussion volume is stable across all categories.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("TSI report saved: %s", path)
    return path
