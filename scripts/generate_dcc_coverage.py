"""Generate the tentacle DCC slot-coverage report (BLENDER_PORT_PLAN M5).

Walks the shared ``tentacle/ui/*.ui`` widget surface (the port-checklist denominator) and each
DCC's slot package, and emits ``tentacle/docs/DCC_COVERAGE.md`` — what % of each shared domain
is built per DCC, with the per-domain missing-widget lists for the ones in progress.

The "supported" predicate matches the runtime missing-slot hook (uitk ``connect_slot`` →
``on_missing_slot``) and the M2 contract test (``test_blender_slots.TestSharedUiContract``):
a widget counts as handled when the DCC slot class defines the widget method (a
deferred-message stub counts — the widget answers instead of dying silently) **or** a
``<name>_init`` (the hide-until-ported mechanism). This static form runs headless with no DCC
runtime (Maya slots can't even import outside Maya).

Usage:
    python generate_dcc_coverage.py          # writes tentacle/docs/DCC_COVERAGE.md
    python generate_dcc_coverage.py --check  # exit 1 if the report is stale
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TENTACLE = REPO_ROOT / "tentacle" / "tentacle"
UI_DIR = TENTACLE / "ui"
SLOTS_DIR = TENTACLE / "slots"
OUT_PATH = REPO_ROOT / "tentacle" / "docs" / "DCC_COVERAGE.md"

DCCS = ("maya", "blender")

# Widget-name shapes the slot layer is contractually bound to (matches the M2 test).
INTERACTIVE = re.compile(r"^(tb|b|chk|cmb|s|list|txt)\d")


def shared_domains() -> dict[str, set[str]]:
    """{domain: interactive widget names} from the shared ui/ root (not the maya_menus overlay)."""
    domains: dict[str, set[str]] = {}
    for f in sorted(UI_DIR.glob("*.ui")):
        domain = f.stem.split("#")[0]
        names = domains.setdefault(domain, set())
        for w in ET.parse(f).iter("widget"):
            n = w.get("name") or ""
            if INTERACTIVE.match(n):
                names.add(n)
    return {d: names for d, names in domains.items() if names}


def slot_methods(path: Path) -> set[str]:
    methods: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ClassDef):
            for x in node.body:
                if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(x.name)
    return methods


def build_report() -> str:
    domains = shared_domains()
    lines = [
        "# tentacle — DCC Slot Coverage",
        "",
        "_Auto-generated (BLENDER_PORT_PLAN M5). Do not edit by hand. Refresh via"
        " `m3trik/scripts/generate_dcc_coverage.py`._",
        "",
        "A widget counts as **handled** when the DCC's slot class defines the widget method"
        " (deferred-message stubs count) or a `<name>_init` (hidden-until-ported). The"
        " denominator is the interactive widget surface of the shared `ui/*.ui` files —"
        " `ui/maya_menus/` overlays are Maya-only whole menus and are out of scope by design.",
        "",
        "| Domain | Widgets | " + " | ".join(d.capitalize() for d in DCCS) + " |",
        "|:---|--:|" + "|".join("--:" for _ in DCCS) + "|",
    ]
    totals = {d: 0 for d in DCCS}
    total_widgets = 0
    missing_by_dcc: dict[str, dict[str, list[str]]] = {d: {} for d in DCCS}

    for domain, widgets in sorted(domains.items()):
        total_widgets += len(widgets)
        row = [f"| {domain} | {len(widgets)} "]
        for dcc in DCCS:
            slot_file = SLOTS_DIR / dcc / f"{domain}.py"
            if not slot_file.exists():
                row.append("| — ")
                missing_by_dcc[dcc][domain] = sorted(widgets)
                continue
            methods = slot_methods(slot_file)
            handled = {w for w in widgets if w in methods or f"{w}_init" in methods}
            missing = sorted(widgets - handled)
            if missing:
                missing_by_dcc[dcc][domain] = missing
            totals[dcc] += len(handled)
            pct = 100.0 * len(handled) / len(widgets)
            row.append(f"| {pct:.0f}% ")
        lines.append("".join(row) + "|")

    pct_row = [f"| **TOTAL** | **{total_widgets}** "]
    for dcc in DCCS:
        pct = 100.0 * totals[dcc] / total_widgets if total_widgets else 0.0
        pct_row.append(f"| **{pct:.0f}%** ")
    lines.append("".join(pct_row) + "|")

    for dcc in DCCS:
        gaps = missing_by_dcc[dcc]
        if not gaps:
            continue
        lines += ["", f"## {dcc} — unhandled widgets", ""]
        for domain, missing in sorted(gaps.items()):
            slot_file = SLOTS_DIR / dcc / f"{domain}.py"
            note = "" if slot_file.exists() else " *(no slot file)*"
            lines.append(f"- **{domain}**{note}: {', '.join(missing)}")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if the report is stale.")
    args = parser.parse_args(argv)

    report = build_report()
    existing = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else None
    if existing == report:
        print(f"Up to date: {OUT_PATH}")
        return 0
    if args.check:
        print(f"Stale: {OUT_PATH}", file=sys.stderr)
        return 1
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
