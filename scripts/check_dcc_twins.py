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
                2026-09-16, ``gap_manager.py`` has 7 of 14 methods identical
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
            both sides (``anim_utils/shots/.../gap_manager.py``).
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
        rel="anim_utils/shots/shot_sequencer/marker_manager.py",
        reason=(
            "Shot-sequencer panel controller. DCC-agnostic marker bookkeeping over "
            "the shared pythontk shots engine, but it is Qt-side, so pythontk "
            "cannot host it and there is no shared uitk panel tier yet."
        ),
        symbols=(
            "MarkerManagerMixin._rebuild_markers_store",
            "MarkerManagerMixin.on_marker_changed",
            "MarkerManagerMixin.on_marker_moved",
            "MarkerManagerMixin.on_marker_removed",
            "_MarkerManagerMixinInternal._marker_to_dict",
        ),
        note=(
            "5 of 6 methods identical. on_marker_added genuinely differs. The file "
            "is 4 normalized lines from whole-file guardable and all 4 are ONE "
            "comment re-wrapped differently -- reconcile that wrap and this entry "
            "can drop its symbol list."
        ),
    ),
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/gap_manager.py",
        reason=(
            "Shot-sequencer gap arithmetic, same tier and same reason as "
            "marker_manager: Qt-side controller over a shared engine."
        ),
        symbols=(
            "GapManagerMixin._drag_modifiers",
            "GapManagerMixin._find_shot_by_end",
            "GapManagerMixin._find_shot_by_start",
            "GapManagerMixin._gap_edit_epilogue",
            "GapManagerMixin._gap_pair_at",
            "GapManagerMixin._refuse_if_gap_locked",
            "GapManagerMixin.on_gap_lock_all",
            "GapManagerMixin.on_gap_unlock_all",
        ),
        note=(
            "8 of 13 methods identical (re-measured 2026-10-10). Both stores now "
            "bracket edits in store.scene_edit(label); the other 5 differ on the "
            "label each host shows (mayatk's chunk ids 'gapresize' / 'shotmove', "
            "Blender's undo-history names 'Resize Gap' / 'Move Shot'), comment "
            "wording, one debug log (on_gap_lock_changed) and a signature wrap "
            "(on_gap_moved). Reconcile the comments and the log and only the "
            "labels remain."
        ),
    ),
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/shot_nav.py",
        reason=(
            "Shot-sequencer navigation controller, same tier and same reason as "
            "the other two: it drives Qt widgets over the shared pythontk shots "
            "engine, so neither pythontk (no Qt) nor uitk (no shot semantics) "
            "can host it today."
        ),
        symbols=(
            "ShotNavMixin._configure_shot_combobox",
            "ShotNavMixin._go_to_shot",
            "ShotNavMixin._land_on_shot",
            "ShotNavMixin._set_playhead_to_shot_start",
            "ShotNavMixin._sync_combobox",
            "ShotNavMixin._update_shot_nav_state",
            "ShotNavMixin.on_shot_block_clicked",
        ),
        note=(
            "7 of 11 methods identical (re-measured 2026-10-12). The other 4 wrap "
            "real DCC calls (playback range, navigation, selection, cell edits) "
            "and are expected to differ."
        ),
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
    TwinSpec(
        rel="uv_utils/texture_combine/_transfer_mode.py",
        reason=(
            "Transfer mode's host-free decisions (which passes run, Auto "
            "source, pairing, the gate): tentacle's UvMixin carried them once; "
            "each panel now carries them, so they are guarded to stay one rule."
        ),
        symbols=(
            "_TransferMode.passes",
            "_TransferMode.resolve_auto",
            "_TransferMode.pair",
        ),
        note=(
            "Measured identical 2026-10-19. auto_source and gate share their "
            "logic but word it per host (UV Set vs UV Map); the scene reads and "
            "writes differ."
        ),
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
        rel="anim_utils/shots/shots_slots.py",
        reason=(
            "Shots panel controller + slots: Qt glue over the pythontk shots engine "
            "(ShotReport words the footer). Same tier and reason as the manifest "
            "controller."
        ),
        symbols=(
            "ShotsController.__init__",
            "ShotsController._active_shot_name",
            "ShotsController._active_store",
            "ShotsController._apply_snap_to_spinboxes",
            "ShotsController._bind_store_listener",
            "ShotsController._index_to_mode",
            "ShotsController._mode_to_index",
            "ShotsController._on_shot_name_refused",
            "ShotsController._on_store_event",
            "ShotsController._on_store_invalidated",
            "ShotsController._option_checked",
            "ShotsController._populate_shot_combobox",
            "ShotsController._push_shot_field",
            "ShotsController._relabel_shot_row",
            "ShotsController._report_deltas",
            "ShotsController._set_footer",
            "ShotsController._setup_delete_menu",
            "ShotsController._setup_gap_menu",
            "ShotsController._setup_hide_on_leave",
            "ShotsController._setup_move_menu",
            "ShotsController._setup_shift_menu",
            "ShotsController._setup_shot_nav",
            "ShotsController._setup_space_menu",
            "ShotsController._setup_trim_menu",
            "ShotsController._shot_name_error",
            "ShotsController._shot_row",
            "ShotsController._sync_footer",
            "ShotsController._sync_from_store",
            "ShotsController._sync_shot_editor",
            "ShotsController._unbind_store_listener",
            "ShotsController._update_shot_nav_state",
            "ShotsController.confirm_removal",
            "ShotsController.delete_scope",
            "ShotsController.label_apply_gap",
            "ShotsController.label_delete_shots",
            "ShotsController.label_shift_all",
            "ShotsController.on_add_space",
            "ShotsController.on_delete_shots",
            "ShotsController.on_detection_changed",
            "ShotsController.on_detection_mode_changed",
            "ShotsController.on_fit_mode_changed",
            "ShotsController.on_gap_changed",
            "ShotsController.on_initial_length_changed",
            "ShotsController.on_move_shot",
            "ShotsController.on_navigate_shot",
            "ShotsController.on_new_shot",
            "ShotsController.on_shift_all_shots",
            "ShotsController.on_shot_desc_changed",
            "ShotsController.on_shot_end_changed",
            "ShotsController.on_shot_name_changed",
            "ShotsController.on_shot_selected",
            "ShotsController.on_shot_start_changed",
            "ShotsController.on_snap_whole_frames_changed",
            "ShotsController.on_trim_all_shots",
            "ShotsController.on_trim_empty",
            "ShotsController.refresh_state",
            "ShotsController.remove_callbacks",
            "ShotsController.scope_count",
            "ShotsController.scope_label",
            "ShotsController.shot_label",
            "ShotsSlots.__init__",
            "ShotsSlots.b000",
            "ShotsSlots.btn_add_leading_space",
            "ShotsSlots.btn_add_trailing_space",
            "ShotsSlots.btn_apply_gap",
            "ShotsSlots.btn_delete_shots",
            "ShotsSlots.btn_move_shot",
            "ShotsSlots.btn_shift_all",
            "ShotsSlots.btn_trim_all",
            "ShotsSlots.btn_trim_all_both",
            "ShotsSlots.btn_trim_all_leading",
            "ShotsSlots.btn_trim_all_trailing",
            "ShotsSlots.btn_trim_both",
            "ShotsSlots.btn_trim_empty",
            "ShotsSlots.btn_trim_leading",
            "ShotsSlots.btn_trim_trailing",
            "ShotsSlots.chk_snap_whole_frames",
            "ShotsSlots.cmb_delete_scope",
            "ShotsSlots.cmb_detection_mode",
            "ShotsSlots.cmb_fit_mode",
            "ShotsSlots.cmb_shot_select",
            "ShotsSlots.spn_detection",
            "ShotsSlots.spn_initial_length",
            "ShotsSlots.spn_shot_end",
            "ShotsSlots.spn_shot_start",
            "ShotsSlots.txt_shot_desc",
            "ShotsSlots.txt_shot_name",
        ),
        note=(
            "87 of 96 shared methods (re-measured 2026-10-12). The other 9 differ "
            "on the undo bracket (_boundary_edit: mayatk's store.scene_edit vs "
            "blendertk's snapshot + CoreUtils.undo_chunk, and on_delete_shot built "
            "on it), host prose (confirm_stale_removal, _setup_delete_shots_menu, "
            "header_init's tooltips), the _store_cls / _sequencer_cls hooks "
            "themselves, and the retired on_delete_all_shots / "
            "on_delete_stale_shots aliases, whose Deprecation remove_in is each "
            "package's own version. btn_delete_all / btn_delete_stale left both "
            "panels on 2026-10-10 for one btn_delete_shots."
        ),
    ),
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/widget_sync.py",
        reason=(
            "Shot Sequencer widget-sync mixin (split from shot_sequencer_slots.py "
            "2026-09-26): Qt glue between the sequencer widget and each host's scene."
        ),
        symbols=(
            "WidgetSyncMixin._apply_view",
            "WidgetSyncMixin._drop_caches",
            "WidgetSyncMixin._on_editor_changed",
            "WidgetSyncMixin._on_frame_on_shot_change_toggled",
            "WidgetSyncMixin._on_select_on_load_toggled",
            "WidgetSyncMixin._rebuild_content",
            "WidgetSyncMixin._resolve_sync_target",
            "WidgetSyncMixin._restore_viewport",
            "WidgetSyncMixin._save_viewport_state",
            "WidgetSyncMixin._set_cmb_mode",
            "WidgetSyncMixin._set_playback_range_mode",
            "WidgetSyncMixin._set_show_internal_holds",
            "WidgetSyncMixin._set_view",
            "WidgetSyncMixin._set_view_mode",
            "WidgetSyncMixin._sync_to_widget",
            "WidgetSyncMixin._visible_shots",
            "WidgetSyncMixin.refresh",
        ),
        note=(
            "17 of 25 shared methods (re-measured 2026-10-12). The other 8 differ "
            "in code: each builds its tracks, clips, audio rows and sub-rows from "
            "its own scene, colors its own scene attributes, and keeps its own "
            "decoration, header and shotless state."
        ),
    ),
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
        rel="anim_utils/shots/shot_sequencer/shot_sequencer_slots.py",
        reason=(
            "Shot Sequencer panel slots: Qt glue over the shared engine, one per "
            "host because each wires its own controller."
        ),
        symbols=(
            "ShotSequencerSlots._delete_shot",
            "ShotSequencerSlots._edit_shot_in_settings",
            "ShotSequencerSlots._on_cmb_mode_changed",
            "ShotSequencerSlots._on_playback_range_changed",
            "ShotSequencerSlots._on_shortcut_overlay_changed",
            "ShotSequencerSlots._on_snap_to_keys_toggled",
            "ShotSequencerSlots._on_track_order_changed",
            "ShotSequencerSlots._register_track_options",
            "ShotSequencerSlots._set_help",
            "ShotSequencerSlots._view_option",
            "ShotSequencerSlots.btn_shortcuts",
            "ShotSequencerSlots.btn_shot_settings",
        ),
        note=(
            "12 of 21 shared methods (re-measured 2026-10-12): the View menu pair, "
            "the header help (one guide for both hosts) and the option and button "
            "handlers. The other 9 differ in their host's undo, shortcut and "
            "dialog wiring (__init__, header_init, the shot combo and its context "
            "menu, shot detection and navigation, colors, the snap spinbox, "
            "ShotEditDialog.show)."
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
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/key_menu.py",
        reason=(
            "Shot Sequencer key-menu mixin: the rows a key selection gets from "
            "any view, and how a key shortcut finds the selection of a view "
            "other than the track rows (the graph's)."
        ),
        symbols=(
            "KeyMenuMixin._add_selection_key_actions",
            "KeyMenuMixin._claims_follow",
            "KeyMenuMixin._copy_keys_shortcut",
            "KeyMenuMixin._key_scene_edit",
            "KeyMenuMixin._key_selection_edit",
            "KeyMenuMixin._key_targets",
            "KeyMenuMixin._key_targets_to_sequences",
            "KeyMenuMixin._paste_keys_shortcut",
            "KeyMenuMixin._selected_key_targets",
            "KeyMenuMixin._target_objects",
            "KeyMenuMixin._target_span",
            "KeyMenuMixin.register_key_targets",
        ),
        note=(
            "12 of 29 shared methods (re-measured 2026-10-12): the selection rows, "
            "the key targets and their edit brackets, the copy / paste shortcuts. "
            "The tangent rows and the key operations themselves differ (Maya "
            "tangent types and animCurves; Blender handle types, interpolation "
            "and fcurves)."
        ),
    ),
    TwinSpec(
        rel="anim_utils/shots/shot_sequencer/scene_selection.py",
        reason=(
            "Shot Sequencer selection mixin: the footer's key-selection line "
            "(2026-10-10), the widget's clips read into the shared "
            "pythontk ShotSequencer.describe_key_selection."
        ),
        symbols=(
            "SceneSelectionMixin._select_target_keys",
            "SceneSelectionMixin._show_key_selection",
            "SceneSelectionMixin.on_header_menu",
        ),
        note=(
            "3 of 20 shared methods (re-measured 2026-10-12); the rest mirror each "
            "host's selection (Maya's selectKey / Channel Box vs Blender's "
            "keyframe points and channels)."
        ),
    ),
    TwinSpec(
        rel="mat_utils/render_opacity/render_effects_slots.py",
        reason=(
            "Render Effects panel controller: Qt glue binding the effect pages to "
            "the scene's effect recipe (pythontk EffectRecipe, through uitk's "
            "ModelBinding and FormRows). uitk names no render effects and "
            "pythontk hosts no Qt, so the glue is mirrored in both DCC packages."
        ),
        symbols=(
            "RenderEffectsSlots._add_settings",
            "RenderEffectsSlots._clear_report",
            "RenderEffectsSlots._fade_preview_plan",
            "RenderEffectsSlots._fit_stack",
            "RenderEffectsSlots._on_mode_changed",
            "RenderEffectsSlots._on_scene_selection",
            "RenderEffectsSlots._pulse_preview_plan",
            "RenderEffectsSlots._recipe_values",
            "RenderEffectsSlots._refit",
            "RenderEffectsSlots._show_recipe_colors",
            "RenderEffectsSlots._shown_channel",
            "RenderEffectsSlots._shown_page",
            "RenderEffectsSlots._spin_value",
            "RenderEffectsSlots._stop_watching",
            "RenderEffectsSlots._sync_pulse_shape",
            "RenderEffectsSlots._update_cycle_readout",
            "RenderEffectsSlots._write_recipe",
            "RenderEffectsSlots.b000",
            "RenderEffectsSlots.ui_field",
            "RenderEffectsSlots.unfocus",
        ),
        note=(
            "20 of 63 shared methods (re-measured 2026-10-12). The rest speak "
            "host vocabulary: mayatk keys a "
            "channel by ChannelSpec and blendertk by name, and selection, undo, "
            "the current frame and the WebXR push are each host's own."
        ),
    ),
    TwinSpec(
        rel="edit_utils/naming/naming_slots.py",
        reason=(
            "The Naming panel. Its Suffix By Type editor lives once in uitk "
            "(NamingConventionEditor); what stays here is host glue handing it data "
            "(_convention_groups / _convention_tooltip / tb003_init, the host "
            "difference expressed as CONVENTION_DISABLED) plus the shared operation "
            "slots."
        ),
        symbols=(
            "NamingSlots._add_apply_button",
            "NamingSlots._apply_dry_run",
            "NamingSlots._arm_apply",
            "NamingSlots._begin",
            "NamingSlots._convention_groups",
            "NamingSlots._convention_tooltip",
            "NamingSlots._disarm_apply",
            "NamingSlots._file_targets",
            "NamingSlots._follow_renames",
            "NamingSlots._log_directories",
            "NamingSlots._on_scope_changed",
            "NamingSlots._report_found",
            "NamingSlots._run",
            "NamingSlots._run_on_files",
            "NamingSlots._scene_only",
            "NamingSlots._sync_scope_options",
            "NamingSlots.base_names",
            "NamingSlots.dry_run",
            "NamingSlots.file_scope",
            "NamingSlots.scope",
            "NamingSlots.tb000",
            "NamingSlots.tb000_init",
            "NamingSlots.tb001_init",
            "NamingSlots.tb002",
            "NamingSlots.tb002_init",
            "NamingSlots.tb003",
            "NamingSlots.tb003_init",
            "NamingSlots.txt001",
            "NamingSlots.txt001_init",
            "NamingSlots.valid_suffixes",
        ),
        note=(
            "30 of 38 shared methods. The rest differ on host vocabulary: the scope "
            "scan, the file browser, Locators vs Empties, the find/select report."
        ),
    ),
    TwinSpec(
        rel="rig_utils/articulated_rig/articulated_rig_slots.py",
        reason=(
            "The Articulated Rig panel: Qt glue over each host's ArticulatedRig "
            "engine (the plan edits and the table's limits / give text are pythontk's "
            "ArticulationPlan). uitk names no rig and pythontk hosts no Qt, so the "
            "glue is mirrored in both DCC packages over one .ui (mayatk's, byte for "
            "byte)."
        ),
        symbols=(
            "ArticulatedRigSlots._entry",
            "ArticulatedRigSlots._init_table",
            "ArticulatedRigSlots._on_end_control_toggled",
            "ArticulatedRigSlots._on_item_changed",
            "ArticulatedRigSlots._reporting",
            "ArticulatedRigSlots._retype",
            "ArticulatedRigSlots._selected_joints",
            "ArticulatedRigSlots._selected_rig",
            "ArticulatedRigSlots._set_give",
            "ArticulatedRigSlots._set_limits",
            "ArticulatedRigSlots._sync_adjust",
            "ArticulatedRigSlots.btn_clear_limits",
            "ArticulatedRigSlots.btn_fold",
            "ArticulatedRigSlots.btn_grab",
            "ArticulatedRigSlots.btn_ik_fk",
            "ArticulatedRigSlots.btn_ik_fk_init",
            "ArticulatedRigSlots.btn_limits_from_pose",
            "ArticulatedRigSlots.btn_rebuild",
            "ArticulatedRigSlots.btn_remove",
            "ArticulatedRigSlots.btn_rest",
            "ArticulatedRigSlots.match_end_control",
            "ArticulatedRigSlots.parse_limits",
        ),
        note=(
            "22 of 36 shared methods (measured 2026-10-17). The rest speak host "
            "vocabulary: Maya selects a control transform, Blender a bone in Pose "
            "Mode (blendertk's _selection / _select / _parts_of); a Blender part is "
            "named by its object, not a DAG path; blendertk defers its Qt imports, "
            "arms the selection-order tracker on open, and its help says Auto Keying."
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
        ),
        note=(
            "10 of 25 shared methods (re-measured 2026-10-12; delivery, the "
            "template render and the Toolbag and source-model paths joined); "
            "export, cage, assignment and retirement read each host's scene "
            "(blendertk swaps the baked material per slot)."
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

    if not checked:
        # Same rule the sibling workflows apply to test counts: a run that
        # compared nothing is not a pass. Without this, a job whose checkout
        # silently lost a sibling reports green forever.
        print("\nFAIL: 0 twin(s) compared - nothing was checked out to compare.")
        return 1

    print(
        f"\n{checked} twin(s) compared, {len(bad)} with drift; "
        f"{len(copies)} body(ies) written twice on the new layout."
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
    if (bad or copies) and args.check:
        return 1
    if bad:
        print("(report mode: exit 0. Wire --check once the ledger is clear.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
