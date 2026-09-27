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

Reset controls
--------------
Every *Reset to Defaults* / *Restore Defaults* button speaks one grammar --
Click, Shift+Click saves the current values as the defaults, Ctrl+Shift+Click
forgets them -- and carries the tooltip that teaches it, because both come from
one class: ``uitk.managers.reset_gesture.ResetGesture``. A button wired by hand
drifts: it keeps a plain click and a one-line tooltip (the uitk bridges, rizom
among them, and fourteen mayatk/blendertk panels did). Production code fails when

* it names ``reset_all`` outside uitk's managers (the primitives own it) -- a
  call, or a reference handed to a signal, or
* it spells a reset label (``setText("Reset to Defaults")``, ``menu.add(...,
  setText=...)``, a label kept in an attribute) and the function doing so never
  builds a ``ResetGesture``. A label that is prose -- a tooltip title, a dialog's
  text -- is not a control, or
* a ``.ui`` declares a widget with that label and a module the Switchboard may
  bind it to (beside it, or under tentacle's sibling ``slots/``) does not attach
  the gesture to that widget, in ``<name>_init`` or as ``ResetGesture(....name)``.

Tests are exempt. A reset that can't be wired goes in :data:`RESET_ALLOWLIST`
with its reason.

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
    "build",
    "dist",
    "__pycache__",
    ".git",
    "archive",
    ".archive",
    "node_modules",
    ".venv",
    "venv",
    "site-packages",
    ".pytest_cache",
    ".tox",
    ".idea",
    ".vscode",
    "temp_tests",
}
#: repo-relative posix prefixes holding vendored/third-party trees (as check_docs.py).
VENDORED = ("comfyui/app/", "www/www/assets/")
#: Generated Qt wrappers — fix the ``.ui``, not the output.
SKIP_SUFFIX = ("_ui.py",)

#: XML predefines only these five; Qt's rich text accepts the whole HTML set.
_XML_ENTITIES = ("amp", "lt", "gt", "quot", "apos")
_NAMED_ENTITY = re.compile(r"&(?!(?:%s);)[a-zA-Z#0-9]+;" % "|".join(_XML_ENTITIES))
#: HTML void elements are written unclosed (``<br>``); XML demands ``<br/>``.
_VOID = re.compile(r"<(br|hr|img|meta|link|input)\b([^>/]*)/?>", re.I)

_TOOLTIP_BUILDERS = ("fmt", "placeholder_preview")

#: A control carrying one of these labels resets a panel's fields.
_RESET_LABEL = re.compile(r"^\s*(?:reset(?: to)?|restore) defaults\s*$", re.I)
#: The one place ``reset_all`` may be named: the reset primitives.
_RESET_OWNERS = ("uitk/uitk/managers/",)
#: Calls whose text is prose about a reset (a tooltip, a dialog), not a control.
_RESET_PROSE_CALLS = (
    "fmt",
    "placeholder_preview",
    "message_box",
    "setToolTip",
    "setStatusTip",
    "setWindowTitle",
)
#: Resets that can't be wired through ResetGesture, each with the reason. A
#: growing list means ResetGesture lacks a capability -- extend it instead.
RESET_ALLOWLIST = {
    "tentacle/tentacle/ui/settings.ui": (
        "b_reset_bindings restores the marking-menu bindings, not panel fields"
    ),
    "uitk/uitk/widgets/editors/color_mapping_editor.py": (
        "clears colour overrides from a mapping table; no field default to save"
    ),
    "uitk/uitk/widgets/editors/style_editor.py": (
        "its own StyleEditor.reset_all clears theme overrides -- the user's styling, "
        "with no field defaults behind them"
    ),
    "uitk/uitk/widgets/textViewBox.py": (
        "QDialogButtonBox's standard RestoreDefaults button; the dialog's caller "
        "decides what it does"
    ),
    "uitk/uitk/widgets/widgetComboBox.py": (
        "a dropdown action row (a QAction: no button to host the gesture) that "
        "restores embedded widgets to their in-memory add-time snapshot; nothing "
        "persisted to save or forget"
    ),
}


