"""
YouTube platform agent for unheard-buzz.

v3 collector patch:
- stronger video scoring
- heuristic language allowlist support on comments
- normalized-text dedup
- collector-level scoring in metadata
"""

import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:  # pragma: no cover - dependency is optional for unit tests.
    build = None

    class HttpError(Exception):
        """Fallback HttpError when googleapiclient is unavailable."""
        pass


from config import Instruction, SocialPost, MIN_COMMENT_WORDS
from language import guess_language, language_allowed

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 2
_MAX_RETRIES = 5
_MIN_VIDEO_COMMENTS = 5
_DAILY_QUOTA_LIMIT = 10_000

_QUOTA_COSTS: Dict[str, int] = {
    "search.list": 100,
    "channels.list": 1,
    "playlistItems.list": 1,
    "videos.list": 1,
    "commentThreads.list": 1,
    "comments.list": 1,
}

_SPAM_PATTERNS: List[re.Pattern] = [
    re.compile(r"https?://\S+.*https?://\S+", re.IGNORECASE),
    re.compile(r"check\s+out\s+my\s+channel", re.IGNORECASE),
    re.compile(r"subscribe\s+to\s+(my|our)", re.IGNORECASE),
    re.compile(r"sub\s+to\s+my", re.IGNORECASE),
    re.compile(r"use\s+code\b", re.IGNORECASE),
    re.compile(r"\d+\s*%\s*off", re.IGNORECASE),
]

_FIRST_SPAM_RE = re.compile(r"^\s*(first!*|1st!*|second!*|2nd!*|third!*|3rd!*)\s*$", re.IGNORECASE)
_TIMESTAMP_ONLY_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(:\d{2})?\s*)+$")


class _QuotaTracker:
    def __init__(self, limit: int = _DAILY_QUOTA_LIMIT) -> None:
        self.limit = limit
        self._used = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(self.limit - self._used, 0)

    def use(self, operation: str) -> None:
        self._used += _QUOTA_COSTS.get(operation, 1)

    def check(self, operation: str) -> bool:
        return self._used + _QUOTA_COSTS.get(operation, 1) <= self.limit

    @property
    def exceeded(self) -> bool:
        return self._used >= self.limit

    def summary(self) -> str:
        pct = (self._used / self.limit * 100) if self.limit else 0
        return f"[quota] {self._used}/{self.limit} units used ({pct:.1f}%), {self.remaining} remaining."


def _build_youtube_client(api_key: str):
    if not api_key:
        raise ValueError("Set YOUTUBE_API_KEY (or configured env var) before running YouTube collection.")
    if build is None:
        raise ImportError("googleapiclient is required for YouTube collection. Install repo requirements first.")
    return build("youtube", "v3", developerKey=api_key)


def _api_call_with_retry(request, quota: _QuotaTracker, operation: str, description: str = "API call"):
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = request.execute()
            quota.use(operation)
            return response
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            if status == 403 and b"quotaExceeded" in (exc.content or b""):
                raise RuntimeError("YouTube API daily quota exceeded.") from exc
            if status in (403, 429, 500, 503) and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE_SECONDS ** attempt
                time.sleep(wait)
                continue
            if status == 404:
                return None
            raise
    response = request.execute()
    quota.use(operation)
    return response


def _apply_term_corrections(query: str, instruction: Instruction) -> str:
    corrected = query
    corrections = getattr(instruction.youtube, "term_corrections", {}) or {}
    for source, target in corrections.items():
        corrected = re.sub(re.escape(source), target, corrected, flags=re.IGNORECASE)
    return corrected


def _get_channel_details(youtube, channel_id: str, quota: _QuotaTracker) -> Optional[dict]:
    if not quota.check("channels.list"):
        return None

    request = youtube.channels().list(part="snippet,statistics,contentDetails", id=channel_id)
    response = _api_call_with_retry(request, quota, "channels.list", f"channel details ({channel_id})")
    if not response or not response.get("items"):
        return None

    item = response["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    uploads_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")

    return {
        "channel_id": channel_id,
        "name": snippet.get("title", ""),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "description": snippet.get("description", ""),
        "uploads_id": uploads_id,
        "publishedAt": snippet.get("publishedAt", ""),
        "custom_url": snippet.get("customUrl", ""),
    }


