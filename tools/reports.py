"""
Cross-platform report generation.

Produces CSV, JSON, and Markdown outputs that unify data from all
platforms into a single coherent analysis. All domain-specific labels
come from the Instruction config — no hardcoded terms.
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

from config import Instruction, SocialPost
from analyzer import analyze_by_platform, get_cross_platform_insights


# ---------------------------------------------------------------------------
# Author anonymization
# ---------------------------------------------------------------------------

def anonymize_authors(posts: List[SocialPost]) -> Tuple[List[SocialPost], Dict[str, str]]:
    """Replace author names with anonymous IDs.

    Returns:
        (posts with anonymized authors, mapping {original: anon_id})
    """
    author_map: Dict[str, str] = {}
    counter = 1

    for post in posts:
        original = post.author
        if original not in author_map:
            author_map[original] = f"User_{counter:04d}"
            counter += 1
        post.author = author_map[original]

    return posts, author_map


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def generate_posts_csv(posts: List[SocialPost], output_dir: str) -> str:
    """Write all posts to output/all_posts.csv with anonymized authors.

    Returns the path to the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "all_posts.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SocialPost.csv_header())
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_csv_row())

    return filepath


# ---------------------------------------------------------------------------
# Summary stats JSON
# ---------------------------------------------------------------------------

