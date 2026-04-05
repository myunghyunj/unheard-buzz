import os
import sys
import unittest
from copy import deepcopy

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from config import Instruction, SocialPost
from issue_intelligence import build_issue_intelligence


def _base_instruction() -> Instruction:
    instruction = Instruction()
    instruction.categories = {
        "OPS": {
            "name": "Operations",
            "description": "Operational pain points",
            "keywords": ["broken", "outage", "manual"],
            "opportunity_signals": ["roadmap", "would pay", "replacement vendor"],
            "example_phrases": ["would pay to switch", "replacement vendor roadmap"],
        }
    }
    return instruction


def _post(
    post_id: str,
    text: str,
    *,
    platform: str = "github_issues",
    source_id: str = "",
    source_family: str = "github",
    source_tier: int = 2,
    trust_weight: float = 0.85,
    publication_date: str = "2026-04-01T00:00:00+00:00",
    extra_metadata=None,
) -> SocialPost:
    metadata = {
        "source_family": source_family,
        "source_tier": source_tier,
        "trust_weight": trust_weight,
        "publication_date": publication_date,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return SocialPost(
        post_id=post_id,
        platform=platform,
        source_id=source_id or post_id,
        source_title=post_id,
        author="user",
        text=text,
        categories=["OPS"],
        metadata=metadata,
    )


def _issues_by_statement(issue_layer):
    return {
        issue.normalized_problem_statement: issue
        for issue in issue_layer["issues"]
    }


class ScoringMatrixTest(unittest.TestCase):
    def test_opportunity_weights_change_ranking(self):
        instruction = _base_instruction()
        severe_issue = _post(
            "sev",
            "Production outage blocks customers and causes lost revenue today.",
        )
        buyer_issue = _post(
            "buy",
            "I wish there were a replacement vendor roadmap because the manual workaround wastes hours and I would pay to switch today.",
        )

        severity_first = deepcopy(instruction)
        severity_first.scoring.opportunity_weights = {
            "severity": 1.0,
            "urgency": 0.0,
            "independent_frequency": 0.0,
            "buyer_intent": 0.0,
            "business_impact": 0.0,
            "strategic_fit": 0.0,
        }
        buyer_first = deepcopy(instruction)
        buyer_first.scoring.opportunity_weights = {
            "severity": 0.0,
            "urgency": 0.0,
            "independent_frequency": 0.0,
            "buyer_intent": 1.0,
            "business_impact": 0.0,
            "strategic_fit": 0.0,
        }

        severity_ranked = build_issue_intelligence(
            [deepcopy(severe_issue), deepcopy(buyer_issue)],
            severity_first,
        )["issues"]
        buyer_ranked = build_issue_intelligence(
            [deepcopy(severe_issue), deepcopy(buyer_issue)],
            buyer_first,
        )["issues"]

        self.assertEqual(severity_ranked[0].normalized_problem_statement, severe_issue.text)
        self.assertEqual(buyer_ranked[0].normalized_problem_statement, buyer_issue.text)

    def test_confidence_weights_change_ranking(self):
        instruction = _base_instruction()
        instruction.scoring.opportunity_weights = {
            "severity": 1.0,
            "urgency": 0.0,
            "independent_frequency": 0.0,
            "buyer_intent": 0.0,
            "business_impact": 0.0,
            "strategic_fit": 0.0,
        }
        source_quality_issue = _post(
            "gh-1",
            "Billing export is broken and blocks finance every day.",
            platform="github_issues",
            source_family="github",
            source_tier=2,
            trust_weight=0.85,
        )
        corroborated_issue_a = _post(
            "rd-1",
            "Invoice sync is broken and blocks finance every day.",
            platform="reddit",
            source_family="community",
            source_tier=4,
            trust_weight=0.5,
            extra_metadata={"subreddit": "finance"},
        )
        corroborated_issue_b = _post(
            "rd-2",
            "Invoice sync is broken and blocks finance every day.",
            platform="reddit",
            source_family="community",
            source_tier=4,
            trust_weight=0.5,
            extra_metadata={"subreddit": "finance"},
        )

        source_quality_first = deepcopy(instruction)
        source_quality_first.scoring.confidence_weights = {
            "source_quality": 1.0,
            "corroboration": 0.0,
            "source_diversity": 0.0,
            "recency": 0.0,
            "specificity": 0.0,
            "extraction_quality": 0.0,
        }
        corroboration_first = deepcopy(instruction)
        corroboration_first.scoring.confidence_weights = {
            "source_quality": 0.0,
            "corroboration": 1.0,
            "source_diversity": 0.0,
            "recency": 0.0,
            "specificity": 0.0,
            "extraction_quality": 0.0,
        }

        source_quality_ranked = build_issue_intelligence(
            [deepcopy(source_quality_issue), deepcopy(corroborated_issue_a), deepcopy(corroborated_issue_b)],
            source_quality_first,
        )["issues"]
        corroboration_ranked = build_issue_intelligence(
            [deepcopy(source_quality_issue), deepcopy(corroborated_issue_a), deepcopy(corroborated_issue_b)],
            corroboration_first,
        )["issues"]

        self.assertEqual(source_quality_ranked[0].normalized_problem_statement, source_quality_issue.text)
        self.assertEqual(corroboration_ranked[0].normalized_problem_statement, corroborated_issue_a.text)

    def test_social_only_guardrail_penalizes_single_source_tier4_issue(self):
        instruction = _base_instruction()
        social_issue = _post(
            "social",
            "Production outage blocks customers and causes lost revenue today.",
            platform="reddit",
            source_family="community",
            source_tier=4,
            trust_weight=0.5,
            extra_metadata={"subreddit": "ops"},
        )
        github_issue = _post(
            "github",
            "Production outage blocks customers and causes lost revenue today in the repo issue tracker.",
            platform="github_issues",
            source_family="github",
            source_tier=2,
            trust_weight=0.85,
        )

        disallowed = deepcopy(instruction)
        disallowed.source_policy.require_tier4_corroboration = True
        disallowed.source_policy.allow_tier4_single_source_top_issues = False
        allowed = deepcopy(instruction)
        allowed.source_policy.require_tier4_corroboration = True
        allowed.source_policy.allow_tier4_single_source_top_issues = True

        disallowed_layer = build_issue_intelligence(
            [deepcopy(social_issue), deepcopy(github_issue)],
            disallowed,
        )
        allowed_layer = build_issue_intelligence(
            [deepcopy(social_issue), deepcopy(github_issue)],
            allowed,
        )

        disallowed_issues = _issues_by_statement(disallowed_layer)
        allowed_issues = _issues_by_statement(allowed_layer)
        disallowed_social = disallowed_issues[social_issue.text]
        allowed_social = allowed_issues[social_issue.text]
        disallowed_github = disallowed_issues[github_issue.text]

        self.assertGreater(disallowed_github.priority_score, disallowed_social.priority_score)
        self.assertIn("social_only_top_issue", disallowed_social.score_breakdown["penalties"]["items"])
        self.assertNotIn("social_only_top_issue", allowed_social.score_breakdown["penalties"]["items"])
        self.assertGreater(allowed_social.priority_score, disallowed_social.priority_score)


if __name__ == "__main__":
    unittest.main()
