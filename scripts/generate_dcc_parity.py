"""Generate the tentacle DCC *depth*-parity report (the gap DCC_COVERAGE.md can't see).

``generate_dcc_coverage.py`` measures the **widget-name surface**: a ``tb000`` counts as
"handled" whether its option box builds 12 controls or 0. This report measures the layer below
that — the **option-box controls and dynamically-built menu buttons** each DCC slot constructs in
code (any ``…add(…, setObjectName=…)`` call: checkboxes, combos, spinboxes, header tools). That is
where real feature depth lives, and where Maya silently outruns Blender.

Method: AST-extract ``{objectName: label}`` from each ``slots/<dcc>/<domain>.py`` (idiom-independent
— matches inline ``widget.option_box.menu.add(...)`` and the ``menu = …; menu.add(...)`` form).
A control built under the **same objectName** in both DCCs is shared (the cross-DCC objectName rule
guarantees same name = same option). A control Maya builds that Blender doesn't is a **candidate gap**.

N/A DISCIPLINE (the whole point):
    The default status of every Maya-only control is **GAP** — it renders loudly as
    "unreviewed". A control is only excused via an explicit entry in
    ``tentacle/docs/dcc_parity_overrides.json`` that MUST carry a written ``reason``. Statuses:
        na             — no Blender mechanism exists at all (rare; justify concretely)
        divergent      — a different Blender paradigm covers it; needs a design decision
        done-elsewhere — already built in Blender under another objectName/mechanism (say where)
        planned        — accepted gap, scheduled (still counts against depth)
    Nothing reaches na/divergent/done-elsewhere by omission. The report flags any override that
    lacks a reason, and any override pointing at a control that no longer exists (stale).

Usage:
    python generate_dcc_parity.py            # writes tentacle/docs/DCC_PARITY.md
    python generate_dcc_parity.py --check    # exit 1 if the report is stale
    python generate_dcc_parity.py --strict   # additionally exit 1 if any UNREVIEWED gaps remain
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SLOTS_DIR = REPO_ROOT / "tentacle" / "tentacle" / "slots"
OUT_PATH = REPO_ROOT / "tentacle" / "docs" / "DCC_PARITY.md"
OVERRIDES_PATH = REPO_ROOT / "tentacle" / "docs" / "dcc_parity_overrides.json"

DCCS = ("maya", "blender")
SKIP = {"__init__.py", "_slots_maya.py", "_slots_blender.py"}
LABEL_KWARGS = ("setText", "setPrefix", "setTitle")
# kwargs whose constant values name/label a code-built control (see built_controls).
_CAPTURE_KWARGS = ("setObjectName", *LABEL_KWARGS, "addItems", "setToolTip")
EXCUSED = {"na", "divergent", "done-elsewhere"}  # excluded from the depth denominator
VALID_STATUS = EXCUSED | {"planned"}


def built_controls(path: Path) -> dict[str, str | None]:
    """{objectName: best-label} for every code-built control in a slot file.

    Idiom-independent: any ``Call`` carrying a ``setObjectName`` counts, regardless of the receiver
    chain. Two binding forms are resolved: a **string literal** (``setObjectName="chk000"``) and a
    **loop variable** bound from iterating a sequence/dict constant
    (``for name, label, … in self._CRITERIA: …add(setObjectName=name, setText=label)``) — the common
    way both DCC slots build a family of related checkboxes, which a literal-only scan would miss and
    silently under-count. Separators (no objectName) are skipped — visual grouping, not controls.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = _build_parents(tree)
    class_consts = _class_constants(tree, parents)

    out: dict[str, str | None] = {}
    for node in ast.walk(tree):  # pass 1 — literal setObjectName on any Call
        if isinstance(node, ast.Call):
            kw = _call_kw(node)
            name = _const_str(kw.get("setObjectName"))
            if name:
                out[name] = _label_from(kw)
    for node in ast.walk(tree):  # pass 2 — loop-variable setObjectName from a known constant
        if isinstance(node, ast.For):
            _record_loop_controls(node, class_consts, parents, out)
    return out


