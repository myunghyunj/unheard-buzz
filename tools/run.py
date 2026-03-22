"""
Main orchestrator for multi-platform social media analysis.
"""

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from collections import Counter

from dotenv import load_dotenv

from config import Instruction, SocialPost, load_instruction, OUTPUT_DIR
from analyzer import filter_posts, posts_for_stats
from reports import generate_all


def _save_checkpoint(phase: str, data: dict, output_dir: str) -> str:
    cp_dir = os.path.join(output_dir, "checkpoints")
    os.makedirs(cp_dir, exist_ok=True)
    filepath = os.path.join(cp_dir, f"{phase}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return filepath


def _load_checkpoint(phase: str, output_dir: str) -> Optional[dict]:
    filepath = os.path.join(output_dir, "checkpoints", f"{phase}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _posts_to_dicts(posts: List[SocialPost]) -> List[dict]:
    return [
        {
            "post_id": p.post_id,
            "platform": p.platform,
            "source_id": p.source_id,
            "source_title": p.source_title,
            "author": p.author,
            "text": p.text,
            "like_count": p.like_count,
            "reply_count": p.reply_count,
            "is_reply": p.is_reply,
            "parent_id": p.parent_id,
            "timestamp": p.timestamp,
            "url": p.url,
            "is_relevant": p.is_relevant,
            "relevance_score": p.relevance_score,
            "categories": p.categories,
            "category_scores": p.category_scores,
            "has_wish": p.has_wish,
            "word_count": p.word_count,
            "analysis_complete": p.analysis_complete,
            "metadata": p.metadata,
        }
        for p in posts
    ]


def _dicts_to_posts(dicts: List[dict]) -> List[SocialPost]:
    posts = []
    for d in dicts:
        cats = d.get("categories", [])
        if isinstance(cats, str):
            cats = [c for c in cats.split("|") if c]
        post = SocialPost(
            post_id=d.get("post_id", ""),
            platform=d.get("platform", ""),
            source_id=d.get("source_id", ""),
            source_title=d.get("source_title", ""),
            author=d.get("author", ""),
            text=d.get("text", ""),
            like_count=int(d.get("like_count", 0)),
            reply_count=int(d.get("reply_count", 0)),
            is_reply=d.get("is_reply", False),
            parent_id=d.get("parent_id"),
            timestamp=d.get("timestamp", ""),
            url=d.get("url", ""),
            is_relevant=d.get("is_relevant", False),
            relevance_score=float(d.get("relevance_score", 0.0)),
            categories=cats,
            category_scores=d.get("category_scores", {}) if isinstance(d.get("category_scores", {}), dict) else {},
            has_wish=d.get("has_wish", False),
            word_count=int(d.get("word_count", 0)),
            analysis_complete=bool(d.get("analysis_complete", False)),
            metadata=d.get("metadata", {}) if isinstance(d.get("metadata", {}), dict) else {},
        )
        posts.append(post)
    return posts


def _run_youtube(instruction: Instruction) -> Dict:
    try:
        from youtube import run_youtube
        return run_youtube(instruction)
    except ImportError:
        print("[youtube] Platform module not found, skipping.")
        return {"posts": [], "error": "module not found"}
    except Exception as e:
        print(f"[youtube] Error: {e}")
        traceback.print_exc()
        return {"posts": [], "error": str(e)}


def _run_reddit(instruction: Instruction) -> Dict:
    try:
        from reddit import run_reddit
        return run_reddit(instruction)
    except ImportError:
        print("[reddit] Platform module not found, skipping.")
        return {"posts": [], "error": "module not found"}
    except Exception as e:
        print(f"[reddit] Error: {e}")
        traceback.print_exc()
        return {"posts": [], "error": str(e)}


def _run_twitter(instruction: Instruction) -> Dict:
    try:
        from twitter import run_twitter
        return run_twitter(instruction)
    except ImportError:
        print("[twitter] Platform module not found, skipping.")
        return {"posts": [], "error": "module not found"}
    except Exception as e:
        print(f"[twitter] Error: {e}")
        traceback.print_exc()
        return {"posts": [], "error": str(e)}


def _run_linkedin(instruction: Instruction) -> Dict:
    try:
        from linkedin import run_linkedin
        return run_linkedin(instruction)
    except ImportError:
        print("[linkedin] Platform module not found, skipping.")
        return {"posts": [], "error": "module not found"}
    except Exception as e:
        print(f"[linkedin] Error: {e}")
        traceback.print_exc()
        return {"posts": [], "error": str(e)}


_PLATFORM_RUNNERS = {
    "youtube": _run_youtube,
    "reddit": _run_reddit,
    "twitter": _run_twitter,
    "linkedin": _run_linkedin,
}


def _run_trends(instruction: Instruction, output_dir: str) -> Optional[dict]:
    try:
        from trends import run_trends_analysis
        result = run_trends_analysis(instruction, output_dir)
        _save_checkpoint("phase0_trends", result, output_dir)
        return result
    except ImportError:
        print("[trends] Trends module not available, skipping.")
        return None
    except Exception as e:
        print(f"[trends] Error: {e}")
        traceback.print_exc()
        return None


def _summarize_trend_direction(trends_result: Optional[dict]) -> str:
    if not trends_result or not isinstance(trends_result, dict):
        return "N/A"

    metrics = trends_result.get("metrics", {})
    if not isinstance(metrics, dict):
        return "N/A"

    counts: Dict[str, int] = {}
    for data in metrics.values():
        if not isinstance(data, dict):
            continue
        direction = data.get("trend_direction")
        if direction in {"rising", "falling", "stable"}:
            counts[direction] = counts.get(direction, 0) + 1

    if not counts:
        return "N/A"
    if len(counts) == 1:
        return next(iter(counts))

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
        return f"mixed ({ranked[0][0]}-leaning)"
    return "mixed"


def run_pipeline(
    instruction: Instruction,
    platforms_override: Optional[List[str]] = None,
    output_dir: str = OUTPUT_DIR,
    resume: bool = False,
    skip_trends: bool = False,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()

    if platforms_override:
        enabled = [p for p in platforms_override if p in _PLATFORM_RUNNERS]
    else:
        enabled = instruction.enabled_platforms

    if not enabled:
        print("ERROR: No platforms enabled. Check your instruction file or --platforms flag.")
        sys.exit(1)

    print(f"Project: {instruction.project_name}")
    print(f"Platforms: {', '.join(enabled)}")
    print(f"Output: {output_dir}")
    print()

    trends_result = None
    if not skip_trends:
        print("=" * 60)
        print("PHASE 0: Google Trends Analysis")
        print("=" * 60)
        if resume:
            trends_result = _load_checkpoint("phase0_trends", output_dir)
            if trends_result:
                print("  Loaded from checkpoint.")
        if trends_result is None:
            trends_result = _run_trends(instruction, output_dir)
        print()

    print("=" * 60)
    print("PHASE 1: Collecting Posts (parallel)")
    print("=" * 60)

    all_posts: List[SocialPost] = []
    platform_stats: Dict[str, int] = {}
    platform_errors: Dict[str, str] = {}

    if resume:
        cp = _load_checkpoint("phase1_collection", output_dir)
        if cp:
            print("  Loaded from checkpoint.")
            all_posts = _dicts_to_posts(cp.get("posts", []))
            platform_stats = cp.get("platform_stats", {})
            platform_errors = cp.get("platform_errors", {})

    if not all_posts:
        with ThreadPoolExecutor(max_workers=len(enabled)) as executor:
            futures = {}
            for platform in enabled:
                runner = _PLATFORM_RUNNERS[platform]
                futures[executor.submit(runner, instruction)] = platform

            for future in as_completed(futures):
                platform = futures[future]
                try:
                    result = future.result()
                    posts = result.get("posts", [])
                    all_posts.extend(posts)
                    platform_stats[platform] = len(posts)
                    error = result.get("error")
                    if error:
                        platform_errors[platform] = error
                    print(f"  [{platform}] Collected {len(posts)} posts")
                except Exception as e:
                    print(f"  [{platform}] FAILED: {e}")
                    platform_errors[platform] = str(e)
                    platform_stats[platform] = 0

        _save_checkpoint("phase1_collection", {
            "posts": _posts_to_dicts(all_posts),
            "platform_stats": platform_stats,
            "platform_errors": platform_errors,
        }, output_dir)

    print(f"\n  Total raw posts: {len(all_posts)}")
    print()

    print("=" * 60)
    print("PHASE 2: Unified Analysis")
    print("=" * 60)

    analysis_loaded = False
    if resume:
        cp = _load_checkpoint("phase2_analysis", output_dir)
        if cp and cp.get("analysis_complete") is True:
            print("  Loaded analyzed posts from checkpoint.")
            all_posts = _dicts_to_posts(cp.get("posts", []))
            analysis_loaded = True

    if not analysis_loaded:
        all_posts = filter_posts(all_posts, instruction)
        _save_checkpoint("phase2_analysis", {
            "analysis_complete": True,
            "posts": _posts_to_dicts(all_posts),
        }, output_dir)

    relevant = sum(1 for p in all_posts if p.is_relevant)
    wishes = sum(1 for p in all_posts if p.has_wish)
    analyzed_complete = sum(1 for p in all_posts if p.analysis_complete)
    print(f"  After filtering: {len(all_posts)} posts")
    print(f"  Relevant: {relevant}")
    print(f"  Wish-tagged: {wishes}")
    print(f"  Analysis-complete posts: {analyzed_complete}")
    print()

    tsi_result = None
    if not skip_trends and all_posts:
        try:
            from trends import run_tsi_analysis, _get_tsi_key
            if _get_tsi_key():
                print("=" * 60)
                print("PHASE 2b: Timeseries Insights API (anomaly detection)")
                print("=" * 60)
                if resume:
                    tsi_result = _load_checkpoint("phase2b_tsi", output_dir)
                    if tsi_result:
                        print("  Loaded from checkpoint.")
                if tsi_result is None:
                    tsi_result = run_tsi_analysis(instruction, all_posts, output_dir=output_dir)
                    if tsi_result:
                        _save_checkpoint("phase2b_tsi", tsi_result, output_dir)
                if tsi_result:
                    print(f"  {tsi_result.get('insight_text', '')}")
                else:
                    print("  No significant anomalies detected or insufficient data.")
                print()
        except Exception as e:
            print(f"  [TSI] Skipped: {e}")

    print("=" * 60)
    print("PHASE 3: Report Generation")
    print("=" * 60)

    generated = generate_all(all_posts, instruction, output_dir)
    if tsi_result and tsi_result.get("report_path"):
        generated["tsi_anomaly_report_md"] = tsi_result["report_path"]
    _save_checkpoint("phase3_reports", {"generated_files": generated}, output_dir)

    for name, path in generated.items():
        print(f"  {name}: {path}")
    print()

    if instruction.validation_enabled:
        print("=" * 60)
        print("PHASE 4: Validation")
        print("=" * 60)
        val_path = generated.get("validation_report_md")
        if val_path:
            print(f"  Validation report: {val_path}")
        else:
            print("  Validation report was not generated.")
        print()

    elapsed = time.time() - start_time
    trend_direction = _summarize_trend_direction(trends_result)

    stats_posts = posts_for_stats(all_posts, instruction)
    cat_counter = Counter()
    for p in stats_posts:
        for c in p.categories:
            cat_counter[c] += 1
    top_cats = [code for code, _ in cat_counter.most_common(5)]

    pct_relevant = (relevant / len(all_posts) * 100) if all_posts else 0

    plat_counts = []
    for plat in ("youtube", "reddit", "twitter", "linkedin"):
        count = platform_stats.get(plat, 0)
        plat_counts.append(f"{plat.capitalize()}: {count}")

    summary = {
        "project_name": instruction.project_name,
        "platforms": enabled,
        "platform_stats": platform_stats,
        "platform_errors": platform_errors,
        "total_posts": len(all_posts),
        "stats_scope": "all_posts" if instruction.include_irrelevant_in_stats else "relevant_only",
        "stats_posts": len(stats_posts),
        "relevant": relevant,
        "wishes": wishes,
        "top_categories": top_cats,
        "trend_direction": trend_direction,
        "output_dir": output_dir,
        "elapsed_seconds": round(elapsed, 1),
        "generated_files": generated,
    }

    print("=" * 60)
    print(f"ANALYSIS COMPLETE: {instruction.project_name}")
    print("=" * 60)
    print(f"Platforms:          {', '.join(enabled)}")
    print(f"Posts collected:    {', '.join(plat_counts)}")
    print(f"Total posts:        {len(all_posts)}")
    print(f"Relevant:           {relevant} ({pct_relevant:.1f}%)")
    print(f"Stats scope:        {summary['stats_scope']} ({len(stats_posts)} posts)")
    print(f"Wish-tagged:        {wishes}")
    print(f"Top categories:     {', '.join(top_cats) if top_cats else 'none'}")
    print(f"Trend direction:    {trend_direction}")
    print(f"Output:             {output_dir}")
    print(f"Time:               {elapsed:.1f}s")
    print("=" * 60)

    if platform_errors:
        print("\nPlatform warnings:")
        for plat, err in platform_errors.items():
            print(f"  [{plat}] {err}")

    return summary


def _dry_run(instruction: Instruction, platforms: List[str], output_dir: str):
    tsi_enabled = bool(os.getenv("GOOGLE_CLOUD_API_KEY") and os.getenv("GOOGLE_CLOUD_PROJECT"))

    print("=" * 60)
    print("DRY RUN — Execution Plan")
    print("=" * 60)
    print(f"Project:     {instruction.project_name}")
    print(f"Description: {instruction.project_description}")
    print(f"Output dir:  {output_dir}")
    print()

    print("Planned phases:")
    print("  0. Google Trends (pytrends)")
    print("  1. Platform collection in parallel")
    print("  2. Unified analysis")
    if tsi_enabled:
        print("  2b. Timeseries Insights anomaly detection")
    print("  3. Report generation")
    if instruction.validation_enabled:
        print("  4. Validation")
    print()

    print("Platforms to run:")
    for p in platforms:
        cfg = getattr(instruction, p, None)
        if cfg and cfg.enabled:
            queries = getattr(cfg, "search_queries", [])
            print(f"  [{p}] {len(queries)} search queries")
        else:
            print(f"  [{p}] NOT enabled in instruction file")
    print()

    print(f"Analysis categories: {len(instruction.categories)}")
    for code, cat in instruction.categories.items():
        print(f"  {code}: {cat['name']} ({len(cat['keywords'])} keywords)")
    print()

    print(f"Relevance keywords: {len(instruction.relevance_keywords)}")
    print(f"Wish patterns: {len(instruction.wish_patterns)}")
    print(f"Minimum words: {instruction.min_comment_words}")
    print(
        "Language allowlist: "
        + (", ".join(instruction.language_allowlist) if instruction.language_allowlist else "none")
    )
    print(f"Normalized-text dedup: {instruction.dedup_normalized_text}")
    print(f"Dedup min chars: {instruction.dedup_min_chars}")
    print(f"Include irrelevant in stats: {instruction.include_irrelevant_in_stats}")
    print(f"TSI enabled: {tsi_enabled}")
    print(f"Validation: {'enabled' if instruction.validation_enabled else 'disabled'}")
    print()
    print("Use without --dry-run to execute.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Platform Social Media Analysis Tool")
    parser.add_argument("--instruction", required=True, help="Path to instruction YAML file")
    parser.add_argument("--platforms", help="Comma-separated list of platforms to run")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without running")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoints if available")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help=f"Output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--skip-trends", action="store_true", help="Skip Google Trends analysis (Phase 0)")
    return parser.parse_args()


if __name__ == "__main__":
    load_dotenv()
    args = parse_args()

    try:
        instruction = load_instruction(args.instruction)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    platforms_override = None
    if args.platforms:
        platforms_override = [p.strip().lower() for p in args.platforms.split(",")]

    if args.dry_run:
        platforms = platforms_override or instruction.enabled_platforms
        _dry_run(instruction, platforms, args.output_dir)
    else:
        run_pipeline(
            instruction=instruction,
            platforms_override=platforms_override,
            output_dir=args.output_dir,
            resume=args.resume,
            skip_trends=args.skip_trends,
        )
