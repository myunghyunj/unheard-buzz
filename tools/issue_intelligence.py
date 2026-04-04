import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from config import EvidenceItem, Instruction, IssueCluster, SocialPost


def _normalize_source_family(post: SocialPost) -> str:
    if post.source_family:
        return post.source_family
    platform = (post.platform or "").lower()
    if platform in {"youtube", "reddit", "twitter", "linkedin"}:
        return "community"
    if platform == "rss":
        return "official"
    if platform == "github_issues":
        return "github"
    return platform or "community"


def apply_source_policy(post: SocialPost, instruction: Instruction) -> None:
    family = _normalize_source_family(post)
    tiers = instruction.source_policy.source_tiers
    weights = instruction.source_policy.trust_weights
    post.source_family = family
    post.source_tier = int(post.metadata.get("source_tier", tiers.get(family, 4)))
    post.evidence_class = post.metadata.get("evidence_class", "community_post")
    post.publication_date = post.publication_date or post.timestamp
    post.trust_weight = float(post.metadata.get("trust_weight", weights.get(family, 0.5)))
    root = post.metadata.get("domain") or post.metadata.get("source_domain") or family
    post.independence_key = str(post.metadata.get("independence_key") or f"{family}:{root}").lower()


def _norm_text(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"https?://\\S+", " ", t)
    t = re.sub(r"[^a-z0-9\\s]", " ", t)
    t = re.sub(r"\\s+", " ", t).strip()
    return t


def _extract_problem_statement(post: SocialPost) -> str:
    text = _norm_text(post.text)
    m = re.search(r"(problem|issue|broken|fail|cannot|can't|unable|delay|outage)[^\\.]{0,120}", text)
    if m:
        return m.group(0).strip()
    return " ".join(text.split()[:14]).strip()


def _freshness_score(publication_date: str, half_life_days: int) -> float:
    try:
        iso = publication_date.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - dt).days, 0)
    except Exception:
        return 40.0
    return max(0.0, min(100.0, 100.0 * math.exp(-age_days / max(1, half_life_days))))


def build_issue_intelligence(posts: List[SocialPost], instruction: Instruction) -> Dict[str, List]:
    by_problem: Dict[str, List[SocialPost]] = defaultdict(list)
    evidences: List[EvidenceItem] = []

    for post in posts:
        apply_source_policy(post, instruction)
        statement = _extract_problem_statement(post)
        normalized_problem = statement[:120] or "unspecified issue"
        post.metadata["normalized_problem_statement"] = normalized_problem
        key = f"{('|'.join(post.categories) or 'uncat')}::{normalized_problem}"
        by_problem[key].append(post)

    clusters: List[IssueCluster] = []
    for idx, (key, cluster_posts) in enumerate(by_problem.items(), 1):
        issue_id = f"ISSUE-{idx:04d}"
        cats = sorted({c for p in cluster_posts for c in p.categories})
        segs = sorted({s for p in cluster_posts for s in p.segments})
        independence_keys = {p.independence_key for p in cluster_posts if p.independence_key}
        family_counts = Counter(p.source_family for p in cluster_posts)
        avg_trust = (sum(p.trust_weight for p in cluster_posts) / len(cluster_posts)) if cluster_posts else 0.5
        specificity_hits = sum(1 for p in cluster_posts if len((p.metadata.get("normalized_problem_statement") or "").split()) >= 5)
        opportunity = min(100.0, 30 + len(cluster_posts) * 8 + len(independence_keys) * 7 + sum(8 for p in cluster_posts if p.has_wish))
        corroboration = min(100.0, len(independence_keys) * 30)
        diversity = min(100.0, len(family_counts) * 25)
        recency = sum(_freshness_score(p.publication_date, instruction.source_policy.freshness_half_life_days) for p in cluster_posts) / max(1, len(cluster_posts))
        confidence = min(100.0, (avg_trust * 45) + (corroboration * 0.25) + (diversity * 0.2) + (recency * 0.1) + (specificity_hits / max(1, len(cluster_posts)) * 20))
        penalties = 0.0
        if not segs:
            penalties += instruction.scoring.penalties.get("missing_segment", 8.0)
        if all(not p.metadata.get("business_consequence") for p in cluster_posts):
            penalties += instruction.scoring.penalties.get("missing_business_consequence", 10.0)
        if min(p.source_tier for p in cluster_posts) >= 4 and len(independence_keys) < 2 and instruction.source_policy.require_tier4_corroboration:
            penalties += instruction.scoring.penalties.get("social_only_top_issue", 30.0)

        opportunity = max(0.0, opportunity - penalties * 0.25)
        confidence = max(0.0, confidence - penalties * 0.75)
        priority = max(0.0, min(100.0, opportunity * (0.4 + 0.6 * confidence / 100.0)))

        cluster = IssueCluster(
            canonical_issue_id=issue_id,
            normalized_problem_statement=key.split("::", 1)[1],
            category_codes=cats,
            segment_codes=segs,
            post_ids=[p.post_id for p in cluster_posts],
            evidence_count=len(cluster_posts),
            independent_source_count=len(independence_keys),
            source_family_count=len(family_counts),
            opportunity_score=round(opportunity, 2),
            confidence_score=round(confidence, 2),
            priority_score=round(priority, 2),
            final_rank_score=round(priority, 2),
        )
        clusters.append(cluster)

        for p in cluster_posts:
            p.canonical_issue_id = issue_id
            p.issue_opportunity_score = cluster.opportunity_score
            p.issue_confidence_score = cluster.confidence_score
            p.issue_priority_score = cluster.priority_score
            p.final_rank_score = cluster.priority_score
            evidence = EvidenceItem(
                evidence_id=f"EVID-{len(evidences)+1:06d}",
                post_id=p.post_id,
                canonical_issue_id=issue_id,
                source_family=p.source_family,
                source_tier=p.source_tier,
                evidence_class=p.evidence_class,
                trust_weight=p.trust_weight,
                publication_date=p.publication_date,
                independence_key=p.independence_key,
                excerpt=(p.text or "")[:300],
                url=p.url,
                platform=p.platform,
            )
            evidences.append(evidence)
            cluster.evidence_ids.append(evidence.evidence_id)

    clusters.sort(key=lambda c: c.priority_score, reverse=True)
    return {"issues": clusters, "evidence": evidences}
