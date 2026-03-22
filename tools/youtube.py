"""
YouTube platform agent for the multi-platform social media analysis tool.

Handles the full YouTube pipeline: channel discovery, video selection,
comment extraction, and conversion to the unified SocialPost format.

YouTube's native data hierarchy is channels -> videos -> comments (threaded).
This agent honors that structure while outputting unified SocialPost objects
for cross-platform analysis.

All domain-specific configuration comes from the ``instruction`` parameter.
Nothing is hardcoded.
"""

import logging
import math
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from config import Instruction, SocialPost, MIN_COMMENT_WORDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BACKOFF_BASE_SECONDS = 2
_MAX_RETRIES = 5
_MIN_VIDEO_COMMENTS = 5
_DAILY_QUOTA_LIMIT = 10_000

# Quota costs per YouTube API operation
_QUOTA_COSTS: Dict[str, int] = {
    "search.list": 100,
    "channels.list": 1,
    "playlistItems.list": 1,
    "videos.list": 1,
    "commentThreads.list": 1,
    "comments.list": 1,
}


# ---------------------------------------------------------------------------
# Spam / noise detection patterns (domain-agnostic)
# ---------------------------------------------------------------------------

_SPAM_PATTERNS: List[re.Pattern] = [
    re.compile(r"https?://\S+.*https?://\S+", re.IGNORECASE),
    re.compile(r"check\s+out\s+my\s+channel", re.IGNORECASE),
    re.compile(r"subscribe\s+to\s+(my|our)", re.IGNORECASE),
    re.compile(r"sub\s+to\s+my", re.IGNORECASE),
    re.compile(r"use\s+code\b", re.IGNORECASE),
    re.compile(r"\d+\s*%\s*off", re.IGNORECASE),
    re.compile(r"check\s+out\s+my\s+(video|content)", re.IGNORECASE),
    re.compile(r"free\s+(v-?bucks|robux|gift\s*card)", re.IGNORECASE),
    re.compile(r"(earn|make)\s+\$?\d+.*per\s+(day|hour|week)", re.IGNORECASE),
    re.compile(
        r"click\s+(the\s+)?link\s+in\s+(my|the)\s+(bio|description)",
        re.IGNORECASE,
    ),
    re.compile(r"dm\s+me\s+for", re.IGNORECASE),
    re.compile(
        r"follow\s+me\s+on\s+(instagram|twitter|tiktok|facebook)",
        re.IGNORECASE,
    ),
    re.compile(r"whatsapp\s*\+?\d{7,}", re.IGNORECASE),
    re.compile(r"promo\s*code", re.IGNORECASE),
]

_FIRST_SPAM_RE = re.compile(
    r"^\s*(first!*|1st!*|second!*|2nd!*|third!*|3rd!*)\s*$",
    re.IGNORECASE,
)

_EMOJI_ONLY_RE = re.compile(
    r"^[\s"
    r"\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FA6F"
    r"\U0001FA70-\U0001FAFF"
    r"\U00002702-\U000027B0"
    r"\U0000FE00-\U0000FE0F"
    r"\U0000200D"
    r"\U000020E3"
    r"\U00002600-\U000026FF"
    r"\U00002300-\U000023FF"
    r"\U0000231A-\U0000231B"
    r"\U000025AA-\U000025AB"
    r"\U000025FB-\U000025FE"
    r"]+$"
)

_TIMESTAMP_ONLY_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(:\d{2})?\s*)+$")


# =========================================================================
# Quota tracker
# =========================================================================

