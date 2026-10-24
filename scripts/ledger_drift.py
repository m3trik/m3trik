#!/usr/bin/python
# coding=utf-8
"""Has the code a ledger entry names changed since it was verified?

``.claude/BACKLOG.md`` and ``FUTURE.md`` entries are leads written against the
code of their day, and the code moves under them (measured 2026-08-20: 0 of 22
prescribed fixes survived critique unchanged; 2026-10-20: of 5 FUTURE entries
spot-checked, 2 had a superseded premise). A date says nothing about whether
THIS entry's code moved -- release commits squash weeks of work under one date --
so the check is on the code itself: when an entry is verified, its ``- Anchors:``
line records a short hash of each definition it names; ``check`` recomputes them
and names every entry whose anchored code changed or vanished. Such an entry
must be re-measured before anyone acts on it (the /backlog skill's SELECT).

A name is anchored when it is a backticked ``Name`` or ``Class.member`` in the
entry's heading or ``- Where:`` line that some module of the entry's packages
defines at top level (a class, function, or ``UPPER_CASE`` constant) -- or, for
``Class.member``, a method or attribute of that class. The hash is of the
definition's AST in a canonical form (:func:`canonical`: node types and non-empty
fields, the same under every interpreter -- ``ast.dump`` and ``ast.unparse`` are
not), so reformatting and comments never flag drift; a name defined in several
modules hashes all of its definitions.

Usage:
    python ledger_drift.py stamp "<heading text>"   # print the - Anchors: line
    python ledger_drift.py check [--strict]         # entries whose anchors moved

``check`` exits 0 (a report); ``--strict`` exits 1 when any anchor moved.
"""

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]
LEDGERS = (WORKSPACE / ".claude" / "BACKLOG.md", WORKSPACE / ".claude" / "FUTURE.md")

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import affected_tests  # noqa: E402  (sibling: the cached package/module index)

ENTRY = re.compile(r"(?m)^(?=## 20\d\d-\d\d-\d\d \|)")
ANCHORS = re.compile(r"(?m)^- Anchors: (.+)$")
TOKEN = re.compile(r"`([^`]+)`")
NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
#: Package aliases the ledgers write names through (``ptk.X`` names ``X``).
ALIASES = {"ptk", "mtk", "btk", "uitk", "pythontk", "mayatk", "blendertk", "tentacle", "unitytk", "extapps"}


def entries(text: str) -> List[str]:
    return [p for p in ENTRY.split(text) if p.startswith("## 20")]


def heading(entry: str) -> str:
    return entry.splitlines()[0]


def entry_packages(entry: str) -> List[str]:
    cols = [c.strip() for c in heading(entry)[3:].split("|")]
    known = affected_tests.packages()
    return [p.strip() for p in cols[1].split(",") if p.strip() in known] if len(cols) > 1 else []


def candidate_names(entry: str) -> List[str]:
    """Backticked ``Name`` / ``Class.member`` tokens of the heading + Where line."""
    lines = [heading(entry)] + [ln for ln in entry.splitlines() if ln.startswith("- Where:")]
    found = []
    for token in TOKEN.findall("\n".join(lines)):
        for dotted in NAME.findall(token):
            parts = dotted.split(".")
            if parts[0] in ALIASES and len(parts) > 1:
                parts = parts[1:]
            head = parts[-2] if len(parts) > 1 else parts[0]
            if len(head) >= 4:
                found.append(".".join(parts[-2:]))  # ``Class.member``, or a bare name
    return list(dict.fromkeys(found))


def _definitions(tree: ast.Module, name: str) -> List[ast.AST]:
    head, _, member = name.partition(".")
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == head:
            if not member:
                nodes.append(node)
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == member:
                        nodes.append(child)
                    elif isinstance(child, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == member for t in child.targets
                    ):
                        nodes.append(child)
        elif not member and isinstance(node, ast.Assign) and head.isupper() and any(
            isinstance(t, ast.Name) and t.id == head for t in node.targets
        ):
            nodes.append(node)
    if not nodes and not member:
        # A bare method name (``_collect_file_info``): every class that has it.
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                nodes.extend(
                    child for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == head
                )
    return nodes


#: Fields that carry no meaning a definition's reader sees: the load/store
#: context (derived), a ``# type:`` comment, a string's ``u`` prefix.
_COSMETIC = {"ctx", "type_comment", "kind"}


