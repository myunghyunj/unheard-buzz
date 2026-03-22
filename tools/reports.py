"""Cross-platform report generation.

v3 additions:
- final rank score is used for quote selection
- category exemplars are included in summary stats and summary reports
- export anonymization remains non-mutating
"""

import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple
from copy import deepcopy

from config import Instruction, SocialPost
from analyzer import (
    analyze_by_platform,
    compute_final_rank_score,
    get_cross_platform_insights,
    posts_for_stats,
    representative_posts_by_category,
)


def clone_posts(posts: List[SocialPost]) -> List[SocialPost]:
    return [deepcopy(p) for p in posts]


def anonymize_authors(posts: List[SocialPost]) -> Tuple[List[SocialPost], Dict[str, str]]:
    author_map: Dict[str, str] = {}
    counter = 1
    cloned = clone_posts(posts)

    for post in cloned:
        original = post.author
        if original not in author_map:
            author_map[original] = f"User_{counter:04d}"
            counter += 1
        post.author = author_map[original]

    return cloned, author_map


def generate_posts_csv(posts: List[SocialPost], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "all_posts.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SocialPost.csv_header())
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_csv_row())

    return filepath


def generate_summary_stats(posts: List[SocialPost], instruction: Instruction, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    stats_posts = posts_for_stats(posts, instruction)
    platform_data = analyze_by_platform(stats_posts)
    insights = get_cross_platform_insights(stats_posts, instruction)

    relevant_posts = [p for p in posts if p.is_relevant]
    wish_posts = [p for p in stats_posts if p.has_wish]

    global_cats: Dict[str, int] = defaultdict(int)
    for post in stats_posts:
        for cat in post.categories:
            global_cats[cat] += 1

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

    exemplar_map = representative_posts_by_category(posts, instruction, per_category=1)
    category_exemplars = {}
    for cat, items in exemplar_map.items():
        if not items:
            continue
        top = items[0]
        category_exemplars[cat] = {
            "post_id": top.post_id,
            "platform": top.platform,
            "score": compute_final_rank_score(top),
            "text_preview": top.text[:180] + ("..." if len(top.text) > 180 else ""),
        }

    stats = {
        "project_name": instruction.project_name,
        "generated_at": datetime.now().isoformat(),
        "stats_scope": "all_posts" if instruction.include_irrelevant_in_stats else "relevant_only",
        "total_posts": len(posts),
        "stats_posts": len(stats_posts),
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
        "category_exemplars": category_exemplars,
    }

    filepath = os.path.join(output_dir, "summary_stats.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


def generate_summary_report(stats: dict, instruction: Instruction, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "summary_report.md")

    lines: List[str] = []
    lines.append(f"# {stats['project_name']} — Analysis Report")
    lines.append("")
    lines.append(f"*Generated: {stats['generated_at']}*")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    total = stats["total_posts"]
    relevant = stats["relevant_posts"]
    wish = stats["wish_posts"]
    scope_total = stats.get("stats_posts", relevant)
    pct_relevant = (relevant / total * 100) if total else 0
    platforms_used = sorted(stats["platforms"].keys())
    lines.append(
        f"This analysis collected **{total:,}** posts across "
        f"**{len(platforms_used)}** platforms ({', '.join(platforms_used)}). "
        f"Of these, **{relevant:,}** ({pct_relevant:.1f}%) were deemed relevant. "
        f"Summary statistics were computed on **{scope_total:,}** posts "
        f"using scope **{stats.get('stats_scope', 'relevant_only')}**. "
        f"Within that scope, **{wish:,}** contained explicit wish/need expressions."
    )
    lines.append("")

    lines.append("## Overall Category Rankings")
    lines.append("")
    lines.append("| Rank | Code | Category | Count |")
    lines.append("|------|------|----------|-------|")
    for rank, (code, count) in enumerate(stats["category_rankings"], 1):
        cat_name = instruction.categories.get(code, {}).get("name", code)
        lines.append(f"| {rank} | {code} | {cat_name} | {count} |")
    lines.append("")

    exemplars = stats.get("category_exemplars", {})
    if exemplars:
        lines.append("## Category Exemplars")
        lines.append("")
        for code, info in exemplars.items():
            cat_name = instruction.categories.get(code, {}).get("name", code)
            lines.append(f"### {code} — {cat_name}")
            lines.append("")
            lines.append(f"- Platform: **{info['platform']}**")
            lines.append(f"- Final score: **{info['score']}**")
            lines.append(f"- Quote preview: {info['text_preview']}")
            lines.append("")

    lines.append("## Platform Breakdown")
    lines.append("")
    platform_table = stats.get("platform_breakdown", {})
    if platform_table:
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

    lines.append("## Per-Platform Statistics")
    lines.append("")
    lines.append("| Platform | Scope Total | Relevant | Wish-tagged |")
    lines.append("|----------|-------------|----------|-------------|")
    for plat in platforms_used:
        pdata = stats["platforms"][plat]
        lines.append(
            f"| {plat.capitalize()} | {pdata['total']} | "
            f"{pdata['relevant']} | {pdata['wish']} |"
        )
    lines.append("")

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

    co_occ = stats.get("co_occurrences", [])
    if co_occ:
        lines.append("## Co-Occurrence Highlights")
        lines.append("")
        lines.append("Category pairs that frequently appear together in the same post:")
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

    lines.append("## Key Statistics")
    lines.append("")
    lines.append(f"- **Total posts analyzed**: {total:,}")
    lines.append(f"- **Relevant posts**: {relevant:,} ({pct_relevant:.1f}%)")
    lines.append(f"- **Stats scope posts**: {scope_total:,}")
    lines.append(f"- **Wish-tagged posts in scope**: {wish:,}")
    lines.append(f"- **Platforms used**: {', '.join(platforms_used)}")
    lines.append(f"- **Categories tracked**: {len(instruction.categories)}")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def select_quotable_excerpts(posts: List[SocialPost], instruction: Instruction, count: int = 25) -> List[dict]:
    scored: List[Tuple[float, SocialPost]] = []

    for post in posts:
        if not post.is_relevant:
            continue
        score = compute_final_rank_score(post)
        scored.append((score, post))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:count]

    excerpts = []
    for score, post in selected:
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
            "relevance_score": round(post.relevance_score, 3),
            "collector_score": round(float(post.metadata.get("collector_score", 0.0)), 3)
            if isinstance(post.metadata, dict)
            else 0.0,
            "final_rank_score": round(score, 4),
        })

    return excerpts


