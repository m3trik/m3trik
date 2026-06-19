#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mechanically diff the *control surface* of a mayatk panel against its blendertk twin.

The PARITY_AUDIT measures depth with numbers; it does NOT tell you *which specific* header
options, option-box controls, config buttons, or slot methods exist in one panel and not the
other. That name-level blind spot is how header options went "flat out missing" unnoticed.

This extracts, from each Slots file (pure AST — no import needed):
  * ``config_buttons(...)`` string args         (header chrome: refresh / menu / collapse / hide)
  * every ``*.menu.add(...)`` / ``option_box.menu.add(...)`` control, keyed by ``setObjectName``
    (falling back to its label / type) — the header menu, option-box menus, and table context menu
  * presence of ``set_toggle`` / ``pin`` / ``add_presets`` (option-box + preset affordances)
  * slot/handler ``def`` names

…then prints what mayatk has that blendertk lacks (and vice-versa). Intentional Blender
divergences are expected in the output — the point is to make every delta a *conscious* decision
instead of an accident.

Usage:
    python compare_panel_surface.py mayatk/.../reference_manager.py blendertk/.../reference_manager.py
    python compare_panel_surface.py --panel reference_manager      # resolve both by convention
"""
from __future__ import annotations
import ast
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# objectNames / config-buttons / labels that are deliberately Maya-only (no Blender surface).
# Keep this small + justified; it documents *why* a delta is acceptable.
KNOWN_MAYA_ONLY = {
    "rizom_bridge_slots": {
        # blendertk's RizomUV bridge is intentionally thin: it subclasses the
        # engine directly (not BridgeSlotsBase) for a one-way send with no
        # script-template / round-trip machinery, so it ships help text and no
        # header menu. The mayatk panel's full Utilities menu is Maya-only.
        "btnopen_uv_editor": "thin Blender bridge has no header menu (help-text only)",
        "btn_open_scripts": "no Lua script-template machinery in the thin Blender bridge",
        "btn_refresh_scripts": "no Lua script-template machinery in the thin Blender bridge",
        "btn_clear_log": "thin Blender bridge has no header menu (help-text only)",
    },
    "reference_manager": {
        "btn_convert_assembly": "assemblies have no Blender analogue",
        "btn_unlink_import_all": "renamed -> btn_make_local_all (Blender 'make local')",
        "btn_unreference_all": "renamed -> btn_remove_all",
        "btn_unlink_import": "row action -> 'Make Local' (make_library_local)",
        "btn_toggle_reference": "row action -> link icon + 'Link'/'Append'",
        "b001": "renamed -> btn_set_current_ws (root option box)",
        "b006": "renamed -> btn_open_dir (root option box)",
        "btn_open_scene": "renamed -> row_open (context menu)",
        "btn_rename_scene": "renamed -> row_rename (context menu)",
        "btn_delete_scene": "renamed -> row_delete (context menu)",
        "btn_open_file_location": "renamed -> row_location (context menu)",
        "chk_hide_binary": ".mb is Maya-only; .blend1 backups already excluded by find_blend_files",
        "chk000": "Recursive lives in the header menu as chk_recursive",
        "chk003": "Ignore-empty-workspaces is moot; find_workspaces never returns empty dirs",
        "txt_subfolder_structure": "renamed -> txt_subfolder",
        "hdr_select_shape": "no DAG transform/shape split in Blender",
        "hdr_select_history": "no construction history in Blender",
    },
    "channels_slots": {
        "chk_keyable": "every Blender custom prop is keyable; no per-attr keyable flag",
        "le_enum_names": "Blender custom props have no Maya-style enum type on arbitrary objects",
        "Names:": "label for the enum-names field (see le_enum_names)",
        "hdr_channel_control": "Maya Channel Control editor; Blender -> Properties/Drivers/Graph editors",
        "hdr_connection_editor": "Maya Connection Editor; no Blender analogue",
        "hdr_select_shape": "no DAG transform/shape split in Blender",
        "hdr_select_history": "no construction history in Blender",
    },
}


def _str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _attr_chain(node):
    """Dotted attribute chain for a Call's func, e.g. 'widget.option_box.menu.add'."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _enclosing_funcs(tree):
    """Map id(node) -> nearest enclosing FunctionDef name (so a control's location is accurate)."""
    loc = {}

    def walk(node, fn_name):
        for child in ast.iter_child_nodes(node):
            nf = child.name if isinstance(child, ast.FunctionDef) else fn_name
            loc[id(child)] = fn_name
            walk(child, nf)

    walk(tree, None)
    return loc


