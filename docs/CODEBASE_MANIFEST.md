# Codebase Manifest

**Nav**: [← m3trik](../CLAUDE.md) · [README: goals and rules in brief](../README.md) · [Code standard](CODE_STANDARD.md) · [Docs standard](DOCS_STANDARD.md)

The architecture of record for the m3trik ecosystem: what each package is for, where each kind of code goes, how a tool is put together, which check holds each part of the shape, and the decisions behind it. The rules themselves live in [CODE_STANDARD.md](CODE_STANDARD.md) (in brief in the [README](../README.md)); the public surface of each package lives in its `API_INDEX.md` / `API_REGISTRY.md`. This file replaces the 2026-10 restructure plan: what the plan decided is recorded here, what it scheduled is done.

## What we are building

Two products of tools on four general libraries:

- **tentacle**, for work inside a DCC: one set of tools (export, baking, shots, materials, rigs, bridges) that behaves the same in Maya and Blender, reached from the marking menu, a panel or a script.
- **extapps**, for work outside one: standalone apps (photogrammetry, Substance Painter, Marmoset Toolbag, texture maps, Unity delivery, WebXR preview, look matching) that need no host. tentacle opens them by name when they are installed.

Three properties follow from that and every placement decision serves them:

1. **Harmony.** Maya and Blender expose the same operation under the same name and behavior, so one panel serves both, and one tool can use another's results.
2. **Reuse.** Every operation is callable on its own: by the marking menu, a panel, a script, another tool, or a test that runs without a DCC.
3. **Libraries that stand alone.** pythontk, uitk, mayatk and blendertk are useful to a developer who has never heard of our pipeline. No library imports a product.

## The packages

| Package | Role | Holds | Depends on | License | Release |
|:--|:--|:--|:--|:--|:--|
| pythontk | library | Pure-Python primitives, and the host-free models both DCCs share (shots, scene-export records, lighting, rig graph) behind adapter Protocols | -- | MIT | cascade |
| uitk | library | Generic Qt: the Switchboard, widgets, editors, the parameter-panel engine, the external-app handler. Names no DCC and no product | pythontk | LGPL-3.0+ | cascade |
| mayatk | library | Maya host operations and every tool's Maya API half; no UI | pythontk, uitk | MIT + Commons Clause | cascade |
| blendertk | library | The Blender mirror of mayatk, by name and behavior (signature too where a shared panel calls it); no UI | pythontk, uitk | GPL-3.0+ | cascade |
| tentacle | product | The marking-menu launcher, and every DCC tool's panel (`.ui`) and Slots class | the four libraries (mayatk / blendertk as extras) | GPL-3.0+ | cascade |
| extapps | product | Standalone apps: each app's engine, panel and Slots in one package; the vendored Toolbag engine | pythontk, uitk | LGPL-3.0+ | standalone |
| unitytk | library | Unity integration: project creation, the deliverer, the C# importers (`templates/` stay MIT: they compile into player builds) | pythontk | LGPL-3.0+ / MIT | standalone |

The dependency chain is `pythontk → uitk → {mayatk, blendertk} → tentacle`, with `pythontk → unitytk` and `{pythontk, uitk} → extapps` beside it. Nothing depends on a product. tentacle reaches extapps only by app name through uitk's external-app handler, which installs a missing app within the version range tentacle declares (`tentacletk[apps]`: the floor and the next-minor cap).

## Where code goes

Ask who needs the code, then put it at the one place every one of them can reach without reaching up.

| Kind of code | Home | Example |
|:--|:--|:--|
| A DCC tool's operations | its library, mirrored in both hosts | `mtk.Bridge.bridge` / `btk.Bridge.bridge` |
| Host-free logic both hosts share | pythontk, behind a small adapter Protocol with a `Pure*` default that each host implements | `ShotStore` over `ShotsHost`; `PreviewController` over `PreviewSession` (uitk, generic Qt) |
| A contract every reader needs | where every reader reaches it | `SceneRecords` (pythontk), read by both hosts, unitytk's generated C# and the WebXR viewer |
| A DCC tool's panel | tentacle: `ui/tools/<tool>.ui` + one Slots class `slots/tools/<tool>.py` (Qt helpers in `slots/tools/_<tool>/`) | `ui/tools/bevel.ui` + `slots/tools/bevel.py` |
| A marking-menu category | tentacle: one composed Slots class `slots/<category>.py`, shared by both hosts | `slots/normals.py` |
| A standalone app | extapps: `extapps/<app>/` with its engine, `<app>.ui`, `slots.py` and `launcher.py` | `extapps/texture_maps/converter/` |
| Generic Qt | uitk | `TableWidget`, `FormPanel`, `ExternalAppHandler` |
| Maintenance tooling | `m3trik/scripts/` | `check_layers.py` |

A `_`-prefixed module is internal; other packages reach a package only through its root (`ptk.X`, `mtk.X`).

## How a tool is built

- **One API, two halves.** Every caller reaches a tool through its library's public API. Only the host halves (mayatk's, blendertk's) touch Maya or Blender, and they expose the same names.
- **Panels call the API, never a host.** A Slots class binds uitk widgets by `objectName` and reaches the host only through `self.tk`, the toolkit the host's entry point puts on the switchboard. It imports no host module.
- **One-host controls are hidden, never stubbed.** `Slots.requires(widget, host)` and `Slots.hide_unless(widget, available)`; uitk's visibility policy hides them and their shortcuts.
- **Large objects are facades over small collaborators**, each with its own state. Public signatures stay on the facade; a collaborator calls its siblings through the facade's public methods. A mixin is only for a capability several classes share.
- **Host behavior is injected, never subclassed.** A library class that keeps a pythontk class's name configures and adds; it never overrides (`check_dcc_twins.py` holds this).
- **Exports are plug-and-play.** A preview overlays the authored value and never changes what the exporter reads. Every export writes data for the objects it ships, and states the unit its writer used.
- **A UI is a `.ui` file or code.** uitk binds either the same way: a Designer `.ui` registered by its file name, or any callable returning a widget tree registered with `sb.register_ui(name, build)`.