def _search_channels(youtube, query: str, max_results: int, quota: _QuotaTracker, instruction: Instruction) -> List[dict]:
    query = _apply_term_corrections(query, instruction)
    if not quota.check("search.list"):
        return []

    request = youtube.search().list(part="snippet", q=query, type="channel", maxResults=min(max_results, 25))
    response = _api_call_with_retry(request, quota, "search.list", f"search channels '{query}'")
    if not response or not response.get("items"):
        return []

    channels = []
    for item in response["items"]:
        channel_id = item["snippet"]["channelId"]
        details = _get_channel_details(youtube, channel_id, quota)
        if details is not None:
            channels.append(details)
    return channels


def _normalize_channel_key(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("https://www.youtube.com/", "")
    value = value.lstrip("@/")
    return re.sub(r"[^a-z0-9]+", "", value)


def _channel_matches_seed(channel: dict, seed: dict) -> bool:
    targets = {
        _normalize_channel_key(seed.get("handle", "")),
        _normalize_channel_key(seed.get("name", "")),
    }
    targets.discard("")
    if not targets:
        return False

    candidates = {
        _normalize_channel_key(channel.get("name", "")),
        _normalize_channel_key(channel.get("custom_url", "")),
        _normalize_channel_key(channel.get("handle", "")),
    }
    candidates.discard("")
    return bool(targets & candidates)


def _merge_channel_seed(channel: dict, seed: dict) -> dict:
    merged = dict(channel)
    for key, value in seed.items():
        if value in ("", None, [], {}):
            continue
        merged[key] = value
    if not merged.get("handle") and seed.get("handle"):
        merged["handle"] = seed["handle"]
    if not merged.get("url"):
        handle = str(merged.get("handle", "")).strip()
        if handle:
            if not handle.startswith("@"):
                handle = "@" + handle.lstrip("/")
            merged["url"] = f"https://www.youtube.com/{handle}"
        elif merged.get("custom_url"):
            merged["url"] = f"https://www.youtube.com/{merged['custom_url']}"
    return merged


def _discover_channels(youtube, instruction: Instruction, quota: _QuotaTracker) -> List[dict]:
    seen = set()
    channels = []

    for seed in instruction.youtube.priority_channels:
        if len(channels) >= instruction.youtube.max_channels:
            break
        query = seed.get("handle") or seed.get("name") or ""
        if not query:
            continue
        found = _search_channels(youtube, query, 5, quota, instruction)
        matched = None
        for channel in found:
            if _channel_matches_seed(channel, seed):
                matched = _merge_channel_seed(channel, seed)
                break
        if matched and matched["channel_id"] not in seen:
            seen.add(matched["channel_id"])
            channels.append(matched)

    for query in instruction.youtube.search_queries:
        if len(channels) >= instruction.youtube.max_channels:
            break
        found = _search_channels(youtube, query, instruction.youtube.max_channels - len(channels), quota, instruction)
        for ch in found:
            for seed in instruction.youtube.priority_channels:
                if _channel_matches_seed(ch, seed):
                    ch = _merge_channel_seed(ch, seed)
                    break
            if ch["channel_id"] not in seen:
                seen.add(ch["channel_id"])
                channels.append(ch)

    return channels


def _list_channel_videos(youtube, playlist_id: str, max_results: int, quota: _QuotaTracker) -> List[dict]:
    videos = []
    next_page = None

    while len(videos) < max_results:
        if not quota.check("playlistItems.list"):
            break
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=min(50, max_results),
            pageToken=next_page,
        )
        response = _api_call_with_retry(request, quota, "playlistItems.list", f"playlist items ({playlist_id})")
        if not response or not response.get("items"):
            break

        for item in response["items"]:
            video_id = item.get("contentDetails", {}).get("videoId", "")
            if not video_id:
                continue
            videos.append({
                "videoId": video_id,
                "title": item.get("snippet", {}).get("title", ""),
                "publishedAt": item.get("snippet", {}).get("publishedAt", ""),
                "channelId": item.get("snippet", {}).get("channelId", ""),
                "channelTitle": item.get("snippet", {}).get("channelTitle", ""),
            })
            if len(videos) >= max_results:
                break

        next_page = response.get("nextPageToken")
        if not next_page:
            break

    return videos