def _menu_location(chain, fn_name):
    """Where a control lives: optbox / action-col / header menu / table context menu / other menu."""
    if "option_box" in chain:
        return "optbox"
    if chain.endswith("actions.add"):
        return "action-col"
    if fn_name and "header" in fn_name:
        return "header"
    if fn_name and ("tbl" in fn_name or "table" in fn_name):
        return "ctx"
    return "menu"


def extract_surface(path):
    """Return a dict of the panel's control surface, by AST."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    loc = _enclosing_funcs(tree)
    surface = {
        "config_buttons": [],
        "controls": {},   # objectName/label/state-set -> "<location> <type> <label>"
        "affordances": set(),  # set_toggle / pin / add_presets
        "slots": set(),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            surface["slots"].add(node.name)
            continue
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "HEADER_MENU_ITEMS" for t in node.targets
        ):
            # Declarative header menu (BridgeSlotsBase.HEADER_MENU_ITEMS): each
            # item is ``(label, objectName, tooltip, handler)``. Key by
            # objectName/label exactly like the equivalent ``menu.add`` controls,
            # so a header item declared as data still counts toward the surface
            # diff (the bridges moved their header menu from code to this attr).
            if isinstance(node.value, (ast.Tuple, ast.List)):
                for item in node.value.elts:
                    if not isinstance(item, (ast.Tuple, ast.List)) or len(item.elts) < 2:
                        continue
                    label = _str(item.elts[0])
                    obj = _str(item.elts[1])
                    key = obj or label
                    if key:
                        surface["controls"][key] = f"header menu {label!r}"
            continue
        if isinstance(node, ast.Attribute) and node.attr in ("set_toggle", "pin", "add_presets", "preset_dir"):
            surface["affordances"].add(node.attr)
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node.func)
        fn_name = loc.get(id(node))
        if chain.endswith("config_buttons"):
            surface["config_buttons"] = [s for s in (_str(a) for a in node.args) if s]
        elif chain.endswith("actions.add"):
            # Action-icon column — key by its state-name set (col index differs by idiom).
            states = next((k.value for k in node.keywords if k.arg == "states"), None)
            names = sorted(s.value for s in getattr(states, "keys", [])
                           if isinstance(s, ast.Constant) and isinstance(s.value, str)) \
                if isinstance(states, ast.Dict) else []
            key = f"action[{','.join(names)}]"
            surface["controls"][key] = f"action-col states={names}"
        elif chain.endswith(".add") and "menu" in chain:
            kw = {k.arg: _str(k.value) for k in node.keywords if k.arg}
            obj = kw.get("setObjectName")
            label = kw.get("setText")
            ctype = _str(node.args[0]) if node.args else "?"
            if ctype == "Separator":
                continue  # separators are cosmetic
            key = obj or label or f"{ctype}:{label}"
            surface["controls"][key] = f"{_menu_location(chain, fn_name)} {ctype} {label!r}"
    return surface


# Slot defs bound to a .ui widget (tb###/b###/cmb###/… + their _init) — idiom-stable across DCCs,
# unlike free-function handlers (open_selected) which diverge by Maya/Blender idiom.
_WIDGET_HANDLER = re.compile(r"^[a-z]+\d{3}(_init)?$")


def _widget_handlers(slots):
    return {s for s in slots
            if _WIDGET_HANDLER.match(s) or (s.endswith("_init") and not s.startswith("__"))}


def pair_gaps(maya_path, blend_path, panel_key, compare_handlers=False):
    """Maya→Blender surface gaps for one pair: missing config-buttons / affordances / controls
    (minus the documented allowlist) and — for tentacle slots — missing widget-handler defs."""
    m, b = extract_surface(maya_path), extract_surface(blend_path)
    known = KNOWN_MAYA_ONLY.get(panel_key, {})  # suppresses any delta type whose name is allowlisted
    g = {
        "m": m, "b": b, "known": known,
        "missing_btns": [x for x in m["config_buttons"] if x not in b["config_buttons"] and x not in known],
        "missing_aff": sorted(a for a in (m["affordances"] - b["affordances"]) if a not in known),
        "ctrl_gaps": [k for k in sorted(m["controls"]) if k not in b["controls"] and k not in known],
        "handler_gaps": [],
    }
    if compare_handlers:
        g["handler_gaps"] = sorted(h for h in (_widget_handlers(m["slots"]) - _widget_handlers(b["slots"]))
                                   if h not in known)
    return g


def _resolve(panel):
    # Marking-menu nav slots use the bare ``<panel>.py``; co-located bridges (and other
    # co-located tool panels) name their slot file ``<panel>_slots.py``. Try the bare
    # name first, then the suffixed one, so ``--panel blender_bridge`` / ``unity_bridge``
    # resolve without explicit paths.
    def _find(pkg):
        for name in (panel + ".py", panel + "_slots.py"):
            hits = glob.glob(os.path.join(ROOT, pkg, pkg, "**", name), recursive=True)
            if hits:
                return hits[0]
        return None

    out = {}
    for pkg in ("mayatk", "blendertk"):
        hit = _find(pkg)
        if not hit:
            sys.exit(f"could not resolve {panel}.py (or {panel}_slots.py) under {pkg}/")
        out[pkg] = hit
    return out["mayatk"], out["blendertk"]


def _print_single(panel, maya_path, blend_path):
    # Widget-handler (tb###/b###) diffing is a clean signal only for the shared marking-menu slots;
    # co-located panels rename these to descriptive defs, so it's noise there.
    is_slot = "/slots/" in maya_path.replace("\\", "/")
    # Key the allowlist by the maya file stem -- same as the --all sweep -- so a
    # KNOWN_MAYA_ONLY entry resolves in both modes. (Co-located bridges are
    # ``<panel>_slots.py`` while --panel is invoked as the bare ``<panel>``.)
    key = os.path.splitext(os.path.basename(maya_path))[0]
    g = pair_gaps(maya_path, blend_path, key, compare_handlers=is_slot)
    m, b = g["m"], g["b"]
    print(f"# Panel surface diff — {panel}")
    print(f"  mayatk:    {os.path.relpath(maya_path, ROOT)}")
    print(f"  blendertk: {os.path.relpath(blend_path, ROOT)}\n")
    print("## config_buttons (header chrome)")
    print(f"  mayatk: {m['config_buttons']}   blendertk: {b['config_buttons']}")
    print(f"  >> MISSING: {g['missing_btns'] or 'none'}\n")
    print("## affordances (option-box toggle / pin / presets)")
    print(f"  mayatk: {sorted(m['affordances'])}   blendertk: {sorted(b['affordances'])}")
    print(f"  >> MISSING: {g['missing_aff'] or 'none'}\n")
    print("## controls (menu / option-box / context / action items)")
    for key in sorted(m["controls"]):
        if key in g["known"] and key not in b["controls"]:
            print(f"  [maya-only OK] {key:30} {m['controls'][key]}  — {g['known'][key]}")
    for key in g["ctrl_gaps"]:
        print(f"  >> MISSING   {key:30} {m['controls'][key]}")
    for key in sorted(set(b["controls"]) - set(m["controls"])):
        print(f"  [blendertk-extra] {key:26} {b['controls'][key]}")
    if is_slot:
        print("\n## widget-handler slots (tb###/b###/cmb###/…)")
        print(f"  >> MISSING: {g['handler_gaps'] or 'none'}")
    hpart = f", {len(g['handler_gaps'])} widget-handler(s)" if is_slot else ""
    print(f"\n## SUMMARY: {len(g['missing_btns'])} config-button(s), {len(g['missing_aff'])} "
          f"affordance(s), {len(g['ctrl_gaps'])} control(s){hpart} "
          f"missing in blendertk (excl. {len(g['known'])} known maya-only).")
    return 1 if any((g["missing_btns"], g["missing_aff"], g["ctrl_gaps"], g["handler_gaps"])) else 0


def _classes(pkg):
    """Map ``*Slots`` class name -> file, for a package's source tree (skips build/ + tests)."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, pkg, pkg, "**", "*.py"), recursive=True):
        fp = f.replace("\\", "/")
        if "/build/" in fp or "/temp_tests/" in fp:
            continue
        try:
            src = open(f, encoding="utf-8").read()
        except OSError:
            continue
        for cn in re.findall(r"^class (\w+Slots)\b", src, re.M):
            out.setdefault(cn, f)
    return out


