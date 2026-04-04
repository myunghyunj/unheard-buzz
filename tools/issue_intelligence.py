from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Sequence, Tuple

from config import EvidenceItem, Instruction, IssueCluster, SocialPost


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "i", "in", "is", "it", "its", "my", "of", "on", "or", "our",
    "that", "the", "their", "this", "to", "we", "with", "you", "your", "when",
    "again", "still", "just", "very", "really", "more", "than", "then",
}

_ISSUE_MARKERS = (
    "broken", "issue", "problem", "fail", "fails", "failed", "failing", "cannot",
    "can't", "unable", "outage", "delay", "slow", "slowness", "error", "errors",
    "crash", "crashes", "bug", "offline", "queue", "waiting", "stuck", "manual",
    "latency", "downtime", "friction", "blocked", "blocker",
)

_URGENCY_MARKERS = (
    "urgent", "immediately", "asap", "now", "today", "right away", "blocked",
    "blocker", "every day", "constantly", "again", "repeatedly", "deadline",
)

_BUYER_INTENT_MARKERS = (
    "wish", "need", "want", "would pay", "would buy", "buy", "purchase", "vendor",
    "switch", "renew", "replacement", "roadmap", "feature request", "pricing",
)

_CONSEQUENCE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "downtime": ("downtime", "offline", "outage", "service down", "cannot access"),
    "lost_revenue": ("lost revenue", "revenue", "lost sales", "refund", "refunds"),
    "compliance_risk": ("compliance", "audit", "legal risk", "regulatory"),
    "manual_work": ("manual", "spreadsheet", "workaround", "copy paste", "hand edit"),
    "latency": ("slow", "latency", "delay", "waiting", "queue", "takes forever"),
    "churn_risk": ("churn", "cancel", "switch away", "left the product"),
    "implementation_failure": ("implementation failed", "deployment failed", "rollout failed", "migration failed"),
    "procurement_friction": ("procurement", "security review", "approval", "vendor review"),
    "error_rate": ("error", "errors", "crash", "crashes", "bug", "bugs"),
}

_BUYER_ROLE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "developer": ("developer", "dev", "engineer", "sdk", "api"),
    "operator": ("operator", "ops", "devops", "sre", "site reliability"),
    "manager": ("manager", "lead", "director", "vp", "head of"),
    "procurement": ("procurement", "buyer", "vendor management", "security review"),
    "admin": ("admin", "administrator", "workspace admin", "owner"),
    "customer_support": ("support", "customer success", "help desk"),
    "end_user": ("user", "customer", "client", "patient", "driver"),
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


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
    domain = _normalize_domain(post.metadata.get("domain") or post.metadata.get("source_domain") or post.url)

    if platform in {"youtube", "reddit", "twitter", "linkedin"}:
        return "community"
    if platform == "github_issues" or "github.com" in domain:
        return "github"
    if platform == "rss":
        if any(token in domain for token in ("docs.", "status.", "support.", "changelog", "release")):
            return "official"
        return "trade_press"
    if any(token in domain for token in ("docs.", "status.", "support.", "help.", "developers.")):
        return "official"
    return platform or "community"


def apply_source_policy(post: SocialPost, instruction: Instruction) -> None:
    family = _normalize_source_family(post)
    tiers = instruction.source_policy.source_tiers
    weights = instruction.source_policy.trust_weights

    post.source_family = family
    post.source_tier = int(post.metadata.get("source_tier", tiers.get(family, 4)))
    post.evidence_class = str(post.metadata.get("evidence_class", post.evidence_class or "community_post"))
    post.publication_date = post.publication_date or post.timestamp or str(post.metadata.get("publication_date", ""))
    post.trust_weight = _safe_float(post.metadata.get("trust_weight", weights.get(family, 0.5)), 0.5)

    root = _normalize_domain(post.metadata.get("domain") or post.metadata.get("source_domain") or post.url)
    if not root:
        root = family or post.platform or "community"
    post.independence_key = str(post.metadata.get("independence_key") or f"{family}:{root}").lower()