def _get_video_metadata(youtube, video_ids: List[str], quota: _QuotaTracker) -> Dict[str, dict]:
    stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        if not quota.check("videos.list"):
            break
        request = youtube.videos().list(part="snippet,statistics", id=",".join(batch))
        response = _api_call_with_retry(request, quota, "videos.list", "video metadata batch")
        if not response or not response.get("items"):
            continue

        for item in response["items"]:
            snippet = item.get("snippet", {})
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "publishedAt": snippet.get("publishedAt", ""),
                "viewCount": int(s.get("viewCount", 0)),
                "commentCount": int(s.get("commentCount", 0)),
                "commentsDisabled": "commentCount" not in s,
            }
    return stats


def _recency_bonus(published_at: str) -> float:
    if not published_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_days = max(0.0, (datetime.now(timezone.utc) - dt).days)
        if age_days <= 30:
            return 2.5
        if age_days <= 180:
            return 1.5
        if age_days <= 365:
            return 0.75
        return 0.0
    except Exception:
        return 0.0


def _score_video(video_info: dict, priority_keywords: List[str]) -> float:
    title = video_info.get("title", "").lower()
    description = video_info.get("description", "").lower()
    comment_count = video_info.get("commentCount", 0)
    view_count = video_info.get("viewCount", 0)
    comments_disabled = video_info.get("commentsDisabled", False)

    if comments_disabled:
        return -9999.0

    text = f"{title} {description}"
    keyword_hits = sum(1 for kw in priority_keywords if kw.lower() in text)
    keyword_score = keyword_hits * 12.0
    comment_score = math.log10(comment_count + 1) * 4.0
    view_score = math.log10(view_count + 1) * 2.0
    recency = _recency_bonus(video_info.get("publishedAt", ""))
    penalty = -1000.0 if comment_count < _MIN_VIDEO_COMMENTS else 0.0
    return round(keyword_score + comment_score + view_score + recency + penalty, 3)


def _video_topic_tags(video_info: dict, priority_keywords: List[str]) -> List[str]:
    text = f"{video_info.get('title', '')} {video_info.get('description', '')}".lower()
    return [keyword for keyword in priority_keywords if keyword.lower() in text]


def _select_all_videos(youtube, channels: List[dict], instruction: Instruction, quota: _QuotaTracker) -> List[dict]:
    selected = []
    for channel in channels:
        playlist_id = channel.get("uploads_id", "")
        if not playlist_id:
            continue
        raw_videos = _list_channel_videos(
            youtube,
            playlist_id,
            max_results=max(instruction.youtube.max_videos_per_channel * 4, 30),
            quota=quota,
        )
        if not raw_videos:
            continue

        stats = _get_video_metadata(youtube, [v["videoId"] for v in raw_videos], quota)
        scored = []
        for v in raw_videos:
            s = stats.get(v["videoId"], {})
            if s.get("title"):
                v["title"] = s.get("title", v.get("title", ""))
            if s.get("publishedAt"):
                v["publishedAt"] = s.get("publishedAt", v.get("publishedAt", ""))
            v["viewCount"] = s.get("viewCount", 0)
            v["commentCount"] = s.get("commentCount", 0)
            v["commentsDisabled"] = s.get("commentsDisabled", True)
            v["description"] = s.get("description", v.get("description", ""))
            v["channelName"] = channel["name"]
            v["collector_video_score"] = _score_video(v, instruction.youtube.video_priority_keywords)
            v["topic_tags"] = _video_topic_tags(v, instruction.youtube.video_priority_keywords)
            scored.append((v["collector_video_score"], v))

        scored.sort(key=lambda x: x[0], reverse=True)
        keep = [v for score, v in scored[:instruction.youtube.max_videos_per_channel] if score > -9999]
        selected.extend(keep)
    return selected


def _is_comments_disabled_error(error: HttpError) -> bool:
    return error.resp.status == 403 and b"commentsDisabled" in (error.content or b"")


