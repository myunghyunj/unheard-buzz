"""Reddit platform agent -- extracts posts and comments from subreddits.

Uses Reddit's public JSON API (no OAuth required for public data).
For each configured subreddit, searches with each query term, deduplicates
results by post ID, then fetches and recursively traverses comment trees.

All domain-specific configuration comes from the ``instruction`` parameter.
Nothing is hardcoded.
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import requests

from config import Instruction, SocialPost

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {"User-Agent": "MarketNeedsAnalyzer/1.0 (research)"}
_BASE_URL = "https://www.reddit.com"
_REQUEST_DELAY = 1.0        # seconds between requests (Reddit ~60 req/min)
_RETRY_DELAY = 60           # seconds to wait on 429
_MAX_RETRIES = 3
_COMMENT_DEPTH_LIMIT = 10   # avoid infinite recursion on deeply nested threads


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rate_limit():
    """Sleep to respect Reddit's rate limit."""
    time.sleep(_REQUEST_DELAY)


def _get_json(url: str, params: Optional[dict] = None,
              retries: int = _MAX_RETRIES) -> Optional[dict]:
    """Fetch JSON from Reddit with retry on 429 and error handling."""
    for attempt in range(1, retries + 1):
        try:
            _rate_limit()
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", _RETRY_DELAY))
                logger.warning(
                    "Rate-limited by Reddit (429). Retrying in %ds (attempt %d/%d).",
                    retry_after, attempt, retries,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 403:
                logger.warning(
                    "Subreddit is private or quarantined (403): %s", url,
                )
                return None

            if resp.status_code == 404:
                logger.warning("Reddit resource not found (404): %s", url)
                return None

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            logger.warning("Request timed out: %s (attempt %d/%d)", url, attempt, retries)
        except requests.exceptions.RequestException as exc:
            logger.warning("Request failed: %s (attempt %d/%d)", exc, attempt, retries)

    logger.error("Exhausted retries for: %s", url)
    return None


def _epoch_to_iso(epoch: float) -> str:
    """Convert a Unix epoch timestamp to ISO 8601 string."""
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return ""


def _search_subreddit(subreddit: str, query: str, sort: str,
                      time_filter: str, limit: int) -> List[dict]:
    """Search a subreddit and return raw post data dicts."""
    url = f"{_BASE_URL}/r/{subreddit}/search.json"
    params = {
        "q": query,
        "sort": sort,
        "t": time_filter,
        "limit": min(limit, 100),
        "restrict_sr": "on",
    }
    data = _get_json(url, params=params)
    if data is None:
        return []

    children = data.get("data", {}).get("children", [])
    return [child.get("data", {}) for child in children if child.get("data")]


def _traverse_comments(children: list, post_id: str, post_title: str,
                       subreddit: str, depth: int = 0) -> List[SocialPost]:
    """Recursively traverse Reddit's nested comment tree.

    Reddit comments are nested: each comment can have a ``replies`` field
    containing another listing of child comments.
    """
    posts = []
    if depth > _COMMENT_DEPTH_LIMIT:
        return posts

    for child in children:
        kind = child.get("kind", "")
        data = child.get("data", {})

        # Skip non-comment nodes (e.g., "more" stubs)
        if kind != "t1":
            continue

        body = data.get("body", "")
        author = data.get("author", "[deleted]")

        # Skip deleted or removed comments
        if author in ("[deleted]", "[removed]") or body in ("[deleted]", "[removed]"):
            continue

        comment_id = data.get("id", "")
        parent_raw = data.get("parent_id", "")
        # parent_id comes as "t1_xxx" or "t3_xxx"; strip prefix
        parent_id = parent_raw.split("_", 1)[-1] if "_" in parent_raw else parent_raw

        comment_post = SocialPost(
            post_id=f"reddit_comment_{comment_id}",
            platform="reddit",
            source_id=post_id,
            source_title=post_title,
            author=author,
            text=body,
            like_count=max(0, data.get("score", 0)),
            reply_count=0,
            is_reply=True,
            parent_id=parent_id,
            timestamp=_epoch_to_iso(data.get("created_utc", 0)),
            url=f"https://www.reddit.com{data.get('permalink', '')}",
            word_count=len(body.split()),
            metadata={"subreddit": subreddit, "depth": depth},
        )
        posts.append(comment_post)

        # Recurse into replies
        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            posts.extend(
                _traverse_comments(reply_children, post_id, post_title,
                                   subreddit, depth + 1)
            )

    return posts


def _fetch_comments(subreddit: str, post_id: str, post_title: str,
                    max_comments: int) -> List[SocialPost]:
    """Fetch and parse comments for a single Reddit post."""
    url = f"{_BASE_URL}/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": min(max_comments, 200)}
    data = _get_json(url, params=params)
    if data is None or not isinstance(data, list) or len(data) < 2:
        return []

    # data[0] = post listing, data[1] = comment listing
    comment_listing = data[1].get("data", {}).get("children", [])
    return _traverse_comments(comment_listing, post_id, post_title, subreddit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_reddit(instruction: Instruction) -> dict:
    """Main entry point for the Reddit agent.

    Searches configured subreddits with each query, deduplicates posts,
    fetches comment trees, and returns unified SocialPost objects.

    Returns:
        dict with keys:
            - posts: List[SocialPost] (both posts and comments)
            - stats: dict with collection statistics
    """
    cfg = instruction.reddit
    if not cfg.enabled:
        logger.info("Reddit is not enabled in instruction. Skipping.")
        return {"posts": [], "stats": {"skipped": True}}

    if not cfg.subreddits:
        logger.warning("No subreddits configured. Skipping Reddit.")
        return {"posts": [], "stats": {"no_subreddits": True}}

    if not cfg.search_queries:
        logger.warning("No search queries configured for Reddit. Skipping.")
        return {"posts": [], "stats": {"no_queries": True}}

    all_posts: List[SocialPost] = []
    seen_post_ids: Set[str] = set()
    raw_posts: List[dict] = []
    stats = {
        "subreddits_searched": 0,
        "queries_executed": 0,
        "raw_posts_found": 0,
        "unique_posts": 0,
        "comments_collected": 0,
        "errors": 0,
    }

    # --- Phase 1: Search and deduplicate posts ---
    for subreddit in cfg.subreddits:
        stats["subreddits_searched"] += 1
        for query in cfg.search_queries:
            stats["queries_executed"] += 1
            logger.info("Searching r/%s for: %s", subreddit, query)
            try:
                results = _search_subreddit(
                    subreddit, query, cfg.sort, cfg.time_filter,
                    cfg.max_posts_per_query,
                )
                for post_data in results:
                    pid = post_data.get("id", "")
                    if pid and pid not in seen_post_ids:
                        seen_post_ids.add(pid)
                        post_data["_subreddit"] = subreddit
                        raw_posts.append(post_data)
                stats["raw_posts_found"] += len(results)
            except Exception as exc:
                logger.error("Error searching r/%s: %s", subreddit, exc)
                stats["errors"] += 1

    stats["unique_posts"] = len(raw_posts)
    logger.info(
        "Reddit search complete: %d unique posts from %d raw results.",
        len(raw_posts), stats["raw_posts_found"],
    )

    # --- Phase 2: Convert posts and fetch comments ---
    for post_data in raw_posts:
        pid = post_data.get("id", "")
        subreddit = post_data.get("_subreddit", post_data.get("subreddit", ""))
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        author = post_data.get("author", "[deleted]")

        if author in ("[deleted]", "[removed]"):
            continue

        # Create the post SocialPost
        post_text = f"{title}\n\n{selftext}".strip() if selftext else title
        post_obj = SocialPost(
            post_id=f"reddit_post_{pid}",
            platform="reddit",
            source_id=pid,
            source_title=title,
            author=author,
            text=post_text,
            like_count=max(0, post_data.get("score", 0)),
            reply_count=post_data.get("num_comments", 0),
            is_reply=False,
            parent_id=None,
            timestamp=_epoch_to_iso(post_data.get("created_utc", 0)),
            url=f"https://www.reddit.com{post_data.get('permalink', '')}",
            word_count=len(post_text.split()),
            metadata={"subreddit": subreddit},
        )
        all_posts.append(post_obj)

        # Fetch comments for this post
        num_comments = post_data.get("num_comments", 0)
        if num_comments > 0:
            logger.info(
                "Fetching comments for post %s (%d comments reported).",
                pid, num_comments,
            )
            try:
                comments = _fetch_comments(
                    subreddit, pid, title, cfg.max_comments_per_post,
                )
                all_posts.extend(comments)
                stats["comments_collected"] += len(comments)
            except Exception as exc:
                logger.error("Error fetching comments for post %s: %s", pid, exc)
                stats["errors"] += 1

    logger.info(
        "Reddit agent complete: %d total items (%d posts + %d comments), %d errors.",
        len(all_posts), stats["unique_posts"],
        stats["comments_collected"], stats["errors"],
    )

    return {"posts": all_posts, "stats": stats}
