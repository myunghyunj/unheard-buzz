import re
from collections import Counter, defaultdict
from typing import Dict, List

from config import Instruction, SocialPost


_ROLE_PATTERNS = {
    "finance": ("finance", "finance team", "finance ops", "accountant", "controller", "bookkeeper"),
    "developer": ("developer", "engineer", "engineering", "dev team"),
    "operator": ("operator", "operations", "ops team", "admin", "administrator"),
    "marketer": ("marketer", "marketing", "growth team"),
    "sales": ("sales", "account executive", "seller"),
    "support": ("support", "customer support", "help desk"),
    "driver": ("driver", "ev driver", "fleet driver"),
    "buyer": ("buyer", "procurement", "purchasing"),
}

_WORKFLOW_PATTERNS = {
    "billing": ("billing", "invoice", "invoicing", "payment reconciliation"),
    "reporting": ("reporting", "export", "analytics workflow", "dashboard"),
    "charging": ("charging", "charger", "station access", "plug-in workflow"),
    "onboarding": ("onboarding", "signup", "activation"),
    "support": ("support ticket", "support queue", "case workflow"),
    "deployment": ("deployment", "release", "shipping workflow"),
    "scheduling": ("scheduling", "calendar", "meeting booking"),
}

_GEOGRAPHY_PATTERNS = {
    "united_states": ("united states", "usa", "us"),
    "europe": ("europe", "eu", "european union"),
    "united_kingdom": ("united kingdom", "uk", "britain"),
    "south_korea": ("south korea", "korea", "seoul"),
    "canada": ("canada", "toronto", "vancouver"),
    "germany": ("germany", "berlin", "munich"),
    "california": ("california", "san francisco", "los angeles"),
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _entity_id(entity_type: str, canonical_name: str) -> str:
    return f"{entity_type}:{_slug(canonical_name)}"


def _candidate_entities(instruction: Instruction) -> Dict[str, dict]:
    candidates: Dict[str, dict] = {}
    alias_map: Dict[str, List[str]] = {}

    for source in instruction.benchmarks.manual_sources:
        if not source.entity:
            continue
        entity_type = source.entity_type or "company"
        entity_id = _entity_id(entity_type, source.entity)
        candidates[entity_id] = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "canonical_name": source.entity,
            "normalized_name": _slug(source.entity),
            "aliases": list(source.aliases or []),
        }

    for name in instruction.benchmarks.alternatives.tracked_entities:
        entity_id = _entity_id("competitor", name)
        candidates.setdefault(
            entity_id,
            {
                "entity_id": entity_id,
                "entity_type": "competitor",
                "canonical_name": name,
                "normalized_name": _slug(name),
                "aliases": [],
            },
        )

    for canonical_name, aliases in instruction.benchmarks.entity_aliases.items():
        normalized_key = _slug(canonical_name)
        target = next(
            (
                entity
                for entity in candidates.values()
                if entity["normalized_name"] == normalized_key
            ),
            None,
        )
        if target is None:
            entity_type = "company"
            entity_id = _entity_id(entity_type, canonical_name)
            target = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "canonical_name": canonical_name,
                "normalized_name": normalized_key,
                "aliases": [],
            }
            candidates[entity_id] = target
        target["aliases"].extend(aliases)
        alias_map[canonical_name] = aliases

    for entity in candidates.values():
        entity["aliases"] = sorted({alias for alias in entity["aliases"] if alias})

    return candidates


def _issue_text(issue, posts_by_id: Dict[str, SocialPost]) -> str:
    parts = [issue.normalized_problem_statement or ""]
    parts.extend(issue.provenance_snippets or [])
    for post_id in issue.post_ids[:6]:
        post = posts_by_id.get(post_id)
        if post:
            parts.append(post.text or "")
    return "\n".join(part for part in parts if part).strip()


