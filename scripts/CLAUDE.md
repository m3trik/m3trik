# m3trik/scripts

**Role**: Repo-maintenance scripts — gates, generators, sync tools, workspace inventory. Each script's module docstring (or `-h`) is the SSoT for its behaviour; this table is the map.

**Nav**: [← parent](../CLAUDE.md) · [← root](../../CLAUDE.md) · standards: [CODE_STANDARD](../docs/CODE_STANDARD.md) · [DOCS_STANDARD](../docs/DOCS_STANDARD.md) · [CONTEXT_BUDGET](../docs/CONTEXT_BUDGET.md)

## Generators (fix the generator, never the output)

| Script | Emits | Notes |
|:--|:--|:--|
| `generate_api_registry.py [pkg…]` | per package `API_INDEX.md` / `API_REGISTRY.md` / `API_REGISTRY.json` / `API_CHANGES.md` + `docs/API_SHADOWS.md` | `ECOSYSTEM_PACKAGES` tuple is the SSoT for the package set — quote it, never re-list. Single-package runs still refresh the whole shadow report; `API_CHANGES` diffs vs `origin/main`'s sidecar. `--check` = CI staleness gate. |
| `compare_panel_surface.py --all --write` / `--panel <name>` | `tentacle/docs/PARITY_SURFACE.md` | Static mayatk↔blendertk + tentacle maya↔blender control-surface diff (loop-unrolled, `.ui` XML, defaults, combos, dead handlers). UNTRIAGED rows in `tentacle/docs/parity_map.py` ⇒ exit 1 (CI gate). |
| `generate_parity_audit.py` | `tentacle/docs/PARITY_AUDIT.md` | Coarse depth scoreboard; refuses stale registry input (`--allow-stale`); `--check` exits 1 if stale. Trust its `surface` column over line ratios. |
| `generate_dcc_coverage.py` | `tentacle/docs/DCC_COVERAGE.md` | tentacle DCC slot-coverage report. |
| `generate_workspace_inventory.py` (+ `Generate-WorkspaceInventory.ps1`) | `docs/workspace_repo_inventory.{md,json}` | Direct child repos: package/code roots, tracked LOC. |

## Gates (exit 0 or the build is red)

| Script | Fails on | Notes |
|:--|:--|:--|
| `check_context_budget.py` | `MEMORY.md` byte/entry caps + coverage, `CLAUDE.md` sizes (root 8,192 / subs 6,144 advisory, 10,240 hard), broken CLAUDE links, root dispatch ≠ `ECOSYSTEM_PACKAGES`, Nav `Deps:` lagging pyproject, stale registries | Rules: [CONTEXT_BUDGET.md](../docs/CONTEXT_BUDGET.md). `--no-runtime` skips the pythontk live-surface spot check (the DCC half is `Check-RuntimeSurface.ps1`). |
| `check_docs.py --workspace <dir>` / `--root <pkg>` | broken relative links/anchors, orphan hand-written md, UNTRIAGED DOCMAP coverage | Policy: [DOCS_STANDARD.md](../docs/DOCS_STANDARD.md). CHANGELOGs, vendored/`archive/`/generated files exempt; `--root` runs the DOCMAP ledger suite (uitk). |
| `check_doc_line_refs.py --root <repo>` | `.py#L<line>` refs to a missing file / out-of-range line | Generated registries excluded. |
| `check_temp_artifacts.py` | unowned artifacts, two ways: production source allocating temp files/dirs outside `ptk.TempArtifacts` (`mkstemp`/`mkdtemp`/`NamedTemporaryFile(delete=False)`), and stray files sitting in a package tree | Self-cleaning forms and bare `gettempdir()` pass; tests exempt. Exceptions go in its `ALLOWLIST` with a reason — a growing list means the primitive lacks a capability. The stray sweep treats a file as legitimate only if Python loads it or `package-data`/`MANIFEST.in` declares it (both are read — uitk's icons are declared only in the manifest); packages declaring neither are skipped. |
| `check_tooltips.py --workspace` | a `tooltip.fmt()` call or `.ui` `toolTip` that Qt would eat (bare `<`) | Renders then parses every tooltip. |
| `check_ui_spacers.py [--root] [--max-gap]` | a `Fixed` vertical spacer taller than the panels' ~10 px gap (Designer's 20×40 default ships dead space) | Sweeps tentacle/mayatk/blendertk/extapps; tentacle also pins it in `test_ui_integrity.py`. |
| `verify_runtime_surface.py verify <pkg>` / `dump` | a member in the live `HelpMixin` surface that the committed registry lacks | Catches metaclass/mixin injection the AST walker can't see; DCC packages dump from a fresh headless session. `Check-RuntimeSurface.ps1` orchestrates; runs in the weekly `ClaudeContextBudget` task via `Invoke-ContextBudgetCheck.ps1`. |
| `sync_rpc_core.py [--check]` | drift between `pythontk/net_utils/rpc/plugin_core.py` and the four staged `_rpc_core.py` plugin payloads (mayatk/blendertk × marmoset/substance) | Never hand-edit a staged copy; `pythontk/test/test_sync_rpc_core.py` pins them. |
| `sync_shared_bat.py [--check]` | drift between `m3trik/package-manager.bat` and the committed mirrors in `mayatk`/`blendertk` `env_utils/` | Ships in each wheel beside the thin per-DCC wrapper; pinned by `m3trik/test/test_sync_shared_bat.py`. |

## Rules

- One-shot maintenance scripts go here. Reusable logic belongs in [pythontk](../../pythontk/CLAUDE.md) instead.
- These are maintenance CLIs — exempt from the root encapsulation rule (flat `def`s + `main()` are fine); tests live in `m3trik/test/`.
- New gate ⇒ wire it into the workflow or weekly task that owns it, and name it in the standard it enforces.