def _load_dsl(workspace):
    """Import pythontk's TooltipFormat from the workspace copy (not an installed one).

    The DSL is pure string work and lives in pythontk (``str_utils/
    tooltip_format.py``; uitk's ``tooltip_mixin`` until 2026-09-26). The
    workspace copy goes on the path: on a bare CI runner the siblings are
    CLONED, never installed -- the gate once died with ``ModuleNotFoundError:
    No module named 'pythontk'`` (measured 2026-09-17, m3trik tests.yml) -- and
    an installed pythontk would be the wrong one to check against anyway.
    """
    root = os.path.join(workspace, "pythontk")
    if os.path.isdir(root) and root not in sys.path:
        sys.path.insert(0, root)
    from pythontk import TooltipFormat

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


def _parse(path, failures):
    """The parsed module, or ``None`` (reported as a finding)."""
    try:
        return ast.parse(io.open(path, encoding="utf-8-sig").read())
    except (SyntaxError, UnicodeDecodeError) as e:
        failures.append((path, 0, f"unparseable: {e}"))
        return None


def scan_python(path, tree, fmt_cls, failures, verbose):
    checked = skipped = 0
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


def _reset_exempt(rel):
    """Tests, the reset primitives' own package, and allowlisted resets."""
    parts = rel.split("/")[:-1]
    return (
        "test" in parts
        or "tests" in parts
        or rel.startswith(_RESET_OWNERS)
        or rel in RESET_ALLOWLIST
    )


def _callee(call):
    """The called name: ``b`` for ``a.b(...)`` and ``b(...)`` alike."""
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _builds_gesture(node):
    """Whether *node*'s subtree constructs a ``ResetGesture``."""
    return any(
        isinstance(n, ast.Call) and _callee(n) == "ResetGesture" for n in ast.walk(node)
    )


def scan_reset_python(rel, tree, failures):
    """Flag a production reset that bypasses ResetGesture. Returns controls seen."""
    if _reset_exempt(rel):
        return 0
    prose = set()  # label constants that describe a reset rather than label one
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _callee(node) in _RESET_PROSE_CALLS:
                prose.update(id(n) for n in ast.walk(node))
            prose.update(id(k.value) for k in node.keywords if k.arg == "title")
    seen = 0

    def visit(node, scope):
        nonlocal seen
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child)
                continue
            if isinstance(child, ast.Attribute) and child.attr == "reset_all":
                seen += 1
                failures.append(
                    (rel, child.lineno, "hand-wires reset_all -- attach ResetGesture")
                )
            elif (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and _RESET_LABEL.match(child.value)
                and id(child) not in prose
            ):
                seen += 1
                if not _builds_gesture(scope):
                    failures.append(
                        (
                            rel,
                            child.lineno,
                            f"'{child.value.strip()}' control not wired through "
                            "ResetGesture in the function that builds it",
                        )
                    )
            visit(child, scope)

    visit(tree, tree)
    return seen


def _slots_modules(ui_path, trees):
    """The modules the Switchboard binds *ui_path* to, found the way it looks.

    uitk's ``switchboard.names``: a class ``<Name>Slots``, else ``<Name>``, else a
    slot-file name (``name.py``, ``name_slots.py``, ``nameSlots.py``,
    ``_name.py``) -- searched beside the ``.ui`` and, for tentacle's layout,
    under its sibling ``slots`` tree, where the Maya and Blender slots each bind
    the same file.
    """
    stem = os.path.basename(ui_path)[: -len(".ui")].split("#")[0]
    folder = os.path.dirname(ui_path)
    candidates = [
        os.path.join(folder, n)
        for n in sorted(os.listdir(folder))
        if n.endswith(".py") and not n.endswith(SKIP_SUFFIX)
    ]
    for dirpath, dirnames, filenames in os.walk(
        os.path.join(os.path.dirname(folder), "slots")
    ):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        candidates += [
            os.path.join(dirpath, n) for n in sorted(filenames) if n.endswith(".py")
        ]
    name = "".join(part.title() for part in stem.split("_"))
    for cls in (f"{name}Slots", name):
        found = [
            p
            for p in candidates
            if any(
                isinstance(n, ast.ClassDef) and n.name == cls
                for n in getattr(_tree(p, trees), "body", ())
            )
        ]
        if found:
            return found
    files = {f"{stem}.py", f"{stem}_slots.py", f"{stem}Slots.py", f"_{stem}.py"}
    return [p for p in candidates if os.path.basename(p) in files]


