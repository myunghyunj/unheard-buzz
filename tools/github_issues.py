"""GitHub issues/discussions/releases collector."""

import os
from datetime import datetime, timezone
from typing import List

import requests

from config import Instruction, SocialPost


def _headers(token: str):
    base = {"Accept": "application/vnd.github+json"}
    if token:
        base["Authorization"] = f"Bearer {token}"
    return base


def run_github_issues(instruction: Instruction) -> dict:
    cfg = instruction.github_issues
    if not cfg.enabled:
        return {"posts": [], "stats": {"skipped": True}}

    token = os.environ.get(cfg.api_key_env, "")
    posts: List[SocialPost] = []

    for repo in cfg.repos:
        issues_url = f"https://api.github.com/repos/{repo}/issues"
        try:
            resp = requests.get(issues_url, headers=_headers(token), params={"state": "open", "per_page": cfg.max_items_per_repo}, timeout=20)
            resp.raise_for_status()
            issues = resp.json()
        except Exception:
            issues = []

        for item in issues:
            if "pull_request" in item:
                continue
            created = item.get("created_at") or datetime.now(timezone.utc).isoformat()
            title = item.get("title", "")
            body = item.get("body") or ""
            benchmark_candidate = any(
                marker in f"{title}\n{body}".lower()
                for marker in ("fixed", "resolved", "released", "support", "status", "available")
            )
            source_tier = 2
            source_family = "github"
            posts.append(
                SocialPost(
                    post_id=f"github_{item.get('id')}",
                    platform="github_issues",
                    source_id=repo,
                    source_title=title[:120],
                    author=item.get("user", {}).get("login", ""),
                    text=f"{title}\n\n{body}".strip(),
                    like_count=int(item.get("reactions", {}).get("total_count", 0) or 0),
                    reply_count=int(item.get("comments", 0) or 0),
                    timestamp=created,
                    publication_date=created,
                    url=item.get("html_url", ""),
                    source_family=source_family,
                    source_tier=source_tier,
                    evidence_class="github_issue",
                    trust_weight=float(instruction.source_policy.trust_weights.get(source_family, 0.85)),
                    independence_key=f"github:{repo}",
                    metadata={"repo": repo, "collector_score": 0.0, "benchmark_source": benchmark_candidate},
                )
            )

    return {"posts": posts, "stats": {"repos": len(cfg.repos), "items": len(posts)}}
