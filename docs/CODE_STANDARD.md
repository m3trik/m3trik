# Code standard — the rules behind the root one-liners

The root [`CLAUDE.md`](../../CLAUDE.md) states every cross-repo rule in one line because it is paid for on every query. §0 is the shape every unit shares; the rest is the long form: the rationale, the worked shape of each rule, and the rules that are needed less often (formatter, docstrings, deprecation, vendoring, performance, repo hygiene, dead code, scratch files, package architecture). Read it before a refactor, a new module, or a public-API change. Package-specific rules stay in each package's `CLAUDE.md`.

**Nav**: [← m3trik](../CLAUDE.md) · [Docs standard](DOCS_STANDARD.md) · [Context budget](CONTEXT_BUDGET.md) · [Test badge standard](TEST_BADGE_STANDARD.md)

## 0. The shape — one holon at every scale

Every boundary here is a **holon**, a whole to its parts and a part to its whole (Koestler): the workspace, a repo, a subpackage, a module, a class. Each has the same parts and obeys the same rules, so the structure reads the same at every zoom level, a unit moves up or down a scale by being *moved*, never rewritten, and someone working inside one holon cannot drift another, because the only ways across are declared. The sections below are the Python spelling: §3 layout and growth, §4 surface and imports, §5 contracts over time, §6 twins, §14 placement and seams.

Each classic pattern governs one relationship, and the shape assigns it at every scale: to its **parent** a holon is a plugin (it registers through a seam, touched only through its surface); to its **children** a kernel (it owns their seams); among **siblings** a slice in a declared order; **inside** a host-free model under host adapters; to its **twins** in other hosts or languages a contract pinned by generated cases; **over time** a version (tolerant readers, dated removals).

| Part | What it is | The rule, at every scale |
|---|---|---|
| **Charter** | purpose, owner, the secret it hides, what it refuses | One owner, one purpose, one secret. A charter that needs "and" is two holons. Write the refusals down. |
| **Surface** | every name something outside calls **or stores** | Others touch only the surface; curated, domain-named, never leaking layout. It exposes whole parts (a class), never a part's insides flattened into the parent (the wildcard `*_utils` roots are grandfathered). |
| **Model** | host-free logic: plain values in and out | Everything that can be host-free is, and sinks to the lowest holon whose dependencies it needs. |
| **Adapters** | code binding the model to a host (DCC, engine, Qt, disk, network) | Adapters depend on the model, never the reverse. A new host adds adapters (a twin at the same relative path), never an abstraction layer over hosts. |
| **Parts** | child holons in a declared order; the lowest is the **kernel** | Parts depend only downward; peers of one rank never import each other; a shared need sinks to a lower part. The kernel imports nothing above it. |
| **Seams** | registries where parts plug in | A new part lands as an addition plus one declaration. Editing a dispatcher to add a case means a seam is missing: add it first, in its own change. |
| **Contracts** | data and APIs crossing the surface | Declared once, as data, in the lowest holon every reader can reach. Python reads the declaration; other languages get generated types, and every restatement is checked. Versioned: readers tolerate, removal is expand, migrate, contract on a dated window. |
| **Proof** | tests, generated cases, guards | Every rule has a check at the scale it governs; a rule without one is a wish. A port is pinned by cases its reference generates. A new check freezes today's violations and fails only on new ones. |

