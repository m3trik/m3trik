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

Written once between the hosts
------------------------------
Host-free logic both DCC packages carry is written once, in pythontk
(CODE_STANDARD section 14), so the rule runs between mayatk and blendertk too: a
body of 8+ lines the two write over no host (or over the same one) is a copy,
unless the ledger guards it as a twin or another drift guard holds its file
(:data:`GUARDED_ELSEWHERE`). The copies older than the rule are frozen in
``check_dcc_twins_baseline.json``, one ``mayatk/<rel>::<name> =
blendertk/<rel>::<name>`` pair each; ``--check`` fails on a pair it does not list
and reports a listed one that no longer occurs. The baseline only shrinks:
``--written-once --update`` drops the paid pairs and never freezes a new one.

Host bindings
-------------
Host behavior is injected (an adapter), never a per-host subclass (CODE_STANDARD
section 0, Adapters). Where a library keeps its own name for a shared class
(pythontk's ``SceneDataSidecarBase`` as ``mtk.SceneDataSidecar``, uitk's
``PreviewController`` as ``mtk.Preview``), that class is a *binding*:
configuration (class attributes, the adapter it is bound to) and, where it is
the tool's API half, host-only additions -- but nothing in it, or ahead of the
shared class in its MRO, replaces a method the shared class or its lineage
defines (a library copy behind it is dead code, reported as SHADOWED). The
roster is derived, never hand-listed (CODE_STANDARD section 6): every mayatk /
blendertk class that derives from a pythontk or uitk class -- through the
package root (``ptk.X``, ``uitk.X``), a ``from`` import or a lazy export,
directly or through other classes of its library -- is a binding, unless that
base is a reasoned exemption (:data:`BINDING_EXEMPT`: template-method kits and
frameworks, bases not yet given an adapter) or declares itself one by name (a
seam's ``Pure<X>Host`` defaults, a ``<X>Mixin`` capability).
:data:`HOST_BINDINGS` documents the known pairs, and one the derivation misses
fails; an override fails ``--check``.

Usage
-----
    python m3trik/scripts/check_dcc_twins.py           # report (exit 0 always)
    python m3trik/scripts/check_dcc_twins.py --check   # exit 1 on drift
    python m3trik/scripts/check_dcc_twins.py --list    # print the ledger
    python m3trik/scripts/check_dcc_twins.py --written-once [--check] [pkg ...]
    python m3trik/scripts/check_dcc_twins.py --written-once --update  # drop paid copies

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
import json
import os
import re
import subprocess
import sys
import textwrap
import tokenize
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

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
    TwinSpec(
        rel="uv_utils/rizom_bridge/parameters.py",
        reason=(
            "The RizomUV bridge's Lua placeholder registry and its derived pack "
            "gutters: one text in both packages, mayatk's the SSoT, so a preset "
            "sent from either host reads the same knobs. RizomUV-specific, so "
            "the app-agnostic pythontk cannot host it; the gutter rule it calls "
            "is each host's own UvUtils, imported relatively."
        ),
        note=(
            "Whole file since 2026-10-29: the copies had drifted in prose only "
            "(blendertk also imported its UvUtils by package name)."
        ),
    ),
    TwinSpec(
        rel="uv_utils/rizom_bridge/_rizom_bridge.py",
        reason=(
            "The RizomUV bridge's host-free reads of the app itself -- its "
            "version (parsed from the install), the preset modes its templates "
            "offer, and why a clean exit wrote no FBX -- on the bridge class "
            "beside the scene I/O that differs. RizomUV-specific, so the "
            "app-agnostic pythontk cannot host them."
        ),
        symbols=(
            "_RizomUVBridgeInternal._parse_rizom_version",
            "RizomUVBridge.rizom_version",
            "RizomUVBridge.list_template_modes",
            "RizomUVBridge._no_save_diagnosis",
        ),
        note=(
            "4 shared methods (2026-10-29, the written-once rule's first pass; "
            "_no_save_diagnosis took mayatk's line wrapping). Export, send and "
            "the round trip read each host's scene."
        ),
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


#: The decorators that make a def another half of one property (``@v.setter``).
_ACCESSORS = ("getter", "setter", "deleter")


def _def_name(fn: ast.AST) -> str:
    """*fn*'s own name, a property accessor's with its half: ``v.setter`` for
    a def under ``@v.setter`` -- its getter (under ``@property``) is ``v``."""
    for deco in getattr(fn, "decorator_list", ()):
        if (
            isinstance(deco, ast.Attribute)
            and deco.attr in _ACCESSORS
            and isinstance(deco.value, ast.Name)
            and deco.value.id == fn.name
        ):
            return f"{fn.name}.{deco.attr}"
    return fn.name


def _unique(name: str, seen: Dict[str, int]) -> str:
    """*name* the first time a file defines it, ``name#k`` for its k-th
    definition (a def repeated in if/else or try branches)."""
    seen[name] = seen.get(name, 0) + 1
    return name if seen[name] == 1 else f"{name}#{seen[name]}"


def _named_defs(
    node: ast.AST,
    prefix: str = "",
    seen: Optional[Dict[str, int]] = None,
    nested: bool = True,
    in_class: bool = False,
):
    """Each class and function under *node*, in source order, with a qualified
    name no other definition in the file shares: ``Class.method``,
    ``outer.inner``, a property's halves apart (``C.v``, ``C.v.setter``) and a
    repeated def numbered (``C.v#2``). Without *nested*, only what a module and
    its top-level classes define, through their if/try blocks: no function
    inside a function, no class inside a class."""
    seen = {} if seen is None else seen
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            if in_class and not nested:
                continue
            name = _unique(f"{prefix}{child.name}", seen)
            yield name, child
            yield from _named_defs(child, f"{name}.", seen, nested, True)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = _unique(f"{prefix}{_def_name(child)}", seen)
            yield name, child
            if nested:
                yield from _named_defs(child, f"{name}.", seen, nested, False)
        else:
            yield from _named_defs(child, prefix, seen, nested, in_class)


def _covers(symbol: str, name: str) -> bool:
    """Whether a ledger *symbol* holds *name*: itself, its other halves and
    repeats (``C.v.setter``, ``C.v#2``), and what it encloses (a class its
    methods, a method its inner functions)."""
    return name == symbol or name.startswith((f"{symbol}.", f"{symbol}#"))


def _halves(symbol: str, names: Iterable[str]) -> List[str]:
    """The keys of *names* a ledger *symbol* compares: itself and its other
    definitions -- a property's accessors and a repeated def -- which a whole
    class or method text does not include."""
    pattern = re.compile(re.escape(symbol) + r"(\.(getter|setter|deleter))?(#\d+)?")
    return sorted(n for n in set(names) if pattern.fullmatch(n))


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
    -- loudly, which is the safe direction for a narrowing. Names are
    :func:`_named_defs`': a property's halves and a repeated def are keyed
    apart, so neither stands in for the other.

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

    # A class as a whole too -- decorators, fields and every method -- for a
    # twin that is one small type (a dataclass both packages return) rather
    # than a few shared methods of a larger class.
    for key, node in _named_defs(tree, nested=False):
        _add(key, node)
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
    names = [
        key
        for symbol in spec.symbols
        for key in (_halves(symbol, set(a_syms) | set(b_syms)) or [symbol])
    ]
    for name in names:
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


def _functions(node: ast.AST):
    """Each function under *node* with its qualified name, unique in the file
    (:func:`_named_defs`), in source order."""
    for name, child in _named_defs(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield name, child


def function_bodies(path: str) -> List[Tuple[int, str, str, Optional[str]]]:
    """``(line, qualified name, normalized body, host)`` for each function in
    *path* whose body, docstring dropped and reformatted, runs to the minimum
    length."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return []
    found = []
    for qualname, node in _functions(tree):
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
        found.append((node.lineno, qualname, text, _host_of(body)))
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


# ---------------------------------------------- written once between the hosts
#: The two DCC packages the written-once rule also holds to each other: host-free
#: logic both carry is written once, in pythontk (CODE_STANDARD section 14).
HOST_PACKAGES = ("mayatk", "blendertk")
#: Files another drift guard already compares, by path under each package's
#: source dir (a trailing ``/`` holds a folder), with that guard's path: the rule
#: leaves them to it.
_VENDOR_SYNC = "extapps/test/test_vendor_sync.py"
GUARDED_ELSEWHERE: Dict[str, str] = {
    # mirrored from m3trik/pm_doctor.py, the SSoT, beside package-manager.bat
    "env_utils/pm_doctor.py": "m3trik/scripts/sync_shared_bat.py",
    "env_utils/unity_bridge/parameters.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/_marmoset_engine.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/_toolbag_helpers.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/template_params.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/toolbag_log.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/parameters.py": _VENDOR_SYNC,
    "mat_utils/marmoset_bridge/marmoset_rpc/": _VENDOR_SYNC,
    "mat_utils/substance_bridge/_substance_engine.py": _VENDOR_SYNC,
    "mat_utils/substance_bridge/connection.py": _VENDOR_SYNC,
    "mat_utils/substance_bridge/parameters.py": _VENDOR_SYNC,
    "mat_utils/substance_bridge/substance_rpc/": _VENDOR_SYNC,
}
#: The copies older than the rule, under the workspace it was frozen from.
HOST_COPY_BASELINE = "m3trik/scripts/check_dcc_twins_baseline.json"


def _guarded_twin(a: Tuple[str, str], b: Tuple[str, str]) -> bool:
    """Whether a mayatk place and a blendertk place, each ``(rel, name)``, are
    one guarded twin: the same file on both sides, which another guard
    compares (:data:`GUARDED_ELSEWHERE`) or the ledger does -- whole, or as a
    symbol both are (:func:`_covers`). Two guards never excuse a copy between
    the files they hold."""
    (rel, name), (b_rel, b_name) = a, b
    if rel != b_rel:
        return False
    for path in GUARDED_ELSEWHERE:
        if rel == path or (path.endswith("/") and rel.startswith(path)):
            return True
    for spec in LEDGER:
        if spec.rel != rel or {spec.a, spec.b} != set(HOST_PACKAGES):
            continue
        if spec.symbols is None or (
            name == b_name and any(_covers(s, name) for s in spec.symbols)
        ):
            return True
    return False


def host_copies(workspace: Optional[str] = None) -> Dict[str, str]:
    """``{pair: detail}`` for each body mayatk and blendertk both write over no
    host (or over the same one), but for a guarded twin itself
    (:func:`_guarded_twin`). A pair reads ``mayatk/<rel>::<name> =
    blendertk/<rel>::<name>``: qualified names unique in each file
    (:func:`_named_defs`), never line numbers, so it survives an edit above
    it; three places make two pairs. Empty unless both packages are checked
    out."""
    workspace = workspace or REPO
    groups: Dict[Tuple[str, Optional[str]], Dict[str, list]] = {}
    for package in HOST_PACKAGES:
        base = os.path.join(workspace, package, package)
        if not os.path.isdir(base):
            return {}
        for path in _released_files(workspace, f"{package}/{package}"):
            rel = os.path.relpath(path, base).replace(os.sep, "/")
            for line, name, text, host in function_bodies(path):
                place = (rel, name, line)
                groups.setdefault((text, host), {}).setdefault(package, []).append(place)
    found: Dict[str, str] = {}
    a_pkg, b_pkg = HOST_PACKAGES
    for (text, _), places in groups.items():
        lines = text.count("\n") + 1
        for a_rel, a_name, a_line in places.get(a_pkg, ()):
            for b_rel, b_name, b_line in places.get(b_pkg, ()):
                if _guarded_twin((a_rel, a_name), (b_rel, b_name)):
                    continue
                key = f"{a_pkg}/{a_rel}::{a_name} = {b_pkg}/{b_rel}::{b_name}"
                found[key] = f"{lines} lines, at lines {a_line} / {b_line}"
    return found


def compared_elsewhere(workspace: Optional[str] = None) -> Dict[str, Set[str]]:
    """``{guard: the package paths it compares}`` for the guards
    :data:`GUARDED_ELSEWHERE` leaves files to, read from the guards themselves:
    ``sync_shared_bat.PAIRS``' mirrors, and each ``_DccPairSyncMixin`` case of
    extapps' vendor-sync test -- its ``subpath`` with each of its
    ``top_files``, and each of its ``subdirs`` as a folder (a trailing ``/``).
    A file a guard only lists (a host half it never compares) is in none; a
    guard that is not there compares nothing."""
    workspace = workspace or REPO
    out: Dict[str, Set[str]] = {}
    bat = os.path.join(workspace, "m3trik", "scripts", "sync_shared_bat.py")
    if os.path.isfile(bat):
        import importlib.util

        loader = importlib.util.spec_from_file_location("_twins_sync_shared_bat", bat)
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        held = out.setdefault("m3trik/scripts/sync_shared_bat.py", set())
        for _source, mirrors in module.PAIRS:
            for mirror in mirrors:
                for package in HOST_PACKAGES:
                    root = module.REPO_ROOT / package / package
                    if root in mirror.parents:
                        held.add(mirror.relative_to(root).as_posix())
    sync = os.path.join(workspace, *_VENDOR_SYNC.split("/"))
    if os.path.isfile(sync):
        with open(sync, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        consts: Dict[str, Any] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        consts[target.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
        held = out.setdefault(_VENDOR_SYNC, set())
        for node in tree.body:
            if not (
                isinstance(node, ast.ClassDef)
                and any(getattr(b, "id", None) == "_DccPairSyncMixin" for b in node.bases)
            ):
                continue
            attrs: Dict[str, Any] = {}
            for item in node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1:
                    target, value = item.targets[0], item.value
                    if isinstance(target, ast.Name):
                        if isinstance(value, ast.Name):
                            attrs[target.id] = consts.get(value.id, ())
                        else:
                            try:
                                attrs[target.id] = ast.literal_eval(value)
                            except ValueError:
                                pass
            sub = "/".join(attrs.get("subpath", ()))
            held.update(f"{sub}/{name}" for name in attrs.get("top_files", ()))
            held.update(f"{sub}/{name}/" for name in attrs.get("subdirs", ()))
    return out


def _host_copy_baseline_path(workspace: str) -> str:
    return os.path.join(workspace, *HOST_COPY_BASELINE.split("/"))


def load_host_copy_baseline(workspace: Optional[str] = None) -> List[str]:
    """The frozen pairs of *workspace*'s own baseline; none when it has none."""
    path = _host_copy_baseline_path(workspace or REPO)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(json.load(fh).get("copies", []))


def write_host_copy_baseline(copies: Sequence[str], workspace: Optional[str] = None) -> str:
    """Write *copies* as *workspace*'s baseline; returns its path."""
    path = _host_copy_baseline_path(workspace or REPO)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "_doc": (
            "Bodies mayatk and blendertk both write over no host, frozen when "
            "check_dcc_twins.py --written-once started holding them to the rule "
            "(CODE_STANDARD section 14: host-free logic is written once, in "
            "pythontk). Shrink it: move a copy to pythontk, or ledger it as a "
            "twin with its reason. --written-once --update drops the paid pairs; "
            "nothing adds one."
        ),
        "copies": sorted(set(copies)),
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=1) + "\n")
    return path


def _host_copy_state(
    workspace: Optional[str], packages: Optional[Sequence[str]]
) -> Optional[Tuple[Dict[str, str], List[str]]]:
    """``(copies, frozen pairs)``, or ``None`` when the rule does not apply: the
    run names neither host package, or one is not checked out."""
    workspace = workspace or REPO
    if packages and not set(HOST_PACKAGES) & set(packages):
        return None
    if not all(os.path.isdir(os.path.join(workspace, p, p)) for p in HOST_PACKAGES):
        return None
    return host_copies(workspace), load_host_copy_baseline(workspace)


def host_copy_findings(
    workspace: Optional[str] = None, packages: Optional[Sequence[str]] = None
) -> Tuple[List[str], List[str], List[str]]:
    """``(new, frozen, paid)`` pairs: a copy the baseline does not list, one it
    lists, and a listed one that no longer occurs. A run naming *packages* judges
    them only when one is mayatk or blendertk; nothing is judged unless both are
    checked out."""
    state = _host_copy_state(workspace, packages)
    if state is None:
        return [], [], []
    found, baseline = state
    frozen = set(baseline)
    return (
        sorted(k for k in found if k not in frozen),
        sorted(k for k in found if k in frozen),
        sorted(frozen - set(found)),
    )


# ------------------------------------------------------------- host bindings
#: The library classes known to bind a shared class to their host:
#: ``(shared module, shared class, ((package, module, binding class), ...))``,
#: paths relative to each package's inner source dir; a shared module is
#: pythontk's unless spelled ``"<package>:<path>"`` (``"uitk:..."``).
#: Documentation, and a check on the derivation: the bindings checked are
#: derived (:func:`derived_bindings`), so a binding missing here is checked all
#: the same.
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
    (
        "core_utils/engines/key_stash/key_stash_model.py",
        "KeyStash",
        (
            ("mayatk", "anim_utils/key_stash/_key_stash.py", "KeyStash"),
            ("blendertk", "anim_utils/key_stash/_key_stash.py", "KeyStash"),
        ),
    ),
    (
        "core_utils/engines/textures/emissive_groups.py",
        "EmissiveGroupsModel",
        (
            ("mayatk", "mat_utils/emissive_groups.py", "EmissiveGroups"),
            ("blendertk", "mat_utils/emissive_groups.py", "EmissiveGroups"),
        ),
    ),
    (
        "uitk:managers/preview_controller.py",
        "PreviewController",
        (
            ("mayatk", "core_utils/preview.py", "Preview"),
            ("blendertk", "core_utils/preview.py", "Preview"),
        ),
    ),
    (
        "vid_utils/sequence_exporter.py",
        "SequenceExporter",
        (
            ("mayatk", "anim_utils/playblast_exporter.py", "PlayblastExporter"),
            ("blendertk", "anim_utils/playblast_exporter.py", "PlayblastExporter"),
        ),
    ),
    # Its base, read apart (the check reads one class body): the encoder half
    # (``sequence_fps``, ``_notify``, ...) is shared too.
    (
        "vid_utils/sequence_exporter.py",
        "SequenceEncoder",
        (
            ("mayatk", "anim_utils/playblast_exporter.py", "PlayblastExporter"),
            ("blendertk", "anim_utils/playblast_exporter.py", "PlayblastExporter"),
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


def _members_of(node: ast.ClassDef) -> Dict[str, Tuple[int, bool]]:
    """``{member: (line, is_method)}`` the body of *node* binds (:func:`class_members`),
    a statement nested in it (``if`` / ``try`` / ``with`` / a loop / ``match``)
    included; a nested function's or class's own body is not the class's."""
    members: Dict[str, Tuple[int, bool]] = {}

    def walk(statements) -> None:
        for item in statements:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members[item.name] = (item.lineno, True)
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                method = _is_method_value(item.value)
                for target in targets:
                    if isinstance(target, ast.Name):
                        members[target.id] = (item.lineno, method)
            elif not isinstance(item, ast.ClassDef):
                for field in ("body", "orelse", "finalbody"):
                    walk(getattr(item, field, None) or ())
                for branch in getattr(item, "handlers", None) or ():
                    walk(branch.body)
                for branch in getattr(item, "cases", None) or ():
                    walk(branch.body)

    walk(node.body)
    return members


def class_members(path: str, name: str) -> Optional[Dict[str, Tuple[int, bool]]]:
    """``{member: (line, is_method)}`` the body of class *name* in *path* binds:
    each ``def``, and each assigned or annotated name -- a method when its value
    is a lambda or a ``staticmethod``/``classmethod``/``property`` wrap, else
    configuration. ``None`` when the file or the class is not there."""
    tree = _parse(path)
    for node in (tree or _NO_MODULE).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return _members_of(node)
    return None


# ------------------------------------------------------- the derived roster
#: The libraries whose classes are held to the binding rule: every class there
#: that derives from a shared class -- directly, or through other classes of
#: its library -- binds it, listed in :data:`HOST_BINDINGS` or not (CODE_STANDARD
#: section 6: a guard derives its roster, never a hand-listed subset).
BINDING_LIBRARIES = ("mayatk", "blendertk")
#: The packages whose classes the libraries share: host-free pythontk, and
#: uitk's generic Qt (``uitk.PreviewController``).
SHARED_PACKAGES = ("pythontk", "uitk")

#: The shared classes a library may subclass with overrides, and why: their
#: subclasses are not bindings. A *kit* is built to be specialized, its hooks
#: the extension points; an *unconverted* base still asks each host for a
#: per-host subclass and leaves this table when it gets an adapter, as
#: ``ShotStore`` and ``KeyStash`` did. Two kinds of base need no row, their
#: names declare them (:data:`_BY_NAME`): ``Pure<X>Host`` IS an adapter seam's
#: pure defaults, which the host adapter built on it overrides by design, and
#: ``<X>Mixin`` lends a capability several classes share (CODE_STANDARD
#: section 0), so a class using it is no host half of it.
BINDING_EXEMPT: Dict[str, str] = {
    "HandoffBridge": (
        "kit: the app-bridge Template-Method kit (core_utils/handoff) -- "
        "_produce / _deliver / params_defaults are the hooks a bridge fills"
    ),
    "ScriptLaunchBridge": "kit: the handoff kit's script-launch bridge (its templates)",
    "PreviewBridge": "kit: the handoff kit's preview bridge (net_utils/preview)",
    "Deliverer": "kit: the handoff kit's delivery strategy (deliver / preflight)",
    "RpcClient": (
        "kit: the generic JSON-RPC transport (net_utils/rpc) -- 'subclass to "
        "bind defaults for a specific DCC'"
    ),
    "TaskFactory": (
        "kit: the generic task pipeline -- a subclass is its task set, and "
        "extends __init__ / run_tasks through super()"
    ),
    "SchemaSpec": (
        "kit: the declarative template schema -- a spec is a dataclass of its "
        "fields, and 'override from_dict / to_dict' for an irregular shape is "
        "its documented extension point"
    ),
    "CancelProvider": (
        "kit: uitk's cancellation strategy -- 'base class for host providers: "
        "override only what the host can do' (each DCC's CancelProvider)"
    ),
    "ParamRegistry": (
        "kit: uitk's bridge parameter registry -- 'a registry whose rule "
        "differs overrides the method' and reaches the default through super()"
    ),
    "BaseHandler": (
        "kit: uitk's Switchboard handler framework (CONFIG_BRANCH, DEFAULTS, "
        "the singleton instance) a handler specializes"
    ),
    "UiHandler": (
        "kit: uitk's UI handler, specialized by each DCC's native-menu handler "
        "(construction, can_resolve / get / show)"
    ),
    "SceneStoreBase": (
        "unconverted: 'subclass with the primitives' (read / write / values) "
        "is its declared contract; DataNodes is each host's"
    ),
    "ShotManifest": (
        "unconverted: the manifest engine's per-host hooks (_apply_one, "
        "_key_samples, ...) on mayatk's ShotManifest / blendertk's BlenderShotManifest"
    ),
    "ShotSequencer": "unconverted: _ShotSequencerHooks, each host's ShotSequencer",
    "Behaviors": (
        "unconverted: each host's Behaviors re-binds the shared loops "
        "(apply_to_shots, compute_duration) with its own defaults"
    ),
}
_BY_NAME = (
    (re.compile(r"Pure\w*Host"), "an adapter over its seam's pure defaults"),
    (re.compile(r"\w*Mixin"), "a capability mixin: its user is no host half of it"),
)
_NO_MODULE = ast.Module(body=[], type_ignores=[])

#: A class as the derivation names it: ``(package, module, class)``, the module
#: dotted below the package (``""``: its ``__init__``).
_Key = Tuple[str, str, str]


def _parse(path: str) -> Optional[ast.Module]:
    try:
        with open(path, encoding="utf-8") as fh:
            return ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None


class _Source:
    """The ecosystem packages read as source: where each class a base names is
    defined -- through a package root (``ptk.X``, the root ``DEFAULT_INCLUDE``),
    a ``from`` import (absolute or relative), a ``lazy_exports`` package, or the
    module's own classes -- and each class's MRO over the classes it can
    resolve. Only the shared packages and the one a class lives in are followed;
    every other base (the standard library, Qt) is outside the rule. Parses
    each module once."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self._trees: Dict[Tuple[str, str], Optional[ast.Module]] = {}
        self._names: Dict[str, Dict[str, str]] = {}
        self._mro: Dict[_Key, List[_Key]] = {}
        self._classes: Dict[_Key, ast.ClassDef] = {}
        self._scopes: Dict[Tuple[str, str], tuple] = {}

    def root(self, package: str) -> str:
        return os.path.join(self.workspace, package, package)

    def path(self, package: str, dotted: str) -> Optional[str]:
        base = os.path.join(self.root(package), *dotted.split(".")) if dotted else self.root(package)
        for path in (base + ".py", os.path.join(base, "__init__.py")):
            if os.path.isfile(path):
                return path
        return None

    def tree(self, package: str, dotted: str) -> Optional[ast.Module]:
        if (package, dotted) not in self._trees:
            path = self.path(package, dotted)
            self._trees[package, dotted] = _parse(path) if path else None
        return self._trees[package, dotted]

    def names(self, package: str) -> Dict[str, str]:
        """``{root name: module}`` from *package*'s root ``DEFAULT_INCLUDE`` (a
        ``"*"`` module publishes its public classes)."""
        if package not in self._names:
            include: dict = {}
            for node in (self.tree(package, "") or _NO_MODULE).body:
                if (
                    isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == "DEFAULT_INCLUDE"
                ):
                    try:
                        include = ast.literal_eval(node.value)
                    except ValueError:
                        include = {}
            names: Dict[str, str] = {}
            for module, value in include.items():
                if value == "*":
                    for node in (self.tree(package, module) or _NO_MODULE).body:
                        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                            names[node.name] = module
                else:
                    for name in [value] if isinstance(value, str) else value:
                        names[name] = module
            self._names[package] = names
        return self._names[package]

    def scope(self, package: str, dotted: str):
        """``(imports, aliases, local classes)`` of a module: ``{local name:
        (package, module or None for its root, name)}`` for what it imports
        from a shared package or its own, ``{alias: package}`` for each root
        it imports whole (``import pythontk as ptk``), ``{name: ClassDef}``."""
        if (package, dotted) in self._scopes:
            return self._scopes[package, dotted]
        tree = self.tree(package, dotted)
        path = self.path(package, dotted) or ""
        followed = {*SHARED_PACKAGES, package}
        imports: Dict[str, Tuple[str, Optional[str], str]] = {}
        aliases: Dict[str, str] = {}
        for node in (tree or _NO_MODULE).body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in followed:
                        aliases[alias.asname or alias.name] = alias.name
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if node.level:
                parts = dotted.split(".") if dotted else []
                if not path.endswith("__init__.py"):
                    parts = parts[:-1]
                parts = parts[: len(parts) - (node.level - 1)]
                ref: Tuple[str, Optional[str]] = (
                    package, ".".join(parts + ([module] if module else []))
                )
            else:
                head, _, rest = module.partition(".")
                if head not in followed:
                    continue
                ref = (head, rest or None)
            for alias in node.names:
                imports[alias.asname or alias.name] = (ref[0], ref[1], alias.name)
        local = {n.name: n for n in (tree or _NO_MODULE).body if isinstance(n, ast.ClassDef)}
        self._scopes[package, dotted] = (imports, aliases, local)
        return imports, aliases, local

    def base_ref(self, package: str, dotted: str, base: ast.expr):
        """``(package, module or None, name)`` a base expression names, when it
        is a class of a shared package or of *package*; else ``None``."""
        imports, aliases, local = self.scope(package, dotted)
        if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            owner = aliases.get(base.value.id)
            return (owner, None, base.attr) if owner else None
        if isinstance(base, ast.Name):
            if base.id in imports:
                return imports[base.id]
            if base.id in local:
                return (package, dotted, base.id)
        return None

    def find(self, package: str, dotted: Optional[str], name: str, depth: int = 0):
        """The ``_Key`` of class *name* reached from *dotted* in *package*
        (``None``: its root) -- defined there, imported, or lazily exported --
        or ``None``."""
        if dotted is None:
            dotted = self.names(package).get(name)
        tree = self.tree(package, dotted) if dotted is not None and depth < 8 else None
        if tree is None:
            return None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                key = (package, dotted, name)
                self._classes[key] = node
                return key
        imports, _, _ = self.scope(package, dotted)
        if name in imports:
            return self.find(*imports[name], depth=depth + 1)
        for node in tree.body:  # a package's lazy_exports(globals(), {sub: names})
            call = node.value if isinstance(node, ast.Expr) else None
            if not (
                isinstance(call, ast.Call)
                and getattr(call.func, "id", None) == "lazy_exports"
                and len(call.args) > 1
            ):
                continue
            try:
                table = ast.literal_eval(call.args[1])
            except ValueError:
                continue
            for sub, exported in table.items():
                if name in ([exported] if isinstance(exported, str) else exported):
                    return self.find(package, f"{dotted}.{sub}", name, depth + 1)
        return None

    def node(self, key: _Key) -> ast.ClassDef:
        return self._classes[key]

    def bases(self, key: _Key) -> List[_Key]:
        """The resolved bases of *key*, in order (unresolvable ones dropped)."""
        found = []
        for base in self._classes[key].bases:
            ref = self.base_ref(key[0], key[1], base)
            hit = self.find(*ref) if ref is not None else None
            if hit is not None and hit != key:
                found.append(hit)
        return found

    def mro(self, key: _Key, _active: Optional[set] = None) -> List[_Key]:
        """*key*'s method resolution order over the classes the source
        resolves: C3, as Python computes it; a hierarchy C3 rejects (no running
        program has one) falls back to depth-first, first occurrence."""
        if key in self._mro:
            return self._mro[key]
        active = set() if _active is None else _active
        if key in active:
            return [key]  # a cycle on disk (a half-written file): stop here
        active.add(key)
        bases = self.bases(key)
        seqs = [list(self.mro(b, active)) for b in bases] + [list(bases)]
        merged: List[_Key] = [key]
        while any(seqs):
            head = next(
                (
                    s[0]
                    for s in seqs
                    if s and not any(s[0] in other[1:] for other in seqs)
                ),
                None,
            )
            if head is None:  # inconsistent: depth-first, first occurrence
                for seq in seqs:
                    merged.extend(k for k in seq if k not in merged)
                break
            merged.append(head)
            seqs = [[k for k in s if k != head] for s in seqs]
        active.discard(key)
        self._mro[key] = merged
        return merged


def _label(key: _Key, workspace_rel: Dict[_Key, str]) -> str:
    return workspace_rel.get(key) or f"{key[0]}/{key[1]}::{key[2]}"


def derived_bindings(
    workspace: Optional[str] = None,
) -> Tuple[Dict[str, dict], List[str], List[str]]:
    """``({label: binding}, failures, exempt)``: every class of
    :data:`BINDING_LIBRARIES` whose MRO reaches a shared class (of
    :data:`SHARED_PACKAGES`) through a base that neither :data:`BINDING_EXEMPT`
    nor a name rule (:data:`_BY_NAME`) exempts -- a direct base, or one reached
    through other classes of its library (a subclass of a binding binds it
    too).

    A binding is ``{"lineage": the shared classes' names,
    "overrides": [...], "shadowed": [...]}``. Members are read in MRO order: a
    library class ahead of the shared class that defines a shared method
    overrides it (reported once, where it is written: on the binding itself,
    or on the first binding over a mixin that is none); one behind it is dead
    code, shadowed, and reported as such. A base naming a shared class the
    source does not hold is a failure: the binding can no longer be held to
    the rule. *exempt* lists ``label <- base (reason)`` for each class's own
    exempt bases, for the report."""
    workspace = workspace or REPO
    src = _Source(workspace)
    bindings: Dict[str, dict] = {}
    failures: List[str] = []
    exempt: List[str] = []
    present = {p for p in SHARED_PACKAGES if os.path.isdir(src.root(p))}
    if not present:
        return bindings, failures, exempt
    rel: Dict[_Key, str] = {}
    classes: List[_Key] = []
    for package in BINDING_LIBRARIES:
        inner = src.root(package)
        for path in sorted(_released_files(workspace, f"{package}/{package}")):
            module_rel = os.path.relpath(path, inner).replace(os.sep, "/")
            dotted = module_rel[:-3].replace("/", ".")
            if dotted.endswith("__init__"):
                dotted = dotted[: -len("__init__")].rstrip(".")
            tree = src.tree(package, dotted)
            for node in (tree or _NO_MODULE).body:
                if isinstance(node, ast.ClassDef):
                    key = src.find(package, dotted, node.name)
                    if key is not None:
                        rel[key] = f"{package}/{module_rel}::{node.name}"
                        classes.append(key)

    def reason_for(name: str) -> Optional[str]:
        return BINDING_EXEMPT.get(name) or next(
            (why for rule, why in _BY_NAME if rule.fullmatch(name)), None
        )

    shared_of: Dict[_Key, set] = {}
    for key in classes:
        label = _label(key, rel)
        entries: List[_Key] = []
        for klass in src.mro(key):
            if klass[0] in SHARED_PACKAGES:
                continue
            for base in src.node(klass).bases:
                ref = src.base_ref(klass[0], klass[1], base)
                if ref is None or ref[0] not in present:
                    continue  # not a shared class (or its package is not checked out)
                hit = src.find(*ref)
                reason = reason_for(ref[2])
                if reason is not None:
                    if klass == key:
                        exempt.append(f"{label} <- {ref[2]}  ({reason})")
                    continue
                if hit is None:
                    if klass == key:
                        where = ref[1] or src.names(ref[0]).get(ref[2]) or "root"
                        failures.append(
                            f"{label}  (shared class {ref[0]} {where}::{ref[2]} not found)"
                        )
                    continue
                if hit not in entries:
                    entries.append(hit)
        shared = {k for entry in entries for k in src.mro(entry) if k[0] in SHARED_PACKAGES}
        if shared:
            shared_of[key] = shared
    for key, shared in shared_of.items():
        label = _label(key, rel)
        order = src.mro(key)
        members = {klass: _members_of(src.node(klass)) for klass in order}
        methods = {
            name
            for klass in shared
            for name, (_, is_method) in members[klass].items()
            if is_method
        }
        overrides, shadowed = [], []
        for name in sorted(methods):
            winner = next(k for k in order if name in members[k])
            definer = next(k for k in order if k in shared and name in members[k])
            for klass in order:
                if klass[0] in SHARED_PACKAGES or name not in members[klass]:
                    continue
                if klass != key and klass in shared_of:
                    continue  # that binding reports what it writes
                line = members[klass][name][0]
                where = "" if klass == key else f", in {_label(klass, rel)}"
                if klass == winner:
                    overrides.append(
                        f"{label}.{name} (line {line}{where}) overrides "
                        f"{definer[0]} {definer[2]}.{name}"
                    )
                elif order.index(klass) > order.index(definer):
                    shadowed.append(
                        f"{label}.{name} (line {line}{where}) is shadowed by "
                        f"{definer[0]} {definer[2]}.{name}: dead code"
                    )
        bindings[label] = {
            "lineage": {k[2] for k in shared},
            "overrides": overrides,
            "shadowed": shadowed,
        }
    return bindings, failures, exempt


def host_binding_overrides(
    workspace: Optional[str] = None, shadowed: Optional[List[str]] = None
) -> Tuple[List[str], int, List[str]]:
    """``(failures, bindings checked, bindings absent)``: each method of its
    shared classes (pythontk's, uitk's) a binding replaces in its MRO, by
    ``def`` or by assignment (configuration may be reset). *shadowed*, when
    given, collects the library copies the MRO never reaches (reported, not
    failed).

    The bindings are derived (:func:`derived_bindings`); :data:`HOST_BINDINGS`
    documents the known pairs, and a pair the derivation does not see is a
    failure -- the roster would be missing it. Only a package that is not
    checked out is absent: a binding class gone from a checked-out package, or
    a shared class gone from a checked-out shared package, is a failure -- the
    binding can no longer be held to the rule."""
    workspace = workspace or REPO
    bindings, failures, _ = derived_bindings(workspace)
    absent: List[str] = []
    seen = set(bindings)
    for module, shared, rows in HOST_BINDINGS:
        owner, _, module = module.rpartition(":")
        owner = owner or "pythontk"
        shared_root = os.path.join(workspace, owner, owner)
        for package, rel, name in rows:
            label = f"{package}/{rel}::{name}"
            root = os.path.join(workspace, package, package)
            if not os.path.isdir(shared_root) or not os.path.isdir(root):
                absent.append(label)
                continue
            seen.add(label)
            if label in bindings:
                if shared not in bindings[label]["lineage"]:
                    failures.append(
                        f"{label}  (declared over {owner} {shared}, which is not "
                        "in its shared lineage)"
                    )
                continue
            if any(f.startswith(f"{label}  ") for f in failures):
                continue  # already failed: its shared class is gone
            if class_members(os.path.join(shared_root, *module.split("/")), shared) is None:
                failures.append(
                    f"{label}  (shared class {owner} {module}::{shared} not found)"
                )
            elif class_members(os.path.join(root, *rel.split("/")), name) is None:
                failures.append(f"{label}  (binding class not found)")
            else:
                failures.append(
                    f"{label}  (declared, but no base of it resolves to {owner} "
                    f"{shared}: the derived roster misses it)"
                )
    for label, binding in sorted(bindings.items()):
        failures.extend(binding["overrides"])
        if shadowed is not None:
            shadowed.extend(binding["shadowed"])
    return failures, len(seen), absent


_HOST_COPY_HINT = (
    "\nmayatk and blendertk both write a body that names no host. Move it to "
    "pythontk and call it\nfrom both (host-free logic is written once there, "
    "CODE_STANDARD.md §14), or ledger it\nas a twin with the reason it cannot "
    "move (§6)."
)


def _print_host_copies(state: Optional[Tuple[Dict[str, str], List[str]]]) -> List[str]:
    """Print the host copies outside the baseline and the paid pairs; returns the new ones."""
    if state is None:
        return []
    found, baseline = state
    frozen = set(baseline)
    new = sorted(k for k in found if k not in frozen)
    for key in new:
        print(f"  HOST    {key}  ({found[key]})")
    for key in sorted(frozen - set(found)):
        print(f"  PAID    {key}  no longer written twice (--written-once --update drops it)")
    return new


def _host_copy_summary(state: Optional[Tuple[Dict[str, str], List[str]]]) -> str:
    if state is None:
        return "host copies not compared (a host package is not in the run)"
    found, baseline = state
    frozen = set(baseline)
    new = sum(1 for k in found if k not in frozen)
    paid = len(frozen - set(found))
    return (
        f"{new} host copy(ies) outside the baseline "
        f"({len(found) - new} frozen, {paid} paid)"
    )


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
    parser.add_argument(
        "--update",
        action="store_true",
        help="with --written-once: drop the baseline's paid host copies (adds none)",
    )
    parser.add_argument("--workspace", default=None, help="the monorepo root")
    parser.add_argument(
        "packages",
        nargs="*",
        help="with --written-once: check only when one of these is tentacle or a library",
    )
    args = parser.parse_args(argv)
    if args.update and not args.written_once:
        parser.error("--update needs --written-once")
    if args.update and args.packages:
        parser.error("--update rewrites the whole baseline: name no packages")

    if args.written_once:
        involved = {"tentacle"} | {top.split("/")[0] for top in LIBRARIES}
        if args.packages and not involved & set(args.packages):
            print("Written once: none of these packages is on the layout or a library.")
            return 0
        copies = written_once_violations(args.workspace, args.packages)
        for line in copies:
            print(f"  COPY    {line}")
        state = _host_copy_state(args.workspace, args.packages)
        new = _print_host_copies(state)
        if args.update:
            if state is not None:
                found, baseline = state
                kept = sorted(set(baseline) & set(found))
                path = write_host_copy_baseline(kept, args.workspace)
                print(f"[WROTE] {path}: {len(kept)} frozen host copy(ies)")
            return 1 if new else 0
        print(
            f"{len(copies)} body(ies) written twice on the new layout; "
            f"{_host_copy_summary(state)}."
        )
        if new and args.check:
            print(_HOST_COPY_HINT)
        return 1 if (copies or new) and args.check else 0

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
    host_state = _host_copy_state(None, None)
    host_new = _print_host_copies(host_state)

    shadowed: List[str] = []
    overrides, bound, unbound = host_binding_overrides(shadowed=shadowed)
    for line in overrides:
        print(f"  OVERRIDE {line}")
    for line in shadowed:  # dead code the MRO never reaches: reported, not failed
        print(f"  SHADOWED {line}")
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
        f"{_host_copy_summary(host_state)}; "
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
    if host_new and args.check:
        print(_HOST_COPY_HINT)
    if bad and args.check:
        print(
            "\nA declared twin has diverged. Either port the change to the other "
            "side,\nor narrow the ledger entry and record WHY the two may now "
            "differ.\nCODE_STANDARD.md §6: a vendored copy is sanctioned only "
            "while it is guarded."
        )
    if (bad or copies or host_new or overrides) and args.check:
        return 1
    if bad:
        print("(report mode: exit 0. Wire --check once the ledger is clear.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
