# m3trik/scripts

**Role**: Python repo-maintenance scripts — linting, release automation, ecosystem consistency, workspace inventory.

**Nav**: [← parent](../CLAUDE.md) · [← root](../../CLAUDE.md)

## Scripts

- `generate_workspace_inventory.py` — scans direct child repos under `_scripts/`, writes Markdown/JSON inventory to `m3trik/docs/` (repo breakdowns, package roots, code roots, tracked LOC).

## Rules

- One-shot maintenance scripts go here. Reusable logic belongs in [pythontk](../../pythontk/CLAUDE.md) instead.