def _match_configured_entities(text: str, candidates: Dict[str, dict]) -> List[dict]:
    matches = []
    normalized = _norm(text)
    for entity in candidates.values():
        phrases = [entity["canonical_name"], *entity.get("aliases", [])]
        for phrase in phrases:
            phrase_norm = _norm(phrase)
            if not phrase_norm:
                continue
            if phrase_norm in normalized:
                matches.append(
                    {
                        "entity_id": entity["entity_id"],
                        "entity_type": entity["entity_type"],
                        "canonical_name": entity["canonical_name"],
                        "link_type": "competitor_mentioned" if entity["entity_type"] == "competitor" else "entity_mentioned",
                        "confidence": 0.95 if phrase == entity["canonical_name"] else 0.85,
                        "provenance": phrase,
                    }
                )
                break
    return matches


def _match_pattern_entities(text: str, patterns: Dict[str, tuple], entity_type: str, link_type: str) -> List[dict]:
    normalized = _norm(text)
    matches = []
    for canonical_name, phrases in patterns.items():
        for phrase in phrases:
            if _norm(phrase) in normalized:
                display_name = canonical_name.replace("_", " ").title()
                matches.append(
                    {
                        "entity_id": _entity_id(entity_type, display_name),
                        "entity_type": entity_type,
                        "canonical_name": display_name,
                        "link_type": link_type,
                        "confidence": 0.8,
                        "provenance": phrase,
                    }
                )
                break
    return matches


def build_entity_layer(issue_layer: Dict[str, List], posts: List[SocialPost], instruction: Instruction) -> dict:
    posts_by_id = {post.post_id: post for post in posts}
    candidates = _candidate_entities(instruction)
    entities: Dict[str, dict] = {
        entity_id: {
            **entity,
            "supporting_issue_count": 0,
            "mention_count": 0,
        }
        for entity_id, entity in candidates.items()
    }
    issue_entity_links = []

    for issue in issue_layer["issues"]:
        text = _issue_text(issue, posts_by_id)
        matches = []
        matches.extend(_match_configured_entities(text, candidates))
        matches.extend(_match_pattern_entities(text, _ROLE_PATTERNS, "role", "affected_role"))
        matches.extend(_match_pattern_entities(text, _WORKFLOW_PATTERNS, "workflow", "affected_workflow"))
        matches.extend(_match_pattern_entities(text, _GEOGRAPHY_PATTERNS, "geography", "geography_mentioned"))

        deduped = {}
        for match in matches:
            deduped[(match["entity_id"], match["link_type"])] = match

        for match in deduped.values():
            entity = entities.setdefault(
                match["entity_id"],
                {
                    "entity_id": match["entity_id"],
                    "entity_type": match["entity_type"],
                    "canonical_name": match["canonical_name"],
                    "normalized_name": _slug(match["canonical_name"]),
                    "supporting_issue_count": 0,
                    "mention_count": 0,
                },
            )
            entity["supporting_issue_count"] += 1
            entity["mention_count"] += 1
            issue_entity_links.append(
                {
                    "canonical_issue_id": issue.canonical_issue_id,
                    "entity_id": match["entity_id"],
                    "entity_type": match["entity_type"],
                    "canonical_name": match["canonical_name"],
                    "link_type": match["link_type"],
                    "confidence": round(match["confidence"], 2),
                    "provenance": match["provenance"],
                }
            )

    alternative_rows = []
    issues_by_entity = defaultdict(list)
    for link in issue_entity_links:
        if link["entity_type"] == "competitor":
            issues_by_entity[link["entity_id"]].append(link["canonical_issue_id"])
    for entity_id, issue_ids in sorted(issues_by_entity.items()):
        entity = entities[entity_id]
        alternative_rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity["canonical_name"],
                "entity_type": entity["entity_type"],
                "issue_count": len(sorted(set(issue_ids))),
                "issues": "|".join(sorted(set(issue_ids))),
            }
        )

    entity_rows = sorted(
        entities.values(),
        key=lambda item: (-item.get("supporting_issue_count", 0), item["entity_type"], item["canonical_name"]),
    )
    return {
        "entities": entity_rows,
        "issue_entity_links": sorted(
            issue_entity_links,
            key=lambda item: (item["canonical_issue_id"], item["entity_type"], item["canonical_name"]),
        ),
        "alternatives_matrix": alternative_rows,
    }