class _QuotaTracker:
    """Simple internal quota tracker for the YouTube Data API.

    YouTube free tier allows 10,000 units per day.  This tracker counts
    usage and prints a warning at 80% consumption.  At 100% it signals
    that no further calls should be made.
    """

    def __init__(self, limit: int = _DAILY_QUOTA_LIMIT) -> None:
        self.limit = limit
        self._used = 0
        self._warned = False

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(self.limit - self._used, 0)

    def use(self, operation: str) -> None:
        """Record the quota cost of *operation*."""
        cost = _QUOTA_COSTS.get(operation, 1)
        self._used += cost

        pct = self._used / self.limit
        if pct >= 0.80 and not self._warned:
            self._warned = True
            logger.warning(
                "[quota] WARNING: YouTube API quota at %.0f%% (%d / %d units used).",
                pct * 100,
                self._used,
                self.limit,
            )
            print(
                f"  [quota] WARNING: YouTube API quota at {pct*100:.0f}% "
                f"({self._used}/{self.limit} units used)."
            )

    def check(self, operation: str) -> bool:
        """Return True if there is enough quota remaining for *operation*.

        Returns False and prints a message when the quota is exhausted.
        """
        cost = _QUOTA_COSTS.get(operation, 1)
        if self._used + cost > self.limit:
            logger.warning(
                "[quota] Cannot execute %s (cost %d) -- "
                "quota exhausted (%d / %d).",
                operation,
                cost,
                self._used,
                self.limit,
            )
            return False
        return True

    @property
    def exceeded(self) -> bool:
        return self._used >= self.limit

    def summary(self) -> str:
        pct = (self._used / self.limit * 100) if self.limit else 0
        return (
            f"[quota] {self._used}/{self.limit} units used "
            f"({pct:.1f}%), {self.remaining} remaining."
        )


# =========================================================================
# YouTube API client
# =========================================================================

def _build_youtube_client(api_key: str) -> Resource:
    """Build and return a YouTube Data API v3 client."""
    if not api_key:
        raise ValueError(
            "YouTube API key must be a non-empty string. "
            "Set the environment variable referenced in instruction.youtube.api_key_env. "
            "Get a key from https://console.cloud.google.com/apis/credentials"
        )
    return build("youtube", "v3", developerKey=api_key)


# =========================================================================
# Retry helper
# =========================================================================

