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
The 198 mayatk<->blendertk name collisions in ``docs/API_SHADOWS.md`` are the
deliberate public-API mirror that keeps tentacle's slots branch-free. Those are
not twins in this sense and are none of this script's business. What IS in scope
is the **controller tier**: helper mixins that carry the same algorithm in both
packages because there is nowhere shared for them to live (uitk hosts no
DCC-agnostic panel controller; pythontk cannot host Qt). Those files were copied,
and a copy nothing compares is a copy that drifts.

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
            "GapManagerMixin._gap_pair_at",
            "GapManagerMixin._refuse_if_gap_locked",
            "GapManagerMixin.on_gap_lock_all",
            "GapManagerMixin.on_gap_unlock_all",
        ),
        note=(
            "7 of 14 methods identical. The other 7 differ on the undo bracket: "
            "mayatk wraps edits in store.scene_edit(label), a primitive blendertk's "
            "store does not have (it uses CoreUtils.undo_chunk()). That asymmetry "
            "is also the root of the unguarded-boundary-edit bug in blendertk's "
            "shots_slots -- when it is resolved, re-measure and widen this list."
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
            "ShotNavMixin._sync_combobox",
            "ShotNavMixin._update_shot_nav_state",
            "ShotNavMixin.on_shot_block_clicked",
        ),
        note=(
            "4 of 8 methods identical. The rest wrap real DCC calls (playback "
            "range, selection) and are expected to differ."
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
            "generic FileDependencies -- so each baker carries the dataclass."
        ),
        symbols=("LightmapBakeResult",),
        note=(
            "The whole class, fields included. The two engines differ throughout "
            "(Arnold vs Cycles); only the result they report is shared."
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
    """``<root>/<pkg>/<pkg>/<rel>`` if the sibling is checked out, else ``None``."""
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
        or ``absent``. ``absent`` means a sibling is not checked out, which is
        not a failure -- it is a narrower run.
    """
    a_path, b_path = _source(spec.a, spec.rel), _source(spec.b, spec.rel)
    if a_path is None or b_path is None:
        which = spec.a if a_path is None else spec.b
        return "absent", [f"{which} not checked out"]

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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 on drift (default: report and exit 0)",
    )
    parser.add_argument("--list", action="store_true", help="print the ledger")
    args = parser.parse_args(argv)

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

    if not checked:
        # Same rule the sibling workflows apply to test counts: a run that
        # compared nothing is not a pass. Without this, a job whose checkout
        # silently lost a sibling reports green forever.
        print("\nFAIL: 0 twin(s) compared - nothing was checked out to compare.")
        return 1

    print(f"\n{checked} twin(s) compared, {len(bad)} with drift.")
    if bad and args.check:
        print(
            "\nA declared twin has diverged. Either port the change to the other "
            "side,\nor narrow the ledger entry and record WHY the two may now "
            "differ.\nCODE_STANDARD.md §6: a vendored copy is sanctioned only "
            "while it is guarded."
        )
        return 1
    if bad:
        print("(report mode: exit 0. Wire --check once the ledger is clear.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
