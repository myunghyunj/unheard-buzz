# Governance and Source Policy

`unheard-buzz` is a local consulting workflow, not a truth engine.
This file defines the operating hygiene expected when using it repeatedly.

## Source-use principles

- Discovery evidence is not automatically recommendation-grade evidence.
- Corroboration should prefer independent sources, not repeated posts from the same thread or channel.
- Official or benchmark sources should stay distinct from complaint evidence.
- Contradictions should stay visible all the way into decision artifacts.

## Source classes

Typical classes in this repo:
- community
- github
- trade_press
- official

Recommended use:
- discovery only: weak community or single-source signals
- corroboration: multiple independent community sources or stronger-source reports
- final recommendation support: benchmark-aware evidence with visible provenance and contradictions

## Manual and private inputs

Examples:
- `input/linkedin_export.csv`
- `input/reviewer_annotations.csv`

Guidance:
- treat manual imports as potentially sensitive
- keep them local
- avoid copying personal identifiers into public artifacts when not necessary
- prefer anonymized summaries and short excerpts over bulk raw text reuse

## Confidence communication

The repo should not imply certainty beyond the evidence mix.

Always distinguish:
- evidence
- inference
- recommendation

Recommendations should be flagged for human review when they are:
- benchmark-contradicted
- social-only with weak corroboration
- sensitive or high-stakes
- dependent on sparse or stale evidence

## Governance gaps still open

Current implementation still needs:
- a fuller source-terms matrix by connector
- retention/compaction policy for stored raw text
- stronger rules for sensitive domains and compliance-heavy recommendations
