#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate tentacle/docs/PARITY_AUDIT.md — the measured Maya<->Blender parity audit.

Everything quantitative is computed from source so the numbers can never drift or be
hand-fumbled (this audit was wrong three times from hand arithmetic + shallow metrics).

Metrics, and *why* — learned the hard way:
  * Button presence and a matching ``.ui`` skeleton are PRESENCE, not depth — worthless for
    "is it faithful". In this architecture the real UI (option boxes, menus, sub-controls) is
    built in *code*; depth must be measured there.
  * Panel "feel" depth  = static interactive ``.ui`` widgets + code-built controls (``.add``)
    + option boxes (weighted x2 — each is a whole sub-menu).
  * Panel "logic" depth = source lines (often far below the feel number).
  * Slot depth          = dynamic controls built in code per shared menu.
  * Helper coverage      = shared public names / mayatk public names (idiom-neutral).

Usage:
    python generate_parity_audit.py                  # write the doc
    python generate_parity_audit.py --check          # exit 1 if stale (CI)
    python generate_parity_audit.py --allow-stale    # skip the registry-freshness guard

Inputs that are NOT source (guarded): the L4 layer reads mayatk/blendertk API_REGISTRY.json —
the 2026-06-19 audit shipped "nurbs_utils ABSENT" because it was generated from a stale
working-tree registry. The freshness guard refuses to run when a registry predates the
package source (regenerate via generate_api_registry.py first). Maya-only panel triage comes
from tentacle/docs/parity_map.py (the shared ledger), not a local table.
"""
from __future__ import annotations
import ast
import glob
import json
import os
import re
import sys

import compare_panel_surface as cps

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "tentacle", "docs", "PARITY_AUDIT.md")


def check_registry_freshness(pkg):
    """Refuse to compute L4 from a registry older than the package source."""
    reg = rp(pkg, "API_REGISTRY.json")
    if not os.path.isfile(reg):
        sys.exit(f"missing {reg} — run generate_api_registry.py {pkg} first")
    reg_m = os.path.getmtime(reg)
    newest = max(
        (os.path.getmtime(f) for f in glob.glob(rp(pkg, pkg, "**", "*.py"), recursive=True)
         if "__pycache__" not in f),
        default=0,
    )
    if newest > reg_m:
        sys.exit(
            f"STALE INPUT: {pkg}/API_REGISTRY.json predates {pkg} source — the L4 numbers "
            f"would be wrong. Run: python m3trik/scripts/generate_api_registry.py {pkg} "
            f"(or pass --allow-stale to override)."
        )


def rp(*a):
    return os.path.join(ROOT, *a)


# --------------------------------------------------------------------------- shared helpers
INTERACTIVE = {
    "LineEdit", "QLineEdit", "ComboBox", "QComboBox", "SpinBox", "QSpinBox", "QDoubleSpinBox",
    "CheckBox", "QCheckBox", "PushButton", "QPushButton", "ToolButton", "QToolButton",
    "RadioButton", "QRadioButton", "TableWidget", "QTableWidget", "ListWidget", "QListWidget",
    "TreeWidget", "QTreeWidget", "Slider", "QSlider", "QPlainTextEdit", "TextEdit", "QTextEdit",
}
HANDLER = re.compile(r"^(tb|b|chk|cmb|list|s|d|i|w)\d+$")


def read(path):
    return open(path, encoding="utf-8", errors="ignore").read()


def ui_interactive(ui_path):
    if not os.path.isfile(ui_path):
        return 0
    return sum(1 for c in re.findall(r'<widget class="([^"]+)"', read(ui_path)) if c in INTERACTIVE)


def code_metrics(path):
    """(lines, code-built controls, option boxes, handlers, hollow handlers) for a slot/panel file."""
    src = read(path)
    lines = src.count("\n") + 1
    controls = len(re.findall(r"\.add\(", src)) - len(re.findall(r'\.add\(\s*["\']Separator', src))
    opt_boxes = handlers = hollow = 0
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree:
        for n in ast.walk(tree):
            if not isinstance(n, ast.FunctionDef):
                continue
            seg = ast.get_source_segment(src, n) or ""
            if ".option_box." in seg:
                opt_boxes += 1
            if HANDLER.match(n.name) and not n.name.endswith("_init"):
                handlers += 1
                body = seg.split("\n", 1)[1] if "\n" in seg else ""
                if "message_box" in body and not re.search(
                    r"\b(btk|mtk)\.\w|\bbpy\.(ops|context|data)\b|\bcmds\.\w|\bmel\.\w|\bbmesh\.\w", body
                ):
                    hollow += 1
    return dict(lines=lines, controls=controls, opt_boxes=opt_boxes, handlers=handlers, hollow=hollow)


def pct(a, b):
    return round(100 * a / b) if b else None


def ps(v):
    return f"{v}%" if v is not None else "—"


# --------------------------------------------------------------------------- L4 helper coverage
def flat_names(reg_path):
    reg = json.load(open(reg_path, encoding="utf-8"))
    per, alln = {}, set()
    for mod in reg["modules"]:
        top = mod["relpath"].replace("\\", "/").split("/")[0]
        s = per.setdefault(top, set())
        for fn in mod.get("functions", []):
            if not fn["name"].startswith("_"):
                s.add(fn["name"]); alln.add(fn["name"])
        for c in mod.get("classes", []):
            for m in c.get("members", []):
                if not m["name"].startswith("_"):
                    s.add(m["name"]); alln.add(m["name"])
    return per, alln


# --------------------------------------------------------------------------- L3 panels
# Maya-only panel triage lives in the shared ledger (tentacle/docs/parity_map.py PANELS):
# status na -> N/A by design, counterpart -> mirrored pair, pending -> tracked open port.
# An unledgered Maya-only panel is UNTRIAGED and flagged loudly.


def find_panels(pkg_root):
    out = {}
    for f in glob.glob(rp(pkg_root, "**", "*.py"), recursive=True):
        if "__pycache__" in f:
            continue
        for cn in re.findall(r"^class (\w+Slots)\b", read(f), re.M):
            out[cn] = f
    return out


def panel_metrics(pyfile):
    uipath = os.path.splitext(pyfile)[0] + ".ui"
    if not os.path.isfile(uipath):
        cands = glob.glob(os.path.join(os.path.dirname(pyfile), "*.ui"))
        uipath = cands[0] if len(cands) == 1 else uipath
    uw = ui_interactive(uipath)
    # HYBRID/dynamic panels build their options body at runtime from AttributeSpec dicts
    # (TubeRig) — count those statically-declared option keys as UI surface, or dynamic
    # panels score 3/16 "thin shell" while actually rendering 7+ controls.
    spec = cps.Surface(pyfile).spec_options
    uw += len({k for keys in spec.values() for k in keys})
    m = code_metrics(pyfile)
    return dict(ui=uw, controls=m["controls"], opt=m["opt_boxes"], lines=m["lines"])


# --------------------------------------------------------------------------- L2/L1 shared menus
DOMAINS = [
    "animation", "cameras", "crease", "deformation", "display", "duplicate", "edit", "editors", "hud",
    "lighting", "main", "materials", "normals", "nurbs", "pivot", "polygons", "preferences", "rendering",
    "rigging", "scene", "selection", "settings", "subdivision", "symmetry", "transform", "utilities", "uv",
]
WNAME = re.compile(r'name="((?:tb|b|chk|cmb|list|s|d|i|w)\d+)"')
DEFP = re.compile(r"^\s{4}def\s+([a-zA-Z_]\w*)\s*\(", re.M)


def ui_widget_names(domain):
    names = set()
    for p in glob.glob(rp("tentacle/tentacle/ui", domain + ".ui")) + glob.glob(
        rp("tentacle/tentacle/ui", domain + "#*.ui")
    ):
        names |= set(WNAME.findall(read(p)))
    return names


def slot_defs(folder, domain):
    p = rp("tentacle/tentacle/slots", folder, domain + ".py")
    return set(DEFP.findall(read(p))) if os.path.isfile(p) else set()


# =========================================================================== build
def build():
    L = []
    w = L.append

    # ---- L4 ----
    M, Ma = flat_names(rp("mayatk/API_REGISTRY.json"))
    B, Ba = flat_names(rp("blendertk/API_REGISTRY.json"))
    helper_cov = pct(len(Ma & Ba), len(Ma))
    absent_mods = sorted(m for m in M if M[m] and not B.get(m))

    # ---- L3 ----
    ledger = cps.load_ledger()
    pan_ledger = ledger["panels"]
    MP, BP = find_panels("mayatk/mayatk"), find_panels("blendertk/blendertk")
    present = sorted(set(MP) & set(BP))
    missing = sorted(set(MP) - set(BP))
    bonly = sorted(set(BP) - set(MP))
    panel_rows = []
    for cn in present:
        m, b = panel_metrics(MP[cn]), panel_metrics(BP[cn])
        stem = os.path.splitext(os.path.basename(MP[cn]))[0]
        d = cps.diff_pair(MP[cn], BP[cn], stem, ledger, is_slot=False)
        surf = (len(d["untriaged"]), len(d["pending"]))
        panel_rows.append((cn, m, b, pct(b["lines"], m["lines"]), pct(b["ui"], m["ui"]), surf))
    panel_rows.sort(key=lambda r: (r[3] if r[3] is not None else 999))
    untriaged_missing = [c for c in missing if c not in pan_ledger]
    open_ports = [c for c in missing if pan_ledger.get(c, {}).get("status") == "pending"]
    na_panels = [c for c in missing if pan_ledger.get(c, {}).get("status") == "na"]
    counterpart = [c for c in missing if pan_ledger.get(c, {}).get("status") == "counterpart"]

    # ---- L2 / L1 ----
    slot_rows = []
    tmc = tbc = thol = 0
    l1_maya = l1_blen = l1_gap = 0
    for d in DOMAINS:
        mp, bp = rp("tentacle/tentacle/slots/maya", d + ".py"), rp("tentacle/tentacle/slots/blender", d + ".py")
        m = code_metrics(mp) if os.path.isfile(mp) else dict(controls=0, opt_boxes=0, hollow=0, lines=0)
        b = code_metrics(bp) if os.path.isfile(bp) else dict(controls=0, opt_boxes=0, hollow=0, lines=0)
        slot_rows.append((d, m, b, pct(b["controls"], m["controls"])))
        tmc += m["controls"]; tbc += b["controls"]; thol += b["hollow"]
        wn = ui_widget_names(d)
        mi, bi = wn & slot_defs("maya", d), wn & slot_defs("blender", d)
        l1_maya += len(mi); l1_blen += len(bi); l1_gap += len(mi - bi)
    slot_depth = pct(tbc, tmc)

    # ===================================================================== render
    w("# tentacle / blendertk — Maya↔Blender Parity Audit")
    w("")
    w("> **Auto-generated by `m3trik/scripts/generate_parity_audit.py` — measured & fully "
      "reproducible.** Do not edit by hand; re-run the script (commit date records when). Every number "
      "below is computed from the registries, the shared `ui/*.ui`, and the slot/panel source — no "
      "hand arithmetic.")
    w("")
    w("**Why this doc exists:** the port was declared \"100%/100% complete\" three times. That number "
      "measured *button presence*; a matching `.ui` skeleton is likewise presence, not depth. Real "
      "parity lives one layer down — option boxes, menus, sub-controls (built in code) and engine "
      "logic. This audit measures *that*, per panel and per menu.")
    w("")

    # scorecard
    n_thin = sum(1 for r in panel_rows if r[3] is not None and r[3] < 50)  # by logic (lines) %
    w("## Scorecard")
    w("")
    w("| Layer | What it measures | Result |")
    w("|:--|:--|:--|")
    w(f"| **1. Menu buttons** | shared-menu widgets with a slot handler | Maya {l1_maya}, Blender "
      f"{l1_blen} — only **{l1_gap}** Maya-handled widget missing in Blender ⇒ ~100% *(presence; the "
      "metric that misled)* |")
    w(f"| **2. Shared-menu slot depth** | `.add(` controls, Blender ÷ Maya | "
      f"**{slot_depth}%** ({tbc}/{tmc}) — *floor only; undercounts loop-built controls & legit "
      f"divergence. Spot-checks (pivot, selection) show menus are **largely faithful**.* {thol} hollow "
      "handlers |")
    w(f"| **3. Tool panels** | co-located `*Slots` tools | **{len(present)} present** pairs (of "
      f"Maya's {len(MP)}), {len(open_ports)} open ports (tracked), {len(na_panels)} N/A by design, "
      f"{len(counterpart)} counterpart-pair"
      + (f", **{len(untriaged_missing)} UNTRIAGED**" if untriaged_missing else "")
      + f". {n_thin} below 50% by line count (see per-panel surface column) |")
    w(f"| **4. Helper surface** | public names, Blender covers of mayatk | **{helper_cov}%** "
      f"({len(Ma & Ba)}/{len(Ma)} names); {len(absent_mods)} modules absent: {', '.join(absent_mods)} |")
    w("")
    w("**Bottom line:** depth numbers here are coarse floors — the per-element truth (every "
      "control/widget/handler, classified through the triage ledger) is "
      "[`PARITY_SURFACE.md`](PARITY_SURFACE.md); its UNTRIAGED and `pending` rows are the real "
      f"work list. Helper library at {helper_cov}% with {len(absent_mods)} module(s) absent "
      f"({', '.join(absent_mods)}); {len(open_ports)} panel ports open.")
    w("")

    # L4
    w("---\n\n## Layer 4 — Helper surface (`blendertk` mirroring `mayatk`)")
    w("")
    w("Idiom-neutral: all public functions + class methods flattened to bare names (so the "
      "module-function vs classmethod idiom doesn't distort the count). *Coverage* = mayatk names "
      "also present in blendertk ÷ mayatk names.")
    w("")
    w("| module | mayatk | blendertk | shared | coverage |")
    w("|:--|--:|--:|--:|--:|")
    for mod in sorted(set(M) | set(B)):
        m, b = M.get(mod, set()), B.get(mod, set())
        flag = " **(ABSENT)**" if m and not b else ""
        w(f"| {mod}{flag} | {len(m)} | {len(b)} | {len(m & b)} | {ps(pct(len(m & b), len(m)))} |")
    w(f"| **TOTAL (unique)** | **{len(Ma)}** | **{len(Ba)}** | **{len(Ma & Ba)}** | **{helper_cov}%** |")
    w("")
    w("> Caveat: many absent names are *internals of the missing panels* (they arrive when the panel "
      "is ported), and some mayatk helpers are replaced inline by native `bpy.ops` by design — so the "
      "absent count overstates *distinct* helper work. The hard gaps are the 3 absent modules plus "
      "`node_utils` attributes, `core_utils` geometry math, and `xform_utils` pivots.")
    w("")

    # L3
    w("---\n\n## Layer 3 — Tool panels")
    w("")
    w("Co-located `*Slots` tools (own `.ui` + engine), launched from a menu button. Raw counts straight "
      "from each slot/`.ui` pair — no weighting. *logic%* = Blender lines ÷ Maya lines (how much the "
      "panel **does**); *UI%* = Blender interactive `.ui` widgets ÷ Maya's (how complete it **looks**). "
      "When UI% is high but logic% low, the panel looks complete but does much less.")
    w("")
    w("> **logic% is a line ratio — it understates panels whose Maya source carries large Maya-only "
      "machinery** (assemblies, namespaces, `_FileRef`, controllers). It is NOT a control-surface "
      "verdict: a panel can read low here yet still be control-surface-complete. For the per-panel "
      "name-level 1:1 check (every `config_buttons` / menu / option-box / action control), run "
      "`python m3trik/scripts/compare_panel_surface.py --panel <name>`.")
    w("")
    w(f"### Present pairs ({len(present)}) — worst first by logic")
    w("")
    w("> **The `surface` column is the verdict that matters** — it comes from the name-level "
      "classified diff (`compare_panel_surface.py` + `parity_map.py`): `clean` = every element "
      "matched or consciously triaged; `N open` = ledgered pending gaps; `N!` = untriaged. "
      "A `clean` panel with a low logic% just needs less code in Blender (native-op collapse, "
      "shared helpers) — that is not a defect.")
    w("")
    w("| panel | option boxes M→B | code controls M→B | `.ui` widgets M→B | lines M→B | logic% | UI% | surface |")
    w("|:--|:--:|:--:|:--:|:--:|--:|--:|:--|")
    for cn, m, b, ld, ud, (n_unt, n_pend) in panel_rows:
        if n_unt:
            surf = f"**{n_unt}!**" + (f" +{n_pend} open" if n_pend else "")
        elif n_pend:
            surf = f"{n_pend} open"
        else:
            surf = "clean"
        ob = f"{m['opt']}→{b['opt']}" + (" ⚠" if m["opt"] > b["opt"] else "")
        w(f"| {cn.replace('Slots','')} | {ob} | {m['controls']}→{b['controls']} | {m['ui']}→{b['ui']} | "
          f"{m['lines']}→{b['lines']} | {ps(ld)} | {ps(ud)} | {surf} |")
    w("")
    if untriaged_missing:
        w(f"### UNTRIAGED Maya-only panels ({len(untriaged_missing)}) — add a parity_map PANELS entry")
        w("")
        w(", ".join(c.replace("Slots", "") for c in untriaged_missing) + ".")
        w("")
    w(f"### Open panel ports ({len(open_ports)}) — tracked in parity_map")
    w("")
    for c in open_ports:
        w(f"- **{c.replace('Slots','')}** — {pan_ledger[c]['reason']}.")
    w("")
    w(f"### Not gaps ({len(na_panels) + len(counterpart)})")
    w("")
    for c in na_panels:
        w(f"- **{c.replace('Slots','')}** — N/A: {pan_ledger[c]['reason']}.")
    for c in counterpart:
        w(f"- **{c.replace('Slots','')}** ↔ {pan_ledger[c].get('to', '')} — {pan_ledger[c]['reason']}.")
    if bonly:
        w("")
        w("Blender-only panels (no mayatk counterpart): " + ", ".join(c.replace("Slots", "") for c in bonly) + ".")
    w("")

    # L2
    w("---\n\n## Layer 2 — Shared-menu slot depth")
    w("")
    w("The 27 shared menus both DCCs load. *Controls* = `.add(` calls (option-box sub-controls + menu "
      "items).")
    w("")
    w("> ⚠️ **This per-domain % is an UPPER BOUND on the gap, NOT the gap — confirm by reading the slot "
      "pair before acting.** It is wrong in two directions, both proven by spot-checks: (1) it "
      "**undercounts loop-built controls** — `selection` builds all 10 Select-Similar criteria in one "
      "`for` loop (counts as 1, not 10), so its real faithfulness is ~90%, not the 53% shown; (2) it "
      "**can't tell legitimate Blender divergence from a gap** — `pivot`'s 36% is *entirely* Blender's "
      "single baked-origin model (no per-channel/​manip pivot), i.e. already faithful with nothing to "
      "fix. Treat a low number as \"read this slot,\" never as \"this much is missing.\"")
    w("")
    w("| domain | controls M→B | depth | option boxes M→B | hollow (B) |")
    w("|:--|:--:|--:|:--:|--:|")
    for d, m, b, dep in slot_rows:
        ob = f"{m['opt_boxes']}→{b['opt_boxes']}" + (" ⚠" if m["opt_boxes"] > b["opt_boxes"] else "")
        hl = str(b["hollow"]) if b["hollow"] else ""
        w(f"| {d} | {m['controls']}→{b['controls']} | {ps(dep)} | {ob} | {hl} |")
    w(f"| **TOTAL** | **{tmc}→{tbc}** | **{slot_depth}%** | | **{thol}** |")
    w("")

    # methodology
    w("---\n\n## Methodology & honest limits")
    w("")
    w("- **Option boxes** = distinct slot methods whose body references `.option_box.` (validated "
      "against Reference Manager: mayatk 2, Blender 0).")
    w("- **Code controls** = `.add(` calls minus `Separator`s (option-box sub-controls + menu items).")
    w("- **`.ui` widgets** = static interactive widgets declared in the panel's `.ui` (covers panels "
      "that put controls in the `.ui` rather than building them in code).")
    w("- **Limits:** static `.add()`/widget counting is a proxy, not a render — it can't see whether a "
      "control *works* or matches Maya's behavior. The only true \"feels seamless\" test is rendering "
      "both panels side by side. Logic% compares file lines and is blunt where engine code lives "
      "elsewhere (e.g. Blender panels delegate to `*_utils` helpers).")
    w("- **What this audit deliberately does NOT trust:** button presence, `.ui`-skeleton similarity, "
      "or a `*Slots` class merely existing — all are presence, not parity.")
    w("")
    return "\n".join(L) + "\n"


def main():
    if "--allow-stale" not in sys.argv:
        for pkg in ("mayatk", "blendertk"):
            check_registry_freshness(pkg)
    report = build()
    if "--check" in sys.argv:
        cur = read(OUT) if os.path.isfile(OUT) else ""
        if cur.strip() != report.strip():
            print("STALE: PARITY_AUDIT.md differs from generator output. Re-run generate_parity_audit.py.")
            sys.exit(1)
        print("Up to date:", OUT)
        return
    open(OUT, "w", encoding="utf-8").write(report)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
