"""
Configuration loader for Multi-Platform Social Media Market Needs Analysis.
All domain-specific settings come from the instruction YAML file.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Platform-specific config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class YouTubeConfig:
    enabled: bool = False
    api_key_env: str = "YOUTUBE_API_KEY"
    search_queries: List[str] = field(default_factory=list)
    priority_channels: List[dict] = field(default_factory=list)
    video_priority_keywords: List[str] = field(default_factory=list)
    max_channels: int = 25
    max_videos_per_channel: int = 10
    max_comments_per_video: int = 200
    transcript_enabled: bool = False
    whisper_model: str = "medium"
    transcript_max_videos: int = 50
    term_corrections: Dict[str, str] = field(default_factory=dict)


@dataclass
class RedditConfig:
    enabled: bool = False
    subreddits: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    sort: str = "relevance"
    time_filter: str = "year"
    max_posts_per_query: int = 100
    max_comments_per_post: int = 200


@dataclass
class TwitterConfig:
    enabled: bool = False
    api_key_env: str = "TWITTER_BEARER_TOKEN"
    search_queries: List[str] = field(default_factory=list)
    search_operators: str = "-is:retweet lang:en"
    max_results_per_query: int = 100
    max_total_tweets: int = 1000


@dataclass
class LinkedInConfig:
    enabled: bool = False
    api_key_env: str = "LINKEDIN_ACCESS_TOKEN"
    search_queries: List[str] = field(default_factory=list)
    max_posts: int = 100


# ---------------------------------------------------------------------------
# Unified instruction
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    """Parsed multi-platform instruction file."""
    # Project
    project_name: str = ""
    project_description: str = ""
    # Shared analysis (applies across all platforms)
    relevance_keywords: List[str] = field(default_factory=list)
    categories: Dict[str, dict] = field(default_factory=dict)
    wish_patterns: List[str] = field(default_factory=list)
    # Platform configs
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    # Validation
    validation_enabled: bool = False
    validation_references: List[dict] = field(default_factory=list)

    @property
    def enabled_platforms(self) -> List[str]:
        platforms = []
        if self.youtube.enabled:
            platforms.append("youtube")
        if self.reddit.enabled:
            platforms.append("reddit")
        if self.twitter.enabled:
            platforms.append("twitter")
        if self.linkedin.enabled:
            platforms.append("linkedin")
        return platforms


def load_instruction(yaml_path: str) -> Instruction:
    """Load and validate a multi-platform instruction YAML file."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    errors = []

    # --- Required fields ---
    project = raw.get("project", {})
    if not project.get("name"):
        errors.append("project.name is required")

    analysis = raw.get("analysis", {})
    if not analysis.get("relevance_keywords"):
        errors.append("analysis.relevance_keywords is required (at least 1)")
    categories = analysis.get("categories", {})
    if not categories:
        errors.append("analysis.categories is required (at least 1)")
    for code, cat in categories.items():
        for req in ("name", "description", "keywords"):
            if not cat.get(req):
                errors.append(f"analysis.categories.{code}.{req} is required")

    platforms = raw.get("platforms", {})
    any_enabled = any(
        platforms.get(p, {}).get("enabled", False)
        for p in ("youtube", "reddit", "twitter", "linkedin")
    )
    if not any_enabled:
        errors.append("At least one platform must be enabled")

    if errors:
        raise ValueError(
            "Instruction validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    # --- Build instruction ---
    instr = Instruction()
    instr.project_name = project.get("name", "")
    instr.project_description = project.get("description", "")
    instr.relevance_keywords = analysis.get("relevance_keywords", [])
    instr.categories = categories
    instr.wish_patterns = analysis.get("wish_patterns", [
        r"\bwish\b", r"\bhope\b", r"\bwant\b", r"\bneed\b",
        r"\bif only\b", r"\bwould be nice\b", r"\bshould be\b", r"\bimprove\b",
    ])

    # YouTube
    yt = platforms.get("youtube", {})
    if yt.get("enabled"):
        quota = yt.get("quota", {})
        tx = yt.get("transcript", {})
        instr.youtube = YouTubeConfig(
            enabled=True,
            api_key_env=yt.get("api_key_env", "YOUTUBE_API_KEY"),
            search_queries=yt.get("search_queries", []),
            priority_channels=yt.get("priority_channels", []),
            video_priority_keywords=yt.get("video_priority_keywords", []),
            max_channels=quota.get("max_channels", 25),
            max_videos_per_channel=quota.get("max_videos_per_channel", 10),
            max_comments_per_video=quota.get("max_comments_per_video", 200),
            transcript_enabled=tx.get("enabled", False),
            whisper_model=tx.get("whisper_model", "medium"),
            transcript_max_videos=tx.get("max_videos", 50),
            term_corrections=tx.get("term_corrections", {}),
        )

    # Reddit
    rd = platforms.get("reddit", {})
    if rd.get("enabled"):
        quota = rd.get("quota", {})
        instr.reddit = RedditConfig(
            enabled=True,
            subreddits=rd.get("subreddits", []),
            search_queries=rd.get("search_queries", []),
            sort=rd.get("sort", "relevance"),
            time_filter=rd.get("time_filter", "year"),
            max_posts_per_query=quota.get("max_posts_per_query", 100),
            max_comments_per_post=quota.get("max_comments_per_post", 200),
        )

    # Twitter
    tw = platforms.get("twitter", {})
    if tw.get("enabled"):
        quota = tw.get("quota", {})
        instr.twitter = TwitterConfig(
            enabled=True,
            api_key_env=tw.get("api_key_env", "TWITTER_BEARER_TOKEN"),
            search_queries=tw.get("search_queries", []),
            search_operators=tw.get("search_operators", "-is:retweet lang:en"),
            max_results_per_query=quota.get("max_results_per_query", 100),
            max_total_tweets=quota.get("max_total_tweets", 1000),
        )

    # LinkedIn
    li = platforms.get("linkedin", {})
    if li.get("enabled"):
        quota = li.get("quota", {})
        instr.linkedin = LinkedInConfig(
            enabled=True,
            api_key_env=li.get("api_key_env", "LINKEDIN_ACCESS_TOKEN"),
            search_queries=li.get("search_queries", []),
            max_posts=quota.get("max_posts", 100),
        )

    # Validation
    val = raw.get("validation", {})
    instr.validation_enabled = val.get("enabled", False)
    instr.validation_references = val.get("references", [])

    return instr


# ---------------------------------------------------------------------------
# Shared post model for cross-platform analysis
# ---------------------------------------------------------------------------

@dataclass
class SocialPost:
    """Unified post/comment model across all platforms.
    Each platform adapter converts its native data into this format.
    """
    post_id: str
    platform: str               # youtube, reddit, twitter, linkedin
    source_id: str              # video_id, post_id, tweet_id, etc.
    source_title: str           # video title, post title, tweet text preview
    author: str
    text: str
    like_count: int = 0
    reply_count: int = 0
    is_reply: bool = False
    parent_id: Optional[str] = None
    timestamp: str = ""
    url: str = ""
    # Analysis fields
    is_relevant: bool = False
    categories: List[str] = field(default_factory=list)
    has_wish: bool = False
    word_count: int = 0
    # Platform-specific metadata (flexible dict)
    metadata: Dict = field(default_factory=dict)

    def to_csv_row(self) -> dict:
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "author": self.author,
            "text": self.text,
            "like_count": self.like_count,
            "is_reply": self.is_reply,
            "timestamp": self.timestamp,
            "url": self.url,
            "is_relevant": self.is_relevant,
            "categories": "|".join(self.categories),
            "has_wish": self.has_wish,
            "word_count": self.word_count,
        }

    @staticmethod
    def csv_header() -> list:
        return [
            "post_id", "platform", "source_id", "source_title", "author",
            "text", "like_count", "is_reply", "timestamp", "url",
            "is_relevant", "categories", "has_wish", "word_count",
        ]


# ---------------------------------------------------------------------------
# System constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = "output"
CHECKPOINT_DIR = "output/checkpoints"
MIN_COMMENT_WORDS = 15