def _norm_text(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^\w\s\-]", " ", value, flags=re.UNICODE)
    value = re.sub(r"_", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _sentence_split(text: str) -> List[str]:
    chunks = re.split(r"[\n\r]+|(?<=[\.!?;:])\s+", text or "")
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _signature_tokens(text: str) -> List[str]:
    tokens = []
    for token in _norm_text(text).split():
        if len(token) < 3:
            continue
        if token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens[:18]


def _statement_similarity(left: str, right: str) -> float:
    left_tokens = set(_signature_tokens(left))
    right_tokens = set(_signature_tokens(right))
    jaccard = (len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))) if (left_tokens or right_tokens) else 0.0
    seq = SequenceMatcher(None, _norm_text(left), _norm_text(right)).ratio()
    return max(jaccard, seq)


def _extract_problem_statement(post: SocialPost) -> str:
    sentences = _sentence_split(post.text)
    if not sentences:
        return " ".join(_norm_text(post.text).split()[:14]).strip() or "unspecified issue"

    ranked: List[Tuple[float, str]] = []
    for sentence in sentences:
        norm = _norm_text(sentence)
        if not norm:
            continue
        score = 0.0
        score += sum(12.0 for marker in _ISSUE_MARKERS if marker in norm)
        score += sum(8.0 for marker in _URGENCY_MARKERS if marker in norm)
        score += 6.0 if any(char.isdigit() for char in sentence) else 0.0
        score += 6.0 if any(marker in norm for marker in ("because", "causes", "leads to", "means")) else 0.0
        score += min(len(norm.split()), 18) * 0.8
        ranked.append((score, sentence.strip()))

    ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    best = ranked[0][1]
    best = re.sub(r"^(i|we|our team)\s+(have|had|keep having)\s+", "", best, flags=re.IGNORECASE)
    best = re.sub(r"\s+", " ", best).strip(" -")
    return best[:180] or "unspecified issue"


def _extract_business_consequence(post: SocialPost) -> str:
    norm = _norm_text(post.text)
    labels = [label for label, patterns in _CONSEQUENCE_PATTERNS.items() if any(pattern in norm for pattern in patterns)]
    if labels:
        return "|".join(labels)
    if any(term in norm for term in ("blocked", "cannot", "can't", "unable", "stuck")):
        return "downtime"
    return ""


def _extract_buyer_role(post: SocialPost) -> str:
    norm = _norm_text(post.text)
    for role, patterns in _BUYER_ROLE_PATTERNS.items():
        if any(pattern in norm for pattern in patterns):
            return role
    return ""


def _extract_geography(post: SocialPost) -> str:
    for key in ("geography", "country", "region", "market", "locale"):
        value = post.metadata.get(key)
        if value:
            return str(value)
    return ""


def _specificity_score(post: SocialPost, statement: str, consequence: str, buyer_role: str) -> float:
    score = 20.0
    norm = _norm_text(post.text)
    tokens = _signature_tokens(statement)
    score += min(len(tokens), 12) * 3.0
    score += 12.0 if any(char.isdigit() for char in post.text) else 0.0
    score += 12.0 if consequence else 0.0
    score += 8.0 if buyer_role else 0.0
    score += 10.0 if post.segments else 0.0
    score += 10.0 if post.categories else 0.0
    score += 8.0 if any(term in norm for term in ("because", "after", "during", "whenever", "every time")) else 0.0
    return _clamp(score)


def _extraction_quality_score(post: SocialPost) -> float:
    score = 25.0
    score += 20.0 if getattr(post, "normalized_problem_statement", "") else 0.0
    score += 15.0 if getattr(post, "business_consequence", "") else 0.0
    score += 10.0 if getattr(post, "buyer_role", "") else 0.0
    score += 10.0 if post.segments else 0.0
    score += 10.0 if post.publication_date else 0.0
    score += 10.0 if len(post.text.split()) >= 12 else 0.0
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
    total_weight = sum(max(weight, 0.0) for weight in weights.values()) or 1.0
    return _clamp(sum(_clamp(components.get(name, 0.0)) * max(weight, 0.0) for name, weight in weights.items()) / total_weight)


def _severity_score(posts: Sequence[SocialPost]) -> float:
    severity = []
    consequence_weights = {
        "downtime": 95.0,
        "lost_revenue": 92.0,
        "compliance_risk": 90.0,
        "manual_work": 70.0,
        "latency": 60.0,
        "churn_risk": 85.0,
        "implementation_failure": 82.0,
        "procurement_friction": 65.0,
        "error_rate": 74.0,
    }
    for post in posts:
        value = 35.0
        norm = _norm_text(post.text)
        for label in str(getattr(post, "business_consequence", "")).split("|"):
            if label:
                value = max(value, consequence_weights.get(label, 55.0))
        if any(term in norm for term in ("blocked", "cannot", "can't", "unable", "production", "customers")):
            value += 12.0
        if post.like_count >= 10:
            value += 4.0
        severity.append(_clamp(value))
    return round(sum(severity) / max(1, len(severity)), 2)