def generate_excerpts_md(excerpts: List[dict], instruction: Instruction, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "quotable_excerpts.md")

    lines: List[str] = []
    lines.append(f"# {instruction.project_name} — Quotable Excerpts")
    lines.append("")
    lines.append(f"Top {len(excerpts)} quotes selected across all platforms, ranked by final rank score.")
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
            f"*Final score: {exc['final_rank_score']} | Collector score: {exc['collector_score']} | "
            f"Relevance score: {exc['relevance_score']} | Likes: {exc['like_count']} | "
            f"Categories: {', '.join(exc['category_names']) or 'none'}*"
        )
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def generate_validation_report(posts: List[SocialPost], instruction: Instruction, output_dir: str) -> str:
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

    stats_posts = posts_for_stats(posts, instruction)
    cat_counts: Dict[str, int] = defaultdict(int)
    for post in stats_posts:
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
            lines.append(f"**Reference top categories**: {', '.join(top_categories)}")
            our_top5 = [code for code, _ in our_ranking[:5]]
            matched = [c for c in top_categories if c in our_top5]
            lines.append(
                f"**Overlap with our top 5**: {', '.join(matched) if matched else 'none'}"
            )
            lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def generate_all(posts: List[SocialPost], instruction: Instruction, output_dir: str = "output") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    generated: Dict[str, str] = {}

    export_posts, _author_map = anonymize_authors(posts)

    csv_path = generate_posts_csv(export_posts, output_dir)
    generated["all_posts_csv"] = csv_path

    stats = generate_summary_stats(posts, instruction, output_dir)
    generated["summary_stats_json"] = os.path.join(output_dir, "summary_stats.json")

    report_path = generate_summary_report(stats, instruction, output_dir)
    generated["summary_report_md"] = report_path

    excerpts = select_quotable_excerpts(export_posts, instruction)
    excerpts_path = generate_excerpts_md(excerpts, instruction, output_dir)
    generated["quotable_excerpts_md"] = excerpts_path

    if instruction.validation_enabled:
        val_path = generate_validation_report(posts, instruction, output_dir)
        generated["validation_report_md"] = val_path

    return generated