## How the shape is held

Each part of the shape has a check, so the rule it holds is stated once, in the check and the [README's check table](../README.md). The checks run in m3trik's CI and in `push.ps1` before a release.

| Part of the shape | Check |
|:--|:--|
| Layer order; no library imports a product; a Slots module imports no host | `check_layers.py` (layer and role rules) |
| Written once; bindings never override | `check_dcc_twins.py` (+ `extapps/test/test_vendor_sync.py` for the one sanctioned vendored copy) |
| Every `self.tk` call a shared panel makes exists in both libraries | `compare_panel_surface.py` |
| A user's saved widget and record names survive every move | `check_saved_names.py` |
| A removed public name names its new home | `generate_api_registry.py --semver` and each package's `MOVED_NAMES` |
| Small objects and functions in tentacle's Slots | ruff, configured by path |

## Decisions

The calls that set the shape, with the reason each one was made. A later decision that supersedes an earlier one says so.

| Date | Decision | Why |
|:--|:--|:--|
| 2026-10-26 | **Split by feature** into libraries and a product; panels and Slots move into tentacle, shared by both hosts. | Twin panels drifted (87 twin functions apart, 52 in their logic), and every fix had to be made twice. |
| 2026-10-27 | **Libraries hold the logic, tentacle the UI** (corrects the first reading, which moved tool logic into `tentacle/tools/`). | The point of the split: scripts, other tools and the other host reuse an operation only if it lives in the library. |
| 2026-10-26 | **Facades over collaborators; host behavior injected.** | A 200-method object with single-use mixins cannot be reused or tested in parts; a per-host subclass can override anything, so hosts drift silently. |
| 2026-10-26 | **Guardrails strict on the new layout from its first file, nothing frozen,** on checks that already exist. | Baselines kept for months become exceptions nobody removes; a draining legacy tree needs none. |
| 2026-10-26 | **CLAUDE.md keeps judgment rules, one line each;** rules a check holds collapse into one line naming the checks. | A rule a check holds needs no prose; a failing check carries the detail. |
| 2026-10-26 | **tentacle is GPL-3.0+,** with its exception for mayatk and Maya. | Every tool, panel and Slots class runs in Blender, whose Python API makes that code GPL-covered; no part could keep a no-sale term. |
| 2026-10-28 | **uitk's generic sequencer stays; its shot layer moves to tentacle** behind uitk extension seams (`SequencerLayer`). | Shots are our pipeline's vocabulary; a generic timeline is not. |
| 2026-10-28 | **Marking-menu categories composed at once,** one Slots class each over `self.tk`. | Composing them when next touched would have kept two layouts alive for months. |
| 2026-10-28 | **One-host controls are hidden on the host that lacks them,** never greyed stubs. | A control that cannot work is clutter; the gap is a backlog entry, not a disabled button. |
| 2026-10-31 | **extapps is the standalone-apps product, off the chain** (supersedes 2026-10-26 "fold extapps into tentacle" and its 2026-10-28 "engines only" phase). A tool with a host half goes to tentacle; a host-free app to extapps. | Folding it in made every standalone app need GPL tentacle and its DCC launcher, and the planned next step would have put extapps under both host libraries for one shared engine. Off the chain, nothing depends on it. |
| 2026-10-31 | **One Unity app,** in extapps; inside a DCC, tentacle opens it and adds a "Current scene" source with the host's export options. unitytk leaves mayatk, blendertk and tentacle. | The Unity side was already the file-based app's; two Unity panels shared a helper only by vendoring it. |
| 2026-10-31 | **Version-aware app installs:** a tentacle release declares an extapps floor and the next-minor cap, and the handler installs or offers an update within it. | An extapps minor can break an older tentacle; the range keeps the pair in step without pinning every release together. |
| 2026-10-31 | **Code-built UIs register like `.ui` files** (`sb.register_ui`); no spec format until a consumer needs one, shaped for users outside our products. | uitk already bound code-built widget trees; what was missing was a way in and docs that admitted it. A new file format is a maintenance cost with no consumer yet. |
| 2026-10-31 | **One launcher, host behavior injected:** tentacle's `Tcl` builds ONE `uitk.MarkingMenu(host=...)` for every host; each host library ships the `uitk.MarkingMenuHost` adapter (`MayaMarkingMenuHost`, `BlenderMarkingMenuHost`), Blender's Qt hosting is blendertk's, and 3ds Max is dropped. | Three `MarkingMenu` subclasses repeated one recipe with different values and overrode its seams; Blender's hosting sat above blendertk, which kept two mirrors of it; the Max fork could run no shared tool. |
| 2026-10-31 | **Exports scope their records to what they ship,** through one context the exporter fills, and **the writer states its unit.** | Hand-offs shipped (and embedded) other objects' bake data; a record labelled with the scene's unit beside geometry its writer wrote in another unit misreads by that factor. |

## See also

- [CODE_STANDARD.md](CODE_STANDARD.md): every rule with its reasoning.
- [CONTEXT_BUDGET.md](CONTEXT_BUDGET.md): the size caps the instruction files keep.
- [API_SHADOWS.md](API_SHADOWS.md): name collisions across packages.