def _urgency_score(posts: Sequence[SocialPost]) -> float:
    values = []
    for post in posts:
        norm = _norm_text(post.text)
        value = 20.0
        value += 18.0 if post.has_wish else 0.0
        value += sum(10.0 for marker in _URGENCY_MARKERS if marker in norm)
        value += 10.0 if any(term in norm for term in ("every day", "again", "still", "recurring")) else 0.0
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _buyer_intent_score(posts: Sequence[SocialPost]) -> float:
    values = []
    for post in posts:
        norm = _norm_text(post.text)
        value = 15.0
        value += 20.0 if post.has_wish else 0.0
        value += sum(10.0 for marker in _BUYER_INTENT_MARKERS if marker in norm)
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _business_impact_score(posts: Sequence[SocialPost]) -> float:
    values = []
    for post in posts:
        value = 25.0
        labels = str(getattr(post, "business_consequence", "")).split("|")
        if "downtime" in labels:
            value = max(value, 90.0)
        if "lost_revenue" in labels or "churn_risk" in labels:
            value = max(value, 88.0)
        if "manual_work" in labels:
            value = max(value, 72.0)
        if "latency" in labels or "error_rate" in labels:
            value = max(value, 68.0)
        values.append(_clamp(value))
    return round(sum(values) / max(1, len(values)), 2)


def _strategic_fit_score(posts: Sequence[SocialPost], instruction: Instruction) -> float:
    score = _safe_float(getattr(instruction.scoring, "default_strategic_fit", 60.0), 60.0)
    matched_signal = False
    for post in posts:
        norm = _norm_text(post.text)
        for category_code in post.categories:
            category = instruction.categories.get(category_code, {})
            for example in category.get("example_phrases", []) or []:
                if _norm_text(example) and _norm_text(example) in norm:
                    matched_signal = True
            if category.get("opportunity_signals"):
                matched_signal = matched_signal or post.has_wish
    if matched_signal:
        score += 12.0
    if any(post.has_wish for post in posts):
        score += 8.0
    return _clamp(score)


def _source_quality_score(posts: Sequence[SocialPost]) -> float:
    values = []
    for post in posts:
        base = _clamp(post.trust_weight * 100.0)
        if post.source_tier <= 1:
            base += 5.0
        values.append(_clamp(base))
    return round(sum(values) / max(1, len(values)), 2)


def _corroboration_score(independent_count: int) -> float:
    if independent_count <= 1:
        return 20.0
    if independent_count == 2:
        return 55.0
    if independent_count == 3:
        return 75.0
    return 90.0 + min(10.0, (independent_count - 4) * 2.5)


def _source_diversity_score(family_counts: Counter) -> float:
    families = len(family_counts)
    if families <= 1:
        return 25.0
    if families == 2:
        return 60.0
    if families == 3:
        return 80.0
    return 95.0


def _annotate_post(post: SocialPost, instruction: Instruction) -> None:
    apply_source_policy(post, instruction)
    statement = _extract_problem_statement(post)
    consequence = _extract_business_consequence(post)
    buyer_role = _extract_buyer_role(post)
    geography = _extract_geography(post)
    specificity = _specificity_score(post, statement, consequence, buyer_role)

    post.normalized_problem_statement = statement
    post.business_consequence = consequence
    post.buyer_role = buyer_role
    post.geography = geography
    post.specificity_score = round(specificity, 2)
    post.extraction_quality = round(_extraction_quality_score(post), 2)

    post.metadata["normalized_problem_statement"] = statement
    post.metadata["business_consequence"] = consequence
    post.metadata["buyer_role"] = buyer_role
    post.metadata["geography"] = geography
    post.metadata["specificity_score"] = post.specificity_score
    post.metadata["extraction_quality"] = post.extraction_quality