def _call_kw(node: ast.Call) -> dict:
    """The subset of a Call's keywords we care about, by arg name."""
    return {k.arg: k.value for k in node.keywords if k.arg in _CAPTURE_KWARGS}


def _label_from(kw: dict) -> str | None:
    """Best human label from a control's captured kwargs (literal text → items → trimmed tooltip)."""
    label = next((s for lk in LABEL_KWARGS if (s := _const_str(kw.get(lk)))), None)
    if not label and "addItems" in kw:  # comboboxes label themselves via their items
        label = _const_list(kw["addItems"])
    if not label:  # last resort so combos/tools aren't anonymous "(no label)"
        tip = _const_str(kw.get("setToolTip"))
        label = (tip[:60] + "…") if tip and len(tip) > 60 else tip
    return label


def _const_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _const_list(node) -> str | None:
    """A '/'-joined preview of a constant string list (e.g. ``addItems=["A","B"]``)."""
    if not isinstance(node, ast.List):
        return None
    items = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return ("{" + " / ".join(items) + "}") if items else None


# --- loop-variable resolution (controls built by iterating a sequence/dict constant) -------------

def _build_parents(tree) -> dict:
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


def _enclosing(node, parents, types):
    p = parents.get(node)
    while p is not None and not isinstance(p, types):
        p = parents.get(p)
    return p


def _class_constants(tree, parents) -> dict:
    """{name: value_node} for class/module-level sequence/dict literals (e.g. ``_CRITERIA = (...)``)."""
    consts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List, ast.Dict)):
            if isinstance(parents.get(node), (ast.ClassDef, ast.Module)):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        consts[t.id] = node.value
    return consts


def _seq_elts(node):
    return list(node.elts) if isinstance(node, (ast.Tuple, ast.List)) else None


def _iter_const(iter_node) -> tuple[str | None, bool]:
    """(constant-name, via_items) for ``self.X`` / ``X`` / ``X.items()`` iterables, else (None, …)."""
    via_items = False
    node = iter_node
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "items":
        via_items, node = True, node.func.value
    if isinstance(node, ast.Attribute):  # self.X
        return node.attr, via_items
    if isinstance(node, ast.Name):  # local/module X
        return node.id, via_items
    return None, via_items


def _resolve_const(name, loop, class_consts, parents):
    """The value-node for ``name`` — a local assignment in the loop's function (last one wins),
    else a class/module constant."""
    func = _enclosing(loop, parents, (ast.FunctionDef, ast.AsyncFunctionDef))
    found = None
    if func is not None:
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, (ast.Tuple, ast.List, ast.Dict))
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
            ):
                found = node.value
    return found if found is not None else class_consts.get(name)


def _rows_of(const_node, via_items):
    """Yield each iterated row as a list of element nodes. A dict via ``.items()`` yields
    ``[key, value]``; a sequence-of-sequences yields the inner elements; a flat sequence yields
    one-element rows."""
    if via_items:
        if isinstance(const_node, ast.Dict):
            for k, v in zip(const_node.keys, const_node.values):
                yield [k, v]
        return
    for row in _seq_elts(const_node) or []:
        yield _seq_elts(row) or [row]


def _target_path(target, varname):
    """Index path to ``varname`` within a for-loop target (e.g. ``a, (b, c)`` → b is ``[1, 0]``)."""
    if isinstance(target, ast.Name):
        return [] if target.id == varname else None
    for i, e in enumerate(_seq_elts(target) or []):
        if isinstance(e, ast.Name) and e.id == varname:
            return [i]
        sub = _target_path(e, varname)
        if sub is not None:
            return [i, *sub]
    return None


def _index_path(row, path):
    """Resolve the node at ``path`` within a row's element list (descending into nested seqs)."""
    cur, node = row, None
    for depth, idx in enumerate(path):
        if not isinstance(cur, list) or idx >= len(cur):
            return None
        node = cur[idx]
        if depth < len(path) - 1:
            cur = _seq_elts(node)
            if cur is None:
                return None
    return node