- **A surface is every name something else depends on**, not only what the code exports: a script GUID in a `.meta`, a serialized field, a menu path, an event, a manifest key, a `.ui` objectName, an attribute on a scene node, a settings key. Most drift is a surface change nobody recognized as one. **Saved data is always published**: scenes, prefabs, GLBs and presets outlive the code, so the names they store get the longest window.
- **The kernel is a role, not a folder name.** A folder named `core_utils` that imports its siblings is not acting as a kernel; declare the tenants that are really the top (pythontk's `core_utils/engines`) at their true rank.
- **Visibility sets the change process.** Private to the holon: change freely. Internal to the repo: one commit with every consumer. Published (another repo, a user script, a deployed project, a saved file): a version, a `ptk.Deprecation` alias with `remove_in` and `since` (§5).
- **Growth** is the §3 triggers at every scale; a subpackage becomes a repo only on a release cadence, toolchain or consumer set its parent cannot serve. A holon that stops earning its boundary merges back.
- **Working independently**: work inside one holon; land a cross-holon contract first, then build each side against it; seam changes and moves are their own commits, announced to concurrent sessions.

**Declared and checked.** [`m3trik/workspace.json`](../workspace.json) declares the cascade and each unit's release mode and domain; `push.ps1` and the generators read it, and `sync_workspace.py --check` holds the root Dispatch table, the CI sibling lists and every unit's charter to it. Membership stays measured (a folder holding `.git` belongs). Each package declares its parts' order in `[tool.m3trik.layers]` of its `pyproject.toml`, and `check_layers.py --check` holds both scales (an ecosystem import must be a declared dependency; imports point down the order -- a served ES module's relative imports too, a `"<folder>/*"` part making each child a peer) against a frozen baseline. A contract other languages read is declared once in Python -- a scene record's payload and web manifest as typed `SchemaSpec`s (`RecordSpec.shape`, `WebProjection`) -- and `sync_scene_records.py --check` holds the generated JavaScript typedefs and C# record types to it; a model ported to another runtime is pinned by the golden cases its reference generates (`ptk.Conformance`); `check_js_types.py` type-checks the JavaScript (`tsc --checkJs`). Where each host spells the anatomy: [the WebXR runtime](../../pythontk/docs/webxr_preview.md#the-runtimes-anatomy), [the Unity package](../../unitytk/unitytk/templates/README.md#extending-the-package-its-anatomy).

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
- **`ruff check` is CI-gated in 5 of 7 repos** (2026-09-16): pythontk and extapps at whole-repo scope (`ruff check .`), uitk / blendertk / unitytk at **package** scope, because their `test/` trees still carry findings (27 / 326 / 29, re-measured 2026-09-17) and gating on `.` would have made the job red on arrival. mayatk (25 in-package, 119 repo-wide) and tentacle (36 in-package, 89 repo-wide) are not gated yet — both are auto-fixable, so the burn-down is `ruff check --fix` plus review in an isolated commit with a `.git-blame-ignore-revs` entry, then widen the gate. The version is pinned (`ruff==0.15.17`): an unpinned ruff turns an upstream rule addition into a red PR nobody changed.
- **Everywhere, gated or not**: run `ruff check` on the files you touch and fix what you introduced; `ruff format` new files, and existing files only when you are already rewriting most of them — never a drive-by reformat (it buries the real change and invites merge conflicts with concurrent work). The one-time whole-tree *format* pass (`ruff format`, a separate question from `check` — 114 files predate the current ruff) stays a tree-idle job per repo, tracked in [`.claude/FUTURE.md`](../../.claude/FUTURE.md) — not `BACKLOG.md`, whose bar drops S3 hygiene work, which is why the entry cycled into the archive twice before landing there.

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