def _same_issue_bucket(group: dict, post: SocialPost) -> bool:
    group_categories = set(group["categories"])
    post_categories = set(post.categories)
    if group_categories and post_categories and not (group_categories & post_categories):
        return False
    similarity = _statement_similarity(group["statement"], post.normalized_problem_statement)
    left_tokens = set(_signature_tokens(group["statement"]))
    right_tokens = set(_signature_tokens(post.normalized_problem_statement))
    shared_tokens = len(left_tokens & right_tokens)
    if similarity >= 0.72:
        return True
    return shared_tokens >= 3 and similarity >= 0.48


def _cluster_posts(posts: Sequence[SocialPost]) -> List[dict]:
    groups: List[dict] = []
    for post in posts:
        placed = False
        for group in groups:
            if _same_issue_bucket(group, post):
                group["posts"].append(post)
                group["categories"].update(post.categories)
                group["segments"].update(post.segments)
                # keep the most specific representative statement
                current = group["statement"]
                if getattr(post, "specificity_score", 0.0) > group.get("statement_specificity", 0.0):
                    group["statement"] = post.normalized_problem_statement
                    group["statement_specificity"] = getattr(post, "specificity_score", 0.0)
                elif _statement_similarity(current, post.normalized_problem_statement) > 0.9 and len(post.normalized_problem_statement) < len(current):
                    group["statement"] = post.normalized_problem_statement
                placed = True
                break
        if not placed:
            groups.append(
                {
                    "statement": post.normalized_problem_statement,
                    "statement_specificity": getattr(post, "specificity_score", 0.0),
                    "categories": set(post.categories),
                    "segments": set(post.segments),
                    "posts": [post],
                }
            )
    return groups


