# m3trik/scripts

**Role**: Repo-maintenance scripts: gates, generators, sync tools. Each script's docstring (or `-h`) is the SSoT for its behaviour; this table is the map.

**Nav**: [← parent](../AGENTS.md) · [← root](../../AGENTS.md) · standards: [CODE_STANDARD](../docs/CODE_STANDARD.md) · [DOCS_STANDARD](../docs/DOCS_STANDARD.md) · [CONTEXT_BUDGET](../docs/CONTEXT_BUDGET.md)

**Everyday**: `affected_tests.py <files> [--run]` — the tests a change reaches, run headless one package at a time (CODE_STANDARD §9). `ledger_drift.py check` — ledger entries whose named code moved.

## Generators (fix the generator, never the output)

| Script | Emits | Notes |
|:--|:--|:--|
| `compare_panel_surface.py --all --write` / `--panel <n>`; `generate_parity_audit.py` | `tentacle/docs/PARITY_SURFACE.md`, `PARITY_AUDIT.md` | Every `self.tk` chain resolves on both hosts; gap ⇒ exit 1. |
| `generate_workspace_inventory.py` (+ `Generate-WorkspaceInventory.ps1`) | `docs/workspace_repo_inventory.{md,json}` | Child repos: package/code roots, LOC. |
| `sync_unity_samples.py [--check]` | unitytk `Samples~/`, `samples` | Recipes: `unity_samples/`. Maya: local, `push.ps1`. |
| `generate_readme_diagrams.py [--check] [--prune]` | `docs/diagrams/`, README `diagram:` blocks | |
| `build_stingray_ao_presets.py [--check]` | `mayatk/mat_utils/shaderfx/Standard_{Masked,Transparent}_AO.sfx` | Maya's opacity presets + the opaque AO chain, spliced. |
| `scaffold_unity_part.py <kind> <name>` | a unitytk part: folders, asmdefs, `.meta`s, a failing test | One-off; refuses to overwrite. |
| `setup_workspace.py [--apply]` | the workspace around a clone of m3trik: the other repos, the `.venv`, the root's instruction files | Plans by default; leaves what exists as it is. |

## Gates (exit 0 or the build is red)

