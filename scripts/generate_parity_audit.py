#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate tentacle/docs/PARITY_AUDIT.md — the measured Maya<->Blender parity audit.

Everything quantitative is computed from source so the numbers can never drift or be
hand-fumbled (this audit was wrong three times from hand arithmetic + shallow metrics).

One Slots class per category and per tool serves both hosts through ``self.tk``, so there
is no Maya panel to measure a Blender twin against: parity is what each host can run.
Layers 1-3 read the parity gate (``compare_panel_surface.sweep``, every toolkit chain a
shared Slots class calls, resolved on mayatk and blendertk); Layer 4 the libraries.

  * Layer 1 -- menu buttons: each category's ``.ui`` widgets with a handler, and the ones
    a ``requires`` tag hides on each host (presence, never depth on its own).
  * Layer 2 -- category toolkit calls: chains and call sites, the one-host operations
    (hidden or guarded where the library lacks them), the gaps.
  * Layer 3 -- tool panels: the same per tool, with the hosts each serves
    (``slots.tools.HOSTS`` / ``STANDALONE``).
  * Layer 4 -- helper surface: shared public names / mayatk public names (idiom-neutral).

Usage:
    python generate_parity_audit.py                  # write the doc
    python generate_parity_audit.py --check          # exit 1 if stale (CI)
    python generate_parity_audit.py --allow-stale    # skip the registry-freshness guard

