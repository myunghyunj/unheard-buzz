"""Twitter/X platform agent -- searches recent tweets via API v2.

v2 collector patch:
- optional language allowlist enforced using API-provided `lang`
- normalized-text dedup across multiple queries
"""

import logging
import os
import time
import re
from typing import Dict, List, Optional

import requests

from config import Instruction, SocialPost
from language import guess_language, language_allowed

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
_TWEET_FIELDS = "created_at,public_metrics,conversation_id,in_reply_to_user_id,lang"
_EXPANSIONS = "author_id"
_USER_FIELDS = "username"
_MAX_RESULTS_PER_PAGE = 100
_RETRY_DELAY_DEFAULT = 60
_MAX_RETRIES = 3


def _get_bearer_token(instruction: Instruction) -> Optional[str]:
    env_var = instruction.twitter.api_key_env
    token = os.environ.get(env_var)
    if not token:
        logger.warning("Twitter Bearer token not found in %s. Skipping Twitter.", env_var)
        return None
    return token


def _build_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _request_with_retry(url: str, headers: dict, params: dict, retries: int = _MAX_RETRIES) -> Optional[dict]:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                logger.error("Twitter API returned 401 Unauthorized.")
                return None
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", _RETRY_DELAY_DEFAULT))
                logger.warning("Twitter rate limit hit (429). Waiting %ds (attempt %d/%d).", retry_after, attempt, retries)
                time.sleep(retry_after)
                continue
            if resp.status_code == 403:
                logger.warning("Twitter API returned 403 Forbidden.")
                return None

            logger.warning(
                "Twitter API returned %d: %s (attempt %d/%d)",
                resp.status_code, resp.text[:200], attempt, retries,
            )
        except requests.exceptions.Timeout:
            logger.warning("Twitter request timed out (attempt %d/%d)", attempt, retries)
        except requests.exceptions.RequestException as exc:
            logger.warning("Twitter request failed: %s (attempt %d/%d)", exc, attempt, retries)

    logger.error("Exhausted retries for Twitter API request.")
    return None


def _search_tweets(query: str, headers: dict, max_results: int, max_total: int, collected_so_far: int) -> List[dict]:
    tweets = []
    next_token = None
    remaining = max_total - collected_so_far

    if remaining <= 0:
        return tweets

    while remaining > 0:
        page_size = min(_MAX_RESULTS_PER_PAGE, max_results, remaining)
        params = {
            "query": query,
            "max_results": max(10, page_size),
            "tweet.fields": _TWEET_FIELDS,
            "expansions": _EXPANSIONS,
            "user.fields": _USER_FIELDS,
        }
        if next_token:
            params["next_token"] = next_token

        resp = _request_with_retry(_SEARCH_URL, headers, params)
        if resp is None:
            break

        users_map: Dict[str, str] = {}
        includes = resp.get("includes", {})
        for user in includes.get("users", []):
            users_map[user.get("id", "")] = user.get("username", "")

        data = resp.get("data", [])
        if not data:
            break

        for tweet in data:
            author_id = tweet.get("author_id", "")
            tweet["_username"] = users_map.get(author_id, author_id)
            tweets.append(tweet)

        remaining = max_total - collected_so_far - len(tweets)
        meta = resp.get("meta", {})
        next_token = meta.get("next_token")
        if not next_token:
            break

    return tweets


def _tweet_to_socialpost(tweet: dict) -> SocialPost:
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
            "tweet_id": tweet_id,
            "conversation_id": conversation_id,
            "retweet_count": metrics.get("retweet_count", 0),
            "quote_count": metrics.get("quote_count", 0),
            "impression_count": metrics.get("impression_count", 0),
            "lang": lang,
        },
    )


def _normalize_text_signature(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9가-힣\u0400-\u04FF\u3040-\u30ff\u4e00-\u9fff#@ ]+", "", text)
    return text.strip()


def _dedup_posts(posts: List[SocialPost], instruction: Instruction) -> tuple[List[SocialPost], int]:
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
            sig_key = (post.platform, signature)
            if sig_key in seen_signatures:
                removed += 1
                continue
            seen_signatures.add(sig_key)
            post.metadata["text_signature"] = signature[:120]

        kept.append(post)

    return kept, removed


def run_twitter(instruction: Instruction) -> dict:
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
        "lang_filtered": 0,
        "duplicates_removed": 0,
        "errors": 0,
    }

    for query_base in cfg.search_queries:
        if stats["tweets_collected"] >= cfg.max_total_tweets:
            break

        full_query = f"{query_base} {cfg.search_operators}".strip()
        stats["queries_executed"] += 1

        try:
            raw_tweets = _search_tweets(
                query=full_query,
                headers=headers,
                max_results=cfg.max_results_per_query,
                max_total=cfg.max_total_tweets,
                collected_so_far=stats["tweets_collected"],
            )

            for tweet in raw_tweets:
                tweet_lang = str(tweet.get("lang", "")).lower() or guess_language(
                    str(tweet.get("text", ""))
                )
                if not language_allowed(tweet_lang, instruction.language_allowlist):
                    stats["lang_filtered"] += 1
                    continue
                post = _tweet_to_socialpost(tweet)
                post.metadata["language_guess"] = tweet_lang
                all_posts.append(post)
                stats["tweets_collected"] += 1

        except Exception as exc:
            logger.error("Error processing Twitter query '%s': %s", query_base, exc)
            stats["errors"] += 1

    deduped_posts, duplicates_removed = _dedup_posts(all_posts, instruction)
    stats["duplicates_removed"] = duplicates_removed
    for post in deduped_posts:
        post.metadata.setdefault("collector_score", 0.0)
        post.metadata.setdefault("source_family", "community")
        post.metadata.setdefault("source_tier", 4)
        post.metadata.setdefault("evidence_class", "community_post")
        post.metadata.setdefault("publication_date", post.timestamp)
        post.metadata.setdefault("trust_weight", instruction.source_policy.trust_weights.get("community", 0.5))
        conversation_id = str(post.metadata.get("conversation_id") or post.source_id or "").strip()
        if conversation_id:
            independence_key = f"twitter:conversation:{conversation_id}".lower()
        else:
            fallback_post_id = str(post.metadata.get("tweet_id") or post.post_id).strip()
            independence_key = f"twitter:post:{fallback_post_id}".lower()
        post.metadata.setdefault("independence_key", independence_key)

    logger.info(
        "Twitter agent complete: %d tweets after dedup, %d lang-filtered, %d errors.",
        len(deduped_posts), stats["lang_filtered"], stats["errors"],
    )

    return {"posts": deduped_posts, "stats": stats}
