import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from config import Instruction, SocialPost


_POSITIVE_CLAIM_MARKERS = (
    "fixed", "resolved", "available", "supported", "launched", "released",
    "uptime", "stable", "online", "improved", "faster", "cheaper",
)
_NEGATIVE_ISSUE_MARKERS = (
    "broken", "issue", "outage", "offline", "blocked", "delay", "slow",
    "fails", "failing", "cannot", "can't", "unable", "awful",
)
_POSITIVE_COMPETITOR_MARKERS = (
    "better", "works", "switched to", "moved to", "using", "faster", "cheaper",
    "reliable", "stable",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _entity_id(entity_type: str, canonical_name: str) -> str:
    return f"{entity_type}:{_slug(canonical_name)}"


def _hash_id(prefix: str, payload: str) -> str:
    return f"{prefix}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _claim_polarity(text: str) -> str:
    normalized = _norm(text)
    if any(marker in normalized for marker in _POSITIVE_CLAIM_MARKERS):
        return "positive"
    if any(marker in normalized for marker in _NEGATIVE_ISSUE_MARKERS):
        return "negative"
    return "neutral"


def _split_claims(text: str) -> List[str]:
    parts = re.split(r"[\n\r]+|(?<=[.!?])\s+", text or "")
    claims = []
    for part in parts:
        normalized = _norm(part)
        if len(normalized.split()) < 3:
            continue
        if any(marker in normalized for marker in _POSITIVE_CLAIM_MARKERS):
            claims.append(part.strip()[:240])
    return claims[:6]


def _manual_documents(instruction: Instruction) -> List[dict]:
    now = datetime.now(timezone.utc).isoformat()
    documents = []
    for source in instruction.benchmarks.manual_sources:
        entity_id = _entity_id(source.entity_type or "company", source.entity) if source.entity else ""
        excerpt = source.excerpt or source.name
        documents.append(
            {
                "doc_id": _hash_id("benchdoc", f"{source.name}|{source.url}|{source.entity}|manual"),
                "source_type": source.kind or "manual_source",
                "source_family": source.source_family or "official",
                "source_tier": int(source.source_tier or 1),
                "entity_id": entity_id,
                "title": source.name,
                "url": source.url,
                "publication_date": now,
                "text_excerpt": excerpt,
                "provenance": "manual_source",
                "claims": list(source.claims or []),
                "tags": list(source.tags or []),
            }
        )
    return documents


def _ingested_documents(posts: List[SocialPost]) -> List[dict]:
    documents = []
    for post in posts:
        source_family = post.source_family or post.metadata.get("source_family", "")
        if source_family == "community":
            continue
        if post.platform == "github_issues" and not any(marker in _norm(post.text) for marker in _POSITIVE_CLAIM_MARKERS):
            continue
        if post.platform != "github_issues" and post.source_tier >= 4:
            continue
        documents.append(
            {
                "doc_id": _hash_id("benchdoc", f"{post.platform}|{post.post_id}|{post.url}"),
                "source_type": post.evidence_class or post.platform,
                "source_family": source_family or "official",
                "source_tier": int(post.source_tier or 1),
                "entity_id": "",
                "title": post.source_title,
                "url": post.url,
                "publication_date": post.publication_date or post.timestamp,
                "text_excerpt": (post.text or "")[:300],
                "provenance": f"ingested:{post.platform}",
                "claims": [],
                "tags": [],
            }
        )
    return documents


def _benchmark_claims(documents: List[dict]) -> List[dict]:
    claims = []
    for document in documents:
        raw_claims = list(document.get("claims", []) or [])
        if not raw_claims:
            raw_claims = _split_claims(document.get("text_excerpt", ""))
        for index, claim_text in enumerate(raw_claims):
            claims.append(
                {
                    "claim_id": _hash_id("claim", f"{document['doc_id']}|{index}|{claim_text}"),
                    "doc_id": document["doc_id"],
                    "entity_id": document.get("entity_id", ""),
                    "claim_text": claim_text,
                    "claim_type": document.get("source_type", "benchmark_claim"),
                    "polarity": _claim_polarity(claim_text),
                    "publication_date": document.get("publication_date", ""),
                    "url": document.get("url", ""),
                }
            )
    return claims


def _issue_entity_index(issue_entity_links: List[dict]) -> Dict[str, List[str]]:
    issue_entities = defaultdict(list)
    for link in issue_entity_links:
        issue_entities[link["canonical_issue_id"]].append(link["entity_id"])
    return issue_entities


def _issue_text(issue, posts_by_id: Dict[str, SocialPost]) -> str:
    parts = [issue.normalized_problem_statement or ""]
    parts.extend(issue.provenance_snippets or [])
    for post_id in issue.post_ids[:6]:
        post = posts_by_id.get(post_id)
        if post:
            parts.append(post.text)
    return "\n".join(part for part in parts if part)


def _issue_segment_contradictions(issue_layer: Dict[str, List], posts_by_id: Dict[str, SocialPost]) -> List[dict]:
    rows = []
    for issue in issue_layer["issues"]:
        segment_scores = defaultdict(list)
        for post_id in issue.post_ids:
            post = posts_by_id.get(post_id)
            if not post or not post.segments:
                continue
            normalized = _norm(post.text)
            severity = 20 + sum(10 for marker in _NEGATIVE_ISSUE_MARKERS if marker in normalized)
            for segment in post.segments:
                segment_scores[segment].append(severity)
        if len(segment_scores) < 2:
            continue
        averages = {
            segment: sum(values) / max(1, len(values))
            for segment, values in segment_scores.items()
        }
        if max(averages.values()) - min(averages.values()) < 10:
            continue
        rows.append(
            {
                "contradiction_id": _hash_id("contra", f"{issue.canonical_issue_id}|segment"),
                "contradiction_type": "segment_severity_gap",
                "canonical_issue_id": issue.canonical_issue_id,
                "entity_id": "",
                "left_evidence": json.dumps(averages, ensure_ascii=False, sort_keys=True),
                "right_evidence": "",
                "summary": f"Severity differs by segment: {averages}",
            }
        )
    return rows


def build_benchmark_pack(
    issue_layer: Dict[str, List],
    posts: List[SocialPost],
    entity_layer: dict,
    instruction: Instruction,
) -> dict:
    posts_by_id = {post.post_id: post for post in posts}
    documents = _manual_documents(instruction)
    documents.extend(_ingested_documents(posts))
    deduped_documents = {}
    for document in documents:
        deduped_documents[document["doc_id"]] = document
    documents = list(deduped_documents.values())

    claims = _benchmark_claims(documents)
    issue_entities = _issue_entity_index(entity_layer.get("issue_entity_links", []))
    contradictions = []

    for issue in issue_layer["issues"]:
        issue_text = _issue_text(issue, posts_by_id)
        normalized_issue = _norm(issue_text)
        issue_entity_ids = set(issue_entities.get(issue.canonical_issue_id, []))

        for claim in claims:
            if claim["polarity"] != "positive":
                continue
            normalized_claim = _norm(claim["claim_text"])
            shared_entities = bool(claim.get("entity_id")) and claim.get("entity_id") in issue_entity_ids
            shared_markers = any(marker in normalized_issue and marker in normalized_claim for marker in ("billing", "charging", "support", "deployment", "status"))
            if not shared_entities and not shared_markers:
                continue
            if not any(marker in normalized_issue for marker in _NEGATIVE_ISSUE_MARKERS):
                continue
            contradictions.append(
                {
                    "contradiction_id": _hash_id("contra", f"{issue.canonical_issue_id}|{claim['claim_id']}"),
                    "contradiction_type": "complaint_vs_benchmark_claim",
                    "canonical_issue_id": issue.canonical_issue_id,
                    "entity_id": claim.get("entity_id", ""),
                    "left_evidence": issue_text[:220],
                    "right_evidence": claim["claim_text"][:220],
                    "summary": "Complaint evidence conflicts with an official or benchmark claim.",
                }
            )

        for link in entity_layer.get("issue_entity_links", []):
            if link["canonical_issue_id"] != issue.canonical_issue_id or link["entity_type"] != "competitor":
                continue
            if any(marker in normalized_issue for marker in _POSITIVE_COMPETITOR_MARKERS):
                contradictions.append(
                    {
                        "contradiction_id": _hash_id("contra", f"{issue.canonical_issue_id}|{link['entity_id']}|alt"),
                        "contradiction_type": "alternative_positive_signal",
                        "canonical_issue_id": issue.canonical_issue_id,
                        "entity_id": link["entity_id"],
                        "left_evidence": issue_text[:220],
                        "right_evidence": link["canonical_name"],
                        "summary": "The issue mentions an alternative or competitor with positive comparative language.",
                    }
                )

    contradictions.extend(_issue_segment_contradictions(issue_layer, posts_by_id))

    coverage_by_entity = Counter(document.get("entity_id") or "unlinked" for document in documents)
    source_mix = Counter(document.get("source_family") or "unknown" for document in documents)
    return {
        "benchmark_documents": documents,
        "benchmark_claims": claims,
        "contradictions": contradictions,
        "coverage": {
            "enabled": instruction.benchmarks.enabled,
            "document_count": len(documents),
            "claim_count": len(claims),
            "contradiction_count": len(contradictions),
            "coverage_by_entity": dict(coverage_by_entity),
            "source_mix": dict(source_mix),
            "benchmark_documents": documents,
            "benchmark_claims": claims,
        },
    }