def canonical(node) -> str:
    """*node* as text that names the code, not the interpreter: node types and
    their non-empty fields, minus the empty string 3.12 appends to an f-string
    format spec ending in a field. Measured 2026-10-24 over 51472 workspace
    definitions, 3.11 vs 3.12: ``ast.dump`` differed for every one (3.12 adds
    ``type_params``; 3.13 also drops empty fields), ``ast.unparse`` for 1956
    (3.12 re-quotes f-strings), this for none."""
    if isinstance(node, list):
        return "[" + ", ".join(canonical(item) for item in node) + "]"
    if not isinstance(node, ast.AST):
        return repr(node)
    parts = []
    for name, value in ast.iter_fields(node):
        if isinstance(node, ast.JoinedStr) and name == "values":
            value = [v for v in value if not (isinstance(v, ast.Constant) and v.value == "")]
        if value is None or value == [] or name in _COSMETIC:
            continue
        parts.append(f"{name}={canonical(value)}")
    return f"{type(node).__name__}({', '.join(parts)})"


def definition_files(pkg: str) -> List["affected_tests.FileInfo"]:
    """Where *pkg*'s named code can live: its source modules, plus the test
    harness beside its tests (``run_tests.py``, ``base_test.py``, a suite
    driver) -- entries about the test infrastructure name those."""
    package = affected_tests.packages()[pkg]
    harness = [
        affected_tests._parse(path, package.import_root)
        for path in sorted(package.test_dir.glob("*.py"))
        if not path.name.startswith("test_")
    ]
    return list(affected_tests.source_files(pkg)) + [info for info in harness if info]


def fingerprint(name: str, packages: Sequence[str]) -> Optional[str]:
    """8-hex hash of every definition of *name* in *packages*, or None if none."""
    head = name.split(".")[0]
    digest = hashlib.sha1()
    hit = False
    for pkg in packages:
        for info in definition_files(pkg):
            as_method = "." not in name and any(m.endswith("." + head) for m in info.members)
            if head not in info.defines and not as_method:
                continue
            try:
                tree = ast.parse(info.path.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, SyntaxError, ValueError):
                continue
            for node in _definitions(tree, name):
                digest.update(info.module.encode())
                digest.update(canonical(node).encode())
                hit = True
    return digest.hexdigest()[:8] if hit else None


def stamp_line(entry: str) -> Optional[str]:
    """The ``- Anchors:`` line for *entry* now, or None when it names no definition."""
    packages = entry_packages(entry)
    pairs = []
    for name in candidate_names(entry):
        value = fingerprint(name, packages)
        if value:
            pairs.append(f"{name}@{value}")
    return f"- Anchors: {' '.join(pairs)}" if pairs else None


def drift(entry: str) -> List[Tuple[str, str, Optional[str]]]:
    """``(name, recorded, now)`` for each anchor that no longer matches (now None = gone)."""
    match = ANCHORS.search(entry)
    if not match:
        return []
    packages = entry_packages(entry)
    moved = []
    for pair in match.group(1).split():
        name, _, recorded = pair.partition("@")
        now = fingerprint(name, packages)
        if now != recorded:
            moved.append((name, recorded, now))
    return moved


def check(paths: Iterable[Path] = LEDGERS) -> List[Tuple[Path, str, list]]:
    affected_tests._load_index()
    report = []
    for path in paths:
        if not path.is_file():
            continue
        for entry in entries(path.read_text(encoding="utf-8")):
            moved = drift(entry)
            if moved:
                report.append((path, heading(entry), moved))
    affected_tests.save_index()
    return report


def find_entry(text: str) -> Optional[str]:
    """The one entry whose heading contains *text* across both ledgers."""
    hits = [e for path in LEDGERS if path.is_file()
            for e in entries(path.read_text(encoding="utf-8")) if text in heading(e)]
    if len(hits) != 1:
        raise SystemExit(f"{len(hits)} entries match {text!r}; give more of the heading")
    return hits[0]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    stamp = sub.add_parser("stamp", help="print the - Anchors: line for one entry")
    stamp.add_argument("heading", help="text from the entry's heading")
    chk = sub.add_parser("check", help="entries whose anchored code moved")
    chk.add_argument("--strict", action="store_true", help="exit 1 when any anchor moved")
    args = parser.parse_args(argv)

    if args.cmd == "stamp":
        affected_tests._load_index()
        line = stamp_line(find_entry(args.heading))
        affected_tests.save_index()
        print(line or "(no backticked name in the heading / Where line resolves to a definition)")
        return 0

    report = check()
    for path, head, moved in report:
        print(f"{path.name}: {head[:110]}")
        for name, recorded, now in moved:
            print(f"    {name}: {recorded} -> {now or 'GONE'}")
    print(f"{len(report)} entr{'y' if len(report) == 1 else 'ies'} with moved anchors"
          + (" -- re-measure before acting on them." if report else "."))
    return 1 if (report and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