Which type for which need -- the Python spelling of a toolbox each host spells its own way ([the WebXR runtime](../../pythontk/docs/webxr_preview.md#the-runtimes-anatomy), [the Unity package](../../unitytk/unitytk/templates/README.md#extending-the-package-its-anatomy)):

| Need | Python (3.9 floor) |
|:---|:---|
| value object | `@dataclass(frozen=True)` |
| vocabulary | `class X(str, Enum)`; `Literal[...]` |
| JSON payload shape | a typed `ptk.SchemaSpec` (`TYPED = True`): it validates a payload and publishes the JSON Schema other languages' types are generated from (§0, Contracts) |
| structural contract | `typing.Protocol` |
| distinct ids | `NewType("NodeIndex", int)` |
| variants | subclasses plus a strategy table |
| identity in saved data | a stable name -- published the moment a file stores it (§5) |

## 3. Naming and layout

- `class MyClass` → `my_class.py` (PEP 8). **Grandfathered**: `uitk/widgets/*.py` module names are camelCase (`pushButton.py`) because `.ui` files across the ecosystem reference them as custom-widget headers — frozen public API, never renamed.
- A `*_utils` package is `<x>_utils/_<x>_utils.py` holding the `<X>Utils` class (plus its `_<X>UtilsInternal` helper base), with sibling feature modules named `snake_case.py` after the feature (`edit_utils/mirror.py`, `env_utils/usd.py`) — **never a nested `*_utils` name** (`env_utils/usd_utils.py`): the suffix means "package root", and a second level of it hides which class owns the surface.
- A `_`-prefixed module is internal to its package (kept out of Slots/UI discovery, never imported by another package). Public names reach the root via `DEFAULT_INCLUDE`; the wildcard-exposed `*_utils` roots are the *sole* flat form.
- **A feature earns a subpackage; it never starts in one.** Every feature starts as one module (`feature.py`: one public class plus its `_<Class>Internal` base) and is promoted to a `<feature>/` subpackage as soon as any of these holds:
  1. **A second cohesive module arrives**: one that changes with the first and means nothing without it (a store and the library built on it; an engine and its slots; a reader / writer / pipeline set). Cohesion is the test, not the count: two unrelated modules that happen to share a prefix stay flat.
  2. **It needs private internals**: helper modules (`_sidecar.py`, `_task_scene.py`) that nothing outside the feature may import.
  3. **It owns an asset directory** it alone consumes (`presets/`, `templates/`, `scripts/`, shaders). One `<tool>.ui` beside `<tool>.py` is *not* a trigger: that pair is the small-tool shape.
  4. **Three or more siblings share a concept prefix** their neighbours don't (`glb_*` among `mesh_convert`'s FBX modules, now `mesh_convert/glb/`): the prefix is a namespace spelled into file names because the folder was never made. The parent domain's own name (`mat_*` in `mat_utils/`) and the host's (`maya_*`) are not concept prefixes, and neither is a prefix on the parts of one class (`scene_exporter/_task_*`: the phase mixins `TaskManager` is built from).
  5. **A god module**: past ~1,500 lines *and* doing more than one job. Split along the jobs (model / IO / algorithm / presentation) behind the same facade class; a long module with one job is not a trigger, and a tool's engine plus its own Slots class counts as one job (the flat-tool shape, `light_utils/hdr_manager.py`). On a wildcard-exposed `*Utils` root, keep each public method's signature and docstring on the facade and move only its body into `_<feature>.py` (`UvUtils.pack_uvs` returns `_uv_pack._UvPackInternal.run(...)`): the resolver registers flat names from the class's own body, so a method moved onto a mixin base silently drops out of `mtk.<method>`.

  The motivating case: `pythontk/core_utils/` reached 41 flat modules, so `preset_library.py` landed as one more sibling of `preset_store.py`, the store it is built on, and the family was invisible in a listing (now `core_utils/presets/`). **Not warranted**: a subpackage whose only content is `_<x>.py` (a path level with nothing behind it); the `*_utils` domain roots and `core_utils/engines/<system>/` tenants are charter namespaces and exempt. Prefer wide and cohesive to deep: every level is typed again in each import and `DEFAULT_INCLUDE` key.
- **Subpackage shape**: mirror the layout of the existing ones (`file_utils/mesh_convert/`, `engines/textures/map_factory/`, mayatk `anim_utils/smart_bake/`). `__init__.py` is a docstring, plus one `lazy_exports` call when the subpackage publishes names (§4). `_<feature>.py` holds the facade / orchestrator class, so the public name survives the promotion unchanged. Siblings are named for the concept they hold (`glb/reader.py`, `fbx_media.py`), never for a role (`utils.py`, `helpers.py`, `common.py`, `misc.py`): a role name accepts anything, so it becomes the grab-bag. The folder is named for the domain noun. A DCC tool subpackage is `_<tool>.py` (engine, no Qt) + `<tool>_slots.py` + `<tool>.ui` (+ `presets/` when it ships any), and its twin sits at the **same relative path** in the other DCC package, so parity tooling, drift guards and reviewers pair them by path ([`blendertk/docs/STRUCTURE.md`](../../blendertk/docs/STRUCTURE.md) is the correspondence map; update it with every add, move or rename). Where the twin has only one module to put there, it stays flat (a one-module subpackage is not warranted) and `STRUCTURE.md` records the exception. Layouts that predate these rules (`lightmap_baker/lightmap_baker.py` without the `_`) stay until a real change touches them: never a churn-only rename. Moving or promoting a module: §14.
- Slots classes are `<Base>Slots` in the same module as the tool they drive (a tool subpackage keeps them in `<tool>_slots.py`, beside the engine); the loader tries `<Base>Slots` before `<Base>`.

## 4. Encapsulation and imports

**Encapsulate.** Logic lives on classes; callers use the class namespace (`mtk.CoreUtils.short_name`), never a hand-written flat `pkg.fn` wrapper. Helpers go on a `_<Class>Internal` base (gold standard: `mayatk/core_utils/_core_utils.py`). One-shots are `@classmethod`s. When a module-level function moves into a class, expose **only the class** in `DEFAULT_INCLUDE` — a dotted `"Workspace.parse_x"` entry just recreates the flat surface. Name collisions are solved (rename, internal helper class), never used as an excuse to keep a module-level function.
*Scope*: the six ecosystem Python packages (`pythontk uitk mayatk blendertk unitytk extapps`; tentacle is Slots classes only). *Exempt*: `m3trik/scripts` (maintenance CLIs), exec-templates, `plugin_src/`, addon hooks, `__getattr__`/decorators, bootstrap.

**Load lazily unless there is a reason not to; imports have no side effects.** A package `__init__` declares its names and imports none of them: the root through `DEFAULT_INCLUDE` + `bootstrap_package`, a subpackage through `lazy_exports(globals(), {submodule: names})` (both in `pythontk.core_utils.module_resolver`), or a docstring alone when the root registers everything. A parent's `bootstrap_package` scan imports every subpackage `__init__`, so an eager re-export there is paid by every `import <root>` in the ecosystem, and a hand-written PEP 562 loader is a copy of `lazy_exports`. Inside a module the same holds for a heavy or optional dependency that one path uses: import it in that path. An eager import states its reason in a comment (a registration that must run at import, a base class needed at definition time, an import cycle). Exempt: a subpackage that is itself a bootstrap/entry-point root (each `extapps/<tool>/__init__.py` carries its own `DEFAULT_INCLUDE` because the tool is discovered by entry point) and the in-app `plugin_src/` packages. unitytk uses an explicit `__all__` — same contract, no bootstrap.

**Import other packages through their root.** Across a package boundary use the root name (`ptk.StrUtils`, `from pythontk import StrUtils`), never a `_`-prefixed module (§3), and prefer it to any module path. The root is the contract; the module path is layout, and layout has to stay free to change: promoting a module into a subpackage stays inside its package (a `DEFAULT_INCLUDE` key plus in-package imports) only while no other package imports its old path. A deep import of a *public* module is tolerated where the root cannot serve (a name the root deliberately leaves unregistered, an import cycle at bootstrap), and it turns that path into a contract a later move must alias (§14). Exempt: the bootstrap import (`pythontk.core_utils.module_resolver`), exec-templates, and the frozen uitk widget paths that `.ui` headers name (§3). Inside a package, import whatever is clearest.

**DCC runtimes — two deliberate policies, one per mirror.**
- `mayatk`: `import maya.cmds as cmds` (and `maya.mel`, `maya.api.OpenMaya as om`) at module top inside `try: … except: cmds = mel = om = None` — the overwhelming majority of modules. mayapy is always present where mayatk runs, and the guard lets the API registry, docs tooling and mock tests import the module surface without Maya.
- `blendertk`: `import bpy` **deferred into call bodies**, and Qt-only `uitk` imports deferred into the Slots methods that use them — headless `blender --background` ships no Qt, and the package surface must resolve without a running Blender.
- **No PyMEL** anywhere (`maya.cmds` / `maya.mel` only): `import pymel.core` at module top blocks Maya's UI for minutes during init.

## 5. Public-API contract and deprecation

Public APIs are contracts; `blendertk` mirrors `mayatk`'s at the name + behavior level so the tentacle slots stay branch-free. When a public name must be renamed, moved or removed:

1. Keep the old name working as an **alias for one release**, through `ptk.Deprecation` — never a hand-rolled `warnings.warn`, a silent binding alias, or a docstring line. Pick the shape that matches what is being retired:
   - `@Deprecation.symbol(replacement, remove_in=...)` — a function, method or class (on a class it wraps `__new__`, so a subclass warns too).
   - `@Deprecation.parameter(old, new=..., transform=..., remove_in=...)` — one keyword of a function that stays, including a rename-and-remap. It does **not** mark the owner deprecated; the method is live.
   - `Deprecation.attributes(globals(), {...}, remove_in=...)` — module attributes that moved. Chains onto an existing `__getattr__`, so it is safe on a module that already fronts a lazy loader.
   - `Deprecation.values({...}, what=..., remove_in=...)` — a retired member of a value vocabulary (a mode string that now builds as something else).

   For a shape none of the four reach — a deprecated branch inside a live function, say — call `Deprecation.warn(what, replacement, remove_in=...)` from the body. It is the only sanctioned alternative; reaching for `warnings.warn` yourself is what produced the seven spellings, and the two hand-derived `stacklevel`s that six call sites disagreed over, this replaced. `warn`'s `stacklevel` counts out from the first frame outside the machinery, so a consumer that wraps it in a helper of its own raises it by one per hop.
2. **`remove_in` is mandatory and is a version, not a sentence.** "Removed in the next release" is what every hand-rolled notice said and is exactly what nothing could check — `UvUtils.flip_uvs` shipped in 50 releases after its notice, the `FileManager` aliases in 34. An unparseable version raises at import, and so does a patch release (`0.12.1`): a patch never removes a name. Pass `since="YYYY-MM-DD"` (the day the notice first ships) as well: the window is counted in calendar days too, so a name goes only once the version reaches `remove_in` AND `Deprecation.MIN_WINDOW_DAYS` (30) have passed. Seven releases in two weeks retired names 15 days after their first warning. A replacement is mandatory too: a notice the caller cannot act on is noise.
3. Add a `CHANGELOG.md` line naming both; `API_CHANGES.md` records the delta automatically and lists the live retirement debt with its deadlines.
4. Bump **minor**; remove the alias in the release after. You do not have to remember: `generate_api_registry.py --check` fails once the package's `__version__` reaches a recorded `remove_in` and the notice's window has closed (one rule, `Deprecation.window_expired`; a name due by version but not yet by date reads **HELD** in `API_CHANGES.md`), and `Deprecation.expired(__version__)` answers the same question at runtime for the shapes a static walk cannot see. When one fires, delete the alias and its tests — raising the date is a deliberate act that belongs in `CHANGELOG.md`, not a default.

In a DCC, set `Deprecation.sink` once at startup (`cmds.warning`, or a logger): `DeprecationWarning` is hidden outside `__main__`, so otherwise no user ever sees one. It is additive — `warnings.warn` still fires, so `assertWarns` and `-W error` keep working.

Registry ownership: regenerate the **full** set (`python m3trik/scripts/generate_api_registry.py`) before committing a public-API change so `API_CHANGES.md` and `API_SHADOWS.md` are right at review; after publish the CI bot's refresh is authoritative — take theirs on any conflict rather than fighting it commit by commit.

## 6. Vendored copies — the one sanctioned duplicate

"Unify over duplicate" has exactly one exception: a copy vendored across layers that **cannot import each other** (mayatk ↔ blendertk; a DCC engine ↔ the extapps panel that also needs it; an in-app plugin folder where no `pythontk` is importable). Rules:

- The copies are **byte-identical** (or token-identical where DCC names differ) and **drift-guarded** by a `--check` script that CI runs. All of them run in `m3trik`'s `tests.yml`, which is the only CI with every sibling checked out: `sync_rpc_core.py` (`_rpc_core.py` ×4), `sync_shadow_shaders.py` (×2), `sync_shared_bat.py` (`package-manager.bat` ×2), and `check_dcc_twins.py` (the mayatk↔blendertk controller mixins). `extapps/test/test_vendor_sync.py` (Marmoset engine ×3; the Substance engine `_substance_engine.py` + connection, parameters, `substance_rpc/` and templates ×2; curtain-drape ×2; the Unity panels' `UnityPanelMixin` ×3) covers the extapps half and shares one normalizer with `check_dcc_twins.py`, which owns it. It is a pytest module that skips without its siblings, so extapps' own single-repo CI never exercised it; since 2026-09-26 it runs from the same seven-sibling job, where a skip fails the step.
  *This bullet was aspirational until 2026-09-16.* Every guard named here existed and passed, and **none of them ran in any CI** — three `skipTest` without siblings, the fourth was collected by no workflow. Wiring them was the fix; the lesson is that "drift-guarded" is a claim about a *scheduled run*, not about a file existing.
