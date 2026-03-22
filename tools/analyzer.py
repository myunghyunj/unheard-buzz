"""
Unified cross-platform analysis engine.

Takes SocialPost lists from all platforms and applies shared filtering,
categorization, and cross-platform comparison logic. All domain-specific
behavior is driven by the Instruction config — no hardcoded terms.
"""

import re
from collections import defaultdict
from typing import Dict, List

from config import Instruction, SocialPost, MIN_COMMENT_WORDS


# ---------------------------------------------------------------------------
# Spam detection heuristics (platform-agnostic)
# ---------------------------------------------------------------------------

_SPAM_PATTERNS = [
    re.compile(r"(subscribe|sub to me|check.{0,5}my.{0,5}channel)", re.IGNORECASE),
    re.compile(r"(https?://\S+){2,}"),  # multiple URLs
    re.compile(r"(.)\1{9,}"),  # character repeated 10+ times
    re.compile(r"(earn|make)\s*\$\d+", re.IGNORECASE),
    re.compile(r"(follow me|DM me|link in bio)", re.IGNORECASE),
]


def _is_spam(text: str) -> bool:
    """Heuristic spam check across all platforms."""
    return any(pat.search(text) for pat in _SPAM_PATTERNS)


# ---------------------------------------------------------------------------
# Core filtering and annotation
# ---------------------------------------------------------------------------

def filter_posts(posts: List[SocialPost], instruction: Instruction) -> List[SocialPost]:
    """Apply shared filtering and annotation to all posts regardless of platform.

    Steps:
      1. Remove short posts (< MIN_COMMENT_WORDS)
      2. Remove spam
      3. Mark relevant (using instruction.relevance_keywords)
      4. Mark wishes (using instruction.wish_patterns)
      5. Categorize (using instruction.categories)
      6. Set word_count

    Returns the annotated list (spam/short posts excluded).
    """
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

        # Skip short posts
        if word_count < MIN_COMMENT_WORDS:
            continue

        # Skip spam
        if _is_spam(text):
            continue

        # Set word count
        post.word_count = word_count

        # Mark relevance
        text_lower = text.lower()
        post.is_relevant = bool(relevance_re.search(text_lower))

        # Mark wish
        post.has_wish = any(wr.search(text) for wr in wish_res)

        # Categorize
        post.categories = []
        for code, cat_re in category_res.items():
            if cat_re.search(text_lower):
                post.categories.append(code)

        filtered.append(post)

    return filtered


def _build_keyword_regex(keywords: List[str]) -> re.Pattern:
    """Build a single compiled regex that matches any keyword in the list.
    Each keyword is treated as a case-insensitive literal (not a regex)."""
    escaped = [re.escape(kw.lower()) for kw in keywords]
    pattern = "|".join(escaped)
    return re.compile(pattern, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Platform breakdown
# ---------------------------------------------------------------------------

def analyze_by_platform(posts: List[SocialPost]) -> Dict[str, dict]:
    """Break down analysis metrics by platform.

    Returns:
        {
            "youtube": {
                "total": int,
                "relevant": int,
                "wish": int,
                "categories": {"SF": 12, "PM": 8, ...}
            },
            ...
        }
    """
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

    # Convert defaultdicts to plain dicts for JSON serialization
    for p in platforms:
        platforms[p]["categories"] = dict(platforms[p]["categories"])

    return platforms


# ---------------------------------------------------------------------------
# Cross-platform insights
# ---------------------------------------------------------------------------

def get_cross_platform_insights(
    posts: List[SocialPost], instruction: Instruction
) -> dict:
    """Compare category rankings across platforms.

    Returns:
        {
            "platform_breakdown": {platform: {category: count}},
            "category_rankings": {
                platform: [(code, count), ...],  # sorted desc
            },
            "global_ranking": [(code, count), ...],
            "platform_unique_emphases": {
                platform: [codes that rank much higher here than globally]
            },
            "co_occurrences": {
                "pair": (code_a, code_b),
                "count": int,
            },
        }
    """
    platform_data = analyze_by_platform(posts)

    # Global category counts
    global_cats: Dict[str, int] = defaultdict(int)
    for pdata in platform_data.values():
        for cat, count in pdata["categories"].items():
            global_cats[cat] += count

    global_ranking = sorted(global_cats.items(), key=lambda x: x[1], reverse=True)

    # Per-platform rankings
    category_rankings: Dict[str, list] = {}
    for platform, pdata in platform_data.items():
        ranked = sorted(pdata["categories"].items(), key=lambda x: x[1], reverse=True)
        category_rankings[platform] = ranked

    # Platform-unique emphases: categories that rank in top 3 for a platform
    # but not in global top 3
    global_top3 = {code for code, _ in global_ranking[:3]}
    platform_unique: Dict[str, List[str]] = {}
    for platform, ranked in category_rankings.items():
        top3 = {code for code, _ in ranked[:3]}
        unique = top3 - global_top3
        if unique:
            platform_unique[platform] = sorted(unique)

    # Co-occurrence analysis
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
    """Find which category pairs frequently appear together in posts."""
    pair_counts: Dict[tuple, int] = defaultdict(int)

    for post in posts:
        cats = sorted(set(post.categories))
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                pair_counts[(cats[i], cats[j])] += 1

    # Return top 10 co-occurring pairs
    ranked = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return [
        {"pair": list(pair), "count": count}
        for pair, count in ranked
    ]