def generate_summary_stats(
    posts: List[SocialPost], instruction: Instruction, output_dir: str
) -> dict:
    """Compute and write output/summary_stats.json.

    Returns the stats dict.
    """
    os.makedirs(output_dir, exist_ok=True)

    platform_data = analyze_by_platform(posts)
    insights = get_cross_platform_insights(posts, instruction)

    relevant_posts = [p for p in posts if p.is_relevant]
    wish_posts = [p for p in posts if p.has_wish]

    # Global category counts
    global_cats: Dict[str, int] = defaultdict(int)
    for post in posts:
        for cat in post.categories:
            global_cats[cat] += 1

    # Build platform breakdown table
    all_platforms = sorted(platform_data.keys())
    all_categories = sorted(
        instruction.categories.keys(),
        key=lambda c: global_cats.get(c, 0),
        reverse=True,
    )

    platform_table = {}
    for cat in all_categories:
        row = {}
        for plat in all_platforms:
            row[plat] = platform_data.get(plat, {}).get("categories", {}).get(cat, 0)
        row["total"] = global_cats.get(cat, 0)
        platform_table[cat] = row

    stats = {
        "project_name": instruction.project_name,
        "generated_at": datetime.now().isoformat(),
        "total_posts": len(posts),
        "relevant_posts": len(relevant_posts),
        "wish_posts": len(wish_posts),
        "platforms": {
            p: {
                "total": pdata["total"],
                "relevant": pdata["relevant"],
                "wish": pdata["wish"],
            }
            for p, pdata in platform_data.items()
        },
        "category_counts": dict(global_cats),
        "category_rankings": insights["global_ranking"],
        "platform_breakdown": platform_table,
        "co_occurrences": insights["co_occurrences"],
        "platform_unique_emphases": insights["platform_unique_emphases"],
    }

    filepath = os.path.join(output_dir, "summary_stats.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


# ---------------------------------------------------------------------------
# Summary report (Markdown)
# ---------------------------------------------------------------------------

def generate_summary_report(
    stats: dict, instruction: Instruction, output_dir: str
) -> str:
    """Write output/summary_report.md.

    Sections:
      - Executive summary
      - Overall category rankings
      - Platform-by-platform breakdown table
      - Cross-platform comparison
      - Co-occurrence highlights
      - Key statistics

    Returns the filepath.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "summary_report.md")

    lines: List[str] = []

    # Title
    lines.append(f"# {stats['project_name']} — Analysis Report")
    lines.append("")
    lines.append(f"*Generated: {stats['generated_at']}*")
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    total = stats["total_posts"]
    relevant = stats["relevant_posts"]
    wish = stats["wish_posts"]
    pct_relevant = (relevant / total * 100) if total else 0
    platforms_used = sorted(stats["platforms"].keys())
    lines.append(
        f"This analysis collected **{total:,}** posts across "
        f"**{len(platforms_used)}** platforms ({', '.join(platforms_used)}). "
        f"Of these, **{relevant:,}** ({pct_relevant:.1f}%) were deemed relevant "
        f"and **{wish:,}** contained explicit wish/need expressions."
    )
    lines.append("")

    # Overall category rankings
    lines.append("## Overall Category Rankings")
    lines.append("")
    lines.append("| Rank | Code | Category | Count |")
    lines.append("|------|------|----------|-------|")
    for rank, (code, count) in enumerate(stats["category_rankings"], 1):
        cat_name = instruction.categories.get(code, {}).get("name", code)
        lines.append(f"| {rank} | {code} | {cat_name} | {count} |")
    lines.append("")

    # Platform-by-platform breakdown table
    lines.append("## Platform Breakdown")
    lines.append("")
    platform_table = stats.get("platform_breakdown", {})
    if platform_table:
        # Determine columns: all platforms + Total
        all_plats = set()
        for row in platform_table.values():
            all_plats.update(k for k in row if k != "total")
        all_plats = sorted(all_plats)
        plat_headers = [p.capitalize() for p in all_plats]

        header = "| Category | " + " | ".join(plat_headers) + " | Total |"
        separator = "|" + "----------|" * 1 + "---------|" * len(all_plats) + "-------|"
        lines.append(header)
        lines.append(separator)

        for code, row in platform_table.items():
            cat_name = instruction.categories.get(code, {}).get("name", code)
            label = f"{code} ({cat_name})"
            vals = [str(row.get(p, 0)) for p in all_plats]
            total_val = str(row.get("total", 0))
            lines.append(f"| {label} | " + " | ".join(vals) + f" | {total_val} |")
        lines.append("")

    # Per-platform stats
    lines.append("## Per-Platform Statistics")
    lines.append("")
    lines.append("| Platform | Total Posts | Relevant | Wish-tagged |")
    lines.append("|----------|-----------|----------|-------------|")
    for plat in platforms_used:
        pdata = stats["platforms"][plat]
        lines.append(
            f"| {plat.capitalize()} | {pdata['total']} | "
            f"{pdata['relevant']} | {pdata['wish']} |"
        )
    lines.append("")

    # Cross-platform comparison
    unique = stats.get("platform_unique_emphases", {})
    if unique:
        lines.append("## Cross-Platform Comparison")
        lines.append("")
        lines.append(
            "Categories that rank disproportionately high on specific platforms "
            "(top-3 on that platform but not globally):"
        )
        lines.append("")
        for plat, codes in sorted(unique.items()):
            names = [
                f"{c} ({instruction.categories.get(c, {}).get('name', c)})"
                for c in codes
            ]
            lines.append(f"- **{plat.capitalize()}**: {', '.join(names)}")
        lines.append("")

    # Co-occurrence highlights
    co_occ = stats.get("co_occurrences", [])
    if co_occ:
        lines.append("## Co-Occurrence Highlights")
        lines.append("")
        lines.append(
            "Category pairs that frequently appear together in the same post:"
        )
        lines.append("")
        lines.append("| Pair | Count |")
        lines.append("|------|-------|")
        for item in co_occ:
            pair = item["pair"]
            names = [
                f"{c} ({instruction.categories.get(c, {}).get('name', c)})"
                for c in pair
            ]
            lines.append(f"| {' + '.join(names)} | {item['count']} |")
        lines.append("")

    # Key statistics
    lines.append("## Key Statistics")
    lines.append("")
    lines.append(f"- **Total posts analyzed**: {total:,}")
    lines.append(f"- **Relevant posts**: {relevant:,} ({pct_relevant:.1f}%)")
    lines.append(f"- **Wish-tagged posts**: {wish:,}")
    lines.append(f"- **Platforms used**: {', '.join(platforms_used)}")
    lines.append(f"- **Categories tracked**: {len(instruction.categories)}")
    top_cats = stats["category_rankings"][:3]
    if top_cats:
        top_labels = [
            f"{c} ({instruction.categories.get(c, {}).get('name', c)})"
            for c, _ in top_cats
        ]
        lines.append(f"- **Top categories**: {', '.join(top_labels)}")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ---------------------------------------------------------------------------
# Quotable excerpts
# ---------------------------------------------------------------------------

def select_quotable_excerpts(
    posts: List[SocialPost], instruction: Instruction, count: int = 25
) -> List[dict]:
    """Select 20-30 best quotes across platforms.

    Scoring heuristics (platform-agnostic):
      - Relevant post: +2
      - Has wish: +3
      - Number of categories: +1 per category
      - Like count (normalized): +1 per 10 likes
      - Word count sweet spot (25-150 words): +1
    """
    scored: List[Tuple[float, SocialPost]] = []

    for post in posts:
        if not post.is_relevant:
            continue
        score = 2.0  # base for relevance
        if post.has_wish:
            score += 3.0
        score += len(post.categories) * 1.0
        score += min(post.like_count / 10.0, 5.0)  # cap at 5
        if 25 <= post.word_count <= 150:
            score += 1.0
        scored.append((score, post))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:count]

    excerpts = []
    for score, post in selected:
        # Truncate very long quotes
        text = post.text.strip()
        if len(text) > 500:
            text = text[:497] + "..."

        cat_names = [
            instruction.categories.get(c, {}).get("name", c)
            for c in post.categories
        ]

        excerpts.append({
            "text": text,
            "platform": post.platform,
            "source_title": post.source_title,
            "categories": post.categories,
            "category_names": cat_names,
            "has_wish": post.has_wish,
            "like_count": post.like_count,
            "score": round(score, 1),
        })

    return excerpts


def generate_excerpts_md(
    excerpts: List[dict], instruction: Instruction, output_dir: str
) -> str:
    """Write output/quotable_excerpts.md.

    Returns the filepath.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "quotable_excerpts.md")

    lines: List[str] = []
    lines.append(f"# {instruction.project_name} — Quotable Excerpts")
    lines.append("")
    lines.append(
        f"Top {len(excerpts)} quotes selected across all platforms, "
        "ranked by relevance and expressiveness."
    )
    lines.append("")

    for i, exc in enumerate(excerpts, 1):
        tags = []
        if exc["has_wish"]:
            tags.append("WISH")
        tags.extend(exc["categories"])
        tag_str = " | ".join(tags) if tags else "uncategorized"

        lines.append(f"### {i}. [{exc['platform'].capitalize()}] {tag_str}")
        lines.append("")
        lines.append(f"> {exc['text']}")
        lines.append("")
        source = exc.get("source_title", "")
        if source:
            lines.append(f"*Source: {source}*  ")
        lines.append(
            f"*Likes: {exc['like_count']} | "
            f"Categories: {', '.join(exc['category_names']) or 'none'} | "
            f"Score: {exc['score']}*"
        )
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def generate_validation_report(
    posts: List[SocialPost], instruction: Instruction, output_dir: str
) -> str:
    """Write output/validation_report.md comparing findings against references.

    Returns the filepath.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "validation_report.md")

    lines: List[str] = []
    lines.append(f"# {instruction.project_name} — Validation Report")
    lines.append("")

    if not instruction.validation_references:
        lines.append("*No validation references configured.*")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    # Compute our category ranking for comparison
    cat_counts: Dict[str, int] = defaultdict(int)
    for post in posts:
        for cat in post.categories:
            cat_counts[cat] += 1
    our_ranking = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
    our_rank_map = {code: rank for rank, (code, _) in enumerate(our_ranking, 1)}

    lines.append("## Our Category Rankings")
    lines.append("")
    lines.append("| Rank | Code | Category | Count |")
    lines.append("|------|------|----------|-------|")
    for rank, (code, count) in enumerate(our_ranking, 1):
        cat_name = instruction.categories.get(code, {}).get("name", code)
        lines.append(f"| {rank} | {code} | {cat_name} | {count} |")
    lines.append("")

    lines.append("## Reference Comparisons")
    lines.append("")

    for ref in instruction.validation_references:
        lines.append(f"### {ref.get('name', 'Unknown')}")
        lines.append("")
        title = ref.get("title", "")
        if title:
            lines.append(f"*{title}*")
            lines.append("")

        key_findings = ref.get("key_findings", {})
        top_categories = ref.get("top_categories", [])

        if key_findings:
            lines.append("| Category | Reference Finding | Our Rank |")
            lines.append("|----------|-------------------|----------|")
            for code, finding in key_findings.items():
                our_rank = our_rank_map.get(code, "N/A")
                cat_name = instruction.categories.get(code, {}).get("name", code)
                lines.append(f"| {code} ({cat_name}) | {finding} | {our_rank} |")
            lines.append("")

        if top_categories:
            lines.append(
                f"**Reference top categories**: {', '.join(top_categories)}"
            )
            overlap = [c for c in top_categories if c in our_rank_map]
            our_top5 = [code for code, _ in our_ranking[:5]]
            matched = [c for c in top_categories if c in our_top5]
            lines.append(
                f"**Overlap with our top 5**: {', '.join(matched) if matched else 'none'}"
            )
            lines.append("")

    # Overall agreement summary
    lines.append("## Agreement Summary")
    lines.append("")
    all_ref_cats = set()
    for ref in instruction.validation_references:
        all_ref_cats.update(ref.get("key_findings", {}).keys())
        all_ref_cats.update(ref.get("top_categories", []))
    our_top5 = {code for code, _ in our_ranking[:5]}
    agreement = all_ref_cats & our_top5
    lines.append(
        f"- **Reference categories mentioned**: {', '.join(sorted(all_ref_cats))}"
    )
    lines.append(
        f"- **Our top 5**: {', '.join(code for code, _ in our_ranking[:5])}"
    )
    lines.append(
        f"- **Agreement (in our top 5)**: "
        f"{', '.join(sorted(agreement)) if agreement else 'none'}"
    )
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_all(
    posts: List[SocialPost],
    instruction: Instruction,
    output_dir: str = "output",
) -> dict:
    """Generate all report artifacts.

    Steps:
      1. Anonymize authors
      2. Write all_posts.csv
      3. Compute and write summary_stats.json
      4. Write summary_report.md
      5. Select and write quotable_excerpts.md
      6. Write validation_report.md (if enabled)

    Returns a dict of generated filepaths.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated: Dict[str, str] = {}

    # 1. Anonymize
    posts, author_map = anonymize_authors(posts)

    # 2. CSV
    csv_path = generate_posts_csv(posts, output_dir)
    generated["all_posts_csv"] = csv_path

    # 3. Summary stats
    stats = generate_summary_stats(posts, instruction, output_dir)
    generated["summary_stats_json"] = os.path.join(output_dir, "summary_stats.json")

    # 4. Summary report
    report_path = generate_summary_report(stats, instruction, output_dir)
    generated["summary_report_md"] = report_path

    # 5. Quotable excerpts
    excerpts = select_quotable_excerpts(posts, instruction)
    excerpts_path = generate_excerpts_md(excerpts, instruction, output_dir)
    generated["quotable_excerpts_md"] = excerpts_path

    # 6. Validation report
    if instruction.validation_enabled:
        val_path = generate_validation_report(posts, instruction, output_dir)
        generated["validation_report_md"] = val_path

    return generated