def _api_call_with_retry(
    request,
    quota: _QuotaTracker,
    operation: str,
    description: str = "API call",
):
    """Execute a YouTube API request with exponential back-off.

    Retries on HTTP 403 (rate-limit), 429 (too many requests), 500, and
    503 (server errors).  Returns ``None`` on 404.  Records quota usage
    on success.

    Raises ``RuntimeError`` when the quota-exceeded error is detected so
    the caller can stop gracefully.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = request.execute()
            quota.use(operation)
            return response
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0

            # Quota exceeded -- stop immediately.
            if status == 403 and b"quotaExceeded" in (exc.content or b""):
                raise RuntimeError(
                    "YouTube API daily quota exceeded. "
                    "Wait until quota resets or use a different API key."
                ) from exc

            # Comments disabled -- let caller handle.
            if status == 403 and b"commentsDisabled" in (exc.content or b""):
                raise

            if status in (403, 429, 500, 503) and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE_SECONDS ** attempt
                logger.warning(
                    "[rate-limit] %s: HTTP %s on attempt %d/%d. "
                    "Retrying in %ds ...",
                    description,
                    status,
                    attempt,
                    _MAX_RETRIES,
                    wait,
                )
                print(
                    f"  [rate-limit] {description}: HTTP {status} on attempt "
                    f"{attempt}/{_MAX_RETRIES}. Retrying in {wait}s ..."
                )
                time.sleep(wait)
                continue

            if status == 404:
                logger.info("[not-found] %s: resource not found (404).", description)
                return None

            logger.error("[error] %s: HTTP %s -- %s", description, status, exc)
            raise

    # Final attempt -- let the error propagate.
    logger.warning("[error] %s: exhausted retries, final attempt ...", description)
    response = request.execute()
    quota.use(operation)
    return response


# =========================================================================
# Phase 1 -- Channel Discovery
# =========================================================================

def _get_channel_details(
    youtube: Resource,
    channel_id: str,
    quota: _QuotaTracker,
) -> Optional[dict]:
    """Fetch channel metadata: title, subscriber count, description, last upload."""
    if not quota.check("channels.list"):
        return None

    request = youtube.channels().list(
        part="snippet,statistics,contentDetails",
        id=channel_id,
    )
    response = _api_call_with_retry(
        request, quota, "channels.list",
        f"channel details ({channel_id})",
    )
    if not response or not response.get("items"):
        return None

    item = response["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    # Try to pull the last upload date via the uploads playlist.
    last_upload = ""
    uploads_id = (
        item.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )
    if uploads_id and quota.check("playlistItems.list"):
        pl_req = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=1,
        )
        pl_resp = _api_call_with_retry(
            pl_req, quota, "playlistItems.list",
            f"last upload ({channel_id})",
        )
        if pl_resp and pl_resp.get("items"):
            last_upload = (
                pl_resp["items"][0]
                .get("snippet", {})
                .get("publishedAt", "")
            )

    custom_url = snippet.get("customUrl", "")
    url = (
        f"https://www.youtube.com/{custom_url}"
        if custom_url
        else f"https://www.youtube.com/channel/{channel_id}"
    )

    return {
        "channel_id": channel_id,
        "name": snippet.get("title", ""),
        "url": url,
        "subscribers": int(stats.get("subscriberCount", 0)),
        "description": snippet.get("description", ""),
        "last_upload": last_upload,
    }


def _resolve_priority_channels(
    youtube: Resource,
    priority_channels: List[dict],
    quota: _QuotaTracker,
) -> List[dict]:
    """Resolve priority channels listed in the instruction config.

    Each entry is a dict with ``handle`` and/or ``name`` keys.  Searches
    YouTube, fetches details, and returns a list of channel-info dicts.
    """
    channels: List[dict] = []

    for entry in priority_channels:
        handle = entry.get("handle", "")
        name = entry.get("name", handle)
        logger.info("[priority] Resolving %s (%s) ...", name, handle)
        print(f"[priority] Resolving {name} ({handle}) ...")

        if not quota.check("search.list"):
            print("  [quota] Approaching limit -- stopping priority resolution.")
            break

        search_term = handle.lstrip("@") if handle else name
        request = youtube.search().list(
            part="snippet",
            q=search_term,
            type="channel",
            maxResults=5,
        )
        response = _api_call_with_retry(
            request, quota, "search.list",
            f"search priority channel '{name}'",
        )
        if not response or not response.get("items"):
            print(f"  -> no results for '{search_term}', skipping.")
            continue

        # Pick the best match -- prefer an exact handle / title match.
        best_item = response["items"][0]
        for item in response["items"]:
            item_title = item["snippet"].get("channelTitle", "")
            if item_title.lower() == name.lower():
                best_item = item
                break

        channel_id = best_item["snippet"]["channelId"]
        details = _get_channel_details(youtube, channel_id, quota)
        if details is None:
            print(f"  -> could not fetch details for channel {channel_id}, skipping.")
            continue

        channels.append(details)
        print(f"  -> found: {details['name']} ({details['subscribers']:,} subs)")

    return channels


def _search_channels(
    youtube: Resource,
    query: str,
    max_results: int,
    quota: _QuotaTracker,
) -> List[dict]:
    """Search YouTube for channels matching *query*."""
    capped = min(max_results, 50)
    logger.info("[search] query='%s' (max %d) ...", query, capped)
    print(f"[search] query='{query}' (max {capped}) ...")

    if not quota.check("search.list"):
        print("  [quota] Approaching limit -- skipping search.")
        return []

    request = youtube.search().list(
        part="snippet",
        q=query,
        type="channel",
        maxResults=capped,
    )
    response = _api_call_with_retry(
        request, quota, "search.list",
        f"search channels '{query}'",
    )
    if not response or not response.get("items"):
        print("  -> no results.")
        return []

    channels: List[dict] = []
    for item in response["items"]:
        if not quota.check("channels.list"):
            print("  [quota] Approaching limit -- stopping channel detail fetch.")
            break
        channel_id = item["snippet"]["channelId"]
        details = _get_channel_details(youtube, channel_id, quota)
        if details is not None:
            channels.append(details)

    print(f"  -> found {len(channels)} channel(s).")
    return channels


def _discover_channels(
    youtube: Resource,
    instruction: Instruction,
    quota: _QuotaTracker,
) -> List[dict]:
    """Phase 1: discover channels from priority list and search queries.

    Returns a de-duplicated list of channel-info dicts.
    """
    seen_ids: set = set()
    all_channels: List[dict] = []

    def _add_unique(channels: List[dict]) -> None:
        for ch in channels:
            cid = ch["channel_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_channels.append(ch)

    yt_cfg = instruction.youtube
    max_channels = yt_cfg.max_channels

    # Step 1 -- priority channels
    print("=" * 60)
    print("PHASE 1-A: Resolving priority channels")
    print("=" * 60)
    priority = _resolve_priority_channels(
        youtube, yt_cfg.priority_channels, quota,
    )
    _add_unique(priority)
    print(f"\nPriority channels resolved: {len(all_channels)}")

    # Step 2 -- search-based expansion
    print("\n" + "=" * 60)
    print("PHASE 1-B: Searching for additional channels")
    print("=" * 60)
    for query in yt_cfg.search_queries:
        if len(all_channels) >= max_channels:
            print(f"  Reached target of {max_channels} channels, stopping search.")
            break
        if not quota.check("search.list"):
            print("  [quota] Approaching limit -- stopping search expansion.")
            break
        remaining_slots = max_channels - len(all_channels)
        results = _search_channels(youtube, query, remaining_slots, quota)
        _add_unique(results)
        print(f"  Total unique channels so far: {len(all_channels)}")

    print(f"\nPhase 1 complete: {len(all_channels)} unique channels discovered.")
    print(quota.summary())
    return all_channels


# =========================================================================
# Phase 2 -- Video Selection
# =========================================================================

def _get_uploads_playlist_id(
    youtube: Resource,
    channel_id: str,
    quota: _QuotaTracker,
) -> str:
    """Get the uploads playlist ID for a channel."""
    if not quota.check("channels.list"):
        return ""

    request = youtube.channels().list(
        part="contentDetails",
        id=channel_id,
    )
    response = _api_call_with_retry(
        request, quota, "channels.list",
        f"uploads playlist ({channel_id})",
    )
    if not response or not response.get("items"):
        return ""
    return (
        response["items"][0]
        .get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )


def _list_channel_videos(
    youtube: Resource,
    playlist_id: str,
    max_results: int,
    quota: _QuotaTracker,
) -> List[dict]:
    """List videos from an uploads playlist, paginating as needed."""
    videos: List[dict] = []
    next_page: Optional[str] = None
    per_page = min(max_results, 50)

    while len(videos) < max_results:
        if not quota.check("playlistItems.list"):
            print("  [quota] Approaching limit -- stopping video listing.")
            break

        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=per_page,
            pageToken=next_page,
        )
        response = _api_call_with_retry(
            request, quota, "playlistItems.list",
            f"list videos ({playlist_id})",
        )
        if not response or not response.get("items"):
            break

        for item in response["items"]:
            video_id = item.get("contentDetails", {}).get("videoId", "")
            if video_id:
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


def _get_video_statistics(
    youtube: Resource,
    video_ids: List[str],
    quota: _QuotaTracker,
) -> Dict[str, dict]:
    """Batch-fetch statistics for video IDs (up to 50 per API call)."""
    stats: Dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        if not quota.check("videos.list"):
            print("  [quota] Approaching limit -- stopping statistics fetch.")
            break

        batch = video_ids[i: i + 50]
        request = youtube.videos().list(
            part="statistics",
            id=",".join(batch),
        )
        response = _api_call_with_retry(
            request, quota, "videos.list",
            "video statistics batch",
        )
        if not response or not response.get("items"):
            continue

        for item in response["items"]:
            vid = item["id"]
            s = item.get("statistics", {})
            comments_disabled = "commentCount" not in s
            stats[vid] = {
                "viewCount": int(s.get("viewCount", 0)),
                "commentCount": int(s.get("commentCount", 0)),
                "commentsDisabled": comments_disabled,
            }

    return stats


def _score_video(video_info: dict, priority_keywords: List[str]) -> float:
    """Score a video for relevance using the instruction's priority keywords.

    Components:
    - Keyword matches: each keyword found in the title adds 10 points.
    - Comment volume: log10(commentCount + 1) * 5.
    - Low-comment penalty: -1000 if below _MIN_VIDEO_COMMENTS.
    - Comments disabled: -9999.
    """
    title = video_info.get("title", "").lower()
    comment_count = video_info.get("commentCount", 0)
    comments_disabled = video_info.get("commentsDisabled", False)

    if comments_disabled:
        return -9999.0

    keyword_score = sum(
        10 for kw in priority_keywords if kw.lower() in title
    )
    comment_score = math.log10(comment_count + 1) * 5
    penalty = -1000 if comment_count < _MIN_VIDEO_COMMENTS else 0

    return keyword_score + comment_score + penalty


def _tag_topics(title: str, priority_keywords: List[str]) -> List[str]:
    """Auto-tag a video with topic labels based on keyword matches."""
    lower = title.lower()
    return sorted({kw for kw in priority_keywords if kw.lower() in lower})


def _select_videos_for_channel(
    youtube: Resource,
    channel: dict,
    instruction: Instruction,
    quota: _QuotaTracker,
) -> List[dict]:
    """Select the most relevant videos from a single channel.

    Returns a list of video-info dicts, each enriched with statistics,
    scores, and topic tags.
    """
    yt_cfg = instruction.youtube
    max_videos = yt_cfg.max_videos_per_channel
    priority_keywords = yt_cfg.video_priority_keywords
    channel_name = channel["name"]
    channel_id = channel["channel_id"]

    print(f"  [videos] {channel_name}: fetching uploads ...")
    playlist_id = _get_uploads_playlist_id(youtube, channel_id, quota)
    if not playlist_id:
        print(f"  [videos] {channel_name}: no uploads playlist found, skipping.")
        return []

    # Retrieve a generous pool so we have enough to score and filter.
    pool_size = max(max_videos * 4, 50)
    raw_videos = _list_channel_videos(
        youtube, playlist_id, max_results=pool_size, quota=quota,
    )
    if not raw_videos:
        print(f"  [videos] {channel_name}: no videos found.")
        return []
    print(f"  [videos] {channel_name}: {len(raw_videos)} candidates fetched.")

    # Batch-fetch statistics.
    ids = [v["videoId"] for v in raw_videos]
    stats = _get_video_statistics(youtube, ids, quota)

    # Merge statistics and score.
    scored: List[Tuple[float, dict]] = []
    for v in raw_videos:
        vid = v["videoId"]
        s = stats.get(vid, {})
        v["viewCount"] = s.get("viewCount", 0)
        v["commentCount"] = s.get("commentCount", 0)
        v["commentsDisabled"] = s.get("commentsDisabled", True)
        sc = _score_video(v, priority_keywords)
        scored.append((sc, v))

    # Sort descending by score and take the top N.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [v for _sc, v in scored[:max_videos] if _sc > -9999]

    # Enrich each selected video with additional metadata.
    for v in selected:
        v["channelName"] = channel_name
        v["topicTags"] = _tag_topics(v.get("title", ""), priority_keywords)

    if scored:
        print(
            f"  [videos] {channel_name}: selected {len(selected)} video(s) "
            f"(top score {scored[0][0]:.1f})."
        )
    else:
        print(f"  [videos] {channel_name}: no scorable videos.")

    return selected


def _select_all_videos(
    youtube: Resource,
    channels: List[dict],
    instruction: Instruction,
    quota: _QuotaTracker,
) -> List[dict]:
    """Phase 2: select videos across all channels."""
    print("=" * 60)
    print("PHASE 2: Video Selection")
    print("=" * 60)

    all_videos: List[dict] = []
    for idx, channel in enumerate(channels, 1):
        print(f"\n[{idx}/{len(channels)}] Processing {channel['name']} ...")
        if not quota.check("channels.list"):
            print("  [quota] Approaching limit -- stopping video selection.")
            break
        videos = _select_videos_for_channel(youtube, channel, instruction, quota)
        channel["videos_sampled"] = len(videos)
        all_videos.extend(videos)

    print(
        f"\nPhase 2 complete: {len(all_videos)} videos selected "
        f"across {len(channels)} channels."
    )
    print(quota.summary())
    return all_videos


# =========================================================================
# Phase 3 -- Comment Extraction
# =========================================================================

def _is_comments_disabled_error(error: HttpError) -> bool:
    return error.resp.status == 403 and b"commentsDisabled" in (error.content or b"")


def _fetch_all_replies(
    youtube: Resource,
    parent_id: str,
    video_id: str,
    channel_name: str,
    quota: _QuotaTracker,
) -> List[dict]:
    """Fetch all replies for a thread via ``comments.list`` (for >5 replies)."""
    replies: List[dict] = []
    page_token: Optional[str] = None

    while True:
        if not quota.check("comments.list"):
            logger.warning("Quota limit reached while fetching replies -- stopping.")
            break

        request = youtube.comments().list(
            part="snippet",
            parentId=parent_id,
            maxResults=100,
            pageToken=page_token,
        )
        response = _api_call_with_retry(
            request, quota, "comments.list",
            f"replies for {parent_id}",
        )
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


def _parse_inline_replies(
    thread: dict,
    video_id: str,
    channel_name: str,
    parent_id: str,
) -> List[dict]:
    """Parse the (up to 5) replies embedded in a commentThread resource."""
    replies: List[dict] = []
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


def _extract_comments_for_video(
    youtube: Resource,
    video: dict,
    max_comments: int,
    quota: _QuotaTracker,
) -> List[dict]:
    """Extract comments (top-level + replies) for a single video.

    Handles pagination, threaded replies, comments-disabled errors, and
    quota limits.
    """
    video_id = video["videoId"]
    video_title = video.get("title", "")
    channel_name = video.get("channelName", "")
    comments: List[dict] = []
    page_token: Optional[str] = None

    logger.info(
        "Extracting comments for video '%s' (%s)", video_title, video_id,
    )
    print(f"    [comments] '{video_title}' ({video_id}): extracting ...")

    while len(comments) < max_comments:
        if not quota.check("commentThreads.list"):
            logger.warning(
                "Quota limit reached -- stopping extraction for '%s'.", video_title,
            )
            break

        try:
            request = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=100,
                pageToken=page_token,
            )
            response = _api_call_with_retry(
                request, quota, "commentThreads.list",
                f"commentThreads for {video_id}",
            )
        except HttpError as exc:
            if _is_comments_disabled_error(exc):
                logger.warning(
                    "Comments are disabled for video '%s' (%s) -- skipping.",
                    video_title,
                    video_id,
                )
                print(f"    [comments] '{video_title}': comments disabled, skipping.")
                return []
            raise

        if not response:
            break

        for thread in response.get("items", []):
            if len(comments) >= max_comments:
                break

            # -- Top-level comment ----------------------------------------
            top_resource = thread["snippet"]["topLevelComment"]
            top_id = top_resource["id"]
            top_snippet = top_resource["snippet"]
            text = (
                top_snippet.get("textOriginal")
                or top_snippet.get("textDisplay", "")
            )

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

            # -- Replies --------------------------------------------------
            total_reply_count = thread["snippet"].get("totalReplyCount", 0)
            if total_reply_count == 0:
                continue

            if total_reply_count > 5:
                try:
                    reply_dicts = _fetch_all_replies(
                        youtube, top_id, video_id, channel_name, quota,
                    )
                except HttpError:
                    logger.warning(
                        "Failed to fetch full replies for comment %s -- "
                        "falling back to inline replies.",
                        top_id,
                    )
                    reply_dicts = _parse_inline_replies(
                        thread, video_id, channel_name, top_id,
                    )
            else:
                reply_dicts = _parse_inline_replies(
                    thread, video_id, channel_name, top_id,
                )

            remaining = max_comments - len(comments)
            comments.extend(reply_dicts[:remaining])

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    print(f"    [comments] '{video_title}': {len(comments)} extracted.")
    logger.info(
        "Extracted %d comments for video '%s' (%s).",
        len(comments),
        video_title,
        video_id,
    )
    return comments


def _extract_all_comments(
    youtube: Resource,
    videos: List[dict],
    instruction: Instruction,
    quota: _QuotaTracker,
) -> List[dict]:
    """Phase 3: extract comments for all selected videos."""
    print("=" * 60)
    print("PHASE 3: Comment Extraction")
    print("=" * 60)

    all_comments: List[dict] = []
    max_comments = instruction.youtube.max_comments_per_video
    total = len(videos)

    for idx, video in enumerate(videos, start=1):
        print(f"\n  [{idx}/{total}] {video.get('title', 'untitled')}")

        if quota.exceeded:
            print("  [quota] Quota exhausted -- stopping comment extraction.")
            break

        try:
            video_comments = _extract_comments_for_video(
                youtube, video, max_comments, quota,
            )
            all_comments.extend(video_comments)
        except RuntimeError:
            # Quota exceeded -- stop gracefully.
            logger.error("Quota exceeded during comment extraction -- stopping.")
            print("  [quota] Quota exceeded -- stopping comment extraction.")
            break
        except Exception:
            logger.exception(
                "Unexpected error extracting comments for video '%s' (%s) -- skipping.",
                video.get("title", ""),
                video.get("videoId", ""),
            )

    print(
        f"\nPhase 3 complete: {len(all_comments)} comments extracted "
        f"from {total} videos."
    )
    print(quota.summary())
    return all_comments


# =========================================================================
# Filtering helpers
# =========================================================================

def _is_spam(text: str) -> bool:
    """Detect bot/spam comments using known promotional patterns."""
    for pattern in _SPAM_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _is_noise(text: str, channel_name: str, author: str) -> bool:
    """Return True if the comment should be filtered out."""
    stripped = text.strip()
    if not stripped:
        return True
    # Creator comment
    if author.strip().lower() == channel_name.strip().lower():
        return True
    # Emoji / timestamp / "first!" only
    if _EMOJI_ONLY_RE.match(stripped):
        return True
    if _TIMESTAMP_ONLY_RE.match(stripped):
        return True
    if _FIRST_SPAM_RE.match(stripped):
        return True
    # Too short
    if len(stripped.split()) < MIN_COMMENT_WORDS:
        return True
    # Spam
    if _is_spam(stripped):
        return True
    return False


# =========================================================================
# Conversion to SocialPost
# =========================================================================

def _comment_to_social_post(
    comment: dict,
    video: dict,
) -> SocialPost:
    """Convert a raw YouTube comment dict into a unified SocialPost."""
    video_id = comment["video_id"]
    return SocialPost(
        post_id=comment["comment_id"],
        platform="youtube",
        source_id=video_id,
        source_title=video.get("title", ""),
        author=comment["author"],
        text=comment["text"],
        like_count=comment.get("like_count", 0),
        is_reply=comment.get("is_reply", False),
        parent_id=comment.get("parent_id"),
        timestamp=comment.get("timestamp", ""),
        url=f"https://youtube.com/watch?v={video_id}",
        word_count=len(comment["text"].split()),
        metadata={
            "channel": comment.get("channel_name", ""),
            "view_count": video.get("viewCount", 0),
        },
    )


def _convert_comments_to_posts(
    comments: List[dict],
    videos: List[dict],
) -> List[SocialPost]:
    """Convert raw comment dicts to SocialPost objects, filtering noise.

    Builds a video lookup by videoId so each comment can reference its
    parent video metadata.
    """
    video_lookup: Dict[str, dict] = {v["videoId"]: v for v in videos}
    posts: List[SocialPost] = []

    for comment in comments:
        channel_name = comment.get("channel_name", "")
        author = comment.get("author", "")
        text = comment.get("text", "")

        if _is_noise(text, channel_name, author):
            continue

        video = video_lookup.get(comment["video_id"], {})
        posts.append(_comment_to_social_post(comment, video))

    return posts


# =========================================================================
# Main entry point
# =========================================================================

def run_youtube(instruction: Instruction) -> dict:
    """Main entry point for the YouTube platform agent.

    Orchestrates the full pipeline:
      1. Build API client
      2. Discover channels (priority + search)
      3. Select top videos per channel
      4. Extract comments (with pagination, threaded replies)
      5. Filter noise and convert to SocialPost

    Parameters
    ----------
    instruction : Instruction
        The parsed multi-platform instruction containing YouTube-specific
        configuration under ``instruction.youtube``.

    Returns
    -------
    dict
        - ``posts``    : List[SocialPost] -- all comments converted to SocialPost
        - ``channels`` : List[dict]       -- channel metadata
        - ``videos``   : List[dict]       -- video metadata
        - ``stats``    : dict             -- extraction statistics
    """
    yt_cfg = instruction.youtube
    if not yt_cfg.enabled:
        logger.info("YouTube platform is disabled in instruction -- skipping.")
        return {"posts": [], "channels": [], "videos": [], "stats": {}}

    # -- 1. Build API client -----------------------------------------------
    api_key = os.environ.get(yt_cfg.api_key_env, "")
    youtube = _build_youtube_client(api_key)
    quota = _QuotaTracker()

    print("\n" + "#" * 60)
    print("# YOUTUBE AGENT")
    print("#" * 60)

    # -- 2. Discover channels ----------------------------------------------
    try:
        channels = _discover_channels(youtube, instruction, quota)
    except RuntimeError as exc:
        logger.error("Channel discovery aborted: %s", exc)
        print(f"\n[error] Channel discovery aborted: {exc}")
        channels = []

    # -- 3. Select videos --------------------------------------------------
    try:
        videos = _select_all_videos(youtube, channels, instruction, quota)
    except RuntimeError as exc:
        logger.error("Video selection aborted: %s", exc)
        print(f"\n[error] Video selection aborted: {exc}")
        videos = []

    # -- 4. Extract comments -----------------------------------------------
    try:
        raw_comments = _extract_all_comments(youtube, videos, instruction, quota)
    except RuntimeError as exc:
        logger.error("Comment extraction aborted: %s", exc)
        print(f"\n[error] Comment extraction aborted: {exc}")
        raw_comments = []

    # -- 5. Filter and convert to SocialPost --------------------------------
    print("\n" + "=" * 60)
    print("PHASE 4: Converting to SocialPost format")
    print("=" * 60)

    posts = _convert_comments_to_posts(raw_comments, videos)

    # -- Stats --------------------------------------------------------------
    reply_posts = [p for p in posts if p.is_reply]
    unique_authors = len({p.author for p in posts})

    stats = {
        "channels_discovered": len(channels),
        "videos_selected": len(videos),
        "raw_comments_extracted": len(raw_comments),
        "posts_after_filtering": len(posts),
        "reply_posts": len(reply_posts),
        "unique_authors": unique_authors,
        "quota_used": quota.used,
        "quota_remaining": quota.remaining,
    }

    print(f"\nPosts after noise filtering: {len(posts)}")
    print(f"  - Replies: {len(reply_posts)}")
    print(f"  - Unique authors: {unique_authors}")
    print(f"  - Discarded (noise): {len(raw_comments) - len(posts)}")
    print(quota.summary())
    print("#" * 60)
    print("# YOUTUBE AGENT COMPLETE")
    print("#" * 60 + "\n")

    return {
        "posts": posts,
        "channels": channels,
        "videos": videos,
        "stats": stats,
    }
