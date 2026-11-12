# Monorepo Instructions

Written in [`m3trik/agents/workspace.md`](workspace.md); the workspace root's `AGENTS.md` is its render (`sync_workspace.py`), never edited.

Interdependent packages. Before touching a sub-repo, read its `AGENTS.md`. The rules every repo shares are the packs (sources: [`m3trik/agents/packs/`](packs/)); this file adds the workspace's. Rationale and rarer rules: [`m3trik/docs/CODE_STANDARD.md`](../docs/CODE_STANDARD.md) — read it before a refactor, a new module or tool, or a public-API change. A rule change updates its pack or this file's source and CODE_STANDARD together, plus the [`m3trik/README.md`](../README.md) pitch where it describes the rule, then `python m3trik/scripts/sync_workspace.py`. Agent tooling (packs, operations, MCP, the plugin), set up and used: [`AGENT_INSTRUCTIONS.md`](../docs/AGENT_INSTRUCTIONS.md).

## Dispatch

| Unit | Domain |
|:---|:---|
| [`pythontk/`](../../pythontk/AGENTS.md) | Core utils — DCC-agnostic, zero-dep |
| [`uitk/`](../../uitk/AGENTS.md) | Generic Qt UI library; no DCC/app logic |
| [`mayatk/`](../../mayatk/AGENTS.md) | Maya 2025+ host library; each tool's Maya API half |
| [`blendertk/`](../../blendertk/AGENTS.md) | Blender 4.x+ host library, mirrors mayatk; each tool's Blender API half |
| [`tentacle/`](../../tentacle/AGENTS.md) | The product: the launcher, every tool's panel and Slots class |
| [`unitytk/`](../../unitytk/AGENTS.md) | Unity integration |
| [`server/`](../../server/AGENTS.md) | Linux infra, zero-trust secrets |
| [`m3trik/`](../AGENTS.md) | PowerShell DevOps, release automation |
| [`m3trik/scripts/`](../scripts/AGENTS.md) | Python maintenance scripts |
| [`comfyui/`](../../comfyui/AGENTS.md) | ComfyUI custom nodes |
| [`extapps/`](../../extapps/AGENTS.md) | Standalone apps: each host-free app's engine, panel and Slots class |
| [`www/`](../../www/AGENTS.md) | Web |
| [`androidtk/`](../../androidtk/AGENTS.md) | Android device toolkit (satellite) |

## Ecosystem chain
`pythontk → uitk → {mayatk, blendertk} → tentacle`; also `pythontk → unitytk`, `uitk → extapps`. Each tool's API half is mayatk/blendertk; truly reusable logic both hosts share is pythontk (generic Qt: uitk); tentacle holds only the launcher, the UIs and the Slots classes (§14). **Two products, never imported**: a tool with a host half, or that needs a DCC to run, is tentacle's; a host-free app (engine + panel + Slots) is extapps', on pythontk + uitk alone, opened by name from tentacle's menus (host behaviour injected, never imported). A contract sits where every reader reaches it (`SceneRecords`: pythontk). A moved public name's row is `MOVED_NAMES` (alias: `ptk.Deprecation`); breaking changes cascade upward. `blendertk` mirrors `mayatk` by name + behavior (signature too where a shared panel calls it). **Release cascade** `pythontk uitk mayatk blendertk tentacle` (`push.ps1`); **ecosystem set** `ECOSYSTEM_PACKAGES` = cascade + `unitytk extapps` (standalone `publish.yml` on `main`).
**Licenses**: pythontk MIT; mayatk MIT + Commons Clause; blendertk, tentacle GPL-3.0+; uitk, extapps, unitytk LGPL-3.0+. Code that runs in Blender stays GPL-compatible: never import mayatk there; unitytk's Unity package (`com.m3trik.unitytk/`) stays MIT (player builds).

## API surface — read live, never committed
`api.search` finds a public symbol, `api.describe` reads one. Delta since release, semver verdict, collisions: [`check_api_surface.py`](../scripts/check_api_surface.py) (`--check`, retirement windows, is the CI gate).