def _fetch_all_replies(youtube, parent_id: str, video_id: str, channel_name: str, quota: _QuotaTracker) -> List[dict]:
    replies = []
    page_token = None

    while True:
        if not quota.check("comments.list"):
            break

        request = youtube.comments().list(
            part="snippet",
            parentId=parent_id,
            maxResults=100,
            pageToken=page_token,
        )
        response = _api_call_with_retry(request, quota, "comments.list", f"replies for {parent_id}")
        if not response:
            break

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            text = snippet.get("textOriginal") or snippet.get("textDisplay", "")
            replies.append({
                "comment_id": item["id"],
                "video_id": video_id,
                "channel_name": channel_name,
                "author": snippet.get("authorDisplayName", ""),
                "text": text,
                "like_count": snippet.get("likeCount", 0),
                "is_reply": True,
                "parent_id": parent_id,
                "timestamp": snippet.get("publishedAt", ""),
            })

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return replies


def _parse_inline_replies(thread: dict, video_id: str, channel_name: str, parent_id: str) -> List[dict]:
    replies = []
    for item in thread.get("replies", {}).get("comments", []):
        snippet = item.get("snippet", {})
        text = snippet.get("textOriginal") or snippet.get("textDisplay", "")
        replies.append({
            "comment_id": item["id"],
            "video_id": video_id,
            "channel_name": channel_name,
            "author": snippet.get("authorDisplayName", ""),
            "text": text,
            "like_count": snippet.get("likeCount", 0),
            "is_reply": True,
            "parent_id": parent_id,
            "timestamp": snippet.get("publishedAt", ""),
        })
    return replies


def _extract_comments_for_video(youtube, video: dict, max_comments: int, quota: _QuotaTracker) -> List[dict]:
    video_id = video["videoId"]
    channel_name = video.get("channelName", "")
    comments = []
    page_token = None

    while len(comments) < max_comments:
        if not quota.check("commentThreads.list"):
            break

        try:
            request = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=100,
                pageToken=page_token,
            )
            response = _api_call_with_retry(request, quota, "commentThreads.list", f"commentThreads for {video_id}")
        except HttpError as exc:
            if _is_comments_disabled_error(exc):
                return []
            raise

        if not response:
            break

        for thread in response.get("items", []):
            if len(comments) >= max_comments:
                break

            top_resource = thread["snippet"]["topLevelComment"]
            top_id = top_resource["id"]
            top_snippet = top_resource["snippet"]
            text = top_snippet.get("textOriginal") or top_snippet.get("textDisplay", "")

            comments.append({
                "comment_id": top_id,
                "video_id": video_id,
                "channel_name": channel_name,
                "author": top_snippet.get("authorDisplayName", ""),
                "text": text,
                "like_count": top_snippet.get("likeCount", 0),
                "is_reply": False,
                "parent_id": None,
                "timestamp": top_snippet.get("publishedAt", ""),
            })

            total_reply_count = thread["snippet"].get("totalReplyCount", 0)
            if total_reply_count == 0:
                continue

            if total_reply_count > 5:
                reply_dicts = _fetch_all_replies(youtube, top_id, video_id, channel_name, quota)
            else:
                reply_dicts = _parse_inline_replies(thread, video_id, channel_name, top_id)

            remaining = max_comments - len(comments)
            comments.extend(reply_dicts[:remaining])

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return comments


def _extract_all_comments(youtube, videos: List[dict], instruction: Instruction, quota: _QuotaTracker) -> List[dict]:
    all_comments = []
    max_comments = instruction.youtube.max_comments_per_video

    for video in videos:
        if quota.exceeded:
            break
        raw = _extract_comments_for_video(youtube, video, max_comments, quota)
        all_comments.extend(raw)
    return all_comments


def _is_spam(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SPAM_PATTERNS)


def _normalize_text_signature(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9가-힣\u0400-\u04FF\u3040-\u30ff\u4e00-\u9fff ]+", "", text)
    return text.strip()


