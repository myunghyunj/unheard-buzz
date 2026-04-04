"""RSS collector for official docs, release notes, and trade feeds."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from config import Instruction, SocialPost


def _parse_date(text: str) -> str:
    if not text:
        return datetime.now(timezone.utc).isoformat()
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def run_rss(instruction: Instruction) -> dict:
    cfg = instruction.rss
    if not cfg.enabled:
        return {"posts": [], "stats": {"skipped": True}}

    posts: List[SocialPost] = []
    for feed in cfg.feeds:
        url = feed.get("url", "")
        if not url:
            continue
        tier = int(feed.get("source_tier", 1))
        source_family = feed.get("source_family", "official")
        evidence_class = feed.get("evidence_class", "release_note")
        trust_weight = float(feed.get("trust_weight", instruction.source_policy.trust_weights.get(source_family, 1.0)))

        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception:
            continue

        items = root.findall(".//item")[: cfg.max_items_per_feed]
        for idx, item in enumerate(items):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or url).strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = _parse_date(item.findtext("pubDate") or "")
            text = f"{title}\n\n{desc}".strip()
            domain = (urlparse(link).netloc or "rss").lower()
            posts.append(
                SocialPost(
                    post_id=f"rss_{domain}_{idx}",
                    platform="rss",
                    source_id=domain,
                    source_title=title or domain,
                    author=feed.get("name", domain),
                    text=text,
                    timestamp=pub_date,
                    url=link,
                    publication_date=pub_date,
                    source_family=source_family,
                    source_tier=tier,
                    evidence_class=evidence_class,
                    trust_weight=trust_weight,
                    independence_key=f"{source_family}:{domain}",
                    metadata={"domain": domain, "collector_score": 0.0},
                )
            )

    return {"posts": posts, "stats": {"feeds": len(cfg.feeds), "items": len(posts)}}
