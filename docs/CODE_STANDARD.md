# Code standard — the rules behind the root one-liners

The root [`CLAUDE.md`](../../CLAUDE.md) states every cross-repo rule in one line because it is paid for on every query. This page is the long form: the rationale, the worked shape of each rule, and the rules that are needed less often (formatter, docstrings, deprecation, vendoring, performance, repo hygiene, dead code, scratch files). Read it before a refactor, a new module, or a public-API change. Package-specific rules stay in each package's `CLAUDE.md`.

**Nav**: [← m3trik](../CLAUDE.md) · [Docs standard](DOCS_STANDARD.md) · [Context budget](CONTEXT_BUDGET.md) · [Test badge standard](TEST_BADGE_STANDARD.md)

## 1. Formatter and lint — `ruff`

One tool for both: `ruff format` (black-compatible, 88 columns — the codebase's de-facto style: two thirds of the tree is already clean at 88, and 100/120 make it *worse*) and `ruff check` with the default rule set (`E4`, `E7`, `E9`, `F`). Each ecosystem package carries the same block in its `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py39"          # blendertk: "py310"

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
ignore = ["E402"]                 # house pattern: try-guarded DCC imports precede other imports

[tool.ruff.lint.per-file-ignores]
"**/templates/**" = ["F821"]      # exec-templates carry __PLACEHOLDER__ tokens substituted at run time
```

- `E402` is off because the DCC layers deliberately guard `import maya.cmds` in a `try:` block at the top of the module (§4) and import `pythontk` after it.
- `**/templates/**` is exempt from undefined-name checks because those files are *not* importable modules: they are handed to a host interpreter (Toolbag, Blender, Maya) after token substitution. This mirrors what `mayatk/test/test_static_analysis.py` already excludes.
- **Interim rule until the CI gate is wired**: run `ruff check` on the files you touch and fix what you introduced; `ruff format` new files, and existing files only when you are already rewriting most of them — never a drive-by reformat (it buries the real change and invites merge conflicts with concurrent work). The one-time whole-tree reformat and the CI gate are a tree-idle pass per repo, tracked in `.claude/BACKLOG.md`.

## 2. Docstrings and type hints

House layout is Google-style sections with `Parameters:` (not `Args:`), `Returns:`, `Raises:`, `Yields:`; one-line summary first, blank line, then detail:

```python
def leaf_name(node: str, strip_namespace: bool = True) -> str:
    """Return the last path component of a node name.

    Parameters:
        node: Long or short DAG path.
        strip_namespace: Drop a `ns:` prefix from the result.

    Returns:
        The leaf name.
    """
```

Type-hint public signatures (essential for OpenMaya interop and for the API registry, which prints them). Private helpers may skip hints when the types are obvious.

## 3. Naming and layout

- `class MyClass` → `my_class.py` (PEP 8). **Grandfathered**: `uitk/widgets/*.py` module names are camelCase (`pushButton.py`) because `.ui` files across the ecosystem reference them as custom-widget headers — frozen public API, never renamed.
- A `*_utils` package is `<x>_utils/_<x>_utils.py` holding the `<X>Utils` class (plus its `_<X>UtilsInternal` helper base), with sibling feature modules named `snake_case.py` after the feature (`edit_utils/mirror.py`, `env_utils/usd.py`) — **never a nested `*_utils` name** (`env_utils/usd_utils.py`): the suffix means "package root", and a second level of it hides which class owns the surface.
- A `_`-prefixed module is internal to its package (kept out of Slots/UI discovery, never imported by another package). Public names reach the root via `DEFAULT_INCLUDE`; the wildcard-exposed `*_utils` roots are the *sole* flat form.
- Slots classes are `<Base>Slots` in the same module as the tool they drive; the loader tries `<Base>Slots` before `<Base>`.

## 4. Encapsulation and imports

**Encapsulate.** Logic lives on classes; callers use the class namespace (`mtk.CoreUtils.short_name`), never a hand-written flat `pkg.fn` wrapper. Helpers go on a `_<Class>Internal` base (gold standard: `mayatk/core_utils/_core_utils.py`). One-shots are `@classmethod`s. When a module-level function moves into a class, expose **only the class** in `DEFAULT_INCLUDE` — a dotted `"Workspace.parse_x"` entry just recreates the flat surface. Name collisions are solved (rename, internal helper class), never used as an excuse to keep a module-level function.
*Scope*: the six ecosystem Python packages (`pythontk uitk mayatk blendertk unitytk extapps`; tentacle is Slots classes only). *Exempt*: `m3trik/scripts` (maintenance CLIs), exec-templates, `plugin_src/`, addon hooks, `__getattr__`/decorators, bootstrap.

**Imports have no side effects.** Subpackage `__init__.py` is docstring-only and the root registers names via `DEFAULT_INCLUDE` + `bootstrap_package` — except where the subpackage is itself a bootstrap/entry-point root (each `extapps/<tool>/__init__.py` carries its own `DEFAULT_INCLUDE` because the tool is discovered by entry point). unitytk uses an explicit `__all__` — same contract, no bootstrap.

**DCC runtimes — two deliberate policies, one per mirror.**
- `mayatk`: `import maya.cmds as cmds` (and `maya.mel`, `maya.api.OpenMaya as om`) at module top inside `try: … except: cmds = mel = om = None` — the overwhelming majority of modules. mayapy is always present where mayatk runs, and the guard lets the API registry, docs tooling and mock tests import the module surface without Maya.
- `blendertk`: `import bpy` **deferred into call bodies**, and Qt-only `uitk` imports deferred into the Slots methods that use them — headless `blender --background` ships no Qt, and the package surface must resolve without a running Blender.
- **No PyMEL** anywhere (`maya.cmds` / `maya.mel` only): `import pymel.core` at module top blocks Maya's UI for minutes during init.

## 5. Public-API contract and deprecation

Public APIs are contracts; `blendertk` mirrors `mayatk`'s at the name + behavior level so the tentacle slots stay branch-free. When a public name must be renamed, moved or removed:

1. Keep the old name working as an **alias for one release** (a module attribute, a `@classmethod` shim, or a `LEGACY_ALIASES` map — the unitytk fixture precedent), pointing at the new home.
2. Add a `CHANGELOG.md` line naming both; `API_CHANGES.md` records the delta automatically.
3. Bump **minor**; remove the alias in the release after.

Registry ownership: regenerate the **full** set (`python m3trik/scripts/generate_api_registry.py`) before committing a public-API change so `API_CHANGES.md` and `API_SHADOWS.md` are right at review; after publish the CI bot's refresh is authoritative — take theirs on any conflict rather than fighting it commit by commit.

## 6. Vendored copies — the one sanctioned duplicate

"Unify over duplicate" has exactly one exception: a copy vendored across layers that **cannot import each other** (mayatk ↔ blendertk; a DCC engine ↔ the extapps panel that also needs it; an in-app plugin folder where no `pythontk` is importable). Rules:

- The copies are **byte-identical** (or token-identical where DCC names differ) and **drift-guarded** by a test or a `--check` script that CI runs — `extapps/test/test_vendor_sync.py` (Marmoset engine ×3, Substance, curtain-drape ×2), `sync_rpc_core.py --check` (`_rpc_core.py` ×4), `sync_shared_bat.py --check` (`package-manager.bat` ×2).
- The SSoT is named in the copy's header, and only the SSoT is hand-edited.
- Extract the general primitive to `pythontk` first (`geo_utils.RailSurface` stayed; only `CurtainDrape` was vendored) — a growing vendored file means a primitive is missing upstream.

## 7. Performance — DCC layers

- Batch the command API: one `cmds.ls`/`cmds.getAttr` over a list beats one call per item; never `cmds.objExists`/`cmds.ls` inside a per-node loop when a set lookup does.
- Heavy geometry (per-vertex/face work) goes through `maya.api.OpenMaya` iterators / `bmesh`, not `cmds` per component.
- Suspend viewport refresh around bulk edits (`cmds.refresh(suspend=True)`; tentacle already does for heavy scenes) and undo-chunk long operations.
- Resolve app paths and installs once — an `ptk.AppSpec` per bridge, cached (`<Bridge>.APP.available` for the gate, `resolve()` only on the launch path).
- Prefer a native operator over a re-implemented mayatk algorithm in blendertk (`bpy.ops` / `bmesh.ops` ship the capability as one call).

## 8. Logging and errors

Classes that report use `ptk.LoggingMixin` (`self.logger`, `log_level=` in `__init__`, sinks/DCC handlers configured centrally) — no import-time `StreamHandler`s. Errors **raise**; `print` is for worker scripts, exec-templates and CLI entry points only. A refusal to act (unsupported input, unsafe operation) is a named warning plus a skipped result, not a silent pass.

## 9. Tests

- Issue-driven TDD (root): reproduce in `test/temp_tests/`, write the failing test in `test/test_<module>.py`, fix, verify; the test stays. One test file per module.
- **After any behavior change, run the package's runner** (`test/run_tests.py`; each `CLAUDE.md` names the DCC-specific form) and report the real result — a `pytest | tail` exit code is `tail`'s. Session safety applies to test runs too: never `--reuse`, never `force_new_instance=False` outside a mock-only unit test that launches nothing.
- Test artifacts go in `test/temp_tests/` and are cleaned in teardown; tests are exempt from the `TempArtifacts` rule (the harness owns teardown, and `check_temp_artifacts.py` skips them). Badge semantics: [TEST_BADGE_STANDARD.md](TEST_BADGE_STANDARD.md).

## 10. Dead code and scratch files

- Dead code is deleted, not commented out: grep-confirm zero callers across the workspace (all layers — a name can be a `.ui` slot or an entry point), then remove. Deleting a public name is a public-API change (§5): registry regen + `CHANGELOG.md` line.
- No scratch files outside the repo: repros live in `test/temp_tests/` (gitignored) and are deleted when done; one-shot reports (audits, plans) are folded into the owning docs/CHANGELOG and archived, per [DOCS_STANDARD.md](DOCS_STANDARD.md).
- Never overwrite a file you have not read this session; anchor edits on exact text — concurrent sessions and the user edit the same trees.

## 11. Public-repo hygiene

Most ecosystem repos are public. Tracked source, tests, docs and instruction files carry **no client names, studio drive layouts, hostnames, LAN IPs or credentials**. Large or client-owned fixtures resolve from an env var (`MAYATK_TEST_ASSETS`, `UNITYTK_TEST_ASSETS`) and env-skip when unset; internal hosts and credential helpers live in the private repos (`server`, `comfyui`) — check `gh repo view <name> --json visibility` before placing them.

## 12. CHANGELOG shape, commits and branches

- `CHANGELOG.md` is the only home for work history: `## <year>` headings, dated bold bullets — `- **YYYY-MM-DD — headline (touched paths).** body` — newest first, no `[Unreleased]` section. Release notes are cut from the lines added since the last release, so lead with the one-sentence headline a user of the package needs; detail after.
- Cascade repos work on `dev`; `main` is release-only and reached through `push.ps1` (never plain `git push`). unitytk and extapps publish from `main` too (their own `publish.yml`, no cascade) — unitytk develops on `dev`, extapps on `main`; the non-package repos (m3trik, server, comfyui, www) work on `main`. Commit your own work before running `push.ps1 -Merge` — it commits the whole tree.
- Never hand-write the release tool's commit messages (`Bump version to X`, `Update dependencies & bump version to X`); the housekeeping classifier keys on them.