def _collector_score(text: str, like_count: int, is_reply: bool, instruction: Instruction) -> float:
    sig = _normalize_text_signature(text)
    keyword_hits = 0
    for kw in instruction.relevance_keywords:
        if kw and kw.lower() in sig:
            keyword_hits += 1
    length_bonus = 1.0 if 40 <= len(sig) <= 400 else 0.0
    engagement = min(like_count / 10.0, 5.0)
    reply_bonus = 0.5 if is_reply else 1.0
    return round(keyword_hits * 1.5 + length_bonus + engagement + reply_bonus, 3)


def _is_noise(text: str, channel_name: str, author: str, instruction: Instruction) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if author.strip().lower() == channel_name.strip().lower():
        return True
    if _TIMESTAMP_ONLY_RE.match(stripped):
        return True
    if _FIRST_SPAM_RE.match(stripped):
        return True
    min_words = max(1, getattr(instruction, "min_comment_words", MIN_COMMENT_WORDS))
    if len(stripped.split()) < min_words:
        return True
    if _is_spam(stripped):
        return True
    return False


def _convert_comments_to_posts(comments: List[dict], videos: List[dict], instruction: Instruction) -> Tuple[List[SocialPost], int]:
    video_lookup: Dict[str, dict] = {v["videoId"]: v for v in videos}
    posts: List[SocialPost] = []
    lang_filtered = 0

    for comment in comments:
        channel_name = comment.get("channel_name", "")
        author = comment.get("author", "")
        text = comment.get("text", "")

        if _is_noise(text, channel_name, author, instruction):
            continue

        lang = guess_language(text)
        if not language_allowed(lang, instruction.language_allowlist):
            lang_filtered += 1
            continue

        video = video_lookup.get(comment["video_id"], {})
        post = SocialPost(
            post_id=comment["comment_id"],
            platform="youtube",
            source_id=comment["video_id"],
            source_title=video.get("title", ""),
            author=author,
            text=text,
            like_count=comment.get("like_count", 0),
            is_reply=comment.get("is_reply", False),
            parent_id=comment.get("parent_id"),
            timestamp=comment.get("timestamp", ""),
            url=f"https://youtube.com/watch?v={comment['video_id']}",
            word_count=len(text.split()),
            metadata={
                "channel": channel_name,
                "view_count": video.get("viewCount", 0),
                "collector_video_score": video.get("collector_video_score", 0.0),
                "language_guess": lang,
                "collector_score": _collector_score(text, comment.get("like_count", 0), comment.get("is_reply", False), instruction),
            },
        )
        posts.append(post)

    return posts, lang_filtered


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


def run_youtube(instruction: Instruction) -> dict:
    yt_cfg = instruction.youtube
    if not yt_cfg.enabled:
        return {"posts": [], "channels": [], "videos": [], "stats": {}}

    api_key = os.environ.get(yt_cfg.api_key_env, "")
    youtube = _build_youtube_client(api_key)
    quota = _QuotaTracker()

    channels = _discover_channels(youtube, instruction, quota)
    videos = _select_all_videos(youtube, channels, instruction, quota)
    raw_comments = _extract_all_comments(youtube, videos, instruction, quota)
    posts, lang_filtered = _convert_comments_to_posts(raw_comments, videos, instruction)
    posts, duplicates_removed = _dedup_posts(posts, instruction)
    for post in posts:
        post.metadata.setdefault("source_family", "community")
        post.metadata.setdefault("source_tier", 4)
        post.metadata.setdefault("evidence_class", "community_comment")
        post.metadata.setdefault("publication_date", post.timestamp)
        post.metadata.setdefault("trust_weight", instruction.source_policy.trust_weights.get("community", 0.5))
        post.metadata.setdefault("independence_key", "community:youtube.com")

    reply_posts = [p for p in posts if p.is_reply]
    unique_authors = len({p.author for p in posts})

    stats = {
        "channels_discovered": len(channels),
        "videos_selected": len(videos),
        "raw_comments_extracted": len(raw_comments),
        "posts_after_filtering": len(posts),
        "reply_posts": len(reply_posts),
        "unique_authors": unique_authors,
        "lang_filtered": lang_filtered,
        "duplicates_removed": duplicates_removed,
        "quota_used": quota.used,
        "quota_remaining": quota.remaining,
    }

    return {
        "posts": posts,
        "channels": channels,
        "videos": videos,
        "stats": stats,
    }
