"""Cross-platform report generation.

The reporting layer aims to produce both lightweight markdown summaries and
analysis-ready exports that resemble consulting deliverables:
- report-friendly markdown
- coded post exports
- source registries
- optional platform-specific registries
"""

import csv
import json
import os
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from analyzer import (
    analyze_by_platform,
    compute_final_rank_score,
    get_cross_platform_insights,
    posts_for_stats,
    representative_posts_by_category,
)
from config import Instruction, SocialPost


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


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _write_csv(filepath: str, fieldnames: List[str], rows: List[dict]) -> str:
    with open(filepath, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return filepath


def generate_posts_csv(posts: List[SocialPost], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "all_posts.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SocialPost.csv_header())
        writer.writeheader()
        for post in posts:
            writer.writerow(post.to_csv_row())

    return filepath


def generate_coded_posts_csv(posts: List[SocialPost], output_dir: str) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    rows: List[dict] = []

    for post in posts:
        rows.append(
            {
                "post_id": post.post_id,
                "platform": post.platform,
                "source_id": post.source_id,
                "source_title": post.source_title,
                "author": post.author,
                "text": post.text,
                "like_count": post.like_count,
                "reply_count": post.reply_count,
                "is_reply": post.is_reply,
                "timestamp": post.timestamp,
                "url": post.url,
                "is_relevant": post.is_relevant,
                "relevance_score": round(post.relevance_score, 3),
                "categories": "|".join(post.categories),
                "segments": "|".join(post.segments),
                "has_wish": post.has_wish,
                "word_count": post.word_count,
                "final_rank_score": round(post.final_rank_score, 4),
                "collector_score": round(float(post.metadata.get("collector_score", 0.0) or 0.0), 3),
                "language_guess": post.metadata.get("language_guess", ""),
                "channel": post.metadata.get("channel", ""),
                "subreddit": post.metadata.get("subreddit", ""),
                "metadata_json": json.dumps(post.metadata, ensure_ascii=False, sort_keys=True),
            }
        )

    fieldnames = [
        "post_id",
        "platform",
        "source_id",
        "source_title",
        "author",
        "text",
        "like_count",
        "reply_count",
        "is_reply",
        "timestamp",
        "url",
        "is_relevant",
        "relevance_score",
        "categories",
        "segments",
        "has_wish",
        "word_count",
        "final_rank_score",
        "collector_score",
        "language_guess",
        "channel",
        "subreddit",
        "metadata_json",
    ]

    coded_posts_path = _write_csv(
        os.path.join(output_dir, "coded_posts.csv"),
        fieldnames,
        rows,
    )
    coded_comments_path = _write_csv(
        os.path.join(output_dir, "coded_comments.csv"),
        fieldnames,
        rows,
    )
    return {
        "coded_posts_csv": coded_posts_path,
        "coded_comments_csv": coded_comments_path,
    }


def generate_source_registry(posts: List[SocialPost], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    buckets: Dict[Tuple[str, str], dict] = {}

    for post in posts:
        key = (post.platform, post.source_id)
        if key not in buckets:
            buckets[key] = {
                "platform": post.platform,
                "source_id": post.source_id,
                "source_title": post.source_title,
                "source_owner": post.metadata.get("channel")
                or post.metadata.get("subreddit")
                or "",
                "source_context": post.metadata.get("subreddit")
                or post.metadata.get("channel")
                or "",
                "source_url": post.url,
                "total_posts": 0,
                "relevant_posts": 0,
                "wish_posts": 0,
                "reply_posts": 0,
                "total_likes": 0,
                "latest_timestamp": "",
                "top_categories": Counter(),
            }

        bucket = buckets[key]
        bucket["total_posts"] += 1
        bucket["relevant_posts"] += int(post.is_relevant)
        bucket["wish_posts"] += int(post.has_wish)
        bucket["reply_posts"] += int(post.is_reply)
        bucket["total_likes"] += post.like_count
        if post.timestamp and post.timestamp > bucket["latest_timestamp"]:
            bucket["latest_timestamp"] = post.timestamp
        for category in post.categories:
            bucket["top_categories"][category] += 1

    rows: List[dict] = []
    for bucket in sorted(
        buckets.values(),
        key=lambda item: (item["platform"], -item["relevant_posts"], -item["total_posts"], item["source_id"]),
    ):
        top_categories = [
            code for code, _count in bucket["top_categories"].most_common(5)
        ]
        rows.append(
            {
                "platform": bucket["platform"],
                "source_id": bucket["source_id"],
                "source_title": bucket["source_title"],
                "source_owner": bucket["source_owner"],
                "source_context": bucket["source_context"],
                "source_url": bucket["source_url"],
                "total_posts": bucket["total_posts"],
                "relevant_posts": bucket["relevant_posts"],
                "wish_posts": bucket["wish_posts"],
                "reply_posts": bucket["reply_posts"],
                "total_likes": bucket["total_likes"],
                "latest_timestamp": bucket["latest_timestamp"],
                "top_categories": "|".join(top_categories),
            }
        )

    fieldnames = [
        "platform",
        "source_id",
        "source_title",
        "source_owner",
        "source_context",
        "source_url",
        "total_posts",
        "relevant_posts",
        "wish_posts",
        "reply_posts",
        "total_likes",
        "latest_timestamp",
        "top_categories",
    ]
    return _write_csv(os.path.join(output_dir, "source_registry.csv"), fieldnames, rows)


def _youtube_channel_url(channel: dict) -> str:
    if channel.get("url"):
        return channel["url"]
    custom_url = channel.get("custom_url", "")
    if custom_url:
        return f"https://www.youtube.com/{custom_url}"
    handle = str(channel.get("handle", "")).strip()
    if handle:
        if not handle.startswith("@"):
            handle = "@" + handle.lstrip("/")
        return f"https://www.youtube.com/{handle}"
    channel_id = channel.get("channel_id", "")
    if channel_id:
        return f"https://www.youtube.com/channel/{channel_id}"
    return ""


def generate_youtube_registries(
    collector_context: Dict[str, dict],
    posts: List[SocialPost],
    output_dir: str,
) -> Dict[str, str]:
    youtube_context = (collector_context or {}).get("youtube", {})
    channels = youtube_context.get("channels", []) or []
    videos = youtube_context.get("videos", []) or []
    if not channels and not videos:
        return {}

    os.makedirs(output_dir, exist_ok=True)
    generated: Dict[str, str] = {}

    posts_by_channel: Dict[str, List[SocialPost]] = defaultdict(list)
    posts_by_video: Dict[str, List[SocialPost]] = defaultdict(list)
    for post in posts:
        if post.platform != "youtube":
            continue
        channel_name = post.metadata.get("channel", "")
        if channel_name:
            posts_by_channel[channel_name].append(post)
        posts_by_video[post.source_id].append(post)

    if channels:
        standard_fields = [
            "channel_name",
            "url",
            "channel_id",
            "subscribers",
            "publishedAt",
            "last_upload",
            "videos_sampled",
            "comments_extracted",
            "relevant_posts",
            "wish_posts",
        ]
        extra_keys = sorted(
            {
                key
                for channel in channels
                for key in channel.keys()
                if key
                not in {
                    "name",
                    "url",
                    "channel_id",
                    "subscribers",
                    "publishedAt",
                    "uploads_id",
                    "description",
                }
            }
        )

        channel_rows: List[dict] = []
        for channel in channels:
            channel_name = channel.get("name", "")
            channel_posts = posts_by_channel.get(channel_name, [])
            last_upload = max(
                (
                    video.get("publishedAt", "")
                    for video in videos
                    if video.get("channelName") == channel_name
                ),
                default="",
            )
            row = {
                "channel_name": channel_name,
                "url": _youtube_channel_url(channel),
                "channel_id": channel.get("channel_id", ""),
                "subscribers": channel.get("subscribers", 0),
                "publishedAt": channel.get("publishedAt", ""),
                "last_upload": last_upload,
                "videos_sampled": sum(
                    1 for video in videos if video.get("channelName") == channel_name
                ),
                "comments_extracted": len(channel_posts),
                "relevant_posts": sum(1 for post in channel_posts if post.is_relevant),
                "wish_posts": sum(1 for post in channel_posts if post.has_wish),
            }
            for key in extra_keys:
                if key in row:
                    continue
                row[key] = channel.get(key, "")
            channel_rows.append(row)

        generated["channel_registry_csv"] = _write_csv(
            os.path.join(output_dir, "channel_registry.csv"),
            standard_fields + [key for key in extra_keys if key not in standard_fields],
            channel_rows,
        )

    if videos:
        video_rows: List[dict] = []
        for video in videos:
            video_posts = posts_by_video.get(video.get("videoId", ""), [])
            video_rows.append(
                {
                    "video_id": video.get("videoId", ""),
                    "channel": video.get("channelName", ""),
                    "title": video.get("title", ""),
                    "views": video.get("viewCount", 0),
                    "comment_count": video.get("commentCount", 0),
                    "upload_date": video.get("publishedAt", ""),
                    "collector_video_score": video.get("collector_video_score", 0.0),
                    "topic_tags": "|".join(video.get("topic_tags", [])),
                    "posts_extracted": len(video_posts),
                    "relevant_posts": sum(1 for post in video_posts if post.is_relevant),
                    "wish_posts": sum(1 for post in video_posts if post.has_wish),
                }
            )

        generated["video_registry_csv"] = _write_csv(
            os.path.join(output_dir, "video_registry.csv"),
            [
                "video_id",
                "channel",
                "title",
                "views",
                "comment_count",
                "upload_date",
                "collector_video_score",
                "topic_tags",
                "posts_extracted",
                "relevant_posts",
                "wish_posts",
            ],
            video_rows,
        )

    return generated


def _build_cooccurrence_matrix(posts: List[SocialPost]) -> Dict[str, Dict[str, int]]:
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for post in posts:
        labels = sorted(set(post.categories))
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                left = labels[i]
                right = labels[j]
                matrix[left][right] += 1
                matrix[right][left] += 1
    return {left: dict(rights) for left, rights in matrix.items()}


def _build_segment_stats(posts: List[SocialPost], instruction: Instruction) -> Dict[str, dict]:
    if not instruction.segments:
        return {}

    stats: Dict[str, dict] = {}
    for code, segment in instruction.segments.items():
        segment_posts = [post for post in posts if code in post.segments]
        category_counts = Counter()
        platform_counts = Counter()
        for post in segment_posts:
            platform_counts[post.platform] += 1
            for category in post.categories:
                category_counts[category] += 1

        stats[code] = {
            "name": segment.get("name", code),
            "description": segment.get("description", ""),
            "count": len(segment_posts),
            "wish_posts": sum(1 for post in segment_posts if post.has_wish),
            "platforms": dict(platform_counts),
            "categories": dict(category_counts),
        }
    return stats


def _build_category_rankings(
    stats_posts: List[SocialPost],
    instruction: Instruction,
) -> Tuple[List[dict], Dict[str, dict]]:
    category_counts = Counter()
    wish_counts = Counter()
    platform_counts: Dict[str, Counter] = defaultdict(Counter)
    segment_counts: Dict[str, Counter] = defaultdict(Counter)

    for post in stats_posts:
        for category in post.categories:
            category_counts[category] += 1
            if post.has_wish:
                wish_counts[category] += 1
            platform_counts[category][post.platform] += 1
            for segment in post.segments:
                segment_counts[category][segment] += 1

    rankings: List[dict] = []
    categories: Dict[str, dict] = {}

    for rank, (code, count) in enumerate(category_counts.most_common(), 1):
        category_name = instruction.categories.get(code, {}).get("name", code)
        wish_count = wish_counts.get(code, 0)
        item = {
            "rank": rank,
            "code": code,
            "name": category_name,
            "count": count,
            "pct_scope": _pct(count, len(stats_posts)),
            "pct_wish": _pct(wish_count, count),
            "wish_count": wish_count,
            "platform_counts": dict(platform_counts.get(code, {})),
            "segment_counts": dict(segment_counts.get(code, {})),
        }
        rankings.append(item)
        categories[code] = item

    return rankings, categories


def _collector_summary(collector_context: Dict[str, dict]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    youtube_context = (collector_context or {}).get("youtube", {})
    youtube_stats = youtube_context.get("stats", {}) or {}
    if youtube_stats:
        summary["youtube_channels"] = int(youtube_stats.get("channels_discovered", 0))
        summary["youtube_videos"] = int(youtube_stats.get("videos_selected", 0))
    return summary


def generate_summary_stats(
    posts: List[SocialPost],
    instruction: Instruction,
    output_dir: str,
    collector_context: Optional[Dict[str, dict]] = None,
    top_quotes: Optional[List[dict]] = None,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    stats_posts = posts_for_stats(posts, instruction)
    platform_data = analyze_by_platform(stats_posts)
    insights = get_cross_platform_insights(stats_posts, instruction)
    category_rankings, categories = _build_category_rankings(stats_posts, instruction)
    relevant_posts = [post for post in posts if post.is_relevant]
    wish_posts = [post for post in stats_posts if post.has_wish]
    cooccurrence_matrix = _build_cooccurrence_matrix(stats_posts)

    all_platforms = sorted(platform_data.keys())
    platform_table: Dict[str, dict] = {}
    for ranking in category_rankings:
        code = ranking["code"]
        row = {
            platform: ranking["platform_counts"].get(platform, 0)
            for platform in all_platforms
        }
        row["total"] = ranking["count"]
        platform_table[code] = row

    exemplar_map = representative_posts_by_category(posts, instruction, per_category=1)
    category_exemplars = {}
    for code, items in exemplar_map.items():
        if not items:
            continue
        exemplar = items[0]
        category_exemplars[code] = {
            "post_id": exemplar.post_id,
            "platform": exemplar.platform,
            "score": compute_final_rank_score(exemplar),
            "source_title": exemplar.source_title,
            "text_excerpt": _truncate(exemplar.text, 280),
            "count": categories.get(code, {}).get("count", 0),
        }

    totals = {
        "total_posts": len(posts),
        "stats_posts": len(stats_posts),
        "relevant_posts": len(relevant_posts),
        "wish_posts": len(wish_posts),
        "unique_sources": len({(post.platform, post.source_id) for post in posts}),
        "unique_authors": len({post.author for post in posts if post.author}),
    }

    stats = {
        "project_name": instruction.project_name,
        "project_description": instruction.project_description,
        "generated_at": datetime.now().isoformat(),
        "stats_scope": "all_posts" if instruction.include_irrelevant_in_stats else "relevant_only",
        "total_posts": totals["total_posts"],
        "stats_posts": totals["stats_posts"],
        "relevant_posts": totals["relevant_posts"],
        "wish_posts": totals["wish_posts"],
        "totals": totals,
        "platforms": {
            platform: {
                "total": pdata["total"],
                "relevant": pdata["relevant"],
                "wish": pdata["wish"],
            }
            for platform, pdata in platform_data.items()
        },
        "collector_summary": _collector_summary(collector_context or {}),
        "category_counts": {code: item["count"] for code, item in categories.items()},
        "categories": categories,
        "category_rankings": category_rankings,
        "category_rankings_legacy": insights["global_ranking"],
        "platform_breakdown": platform_table,
        "co_occurrences": insights["co_occurrences"],
        "co_occurrence_matrix": cooccurrence_matrix,
        "platform_unique_emphases": insights["platform_unique_emphases"],
        "segments": _build_segment_stats(stats_posts, instruction),
        "category_exemplars": category_exemplars,
        "top_quotes": top_quotes or [],
    }

    filepath = os.path.join(output_dir, "summary_stats.json")
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2, ensure_ascii=False)

    return stats


def _append_project_brief(lines: List[str], instruction: Instruction) -> None:
    has_brief = any(
        [
            instruction.project_objectives,
            instruction.project_target_audiences,
            instruction.project_key_questions,
            instruction.project_decision_uses,
        ]
    )
    if not has_brief:
        return

    lines.append("## Research Brief")
    lines.append("")
    if instruction.project_objectives:
        lines.append("**Objectives**")
        lines.extend(f"- {item}" for item in instruction.project_objectives)
        lines.append("")
    if instruction.project_target_audiences:
        lines.append("**Target audiences**")
        lines.extend(f"- {item}" for item in instruction.project_target_audiences)
        lines.append("")
    if instruction.project_key_questions:
        lines.append("**Key questions**")
        lines.extend(f"- {item}" for item in instruction.project_key_questions)
        lines.append("")
    if instruction.project_decision_uses:
        lines.append("**Decision uses**")
        lines.extend(f"- {item}" for item in instruction.project_decision_uses)
        lines.append("")


def _append_voice_of_customer(lines: List[str], stats: dict, instruction: Instruction) -> None:
    quotes = stats.get("top_quotes", [])[:5]
    if not quotes:
        return

    lines.append("## Voice-of-Customer Highlights")
    lines.append("")
    for index, quote in enumerate(quotes, 1):
        category_names = [
            instruction.categories.get(code, {}).get("name", code)
            for code in quote.get("categories", [])
        ]
        label = ", ".join(category_names) if category_names else "uncategorized"
        lines.append(f"### Quote {index}")
        lines.append("")
        lines.append(f"> {quote['text']}")
        lines.append("")
        lines.append(
            f"*Platform: {quote['platform'].capitalize()} | Source: {quote.get('source_title', 'n/a')} | "
            f"Categories: {label}*"
        )
        lines.append("")


def generate_summary_report(stats: dict, instruction: Instruction, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "summary_report.md")

    lines: List[str] = []
    lines.append(f"# {stats['project_name']} — Summary Report")
    lines.append("")
    lines.append(f"*Generated: {stats['generated_at']}*")
    lines.append("")
    if stats.get("project_description"):
        lines.append(stats["project_description"])
        lines.append("")

    _append_project_brief(lines, instruction)
    _append_voice_of_customer(lines, stats, instruction)

    totals = stats.get("totals", {})
    collector_summary = stats.get("collector_summary", {})
    total_posts = totals.get("total_posts", stats.get("total_posts", 0))
    relevant_posts = totals.get("relevant_posts", stats.get("relevant_posts", 0))
    wish_posts = totals.get("wish_posts", stats.get("wish_posts", 0))
    stats_posts = totals.get("stats_posts", stats.get("stats_posts", 0))
    pct_relevant = _pct(relevant_posts, total_posts)
    platforms_used = sorted(stats.get("platforms", {}).keys())

    lines.append("## Executive Summary")
    lines.append("")
    summary_bits = [
        f"This analysis collected **{total_posts:,}** posts across **{len(platforms_used)}** platforms"
        + (f" ({', '.join(platforms_used)})" if platforms_used else ""),
        f"**{relevant_posts:,}** were marked relevant ({pct_relevant:.1f}%)",
        f"summary statistics were computed on **{stats_posts:,}** posts",
        f"**{wish_posts:,}** contained explicit wish or need language",
    ]
    if collector_summary.get("youtube_channels"):
        summary_bits.insert(
            1,
            f"the YouTube collector sampled **{collector_summary['youtube_channels']:,}** channels and "
            f"**{collector_summary.get('youtube_videos', 0):,}** videos",
        )
    lines.append("; ".join(summary_bits) + ".")
    lines.append("")

    lines.append("## Category Rankings")
    lines.append("")
    lines.append("| Rank | Code | Category | Count | % Scope | % Wish |")
    lines.append("|-----:|:----:|----------|------:|--------:|-------:|")
    for item in stats.get("category_rankings", []):
        lines.append(
            f"| {item['rank']} | {item['code']} | {item['name']} | {item['count']} | "
            f"{item['pct_scope']:.1f}% | {item['pct_wish']:.1f}% |"
        )
    lines.append("")

    segment_stats = stats.get("segments", {})
    if segment_stats:
        lines.append("## Segment Comparison")
        lines.append("")
        segment_order = [
            code
            for code, _segment in sorted(
                segment_stats.items(),
                key=lambda item: item[1].get("count", 0),
                reverse=True,
            )
        ]
        top_categories = stats.get("category_rankings", [])[
            : max(1, instruction.reporting.top_category_limit)
        ]
        header = "| Category | " + " | ".join(segment_order) + " |"
        separator = "|----------|" + "|".join(["-------:"] * len(segment_order)) + "|"
        lines.append(header)
        lines.append(separator)
        for item in top_categories:
            cells = [
                str(item.get("segment_counts", {}).get(segment_code, 0))
                for segment_code in segment_order
            ]
            lines.append(f"| {item['code']} ({item['name']}) | " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("## Platform Breakdown")
    lines.append("")
    lines.append("| Platform | Scope Total | Relevant | Wish-tagged |")
    lines.append("|----------|------------:|---------:|------------:|")
    for platform in platforms_used:
        pdata = stats["platforms"][platform]
        lines.append(
            f"| {platform.capitalize()} | {pdata['total']} | {pdata['relevant']} | {pdata['wish']} |"
        )
    lines.append("")

    platform_unique = stats.get("platform_unique_emphases", {})
    if platform_unique:
        lines.append("## Platform-Specific Emphasis")
        lines.append("")
        for platform, codes in sorted(platform_unique.items()):
            names = [
                f"{code} ({instruction.categories.get(code, {}).get('name', code)})"
                for code in codes
            ]
            lines.append(f"- **{platform.capitalize()}**: {', '.join(names)}")
        lines.append("")

    co_occurrences = stats.get("co_occurrences", [])
    if co_occurrences:
        lines.append("## Co-Occurrence Highlights")
        lines.append("")
        lines.append("| Pair | Co-occurrences |")
        lines.append("|------|---------------:|")
        for item in co_occurrences:
            names = [
                f"{code} ({instruction.categories.get(code, {}).get('name', code)})"
                for code in item["pair"]
            ]
            lines.append(f"| {' + '.join(names)} | {item['count']} |")
        lines.append("")

    exemplars = stats.get("category_exemplars", {})
    if exemplars:
        lines.append("## Representative Posts")
        lines.append("")
        for item in stats.get("category_rankings", [])[:5]:
            info = exemplars.get(item["code"])
            if not info:
                continue
            lines.append(f"### {item['code']} — {item['name']}")
            lines.append("")
            lines.append("Representative post:")
            lines.append(f"> {info['text_excerpt']}")
            lines.append("")
            lines.append(
                f"*Platform: {info['platform'].capitalize()} | Final score: {info['score']} | "
                f"Source: {info['source_title'] or 'n/a'}*"
            )
            lines.append("")

    lines.append("## Key Statistics")
    lines.append("")
    lines.append(f"- **Total posts analyzed**: {total_posts:,}")
    lines.append(f"- **Relevant posts**: {relevant_posts:,} ({pct_relevant:.1f}%)")
    lines.append(f"- **Stats-scope posts**: {stats_posts:,}")
    lines.append(f"- **Wish-tagged posts**: {wish_posts:,}")
    lines.append(f"- **Unique sources**: {totals.get('unique_sources', 0):,}")
    lines.append(f"- **Unique authors**: {totals.get('unique_authors', 0):,}")
    if collector_summary.get("youtube_channels"):
        lines.append(f"- **YouTube channels sampled**: {collector_summary['youtube_channels']:,}")
        lines.append(f"- **YouTube videos sampled**: {collector_summary.get('youtube_videos', 0):,}")
    lines.append(f"- **Categories tracked**: {len(instruction.categories)}")
    if instruction.segments:
        lines.append(f"- **Segments tracked**: {len(instruction.segments)}")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return filepath


def select_quotable_excerpts(
    posts: List[SocialPost],
    instruction: Instruction,
    count: Optional[int] = None,
) -> List[dict]:
    count = count or instruction.reporting.quote_count
    ranked_posts = [
        post for post in posts if post.is_relevant
    ]
    ranked_posts.sort(
        key=lambda post: (
            compute_final_rank_score(post),
            post.relevance_score,
            post.like_count,
            len(post.text),
        ),
        reverse=True,
    )

    selected: List[SocialPost] = []
    seen_ids = set()
    top_categories = [
        code for code, _count in Counter(
            category
            for post in ranked_posts
            for category in post.categories
        ).most_common()
    ]

    for category in top_categories:
        for post in ranked_posts:
            if post.post_id in seen_ids or category not in post.categories:
                continue
            selected.append(post)
            seen_ids.add(post.post_id)
            break
        if len(selected) >= count:
            break

    for post in ranked_posts:
        if len(selected) >= count:
            break
        if post.post_id in seen_ids:
            continue
        selected.append(post)
        seen_ids.add(post.post_id)

    excerpts: List[dict] = []
    for post in selected[:count]:
        category_names = [
            instruction.categories.get(code, {}).get("name", code)
            for code in post.categories
        ]
        excerpts.append(
            {
                "text": _truncate(post.text.strip(), 500),
                "author": post.author,
                "platform": post.platform,
                "source_title": post.source_title,
                "source_url": post.url,
                "categories": post.categories,
                "category_names": category_names,
                "segments": post.segments,
                "has_wish": post.has_wish,
                "like_count": post.like_count,
                "relevance_score": round(post.relevance_score, 3),
                "collector_score": round(float(post.metadata.get("collector_score", 0.0) or 0.0), 3),
                "final_rank_score": round(compute_final_rank_score(post), 4),
            }
        )

    return excerpts


def generate_excerpts_md(excerpts: List[dict], instruction: Instruction, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "quotable_excerpts.md")

    lines: List[str] = []
    lines.append(f"# {instruction.project_name} — Quotable Excerpts")
    lines.append("")
    lines.append(
        f"Top {len(excerpts)} quotes selected across all platforms, diversified to cover the leading need categories."
    )
    lines.append("")

    for index, excerpt in enumerate(excerpts, 1):
        tags = []
        if excerpt["has_wish"]:
            tags.append("WISH")
        tags.extend(excerpt["categories"])
        tag_string = " | ".join(tags) if tags else "uncategorized"

        lines.append(f"### {index}. [{excerpt['platform'].capitalize()}] {tag_string}")
        lines.append("")
        lines.append(f"> {excerpt['text']}")
        lines.append("")
        if excerpt.get("author"):
            lines.append(f"*Author: {excerpt['author']}*  ")
        if excerpt.get("source_title"):
            lines.append(f"*Source: {excerpt['source_title']}*  ")
        if excerpt.get("source_url"):
            lines.append(f"*URL: {excerpt['source_url']}*  ")
        lines.append(
            f"*Final score: {excerpt['final_rank_score']} | Collector score: {excerpt['collector_score']} | "
            f"Relevance score: {excerpt['relevance_score']} | Likes: {excerpt['like_count']} | "
            f"Categories: {', '.join(excerpt['category_names']) or 'none'}*"
        )
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return filepath


def generate_validation_report(posts: List[SocialPost], instruction: Instruction, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "validation_report.md")

    lines: List[str] = []
    lines.append(f"# {instruction.project_name} — Validation Report")
    lines.append("")

    if not instruction.validation_references:
        lines.append("*No validation references configured.*")
        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return filepath

    stats_posts = posts_for_stats(posts, instruction)
    category_counts = Counter()
    for post in stats_posts:
        for category in post.categories:
            category_counts[category] += 1

    our_ranking = category_counts.most_common()
    our_rank_map = {code: rank for rank, (code, _count) in enumerate(our_ranking, 1)}

    lines.append("## Our Category Rankings")
    lines.append("")
    lines.append("| Rank | Code | Category | Count |")
    lines.append("|------|------|----------|-------|")
    for rank, (code, count) in enumerate(our_ranking, 1):
        category_name = instruction.categories.get(code, {}).get("name", code)
        lines.append(f"| {rank} | {code} | {category_name} | {count} |")
    lines.append("")

    lines.append("## Reference Comparisons")
    lines.append("")

    for reference in instruction.validation_references:
        lines.append(f"### {reference.get('name', 'Unknown')}")
        lines.append("")
        if reference.get("title"):
            lines.append(f"*{reference['title']}*")
            lines.append("")

        key_findings = reference.get("key_findings", {})
        top_categories = reference.get("top_categories", [])

        if key_findings:
            lines.append("| Category | Reference Finding | Our Rank |")
            lines.append("|----------|-------------------|----------|")
            for code, finding in key_findings.items():
                our_rank = our_rank_map.get(code, "N/A")
                category_name = instruction.categories.get(code, {}).get("name", code)
                lines.append(f"| {code} ({category_name}) | {finding} | {our_rank} |")
            lines.append("")

        if top_categories:
            lines.append(f"**Reference top categories**: {', '.join(top_categories)}")
            our_top_five = [code for code, _count in our_ranking[:5]]
            matched = [code for code in top_categories if code in our_top_five]
            lines.append(
                f"**Overlap with our top 5**: {', '.join(matched) if matched else 'none'}"
            )
            lines.append("")

    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return filepath


def generate_all(
    posts: List[SocialPost],
    instruction: Instruction,
    output_dir: str = "output",
    collector_context: Optional[Dict[str, dict]] = None,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    generated: Dict[str, str] = {}

    export_posts, _author_map = anonymize_authors(posts)

    generated["all_posts_csv"] = generate_posts_csv(export_posts, output_dir)
    generated.update(generate_coded_posts_csv(export_posts, output_dir))
    generated["source_registry_csv"] = generate_source_registry(export_posts, output_dir)
    generated.update(generate_youtube_registries(collector_context or {}, posts, output_dir))

    excerpts = select_quotable_excerpts(
        export_posts,
        instruction,
        count=instruction.reporting.quote_count,
    )
    generated["quotable_excerpts_md"] = generate_excerpts_md(excerpts, instruction, output_dir)

    stats = generate_summary_stats(
        posts,
        instruction,
        output_dir,
        collector_context=collector_context,
        top_quotes=excerpts,
    )
    generated["summary_stats_json"] = os.path.join(output_dir, "summary_stats.json")
    generated["summary_report_md"] = generate_summary_report(stats, instruction, output_dir)

    if instruction.validation_enabled:
        generated["validation_report_md"] = generate_validation_report(posts, instruction, output_dir)

    return generated
