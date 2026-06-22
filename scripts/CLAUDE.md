# m3trik/scripts

**Role**: Repo-maintenance scripts — linting, release automation, ecosystem consistency, workspace inventory, credential helpers.

**Nav**: [← parent](../CLAUDE.md) · [← root](../../CLAUDE.md)

## Scripts

- `generate_workspace_inventory.py` — scans direct child repos under `_scripts/`, writes Markdown/JSON inventory to `m3trik/docs/` (repo breakdowns, package roots, code roots, tracked LOC).
- `Generate-WorkspaceInventory.ps1` — PowerShell wrapper around the above; defaults workspace root and output dir.
- `generate_api_registry.py` — AST-walks the packages in its `ECOSYSTEM_PACKAGES` tuple (the SSoT — don't re-list the names elsewhere; quote the tuple) and emits per package: `API_INDEX.md` (compact, grep-able symbol index — the first-read entrypoint), `API_REGISTRY.md` (full surface — grep, don't Read whole), `API_REGISTRY.json` (diff sidecar), `API_CHANGES.md` (diff). Plus `m3trik/docs/API_SHADOWS.md` (cross-package collisions, with intentional mayatk↔blendertk port parity bucketed separately). Run with no args for the full set, or names for a subset (single-package runs still refresh the full shadow report by reconstructing the others from their JSON sidecars). `--check` exits non-zero if any registry is stale (CI-friendly).
- `compare_panel_surface.py` — AST-diffs the Maya→Blender *control surface* (`config_buttons`, every `menu.add`/option-box/action-column control, `set_toggle`/`pin`/`add_presets`, widget-handler slot defs). The mechanical name-level 1:1 check — manual reads kept missing flat-out-absent header options. `--panel <name>` for one pair; `--all` sweeps **every** mayatk↔blendertk `*Slots` panel **and** every `tentacle/slots/maya`↔`blender` file (+ lists Maya tools/files with no Blender counterpart); `--all --write` regenerates `tentacle/docs/PARITY_SURFACE.md` (the name-level companion to `PARITY_AUDIT.md`). Deltas are either in its `KNOWN_MAYA_ONLY` allowlist (with a reason) or real gaps. Exit 1 on unexplained gaps (CI-friendly).
- `check_context_budget.py` — context-budget guard: enforces the size + consistency caps on the agent-facing surface (`MEMORY.md` byte/entry caps + 1-link-per-topic coverage, `CLAUDE.md` sizes, registry freshness, root dispatch == `ECOSYSTEM_PACKAGES`). FAIL exits non-zero (CI gate in `refresh-api-registry.yml`); WARN is advisory. Rules: [`m3trik/docs/CONTEXT_BUDGET.md`](../docs/CONTEXT_BUDGET.md).
- `update_samba_creds.ps1` — pushes the current user's stored server credential to the Linux server via SSH (DPAPI-decrypted locally).

## Rules

- One-shot maintenance scripts go here. Reusable logic belongs in [pythontk](../../pythontk/CLAUDE.md) instead.
