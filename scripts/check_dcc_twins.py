#!/usr/bin/python
# coding=utf-8
"""Drift guard for the mayatk <-> blendertk twins that are NOT a public-API mirror.

``CODE_STANDARD.md`` §6 licenses exactly one kind of duplication: a copy vendored
across layers that cannot import each other, on the condition that it is
"drift-guarded by a test or a ``--check`` script that CI runs". Measured
2026-09-16, **every named guard ran in no CI**: three ``skipTest`` because no
sibling is checked out, and the fourth lives in a test directory neither DCC's
workflow collects. They passed, so nothing was broken -- but the exemption is the
mechanism by which duplication grows, and it was resting on an enforcement claim
that was false.

Scope -- what this is NOT
-------------------------
The mayatk<->blendertk name collisions in ``docs/API_SHADOWS.md`` are the
deliberate public-API mirror that keeps tentacle's slots branch-free. Those are
not twins in this sense and are none of this script's business. What IS in scope
is the **controller tier**: helper mixins that carry the same algorithm in both
packages because there is nowhere shared for them to live (uitk hosts no
DCC-agnostic panel controller; pythontk cannot host Qt). Those files were copied,
and a copy nothing compares is a copy that drifts. Since 2026-09-26 that tier is
split by rule (CODE_STANDARD §14): the domain rules drop to a pythontk engine,
generic widgetry to uitk (which names no domain), and only the thin domain glue
left over stays mirrored -- and is ledgered here.

Two granularities
-----------------
``identical``   the whole file must match after normalization.
``symbols``     only the named methods must match. This exists because
                whole-file is the wrong unit for most real twins: measured
                2026-09-16, the Shot Sequencer's ``gap_manager.py`` (one shared
                tentacle copy since 2026-10-28) had 7 of 14 methods identical
                while the rest differ for a genuine reason (mayatk brackets its
                edits with ``store.scene_edit(label)``, a primitive blendertk's
                store does not have -- it uses ``CoreUtils.undo_chunk()``). A
                whole-file guard there would be red forever and get deleted; a
                symbol guard pins the 7 that ARE shared and says nothing about
                the 7 that are not.

What "identical" means
----------------------
Not byte equality -- twins legitimately differ in host vocabulary. The normalizer
folds ``mayatk``/``blendertk``, ``mtk``/``btk``, ``bpy``/``maya.cmds`` and
``maya``/``blender`` to neutral placeholders, and collapses docstrings. Crucially
the fold applies **only inside STRING and COMMENT tokens**: a twin may NAME the
other DCC in prose, but an ``import mayatk`` inside blendertk is a real
cross-wiring bug and must never compare equal. That distinction is the whole
safety of this comparison, and ``test_check_dcc_twins.py`` self-tests it.

Written once (the new layout)
-----------------------------
tentacle's new layout (the shared tools' ``slots/tools/``, composed slots) gets
the reverse check, with no ledger: a function body of 8+ lines, docstring dropped
and the toolkit aliases folded, may exist only once across the layout and between
the layout and the four libraries. Copies that call different hosts are a tool's
two halves, the mirror; two over one host, or over none, are a copy. It reads no
library while the layout is empty.

Host bindings
-------------
Host behavior is injected (an adapter), never a per-host subclass (CODE_STANDARD
section 0, Adapters). Where a library keeps its own name for a shared pythontk
class (``mtk.SceneDataSidecar``), that class is a *binding*: configuration (class
attributes, the adapter it is bound to) and, where it is the tool's API half,
host-only additions -- but it defines no method the shared class defines. The
declared roster is :data:`HOST_BINDINGS`; an override fails ``--check``.

Usage
-----
    python m3trik/scripts/check_dcc_twins.py           # report (exit 0 always)
    python m3trik/scripts/check_dcc_twins.py --check   # exit 1 on drift
    python m3trik/scripts/check_dcc_twins.py --list    # print the ledger

Report mode is the default so a bare run is always safe to try. CI runs
``--check``: the rule is that a guard must not go RED the day it lands (that is
how one gets disabled rather than fixed), and this one does not -- every symbol
in the ledger was measured identical before being added. Seed a new entry the
same way, or leave CI on report mode until it is green.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import os
import re
import subprocess
import sys
import textwrap
import tokenize
from typing import Dict, List, Optional, Sequence, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------------------- the ledger


class TwinSpec:
    """One declared twin pair.

    Parameters:
        rel: Path relative to each package's inner source dir, identical on
            both sides (``anim_utils/shots/.../graph_sync.py``).
        symbols: Qualified ``Class.method`` names that must match. ``None``
            means the WHOLE FILE must match.
        reason: Why this pair is duplicated at all -- the §6 justification.
        note: Optional caveat recorded against the entry.
        a: Left package (default mayatk, the reference).
        b: Right package (default blendertk, the mirror).
    """

    def __init__(self, rel, reason, symbols=None, note="", a="mayatk", b="blendertk"):
        self.rel = rel
        self.reason = reason
        # ``symbols=None`` means WHOLE FILE; an empty sequence means "check
        # nothing", which is never what an entry wants. Coercing one into the
        # other -- as this did -- turns a typo into the strictest possible
        # comparison, silently.
        if symbols is not None and not tuple(symbols):
            raise ValueError(
                "%s: symbols=[] checks nothing. Pass symbols=None for a "
                "whole-file comparison, or name the symbols." % rel
            )
        self.symbols = tuple(symbols) if symbols is not None else None
        self.note = note
        self.a = a
        self.b = b

    @property
    def label(self) -> str:
        kind = (
            "whole-file" if self.symbols is None else f"{len(self.symbols)} symbol(s)"
        )
        return f"{self.rel}  [{self.a}<->{self.b}, {kind}]"


# Seeded 2026-09-16 from a measured pass, NOT from a guess: every symbol below
# was confirmed identical-after-fold at the moment it was added. An entry that
# was never green is worse than no entry -- it teaches the reader that red is
# normal here.
LEDGER: List[TwinSpec] = [
    TwinSpec(
        rel="core_utils/_core_utils.py",
        reason=(
            "The decorator tentacle's composed Slots lean on to read the selection "
            "for a None target. Host-free logic, but a library helper both DCC "
            "packages expose on CoreUtils, and code never moves into pythontk; the "
            "selection read is each host's CoreUtils.selected_objects."
        ),
        symbols=("CoreUtils.selected",),
    ),
    TwinSpec(
        rel="env_utils/usd.py",
        reason=(
            "The two UsdUtils are the mirrored public API a tentacle slot calls "
            "branch-free, so BOTH packages have to expose these. Their bodies are "
            "pure pxr with no DCC call in them, but the only shared tier below is "
            "pythontk, which is zero-dependency by contract (numpy + Pillow) and "
            "pxr ships only inside a DCC host -- hosting them there would give the "
            "core a module that cannot import on a bare interpreter."
        ),
        symbols=(
            "UsdUtils.sanitize_prim_name",
            "UsdUtils.skinning_methods",
        ),
        note=(
            "2 of the 6 shared names are identical. The other 4 (export, "
            "import_scene, is_usd_file, sampling_frame_range) each wrap their own "
            "host's importer and are expected to differ. sanitize_prim_name also "
            "has a third, dependency-free copy in mayatk's _import_scene_usd "
            "template, executed by that suite's template guards."
        ),
    ),
    TwinSpec(
        rel="light_utils/lightmap_baker/lightmap_baker.py",
        reason=(
            "What LightmapBaker.bake returns, one shape in both packages so the "
            "panels and a script read the same result. A lightmap-only type has "
            "no home in pythontk -- the shared half of this tool there is the "
            "generic FileDependencies -- so each baker carries the dataclass, and "
            "the few host-free baker helpers beside it for the same reason."
        ),
        symbols=(
            "LightmapBakeResult",
            "LightmapBaker._atlas_gutter",
            "LightmapBaker._move_into_place",
            "LightmapBaker.peak_level",
            "LightmapBaker.plan_sizes",
            "LightmapBaker.preset_store",
            "LightmapBaker._claimed_by",
            "LightmapBaker._edges_in_atlas",
            "LightmapBaker._merge_result",
            "LightmapBaker._probe_folder",
            "LightmapBaker._to_region_rect",
            "LightmapBaker.rebake_changed",
            "LightmapBaker._lit_as",
            "LightmapBaker._light_rule",
            "_InPlacePlan.placed",
        ),
        note=(
            "The result class whole, fields included, plus the host-free baker "
            "helpers identical on both sides (re-measured 2026-10-19): the atlas "
            "gutter, the safe move into place, the brightest-map level, the "
            "atlas plan's pixel sizes, the preset store, and the in-place / "
            "Changed-scope helpers. The two engines differ throughout "
            "otherwise (Arnold vs Cycles)."
        ),
    ),
    TwinSpec(
        rel="light_utils/lightmap_baker/lightmap_records.py",
        reason=(
            "The lightmap record's bake-state and probe bookkeeping: one rule "
            "in both packages so a scene baked in either reads the same; the "
            "markers themselves are host attributes, so the class stays per host."
        ),
        symbols=(
            "LightmapRecords._advance_bake_state",
            "LightmapRecords._own_probe_file",
            "LightmapRecords._probe_ref",
        ),
        note="Measured identical 2026-10-19; the rest read host markers.",
    ),
    TwinSpec(
        rel="uv_utils/texture_combine/texture_combine.py",
        reason=(
            "Texture Combine's record format (fingerprint, array encode, file "
            "stamp) and its record queries: one text in both packages so a "
            "combine recorded in either host reads the same. Host-free, but "
            "a record-only type has no pythontk home yet (FUTURE.md: a ptk "
            "CombineRecord would end the copy)."
        ),
        symbols=(
            "_TextureCombineInternal._fingerprint",
            "_TextureCombineInternal._encode",
            "_TextureCombineInternal._decode",
            "_TextureCombineInternal._stamp",
            "TextureCombine.names",
            "TextureCombine.entry",
            "TextureCombine.stale",
            "TextureCombine.plan",
            "TextureCombine._entry",
        ),
        note="Measured identical 2026-10-19; the gather and write-back read host meshes.",
    ),
    # Seeded 2026-09-26 after the auto-instancer's DCC-free merge/format moved
    # to ``ptk.InstanceGrouping``: what is still identical, measured green.
    TwinSpec(
        rel="core_utils/auto_instancer/_auto_instancer.py",
        reason=(
            "The mirrored AutoInstancer public API a tentacle slot calls "
            "branch-free. Its signature merge and run summary now delegate to "
            "ptk.InstanceGrouping; what stays in both packages is the class "
            "shell around the scene calls: config properties, logging, and "
            "the delegating wrappers."
        ),
        symbols=(
            "AutoInstancer._log_report",
            "AutoInstancer._merge_similar_signatures",
            "AutoInstancer._reset_summary",
            "AutoInstancer.check_uvs",
            "AutoInstancer.combine_assemblies",
            "AutoInstancer.default_summary",
            "AutoInstancer.format_summary",
            "AutoInstancer.require_same_material",
            "AutoInstancer.scale_tolerance",
            "AutoInstancer.search_radius_mult",
            "AutoInstancer.tolerance",
            "AutoInstancer.verbose",
            "InstanceGroup.__init__",
        ),
        note=(
            "13 of 38 shared symbols. The rest walk the scene (DAG paths + "
            "UUIDs vs bpy objects + session_uid) and are expected to differ. "
            "The natural-sort key they both carried is ptk.StrUtils."
            "natural_sort_key now, and instancing_strategy.py is a per-host "
            "binding of ptk.InstancingStrategy (only the triangle-count hook "
            "differs; nothing left to guard)."
        ),
    ),
    TwinSpec(
        rel="core_utils/auto_instancer/geometry_matcher.py",
        reason=(
            "Geometry signature matcher behind both AutoInstancers. The mesh "
            "reads differ per host (OpenMaya vs bmesh), but the quantizer and "
            "the cache reset are the same code and must stay so, or equal "
            "meshes stop matching across the two hosts' signatures."
        ),
        symbols=("GeometryMatcher.clear_cache", "GeometryMatcher.quantize"),
        note="2 of 16 shared methods; the rest read host geometry.",
    ),
    # Seeded 2026-09-26 after the DCC-free Qt split: the domain rules went to
    # pythontk (RangeResolver / ManifestModel / Mapping / StepStatus / ShotReport,
    # HierarchyBaselineStore) and the Suffix By Type editor to uitk
    # (NamingConventionEditor). What each DCC keeps is thin panel glue over
    # those -- identical, so it is guarded here, measured green.
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/segment_collector.py",
        reason=(
            "Shot Sequencer segment reader: the object-row summary rule is "
            "host-neutral, the key probe under it (_has_key_at) is each host's "
            "own curve query."
        ),
        symbols=(
            "SegmentCollector.active_object_set",
            "SegmentCollector.summary_times",
        ),
        note=(
            "2 of 6 shared methods (2026-10-12): the summary rule and the active "
            "shot's object set. The rest read Maya animCurves or Blender fcurves "
            "directly."
        ),
    ),
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/graph_sync.py",
        reason=(
            "Shot Sequencer graph-editor glue: what the graph shows (the visible "
            "shots' members, the frame window) and how its key selection reaches "
            "the key menu are host-neutral; reading and writing curves is each "
            "host's own."
        ),
        symbols=(
            "GraphSync._bounds",
            "GraphSync._edit",
            "GraphSync._ledger",
            "GraphSync._on_rebuilt",
            "GraphSync._shot_at",
            "GraphSync._visible",
            "GraphSync.key_targets",
            "GraphSync.on_key_menu",
            "GraphSync.sync",
        ),
        note=(
            "9 of 29 shared methods (re-measured 2026-10-12). Curve ids, reads, "
            "writes, infinity, selection following and change detection are per "
            "host (Maya animCurve nodes and MAnimMessage; Blender fcurves, Cycles "
            "modifiers and fingerprints)."
        ),
    ),
    # Seeded 2026-09-26 after the scene-export engine pass: SceneExporterBase and
    # SceneDataSidecarBase (pythontk) took the exporter's DCC-free shell and the
    # sidecar; HierarchyAnalyzer the Hierarchy Sync pairing passes; TiledPath the
    # tile/frame tokens. What each DCC still carries identically, measured green.
    TwinSpec(
        rel="env_utils/scene_exporter/task_manager.py",
        reason=(
            "The Scene Exporter's TaskManager is a per-host TaskFactory built from "
            "the _task_* phase mixins, which reach the scene throughout; these two "
            "DCC-free members ride it (pythontk has no export-task base to host "
            "them without taking the phase mixins along)."
        ),
        symbols=("TaskManager._sidecar_kwargs", "TaskManager.run_tasks"),
        note="2 of 7 shared methods; the rest build or read the host's scene.",
    ),
    TwinSpec(
        rel="env_utils/scene_exporter/_task_data.py",
        reason=(
            "Exporter phase-mixin helpers that are pure delegations: the tile/frame "
            "collapse is ptk.TiledPath (a private 3-token regex here once let a "
            "<frame> / <u>_<v> texture skip the representative collapse)."
        ),
        symbols=(
            "_TaskDataMixin._is_tiled_path",
            "_TaskDataMixin._log_link",
            "_TaskDataMixin._tiled_representative",
            "_TaskDataMixin.export_path",
        ),
        note=(
            "4 of 17 shared methods (re-measured 2026-10-12); the texture scan "
            "itself walks each host's nodes."
        ),
    ),
    TwinSpec(
        rel="env_utils/scene_exporter/_task_animation.py",
        reason=(
            "The scene-records publish step's reporting (its log lines and the "
            "range-coverage gate), identical over the pythontk ExportSnapshot both "
            "exporters assemble; it lives on the per-host animation phase mixin."
        ),
        symbols=(
            "_AnimationTasksMixin._bake_range_token",
            "_AnimationTasksMixin._log_data_node_summary",
            "_AnimationTasksMixin._log_snapshot_notes",
            "_AnimationTasksMixin._note_link",
            "_AnimationTasksMixin._require_range_coverage",
            "_AnimationTasksMixin.ensure_scene_records_published",
        ),
        note=(
            "6 of 23 shared methods (re-measured 2026-10-12); the bake and publish "
            "steps reach the scene."
        ),
    ),
    TwinSpec(
        rel="env_utils/scene_exporter/_task_checks.py",
        reason=(
            "Two check helpers with no scene call (the deliverable's file list and "
            "the texture-budget remedy text), on the per-host checks mixin."
        ),
        symbols=(
            "_TaskChecksMixin._deliverable_paths",
            "_TaskChecksMixin._texture_size_limit_remedy",
        ),
        note="2 of 20 shared methods; every check body reads its host's scene.",
    ),
    TwinSpec(
        rel="env_utils/scene_exporter/task_definitions.py",
        reason=(
            "The definitions accessor of the per-host task/check tables (the tables "
            "themselves list each host's tasks)."
        ),
        symbols=("_TaskDefinitionsMixin.definitions",),
        note="1 of 3 shared methods; task_definitions / check_definitions differ by host.",
    ),
    TwinSpec(
        rel="env_utils/hierarchy_sync/_hierarchy_sync.py",
        reason=(
            "Hierarchy Sync's pairing passes are ptk.HierarchyAnalyzer's "
            "(detect_fuzzy_renames / detect_suffix_flattening); what stays is each "
            "host's thin wrapper -- the fuzzy_matching toggle, the debug log and the "
            "never-raise guard around a diff."
        ),
        symbols=(
            "HierarchySync._detect_fuzzy_renames",
            "HierarchySync._detect_suffix_flattening",
        ),
        note=(
            "2 of 19 shared methods. _detect_reparented differs by design: mayatk "
            "vetoes a pairing by shape type (_reparent_pair_compatible); the fix_* "
            "passes edit each host's scene."
        ),
    ),
    TwinSpec(
        rel="env_utils/hierarchy_sync/hierarchy_sync_session.py",
        reason=(
            "What the shared Hierarchy Sync panel asks of each host's scene: the "
            "repair pruning, the loaded check and the fuzzy-matching toggle are "
            "host-free and kept identical; the scene reads and edits differ."
        ),
        symbols=(
            "HierarchySyncSession.is_loaded",
            "HierarchySyncSession._prune_resolved_by_renames",
            "HierarchySyncSession.fuzzy_matching",
        ),
    ),
    TwinSpec(
        rel="mat_utils/marmoset_bridge/_marmoset_bridge.py",
        reason=(
            "The Marmoset bake roundtrip's host-free bookkeeping: packed-map "
            "unpack staging over the material manifest, the re-bake-stable "
            "material names, the map-filing aliases and the bucketing of baked "
            "maps to source materials. It rides the bridge's DCC half beside the "
            "scene I/O that differs, and the vendored engine it would otherwise "
            "move into is extapps' too, which bakes nothing."
        ),
        symbols=(
            "_MarmosetBridgeInternal._stage_manifest_textures",
            "MarmosetBridge.source_material_name",
            "MarmosetBridge.baked_material_name",
            "MarmosetBridge.texture_set_aliases",
            "MarmosetBridge._group_baked_outputs",
            "MarmosetBridge._deliver",
            "MarmosetBridge._delivered_paths",
            "MarmosetBridge.render_template",
            "MarmosetBridge.source_model_path_for",
            "MarmosetBridge.toolbag_path",
            "MarmosetBridge.params_registry",
            "MarmosetBridge.list_template_modes",
            "MarmosetBridge.params_defaults",
        ),
        note=(
            "13 of 27 shared methods (re-measured 2026-10-28: the panel's "
            "registry, template modes and defaults joined when the panel moved "
            "to tentacle; 2026-10-12: delivery, the template render and the "
            "Toolbag and source-model paths); "
            "export, cage, assignment and retirement read each host's scene "
            "(blendertk swaps the baked material per slot)."
        ),
    ),
    TwinSpec(
        rel="uv_utils/_uv_utils.py",
        reason=(
            "What UvUtils.unfold_uvs returns: one shape in both packages, so tentacle's "
            "shared UV page reads either host's result (2026-10-28)."
        ),
        symbols=("UnfoldResult",),
    ),
]


# ------------------------------------------------------------ normalization
#
# The host vocabulary a twin is ALLOWED to differ in -- in PROSE. Ordered
# longest-first within each pair so `blendertk` folds before `blender` could
# match inside it. Mapped to neutral tokens rather than to one side's spelling:
# folding "Blender"->"Maya" would let a genuine cross-wiring slip through in the
# other direction.
HOST_TOKENS = (
    (r"blendertk|mayatk", "<dcctk>"),
    (r"\bbtk\b|\bmtk\b", "<dcc>"),
    (r"\bbpy\b|maya\.cmds|maya\.mel", "<dccapi>"),
    (r"\bblender\b|\bmaya\b", "<dccname>"),
)
_HOST_RE = tuple((re.compile(p, re.IGNORECASE), sub) for p, sub in HOST_TOKENS)


def fold_hosts(text: str) -> str:
    """Replace every host-vocabulary token in *text* with its neutral placeholder."""
    for rx, sub in _HOST_RE:
        text = rx.sub(sub, text)
    return text


def collapse_docstrings(lines: Sequence[str]) -> List[str]:
    """Source lines with each docstring collapsed to a one-line placeholder.

    Lets per-package docstrings (module-path self-references) diverge while
    keeping everything else -- code, comments, formatting -- line-comparable.

    Raises:
        SyntaxError: if *lines* are not parseable Python.
    """
    src = "\n".join(lines)
    lines = list(lines)
    drop = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0].value
                lines[doc.lineno - 1] = '"""<doc>"""'
                drop.update(range(doc.lineno, doc.end_lineno))
    return [ln for i, ln in enumerate(lines) if i not in drop]


def host_normalized(lines: Sequence[str], code_aware: bool = False) -> List[str]:
    """Fold the host vocabulary so 'same file, other DCC' compares equal.

    With *code_aware*, only STRING and COMMENT tokens are folded -- executable
    code is compared verbatim. That distinction is the whole safety of this
    normalizer. A twin may legitimately *name* the other DCC in prose
    (blendertk's vendored engine docstring says "the Maya bridge in mayatk", by
    design), but it must never name it in code: an ``import mayatk`` inside
    blendertk, or an ``mtk.foo()`` call where the twin has ``btk.foo()``, is a
    real cross-wiring bug, and a whole-line fold would quietly report those two
    lines as equal.

    Without *code_aware* the fold is applied whole-line -- used for ``.lua`` and
    ``.ui``, which carry no imports to mask.

    When *code_aware* is set and the text does NOT tokenize, this returns the
    lines UNFOLDED rather than degrading to the whole-line fold. Unparseable
    Python is the one case where the coarse fold is least safe and its failure
    is least visible: it would mask a cross-wired ``import mayatk`` and report
    the entry ``ok``. Leaving the host vocabulary unfolded instead makes the two
    sides differ on that vocabulary and report ``drift`` -- a false alarm a
    maintainer can read and dismiss, in place of a false all-clear nobody sees.
    Fail loud, not silent.
    """
    if not code_aware:
        return [fold_hosts(line) for line in lines]

    src = "\n".join(lines)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return list(lines)

    out = list(lines)
    for tok in toks:
        if tok.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        if srow == erow:
            line = out[srow - 1]
            out[srow - 1] = line[:scol] + fold_hosts(line[scol:ecol]) + line[ecol:]
            continue
        # Multi-line string: fold only the part INSIDE it on the first and last
        # lines. Folding those lines whole would reach the code around the quotes
        # -- `x = mtk.f("""Maya` would have its `mtk` folded too, which is exactly
        # the masking this function exists to avoid.
        out[srow - 1] = out[srow - 1][:scol] + fold_hosts(out[srow - 1][scol:])
        for i in range(srow, erow - 1):
            out[i] = fold_hosts(out[i])
        out[erow - 1] = fold_hosts(out[erow - 1][:ecol]) + out[erow - 1][ecol:]
    return out


def comment_stripped(lines: Sequence[str], marker: str) -> List[str]:
    """Drop whole-line *marker* comments -- the non-Python analogue of docstrings.

    A ``.lua`` preset's leading ``--`` block is its description and names its host
    exactly like a module docstring does; the code below it is the twin contract.
    """
    return [ln for ln in lines if not ln.lstrip().startswith(marker)]


def twin_normalized(lines: Sequence[str], rel: str) -> List[str]:
    """Reduce *lines* to what a declared twin must share, by file type.

    Order matters and is the reason this is one function rather than a chain of
    fallbacks. The host fold runs FIRST, on the original source, because that is
    the form guaranteed to tokenize -- collapsing docstrings first can leave a
    function whose body was only a docstring with no body at all, and the fold
    would then degrade to its unfolded fallback -- reporting drift on host
    vocabulary alone -- for exactly the files that most need the precise mode.
    Folding cannot break parseability
    itself: the placeholders contain no quotes, so the folded source is still
    valid Python.
    """
    if rel.endswith(".py"):
        lines = host_normalized(lines, code_aware=True)
        try:
            return collapse_docstrings(lines)
        except SyntaxError:
            return lines  # unparseable: the fold alone is the comparison
    if rel.endswith(".lua"):
        lines = comment_stripped(lines, "--")
    return host_normalized(lines)


# --------------------------------------------------------------- comparison
def _source(package: str, rel: str) -> Optional[str]:
    """``<root>/<pkg>/<pkg>/<rel>`` if that file exists, else ``None``."""
    path = os.path.join(REPO, package, package, *rel.split("/"))
    return path if os.path.isfile(path) else None


def _read(path: str) -> List[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def extract_symbols(path: str, rel: str) -> Dict[str, List[str]]:
    """Map symbol name -> normalized source lines for every function and class in *path*.

    Keys are ``Class.method`` for a method and the bare name for a module-level
    function or a whole class (its decorators, fields and methods). All three,
    because a ledger entry may legitimately name any of them and a symbol this
    cannot see reports as ``missing`` -- which :func:`compare` treats as a
    FAILURE, so an invisible symbol is a permanently red entry rather than a
    merely unchecked one.

    TOP-LEVEL definitions only: a class nested in a class or a function defined
    inside another is not extracted, and a ledger naming one reports ``missing``
    -- loudly, which is the safe direction for a narrowing.

    Each function is dedented and normalized INDEPENDENTLY. Normalizing the
    whole file and slicing by line number does not work: ``collapse_docstrings``
    removes lines, so every line number after the first docstring is wrong.
    """
    raw = _read(path)
    try:
        tree = ast.parse("\n".join(raw))
    except SyntaxError:
        return {}
    out: Dict[str, List[str]] = {}

    def _add(key, fn):
        start = min([d.lineno for d in fn.decorator_list] + [fn.lineno])
        block = textwrap.dedent("\n".join(raw[start - 1 : fn.end_lineno]))
        out[key] = twin_normalized(block.splitlines(), rel)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # The class as a whole too -- decorators, fields and every method --
            # for a twin that is one small type (a dataclass both packages
            # return) rather than a few shared methods of a larger class.
            _add(node.name, node)
            for fn in node.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _add(f"{node.name}.{fn.name}", fn)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add(node.name, node)
    return out


def compare(spec: TwinSpec) -> Tuple[str, List[str]]:
    """Compare one ledger entry.

    Returns:
        ``(status, detail_lines)`` where status is ``ok``, ``drift``, ``missing``
        or ``absent``. ``absent`` means a sibling PACKAGE is not checked out,
        which is not a failure -- it is a narrower run. A checked-out package
        without the twin FILE is ``missing``: a rename or a deletion on one side
        must not retire the guard as a skip.
    """
    for pkg in (spec.a, spec.b):
        if not os.path.isdir(os.path.join(REPO, pkg, pkg)):
            return "absent", [f"{pkg} not checked out"]
    a_path, b_path = _source(spec.a, spec.rel), _source(spec.b, spec.rel)
    if a_path is None or b_path is None:
        which = spec.a if a_path is None else spec.b
        return "missing", [f"{spec.rel}: not found in {which}"]

    if spec.symbols is None:
        a = twin_normalized(_read(a_path), spec.rel)
        b = twin_normalized(_read(b_path), spec.rel)
        if a == b:
            return "ok", []
        diff = [
            ln
            for ln in difflib.unified_diff(a, b, spec.a, spec.b, lineterm="", n=1)
            if ln[:1] in "+- " and ln[:3] not in ("---", "+++")
        ]
        return "drift", diff

    a_syms, b_syms = (
        extract_symbols(a_path, spec.rel),
        extract_symbols(b_path, spec.rel),
    )
    detail, drifted, missing = [], [], []
    for name in spec.symbols:
        if name not in a_syms or name not in b_syms:
            where = spec.a if name not in a_syms else spec.b
            missing.append(f"{name}: not found in {where}")
            continue
        if a_syms[name] != b_syms[name]:
            drifted.append(name)
            detail.extend(
                ln
                for ln in difflib.unified_diff(
                    a_syms[name],
                    b_syms[name],
                    f"{spec.a}:{name}",
                    f"{spec.b}:{name}",
                    lineterm="",
                    n=0,
                )
                if ln[:1] in "+-" and ln[:3] not in ("---", "+++")
            )
    if missing:
        # A renamed or deleted symbol is drift of the worst kind: the guard
        # silently stops covering it. Never downgrade this to "ok".
        return "missing", missing + detail
    if drifted:
        return "drift", [f"drifted: {', '.join(drifted)}"] + detail
    return "ok", []


# ------------------------------------------------------------- written once
#: CODE_STANDARD section 3, guardrail 3: on the new layout a function body of
#: this many lines exists once -- across the layout, and between the layout and
#: the four libraries. Copies that call different hosts (a tool's two halves, the
#: mirror) are not copies; two over one host, or over none, are.
WRITTEN_ONCE_MIN_LINES = 8
NEW_LAYOUT = ("tentacle/tentacle/slots/tools",)
#: Composed Slots classes: the public modules at this folder's top level. The
#: ``_<panel>.py`` mixins and the per-host folders are unmoved code.
COMPOSED_SLOTS = "tentacle/tentacle/slots"
LIBRARIES = ("pythontk/pythontk", "uitk/uitk", "mayatk/mayatk", "blendertk/blendertk")
_HOST_NAMES = {
    "maya": frozenset({"maya", "cmds", "mel", "om", "om2", "pm", "pymel", "mtk", "mayatk"}),
    "blender": frozenset({"bpy", "bmesh", "mathutils", "btk", "blendertk"}),
}
#: Each toolkit's alias folds to one name, so a body that differs only by which
#: toolkit it calls compares equal -- and is then judged by the hosts it names.
_ALIAS_FOLD = ((re.compile(r"\b(?:mtk|btk)\b"), "_tk"), (re.compile(r"\b(?:mayatk|blendertk)\b"), "_tkpkg"))
_SKIP_DIRS = {"templates", "plugin_src", "__pycache__"}


def _released_files(workspace: str, top: str) -> List[str]:
    """The ``.py`` files under *top* (``<repo>/<path>``) a release would commit:
    tracked, or new and not ignored, so a generated ``*_ui.py`` is compared
    neither here nor in CI, whose checkout never has it. A tree outside git is
    walked whole."""
    base = os.path.join(workspace, *top.split("/"))
    if not os.path.isdir(base):
        return []
    repo, _, sub = top.partition("/")
    listed = subprocess.run(
        ["git", "-C", os.path.join(workspace, repo), "ls-files", "--cached",
         "--others", "--exclude-standard", "-z", "--", sub],
        capture_output=True, text=True, encoding="utf-8",
    )
    if listed.returncode == 0:
        rels = [rel for rel in listed.stdout.split("\0") if rel]
        paths = [os.path.join(workspace, repo, *rel.split("/")) for rel in rels]
    else:
        paths = [
            os.path.join(root, n)
            for root, _, names in os.walk(base)
            for n in names
        ]
    return [
        path for path in paths
        if path.endswith(".py")
        and os.path.isfile(path)
        and not _SKIP_DIRS & set(os.path.relpath(path, base).split(os.sep)[:-1])
    ]


def _layout_files(workspace: str) -> List[str]:
    files = [f for top in NEW_LAYOUT for f in _released_files(workspace, top)]
    slots = os.path.join(workspace, *COMPOSED_SLOTS.split("/"))
    files += [
        path for path in _released_files(workspace, COMPOSED_SLOTS)
        if os.path.dirname(path) == slots
        and not os.path.basename(path).startswith("_")
    ]
    return sorted(files)


def _library_files(workspace: str) -> List[str]:
    return sorted(f for top in LIBRARIES for f in _released_files(workspace, top))


def _host_of(body: List[ast.stmt]) -> Optional[str]:
    """The one host a body's code names, or None (none, or both)."""
    names = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.alias):
                names.add((node.asname or node.name).split(".")[0])
    hosts = [host for host, known in _HOST_NAMES.items() if names & known]
    return hosts[0] if len(hosts) == 1 else None


def function_bodies(path: str) -> List[Tuple[int, str, str, Optional[str]]]:
    """``(line, name, normalized body, host)`` for each function in *path* whose
    body, docstring dropped and reformatted, runs to the minimum length."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno - node.lineno < WRITTEN_ONCE_MIN_LINES:
            continue  # cheap: a body shorter in source is shorter unparsed too
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        if not body:
            continue
        text = ast.unparse(ast.Module(body=body, type_ignores=[]))
        if text.count("\n") + 1 < WRITTEN_ONCE_MIN_LINES:
            continue
        for pattern, neutral in _ALIAS_FOLD:
            text = pattern.sub(neutral, text)
        found.append((node.lineno, node.name, text, _host_of(body)))
    return found


def written_once_violations(
    workspace: Optional[str] = None, packages: Optional[Sequence[str]] = None
) -> List[str]:
    """Each body of the new layout that exists twice over one host (or over
    none), with every place it is written; empty while the layout is empty.
    Naming *packages* keeps the copies one of them writes a place of, so
    another package's uncommitted work never stops their release."""
    workspace = workspace or REPO
    run = None if not packages else set(packages)
    groups: Dict[str, List[Tuple[str, Optional[str]]]] = {}

    def record(path: str, keep_new: bool) -> None:
        rel = os.path.relpath(path, workspace).replace(os.sep, "/")
        for line, name, text, host in function_bodies(path):
            if keep_new or text in groups:
                groups.setdefault(text, []).append((f"{rel}:{line} {name}", host))

    for path in _layout_files(workspace):
        record(path, keep_new=True)
    if not groups:
        return []  # nothing on the new layout: no library needs reading
    for path in _library_files(workspace):
        record(path, keep_new=False)

    found = []
    for text, places in groups.items():
        by_host: Dict[Optional[str], List[str]] = {}
        for where, host in places:
            by_host.setdefault(host, []).append(where)
        for host, wheres in by_host.items():
            if len(wheres) > 1 and (
                run is None or {w.split("/", 1)[0] for w in wheres} & run
            ):
                lines = text.count("\n") + 1
                found.append(f"{' = '.join(sorted(wheres))}  ({lines} lines)")
    return sorted(found)


# ------------------------------------------------------------- host bindings
#: The library classes that bind a shared pythontk class to their host:
#: ``(pythontk module, shared class, ((package, module, binding class), ...))``,
#: paths relative to each package's inner source dir.
HOST_BINDINGS: Tuple[Tuple[str, str, Tuple[Tuple[str, str, str], ...]], ...] = (
    (
        "core_utils/engines/scene_export/scene_data_sidecar.py",
        "SceneDataSidecarBase",
        (
            ("mayatk", "env_utils/hierarchy_sync/scene_data_sidecar.py", "SceneDataSidecar"),
            ("blendertk", "env_utils/hierarchy_sync/scene_data_sidecar.py", "SceneDataSidecar"),
        ),
    ),
    (
        "core_utils/engines/scene_export/hierarchy_baseline.py",
        "HierarchyBaselineStore",
        (
            ("mayatk", "env_utils/hierarchy_sync/hierarchy_baseline.py", "HierarchyBaseline"),
            ("blendertk", "env_utils/hierarchy_sync/hierarchy_baseline.py", "HierarchyBaseline"),
        ),
    ),
    (
        "core_utils/engines/scene_export/scene_exporter.py",
        "SceneExporterBase",
        (
            ("mayatk", "env_utils/scene_exporter/_scene_exporter.py", "SceneExporter"),
            ("blendertk", "env_utils/scene_exporter/_scene_exporter.py", "SceneExporter"),
        ),
    ),
    (
        "geo_utils/probe_placement.py",
        "ProbePlacement",
        (
            ("mayatk", "light_utils/lightmap_baker/_probe_placement.py", "ProbePlacement"),
            ("blendertk", "light_utils/lightmap_baker/_probe_placement.py", "ProbePlacement"),
        ),
    ),
    (
        "geo_utils/curtain_drape.py",
        "CurtainDrape",
        (
            ("mayatk", "edit_utils/curtain/_curtain.py", "CurtainMesh"),
            ("blendertk", "edit_utils/curtain/_curtain.py", "CurtainMesh"),
        ),
    ),
    (
        "file_utils/workspace_map.py",
        "WorkspaceMapBase",
        (
            ("mayatk", "env_utils/workspace_map.py", "WorkspaceMap"),
            ("blendertk", "env_utils/workspace_map.py", "WorkspaceMap"),
        ),
    ),
)

#: What a class-body assignment makes a METHOD of, not configuration:
#: ``_close = classmethod(lambda ...)`` is a method as much as a ``def`` is.
_METHOD_WRAPPERS = frozenset({"staticmethod", "classmethod", "property", "partialmethod"})


def _is_method_value(value: Optional[ast.expr]) -> bool:
    if isinstance(value, ast.Lambda):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _METHOD_WRAPPERS
    return False


def class_members(path: str, name: str) -> Optional[Dict[str, Tuple[int, bool]]]:
    """``{member: (line, is_method)}`` the body of class *name* in *path* binds:
    each ``def``, and each assigned or annotated name -- a method when its value
    is a lambda or a ``staticmethod``/``classmethod``/``property`` wrap, else
    configuration. ``None`` when the file or the class is not there."""
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name == name):
            continue
        members: Dict[str, Tuple[int, bool]] = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members[item.name] = (item.lineno, True)
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                method = _is_method_value(item.value)
                for target in targets:
                    if isinstance(target, ast.Name):
                        members[target.id] = (item.lineno, method)
        return members
    return None


def host_binding_overrides(
    workspace: Optional[str] = None,
) -> Tuple[List[str], int, List[str]]:
    """``(failures, bindings checked, bindings absent)`` over
    :data:`HOST_BINDINGS`: each method of its shared pythontk class a binding
    class rebinds (by ``def`` or by assignment; configuration may be reset).
    Only a package that is not checked out is absent: a binding class gone from
    a checked-out package, or a shared class gone from a checked-out pythontk,
    is a failure -- the binding can no longer be held to the rule."""
    workspace = workspace or REPO
    failures: List[str] = []
    absent: List[str] = []
    checked = 0
    pythontk_root = os.path.join(workspace, "pythontk", "pythontk")
    for module, shared, bindings in HOST_BINDINGS:
        base = class_members(os.path.join(pythontk_root, *module.split("/")), shared)
        methods = {m for m, (_, is_method) in (base or {}).items() if is_method}
        for package, rel, name in bindings:
            label = f"{package}/{rel}::{name}"
            root = os.path.join(workspace, package, package)
            if not os.path.isdir(pythontk_root) or not os.path.isdir(root):
                absent.append(label)
                continue
            checked += 1
            if base is None:
                failures.append(
                    f"{label}  (shared class pythontk {module}::{shared} not found)"
                )
                continue
            own = class_members(os.path.join(root, *rel.split("/")), name)
            if own is None:
                failures.append(f"{label}  (binding class not found)")
                continue
            failures.extend(
                f"{label}.{member} (line {line}) overrides pythontk {shared}.{member}"
                for member, (line, _) in sorted(own.items())
                if member in methods
            )
    return failures, checked, absent


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 on drift (default: report and exit 0)",
    )
    parser.add_argument("--list", action="store_true", help="print the ledger")
    parser.add_argument(
        "--written-once",
        action="store_true",
        help="run only the new layout's written-once rule",
    )
    parser.add_argument("--workspace", default=None, help="the monorepo root")
    parser.add_argument(
        "packages",
        nargs="*",
        help="with --written-once: check only when one of these is tentacle or a library",
    )
    args = parser.parse_args(argv)

    if args.written_once:
        involved = {"tentacle"} | {top.split("/")[0] for top in LIBRARIES}
        if args.packages and not involved & set(args.packages):
            print("Written once: none of these packages is on the layout or a library.")
            return 0
        copies = written_once_violations(args.workspace, args.packages)
        for line in copies:
            print(f"  COPY    {line}")
        print(f"{len(copies)} body(ies) written twice on the new layout.")
        return 1 if copies and args.check else 0

    if args.list:
        for spec in LEDGER:
            print(f"{spec.label}\n    why:  {spec.reason}")
            if spec.note:
                print(f"    note: {spec.note}")
            if spec.symbols:
                for s in spec.symbols:
                    print(f"      - {s}")
            print()
        return 0

    bad, absent, checked = [], [], 0
    for spec in LEDGER:
        status, detail = compare(spec)
        if status == "absent":
            absent.append(spec.label)
            continue
        checked += 1
        if status == "ok":
            print(f"  ok      {spec.label}")
            continue
        bad.append((spec, status, detail))
        print(f"  {status.upper():<7} {spec.label}")
        for line in detail[:20]:
            print(f"            {line[:120]}")
        if len(detail) > 20:
            print(f"            ... {len(detail) - 20} more line(s)")

    for label in absent:
        print(f"  skipped {label}  (sibling not checked out)")

    copies = written_once_violations()
    for line in copies:
        print(f"  COPY    {line}")

    overrides, bound, unbound = host_binding_overrides()
    for line in overrides:
        print(f"  OVERRIDE {line}")
    for label in unbound:
        print(f"  skipped {label}  (sibling not checked out)")

    if not checked:
        # Same rule the sibling workflows apply to test counts: a run that
        # compared nothing is not a pass. Without this, a job whose checkout
        # silently lost a sibling reports green forever.
        print("\nFAIL: 0 twin(s) compared - nothing was checked out to compare.")
        return 1

    print(
        f"\n{checked} twin(s) compared, {len(bad)} with drift; "
        f"{len(copies)} body(ies) written twice on the new layout; "
        f"{bound} host binding(s), {len(overrides)} override(s)."
    )
    if overrides and args.check:
        print(
            "\nA host binding overrides its shared class. Move the host's half "
            "into the adapter\nthe shared class is injected with, never a "
            "subclass override (CODE_STANDARD.md §0)."
        )
    if copies and args.check:
        print(
            "\nA body on the new layout is written twice. Keep one copy -- the "
            "model, core/ or the\nlibrary that owns it -- and call it from the "
            "other place (CODE_STANDARD.md §3)."
        )
    if bad and args.check:
        print(
            "\nA declared twin has diverged. Either port the change to the other "
            "side,\nor narrow the ledger entry and record WHY the two may now "
            "differ.\nCODE_STANDARD.md §6: a vendored copy is sanctioned only "
            "while it is guarded."
        )
    if (bad or copies or overrides) and args.check:
        return 1
    if bad:
        print("(report mode: exit 0. Wire --check once the ledger is clear.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
