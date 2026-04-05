"""
Configuration loader for Multi-Platform Social Media Market Needs Analysis.
All domain-specific settings come from the instruction YAML file.
"""

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


@dataclass
class RssConfig:
    enabled: bool = False
    feeds: List[dict] = field(default_factory=list)
    max_items_per_feed: int = 50


@dataclass
class GitHubIssuesConfig:
    enabled: bool = False
    api_key_env: str = "GITHUB_TOKEN"
    repos: List[str] = field(default_factory=list)
    include_discussions: bool = True
    include_releases: bool = True
    max_items_per_repo: int = 50


@dataclass
class ReportingConfig:
    quote_count: int = 25
    max_cooccurrence_pairs: int = 15
    top_category_limit: int = 10


@dataclass
class ManualSourceConfig:
    name: str = ""
    kind: str = ""
    url: str = ""
    source_family: str = "official"
    source_tier: int = 1
    entity: str = ""
    entity_type: str = "company"
    tags: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    excerpt: str = ""
    claims: List[str] = field(default_factory=list)


@dataclass
class AlternativesConfig:
    tracked_entities: List[str] = field(default_factory=list)


@dataclass
class BenchmarkConfig:
    enabled: bool = False
    manual_sources: List[ManualSourceConfig] = field(default_factory=list)
    benchmark_feeds: List[dict] = field(default_factory=list)
    alternatives: AlternativesConfig = field(default_factory=AlternativesConfig)
    entity_aliases: Dict[str, List[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Unified instruction
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    """Parsed multi-platform instruction file."""
    # Project
    project_name: str = ""
    project_description: str = ""
    project_objectives: List[str] = field(default_factory=list)
    project_target_audiences: List[str] = field(default_factory=list)
    project_key_questions: List[str] = field(default_factory=list)
    project_decision_uses: List[str] = field(default_factory=list)
    # Shared analysis
    relevance_keywords: List[str] = field(default_factory=list)
    categories: Dict[str, dict] = field(default_factory=dict)
    segments: Dict[str, dict] = field(default_factory=dict)
    wish_patterns: List[str] = field(default_factory=list)
    include_irrelevant_in_stats: bool = False
    min_comment_words: int = 15
    language_allowlist: List[str] = field(default_factory=list)
    dedup_normalized_text: bool = True
    dedup_min_chars: int = 40
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    source_policy: "SourcePolicyConfig" = field(default_factory=lambda: SourcePolicyConfig())
    scoring: "ScoringConfig" = field(default_factory=lambda: ScoringConfig())
    visualization: "VisualizationConfig" = field(default_factory=lambda: VisualizationConfig())
    state_store: "StateStoreConfig" = field(default_factory=lambda: StateStoreConfig())
    history: "HistoryConfig" = field(default_factory=lambda: HistoryConfig())
    benchmarks: "BenchmarkConfig" = field(default_factory=lambda: BenchmarkConfig())
    # Platform configs
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    rss: RssConfig = field(default_factory=RssConfig)
    github_issues: GitHubIssuesConfig = field(default_factory=GitHubIssuesConfig)
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
        if self.rss.enabled:
            platforms.append("rss")
        if self.github_issues.enabled:
            platforms.append("github_issues")
        return platforms


@dataclass
class SourcePolicyConfig:
    source_tiers: Dict[str, int] = field(default_factory=lambda: {
        "official": 1,
        "github": 2,
        "trade_press": 3,
        "community": 4,
    })
    trust_weights: Dict[str, float] = field(default_factory=lambda: {
        "official": 1.0,
        "github": 0.85,
        "trade_press": 0.7,
        "community": 0.5,
    })
    require_tier4_corroboration: bool = True
    allow_tier4_single_source_top_issues: bool = False
    independence_by_source_family: bool = True
    freshness_half_life_days: int = 45


@dataclass
class ScoringConfig:
    opportunity_weights: Dict[str, float] = field(default_factory=lambda: {
        "severity": 0.25,
        "urgency": 0.15,
        "independent_frequency": 0.2,
        "buyer_intent": 0.1,
        "business_impact": 0.2,
        "strategic_fit": 0.1,
    })
    confidence_weights: Dict[str, float] = field(default_factory=lambda: {
        "source_quality": 0.25,
        "corroboration": 0.2,
        "source_diversity": 0.15,
        "recency": 0.1,
        "specificity": 0.15,
        "extraction_quality": 0.15,
    })
    penalties: Dict[str, float] = field(default_factory=lambda: {
        "vague_claim": 8.0,
        "missing_date": 6.0,
        "missing_business_consequence": 10.0,
        "missing_segment": 8.0,
        "social_only_top_issue": 30.0,
    })
    default_strategic_fit: float = 60.0


@dataclass
class VisualizationConfig:
    enabled: bool = True
    executive_dashboard: bool = True
    analyst_drilldown: bool = True
    include_time_trend: bool = True
    include_heatmap: bool = True


@dataclass
class StateStoreConfig:
    enabled: bool = False
    backend: str = "sqlite"
    path: str = "state/unheard_buzz.sqlite3"
    project_id: str = ""
    keep_raw_text: bool = True


@dataclass
class HistoryConfig:
    enabled: bool = False
    lookback_runs: int = 5
    emit_diff_report: bool = True


def load_instruction(yaml_path: str) -> Instruction:
    """Load and validate a multi-platform instruction YAML file."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    errors = []

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

    segments = analysis.get("segments", {})
    for code, segment in segments.items():
        for req in ("name", "description", "keywords"):
            if not segment.get(req):
                errors.append(f"analysis.segments.{code}.{req} is required")

    platforms = raw.get("platforms", {})
    any_enabled = any(
        platforms.get(p, {}).get("enabled", False)
        for p in ("youtube", "reddit", "twitter", "linkedin", "rss", "github_issues")
    )
    if not any_enabled:
        errors.append("At least one platform must be enabled")

    if errors:
        raise ValueError(
            "Instruction validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    instr = Instruction()
    instr.project_name = project.get("name", "")
    instr.project_description = project.get("description", "")
    instr.project_objectives = project.get("objectives", [])
    instr.project_target_audiences = project.get("target_audiences", [])
    instr.project_key_questions = project.get("key_questions", [])
    instr.project_decision_uses = project.get("decision_uses", [])
    instr.relevance_keywords = analysis.get("relevance_keywords", [])
    instr.categories = categories
    instr.segments = segments
    instr.wish_patterns = analysis.get("wish_patterns", [
        r"\bwish\b", r"\bhope\b", r"\bwant\b", r"\bneed\b",
        r"\bif only\b", r"\bwould be nice\b", r"\bshould be\b", r"\bimprove\b",
    ])
    instr.include_irrelevant_in_stats = bool(
        analysis.get("include_irrelevant_in_stats", False)
    )
    instr.min_comment_words = int(analysis.get("min_comment_words", 15))
    instr.language_allowlist = [str(x).lower() for x in analysis.get("language_allowlist", [])]
    instr.dedup_normalized_text = bool(analysis.get("dedup_normalized_text", True))
    instr.dedup_min_chars = int(analysis.get("dedup_min_chars", 40))
    reporting = raw.get("reporting", {})
    instr.reporting = ReportingConfig(
        quote_count=int(reporting.get("quote_count", 25)),
        max_cooccurrence_pairs=int(reporting.get("max_cooccurrence_pairs", 15)),
        top_category_limit=int(reporting.get("top_category_limit", 10)),
    )
    source_policy = raw.get("source_policy", {})
    instr.source_policy = SourcePolicyConfig(
        source_tiers=source_policy.get("source_tiers", SourcePolicyConfig().source_tiers),
        trust_weights=source_policy.get("trust_weights", SourcePolicyConfig().trust_weights),
        require_tier4_corroboration=bool(source_policy.get("require_tier4_corroboration", True)),
        allow_tier4_single_source_top_issues=bool(
            source_policy.get("allow_tier4_single_source_top_issues", False)
        ),
        independence_by_source_family=bool(source_policy.get("independence_by_source_family", True)),
        freshness_half_life_days=int(source_policy.get("freshness_half_life_days", 45)),
    )
    scoring = raw.get("scoring", {})
    instr.scoring = ScoringConfig(
        opportunity_weights=scoring.get("opportunity_weights", ScoringConfig().opportunity_weights),
        confidence_weights=scoring.get("confidence_weights", ScoringConfig().confidence_weights),
        penalties=scoring.get("penalties", ScoringConfig().penalties),
        default_strategic_fit=float(scoring.get("default_strategic_fit", 60.0)),
    )
    visualization = raw.get("visualization", {})
    instr.visualization = VisualizationConfig(
        enabled=bool(visualization.get("enabled", True)),
        executive_dashboard=bool(visualization.get("executive_dashboard", True)),
        analyst_drilldown=bool(visualization.get("analyst_drilldown", True)),
        include_time_trend=bool(visualization.get("include_time_trend", True)),
        include_heatmap=bool(visualization.get("include_heatmap", True)),
    )
    state_store = raw.get("state_store", {})
    instr.state_store = StateStoreConfig(
        enabled=bool(state_store.get("enabled", False)),
        backend=str(state_store.get("backend", "sqlite") or "sqlite").strip().lower(),
        path=str(state_store.get("path", "state/unheard_buzz.sqlite3") or "state/unheard_buzz.sqlite3"),
        project_id=str(state_store.get("project_id", "") or "").strip(),
        keep_raw_text=bool(state_store.get("keep_raw_text", True)),
    )
    history = raw.get("history", {})
    instr.history = HistoryConfig(
        enabled=bool(history.get("enabled", False)),
        lookback_runs=int(history.get("lookback_runs", 5)),
        emit_diff_report=bool(history.get("emit_diff_report", True)),
    )
    benchmarks = raw.get("benchmarks", {})
    alternatives = benchmarks.get("alternatives", {}) if isinstance(benchmarks, dict) else {}
    manual_sources = []
    for source in benchmarks.get("manual_sources", []) if isinstance(benchmarks, dict) else []:
        if not isinstance(source, dict):
            continue
        manual_sources.append(
            ManualSourceConfig(
                name=str(source.get("name", "") or ""),
                kind=str(source.get("kind", "") or ""),
                url=str(source.get("url", "") or ""),
                source_family=str(source.get("source_family", "official") or "official"),
                source_tier=int(source.get("source_tier", 1) or 1),
                entity=str(source.get("entity", "") or ""),
                entity_type=str(source.get("entity_type", "company") or "company"),
                tags=[str(tag) for tag in source.get("tags", []) if str(tag).strip()],
                aliases=[str(tag) for tag in source.get("aliases", []) if str(tag).strip()],
                excerpt=str(source.get("excerpt", "") or ""),
                claims=[str(tag) for tag in source.get("claims", []) if str(tag).strip()],
            )
        )
    entity_aliases = {}
    for key, values in (benchmarks.get("entity_aliases", {}) if isinstance(benchmarks, dict) else {}).items():
        if not isinstance(values, list):
            continue
        entity_aliases[str(key)] = [str(value) for value in values if str(value).strip()]
    instr.benchmarks = BenchmarkConfig(
        enabled=bool(benchmarks.get("enabled", False)) if isinstance(benchmarks, dict) else False,
        manual_sources=manual_sources,
        benchmark_feeds=benchmarks.get("benchmark_feeds", []) if isinstance(benchmarks, dict) else [],
        alternatives=AlternativesConfig(
            tracked_entities=[str(item) for item in alternatives.get("tracked_entities", []) if str(item).strip()]
        ),
        entity_aliases=entity_aliases,
    )

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

    li = platforms.get("linkedin", {})
    if li.get("enabled"):
        quota = li.get("quota", {})
        instr.linkedin = LinkedInConfig(
            enabled=True,
            api_key_env=li.get("api_key_env", "LINKEDIN_ACCESS_TOKEN"),
            search_queries=li.get("search_queries", []),
            max_posts=quota.get("max_posts", 100),
        )
    rss_cfg = platforms.get("rss", {})
    if rss_cfg.get("enabled"):
        quota = rss_cfg.get("quota", {})
        instr.rss = RssConfig(
            enabled=True,
            feeds=rss_cfg.get("feeds", []),
            max_items_per_feed=int(quota.get("max_items_per_feed", 50)),
        )
    gh = platforms.get("github_issues", {})
    if gh.get("enabled"):
        quota = gh.get("quota", {})
        instr.github_issues = GitHubIssuesConfig(
            enabled=True,
            api_key_env=gh.get("api_key_env", "GITHUB_TOKEN"),
            repos=gh.get("repos", []),
            include_discussions=bool(gh.get("include_discussions", True)),
            include_releases=bool(gh.get("include_releases", True)),
            max_items_per_repo=int(quota.get("max_items_per_repo", 50)),
        )

    val = raw.get("validation", {})
    instr.validation_enabled = val.get("enabled", False)
    instr.validation_references = val.get("references", [])

    return instr


# ---------------------------------------------------------------------------
# Shared post model for cross-platform analysis
# ---------------------------------------------------------------------------

@dataclass
class SocialPost:
    """Unified post/comment model across all platforms."""
    post_id: str
    platform: str
    source_id: str
    source_title: str
    author: str
    text: str
    like_count: int = 0
    reply_count: int = 0
    is_reply: bool = False
    parent_id: Optional[str] = None
    timestamp: str = ""
    url: str = ""
    is_relevant: bool = False
    relevance_score: float = 0.0
    categories: List[str] = field(default_factory=list)
    category_scores: Dict[str, float] = field(default_factory=dict)
    segments: List[str] = field(default_factory=list)
    segment_scores: Dict[str, float] = field(default_factory=dict)
    final_rank_score: float = 0.0
    has_wish: bool = False
    word_count: int = 0
    analysis_complete: bool = False
    canonical_issue_id: str = ""
    issue_priority_score: float = 0.0
    issue_confidence_score: float = 0.0
    issue_opportunity_score: float = 0.0
    source_family: str = ""
    source_tier: int = 4
    evidence_class: str = "community_post"
    publication_date: str = ""
    trust_weight: float = 0.5
    independence_key: str = ""
    normalized_problem_statement: str = ""
    business_consequence: str = ""
    specificity_score: float = 0.0
    extraction_quality: float = 0.0
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
            "relevance_score": self.relevance_score,
            "categories": "|".join(self.categories),
            "category_scores": json_dumps_safe(self.category_scores),
            "segments": "|".join(self.segments),
            "segment_scores": json_dumps_safe(self.segment_scores),
            "final_rank_score": self.final_rank_score,
            "has_wish": self.has_wish,
            "word_count": self.word_count,
            "analysis_complete": self.analysis_complete,
            "canonical_issue_id": self.canonical_issue_id,
            "issue_priority_score": self.issue_priority_score,
            "issue_confidence_score": self.issue_confidence_score,
            "issue_opportunity_score": self.issue_opportunity_score,
            "source_family": self.source_family,
            "source_tier": self.source_tier,
            "evidence_class": self.evidence_class,
            "publication_date": self.publication_date,
            "trust_weight": self.trust_weight,
            "independence_key": self.independence_key,
        }

    @staticmethod
    def csv_header() -> list:
        return [
            "post_id", "platform", "source_id", "source_title", "author",
            "text", "like_count", "is_reply", "timestamp", "url",
            "is_relevant", "relevance_score", "categories", "category_scores",
            "segments", "segment_scores",
            "final_rank_score", "has_wish", "word_count", "analysis_complete",
            "canonical_issue_id", "issue_priority_score", "issue_confidence_score",
            "issue_opportunity_score", "source_family", "source_tier",
            "evidence_class", "publication_date", "trust_weight", "independence_key",
        ]


@dataclass
class EvidenceItem:
    evidence_id: str
    post_id: str
    canonical_issue_id: str
    source_family: str
    source_tier: int
    evidence_class: str
    trust_weight: float
    publication_date: str
    independence_key: str
    excerpt: str
    url: str = ""
    platform: str = ""
    source_title: str = ""
    business_consequence: str = ""
    specificity_score: float = 0.0
    extraction_quality: float = 0.0


@dataclass
class IssueCluster:
    canonical_issue_id: str
    normalized_problem_statement: str
    category_codes: List[str] = field(default_factory=list)
    segment_codes: List[str] = field(default_factory=list)
    post_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    evidence_count: int = 0
    independent_source_count: int = 0
    source_family_count: int = 0
    opportunity_score: float = 0.0
    confidence_score: float = 0.0
    priority_score: float = 0.0
    final_rank_score: float = 0.0
    freshness_score: float = 0.0
    source_mix: Dict[str, int] = field(default_factory=dict)
    score_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)
    provenance_snippets: List[str] = field(default_factory=list)


def json_dumps_safe(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


OUTPUT_DIR = "output"
CHECKPOINT_DIR = "output/checkpoints"
MIN_COMMENT_WORDS = 15
