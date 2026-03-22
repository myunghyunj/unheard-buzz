# Contributing

Thanks for helping improve `unheard-buzz`.

## Before you open a PR

1. Keep changes scoped and explain the user-facing impact.
2. Avoid committing secrets, raw exports, or generated `output/` artifacts.
3. Update docs when behavior, flags, or instruction schema change.

## Local setup

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
cp instruction_template.yaml instruction.yaml
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```

## Minimal verification

Run these before opening a PR:

```bash
python3 -m py_compile tools/*.py
python3 tools/run.py --instruction examples/amputee.yaml --dry-run
```

If your change touches collection or reporting behavior, include a short note about what you tested and what outputs changed.

## Contribution guidelines

- Prefer config-driven behavior over hardcoded domain logic.
- Normalize new platform data into `SocialPost`.
- Preserve partial success: one failing platform should not take down the whole pipeline.
- Keep runtime docs in `AGENTS.md` and `CLAUDE.md`.
- Keep deep implementation notes in `ARCHITECTURE.md`.

## Pull request checklist

- Code and docs match
- No secrets or local paths committed
- README reflects any new setup or limitations
- Example or template YAML updated when schema changes
