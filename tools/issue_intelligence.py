import hashlib
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set

from config import EvidenceItem, Instruction, IssueCluster, SocialPost


_ISSUE_MARKERS = (
    "problem", "issue", "broken", "breaks", "fail", "fails", "failing", "cannot",
    "can't", "unable", "delay", "outage", "offline", "error", "errors", "queue",
    "waiting", "stuck", "manual", "slow", "latency", "blocked", "blocker",
)
_URGENCY_MARKERS = (
    "urgent", "asap", "immediately", "right now", "today", "every day", "again",
    "still", "repeatedly", "constantly", "deadline", "blocked", "blocker",
)
_BUYER_INTENT_MARKERS = (
    "wish", "want", "need", "looking for", "feature request", "would pay",
    "would buy", "vendor", "switch", "replacement", "roadmap",
)
_CONSEQUENCE_PATTERNS = {
    "downtime": ("downtime", "offline", "outage", "service down", "cannot access", "blocked"),
    "lost_revenue": ("lost revenue", "lost sales", "refund", "refunds", "churn"),
    "manual_work": ("manual", "spreadsheet", "workaround", "copy paste", "hand edit"),
    "latency": ("slow", "latency", "delay", "waiting", "queue", "takes forever"),
    "compliance_risk": ("compliance", "audit", "legal risk", "regulatory"),
}
_CONSEQUENCE_WEIGHTS = {
    "downtime": 95.0,
    "lost_revenue": 92.0,
    "manual_work": 72.0,
    "latency": 64.0,
    "compliance_risk": 88.0,
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _normalize_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return normalized.strip("-")


def _normalize_domain(raw: str) -> str:
    value = (raw or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def _normalize_source_family(post: SocialPost) -> str:
    hinted = (post.metadata.get("source_family") or post.source_family or "").strip().lower()
    if hinted:
        return hinted

    platform = (post.platform or "").strip().lower()
    if platform in {"youtube", "reddit", "twitter", "linkedin"}:
        return "community"
    if platform == "rss":
        domain = _normalize_domain(post.metadata.get("domain") or post.metadata.get("source_domain") or post.url)
        if any(token in domain for token in ("docs.", "status.", "support.", "help.")):
            return "official"
        return "trade_press"
    if platform == "github_issues":
        return "github"
    return platform or "community"


def _infer_independence_key(post: SocialPost, family: str) -> str:
    platform = (post.platform or "").lower()

    if platform == "reddit":
        subreddit = _normalize_slug(str(post.metadata.get("subreddit", "")))
        source_id = post.source_id or post.post_id
        if subreddit:
            return f"reddit:{subreddit}:thread:{source_id}".lower()
        return f"reddit:thread:{source_id}".lower()

    if platform == "twitter":
        conversation_id = str(post.metadata.get("conversation_id") or post.source_id or "").strip()
        if conversation_id:
            return f"twitter:conversation:{conversation_id}".lower()
        return f"twitter:post:{post.post_id}".lower()

    if platform == "youtube":
        channel_name = _normalize_slug(
            str(post.metadata.get("channel") or post.metadata.get("channel_name") or post.metadata.get("channel_id") or "")
        )
        if channel_name:
            return f"youtube:channel:{channel_name}".lower()
        return f"youtube:video:{post.source_id or post.post_id}".lower()

    if platform == "linkedin":
        if post.source_id:
            return f"linkedin:post:{post.source_id}".lower()
        normalized_author = _normalize_slug(post.author)
        if normalized_author:
            return f"linkedin:author:{normalized_author}".lower()
        return f"linkedin:post:{post.post_id}".lower()

    if platform == "rss":
        domain = _normalize_domain(post.metadata.get("domain") or post.metadata.get("source_domain") or post.url)
        return f"rss:{domain or 'unknown'}".lower()

    if platform == "github_issues":
        repo = _normalize_slug(str(post.metadata.get("repo") or post.metadata.get("repository") or ""))
        if repo:
            return f"github:{repo}:issue:{post.source_id or post.post_id}".lower()
        return f"github:issue:{post.source_id or post.post_id}".lower()

    domain = _normalize_domain(post.metadata.get("domain") or post.metadata.get("source_domain") or post.url)
    if domain:
        return f"{family}:{domain}".lower()
    return f"{family}:{post.source_id or post.post_id or platform or 'unknown'}".lower()


def _has_coarse_community_key(post: SocialPost, value: str) -> bool:
    return value in {
        "community:reddit.com",
        "community:twitter.com",
        "community:youtube.com",
        "community:linkedin.com",
    }


def apply_source_policy(post: SocialPost, instruction: Instruction) -> None:
    family = _normalize_source_family(post)
    tiers = instruction.source_policy.source_tiers
    weights = instruction.source_policy.trust_weights

    post.source_family = family
    post.source_tier = int(post.metadata.get("source_tier", post.source_tier or tiers.get(family, 4)))
    post.evidence_class = str(post.metadata.get("evidence_class", post.evidence_class or "community_post"))
    post.publication_date = post.publication_date or str(post.metadata.get("publication_date", "")) or post.timestamp
    post.trust_weight = _safe_float(post.metadata.get("trust_weight", post.trust_weight or weights.get(family, 0.5)), 0.5)

    provided = str(post.metadata.get("independence_key", post.independence_key or "")).strip().lower()
    if not provided or _has_coarse_community_key(post, provided):
        provided = _infer_independence_key(post, family)
    post.independence_key = provided
    post.metadata["independence_key"] = post.independence_key


def _norm_text(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_problem_statement(post: SocialPost) -> str:
    sentences = re.split(r"[\n\r]+|(?<=[.!?])\s+", post.text or "")
    candidates = []
    for sentence in sentences:
        norm = _norm_text(sentence)
        if not norm:
            continue
        score = 0.0
        score += sum(12.0 for marker in _ISSUE_MARKERS if marker in norm)
        score += sum(6.0 for marker in _URGENCY_MARKERS if marker in norm)
        score += 5.0 if any(ch.isdigit() for ch in sentence) else 0.0
        score += 4.0 if any(marker in norm for marker in ("because", "after", "during", "when")) else 0.0
        score += min(len(norm.split()), 20) * 0.7
        candidates.append((score, sentence.strip()))
    if not candidates:
        return " ".join(_norm_text(post.text).split()[:16]).strip() or "unspecified issue"
    candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    return candidates[0][1][:180]


def _extract_business_consequence(text: str) -> str:
    norm = _norm_text(text)
    labels = [label for label, patterns in _CONSEQUENCE_PATTERNS.items() if any(pattern in norm for pattern in patterns)]
    return "|".join(labels)


def _specificity_score(post: SocialPost, problem_statement: str, business_consequence: str) -> float:
    norm = _norm_text(post.text)
    score = 22.0
    score += min(len(problem_statement.split()), 14) * 3.0
    score += 12.0 if any(ch.isdigit() for ch in post.text) else 0.0
    score += 10.0 if business_consequence else 0.0
    score += 8.0 if post.categories else 0.0
    score += 8.0 if post.segments else 0.0
    score += 8.0 if any(marker in norm for marker in ("because", "after", "during", "every time", "whenever")) else 0.0
    return _clamp(score)


def _extraction_quality(post: SocialPost) -> float:
    score = 25.0
    score += 20.0 if post.normalized_problem_statement else 0.0
    score += 15.0 if post.business_consequence else 0.0
    score += 10.0 if post.publication_date else 0.0
    score += 10.0 if len((post.text or "").split()) >= 12 else 0.0
    score += 10.0 if post.categories else 0.0
    score += 10.0 if post.segments else 0.0
    return _clamp(score)


def _freshness_score(publication_date: str, half_life_days: int) -> float:
    try:
        iso = (publication_date or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - dt).days, 0)
    except Exception:
        return 40.0
    return _clamp(100.0 * math.exp(-age_days / max(1, half_life_days)))


def _weighted_score(components: Dict[str, float], weights: Dict[str, float]) -> float:
    total_weight = sum(max(_safe_float(weight, 0.0), 0.0) for weight in weights.values()) or 1.0
    return _clamp(
        sum(_clamp(components.get(name, 0.0)) * max(_safe_float(weight, 0.0), 0.0) for name, weight in weights.items()) / total_weight
    )


def _severity_score(posts: List[SocialPost]) -> float:
    values = []
    for post in posts:
        value = 28.0
        for label in (post.business_consequence or "").split("|"):
            if label:
                value = max(value, _CONSEQUENCE_WEIGHTS.get(label, 55.0))
        norm = _norm_text(post.text)
        if any(marker in norm for marker in ("production", "customers", "blocked", "cannot", "unable")):
            value += 8.0
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _urgency_score(posts: List[SocialPost]) -> float:
    values = []
    for post in posts:
        norm = _norm_text(post.text)
        value = 18.0 + (10.0 if post.has_wish else 0.0)
        value += sum(8.0 for marker in _URGENCY_MARKERS if marker in norm)
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _independent_frequency_score(independent_units: int, evidence_count: int) -> float:
    return round(_clamp(18.0 + min(independent_units, 4) * 18.0 + min(evidence_count, 6) * 4.0), 2)


def _buyer_intent_score(posts: List[SocialPost]) -> float:
    values = []
    for post in posts:
        norm = _norm_text(post.text)
        value = 14.0 + (18.0 if post.has_wish else 0.0)
        value += sum(10.0 for marker in _BUYER_INTENT_MARKERS if marker in norm)
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _business_impact_score(posts: List[SocialPost]) -> float:
    values = []
    for post in posts:
        value = 24.0
        for label in (post.business_consequence or "").split("|"):
            if label:
                value = max(value, _CONSEQUENCE_WEIGHTS.get(label, 55.0))
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _strategic_fit_score(posts: List[SocialPost], instruction: Instruction) -> float:
    score = _safe_float(instruction.scoring.default_strategic_fit, 60.0)
    matched_signal = False
    for post in posts:
        norm = _norm_text(post.text)
        if post.has_wish:
            matched_signal = True
        for code in post.categories:
            category = instruction.categories.get(code, {})
            for phrase in category.get("example_phrases", []) or []:
                phrase_norm = _norm_text(str(phrase))
                if phrase_norm and phrase_norm in norm:
                    matched_signal = True
            for signal in category.get("opportunity_signals", []) or []:
                signal_norm = _norm_text(str(signal))
                if signal_norm and signal_norm in norm:
                    matched_signal = True
    if matched_signal:
        score += 12.0
    return _clamp(score)


def _source_quality_score(posts: List[SocialPost]) -> float:
    values = []
    for post in posts:
        base = _clamp(post.trust_weight * 100.0)
        if post.source_tier <= 2:
            base += 5.0
        values.append(_clamp(base))
    return round(sum(values) / max(1, len(values)), 2)


def _corroboration_score(independent_units: int) -> float:
    if independent_units <= 1:
        return 20.0
    if independent_units == 2:
        return 60.0
    if independent_units == 3:
        return 80.0
    return 95.0


def _source_diversity_score(source_family_count: int) -> float:
    if source_family_count <= 1:
        return 25.0
    if source_family_count == 2:
        return 65.0
    if source_family_count == 3:
        return 85.0
    return 95.0


def _annotate_post(post: SocialPost, instruction: Instruction) -> None:
    apply_source_policy(post, instruction)
    post.normalized_problem_statement = _extract_problem_statement(post)
    post.business_consequence = _extract_business_consequence(post.text)
    post.specificity_score = round(_specificity_score(post, post.normalized_problem_statement, post.business_consequence), 2)
    post.extraction_quality = round(_extraction_quality(post), 2)
    post.metadata["normalized_problem_statement"] = post.normalized_problem_statement
    post.metadata["business_consequence"] = post.business_consequence
    post.metadata["specificity_score"] = post.specificity_score
    post.metadata["extraction_quality"] = post.extraction_quality


def _cluster_key(post: SocialPost) -> str:
    category_part = "|".join(sorted(post.categories)) or "uncat"
    statement = _norm_text(post.normalized_problem_statement)[:180] or "unspecified issue"
    return f"{category_part}::{statement}"


def _canonical_issue_id(statement: str, categories: List[str]) -> str:
    payload = f"{'|'.join(sorted(categories))}::{_norm_text(statement)}".encode("utf-8")
    return f"ISSUE-{hashlib.sha1(payload).hexdigest()[:12].upper()}"


def _independence_keys_by_family(posts: List[SocialPost]) -> Dict[str, Set[str]]:
    family_keys: Dict[str, Set[str]] = defaultdict(set)
    for post in posts:
        family_keys[post.source_family or post.platform or "unknown"].add(post.independence_key or post.post_id)
    return family_keys


def _corroboration_units(posts: List[SocialPost], cap_by_family: bool) -> int:
    family_keys = _independence_keys_by_family(posts)
    if cap_by_family:
        return sum(1 for keys in family_keys.values() if keys)
    return sum(len(keys) for keys in family_keys.values())


def build_issue_intelligence(posts: List[SocialPost], instruction: Instruction) -> Dict[str, List]:
    by_problem: Dict[str, List[SocialPost]] = defaultdict(list)
    evidences: List[EvidenceItem] = []

    for post in posts:
        _annotate_post(post, instruction)
        by_problem[_cluster_key(post)].append(post)

    scored_clusters: List[dict] = []
    for cluster_posts in by_problem.values():
        issue_statement = cluster_posts[0].normalized_problem_statement or "unspecified issue"
        categories = sorted({code for post in cluster_posts for code in post.categories})
        segments = sorted({code for post in cluster_posts for code in post.segments})
        independent_keys = {post.independence_key for post in cluster_posts if post.independence_key}
        family_counts = Counter(post.source_family or post.platform or "unknown" for post in cluster_posts)
        independent_source_count = len(independent_keys)
        corroboration_units = _corroboration_units(
            cluster_posts,
            instruction.source_policy.independence_by_source_family,
        )
        freshness_score = round(
            sum(_freshness_score(post.publication_date, instruction.source_policy.freshness_half_life_days) for post in cluster_posts) / max(1, len(cluster_posts)),
            2,
        )
        specificity_score = round(
            sum(post.specificity_score for post in cluster_posts) / max(1, len(cluster_posts)),
            2,
        )
        extraction_quality = round(
            sum(post.extraction_quality for post in cluster_posts) / max(1, len(cluster_posts)),
            2,
        )

        opportunity_components = {
            "severity": _severity_score(cluster_posts),
            "urgency": _urgency_score(cluster_posts),
            "independent_frequency": _independent_frequency_score(independent_source_count, len(cluster_posts)),
            "buyer_intent": _buyer_intent_score(cluster_posts),
            "business_impact": _business_impact_score(cluster_posts),
            "strategic_fit": _strategic_fit_score(cluster_posts, instruction),
        }
        confidence_components = {
            "source_quality": _source_quality_score(cluster_posts),
            "corroboration": _corroboration_score(corroboration_units),
            "source_diversity": _source_diversity_score(len(family_counts)),
            "recency": freshness_score,
            "specificity": specificity_score,
            "extraction_quality": extraction_quality,
        }

        weighted_opportunity_score = _weighted_score(opportunity_components, instruction.scoring.opportunity_weights)
        weighted_confidence_score = _weighted_score(confidence_components, instruction.scoring.confidence_weights)

        penalties: Dict[str, float] = {}
        if specificity_score < 45.0:
            penalties["vague_claim"] = _safe_float(instruction.scoring.penalties.get("vague_claim", 8.0), 8.0)
        if not any(post.publication_date for post in cluster_posts):
            penalties["missing_date"] = _safe_float(instruction.scoring.penalties.get("missing_date", 6.0), 6.0)
        if not any(post.business_consequence for post in cluster_posts):
            penalties["missing_business_consequence"] = _safe_float(
                instruction.scoring.penalties.get("missing_business_consequence", 10.0), 10.0
            )
        if instruction.segments and not segments:
            penalties["missing_segment"] = _safe_float(instruction.scoring.penalties.get("missing_segment", 8.0), 8.0)

        social_only = all(post.source_tier >= 4 for post in cluster_posts)
        if social_only and instruction.source_policy.require_tier4_corroboration and independent_source_count < 2:
            if not instruction.source_policy.allow_tier4_single_source_top_issues:
                penalties["social_only_top_issue"] = _safe_float(
                    instruction.scoring.penalties.get("social_only_top_issue", 30.0), 30.0
                )

        total_penalty = sum(penalties.values())
        opportunity_score = _clamp(weighted_opportunity_score - total_penalty * 0.25)
        confidence_score = _clamp(weighted_confidence_score - total_penalty * 0.75)
        priority_score = _clamp(opportunity_score * (0.4 + 0.6 * confidence_score / 100.0))

        scored_clusters.append(
            {
                "posts": cluster_posts,
                "statement": issue_statement,
                "categories": categories,
                "segments": segments,
                "independent_keys": independent_keys,
                "family_counts": family_counts,
                "independent_source_count": independent_source_count,
                "corroboration_units": corroboration_units,
                "freshness_score": freshness_score,
                "opportunity_score": round(opportunity_score, 2),
                "confidence_score": round(confidence_score, 2),
                "priority_score": round(priority_score, 2),
                "score_breakdown": {
                    "opportunity": {
                        "components": {key: round(value, 2) for key, value in opportunity_components.items()},
                        "weights": {key: round(_safe_float(weight, 0.0), 4) for key, weight in instruction.scoring.opportunity_weights.items()},
                        "weighted_score": round(weighted_opportunity_score, 2),
                        "score_after_penalties": round(opportunity_score, 2),
                    },
                    "confidence": {
                        "components": {key: round(value, 2) for key, value in confidence_components.items()},
                        "weights": {key: round(_safe_float(weight, 0.0), 4) for key, weight in instruction.scoring.confidence_weights.items()},
                        "weighted_score": round(weighted_confidence_score, 2),
                        "score_after_penalties": round(confidence_score, 2),
                    },
                    "penalties": {
                        "items": {key: round(value, 2) for key, value in penalties.items()},
                        "total": round(total_penalty, 2),
                    },
                    "priority": {
                        "score": round(priority_score, 2),
                        "confidence_multiplier": round(0.4 + 0.6 * confidence_score / 100.0, 4),
                    },
                    "corroboration": {
                        "independent_source_count": independent_source_count,
                        "source_family_count": len(family_counts),
                        "capped_units": corroboration_units,
                        "independence_by_source_family": instruction.source_policy.independence_by_source_family,
                    },
                },
            }
        )

    scored_clusters.sort(
        key=lambda item: (
            item["priority_score"],
            item["confidence_score"],
            len(item["independent_keys"]),
            len(item["posts"]),
        ),
        reverse=True,
    )

    clusters: List[IssueCluster] = []
    for cluster_data in scored_clusters:
        issue_id = _canonical_issue_id(
            cluster_data["statement"],
            cluster_data["categories"],
        )
        cluster = IssueCluster(
            canonical_issue_id=issue_id,
            normalized_problem_statement=cluster_data["statement"],
            category_codes=cluster_data["categories"],
            segment_codes=cluster_data["segments"],
            post_ids=[post.post_id for post in cluster_data["posts"]],
            evidence_count=len(cluster_data["posts"]),
            independent_source_count=cluster_data["independent_source_count"],
            source_family_count=len(cluster_data["family_counts"]),
            opportunity_score=cluster_data["opportunity_score"],
            confidence_score=cluster_data["confidence_score"],
            priority_score=cluster_data["priority_score"],
            final_rank_score=cluster_data["priority_score"],
            freshness_score=cluster_data["freshness_score"],
            source_mix=dict(cluster_data["family_counts"]),
            score_breakdown=cluster_data["score_breakdown"],
            provenance_snippets=[],
        )

        ranked_posts = sorted(
            cluster_data["posts"],
            key=lambda post: (
                post.trust_weight,
                post.extraction_quality,
                post.specificity_score,
                post.like_count,
                len(post.text or ""),
            ),
            reverse=True,
        )

        for post in ranked_posts:
            post.canonical_issue_id = issue_id
            post.issue_opportunity_score = cluster.opportunity_score
            post.issue_confidence_score = cluster.confidence_score
            post.issue_priority_score = cluster.priority_score
            post.final_rank_score = cluster.priority_score
            post.metadata["score_breakdown"] = cluster.score_breakdown
            post.metadata["source_mix"] = cluster.source_mix
            post.metadata["freshness_score"] = cluster.freshness_score
            post.metadata["independent_source_count"] = cluster.independent_source_count
            post.metadata["source_family_count"] = cluster.source_family_count

            evidence = EvidenceItem(
                evidence_id=f"EVID-{len(evidences) + 1:06d}",
                post_id=post.post_id,
                canonical_issue_id=issue_id,
                source_family=post.source_family,
                source_tier=post.source_tier,
                evidence_class=post.evidence_class,
                trust_weight=post.trust_weight,
                publication_date=post.publication_date,
                independence_key=post.independence_key,
                excerpt=(post.text or "")[:300],
                url=post.url,
                platform=post.platform,
                source_title=post.source_title,
                business_consequence=post.business_consequence,
                specificity_score=post.specificity_score,
                extraction_quality=post.extraction_quality,
            )
            evidences.append(evidence)
            cluster.evidence_ids.append(evidence.evidence_id)
            if len(cluster.provenance_snippets) < 4:
                cluster.provenance_snippets.append(f"{post.platform}:{post.source_family}: {(post.text or '').strip()[:120]}")

        clusters.append(cluster)

    return {"issues": clusters, "evidence": evidences}
