"""Tooltip sweep: every rich-text tooltip in the workspace must render as valid markup.

Qt auto-detects a tooltip string as rich text the moment it contains markup, and
its parser is *silent* about breakage — a bare ``<`` opens a tag and swallows
everything up to the next ``>``, so the tail of a sentence simply disappears from
the popup with nothing logged. This gate makes that failure loud.

Deterministic, stdlib-only, CI-friendly: FAIL exits 1.

What it checks
--------------
Every ``…tooltip.fmt(...)`` / ``…tooltip.placeholder_preview(...)`` call reachable
through uitk's DSL (``self.sb.tooltip`` on a slots class, ``widget.tooltip`` on a
registered widget, or ``TooltipFormat`` imported directly), plus the ``toolTip``
properties declared in ``.ui`` files. Calls whose arguments aren't literals are
counted and skipped — they can only be judged at runtime.

The parse is structural, not a vocabulary check: named HTML entities Qt renders
(``&nbsp;``, ``&mdash;``, …) are neutralised first, since XML predefines only
five and would otherwise report them as errors.

Usage
-----
    python m3trik/scripts/check_tooltips.py [--workspace <dir>] [-v]
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

#: Directories that never hold hand-written tooltips (mirrors check_docs.py's set).
SKIP_DIRS = {
    "build", "dist", "__pycache__", ".git", "archive", ".archive", "node_modules",
    ".venv", "venv", "site-packages", ".pytest_cache", ".tox", ".idea", ".vscode",
    "temp_tests",
}
#: repo-relative posix prefixes holding vendored/third-party trees (as check_docs.py).
VENDORED = ("comfyui/app/", "www/www/assets/")
#: Generated Qt wrappers — fix the ``.ui``, not the output.
SKIP_SUFFIX = ("_ui.py",)

#: XML predefines only these five; Qt's rich text accepts the whole HTML set.
_XML_ENTITIES = ("amp", "lt", "gt", "quot", "apos")
_NAMED_ENTITY = re.compile(
    r"&(?!(?:%s);)[a-zA-Z#0-9]+;" % "|".join(_XML_ENTITIES)
)
#: HTML void elements are written unclosed (``<br>``); XML demands ``<br/>``.
_VOID = re.compile(r"<(br|hr|img|meta|link|input)\b([^>/]*)/?>", re.I)

_TOOLTIP_BUILDERS = ("fmt", "placeholder_preview")


def _load_dsl(workspace):
    """Import uitk's TooltipFormat from the workspace copy (not an installed one)."""
    sys.path.insert(0, os.path.join(workspace, "uitk"))
    from uitk.widgets.mixins.tooltip_mixin import TooltipFormat

    return TooltipFormat


def is_well_formed(html: str) -> str | None:
    """Return an error string when *html* isn't parseable markup, else None.

    Normalises the two places HTML is legally laxer than XML — named entities and
    unclosed void elements — so the parse reports *structural* breakage (a stray
    ``<``, a bogus ``<placeholder>``, a genuinely unbalanced tag) and nothing else.
    """
    probe = _NAMED_ENTITY.sub("&amp;", html)
    probe = _VOID.sub(r"<\1\2/>", probe)
    try:
        ET.fromstring(f"<root>{probe}</root>")
    except ET.ParseError as e:
        return str(e)
    return None


def _is_tooltip_call(node: ast.Call) -> bool:
    """True for ``<anything>.tooltip.fmt(...)`` or a bare ``TooltipFormat.fmt(...)``."""
    f = node.func
    if not isinstance(f, ast.Attribute) or f.attr not in _TOOLTIP_BUILDERS:
        return False
    owner = f.value
    if isinstance(owner, ast.Attribute) and owner.attr == "tooltip":
        return True
    return isinstance(owner, ast.Name) and owner.id == "TooltipFormat"


def scan_python(path, fmt_cls, failures, verbose):
    checked = skipped = 0
    try:
        tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
    except (SyntaxError, UnicodeDecodeError) as e:
        failures.append((path, 0, f"unparseable: {e}"))
        return 0, 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_tooltip_call(node):
            continue
        try:
            kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg}
            args = [ast.literal_eval(a) for a in node.args]
        except ValueError:
            skipped += 1  # runtime-built content; nothing static to verify
            continue
        try:
            html = getattr(fmt_cls, node.func.attr)(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — a bad call signature is a finding
            failures.append((path, node.lineno, f"call failed: {e}"))
            continue
        checked += 1
        err = is_well_formed(html)
        if err:
            failures.append((path, node.lineno, err))
        elif verbose:
            print(f"    ok {path}:{node.lineno}")
    return checked, skipped


def scan_ui(path, failures, verbose):
    """Check ``toolTip`` property strings declared in a Qt Designer file."""
    checked = 0
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        failures.append((path, 0, f"unparseable .ui: {e}"))
        return 0
    for prop in root.iter("property"):
        if prop.get("name") != "toolTip":
            continue
        text = (prop.findtext("string") or "").strip()
        # Plain text is fine — Qt only parses strings that look like markup.
        if not text or "<" not in text:
            continue
        checked += 1
        err = is_well_formed(text)
        if err:
            failures.append((path, 0, err))
        elif verbose:
            print(f"    ok {path} (toolTip)")
    return checked


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default=".", help="monorepo root (default: cwd)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    workspace = os.path.abspath(args.workspace)
    fmt_cls = _load_dsl(workspace)

    failures, checked, skipped, ui_checked = [], 0, 0, 0
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        here = os.path.relpath(dirpath, workspace).replace("\\", "/") + "/"
        if any(here.startswith(v) for v in VENDORED):
            dirnames[:] = []
            continue
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, workspace).replace("\\", "/")
            if fn.endswith(".py") and not fn.endswith(SKIP_SUFFIX):
                c, s = scan_python(path, fmt_cls, failures, args.verbose)
                checked += c
                skipped += s
                if failures and failures[-1][0] == path:
                    failures[-1] = (rel,) + failures[-1][1:]
            elif fn.endswith(".ui"):
                ui_checked += scan_ui(path, failures, args.verbose)

    for path, line, err in failures:
        rel = os.path.relpath(path, workspace).replace("\\", "/")
        where = f"{rel}:{line}" if line else rel
        print(f"  FAIL {where} — {err}")

    print(
        f"{checked} tooltip call(s) + {ui_checked} .ui toolTip(s) checked, "
        f"{skipped} runtime-built (skipped), {len(failures)} malformed"
    )
    if failures:
        print("MALFORMED TOOLTIPS — Qt renders these silently truncated.")
        return 1
    print("Result: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