- The SSoT is named in the copy's header, and only the SSoT is hand-edited.
- **A family with no SSoT is not a sanctioned duplicate.** N hand-written copies of one shape — 11 `launcher.py` shells, a per-tool settings block — are not vendored copies; there is no source to guard against. Either give the family a base, or derive its guard from the roster that already lists it (an entry-point group, `DEFAULT_INCLUDE`, a pyproject table) — **never a hand-listed subset**, which is how the frameless-window fix landed in 3 of 11 launchers and the other 8 kept the bug for a release.
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
- **A test that forks on a MACHINE CAPABILITY must pin the branch, not discover it** (symlink privilege, DCC host, interpreter identity). Left to discover, it silently means something different on the developer's box than in CI, so it is green where it proves the least. Measured 2026-08-23: `test_install_force_rewrites` assumed `install_plugin`'s `copytree` fallback, and on the GitHub runner -- which HOLDS the symlink privilege -- the install dir *was* `plugin_src`, so the test both failed and wrote its marker into the tracked plugin source. Pin the branch (`mock.patch("os.symlink", side_effect=OSError)`) and cover the other one in its own test, skipped where the OS cannot reach it. Same class: `sys.executable` is the HOST binary inside a DCC (`maya.exe`), not an interpreter.
- Test artifacts go in `test/temp_tests/` and are cleaned in teardown; tests are exempt from the `TempArtifacts` rule (the harness owns teardown, and `check_temp_artifacts.py` skips them). Badge semantics: [TEST_BADGE_STANDARD.md](TEST_BADGE_STANDARD.md).

