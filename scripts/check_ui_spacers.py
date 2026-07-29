#!/usr/bin/env python
"""Dead-space guard for the ecosystem's `.ui` panels.

A `Fixed` vertical spacer's `sizeHint` is its EXACT height — it can neither
grow nor shrink — so the number in the `.ui` is load-bearing. Qt Designer
stamps **20x40** on every spacer it creates, and an untuned default then ships
as a permanent band of dead space above the footer that the user cannot resize
away (live report: the tentacle materials panel; the same default was found in
seven mayatk/blendertk panels). The panels' deliberate gap is ~10px.

This is a workspace sweep rather than a per-repo test so the rule has ONE
implementation across `tentacle`, `mayatk`, `blendertk`, and `extapps`
(tentacle additionally pins it in its own CI suite via `test_ui_integrity.py`).

Checks
------
  SPACER    no `Fixed` vertical spacer taller than the allowed gap.

FAIL exits non-zero (CI gate).

Usage
-----
  python check_ui_spacers.py                 # sweep the whole workspace
  python check_ui_spacers.py --root PATH      # sweep one tree
  python check_ui_spacers.py --max-gap 12     # override the allowed gap
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
PACKAGES = ("tentacle", "mayatk", "blendertk", "extapps")
SKIP_PARTS = {"build", ".archive", "temp_tests", ".venv", "node_modules"}
DEFAULT_MAX_GAP = 12


def _spacer_height(spacer: ET.Element):
    """Return (orientation, size_type, hint_height) for a `<spacer>`."""
    orientation = size_type = ""
    height = None
    for prop in spacer.findall("property"):
        name = prop.get("name")
        if name == "orientation":
            orientation = prop.findtext("enum") or ""
        elif name == "sizeType":
            size_type = prop.findtext("enum") or ""
        elif name == "sizeHint":
            size = prop.find("size")
            if size is not None:
                try:
                    height = int(size.findtext("height") or 0)
                except ValueError:
                    height = None
    return orientation, size_type, height


def iter_offenders(root: Path, max_gap: int):
    """Yield `(path, spacer_name, height)` for every oversized Fixed spacer."""
    for path in sorted(root.rglob("*.ui")):
        if SKIP_PARTS & set(path.parts):
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            yield path, f"<malformed XML: {e}>", -1
            continue
        for spacer in tree.iter("spacer"):
            orientation, size_type, height = _spacer_height(spacer)
            if (
                orientation.endswith("Vertical")
                and size_type.endswith("Fixed")
                and height is not None
                and height > max_gap
            ):
                yield path, spacer.get("name") or "<unnamed>", height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="sweep a single tree instead of the whole workspace",
    )
    parser.add_argument(
        "--max-gap",
        type=int,
        default=DEFAULT_MAX_GAP,
        help=f"tallest allowed Fixed vertical spacer (default {DEFAULT_MAX_GAP}px)",
    )
    args = parser.parse_args()

    roots = [args.root] if args.root else [WORKSPACE / p for p in PACKAGES]
    offenders = []
    scanned = 0
    for root in roots:
        if not root.is_dir():
            print(f"WARN  missing tree: {root}")
            continue
        scanned += 1
        offenders.extend(iter_offenders(root, args.max_gap))

    if offenders:
        print(
            f"FAIL  {len(offenders)} oversized Fixed vertical spacer(s) — a Fixed "
            f"spacer's sizeHint is its exact height, so anything over "
            f"{args.max_gap}px is unresizable dead space (Qt Designer's default "
            f"is 20x40; tune it to ~10px):"
        )
        for path, name, height in offenders:
            try:
                shown = path.relative_to(WORKSPACE)
            except ValueError:
                shown = path
            detail = name if height < 0 else f"{name} = {height}px"
            print(f"        {shown}: {detail}")
        return 1

    print(f"OK    no oversized Fixed vertical spacers ({scanned} tree(s) scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
