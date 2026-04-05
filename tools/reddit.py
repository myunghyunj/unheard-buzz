"""Reddit platform agent -- extracts posts and comments from subreddits.

v3 collector patch:
- normalized-text dedup across overlapping searches
- heuristic language allowlist support
- collector-level scoring in metadata
"""

import logging
import time
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import requests

from config import Instruction, SocialPost
from language import guess_language, language_allowed

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "unheard-buzz/3.0 (research toolkit)"}
_BASE_URL = "https://www.reddit.com"
_REQUEST_DELAY = 1.0
_RETRY_DELAY = 60
_MAX_RETRIES = 3
_COMMENT_DEPTH_LIMIT = 10


def _rate_limit():
    time.sleep(_REQUEST_DELAY)


def _get_json(url: str, params: Optional[dict] = None, retries: int = _MAX_RETRIES) -> Optional[dict]:
    for attempt in range(1, retries + 1):
        try:
            _rate_limit()
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", _RETRY_DELAY))
                logger.warning("Rate-limited by Reddit (429). Retrying in %ds (attempt %d/%d).", retry_after, attempt, retries)
                time.sleep(retry_after)
                continue
            if resp.status_code == 403:
                logger.warning("Subreddit is private or quarantined (403): %s", url)
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
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return ""


def _search_subreddit(subreddit: str, query: str, sort: str, time_filter: str, limit: int) -> List[dict]:
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


def _traverse_comments(children: list, post_id: str, post_title: str, subreddit: str, depth: int = 0) -> List[SocialPost]:
    posts = []
    if depth > _COMMENT_DEPTH_LIMIT:
        return posts

    for child in children:
        kind = child.get("kind", "")
        data = child.get("data", {})
        if kind != "t1":
            continue

        body = data.get("body", "")
        author = data.get("author", "[deleted]")
        if author in ("[deleted]", "[removed]") or body in ("[deleted]", "[removed]"):
            continue

        comment_id = data.get("id", "")
        parent_raw = data.get("parent_id", "")
        parent_id = parent_raw.split("_", 1)[-1] if "_" in parent_raw else parent_raw

        posts.append(SocialPost(
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
        ))

        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            posts.extend(_traverse_comments(reply_children, post_id, post_title, subreddit, depth + 1))

    return posts


def _fetch_comments(subreddit: str, post_id: str, post_title: str, max_comments: int) -> List[SocialPost]:
    url = f"{_BASE_URL}/r/{subreddit}/comments/{post_id}.json"
    params = {"limit": min(max_comments, 200)}
    data = _get_json(url, params=params)
    if data is None or not isinstance(data, list) or len(data) < 2:
        return []
    comment_listing = data[1].get("data", {}).get("children", [])
    return _traverse_comments(comment_listing, post_id, post_title, subreddit)


def _normalize_text_signature(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9가-힣\u0400-\u04FF\u3040-\u30ff\u4e00-\u9fff ]+", "", text)
    return text.strip()


def _collector_score(post: SocialPost, instruction: Instruction) -> float:
    sig = _normalize_text_signature(post.text)
    keyword_hits = 0
    for kw in instruction.relevance_keywords:
        if kw and kw.lower() in sig:
            keyword_hits += 1

    length_bonus = 1.0 if 40 <= len(sig) <= 400 else 0.0
    engagement = min(post.like_count / 10.0, 5.0)
    reply_bonus = 0.5 if post.is_reply else 1.0
    score = keyword_hits * 1.5 + length_bonus + engagement + reply_bonus
    return round(score, 3)


def _dedup_posts(posts: List[SocialPost], instruction: Instruction) -> Tuple[List[SocialPost], int]:
    if not getattr(instruction, "dedup_normalized_text", True):
        return posts, 0

    seen_ids = set()
    seen_signatures = set()
    kept = []
    removed = 0
    min_chars = max(1, getattr(instruction, "dedup_min_chars", 40))

    for post in posts:
        if post.post_id in seen_ids:
            removed += 1
            continue
        seen_ids.add(post.post_id)

        signature = _normalize_text_signature(post.text)
        if len(signature) >= min_chars:
            sig_key = (post.platform, post.source_id, signature)
            if sig_key in seen_signatures:
                removed += 1
                continue
            seen_signatures.add(sig_key)
            post.metadata["text_signature"] = signature[:120]

        kept.append(post)

    return kept, removed


def run_reddit(instruction: Instruction) -> dict:
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
        "lang_filtered": 0,
        "duplicates_removed": 0,
        "errors": 0,
    }

    for subreddit in cfg.subreddits:
        stats["subreddits_searched"] += 1
        for query in cfg.search_queries:
            stats["queries_executed"] += 1
            logger.info("Searching r/%s for: %s", subreddit, query)
            try:
                results = _search_subreddit(subreddit, query, cfg.sort, cfg.time_filter, cfg.max_posts_per_query)
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

    for post_data in raw_posts:
        pid = post_data.get("id", "")
        subreddit = post_data.get("_subreddit", post_data.get("subreddit", ""))
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        author = post_data.get("author", "[deleted]")

        if author in ("[deleted]", "[removed]"):
            continue

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

        lang = guess_language(post_obj.text)
        if not language_allowed(lang, instruction.language_allowlist):
            stats["lang_filtered"] += 1
        else:
            post_obj.metadata["language_guess"] = lang
            post_obj.metadata["collector_score"] = _collector_score(post_obj, instruction)
            all_posts.append(post_obj)

        num_comments = post_data.get("num_comments", 0)
        if num_comments > 0:
            try:
                comments = _fetch_comments(subreddit, pid, title, cfg.max_comments_per_post)
                for comment in comments:
                    lang = guess_language(comment.text)
                    if not language_allowed(lang, instruction.language_allowlist):
                        stats["lang_filtered"] += 1
                        continue
                    comment.metadata["language_guess"] = lang
                    comment.metadata["collector_score"] = _collector_score(comment, instruction)
                    all_posts.append(comment)
                stats["comments_collected"] += len(comments)
            except Exception as exc:
                logger.error("Error fetching comments for post %s: %s", pid, exc)
                stats["errors"] += 1

    deduped_posts, duplicates_removed = _dedup_posts(all_posts, instruction)
    stats["duplicates_removed"] = duplicates_removed
    for post in deduped_posts:
        post.metadata.setdefault("source_family", "community")
        post.metadata.setdefault("source_tier", 4)
        post.metadata.setdefault("evidence_class", "community_post")
        post.metadata.setdefault("publication_date", post.timestamp)
        post.metadata.setdefault("trust_weight", instruction.source_policy.trust_weights.get("community", 0.5))
        subreddit = re.sub(r"[^a-z0-9]+", "-", str(post.metadata.get("subreddit", "")).strip().lower()).strip("-")
        source_id = post.source_id or post.post_id
        if subreddit:
            independence_key = f"reddit:{subreddit}:thread:{source_id}".lower()
        else:
            independence_key = f"reddit:thread:{source_id}".lower()
        post.metadata.setdefault("independence_key", independence_key)

    logger.info(
        "Reddit agent complete: %d total items after dedup (%d removed), %d lang-filtered, %d errors.",
        len(deduped_posts), duplicates_removed, stats["lang_filtered"], stats["errors"],
    )

    return {"posts": deduped_posts, "stats": stats}