## Operations — run, don't script
`python -m pythontk ops list|search|describe|run|apply` (`maya.*`, `blender.*` in an instance the tooling owns, kept per MCP session; `--scene` opens a file): `run` plans, `apply` changes; MCP: the plugin's `ops`/`ops-apply`. A library function: `api.search`, then code in `<host>.python.exec`, never wrapped as an operation (Unity's C# too, through `unity.csharp.exec`). Declare only what code cannot reach: a host's exec and view (Unity's kernel adds its doctor, in C#) and the tooling's own, in `operations.py`.

## Release
Cascade packages: `m3trik/push.ps1` only — never plain `git push`; it owns the `Release X.Y.Z` commit, PR-gated merge, tag and GitHub Release, and a re-run finishes an aborted one. Everything else: standard git flow. Flags + receipts gate: [m3trik/AGENTS.md](../AGENTS.md).

## Session safety (DCC apps) — hard rule
The [principles](packs/principles.md) rule for the tooling (bridges: §15), made concrete: an instance the tooling owns is one whose PID and marker it logged, reused only after reloading changed code (Maya: the changed modules); `run_tests.py --reuse` and MCP sessions reuse only those (`ptk.SessionOperationHost`). **Forbidden**: `force_new_instance=False` (except mock-only tests) and attaching to the command port of an instance the tooling did not launch: both reach a person's; real OS input (mouse, keys, focus) while any DCC you did not launch is open (list processes first; probe via Qt or the command API); closing a DCC whose PID your run did not log. Enforcement: [mayatk/AGENTS.md](../../mayatk/AGENTS.md).

## Workspace specifics
- **A tool's UI**: tentacle `ui/tools/<tool>.ui` + one Slots class `slots/tools/<tool>.py` (helpers `slots/tools/_<tool>/`) over its API in mayatk/blendertk. Grandfathered: uitk widget module names (`.ui` headers).
- **Encapsulation**: gold standard mayatk `_core_utils`. Sole flat form: the wildcard `*_utils` roots' names, which stay (§4). Exempt: `m3trik/scripts`, exec-templates, `plugin_src/`, addon hooks, bootstrap (§4).
- **Host conventions**: Maya selection in, one undo chunk, option box; Blender operator undo/redo.
- **Export**: a lookdev aid composes over the authored value; it never duplicates, reassigns, renames or swaps what the exporter reads. Suspend steps and sidecars are a last resort: first ask whether what they undo should exist (§13).
- **Testing**: reproduce a bug in `test/temp_tests/`, the failing test in `test/test_<module>.py`; the affected tests are `python m3trik/scripts/affected_tests.py <files> --run` (headless); full suites: full reviews and releases (§9).

## Conventions
- **Findings**: one a named blocker stops is logged `ready`. Before applying a reviewer's prescribed fix, grep the backlog for a `decision` entry on that code (the maintainer's call; reviewers never see it). Deferrals go to [`.claude/BACKLOG.md`](../../.claude/BACKLOG.md) (bar and TTL in its header; reviewed ideas: `.claude/FUTURE.md`); delete entries your work resolves; work it with `/m3trik:backlog`.
- **Checked, so stated once**: English only, test data too (`check_english_only.py`); every doc reachable from a hub ([`DOCS_STANDARD.md`](../docs/DOCS_STANDARD.md), `check_docs.py --workspace .`); one home per file lifetime: temp `ptk.TempArtifacts`, cache `UserConfig.cache_dir()`, scene files the scene's `ptk.Workspace` (§10, `check_temp_artifacts.py`); size caps ([`CONTEXT_BUDGET.md`](../docs/CONTEXT_BUDGET.md)); layers and roles (`check_layers.py`); written once and host bindings (`check_dcc_twins.py`); saved names (`check_saved_names.py`); instructions, packs and operation catalogs (`sync_workspace.py --check`); README diagrams (`generate_readme_diagrams.py`).
- **Subagents**: sweeps and first-pass reviews on Sonnet (`m3trik:sweep`; `m3trik:reviewer` with `model: sonnet`), Opus verifying only the credible findings; judgment and code changes on Opus; each release-sized change gets a fresh `reviewer`, briefed with the diff, not your conclusions; re-verify a subagent's S1 before acting on it; agents sharing a tree keep every module importable between edits (§10).