## 10. Dead code and scratch files

- Dead code is deleted, not commented out: grep-confirm zero callers across the workspace (all layers — a name can be a `.ui` slot or an entry point), then remove. Deleting a public name is a public-API change (§5): registry regen + `CHANGELOG.md` line.
- No scratch files outside the repo: repros live in `test/temp_tests/` (gitignored) and are deleted when done; one-shot reports (audits, plans) are folded into the owning docs/CHANGELOG and archived, per [DOCS_STANDARD.md](DOCS_STANDARD.md). Point the tool that writes one at that directory rather than accepting its default — a bare `cProfile -o prof` drops the dump wherever you happened to be, and inside a package tree that is a file the wheel silently omits.
- Scratch inside a package is a gate failure, not a `.gitignore` line: `check_temp_artifacts.py` flags any file under `<pkg>/<pkg>/` that Python does not load and neither `package-data` nor `MANIFEST.in` declares, plus extension-less files at a repo root. Ignoring it only hides the artifact from `git status`; if the file belongs, declare it so the wheel actually ships it.
- Temp files and dirs come from `ptk.TempArtifacts` (`.path()` / `.dir_path()`), never `tempfile.mkstemp` / `mkdtemp`: a hand-rolled `finally` cannot run when the process dies (routine inside a DCC), while the primitive's age-gated sweep reclaims what a dead process left behind. Tests are exempt (§9). Gate: `check_temp_artifacts.py`.
- Never overwrite a file you have not read this session; anchor edits on exact text — concurrent sessions and the user edit the same trees.

