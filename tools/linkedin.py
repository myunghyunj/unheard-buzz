"""
LinkedIn platform agent — limited API access, supports manual CSV import.

LinkedIn's API is extremely restricted:
- Requires OAuth 2.0 with user authorization
- Most read endpoints need approved Marketing/Community Management products
- No public search API for posts/comments

This agent supports two modes:
1. API mode: if access token available, fetch organization posts (very limited)
2. Manual mode: import from user-provided CSV file (recommended)
"""

import csv
import logging
import os
import sys

from config import Instruction, SocialPost

logger = logging.getLogger(__name__)

MANUAL_CSV_PATH = os.path.join("input", "linkedin_export.csv")


def run_linkedin(instruction) -> dict:
    """
    LinkedIn platform agent entry point.

    Tries API if token available, otherwise falls back to CSV import.

    Returns:
        dict with keys: posts (List[SocialPost]), stats (dict)
    """
    token = os.environ.get(instruction.linkedin.api_key_env, "")

    if token:
        posts = _fetch_via_api(token, instruction)
    else:
        posts = _import_from_csv()

    for post in posts:
        post.metadata.setdefault("collector_score", 0.0)
        post.metadata.setdefault("source_family", "community")
        post.metadata.setdefault("source_tier", 4)
        post.metadata.setdefault("evidence_class", "community_post")
        post.metadata.setdefault("publication_date", post.timestamp)
        post.metadata.setdefault("trust_weight", instruction.source_policy.trust_weights.get("community", 0.5))
        post.metadata.setdefault("independence_key", "community:linkedin.com")

    stats = {
        "platform": "linkedin",
        "posts_collected": len(posts),
        "mode": "api" if token else "manual_csv",
    }

    logger.info(
        "LinkedIn: collected %d posts (mode=%s)", len(posts), stats["mode"]
    )
    return {"posts": posts, "stats": stats}


# ---------------------------------------------------------------------------
# API mode (very limited — requires approved OAuth app)
# ---------------------------------------------------------------------------

def _fetch_via_api(token: str, instruction) -> list:
    """Attempt to fetch posts via LinkedIn Marketing API."""
    try:
        import requests
    except ImportError:
        logger.error("requests library required. pip install requests")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    posts = []
    for query in instruction.linkedin.search_queries:
        # LinkedIn doesn't have a public search API.
        # The closest is fetching UGC posts from organizations you manage.
        # This is a best-effort attempt.
        logger.info("LinkedIn API: searching '%s' (limited endpoint)", query)

    # Try fetching user's own feed as a fallback
    try:
        resp = requests.get(
            "https://api.linkedin.com/v2/me",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 401:
            logger.warning(
                "LinkedIn: invalid or expired access token. "
                "Falling back to CSV import."
            )
            return _import_from_csv()
        elif resp.status_code == 403:
            logger.warning(
                "LinkedIn: insufficient permissions. "
                "Most endpoints require approved Marketing API products. "
                "Falling back to CSV import."
            )
            return _import_from_csv()
        elif resp.status_code != 200:
            logger.warning(
                "LinkedIn API returned %d. Falling back to CSV import.",
                resp.status_code,
            )
            return _import_from_csv()

        logger.info(
            "LinkedIn: authenticated successfully, but post search "
            "is not available on standard API tier. "
            "Use CSV import for best results."
        )
    except requests.RequestException as exc:
        logger.warning("LinkedIn API request failed: %s", exc)

    return posts


# ---------------------------------------------------------------------------
# Manual CSV import mode (recommended)
# ---------------------------------------------------------------------------

def _import_from_csv() -> list:
    """Import LinkedIn data from user-provided CSV."""
    if not os.path.exists(MANUAL_CSV_PATH):
        logger.info(
            "\n"
            "LinkedIn: No API token and no CSV file found.\n"
            "To include LinkedIn data:\n"
            "  1. Export posts/comments from LinkedIn\n"
            "  2. Save as %s\n"
            "     Columns: author, text, likes, date, url\n"
            "  3. Re-run the pipeline\n",
            MANUAL_CSV_PATH,
        )
        return []

    logger.info("LinkedIn: importing from %s", MANUAL_CSV_PATH)
    posts = []

    try:
        with open(MANUAL_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                text = row.get("text", "").strip()
                if not text:
                    continue

                try:
                    likes = int(row.get("likes", 0))
                except (ValueError, TypeError):
                    likes = 0

                post = SocialPost(
                    post_id=f"linkedin_{i}",
                    platform="linkedin",
                    source_id=f"linkedin_post_{i}",
                    source_title=text[:80],
                    author=row.get("author", "Unknown"),
                    text=text,
                    like_count=likes,
                    timestamp=row.get("date", ""),
                    url=row.get("url", ""),
                )
                posts.append(post)

        logger.info("LinkedIn: imported %d posts from CSV", len(posts))
    except Exception as exc:
        logger.error("Failed to parse LinkedIn CSV: %s", exc)

    return posts