def _record_loop_controls(loop, class_consts, parents, out):
    """Record controls a ``for`` loop builds by iterating a known sequence/dict constant."""
    const_name, via_items = _iter_const(loop.iter)
    if not const_name:
        return
    const_node = _resolve_const(const_name, loop, class_consts, parents)
    if const_node is None:
        return
    rows = list(_rows_of(const_node, via_items))
    if not rows:
        return
    for call in ast.walk(loop):
        if not isinstance(call, ast.Call):
            continue
        kw = _call_kw(call)
        on = kw.get("setObjectName")
        if not isinstance(on, ast.Name):
            continue
        name_path = _target_path(loop.target, on.id)
        if name_path is None:
            continue
        label_paths = {
            lk: p
            for lk in LABEL_KWARGS
            if isinstance(kw.get(lk), ast.Name)
            and (p := _target_path(loop.target, kw[lk].id)) is not None
        }
        for row in rows:
            name = _const_str(_index_path(row, name_path))
            if not name:
                continue
            label = next(
                (s for lk in LABEL_KWARGS if lk in label_paths
                 and (s := _const_str(_index_path(row, label_paths[lk])))),
                None,
            )
            out[name] = label if label is not None else _label_from(kw)


def load_overrides() -> dict[str, dict]:
    if not OVERRIDES_PATH.exists():
        return {}
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


def _override_fields(ov) -> tuple[str | None, str]:
    """(status, reason) from an override entry, tolerant of malformed JSON (non-dict entry or a
    null/non-string ``reason``) — a hand-edited config must flag bad entries, never crash the report."""
    if not isinstance(ov, dict):
        return None, ""
    return ov.get("status"), str(ov.get("reason") or "").strip()


def domains() -> list[str]:
    names = set()
    for dcc in DCCS:
        for f in (SLOTS_DIR / dcc).glob("*.py"):
            if f.name not in SKIP:
                names.add(f.stem)
    return sorted(names)