## 11. Public-repo hygiene

Most ecosystem repos are public. Tracked source, tests, docs and instruction files carry **no client names, studio drive layouts, hostnames, LAN IPs or credentials**. Large or client-owned fixtures resolve from an env var (`MAYATK_TEST_ASSETS`, `UNITYTK_TEST_ASSETS`) and env-skip when unset; internal hosts and credential helpers live in the private repos (`server`, `comfyui`) — check `gh repo view <name> --json visibility` before placing them. `m3trik/scripts/check_public_hygiene.py` enforces the client-name half before every release, against a denylist kept OUTSIDE every repo (`<workspace>/.claude/public_hygiene.txt`): a pattern list in public source publishes what it guards, so never write one into a repo, a test, a commit or a PR body.

## 12. CHANGELOG shape, commits and branches

- `CHANGELOG.md` is the only home for work history: `## <year>` headings, dated bold bullets — `- **YYYY-MM-DD — headline (touched paths).** body` — newest first, no `[Unreleased]` section. Release notes are the bullets added since the last release and dated on or after its tag (so editing an older entry never republishes it): lead with the one-sentence headline a user of the package needs; detail after.
- Cascade repos work on `dev`; `main` is release-only and reached through `push.ps1` (never plain `git push`). unitytk and extapps publish from `main` too (their own `publish.yml`, no cascade) — unitytk develops on `dev`, extapps on `main`; the non-package repos (m3trik, server, comfyui, www) work on `main`. Commit your own work before running `push.ps1 -Merge` — it commits the whole tree.
- `push.ps1` makes exactly one commit per release, `Release X.Y.Z` (version + internal floors + a fresh API registry). Never hand-write that message — and never hand-bump `__version__` unless you mean it: a version on `dev` above the published one is honored as a deliberate minor/major release.

