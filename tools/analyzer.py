"""Unified cross-platform analysis engine.

v3 additions:
- explicit final ranking layer
- representative-post helpers for reporting
- category assignment still gated by relevance by default
"""

import re
from collections import defaultdict
from typing import Dict, List

from config import Instruction, SocialPost, MIN_COMMENT_WORDS


_SPAM_PATTERNS = [
    re.compile(r"(subscribe|sub to me|check.{0,5}my.{0,5}channel)", re.IGNORECASE),
    re.compile(r"(https?://\S+){2,}"),
    re.compile(r"(.)\1{9,}"),
    re.compile(r"(earn|make)\s*\$\d+", re.IGNORECASE),
    re.compile(r"(follow me|DM me|link in bio)", re.IGNORECASE),
]


def _is_spam(text: str) -> bool:
    return any(pat.search(text) for pat in _SPAM_PATTERNS)


def _build_keyword_regex(keywords: List[str]) -> re.Pattern:
    escaped = [re.escape(kw.lower()) for kw in keywords if kw]
    if not escaped:
        return re.compile(r"$^")
    pattern = "|".join(escaped)
    return re.compile(pattern, re.IGNORECASE)


def _count_keyword_hits(regex: re.Pattern, text_lower: str) -> int:
    return len(regex.findall(text_lower))


def _score_from_hits(hit_count: int, keyword_count: int) -> float:
    if keyword_count <= 0 or hit_count <= 0:
        return 0.0
    normalized = hit_count / min(keyword_count, 3)
    return round(min(1.0, normalized), 3)


def compute_final_rank_score(post: SocialPost) -> float:
    raw_collector = float(post.metadata.get("collector_score", 0.0) or 0.0)
    collector_score = min(1.0, max(0.0, raw_collector) / 8.0)
    relevance_score = min(max(post.relevance_score, 0.0), 1.0)
    category_score = max(post.category_scores.values()) if post.category_scores else 0.0
    wish_bonus = 0.15 if post.has_wish else 0.0
    engagement_bonus = min(post.like_count / 50.0, 0.25)
    score = (
        0.35 * collector_score
        + 0.40 * relevance_score
        + 0.25 * category_score
        + wish_bonus
        + engagement_bonus
    )
    return round(score, 4)


def filter_posts(posts: List[SocialPost], instruction: Instruction) -> List[SocialPost]:
    """
    Apply shared filtering and annotation to all posts regardless of platform.

    Steps:
      1. Remove short posts
      2. Remove spam
      3. Score relevance
      4. Mark wish language
      5. Score categories
      6. Assign categories only if relevant by default
      7. Mark analysis_complete
    """
    min_words = max(1, getattr(instruction, "min_comment_words", MIN_COMMENT_WORDS))
    relevance_re = _build_keyword_regex(instruction.relevance_keywords)
    wish_res = [re.compile(pat, re.IGNORECASE) for pat in instruction.wish_patterns]
    category_res = {
        code: _build_keyword_regex(cat["keywords"])
        for code, cat in instruction.categories.items()
    }
    segment_res = {
        code: _build_keyword_regex(segment["keywords"])
        for code, segment in instruction.segments.items()
    }

    filtered: List[SocialPost] = []

    for post in posts:
        text = post.text.strip()
        words = text.split()
        word_count = len(words)

        if word_count < min_words:
            continue
        if _is_spam(text):
            continue

        text_lower = text.lower()
        post.word_count = word_count

        relevance_hits = _count_keyword_hits(relevance_re, text_lower)
        post.relevance_score = _score_from_hits(
            relevance_hits, len(instruction.relevance_keywords)
        )
        post.is_relevant = relevance_hits > 0

        post.has_wish = any(wr.search(text) for wr in wish_res)

        category_scores: Dict[str, float] = {}
        assigned_categories: List[str] = []
        for code, cat_re in category_res.items():
            hits = _count_keyword_hits(cat_re, text_lower)
            score = _score_from_hits(
                hits,
                len(instruction.categories.get(code, {}).get("keywords", [])),
            )
            if score > 0:
                category_scores[code] = score
            if post.is_relevant and score > 0:
                assigned_categories.append(code)

        if post.is_relevant and not assigned_categories and category_scores:
            assigned_categories = sorted(
                category_scores.keys(),
                key=lambda c: category_scores[c],
                reverse=True
            )[:1]

        segment_scores: Dict[str, float] = {}
        assigned_segments: List[str] = []
        for code, seg_re in segment_res.items():
            hits = _count_keyword_hits(seg_re, text_lower)
            score = _score_from_hits(
                hits,
                len(instruction.segments.get(code, {}).get("keywords", [])),
            )
            if score > 0:
                segment_scores[code] = score
                assigned_segments.append(code)

        post.category_scores = category_scores
        post.categories = assigned_categories
        post.segment_scores = segment_scores
        post.segments = assigned_segments
        post.final_rank_score = compute_final_rank_score(post)
        post.analysis_complete = True
        filtered.append(post)

    return filtered