def _slot_files(dcc):
    """Map basename -> file for tentacle/slots/<dcc>/*.py (skips _private + __init__)."""
    d = os.path.join(ROOT, "tentacle", "tentacle", "slots", dcc)
    return {os.path.basename(f): f for f in glob.glob(os.path.join(d, "*.py"))
            if not os.path.basename(f).startswith("_")}


SURFACE_OUT = os.path.join(ROOT, "tentacle", "docs", "PARITY_SURFACE.md")


def _sweep_report():
    """Build the whole-surface Markdown report. Returns (rc, text). rc=1 if any unexplained gap."""
    L = []
    w = L.append
    rc = 0
    w("# tentacle / blendertk — Maya->Blender Control-Surface Diff")
    w("")
    w("> **Auto-generated by `m3trik/scripts/compare_panel_surface.py --all --write`.** Do not edit "
      "by hand. This is the *name-level* companion to `PARITY_AUDIT.md` (which measures depth): it "
      "lists exactly which `config_buttons`, menu / option-box / action controls, and widget-handler "
      "slots exist in a Maya tool but not its Blender twin. Deltas covered by the script's "
      "`KNOWN_MAYA_ONLY` allowlist (with a reason) are suppressed; everything shown is an "
      "**un-triaged delta** — either a real gap to close or a divergence to add to the allowlist.")
    w("")

    mp, bp = _classes("mayatk"), _classes("blendertk")
    panel_pairs = sorted(set(mp) & set(bp))
    panel_missing = sorted(set(mp) - set(bp))
    w("## mayatk <-> blendertk co-located `*Slots` panels")
    w("")
    w("| panel | cfg-btn | afford | controls | status |")
    w("|:--|--:|--:|--:|:--|")
    panel_detail = []
    for cn in panel_pairs:
        key = os.path.splitext(os.path.basename(mp[cn]))[0]
        g = pair_gaps(mp[cn], bp[cn], key)
        nb, na, nc = len(g["missing_btns"]), len(g["missing_aff"]), len(g["ctrl_gaps"])
        rc = rc or int(bool(nb or na or nc))
        w(f"| {cn.replace('Slots','')} | {nb} | {na} | {nc} | {'OK' if not (nb or na or nc) else '**GAP**'} |")
        if nb or na or nc:
            panel_detail.append((cn.replace("Slots", ""), g))
    w("")
    if panel_detail:
        w("### Panel gap detail")
        w("")
        for name, g in panel_detail:
            bits = []
            if g["missing_btns"]:
                bits.append(f"`config_buttons` {g['missing_btns']}")
            if g["missing_aff"]:
                bits.append(f"affordances {g['missing_aff']}")
            head = "; ".join(bits)
            w(f"- **{name}**" + (f" — {head}" if head else ""))
            for k in g["ctrl_gaps"]:
                w(f"  - control `{k}` — {g['m']['controls'][k]}")
        w("")
    if panel_missing:
        w(f"**Missing panels — mayatk `*Slots` with NO blendertk class ({len(panel_missing)}):** "
          + ", ".join(c.replace("Slots", "") for c in panel_missing))
        w("")

    sm, sb = _slot_files("maya"), _slot_files("blender")
    slot_pairs = sorted(set(sm) & set(sb))
    slot_missing = sorted(set(sm) - set(sb))
    w("## tentacle marking-menu slots (`slots/maya` <-> `slots/blender`)")
    w("")
    w("> `handler` = widget-bound defs (`tb###`/`b###`/`cmb###`/… + their `_init`) present in Maya "
      "but not Blender — the precise parity signal for a shared menu. `controls` = option-box / menu "
      "controls; large counts often include dynamic / loop-built widgets, so triage by handler first.")
    w("")
    w("| slot file | handlers | controls | status |")
    w("|:--|--:|--:|:--|")
    slot_detail = []
    for n in slot_pairs:
        g = pair_gaps(sm[n], sb[n], os.path.splitext(n)[0], compare_handlers=True)
        nh, nc = len(g["handler_gaps"]), len(g["ctrl_gaps"])
        rc = rc or int(bool(nh or nc))
        w(f"| {n} | {nh} | {nc} | {'OK' if not (nh or nc) else '**GAP**'} |")
        if g["handler_gaps"]:
            slot_detail.append((n, g["handler_gaps"]))
    w("")
    if slot_detail:
        w("### Slot handler gap detail (Maya handlers with no Blender def)")
        w("")
        for n, handlers in slot_detail:
            w(f"- **{n}** — {', '.join(handlers)}")
        w("")
    if slot_missing:
        w(f"**Missing slot files — `slots/maya` with NO `slots/blender` ({len(slot_missing)}):** "
          + ", ".join(sorted(slot_missing)))
        w("")

    w(f"## Totals: {len(panel_pairs)} panels paired (+{len(panel_missing)} maya-only); "
      f"{len(slot_pairs)} tentacle slots paired (+{len(slot_missing)} maya-only).")
    return rc, "\n".join(L) + "\n"


def main(argv):
    if argv and argv[0] == "--all":
        rc, text = _sweep_report()
        if "--write" in argv:
            with open(SURFACE_OUT, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"Wrote {os.path.relpath(SURFACE_OUT, ROOT)}")
        else:
            print(text)
        return rc
    if len(argv) == 2 and argv[0] == "--panel":
        return _print_single(argv[1], *_resolve(argv[1]))
    if len(argv) == 2:
        return _print_single(os.path.splitext(os.path.basename(argv[0]))[0], argv[0], argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