def build_issue_intelligence(posts: List[SocialPost], instruction: Instruction) -> Dict[str, List]:
    if not posts:
        return {"issues": [], "evidence": []}

    for post in posts:
        _annotate_post(post, instruction)

    grouped = _cluster_posts(posts)
    scored_clusters: List[dict] = []
    for group in grouped:
        cluster_posts = group["posts"]
        families = Counter((post.source_family or post.platform or "unknown") for post in cluster_posts)
        independence_values = {
            (post.source_family or post.platform) if instruction.source_policy.independence_by_source_family else post.independence_key
            for post in cluster_posts
            if (post.source_family or post.independence_key or post.platform)
        }
        corroborating_count = len(independence_values)
        freshness = sum(_freshness_score(post.publication_date, instruction.source_policy.freshness_half_life_days) for post in cluster_posts) / max(1, len(cluster_posts))
        specificity = sum(getattr(post, "specificity_score", 0.0) for post in cluster_posts) / max(1, len(cluster_posts))
        extraction_quality = sum(getattr(post, "extraction_quality", 0.0) for post in cluster_posts) / max(1, len(cluster_posts))

        opportunity_components = {
            "severity": _severity_score(cluster_posts),
            "urgency": _urgency_score(cluster_posts),
            "independent_frequency": _clamp(15.0 + min(5, corroborating_count) * 16.0 + min(6, len(cluster_posts)) * 6.5),
            "buyer_intent": _buyer_intent_score(cluster_posts),
            "business_impact": _business_impact_score(cluster_posts),
            "strategic_fit": _strategic_fit_score(cluster_posts, instruction),
        }
        confidence_components = {
            "source_quality": _source_quality_score(cluster_posts),
            "corroboration": _corroboration_score(corroborating_count),
            "source_diversity": _source_diversity_score(families),
            "recency": round(freshness, 2),
            "specificity": round(specificity, 2),
            "extraction_quality": round(extraction_quality, 2),
        }

        opportunity = _weighted_score(opportunity_components, instruction.scoring.opportunity_weights)
        confidence = _weighted_score(confidence_components, instruction.scoring.confidence_weights)

        penalties: Dict[str, float] = {}
        if specificity < 45.0:
            penalties["vague_claim"] = instruction.scoring.penalties.get("vague_claim", 8.0)
        if not any(post.publication_date for post in cluster_posts):
            penalties["missing_date"] = instruction.scoring.penalties.get("missing_date", 6.0)
        if not any(getattr(post, "business_consequence", "") for post in cluster_posts):
            penalties["missing_business_consequence"] = instruction.scoring.penalties.get("missing_business_consequence", 10.0)
        if instruction.segments and not group["segments"]:
            penalties["missing_segment"] = instruction.scoring.penalties.get("missing_segment", 8.0)

        weakest_tier = min(post.source_tier for post in cluster_posts)
        social_only = weakest_tier >= 4
        if social_only and instruction.source_policy.require_tier4_corroboration and corroborating_count < 2:
            highly_specific_singleton = specificity >= 82.0 and extraction_quality >= 75.0
            if not (instruction.source_policy.allow_tier4_single_source_top_issues and highly_specific_singleton):
                penalties["social_only_top_issue"] = instruction.scoring.penalties.get("social_only_top_issue", 30.0)

        total_penalty = sum(penalties.values())
        opportunity = _clamp(opportunity - total_penalty * 0.25)
        confidence = _clamp(confidence - total_penalty * 0.75)
        priority = _clamp(opportunity * (0.4 + 0.6 * confidence / 100.0))

        scored_clusters.append(
            {
                "statement": group["statement"],
                "categories": sorted(group["categories"]),
                "segments": sorted(group["segments"]),
                "posts": cluster_posts,
                "families": families,
                "corroborating_count": corroborating_count,
                "freshness": round(freshness, 2),
                "opportunity": round(opportunity, 2),
                "confidence": round(confidence, 2),
                "priority": round(priority, 2),
                "opportunity_components": opportunity_components,
                "confidence_components": confidence_components,
                "penalties": penalties,
                "flags": [
                    flag for flag, enabled in (
                        ("social-led", social_only),
                        ("corroborated", corroborating_count >= 2),
                        ("high-specificity", specificity >= 75.0),
                    ) if enabled
                ],
            }
        )

    scored_clusters.sort(
        key=lambda item: (
            item["priority"],
            item["confidence"],
            item["corroborating_count"],
            len(item["posts"]),
            item["statement"],
        ),
        reverse=True,
    )

    evidences: List[EvidenceItem] = []
    clusters: List[IssueCluster] = []
    for index, cluster_data in enumerate(scored_clusters, 1):
        issue_id = f"ISSUE-{index:04d}"
        cluster = IssueCluster(
            canonical_issue_id=issue_id,
            normalized_problem_statement=cluster_data["statement"],
            category_codes=cluster_data["categories"],
            segment_codes=cluster_data["segments"],
            post_ids=[post.post_id for post in cluster_data["posts"]],
            evidence_count=len(cluster_data["posts"]),
            independent_source_count=cluster_data["corroborating_count"],
            source_family_count=len(cluster_data["families"]),
            opportunity_score=cluster_data["opportunity"],
            confidence_score=cluster_data["confidence"],
            priority_score=cluster_data["priority"],
            final_rank_score=cluster_data["priority"],
        )
        cluster.freshness_score = cluster_data["freshness"]
        cluster.source_mix = dict(cluster_data["families"])
        cluster.flags = list(cluster_data["flags"])
        cluster.score_breakdown = {
            "opportunity": {key: round(value, 2) for key, value in cluster_data["opportunity_components"].items()},
            "confidence": {key: round(value, 2) for key, value in cluster_data["confidence_components"].items()},
            "penalties": {key: round(value, 2) for key, value in cluster_data["penalties"].items()},
        }
        cluster.provenance_snippets = []

        ranked_posts = sorted(
            cluster_data["posts"],
            key=lambda post: (
                post.trust_weight,
                getattr(post, "specificity_score", 0.0),
                len(post.text),
                post.like_count,
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
            post.metadata["issue_flags"] = cluster.flags
            post.metadata["freshness_score"] = cluster.freshness_score
            post.metadata["source_mix"] = cluster.source_mix

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
            )
            evidence.normalized_problem_statement = post.normalized_problem_statement
            evidence.business_consequence = getattr(post, "business_consequence", "")
            evidence.buyer_role = getattr(post, "buyer_role", "")
            evidence.segment = "|".join(post.segments)
            evidence.geography = getattr(post, "geography", "")
            evidence.specificity_score = getattr(post, "specificity_score", 0.0)
            evidence.extraction_quality = getattr(post, "extraction_quality", 0.0)
            evidence.source_title = post.source_title
            evidences.append(evidence)

            cluster.evidence_ids.append(evidence.evidence_id)
            if len(cluster.provenance_snippets) < 4:
                snippet = f"{post.platform}:{post.source_family}: {(post.text or '').strip()[:120]}"
                cluster.provenance_snippets.append(snippet)

        clusters.append(cluster)

    return {"issues": clusters, "evidence": evidences}