Inputs that are NOT source (guarded): the L4 layer reads mayatk/blendertk API_REGISTRY.json —
the 2026-06-19 audit shipped "nurbs_utils ABSENT" because it was generated from a stale
working-tree registry. The freshness guard refuses to run when a registry predates the
package source (regenerate via generate_api_registry.py first).
"""
from __future__ import annotations
import argparse
import ast
import glob
import json
import os
import re
import sys
from pathlib import Path

import compare_panel_surface as cps

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "tentacle", "docs", "PARITY_AUDIT.md")


def check_registry_freshness(pkg):
    """Refuse to compute L4 from a registry older than the package source."""
    reg = rp(pkg, "API_REGISTRY.json")
    if not os.path.isfile(reg):
        sys.exit(f"missing {reg} — run generate_api_registry.py {pkg} first")
    reg_m = os.path.getmtime(reg)
    # `*_ui.py` are gitignored compiler output (uitk regenerates them whenever a
    # panel's .ui changes, i.e. every time a tool is opened) and carry no public
    # symbols — the registry skips them, so they must not gate its freshness.
    newest = max(
        (os.path.getmtime(f) for f in glob.glob(rp(pkg, pkg, "**", "*.py"), recursive=True)
         if "__pycache__" not in f and not f.endswith("_ui.py")),
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
HANDLER = re.compile(r"^(tb|b|chk|cmb|list|s|d|i|w)\d+$")


def read(path):
    return open(path, encoding="utf-8", errors="ignore").read()


def is_message_box(node):
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Attribute) and node.func.attr == "message_box")
        or (isinstance(node.func, ast.Name) and node.func.id == "message_box")
    )


def does_work(node):
    """True if `node`'s subtree performs work beyond composing/popping a message box.

    A `message_box` call's own subtree is skipped — its arguments are just the message
    (f-strings, `.format()`, `str()`), never the handler's action.
    """
    if is_message_box(node):
        return False
    if isinstance(node, (ast.Call, ast.Assign, ast.AugAssign, ast.AnnAssign)):
        return True
    return any(does_work(c) for c in ast.iter_child_nodes(node))


def code_metrics(path):
    """(lines, code-built controls, option boxes, handlers, hollow handlers) for a slot/panel file.

    *hollow* = a handler that ONLY pops a message box and is not closed by hiding its widget
    — i.e. parity theater: a visible control that does nothing. This is deliberately narrow.
    A guard clause (`if not selection: message_box(...); return`) on a handler that goes on to
    do real work is NOT hollow, and neither is a control correctly retired via
    `<name>_init -> setVisible(False)`. An earlier substring heuristic ("mentions
    message_box, calls no `btk.`/`bpy.ops`/`cmds.`") could see neither shape: it flagged
    blendertk's 11 guard clauses plus its 2 correctly-hidden controls, putting "13 hollow
    handlers" in the headline scorecard when the true count on both DCCs is 0.
    """
    src = read(path)
    lines = src.count("\n") + 1
    controls = len(re.findall(r"\.add\(", src)) - len(re.findall(r'\.add\(\s*["\']Separator', src))
    opt_boxes = handlers = 0
    hidden, message_only = set(), set()
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
            if n.name.endswith("_init"):
                if "setVisible(False)" in seg:
                    hidden.add(n.name[: -len("_init")])
                continue
            if HANDLER.match(n.name):
                handlers += 1
                body = n.body[1:] if ast.get_docstring(n) else n.body
                if any(
                    is_message_box(c) for stmt in body for c in ast.walk(stmt)
                ) and not any(does_work(stmt) for stmt in body):
                    message_only.add(n.name)
    return dict(
        lines=lines, controls=controls, opt_boxes=opt_boxes, handlers=handlers,
        hollow=len(message_only - hidden),
    )


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
                s.add(fn["name"])
                alln.add(fn["name"])
        for c in mod.get("classes", []):
            for m in c.get("members", []):
                if not m["name"].startswith("_"):
                    s.add(m["name"])
                    alln.add(m["name"])
    return per, alln


# --------------------------------------------------------------------------- L1 menu buttons
def category_buttons(rel):
    """``(widgets with a handler, {host: of them hidden there})`` for one category: its
    ``.ui`` widgets whose name (or ``<name>_init``) the category's Slots class defines."""
    ui_dir = Path(rp("tentacle", "tentacle", "ui"))
    requires = cps._requires_of(cps._paired_ui(ui_dir, rel))
    tree = ast.parse(read(rp("tentacle", "tentacle", "slots", rel)))
    methods = {f.name for c in tree.body if isinstance(c, ast.ClassDef)
               for f in c.body if isinstance(f, ast.FunctionDef)}
    handled = {w for w in requires if HANDLER.match(w) and (w in methods or f"{w}_init" in methods)}
    hidden = {h: sum(1 for w in handled if h not in requires[w]) for h in cps.HOST_PACKAGES}
    return handled, hidden


# --------------------------------------------------------------------------- L2 / L3 from the gate
def gate_rows(result):
    """``{owner: row}`` from the sweep: *owner* is a category file (``scene.py``) or a
    tool (its ``slots/tools/<tool>.py`` plus its ``_<tool>/`` helpers)."""
    gap_sites = {id(s) for g in result.gaps for s in g.sites}
    one_host = {}
    for (chain, host, _), sites in result.one_host.items():
        for s in sites:
            one_host.setdefault(_owner(s.rel, result.tools), set()).add((chain, host))
    rows = {}
    for rel, sites in result.files.items():
        owner = _owner(rel, result.tools)
        if owner is None:
            continue
        row = rows.setdefault(owner, dict(chains=set(), sites=0, gaps=0))
        row["chains"] |= {s.chain for s in sites}
        row["sites"] += len(sites)
        row["gaps"] += sum(1 for s in sites if id(s) in gap_sites)
    for owner, row in rows.items():
        row["one_host"] = len(one_host.get(owner, ()))
    return rows


def _owner(rel, tools):
    """``scene.py`` -> itself; ``tools/x.py`` and ``tools/_x/...`` -> ``tools/x``; a
    helper package no tool owns (shared by several) -> ``tools/_x``; else None."""
    parts = rel.split("/")
    if len(parts) == 1:
        return None if rel.startswith("_") else rel
    if parts[0] != "tools" or parts[1] == "__init__.py":
        return None
    if len(parts) == 2:
        return f"tools/{Path(parts[1]).stem}"
    name = parts[1][1:] if parts[1].startswith("_") else parts[1]
    return f"tools/{name}" if name in tools else f"tools/{parts[1]}"


# =========================================================================== build
def build():
    L = []
    w = L.append

    # ---- L4 ----
    M, Ma = flat_names(rp("mayatk/API_REGISTRY.json"))
    B, Ba = flat_names(rp("blendertk/API_REGISTRY.json"))
    helper_cov = pct(len(Ma & Ba), len(Ma))
    absent_mods = sorted(m for m in M if M[m] and not B.get(m))

    # ---- L1-L3: the parity gate ----
    result = cps.sweep(ROOT)
    rows = gate_rows(result)
    categories = sorted(k for k in rows if not k.startswith("tools/"))
    tools = sorted(k for k in rows if k.startswith("tools/"))
    hosts_of = {f"tools/{t}": h for t, h in result.tools.items()}
    hosts_of.update({t: "shared helpers" for t in tools if t.startswith("tools/_")})
    l1 = {}
    for rel in categories:
        handled, hidden = category_buttons(rel)
        l1[rel] = (len(handled), hidden, code_metrics(rp("tentacle", "tentacle", "slots", rel)))
    n_buttons = sum(v[0] for v in l1.values())
    n_hidden = {h: sum(v[1][h] for v in l1.values()) for h in cps.HOST_PACKAGES}
    n_hollow = sum(v[2]["hollow"] for v in l1.values())

    def total(keys, field):
        return sum(len(rows[k][field]) if field == "chains" else rows[k][field] for k in keys)

    served = {}
    for t in tools:
        served.setdefault(hosts_of.get(t, "both"), []).append(t)

    # ===================================================================== render
    w("# tentacle / blendertk — Maya↔Blender Parity Audit")
    w("")
    w("> **Auto-generated by `m3trik/scripts/generate_parity_audit.py` — measured & fully "
      "reproducible.** Do not edit by hand; re-run the script (commit date records when). Every number "
      "below is computed from the registries, the shared `ui/*.ui`, and the slot source — no hand "
      "arithmetic.")
    w("")
    w("**Why this doc exists:** the port was declared \"100%/100% complete\" three times. That number "
      "measured *button presence*. One Slots class per category and per tool now serves both hosts "
      "through `self.tk`, so parity is what each host can run: every toolkit chain a shared Slots "
      "class calls must resolve on mayatk and blendertk, or be hidden or guarded where it does not. "
      "The per-chain truth is [`PARITY_SURFACE.md`](PARITY_SURFACE.md) (the gate, "
      "`compare_panel_surface.py`); this is its scoreboard.")
    w("")

    w("## Scorecard")
    w("")
    w("| Layer | What it measures | Result |")
    w("|:--|:--|:--|")
    w(f"| **1. Menu buttons** | category `.ui` widgets with a handler in the one Slots class | "
      f"{n_buttons} across {len(categories)} categories; hidden by `requires` on Maya "
      f"{n_hidden['maya']}, on Blender {n_hidden['blender']} *(presence)*; {n_hollow} hollow handlers |")
    w(f"| **2. Category toolkit calls** | `self.tk` chains the categories call, per host | "
      f"{total(categories, 'chains')} chains at {total(categories, 'sites')} sites; "
      f"{total(categories, 'one_host')} one-host operations (hidden or guarded); "
      f"**{total(categories, 'gaps')} gap sites** |")
    w(f"| **3. Tool panels** | the shared tools, per host | {len(result.tools)} tools: "
      + ", ".join(f"{len(v)} {k}" for k, v in sorted(served.items()) if k != "shared helpers")
      + f"; {total(tools, 'chains')} chains at {total(tools, 'sites')} sites; "
      f"{total(tools, 'one_host')} one-host operations; **{total(tools, 'gaps')} gap sites** |")
    w(f"| **4. Helper surface** | public names, Blender covers of mayatk | **{helper_cov}%** "
      f"({len(Ma & Ba)}/{len(Ma)} names); {len(absent_mods)} modules absent"
      + (f": {', '.join(absent_mods)}" if absent_mods else "") + " |")
    w("")
    w(f"**Bottom line:** the gate {'FAILS' if result.failed else 'PASSES'} — "
      f"{len(result.gaps)} gap(s): a call one host cannot resolve, or a signature that does not "
      f"take it. Helper library at {helper_cov}% with {len(absent_mods)} module(s) absent"
      + (f" ({', '.join(absent_mods)})" if absent_mods else "")
      + "; a name blendertk lacks is a gap only where a shared panel calls it.")
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
    w("> Caveat: a Maya name with no Blender twin is often Maya machinery the Blender side does "
      "natively (`bpy.ops`) or does not need; it matters only where a shared panel calls it, "
      "which Layers 2-3 measure.")
    w("")

    # L3
    w("---\n\n## Layer 3 — Tool panels")
    w("")
    w("Each tool's one Slots class (`slots/tools/<tool>.py`, its helpers in `_<tool>/`). *hosts*: "
      "the hosts it serves (`slots.tools.HOSTS`; `standalone` = its own switchboard, no host). "
      "*one-host*: distinct chains one library lacks, hidden or guarded there.")
    w("")
    w("| tool | hosts | chains | sites | one-host | gap sites |")
    w("|:--|:--|--:|--:|--:|--:|")
    for t in tools:
        r = rows[t]
        gaps = f"**{r['gaps']}**" if r["gaps"] else "0"
        w(f"| {t[len('tools/'):]} | {hosts_of.get(t, 'both')} | {len(r['chains'])} | {r['sites']} | "
          f"{r['one_host']} | {gaps} |")
    w("")

    # L2 / L1
    w("---\n\n## Layers 1-2 — Categories")
    w("")
    w("Each marking-menu category's one Slots class (`slots/<category>.py`) over its `ui/<category>"
      "*.ui`. *buttons*: widgets with a handler; *hidden M / B*: of them, tagged for the other host. "
      "*Hollow* = parity theater: a visible control whose handler only pops a message box (a guard "
      "clause that then does work is not hollow, nor a control retired via `<name>_init → "
      "setVisible(False)`).")
    w("")
    w("| category | buttons | hidden M / B | controls | option boxes | chains | sites | one-host | gap sites | hollow |")
    w("|:--|--:|:--:|--:|--:|--:|--:|--:|--:|--:|")
    for rel in categories:
        r, (n, hid, m) = rows[rel], l1[rel]
        gaps = f"**{r['gaps']}**" if r["gaps"] else "0"
        w(f"| {Path(rel).stem} | {n} | {hid['maya']} / {hid['blender']} | {m['controls']} | "
          f"{m['opt_boxes']} | {len(r['chains'])} | {r['sites']} | {r['one_host']} | {gaps} | "
          f"{m['hollow'] or ''} |")
    w("")

    # methodology
    w("---\n\n## Methodology & honest limits")
    w("")
    w("- **Chains** = the toolkit reads a shared Slots class makes (`self.tk.<A>.<b>`, an engine "
      "instance's members), resolved statically against both libraries' sources — see "
      "`compare_panel_surface.py`'s docstring for what hides or guards a call.")
    w("- **Option boxes** = distinct slot methods whose body references `.option_box.`; "
      "**controls** = `.add(` calls minus `Separator`s.")
    w("- **Limits:** resolution proves a name and a signature, not behavior — it cannot see whether "
      "an operation does on Blender what it does on Maya. The only true \"feels seamless\" test is "
      "running both.")
    w("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if PARITY_AUDIT.md is stale (CI)")
    ap.add_argument("--allow-stale", action="store_true", help="skip the registry-freshness guard")
    args = ap.parse_args(argv)
    if not args.allow_stale:
        for pkg in ("mayatk", "blendertk"):
            check_registry_freshness(pkg)
    report = build()
    if args.check:
        cur = read(OUT) if os.path.isfile(OUT) else ""
        if cur.strip() != report.strip():
            print("STALE: PARITY_AUDIT.md differs from generator output. Re-run generate_parity_audit.py.")
            sys.exit(1)
        print("Up to date:", OUT)
        return
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(report)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