## 13. Export is plug-and-play — previews overlay, never replace

The deliverable is the authored scene, written by a stock exporter. Anything a preview or lookdev aid does to the scene is read by that exporter, by every name-keyed manifest (lightmaps, sidecar sections, parity tables) and by the artist looking at the real asset.

- A viewport aid **drives the authored material in place**: a connection that composes over the authored value (`authored + channel x colour`), a display override, an overlay. It never duplicates a material, reassigns an object, renames a node or swaps a shading graph to show an effect. The render-effects "material mode" did all four (`X_Highlight` / `X_Fade` copies, transparent-graph swaps) and was rejected 2026-09-05: the object no longer showed its actual material, and the export needed a suspend/restore pass to put the scene back.
- An export-time **suspend / strip / restore** step, or a **sidecar**, is the last resort for what the carrier genuinely cannot express (a per-object float ramp that FBX flattens; a material property FBX drops). Before adding one, ask whether the thing it undoes should exist at all -- usually the preview should have been an overlay. When one is unavoidable it is one primitive, name-stable, idempotent, and undone by the same bracket that armed it (`FbxUtils.export_prepared`).
- The test of a preview design is: **export with the preview ON and the preview OFF and diff the files.** Any difference the artist did not author is a bug in the preview, not a job for the exporter.

## 14. Architecture — where code lives and how it grows

The monorepo is a shared library first and a set of tools second. Every rule here serves one goal: the next feature lands as an *addition* (a module, a registry entry, a subclass), not as an edit to something stable, and the primitive it needs already exists one layer down.

**Place code at the lowest layer that can host it.** Dependencies point down only: `pythontk` (pure Python; DCC- *and* app-agnostic) → `uitk` (Qt, DCC-free) → `mayatk` / `blendertk` (DCC glue, mirrored API) → `tentacle` (Slots only: a slot calls a toolkit method, it does not hold the algorithm); `extapps` and `unitytk` build on the same base. Decompose a feature across the layers instead of landing it whole where it was first needed: the curtain tool is `geo_utils.RailSurface` (pythontk) + a vendored `CurtainDrape` (both DCCs) + a panel. Three tests decide the layer. *Could a program with no Qt and no DCC use this?* Then it is pythontk, placed by data type ([`pythontk/CLAUDE.md`](../../pythontk/CLAUDE.md) owns the `*_utils` vs `engines/` split). *Qt, but no DCC and no application vocabulary?* Then it is uitk, even when only the two DCC packages use it today: they can both import uitk, so a copy in each is not a sanctioned twin (§6). uitk is a generic UI toolkit and names no DCC, product or domain (no Maya attribute names, no shots, manifests or exporters): a widget takes the host's vocabulary as data, as the sequencer takes its channel colours from `ptk.Palette.channels()`. DCC-free Qt that carries domain logic (a shot-manifest panel's controller) is split rather than lifted whole: the domain model and its rules drop to a pythontk engine, the generic widgetry to uitk, and the thin domain glue left over stays a drift-guarded twin in the DCC packages (§6). *Does it name a product?* Then it is not pythontk, whatever it imports: vendor it with its consumers (§6). A new distribution is never the answer to shared code; a subpackage is the boundary an engine graduates along if it ever outgrows its package.

