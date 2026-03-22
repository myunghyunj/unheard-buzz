"""Twitter/X platform agent -- searches recent tweets via API v2.

Uses Bearer token authentication (free tier). The free tier provides
access to the recent search endpoint (last 7 days, 1500 tweets/month).

All domain-specific configuration comes from the ``instruction`` parameter.
Nothing is hardcoded.
"""

import logging
import os
import sys
import time
from typing import Dict, List, Optional

import requests

from config import Instruction, SocialPost

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
_TWEET_FIELDS = "created_at,public_metrics,conversation_id,in_reply_to_user_id,lang"
_EXPANSIONS = "author_id"
_USER_FIELDS = "username"
_MAX_RESULTS_PER_PAGE = 100  # Twitter API max per page
_RETRY_DELAY_DEFAULT = 60
_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_bearer_token(instruction: Instruction) -> Optional[str]:
    """Retrieve the Bearer token from the environment variable."""
    env_var = instruction.twitter.api_key_env
    token = os.environ.get(env_var)
    if not token:
        logger.warning(
            "Twitter Bearer token not found. Set the %s environment variable. "
            "To obtain a token:\n"
            "  1. Go to https://developer.twitter.com/en/portal/dashboard\n"
            "  2. Create a project and app\n"
            "  3. Generate a Bearer token\n"
            "  4. export %s=your_token_here\n"
            "Skipping Twitter.",
            env_var, env_var,
        )
        return None
    return token


def _build_headers(token: str) -> dict:
    """Build authorization headers for Twitter API v2."""
    return {"Authorization": f"Bearer {token}"}


def _search_tweets(query: str, headers: dict, max_results: int,
                   max_total: int, collected_so_far: int) -> List[dict]:
    """Execute a single query against the recent search endpoint.

    Handles pagination via next_token and respects max_total limit.
    Returns list of raw tweet dicts with author username attached.
    """
    tweets = []
    next_token = None
    remaining = max_total - collected_so_far

    if remaining <= 0:
        return tweets

    while remaining > 0:
        page_size = min(_MAX_RESULTS_PER_PAGE, max_results, remaining)
        params = {
            "query": query,
            "max_results": max(10, page_size),  # Twitter minimum is 10
            "tweet.fields": _TWEET_FIELDS,
            "expansions": _EXPANSIONS,
            "user.fields": _USER_FIELDS,
        }
        if next_token:
            params["next_token"] = next_token

        resp = _request_with_retry(_SEARCH_URL, headers, params)
        if resp is None:
            break

        # Build user ID -> username mapping from includes
        users_map: Dict[str, str] = {}
        includes = resp.get("includes", {})
        for user in includes.get("users", []):
            users_map[user.get("id", "")] = user.get("username", "")

        # Process tweets
        data = resp.get("data", [])
        if not data:
            break

        for tweet in data:
            author_id = tweet.get("author_id", "")
            tweet["_username"] = users_map.get(author_id, author_id)
            tweets.append(tweet)

        remaining = max_total - collected_so_far - len(tweets)

        # Check for next page
        meta = resp.get("meta", {})
        next_token = meta.get("next_token")
        if not next_token:
            break

    return tweets


