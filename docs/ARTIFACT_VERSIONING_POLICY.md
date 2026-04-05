# Artifact Versioning Policy

`unheard-buzz` now emits a mixed artifact pack: CSV, JSON, Markdown, HTML, and persisted state records.
This file defines the compatibility policy for those artifacts.

## Principles

- Every major machine-readable object should have a schema version.
- Run manifests should record the active program contract version.
- Additive changes are preferred over breaking changes.
- Human-readable artifacts should point to the machine-readable artifacts they summarize.

## Current contract

- Program contract version: `consultant-os.v1`
- Current schema versions are defined in [schema_versions.py](/Users/myunghyunjeong/Documents/GitHub/unheard-buzz/tools/schema_versions.py)

## Compatibility rules

### Minor-compatible changes

These are allowed without a contract rename:
- adding a new optional JSON field
- adding a new optional CSV column
- adding a new artifact while preserving existing artifacts
- adding a new agent role or workstream field with a safe default

### Breaking changes

These require a schema version bump and migration note:
- renaming or removing a JSON field
- renaming or removing a CSV column
- changing artifact shape from list to object or vice versa
- changing the meaning of a score or identifier
- replacing an artifact without a documented fallback or alias

## Artifact expectations

- `run_manifest.json` should identify the program contract and artifact inventory path.
- Core JSON artifacts should carry `schema_version`.
- Core list-shaped JSON artifacts should carry `schema_version` at the item level when top-level wrapping would break compatibility.
- CSV artifacts may carry a repeated `schema_version` column for easier downstream handling.

## Migration notes

When a breaking change is introduced:
1. bump the relevant schema version
2. explain the change in release notes or migration notes
3. update tests and example artifacts
4. preserve backward-compatible aliases where feasible