**Write the general version when it costs about the same.** A helper written for one tool is usually a special case of a primitive: a lookup that is really a registry, a file scan that is really a store, a per-tool dialog that is really an editor over a protocol. Name and parameterize it for the general case (plain values in and out, no knowledge of the caller's layer), place it where the general case lives, and let the tool be its first consumer. `PresetLibrary` manages every tool's `PresetStore` rather than one tool's presets; `core_utils/handoff/` is one Template-Method kit that every app bridge shares.

**Build it promotion-ready, not pre-split.** A module should become a subpackage (§3) by *moving* code, never by rewriting it:
- one facade class per feature, delegating to collaborator classes kept in the same module until they earn files of their own: the class boundaries are the future file boundaries;
- variation through a registry or strategy table (a `Codec`, a handler dict, a `MapType` registry), never an `if kind == ...` chain, so each entry can become a module when the family grows (`map_factory/`: conversions registry → processor → handler strategies → orchestrator);
- collaborators injected, state on instances, no module-level mutable state: globals are what turn a split from a move into an untangling;
- the domain-neutral core kept apart from DCC or app glue even inside one module, so the neutral half can drop to `pythontk` intact.

Do not create the folder, the empty modules or the abstract base ahead of a second member: a seam costs nothing, an empty subpackage is clutter. But when the second member is *known to be coming* (the next rig of a planned family, the second bridge), build the shared base now: deferred extractions do not happen.

**One owner per concept.** Before writing a helper, grep the package's `API_INDEX.md` and [`API_SHADOWS.md`](API_SHADOWS.md). A concept defined in two packages is one of three things: (a) a thin facade that subclasses or delegates to the lower-layer primitive; (b) a sanctioned vendored twin (§6); (c) a defect, to be merged down. The logic counts, not the name: one DCC-free helper carried by both DCC packages under different names is a primitive missing from pythontk. A family of hand-written copies gets a base class or a roster-derived guard (§6).

**Extend through the seams that exist.** A new variant plugs into a registration point the codebase already has (`DEFAULT_INCLUDE`, entry points, preset stores, handler and registry tables, Slots `*_init` hooks, `.ui` tags) as a new module plus one registration line. A new scanner, dispatcher or parallel mechanism is the last resort. A change that has to edit a stable dispatcher to add one more case has found a missing seam: add the seam in the same change, then the case.

**Moving a module** (a promotion, a regrouping, a split):
1. Grep the whole workspace for the old path: all seven packages, tests, `.ui` headers, exec-templates. A consumer importing a `_`-prefixed path was already breaking §4 (exec-templates excepted); point it at the root.
2. Move; keep the facade class name; update `DEFAULT_INCLUDE` and the in-package imports. Tests stay one `test_<module>.py` per module.
3. If another package imports the module path, update it in the same change and leave a stub at the old path for one release. Exec-templates count even for a `_` path: a bridge template runs against whatever version the *other* DCC has installed (the Maya↔Blender templates import each other's `_scene_import`, `_smart_bake`, `lightmap_baker`). The stub: `Deprecation.attributes(globals(), {...}, remove_in=..., since=...)` (§5). With no outside consumer the move is internal and needs no alias.
4. Regenerate the registry (`API_CHANGES.md` should show only the path change) and, in pythontk, the surface snapshot (`python test/test_surface_snapshot.py --update`: it records each name's module, so a move fails it by design); run the package runner, and add a `CHANGELOG.md` line.

A move is its own commit, never folded into a behavior change. It rewrites import lines in files other sessions may have open, so coordinate with any session working in that tree before starting (§10).