def _request_with_retry(url: str, headers: dict, params: dict,
                        retries: int = _MAX_RETRIES) -> Optional[dict]:
    """Make a GET request with retry on rate limits and errors."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 401:
                logger.error(
                    "Twitter API returned 401 Unauthorized. "
                    "Your Bearer token may be invalid or expired. "
                    "Regenerate it at https://developer.twitter.com"
                )
                return None

            if resp.status_code == 429:
                retry_after = int(
                    resp.headers.get("Retry-After", _RETRY_DELAY_DEFAULT)
                )
                logger.warning(
                    "Twitter rate limit hit (429). Waiting %ds (attempt %d/%d). "
                    "Free tier: 1500 tweets/month, 1 request/second.",
                    retry_after, attempt, retries,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 403:
                logger.warning(
                    "Twitter API returned 403 Forbidden. "
                    "Your app may lack the required access level."
                )
                return None

            logger.warning(
                "Twitter API returned %d: %s (attempt %d/%d)",
                resp.status_code, resp.text[:200], attempt, retries,
            )

        except requests.exceptions.Timeout:
            logger.warning(
                "Twitter request timed out (attempt %d/%d)", attempt, retries,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Twitter request failed: %s (attempt %d/%d)",
                exc, attempt, retries,
            )

    logger.error("Exhausted retries for Twitter API request.")
    return None


def _tweet_to_socialpost(tweet: dict) -> SocialPost:
    """Convert a raw Twitter API v2 tweet dict to a SocialPost."""
    tweet_id = tweet.get("id", "")
    text = tweet.get("text", "")
    username = tweet.get("_username", "")
    conversation_id = tweet.get("conversation_id", "")
    in_reply_to = tweet.get("in_reply_to_user_id")
    metrics = tweet.get("public_metrics", {})
    created_at = tweet.get("created_at", "")
    lang = tweet.get("lang", "")

    is_reply = in_reply_to is not None

    return SocialPost(
        post_id=f"twitter_{tweet_id}",
        platform="twitter",
        source_id=conversation_id or tweet_id,
        source_title=text[:80] + ("..." if len(text) > 80 else ""),
        author=f"@{username}" if username else "",
        text=text,
        like_count=metrics.get("like_count", 0),
        reply_count=metrics.get("reply_count", 0),
        is_reply=is_reply,
        parent_id=conversation_id if is_reply else None,
        timestamp=created_at,
        url=f"https://twitter.com/i/status/{tweet_id}",
        word_count=len(text.split()),
        metadata={
            "retweet_count": metrics.get("retweet_count", 0),
            "quote_count": metrics.get("quote_count", 0),
            "impression_count": metrics.get("impression_count", 0),
            "lang": lang,
        },
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_twitter(instruction: Instruction) -> dict:
    """Main entry point for the Twitter/X agent.

    Searches for recent tweets matching each configured query,
    respecting the total tweet limit and rate limits.

    Returns:
        dict with keys:
            - posts: List[SocialPost]
            - stats: dict with collection statistics

    Note: Free tier limitations:
        - Only tweets from the last 7 days
        - 1500 tweets per month cap
        - 1 request per second
    """
    cfg = instruction.twitter
    if not cfg.enabled:
        logger.info("Twitter is not enabled in instruction. Skipping.")
        return {"posts": [], "stats": {"skipped": True}}

    token = _get_bearer_token(instruction)
    if not token:
        return {"posts": [], "stats": {"no_token": True}}

    if not cfg.search_queries:
        logger.warning("No search queries configured for Twitter. Skipping.")
        return {"posts": [], "stats": {"no_queries": True}}

    headers = _build_headers(token)
    all_posts: List[SocialPost] = []
    stats = {
        "queries_executed": 0,
        "tweets_collected": 0,
        "max_total": cfg.max_total_tweets,
        "errors": 0,
    }

    for query_base in cfg.search_queries:
        if stats["tweets_collected"] >= cfg.max_total_tweets:
            logger.info("Reached max_total_tweets (%d). Stopping.", cfg.max_total_tweets)
            break

        # Append search operators (e.g., "-is:retweet lang:en")
        full_query = f"{query_base} {cfg.search_operators}".strip()
        stats["queries_executed"] += 1

        logger.info(
            "Searching Twitter for: %s (collected %d/%d so far)",
            full_query, stats["tweets_collected"], cfg.max_total_tweets,
        )

        try:
            raw_tweets = _search_tweets(
                query=full_query,
                headers=headers,
                max_results=cfg.max_results_per_query,
                max_total=cfg.max_total_tweets,
                collected_so_far=stats["tweets_collected"],
            )

            for tweet in raw_tweets:
                post = _tweet_to_socialpost(tweet)
                all_posts.append(post)
                stats["tweets_collected"] += 1

            logger.info(
                "Query returned %d tweets. Total: %d/%d",
                len(raw_tweets), stats["tweets_collected"], cfg.max_total_tweets,
            )

        except Exception as exc:
            logger.error("Error processing Twitter query '%s': %s", query_base, exc)
            stats["errors"] += 1

    logger.info(
        "Twitter agent complete: %d tweets collected across %d queries, %d errors.",
        stats["tweets_collected"], stats["queries_executed"], stats["errors"],
    )

    return {"posts": all_posts, "stats": stats}
