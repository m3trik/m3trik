# Docs standard — monorepo markdown organization

How markdown is organized, wired, and kept from drifting across every repo in `_scripts/`. Machine-enforced by `m3trik/scripts/check_docs.py`; policy lives here so the sweep's rules have a written rationale.

**Nav**: [← m3trik](../CLAUDE.md) · [Context budget](CONTEXT_BUDGET.md) · [uitk DOCMAP tier](../../uitk/docs/MAINTAINING.md)

## Two tiers

| Tier | Applies to | Contract |
|:--|:--|:--|
| **Hub-wired** | every repo | The reachability contract below — no ledger, no ceremony. |
| **DOCMAP-ledgered** | repos with a rich hand-written doc suite (currently **uitk**) | Hub-wired **plus** a `docs/DOCMAP.md` ledger: per-doc status, module→doc coverage map, task backlog. Contract: [uitk/docs/MAINTAINING.md](../../uitk/docs/MAINTAINING.md). Adopt for a repo when its hand-written docs grow past ~5 files with real completion/verification work outstanding. |

## Per-repo shape

- **`CLAUDE.md`** — the agent front door. Small, stable, high-signal; sizes capped by [CONTEXT_BUDGET.md](CONTEXT_BUDGET.md). Its `**Nav**:` line links the repo's other front doors (including `docs/README.md` where one exists). Never log work history here.
- **`README.md` / `docs/README.md`** — the human front door. Ecosystem packages point `pyproject.toml → readme` at `docs/README.md` (GitHub also renders it when no root README exists); uitk keeps both. Front doors are pitches with pointers — depth belongs in topic docs.
- **`CHANGELOG.md`** — the *only* home for work history. Entries describe the tree as it was when they landed, so their links rot by design and are **exempt from link checks** — never retro-edit history to fix a link.
- **`docs/*.md`** — topic docs, each reachable from a hub.
- **Co-located docs** (a format spec or tuning guide next to the code that consumes it) are encouraged — but link them from the repo's docs hub so they're discoverable. A directory-level `README.md` is self-describing in place and exempt.
- **`archive/` dirs** (and the workspace `.archive/`) — parked-by-design content: excluded from all sweeps, often deliberately untracked. Annotate any tracked-doc link into an archive with *"(local archive — untracked)"* so GitHub readers know why it 404s.

## The reachability contract (workspace sweep)

`python m3trik/scripts/check_docs.py --workspace .` (from `_scripts/`) must exit 0:

- **links** — every relative link and `#anchor` in a hand-written doc resolves (GitHub slug rules, case-sensitive).
- **orphans** — every hand-written `.md` has ≥1 inbound link from somewhere in the workspace. Exempt: `README.md` / `CLAUDE.md` / `CHANGELOG.md` / `DOCMAP.md` anywhere, `.github/**`, license files. An unreachable doc is invisible doc-rot: **wire it into a hub, or archive/remove it** — the sweep will not let it linger silently.
- **tracked** (WARN) — a doc that others link to but git doesn't track will 404 on GitHub.
- **empty** (WARN) — near-empty files are either stubs to fill or clutter to remove.
- **docmaps** — any repo shipping `docs/DOCMAP.md` also gets the full ledger suite.

Companions: `check_doc_line_refs.py` (`.py#L<line>` drift — run per repo, on demand or in a repo's CI) and `check_context_budget.py` (instruction-surface size caps). The workspace docs sweep and the context-budget guard both run in the weekly `ClaudeContextBudget` task.

## Generated markdown — fix the generator, never the output

These are emitted by tooling; the sweep never lints them (but links *from* them still count toward reachability):

| File(s) | Generator |
|:--|:--|
| `API_INDEX.md` · `API_REGISTRY.md` · `API_CHANGES.md` · `API_SHADOWS.md` | `m3trik/scripts/generate_api_registry.py` |
| `tentacle/docs/PARITY_SURFACE.md` | `m3trik/scripts/compare_panel_surface.py --all --write` |
| `tentacle/docs/PARITY_AUDIT.md` | `m3trik/scripts/generate_parity_audit.py` |
| `m3trik/docs/workspace_repo_inventory.md` | `m3trik/scripts/generate_workspace_inventory.py` |
| `server/docs/README.md` | `server/test/run-tests.ps1 -UpdateReadme` (templates: `ReadmeTemplates.ps1`) |

Vendored trees are never linted: `comfyui/app/**` (upstream ComfyUI + node packs), `www/www/assets/**` (third-party viewer libs + licenses).

## Adding a new doc — decision path

1. **Does an existing doc own the topic?** Extend it — don't fragment.
2. **Where does it live?** Next to the code it describes (co-located) if it's a spec the code consumes; `docs/` if it's narrative.
3. **Wire it**: link it from the repo's docs hub (or CLAUDE.md if agent-facing). The sweep fails on unreachable docs.
4. **DOCMAP repos**: also add a ledger row + coverage entry (the sweep fails on unledgered files).
5. Run the workspace sweep before finishing.

## What NOT to do

- Don't log work history anywhere but `CHANGELOG.md` (instruction files are cache-loaded every session — churn kills caching).
- Don't duplicate content across repos or docs — link to the owner. Sanctioned duplication only via sync blocks (uitk tier) or documented vendored copies.
- Don't hand-edit generated files.
- Don't leave one-shot reports (audits, migration plans) in the tree after they're acted on — fold conclusions into the owning docs/CHANGELOG and park the report in an archive.
