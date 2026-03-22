"""
Unified cross-platform analysis engine.

v2 changes:
- explicit confidence scoring for relevance and categories
- analysis completion marker on each post
- category assignment gated by relevance by default
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

        post.category_scores = category_scores
        post.categories = assigned_categories
        post.analysis_complete = True
        filtered.append(post)

    return filtered


def posts_for_stats(posts: List[SocialPost], instruction: Instruction) -> List[SocialPost]:
    """Return the posts that should contribute to summary stats."""
    if getattr(instruction, "include_irrelevant_in_stats", False):
        return posts
    return [p for p in posts if p.is_relevant]


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

    co_occurrences = _compute_co_occurrences(posts)

    return {
        "platform_breakdown": {
            p: pdata["categories"] for p, pdata in platform_data.items()
        },
        "category_rankings": category_rankings,
        "global_ranking": global_ranking,
        "platform_unique_emphases": platform_unique,
        "co_occurrences": co_occurrences,
    }


def _compute_co_occurrences(posts: List[SocialPost]) -> List[dict]:
    pair_counts: Dict[tuple, int] = defaultdict(int)

    for post in posts:
        cats = sorted(set(post.categories))
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                pair_counts[(cats[i], cats[j])] += 1

    ranked = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return [
        {"pair": list(pair), "count": count}
        for pair, count in ranked
    ]