def build_report() -> tuple[str, int]:
    overrides = load_overrides()
    used_keys: set[str] = set()
    bad_overrides: list[str] = []

    rows = []
    gap_lists: dict[str, list[tuple[str, str | None]]] = {}
    excused_lists: dict[str, list[tuple[str, str | None, str, str]]] = {}
    tot_maya = tot_shared = tot_gap = tot_excused = tot_planned = 0

    for domain in domains():
        maya_f = SLOTS_DIR / "maya" / f"{domain}.py"
        bl_f = SLOTS_DIR / "blender" / f"{domain}.py"
        maya = built_controls(maya_f) if maya_f.exists() else {}
        bl = built_controls(bl_f) if bl_f.exists() else {}
        if not maya:
            continue  # nothing built in code on the Maya side — no depth to compare

        shared = sorted(set(maya) & set(bl))
        maya_only = sorted(set(maya) - set(bl))

        gaps, excused, planned = [], [], 0
        for name in maya_only:
            key = f"{domain}:{name}"
            ov = overrides.get(key)
            if ov is None:
                gaps.append((name, maya[name]))
                continue
            used_keys.add(key)
            status, reason = _override_fields(ov)
            if status not in VALID_STATUS or not reason:
                bad_overrides.append(key)
                gaps.append((name, maya[name]))  # invalid override → still a gap
                continue
            if status == "planned":
                planned += 1
                gaps.append((name, maya[name]))  # planned still counts as an open gap
            else:
                excused.append((name, maya[name], status, reason))

        # depth denominator excludes truly-excused controls (na/divergent/done-elsewhere)
        denom = len(maya) - len(excused)
        depth = 100.0 * len(shared) / denom if denom else 100.0
        rows.append((domain, len(maya), len(bl), len(shared), len(gaps), len(excused), depth))
        if gaps:
            gap_lists[domain] = gaps
        if excused:
            excused_lists[domain] = excused

        tot_maya += len(maya)
        tot_shared += len(shared)
        tot_gap += len(gaps)
        tot_excused += len(excused)
        tot_planned += planned

    # stale overrides: keys that matched nothing this run (ignore _-prefixed meta/doc keys)
    stale = sorted(k for k in (set(overrides) - used_keys) if not k.startswith("_"))

    L = [
        "# tentacle — DCC Depth Parity (option-box & dynamic-control level)",
        "",
        "> ⚠️ **Superseded by `PARITY_AUDIT.md` for true parity.** This reaches a high parity % by"
        " *excusing* Maya-only controls via `dcc_parity_overrides.json` rather than closing them, and"
        " it only sees option-box controls — not the missing tool-panels or the absent blendertk"
        " modules. See [`PARITY_AUDIT.md`](PARITY_AUDIT.md).",
        "",
        "_Auto-generated. Do not edit by hand. Refresh via"
        " `m3trik/scripts/generate_dcc_parity.py`._",
        "",
        "`DCC_COVERAGE.md` measures widget **presence** (100%/100%). This measures the layer"
        " below it: the **controls each slot builds in code** (option-box checkboxes/combos/"
        "spinboxes + dynamic header buttons). A Maya-only control is a **GAP by default** — it is"
        " only excused via a written, reasoned entry in"
        " [`dcc_parity_overrides.json`](dcc_parity_overrides.json). Nothing becomes N/A by omission.",
        "",
        "**Depth %** = controls built in *both* DCCs ÷ (Maya controls − excused). `planned` gaps"
        " still count as open.",
        "",
        f"## Headline: {tot_gap} open gap(s) — of which **{tot_gap - tot_planned} UNREVIEWED**"
        f", {tot_planned} planned · {tot_excused} excused (na/divergent/elsewhere)",
        "",
        "| Domain | Maya | Blender | Shared | Open gaps | Excused | Depth |",
        "|:---|--:|--:|--:|--:|--:|--:|",
    ]
    for d, m, b, s, g, e, depth in rows:
        flag = " ⚠️" if g else ""
        L.append(f"| {d}{flag} | {m} | {b} | {s} | {g} | {e} | {depth:.0f}% |")
    denom_tot = tot_maya - tot_excused
    tot_depth = 100.0 * tot_shared / denom_tot if denom_tot else 100.0
    L.append(
        f"| **TOTAL** | **{tot_maya}** | — | **{tot_shared}** | **{tot_gap}** |"
        f" **{tot_excused}** | **{tot_depth:.0f}%** |"
    )

    L += ["", "## Open gaps — Maya-only controls Blender doesn't build", ""]
    if not gap_lists:
        L.append("_None._")
    for domain, gaps in gap_lists.items():
        L.append(f"### {domain}")
        for name, label in gaps:
            key = f"{domain}:{name}"
            tag = ""
            status, reason = _override_fields(overrides.get(key))
            if status == "planned":
                tag = f" — _planned: {reason}_"
            elif key in bad_overrides:
                tag = " — ⚠️ **invalid override (missing reason or bad status) → treated as gap**"
            L.append(f"- `{name}` — {label or '(no label)'}{tag}")
        L.append("")

    if excused_lists:
        L += ["## Excused (auditable — challenge any that aren't truly justified)", ""]
        for domain, excused in excused_lists.items():
            L.append(f"### {domain}")
            for name, label, status, reason in excused:
                L.append(f"- `{name}` — {label or '(no label)'} · **{status}**: {reason}")
            L.append("")

    if stale or bad_overrides:
        L += ["## Override hygiene", ""]
        for key in bad_overrides:
            L.append(f"- ⚠️ `{key}` — invalid: status must be one of {sorted(VALID_STATUS)} and a non-empty reason is required.")
        for key in stale:
            L.append(f"- 🗑️ `{key}` — stale: matches no current Maya-only control (remove it).")
        L.append("")

    unreviewed = tot_gap - tot_planned
    return "\n".join(L).rstrip() + "\n", unreviewed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="Exit 1 if the report is stale.")
    p.add_argument("--strict", action="store_true", help="Exit 1 if any UNREVIEWED gaps remain.")
    args = p.parse_args(argv)

    report, unreviewed = build_report()
    existing = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else None
    if existing != report:
        if args.check:
            print(f"Stale: {OUT_PATH}", file=sys.stderr)
            return 1
        OUT_PATH.write_text(report, encoding="utf-8")
        print(f"Wrote {OUT_PATH}")
    else:
        print(f"Up to date: {OUT_PATH}")

    if args.strict and unreviewed:
        print(f"{unreviewed} unreviewed depth gap(s) remain.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