def _wires(tree, name):
    """Whether *tree* attaches ResetGesture to widget *name*: inside
    ``<name>_init``, or as ``ResetGesture(<...>.name)``."""
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == f"{name}_init" and _builds_gesture(node):
                return True
        elif (
            isinstance(node, ast.Call)
            and _callee(node) == "ResetGesture"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
            and node.args[0].attr == name
        ):
            return True
    return False


def _tree(path, trees):
    """*path*'s parsed module (``None`` if unparseable), cached in *trees*."""
    if path not in trees:
        trees[path] = _parse(path, [])
    return trees[path]


def scan_reset_ui(path, rel, failures, trees):
    """Flag a ``.ui`` reset button a module it binds to doesn't wire.

    *trees* caches parsed modules by path. Returns the reset controls seen.
    """
    if _reset_exempt(rel):
        return 0
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return 0  # scan_ui already reported it
    seen, modules = 0, None
    for widget in root.iter("widget"):
        label = next(
            (
                p.findtext("string") or ""
                for p in widget.findall("property")
                if p.get("name") == "text"
            ),
            "",
        )
        if not _RESET_LABEL.match(label):
            continue
        seen += 1
        if modules is None:
            modules = _slots_modules(path, trees)
        name = widget.get("name", "")
        where = f"'{label.strip()}' button {name}"
        if not modules:
            failures.append((rel, 0, f"{where}: no slots module found to wire it"))
        base = os.path.dirname(os.path.dirname(path))
        for module in modules:
            if not _wires(_tree(module, trees), name):
                module = os.path.relpath(module, base).replace("\\", "/")
                failures.append(
                    (rel, 0, f"{where} not wired through ResetGesture in {module}")
                )
    return seen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default=".", help="monorepo root (default: cwd)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    workspace = os.path.abspath(args.workspace)
    fmt_cls = _load_dsl(workspace)

    failures, checked, skipped, ui_checked = [], 0, 0, 0
    resets, reset_seen, trees = [], 0, {}
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
                # A .ui met earlier may have parsed it already (its slots lookup).
                tree = trees.get(path) or _parse(path, failures)
                if tree is None:
                    continue
                trees[path] = tree
                c, s = scan_python(path, tree, fmt_cls, failures, args.verbose)
                checked += c
                skipped += s
                reset_seen += scan_reset_python(rel, tree, resets)
            elif fn.endswith(".ui"):
                ui_checked += scan_ui(path, failures, args.verbose)
                reset_seen += scan_reset_ui(path, rel, resets, trees)

    for path, line, err in failures + resets:
        if os.path.isabs(path):
            path = os.path.relpath(path, workspace).replace("\\", "/")
        where = f"{path}:{line}" if line else path
        print(f"  FAIL {where} — {err}")

    print(
        f"{checked} tooltip call(s) + {ui_checked} .ui toolTip(s) checked, "
        f"{skipped} runtime-built (skipped), {len(failures)} malformed; "
        f"{reset_seen} reset control(s), {len(resets)} outside ResetGesture"
    )
    if failures:
        print("MALFORMED TOOLTIPS — Qt renders these silently truncated.")
    if resets:
        print(
            "RESET CONTROLS OUTSIDE ResetGesture — they lose Shift/Ctrl+Shift and "
            "the tooltip that teaches them. Wire the button with "
            "ResetGesture(button) (uitk.managers.reset_gesture)."
        )
    if failures or resets:
        return 1
    print("Result: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