def posts_for_stats(posts: List[SocialPost], instruction: Instruction) -> List[SocialPost]:
    """Return the posts that should contribute to summary stats."""
    if getattr(instruction, "include_irrelevant_in_stats", False):
        return posts
    return [p for p in posts if p.is_relevant]


def representative_posts_by_category(
    posts: List[SocialPost],
    instruction: Instruction,
    per_category: int = 1,
) -> Dict[str, List[SocialPost]]:
    scoped = posts_for_stats(posts, instruction)
    buckets: Dict[str, List[SocialPost]] = defaultdict(list)

    for post in scoped:
        for cat in post.categories:
            buckets[cat].append(post)

    selected: Dict[str, List[SocialPost]] = {}
    for cat, items in buckets.items():
        ranked = sorted(
            items,
            key=lambda post: (
                compute_final_rank_score(post),
                post.relevance_score,
                post.like_count,
            ),
            reverse=True,
        )
        selected[cat] = ranked[:per_category]
    return selected


def analyze_by_platform(posts: List[SocialPost]) -> Dict[str, dict]:
    platforms: Dict[str, dict] = {}

    for post in posts:
        p = post.platform
        if p not in platforms:
            platforms[p] = {
                "total": 0,
                "relevant": 0,
                "wish": 0,
                "categories": defaultdict(int),
            }
        bucket = platforms[p]
        bucket["total"] += 1
        if post.is_relevant:
            bucket["relevant"] += 1
        if post.has_wish:
            bucket["wish"] += 1
        for cat in post.categories:
            bucket["categories"][cat] += 1

    for p in platforms:
        platforms[p]["categories"] = dict(platforms[p]["categories"])

    return platforms


def get_cross_platform_insights(posts: List[SocialPost], instruction: Instruction) -> dict:
    platform_data = analyze_by_platform(posts)

    global_cats: Dict[str, int] = defaultdict(int)
    for pdata in platform_data.values():
        for cat, count in pdata["categories"].items():
            global_cats[cat] += count

    global_ranking = sorted(global_cats.items(), key=lambda x: x[1], reverse=True)

    category_rankings: Dict[str, list] = {}
    for platform, pdata in platform_data.items():
        ranked = sorted(pdata["categories"].items(), key=lambda x: x[1], reverse=True)
        category_rankings[platform] = ranked

    global_top3 = {code for code, _ in global_ranking[:3]}
    platform_unique: Dict[str, List[str]] = {}
    for platform, ranked in category_rankings.items():
        top3 = {code for code, _ in ranked[:3]}
        unique = top3 - global_top3
        if unique:
            platform_unique[platform] = sorted(unique)

    co_occurrences = _compute_co_occurrences(
        posts,
        limit=max(1, getattr(instruction.reporting, "max_cooccurrence_pairs", 15)),
    )

    return {
        "platform_breakdown": {
            p: pdata["categories"] for p, pdata in platform_data.items()
        },
        "category_rankings": category_rankings,
        "global_ranking": global_ranking,
        "platform_unique_emphases": platform_unique,
        "co_occurrences": co_occurrences,
    }


def _compute_co_occurrences(posts: List[SocialPost], limit: int = 10) -> List[dict]:
    pair_counts: Dict[tuple, int] = defaultdict(int)

    for post in posts:
        cats = sorted(set(post.categories))
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                pair_counts[(cats[i], cats[j])] += 1

    ranked = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [
        {"pair": list(pair), "count": count}
        for pair, count in ranked
    ]