| Script | Fails on | Notes |
|:--|:--|:--|
| `check_context_budget.py` | `MEMORY.md` byte/entry caps + coverage, `AGENTS.md` sizes, broken instruction links, root dispatch ≠ `workspace.json`, Nav `Deps:` lagging pyproject | `--no-runtime` skips the live check. |
| `check_docs.py --workspace <dir>` / `--root <pkg>` | broken relative links/anchors, orphan hand-written md, UNTRIAGED DOCMAP coverage | CHANGELOGs, vendored, `archive/`, generated exempt; `--root`: DOCMAP ledger suite. |
| `check_english_only.py [repo…]` | a non-Latin letter or a Greek word in any repo's text/paths | Lone Greek letter = notation; generated/vendored exempt. |
| `check_doc_line_refs.py --root <repo>` | `.py#L<line>` refs to a missing file / out-of-range line | `--exclude <glob>` skips a doc. |
| `check_public_hygiene.py [repo…]` | a client identifier in anything a public repo would publish; a user-home or machine path inside a `Samples~/` binary | Denylist is PRIVATE (`<workspace>/.claude/public_hygiene.txt`); never copy a pattern. |
| `check_temp_artifacts.py` | production temp outside `ptk.TempArtifacts` (`mkstemp`, `mkdtemp`, a kept `NamedTemporaryFile`, `gettempdir()`, `TEMP`); stale allowlist entries; stray package files | Self-cleaning forms and tests pass. §10. |
| `check_tooltips.py --workspace` | a tooltip Qt would eat (bare `<`); a reset control off `ResetGesture` | Renders, then parses. |
| `check_ui_spacers.py [--root] [--max-gap]` | a `Fixed` vertical spacer taller than the panels' ~10 px gap | Sweeps the UI repos; tentacle pins it. |
| `check_api_surface.py [pkg…] --check` | a retirement past its window | `--semver` (push.ps1; exit 1 if HELD) / `--changes`: the delta since the last `v*` tag (`--since REF`); `--shadows`: cross-package names; `--floors`: standalone floors carry what they use. |
| `verify_runtime_surface.py verify <pkg>` / `dump` | a member the source declares that the live class lacks | Catches mixin injection `ApiSurface.read` misses; DCC packages: `Check-RuntimeSurface.ps1` (weekly). |
| `sync_rpc_core.py [--check]` | drift between `pythontk/net_utils/rpc/plugin_core.py` and its staged `_rpc_core.py` plugin copies | Never hand-edit a staged copy. |
| `sync_shadow_shaders.py [--check]` | drift between `pythontk/geo_utils/shadow_horizon.glsl` and its generated mirrors (`shadow_rig.js`, `unitytk` `ShadowPlaneHorizon.hlsl`) | Marker-spliced; each keeps its prologue. |
| `sync_shared_bat.py [--check]` | drift between `m3trik/package-manager.bat` and its mirrors in `mayatk`/`blendertk` `env_utils/` | In each wheel. |
| `sync_scene_records.py [--check]` | `ptk.SceneRecords` vs doc table, Unity channels + versions, both PRODUCERS; emits `records.js`, `*.g.cs` | |
| `sync_operation_contract.py [--check]` | drift between pythontk's operation payloads and unitytk's core `*.g.cs` | |
| `sync_job_queue.py [--check]` | drift between pythontk's `JobQueue` layout and extapps' Unity Scripts `QueueLayout.g.cs` | |
| `sync_workspace.py [--check]` | `../workspace.json` vs the Dispatch table, CI loops, charters; the workspace root's files vs their build from `../agents/workspace.md`; instruction tree + packs; `operations.json`; the stated dependency chain; the `m3trik` distribution's package set | §0. Builds the root; a lone clone writes nothing outside itself. |
| `sync_github_about.py [--check]` / `--apply` | a repo's GitHub About (description, topics, PyPI homepage) vs its pyproject | `--apply` needs a `gh` login. |
| `check_layers.py [--check]` / `--update` | undeclared ecosystem import; import up `[tool.m3trik.layers]`; a product or `roles`-forbidden import; an asmdef reference against its `csharp` order (C# without it fails); a name above it or in `[tool.m3trik.names] forbid` | Baselined. |
| `check_csharp.py [--check]` / `--update` | editor code bypassing the `kernel` (`Undo`, progress bars, `Debug.Log`); an assembly with no `Prior art:`; a `*.g.cs` its generator did not write | `*.g.cs`: strict. |
| `check_dcc_twins.py [--written-once]` | a ledgered twin drifting; an 8+-line body written twice | |
| `check_saved_names.py` / `--update` | a frozen `.ui` stem, widget or record name gone | §5 |
| `check_version_bump.py <pkg> --published <v>` | an off-chain push to `main` shipping changes unversioned | |
| `check_js_types.py` | `tsc --checkJs` errors in `PROJECTS` | No compiler = exit 2. |

## Release

| Script | Does | Notes |
|:--|:--|:--|
| `Invoke-RunnerRelease.ps1` | the release runner's run: sync, m3trik main ⇐ dev, preflight, the receipts `push.ps1 -GateReport` says are owed (review pinned to a sha; full suites), release | Dedicated workspace only; [RELEASE_RUNNER](../docs/RELEASE_RUNNER.md). |
| `Install-ReleaseRunner.ps1` | once, on the Maya machine: private repo, workflow, runner, logon task | `-Uninstall`. |

## Rules

- One-shot maintenance scripts go here; reusable logic in [pythontk](../../pythontk/AGENTS.md).
- Maintenance CLIs: flat `def`s + `main()` are fine (encapsulation-exempt); tests live in `m3trik/tests/`.
- New gate ⇒ wire it into the workflow or weekly task that owns it, and name it in the standard it enforces.
