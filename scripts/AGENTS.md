# m3trik/scripts

**Role**: Repo-maintenance scripts: gates, generators, sync tools. Each script's docstring (or `-h`) is the SSoT for its behaviour; this table is the map.

**Nav**: [← parent](../AGENTS.md) · [← root](../../AGENTS.md) · standards: [CODE_STANDARD](../docs/CODE_STANDARD.md) · [DOCS_STANDARD](../docs/DOCS_STANDARD.md) · [CONTEXT_BUDGET](../docs/CONTEXT_BUDGET.md)

**Everyday**: `affected_tests.py <files> [--run]` — the tests a change reaches, run headless one package at a time (CODE_STANDARD §9). `ledger_drift.py check` — ledger entries whose named code moved.

## Generators (fix the generator, never the output)

| Script | Emits | Notes |
|:--|:--|:--|
| `compare_panel_surface.py --all --write` / `--panel <n>`; `generate_parity_audit.py` | `tentacle/docs/PARITY_SURFACE.md`, `PARITY_AUDIT.md` | Every `self.tk` chain resolves on both hosts, else hidden/guarded; gap ⇒ exit 1. |
| `generate_workspace_inventory.py` (+ `Generate-WorkspaceInventory.ps1`) | `docs/workspace_repo_inventory.{md,json}` | Direct child repos: package/code roots, tracked LOC. |
| `build_stingray_ao_presets.py [--check]` | `mayatk/mat_utils/shaderfx/Standard_{Masked,Transparent}_AO.sfx` | Maya's opacity presets + the opaque preset's AO chain, spliced as text (ShaderFX has no `saveGraph`). `--check` = drift gate. Tested. |

## Gates (exit 0 or the build is red)

| Script | Fails on | Notes |
|:--|:--|:--|
| `check_context_budget.py` | `MEMORY.md` byte/entry caps + coverage, `AGENTS.md` sizes, broken instruction links, root dispatch ≠ `workspace.json`, Nav `Deps:` lagging pyproject | `--no-runtime` skips the pythontk live-surface spot check (the DCC half is `Check-RuntimeSurface.ps1`). |
| `check_docs.py --workspace <dir>` / `--root <pkg>` | broken relative links/anchors, orphan hand-written md, UNTRIAGED DOCMAP coverage | CHANGELOGs, vendored/`archive/`/generated files exempt; `--root` runs the DOCMAP ledger suite (uitk). |
| `check_english_only.py [repo…]` | a non-Latin letter or a Greek word in any repo's text/paths | Lone Greek letter = notation; generated/vendored exempt. |
| `check_doc_line_refs.py --root <repo>` | `.py#L<line>` refs to a missing file / out-of-range line | `--exclude <glob>` skips a doc. |
| `check_public_hygiene.py [repo…]` | a client identifier in anything `git add -A` would publish from a public repo (paths, text, CHANGELOGs) | Denylist is PRIVATE (`<workspace>/.claude/public_hygiene.txt`; absent → SKIP); `push.ps1` runs it pre-release. Never copy a pattern into a repo, test, commit or PR. |
| `check_temp_artifacts.py` | production code allocating temp outside `ptk.TempArtifacts` (`mkstemp`, `mkdtemp`, a kept `NamedTemporaryFile`) or naming it outside pythontk (`gettempdir()`, `TEMP` reads); unparsable files; stale allowlist entries; stray package files | Self-cleaning forms and tests pass; `ALLOWLIST` entries carry a reason. Rules: §10. |
| `check_tooltips.py --workspace` | a tooltip Qt would eat (bare `<`); a reset control off `ResetGesture` | Renders, then parses. |
| `check_ui_spacers.py [--root] [--max-gap]` | a `Fixed` vertical spacer taller than the panels' ~10 px gap (Designer's 20×40 default ships dead space) | Sweeps the four UI repos; tentacle also pins it (`test_ui_integrity.py`). |
| `check_api_surface.py [pkg…] --check` | a retirement past its window | Source only (`ApiSurface.read`). `--semver` (push.ps1's gate) / `--changes`: the delta since the newest `v*` tag (`--since REF`); `--shadows`: cross-package names. |
| `verify_runtime_surface.py verify <pkg>` / `dump` | a member the source declares that the live class (`ApiSurface.members` over each `HelpMixin` class) lacks | Catches metaclass/mixin injection the static read (`ApiSurface.read`) misses; DCC packages dump from a fresh headless session via `Check-RuntimeSurface.ps1` (weekly, `Invoke-ContextBudgetCheck.ps1`). |
| `sync_rpc_core.py [--check]` | drift between `pythontk/net_utils/rpc/plugin_core.py` and the four staged `_rpc_core.py` plugin payloads (mayatk/blendertk × marmoset/substance) | Never hand-edit a staged copy. Tested. |
| `sync_shadow_shaders.py [--check]` | drift between `pythontk/geo_utils/shadow_horizon.glsl` and its two generated mirrors (`shadow_rig.js`, `unitytk` `ShadowPlaneHorizon.hlsl`) | **Marker**-spliced: each mirror keeps its own prologue outside the region. Maya/Blender assemble via `ShadowHorizon.shader_source`. |
| `sync_shared_bat.py [--check]` | drift between `m3trik/package-manager.bat` and the committed mirrors in `mayatk`/`blendertk` `env_utils/` | Ships in each wheel beside the thin per-DCC wrapper. Tested. |
| `sync_scene_records.py [--check]` | `ptk.SceneRecords` vs doc table, Unity channels + versions, both PRODUCERS; emits `records.js`, `*.g.cs` | Tested. |
| `sync_operation_contract.py [--check]` | drift between pythontk's operation payloads and unitytk's generated `Kernel/Core/*.g.cs` | |
| `sync_workspace.py [--check]` | `../workspace.json` vs root Dispatch, CI loops, charters; instruction tree + packs; `operations.json` | §0. |
| `sync_github_about.py [--check]` / `--apply` | a repo's GitHub About (description, topics, PyPI homepage) vs its pyproject | `--apply` needs your `gh` login. |
| `check_layers.py [--check]` / `--update` | undeclared ecosystem import; import up `[tool.m3trik.layers]`; a product or `roles`-forbidden import | Layers baselined. |
| `check_dcc_twins.py [--written-once]` | a ledgered twin drifting; an 8+-line body written twice | |
| `check_saved_names.py` / `--update` | a frozen `.ui` stem, widget or record name gone | §5 |
| `check_version_bump.py <pkg> --published <v>` | an off-chain push to `main` shipping changes unversioned | |
| `check_js_types.py` | `tsc --checkJs` errors in `PROJECTS` | No compiler = exit 2. |

## Rules

- One-shot maintenance scripts go here. Reusable logic belongs in [pythontk](../../pythontk/AGENTS.md) instead.
- Maintenance CLIs: flat `def`s + `main()` are fine (encapsulation-exempt); tests live in `m3trik/test/`.
- New gate ⇒ wire it into the workflow or weekly task that owns it, and name it in the standard it enforces.
