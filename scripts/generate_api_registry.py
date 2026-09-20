"""Generate API registries for ecosystem packages by AST-walking their sources.

For each package, emits:
  - <package>/API_INDEX.md      — compact, grep-able symbol index (first-read
                                  entrypoint; top-level signatures + class
                                  method names, no bodies/docstrings)
  - <package>/API_REGISTRY.md   — human-readable registry of public symbols
  - <package>/API_REGISTRY.json — machine-readable sidecar (for diffing)
  - <package>/API_CHANGES.md    — public-API diff vs the last RELEASE (the
                                  JSON sidecar at origin/main; falls back to
                                  the working-tree sidecar when no such
                                  baseline resolves). Caveat: this reads the
                                  LOCAL origin/main without fetching, so "since
                                  the last release" really means "since the
                                  last release this checkout has fetched" —
                                  a stale remote-tracking ref understates the
                                  delta.

Also emits a monorepo-level cross-package shadow report:
  - m3trik/docs/API_SHADOWS.md  — symbols whose simple name collides across
                                  ecosystem packages (DRY review surface)

Usage:
    python generate_api_registry.py            # all ecosystem packages
    python generate_api_registry.py pythontk   # one or more by name
    python generate_api_registry.py --check    # exit 1 if registries stale
    python generate_api_registry.py uitk --check   # one package (the CI gate)
    python generate_api_registry.py uitk --no-shadows  # a release commit: the
                                               # package's own files only
    python generate_api_registry.py mayatk --semver    # JSON: the smallest
                                               # release this delta may ship as
                                               # ('minor' when it removes a
                                               # public symbol), for push.ps1's
                                               # semver gate. Writes nothing.

Outputs carry no generation date — git history is the clock. Regenerating an
unchanged source tree is byte-identical, so nothing downstream (the registry
bot, receipts, `git status`) ever sees churn that is not a surface change.

``--check`` writes nothing and compares CONTENT HASHES, never mtimes — see
``StalenessGate`` for exactly which artifacts are gated and which cosmetics are
normalized out. It is wired into each ecosystem package's own CI (tests.yml /
static-analysis.yml) as a per-package job, which is why the single-package form
above has to stand on its own: that checkout holds the package, this repo and
pythontk -- whose ``core_utils/symbol_record.py`` this module loads at import for
the shared ``SymbolRecord`` DTO, so the pythontk sibling is a hard requirement of
every job, not a convenience -- and nothing else. Anything cross-package (the
shadow report) is therefore out of scope there.

Design notes:
  * Walks <pkg>/<pkg>/ source root only — skips build/, dist/, test/, tests/,
    docs/, .venv/, __pycache__/.
  * Public surface = top-level functions/classes whose names do not start with
    `_`, plus public methods on those classes. Re-exports and dunders are
    excluded.
  * Module summary = first non-empty line of module docstring. Symbol summary
    likewise. Both are truncated to fit one terminal line.
  * Signatures are reproduced via ast.unparse so type annotations survive.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_symbol_record() -> type:
    """Load the shared ``SymbolRecord`` DTO from pythontk source WITHOUT
    importing the pythontk package (the module is pure-stdlib, so this keeps the
    generator dependency-free and runnable on a bare CI box). Single source of
    truth: ``pythontk/pythontk/core_utils/symbol_record.py``."""
    path = REPO_ROOT / "pythontk" / "pythontk" / "core_utils" / "symbol_record.py"
    spec = importlib.util.spec_from_file_location("_ptk_symbol_record", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load SymbolRecord from {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations via
    # sys.modules[cls.__module__], which is None for an unregistered module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SymbolRecord


SymbolRecord = _load_symbol_record()


def _load_version_key():
    """Load ``Deprecation.version_key`` from pythontk source, as above.

    The expiry gate and the runtime roster must agree on what a removal version
    IS; a second parser here would be free to drift into accepting something
    the other rejects, and the failure mode of that drift is an alias that
    never expires -- the exact bug the gate exists to catch. So when the
    sibling cannot supply one, this does NOT fall back to a local parser.

    A pythontk checkout predating ``core_utils/deprecation.py`` is a real and
    ROUTINE state, not a broken one: ``m3trik/CLAUDE.md`` requires this repo to
    reach main BEFORE the packages land their side of a cross-repo change, so
    between those two pushes every sibling is a pythontk without the module --
    and this import runs at module scope, where a raise takes down the whole
    generator, which every package's PR runs as ``--check``. Measured
    2026-09-17: it did, with `FileNotFoundError` at COLLECTION.

    The stand-in raises ``ValueError`` for every input, which is the contract
    both consumers already handle -- :func:`deprecations` sorts such a row last
    ("cannot expire, which is itself worth seeing") and
    :func:`expired_deprecations` skips it. The gate therefore goes quiet rather
    than wrong, and says so on stderr, because a silently disabled expiry gate
    is the failure this whole mechanism exists to prevent.
    """
    path = REPO_ROOT / "pythontk" / "pythontk" / "core_utils" / "deprecation.py"
    if not path.is_file():
        print(
            f"[api-registry] NOTE: {path} is absent (a pythontk predating "
            "ptk.Deprecation), so the deprecation EXPIRY GATE is inactive for "
            "this run. Registry output is unaffected; an overdue alias will "
            "not be reported until the sibling carries the module.",
            file=sys.stderr,
        )

        def _unavailable(version: str):
            raise ValueError(
                "no Deprecation.version_key: the pythontk sibling predates "
                "core_utils/deprecation.py"
            )

        return _unavailable

    spec = importlib.util.spec_from_file_location("_ptk_deprecation", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Deprecation from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Deprecation.version_key


_version_key = _load_version_key()

#: ``__version__ = "1.2.3"`` in a package root, read with a regex rather than an
#: import: this generator runs on a bare CI box where the package it is walking
#: is not installed and its dependencies are absent. The optional annotation
#: matters -- ``__version__: str = "1.2.3"`` is valid and would otherwise read
#: as "no version", which silently disables the expiry gate for that package.
_PKG_VERSION_RE = re.compile(
    r"^__version__\s*(?::[^=]*)?=\s*[\"']([^\"']+)[\"']", re.MULTILINE
)


def package_version(pkg_dir: Path, name: str) -> str:
    """The walked package's own ``__version__``, or ``""`` if it declares none."""
    init = pkg_dir / name / "__init__.py"
    if not init.is_file():
        return ""
    match = _PKG_VERSION_RE.search(init.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def deprecations(pkg: PackageData) -> list[tuple[str, str, str]]:
    """Every retired symbol in *pkg* as ``(relpath, qualname, remove_in)``.

    Sorted by removal version so the oldest debt reads first.
    """
    found: list[tuple[str, str, str]] = []
    for mod in pkg.modules:
        for fn in mod.functions:
            if fn.deprecated:
                found.append((mod.relpath, fn.qualname, fn.remove_in))
        for cls in mod.classes:
            if cls.deprecated:
                found.append((mod.relpath, cls.name, cls.remove_in))
            for member in cls.members:
                if member.deprecated:
                    found.append((mod.relpath, member.qualname, member.remove_in))

    def order(row: tuple[str, str, str]) -> tuple:
        # Deadline first. Under the degraded stand-in (a pythontk sibling that
        # predates ``Deprecation``: ``_load_version_key``, which says so on
        # stderr) every row takes the except branch and sorts by NAME instead --
        # accepted, not fixed (decided 2026-09-19): it cannot fire today, since a
        # dated deprecation needs ``remove_in=`` and only ``Deprecation.symbol``
        # (from the very module whose absence degrades) takes one, measured as
        # byte-identical output both ways; a second, sort-only parser is the drift
        # ``_load_version_key`` refuses; and post-release every CI clone of
        # pythontk@dev carries the module, so the branch is dead outside a stale
        # local checkout.
        try:
            return (0, _version_key(row[2]), row[1])
        except ValueError:
            # No removal version recorded (a bare marker, or the stdlib's).
            # Sorted last: it cannot expire, which is itself worth seeing.
            return (1, (0, 0, 0), row[1])

    return sorted(found, key=order)


def expired_deprecations(pkg: PackageData, version: str) -> list[tuple[str, str, str]]:
    """Retired symbols whose removal release *version* has already reached.

    An empty *version*, or a symbol with no ``remove_in``, can never expire --
    both are reported by :func:`deprecations` instead, where they read as debt
    rather than as a passing gate.
    """
    return _expired(deprecations(pkg), version)


def _expired(rows, version: str) -> list[tuple[str, str, str]]:
    """The ``(relpath, what, remove_in)`` *rows* whose ``remove_in`` *version*
    has reached; nothing when *version* (or a row's ``remove_in``) is absent or
    unparseable -- see :func:`_load_version_key` for why that stays quiet."""
    if not version:
        return []
    try:
        current = _version_key(version)
    except ValueError:
        return []
    out = []
    for row in rows:
        if not row[2]:
            continue
        try:
            if current >= _version_key(row[2]):
                out.append(row)
        except ValueError:
            continue
    return out


#: The ``Deprecation`` calls that retire something smaller than a symbol -- a
#: keyword, a value, a code path, a moved module attribute.  The registry never
#: marks a symbol for them (:data:`_DEPRECATION_DECORATORS` says why), but their
#: ``remove_in`` is the same one-release promise, so the expiry gate reads them
#: too: blendertk's ``smart_bake=`` keyword (``remove_in="0.7.0"``) shipped in
#: 0.8.0 because nothing did.
_RETIREMENT_CALLS = ("parameter", "values", "warn", "attributes")


def _string_constants(tree: ast.AST) -> dict[str, str | None]:
    """``{name: value}`` for every ``NAME = "literal"`` assignment in *tree*,
    at module or class scope -- the shared ``_REMOVE_IN = "0.19.0"`` a module
    hands each of its retirements.  A name bound to two DIFFERENT strings maps
    to ``None``: which one a call means is not readable statically."""
    found: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                prior = found.get(target.id, value.value)
                found[target.id] = value.value if prior == value.value else None
    return found


def _merge_string_constants(
    dst: dict[str, str | None], src: dict[str, str | None]
) -> None:
    """Fold *src* into *dst* under :func:`_string_constants`' own rule: a name
    the two bind to DIFFERENT strings becomes ``None`` (unreadable), so merging
    a module's constants with those of the modules it takes private bases from
    can never resolve a ``remove_in`` to a version its own file never said."""
    for name, value in src.items():
        if name in dst and dst[name] != value:
            dst[name] = None
        else:
            dst.setdefault(name, value)


def _string_value(node: ast.AST, constants: dict[str, str | None]) -> str:
    """The string *node* stands for: a literal, or a name / attribute
    (``_REMOVE_IN``, ``cls._REMOVE_IN``, ``Owner._REMOVE_IN``) bound to one in
    the same module (:func:`_string_constants`); ``""`` when unreadable."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.Name):
        return constants.get(node.id) or ""
    if isinstance(node, ast.Attribute):
        return constants.get(node.attr) or ""
    return ""


def retired_forms(pkg_dir: Path, name: str) -> list[tuple[str, str, str]]:
    """Every sub-symbol retirement in the package source, as ``(relpath, what,
    remove_in)``: a ``Deprecation.<parameter|values|warn|attributes>(...)`` call
    with a literal ``remove_in`` anywhere in a module -- a decorator, a helper
    that builds one, a module-scope ``values`` resolver -- read statically, like
    the symbol walk, so an unimported module is covered too."""
    source_root = pkg_dir / name
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    unreadable: list[str] = []
    for path in _iter_py_files(source_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        relpath = path.relative_to(source_root).as_posix()
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _RETIREMENT_CALLS
            ):
                continue
            owner = _decorator_path(node.func.value)
            if owner != "Deprecation" and not owner.endswith(".Deprecation"):
                continue
            given = next((kw.value for kw in node.keywords if kw.arg == "remove_in"), None)
            if given is None:
                continue
            what = ast.unparse(node.args[0]) if node.args else ""
            remove_in = _string_value(given, constants)
            if not remove_in:
                # A `remove_in` this walk cannot read (a helper's result, a
                # name bound to two different strings) cannot expire here: say
                # so, as the missing-__version__ case does, rather than let the
                # retirement ship past its window.
                unreadable.append(f"{relpath}: Deprecation.{node.func.attr}({what[:60]})")
                continue
            row = (relpath, f"Deprecation.{node.func.attr}({what[:60]})", remove_in)
            # One row per distinct retirement: two of the same shape in one
            # module (mayatk's and blendertk's importers each retire `shots`
            # twice) would print the same overdue line twice.
            if row not in seen:
                seen.add(row)
                out.append(row)
    if unreadable:
        print(
            f"warning: {name} has {len(unreadable)} retirement(s) whose remove_in is "
            "not a literal -- their one-release window is UNCHECKED: "
            + "; ".join(unreadable),
            file=sys.stderr,
        )
    return out


ECOSYSTEM_PACKAGES = (
    "pythontk",
    "uitk",
    "mayatk",
    "blendertk",
    "tentacle",
    "unitytk",
    "extapps",
)

SKIP_DIR_NAMES = {
    "build",
    "dist",
    "test",
    "tests",
    "docs",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
}

SUMMARY_MAX = 100

# Class-name prefixes for auto-generated code that should not appear in the
# registry (Qt Designer generates these from .ui files; they are not part of
# any hand-written API).
GENERATED_CLASS_PREFIXES = ("Ui_",)


# ---------- AST extraction ----------------------------------------------------


@dataclass
class ClassEntry:
    name: str
    summary: str
    line: int
    bases: list[str] = field(default_factory=list)
    members: list[SymbolRecord] = field(default_factory=list)
    # A retired CLASS is the shape `ptk.Git` and unitytk's `SceneBuilder` take,
    # and the walk recorded it as live because only methods were ever read for
    # a deprecation marker.
    deprecated: bool = False
    remove_in: str = ""


@dataclass
class ModuleEntry:
    relpath: str  # POSIX-style relative path inside the package source root
    summary: str
    functions: list[SymbolRecord] = field(default_factory=list)
    classes: list[ClassEntry] = field(default_factory=list)
    # Public module-level ALL_CAPS. They are importable public API and their
    # removal is a breaking change, but the walk collected only classes and
    # functions, so dropping `cli.DEFAULT_HOST` / `DEFAULT_USER` read as a
    # purely ADDITIVE release and skipped the alias-plus-minor-bump rule.
    constants: list[SymbolRecord] = field(default_factory=list)


@dataclass
class PackageData:
    # Deliberately no generation timestamp: git history is the clock. A date
    # baked into the output made the JSON sidecar and API_CHANGES.md differ on
    # the first run of every UTC day with NO change to the public surface, and
    # every consumer of that diff (the registry bot, `git status`, receipts)
    # treated it as real churn.
    name: str
    source_root: str  # POSIX relpath from monorepo root
    modules: list[ModuleEntry] = field(default_factory=list)


def _first_sentence(docstring: str | None) -> str:
    if not docstring:
        return ""
    text = docstring.strip().replace("\r\n", "\n")
    # First non-empty line, then trim at first sentence terminator that is
    # plausibly mid-line punctuation.
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        # Cut at first '. ' if it looks like end-of-sentence; otherwise keep.
        for marker in (". ", "; "):
            idx = line.find(marker)
            if idx > 0:
                line = line[: idx + 1]
                break
        if len(line) > SUMMARY_MAX:
            line = line[: SUMMARY_MAX - 1].rstrip() + "…"
        return line
    return ""


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args

    def render(a: ast.arg, default: ast.expr | None = None) -> str:
        text = a.arg
        if a.annotation is not None:
            text += f": {ast.unparse(a.annotation)}"
        if default is not None:
            rendered = ast.unparse(default)
            text += f" = {rendered}" if a.annotation else f"={rendered}"
        return text

    parts: list[str] = []

    posonly = list(args.posonlyargs)
    regular = list(args.args)
    defaults = list(args.defaults)
    # Defaults align to the END of posonly + regular.
    total_pos = posonly + regular
    pad = [None] * (len(total_pos) - len(defaults)) + defaults
    rendered_pos = [render(a, d) for a, d in zip(total_pos, pad)]
    if posonly:
        parts.extend(rendered_pos[: len(posonly)])
        parts.append("/")
        parts.extend(rendered_pos[len(posonly) :])
    else:
        parts.extend(rendered_pos)

    if args.vararg:
        parts.append("*" + render(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")

    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(render(a, d))

    if args.kwarg:
        parts.append("**" + render(args.kwarg))

    sig = "(" + ", ".join(parts) + ")"
    if node.returns is not None:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


#: Decorator spellings that retire a WHOLE symbol. ``Deprecation.parameter`` is
#: deliberately absent: it retires one keyword of a function that stays, and
#: marking its owner DEPRECATED would make the registry claim a live method is
#: going away -- the same false positive the Removed/Moved split exists to
#: avoid. PEP 702's spellings are listed so a symbol retired with the stdlib
#: decorator (3.13+) reads the same as one retired with ``pythontk``'s.
_DEPRECATION_DECORATORS = (
    "deprecated",
    "Deprecation.symbol",
    "warnings.deprecated",
    "typing_extensions.deprecated",
)


def _decorator_path(dec: ast.expr) -> str:
    """Dotted source spelling of a decorator, e.g. ``ptk.Deprecation.symbol``.

    The previous reader took only ``dec.id`` / ``dec.attr``, so it saw
    ``symbol`` for ``@Deprecation.symbol(...)`` and could not tell it from any
    other one-word attribute decorator. Every deprecation in this ecosystem is
    written through a class namespace (the encapsulation rule leaves no other
    spelling), so the dotted form is the only one that can be matched at all.
    """
    if isinstance(dec, ast.Call):
        dec = dec.func
    parts: list[str] = []
    while isinstance(dec, ast.Attribute):
        parts.append(dec.attr)
        dec = dec.value
    if isinstance(dec, ast.Name):
        parts.append(dec.id)
    return ".".join(reversed(parts))


def _deprecation_of(
    decorators: list, constants: dict[str, str | None] | None = None
) -> tuple[bool, str]:
    """``(deprecated, remove_in)`` read off a decorator list.

    ``remove_in`` is a keyword on the decorator call, so it survives the static
    walk -- which is the point: the runtime roster only sees modules something
    imported, while this sees every decorated symbol in the package and is
    therefore what the expiry gate can be built on.

    *constants* (:func:`_string_constants` for the defining module and any
    module it takes private bases from) resolves the DRY spelling a module with
    many retirements uses -- ``_REMOVE_IN = "0.18.0"`` once, then
    ``remove_in=_REMOVE_IN`` / ``cls._REMOVE_IN`` on each.  Reading only a
    literal recorded ``""`` for all of them, and a symbol with no ``remove_in``
    can never expire (:func:`expired_deprecations`), so mayatk's ``FbxUtils``
    and ``DataNodes`` retirements were invisible to the gate.  A name bound to
    two different strings stays unreadable rather than resolving to a guess.
    """
    for dec in decorators:
        path = _decorator_path(dec)
        if not any(
            path == name or path.endswith(f".{name}")
            for name in _DEPRECATION_DECORATORS
        ):
            continue
        remove_in = ""
        if isinstance(dec, ast.Call):
            for keyword in dec.keywords:
                if keyword.arg == "remove_in":
                    remove_in = _string_value(keyword.value, constants or {})
        return True, remove_in
    return False, ""


def _decorator_kinds(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    constants: dict[str, str | None] | None = None,
) -> tuple[str, bool, str]:
    """Return (kind, deprecated, remove_in). kind is method/staticmethod/classmethod/property."""
    kind = "method"
    for dec in node.decorator_list:
        name = (
            dec.id
            if isinstance(dec, ast.Name)
            else dec.attr
            if isinstance(dec, ast.Attribute)
            else (
                dec.func.id
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name)
                else ""
            )
        )
        if name == "staticmethod":
            kind = "staticmethod"
        elif name == "classmethod":
            kind = "classmethod"
        elif name == "property":
            kind = "property"
    deprecated, remove_in = _deprecation_of(node.decorator_list, constants)
    return kind, deprecated, remove_in


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _is_property_accessor(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True for a property setter/deleter (``@x.setter`` / ``@x.deleter``).

    These re-define an existing property (already emitted by its ``@property``
    getter); recording them as separate members double-lists every writable
    property and mislabels the setter as a plain ``method`` (``.setter`` is not a
    kind ``_decorator_kinds`` recognises)."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter"):
            return True
    return False


def _own_members(
    node: ast.ClassDef, owner: str, constants: dict[str, str | None] | None = None
) -> list[SymbolRecord]:
    """Public methods declared directly in *node*'s body."""
    out: list[SymbolRecord] = []
    for member in node.body:
        if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_public(member.name) or _is_property_accessor(member):
            continue
        kind, deprecated, remove_in = _decorator_kinds(member, constants)
        out.append(
            SymbolRecord(
                name=member.name,
                qualname=f"{owner}.{member.name}",
                kind=kind,
                signature=_format_signature(member),
                summary=_first_sentence(ast.get_docstring(member)),
                line=member.lineno,
                deprecated=deprecated,
                remove_in=remove_in,
            )
        )
    return out


def _class_members(
    node: ast.ClassDef,
    owner: str,
    local_classes: dict[str, ast.ClassDef],
    _seen: set[str] | None = None,
    _visited: set[str] | None = None,
    constants: dict[str, str | None] | None = None,
) -> list[SymbolRecord]:
    """Public members of *node*, including those inherited from PRIVATE bases
    declared in the same module or imported from a sibling module of the
    same package (:func:`_imported_private_classes`).

    Without this the registry silently omits a large slice of the real public
    surface: the repo's convention puts capability groups on private mixins
    (``Matrices(_MatrixMath, …)``, ``TaskManager(_TaskChecksMixin, …)``,
    ``PackageManager(_PackageManagerHelperMixin, …)``), and a private class is
    never emitted on its own.  ``mtk.Matrices.inverse`` and
    ``ptk.PackageManager.install`` were both unfindable in ``API_INDEX.md``,
    which defeats the "grep the registry before writing a helper" rule.

    Only *private* bases are resolved -- declared alongside, or imported
    from a private module of the same package (the scene exporters' phase
    mixins, ``class TaskManager(TaskFactory, _SceneTasksMixin, ...)`` with
    each mixin in its own ``_task_*.py``; without that hop the 2026-09-13
    split read as 44 removed methods).  A public base is already documented
    under its own entry, so pulling its members up would duplicate rather
    than reveal; a base from another package can't be resolved from this
    tree (``verify_runtime_surface.py`` is the gate for that).
    Bases are walked left-to-right, depth-first, first definition winning —
    Python's MRO for the single-inheritance-per-capability shape used here.

    ``_visited`` guards the walk against a base graph that loops.  Python
    itself could never run ``class _A(_A)`` or a mutual pair, but this walker
    parses whatever is on disk — including half-written files, which is why
    ``_walk_module`` already swallows ``SyntaxError`` — and an uncaught
    ``RecursionError`` there would take down the whole registry build (and the
    CI gate) over one bad file.  It also collapses a diamond so shared private
    bases are traversed once.
    """
    seen = set() if _seen is None else _seen
    visited = set() if _visited is None else _visited
    visited.add(node.name)

    out: list[SymbolRecord] = []
    for rec in _own_members(node, owner, constants):
        if rec.name not in seen:
            seen.add(rec.name)
            out.append(rec)
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else None
        if name is None or _is_public(name) or name not in local_classes:
            continue
        if name in visited:
            continue
        out.extend(
            _class_members(
                local_classes[name], owner, local_classes, seen, visited, constants
            )
        )
    return out


_PARSED: dict[Path, ast.Module | None] = {}


def _parse_cached(path: Path) -> ast.Module | None:
    """*path*'s AST, parsed once per run; None when unreadable or unparseable."""
    if path not in _PARSED:
        try:
            _PARSED[path] = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            _PARSED[path] = None
    return _PARSED[path]


def _import_target(
    node: ast.ImportFrom, path: Path, pkg_source_root: Path
) -> Path | None:
    """The ``.py`` file an ``ImportFrom`` names, when it is a module of the
    package being walked (absolute ``pkg.a.b`` or relative ``.b``); else None."""
    parts = (node.module or "").split(".") if node.module else []
    if node.level:
        base = path.parent
        for _ in range(node.level - 1):
            base = base.parent
    else:
        if not parts or parts[0] != pkg_source_root.name:
            return None
        base, parts = pkg_source_root, parts[1:]
    if not parts:
        return None
    target = base.joinpath(*parts).with_suffix(".py")
    return target if target.is_file() else None


def _imported_private_classes(
    tree: ast.Module,
    path: Path,
    pkg_source_root: Path,
    _visiting: set[Path] | None = None,
    _constants: dict[str, str | None] | None = None,
) -> dict[str, ast.ClassDef]:
    """Private classes *tree* imports from sibling modules of its own package,
    keyed by the name they are bound to here.

    What lets a public class resolve the members it inherits from a private
    mixin declared in ANOTHER file (see :func:`_class_members`).  Transitive
    -- a mixin's own imported private bases come along, so a chain
    ``TaskManager -> _SceneTasksMixin -> _TaskDataMixin`` across three files
    resolves -- same-package only, and an unreadable target simply stays
    unresolved.  ``_visiting`` is the import PATH down to *path*, not every
    module seen so far: only a module already on it is a cycle to break.  A
    module reached by two routes (two mixins importing their bases from one
    module, a diamond) is walked on each, so neither route loses its bases;
    :func:`_parse_cached` still parses it once.

    ``_constants``, when given, collects the :func:`_string_constants` of every
    module walked, so a retirement inherited from a base in another file can
    resolve the ``_REMOVE_IN`` that file declares (:func:`_deprecation_of`).
    """
    visiting = {path} if _visiting is None else _visiting
    found: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        wanted = {
            (alias.asname or alias.name): alias.name
            for alias in node.names
            if not _is_public(alias.name)
        }
        if not wanted:
            continue
        target = _import_target(node, path, pkg_source_root)
        if target is None or target in visiting:
            continue
        module = _parse_cached(target)
        if module is None:
            continue
        classes = {n.name: n for n in module.body if isinstance(n, ast.ClassDef)}
        adopted = {b: classes[s] for b, s in wanted.items() if s in classes}
        # Only a module that actually CONTRIBUTES a base lends its constants:
        # folding in every module merely imported from would let an unrelated
        # ``_REMOVE_IN`` collide with this one's and read as ambiguous, costing
        # a deadline the source states plainly.
        if adopted and _constants is not None:
            _merge_string_constants(_constants, _string_constants(module))
        # The target's own imported private bases first, so its classes'
        # bases resolve too; its own definitions then win over those.
        transitive = _imported_private_classes(
            module, target, pkg_source_root, visiting | {target}, _constants
        )
        found.update(adopted)
        for name, cls in transitive.items():
            found.setdefault(name, cls)
    return found


def _walk_module(path: Path, pkg_source_root: Path) -> ModuleEntry | None:
    """Parse one .py file. Return None if it has no public surface."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    summary = _first_sentence(ast.get_docstring(tree))
    relpath = path.relative_to(pkg_source_root).as_posix()

    funcs: list[SymbolRecord] = []
    classes: list[ClassEntry] = []
    constants: list[SymbolRecord] = []

    # Every class in the module -- plus the private ones it imports from
    # sibling modules -- so a public class can resolve members it inherits
    # from a private base declared alongside it or in its own file.
    # The string constants a retirement's ``remove_in=`` may name, from this
    # module and from every module it takes a private base from -- a base's
    # ``_REMOVE_IN`` lives in ITS file, and resolving it against the importer's
    # would print a version the source never said. A name the merged view binds
    # to two different strings collapses to unreadable (``_string_constants``),
    # so an ambiguity reports no deadline rather than the wrong one.
    string_constants: dict[str, str | None] = {}
    local_classes = _imported_private_classes(
        tree, path, pkg_source_root, _constants=string_constants
    )
    local_classes.update({n.name: n for n in tree.body if isinstance(n, ast.ClassDef)})
    _merge_string_constants(string_constants, _string_constants(tree))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name):
                continue
            deprecated, remove_in = _deprecation_of(node.decorator_list, string_constants)
            funcs.append(
                SymbolRecord(
                    name=node.name,
                    qualname=node.name,
                    kind="function",
                    signature=_format_signature(node),
                    summary=_first_sentence(ast.get_docstring(node)),
                    line=node.lineno,
                    deprecated=deprecated,
                    remove_in=remove_in,
                )
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Only ALL_CAPS names: a module-level lowercase binding is a
            # runtime detail (a logger, a compiled regex, a singleton), and
            # recording those would bury the constants that ARE contract.
            targets = (
                [t for t in node.targets if isinstance(t, ast.Name)]
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node.target, ast.Name)
                else []
            )
            for target in targets:
                if not target.id.isupper() or not _is_public(target.id):
                    continue
                constants.append(
                    SymbolRecord(
                        name=target.id,
                        qualname=target.id,
                        kind="constant",
                        signature="",
                        summary="",
                        line=node.lineno,
                    )
                )
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name):
                continue
            if any(node.name.startswith(p) for p in GENERATED_CLASS_PREFIXES):
                continue
            members = _class_members(
                node, node.name, local_classes, constants=string_constants
            )
            bases = [
                ast.unparse(b) if not isinstance(b, ast.Name) else b.id
                for b in node.bases
            ]
            cls_deprecated, cls_remove_in = _deprecation_of(
                node.decorator_list, string_constants
            )
            classes.append(
                ClassEntry(
                    name=node.name,
                    summary=_first_sentence(ast.get_docstring(node)),
                    line=node.lineno,
                    bases=bases,
                    members=members,
                    deprecated=cls_deprecated,
                    remove_in=cls_remove_in,
                )
            )

    if not funcs and not classes and not constants:
        return None
    return ModuleEntry(
        relpath=relpath,
        summary=summary,
        functions=funcs,
        classes=classes,
        constants=constants,
    )


def _iter_py_files(root: Path) -> Iterable[Path]:
    # Sort by the posix string, not the Path object: WindowsPath compares
    # case-insensitively while PosixPath (CI/Linux) compares case-sensitively, so
    # sorting Path objects ordered the modules differently on Windows vs CI and
    # made the generated registries drift between local and CI runs (e.g.
    # table_actions.py vs tableWidget.py). as_posix() is case-sensitive on every
    # platform and equals CI's existing order, so this is deterministic + churn-free.
    for path in sorted(root.rglob("*.py"), key=lambda p: p.as_posix()):
        parts = set(path.relative_to(root).parts[:-1])
        if parts & SKIP_DIR_NAMES:
            continue
        # Skip __init__.py only if it has nothing — handled by _walk_module
        # returning None. Skip __main__.py outright.
        if path.name == "__main__.py":
            continue
        yield path


def walk_package(pkg_dir: Path, repo_root: Path = REPO_ROOT) -> PackageData:
    """Walk <repo>/<pkg>/<pkg>/ and collect public API."""
    name = pkg_dir.name
    source_root = pkg_dir / name
    if not source_root.is_dir():
        raise FileNotFoundError(
            f"Expected package source root at {source_root}, not found."
        )

    modules: list[ModuleEntry] = []
    for path in _iter_py_files(source_root):
        entry = _walk_module(path, source_root)
        if entry is not None:
            modules.append(entry)

    return PackageData(
        name=name,
        source_root=source_root.relative_to(repo_root).as_posix(),
        modules=modules,
    )


# ---------- Markdown emission -------------------------------------------------


def _deprecated_tag(symbol) -> str:
    """The ``**DEPRECATED (remove in X.Y.Z)**`` decoration, or an empty string.

    Shared by the three places that render one so the removal version cannot
    show up in the member rows and be missing from the module-level function
    and class headers, which is how a reviewer ends up trusting a registry that
    marks only some of the retirements it knows about.
    """
    if not getattr(symbol, "deprecated", False):
        return ""
    remove_in = getattr(symbol, "remove_in", "")
    return (
        f" **DEPRECATED (remove in {remove_in})**" if remove_in else " **DEPRECATED**"
    )


def _src_link(pkg: PackageData, relpath: str, line: int) -> str:
    return f"{pkg.source_root}/{relpath}#L{line}"


def _anchor_for(relpath: str) -> str:
    """Build a safe markdown anchor id for a module path."""
    out = relpath.replace("/", "--").replace(".py", "")
    # Strip characters that confuse markdown anchor / URL fragment parsing.
    return "".join(ch for ch in out if ch.isalnum() or ch in "-_")


def emit_registry_markdown(pkg: PackageData) -> str:
    lines: list[str] = []
    lines.append(f"# {pkg.name} — API Registry")
    lines.append("")
    lines.append(
        "_Auto-generated. Do not edit by hand. Refresh via "
        "`m3trik/scripts/generate_api_registry.py`._"
    )
    lines.append("")
    lines.append("## Index")
    lines.append("")
    for mod in pkg.modules:
        anchor = _anchor_for(mod.relpath)
        summary = f" — {mod.summary}" if mod.summary else ""
        lines.append(f"- [`{mod.relpath}`](#{anchor}){summary}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for mod in pkg.modules:
        anchor = _anchor_for(mod.relpath)
        lines.append(f'<a id="{anchor}"></a>')
        lines.append(f"### `{mod.relpath}`")
        if mod.summary:
            lines.append("")
            lines.append(mod.summary)
        lines.append("")
        for fn in mod.functions:
            link = _src_link(pkg, mod.relpath, fn.line)
            dep = _deprecated_tag(fn)
            summary = f" — {fn.summary}" if fn.summary else ""
            lines.append(f"- [`{fn.qualname}{fn.signature}`]({link}){dep}{summary}")
        for const in mod.constants:
            link = _src_link(pkg, mod.relpath, const.line)
            lines.append(f"- [`{const.name}`]({link}) — constant")
        for cls in mod.classes:
            link = _src_link(pkg, mod.relpath, cls.line)
            base = f"({', '.join(cls.bases)})" if cls.bases else ""
            summary = f" — {cls.summary}" if cls.summary else ""
            lines.append(
                f"- **[`class {cls.name}{base}`]({link})**"
                f"{_deprecated_tag(cls)}{summary}"
            )
            for member in cls.members:
                lines.append(member.to_registry_row())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def emit_symbol_index(pkg: PackageData) -> str:
    """Compact, grep-able symbol index — the FIRST-read entrypoint for the
    'check the registry before writing a helper' rule.

    One section per module; top-level functions carry full signatures, classes
    list their base(s) + public method NAMES (no per-method signatures, no
    docstrings, no source links). This strips the prose and bodies that make
    API_REGISTRY.md hundreds of KB, so an agent can grep this for a symbol name
    to learn it exists and where, then slice API_REGISTRY.md for full detail.
    """
    lines: list[str] = [
        f"# {pkg.name} — API Index",
        "",
        "_Auto-generated. Do not edit by hand. Compact symbol index — grep this "
        "for a name; for full signatures/docs, slice "
        "[API_REGISTRY.md](API_REGISTRY.md) (never Read it whole)._",
        "",
    ]
    for mod in pkg.modules:
        header = f"### `{mod.relpath}`"
        if mod.summary:
            header += f" — {mod.summary}"
        lines.append(header)
        for fn in mod.functions:
            dep = _deprecated_tag(fn)
            lines.append(f"- `{fn.name}{fn.signature}`{dep}")
        if mod.constants:
            lines.append(f"- constants: {', '.join(c.name for c in mod.constants)}")
        for cls in mod.classes:
            base = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"- `class {cls.name}{base}`")
            if cls.members:
                names = ", ".join(m.name for m in cls.members)
                lines.append(f"  - methods: {names}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _package_data_from_json(d: dict) -> PackageData:
    """Reconstruct a PackageData from a committed API_REGISTRY.json sidecar.

    Used to supplement the cross-package shadow report with packages that were
    not walked in a partial/single-package run, so the report stays complete.
    """
    modules: list[ModuleEntry] = []
    for m in d.get("modules", []):
        funcs = [SymbolRecord(**f) for f in m.get("functions", [])]
        consts = [SymbolRecord(**c) for c in m.get("constants", [])]
        classes = []
        for c in m.get("classes", []):
            members = [SymbolRecord(**mem) for mem in c.get("members", [])]
            classes.append(
                ClassEntry(
                    name=c["name"],
                    summary=c.get("summary", ""),
                    line=c.get("line", 0),
                    bases=c.get("bases", []),
                    members=members,
                    deprecated=c.get("deprecated", False),
                    remove_in=c.get("remove_in", ""),
                )
            )
        modules.append(
            ModuleEntry(
                relpath=m["relpath"],
                summary=m.get("summary", ""),
                functions=funcs,
                classes=classes,
                constants=consts,
            )
        )
    return PackageData(
        name=d["name"],
        source_root=d.get("source_root", d["name"]),
        modules=modules,
    )


# ---------- Diff against prior JSON ------------------------------------------

BASELINE_REF = "origin/main"


def _git_output(pkg_dir: Path, *args: str) -> str | None:
    """stdout of ``git -C <pkg_dir> <args>``, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(pkg_dir), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _baseline_registry_json(pkg_dir: Path) -> tuple[dict | None, str]:
    """Resolve the API_CHANGES diff baseline: the JSON sidecar as of the last
    release (``origin/main``), falling back to the working-tree sidecar.

    The baseline must NOT be the working-tree JSON this run is about to
    rewrite: every regeneration advanced it, so a second run in the same
    session (or a subset run, or a release-time conflict resolution) diffed
    against the first run's own output and reported "no changes" — silently
    erasing the recorded delta. ``origin/main`` only advances when a release
    merges dev, so anchoring there makes regeneration idempotent and gives
    the diff a stable meaning: public API changes since the last release —
    where "last release" means the last release reflected in this checkout's
    LOCAL ``origin/main``. This function does not fetch, so a stale
    remote-tracking ref (no recent ``git fetch``) silently understates the
    delta rather than erroring.
    """
    baseline_resolves = (
        _git_output(pkg_dir, "rev-parse", "--verify", "-q", BASELINE_REF) is not None
    )
    prefix = _git_output(pkg_dir, "rev-parse", "--show-prefix")
    if prefix is not None:
        rel = f"{prefix.strip()}API_REGISTRY.json"
        content = _git_output(pkg_dir, "show", f"{BASELINE_REF}:{rel}")
        if content is not None:
            try:
                prior = json.loads(content)
            except json.JSONDecodeError:
                prior = None
            if prior is not None:
                sha = (
                    _git_output(pkg_dir, "rev-parse", "--short", BASELINE_REF) or ""
                ).strip()
                return prior, f"the last release ({BASELINE_REF} @ {sha or 'unknown'})"
    path = pkg_dir / "API_REGISTRY.json"
    if path.exists():
        try:
            if baseline_resolves:
                reason = (
                    f"the last refresh (working tree; {BASELINE_REF} resolves "
                    "but holds no valid sidecar)"
                )
            else:
                reason = f"the last refresh (working tree; {BASELINE_REF} unresolvable)"
            return (
                json.loads(path.read_text(encoding="utf-8")),
                reason,
            )
        except json.JSONDecodeError:
            pass
    return None, "none"


def _flatten_signatures(pkg: PackageData) -> dict[str, str]:
    """{module:qualname: signature} for all public callables."""
    out: dict[str, str] = {}
    for mod in pkg.modules:
        prefix = mod.relpath
        for fn in mod.functions:
            out[f"{prefix}::{fn.qualname}"] = fn.signature
        for const in mod.constants:
            out[f"{prefix}::{const.name}"] = "(constant)"
        for cls in mod.classes:
            out[f"{prefix}::{cls.name}"] = "(class)"
            for member in cls.members:
                out[f"{prefix}::{member.qualname}"] = member.signature
    return out


def _class_index(
    entries: "Iterable[tuple[str, str, list[str], set[str]]]",
    foreign: dict[str, set[str]] | None = None,
) -> tuple[dict[tuple[str, str], set[str]], dict[str, list[tuple[str, str]]]]:
    """What each class STILL resolves, keyed by the module that defines it.

    The registry records a member at its DEFINING class, so hoisting a method
    onto a base reads as a removal from the subclass even though the subclass
    still resolves it. Measured three times -- 4 entries on `blendertk`
    (2026-09-01), 9 on `mayatk` (2026-09-08) -- and the damage is not the noise
    itself: the repo's own rule turns a removal into alias-plus-minor-bump
    work, so a false positive either buys a deprecation cycle nobody owed or
    teaches reviewers that the Removed section is noise, which is exactly how a
    REAL removal gets waved through.

    Ownership is keyed by ``(module, class name)``, never by bare name: each
    DCC package carries five classes called `Parameters` (one per bridge) and
    paired `Installer` / `OpRegistry` / `RpcPlugin` / `MainThreadMarshaller`
    across two RPC plugin trees, so merging namesakes would let a deletion from
    one bridge be excused by another -- reintroducing the same waved-through
    removal from the other direction.

    Bases must still match on simple name, because that is all the registry
    records for them. A base in the SAME module wins; then a name unique
    package-wide; then ``foreign``, for bases that live in a sibling ecosystem
    package (`ptk.SequenceExporter`). An ambiguous base, or one nothing can
    resolve, is left alone so its members stay reported as removed rather than
    being silently forgiven.

    Parameters:
        entries: ``(module relpath, class name, base names, member names)``.
        foreign: ``{class name: members it resolves}`` from sibling packages.

    Returns:
        ``({(module, class): {member names it resolves}}, {class name: [keys]})``.
    """
    foreign = foreign or {}
    own: dict[tuple[str, str], set[str]] = {}
    bases: dict[tuple[str, str], list[str]] = {}
    by_name: dict[str, list[tuple[str, str]]] = {}
    for relpath, name, base_names, members in entries:
        key = (relpath, name)
        own.setdefault(key, set()).update(members)
        bases.setdefault(key, []).extend(b.split(".")[-1] for b in base_names)
        by_name.setdefault(name, []).append(key)

    def walk(key: tuple[str, str], seen: set) -> set[str]:
        if key in seen:  # a cycle in recorded bases must not hang the diff
            return set()
        seen.add(key)
        out = set(own.get(key, ()))
        relpath = key[0]
        for base in bases.get(key, ()):
            if (relpath, base) in own:
                target = (relpath, base)  # a sibling in the same module wins
            else:
                candidates = by_name.get(base, ())
                target = candidates[0] if len(candidates) == 1 else None
            if target is not None:
                out |= walk(target, seen)
            else:
                out |= foreign.get(base, set())
        return out

    return {key: walk(key, set()) for key in own}, by_name


def _pkg_class_entries(
    pkg: PackageData,
) -> "Iterable[tuple[str, str, list[str], set[str]]]":
    """`_class_index` entries for a walked package."""
    for mod in pkg.modules:
        for cls in mod.classes:
            yield (
                mod.relpath,
                cls.name,
                list(cls.bases or []),
                {m.qualname.split(".")[-1] for m in cls.members},
            )


def _json_class_entries(
    data: dict,
) -> "Iterable[tuple[str, str, list[str], set[str]]]":
    """`_class_index` entries for a registry sidecar read off disk."""
    for mod in data.get("modules", []):
        for cls in mod.get("classes", []):
            yield (
                mod["relpath"],
                cls["name"],
                list(cls.get("bases") or []),
                {m["qualname"].split(".")[-1] for m in cls.get("members", [])},
            )


def sibling_class_members(
    exclude: str,
    repo_root: Path = REPO_ROOT,
    packages: tuple = ECOSYSTEM_PACKAGES,
) -> dict[str, set[str]]:
    """``{class name: members it resolves}`` for the OTHER ecosystem packages.

    A base can live one layer down the chain -- `mayatk.PlayblastExporter`
    derives from `ptk.SequenceExporter` -- and that is the shape of the largest
    measured false-removal batch, so resolving only within the package leaves
    it unfixed. Read from the committed sidecars rather than re-walking: they
    are the same source the diff itself compares against, and it keeps this
    cheap enough to run per package.

    A name carried by more than one sibling with differing members is DROPPED,
    not merged. Nothing resolving is the safe direction: the member stays in
    Removed, where a human sees it.
    """
    seen: dict[str, set[str]] = {}
    ambiguous: set[str] = set()
    for name in packages:
        if name == exclude:
            continue
        path = repo_root / name / "API_REGISTRY.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # no readable sidecar: its bases simply stay unresolved
        resolved, _ = _class_index(_json_class_entries(data))
        for (_, cls_name), members in resolved.items():
            if cls_name in seen and seen[cls_name] != members:
                ambiguous.add(cls_name)
            seen.setdefault(cls_name, set()).update(members)
    for name in ambiguous:
        seen.pop(name, None)
    return seen


def module_reexports(
    source_root: Path, relpaths: "Iterable[str]"
) -> dict[str, set[str]]:
    """``{module relpath: names it imports}`` for the given modules.

    A hoisted class is usually re-exported from its old home so the import path
    consumers hold keeps working -- `playblast_exporter.py` does exactly this
    for `CaptureResult`, `ExportResult` and `ExportTarget`. The registry walks
    definitions, not imports, so without this the re-export is invisible and a
    still-importable name reads as removed.

    Only the modules that actually lost a symbol are parsed, so this costs a
    handful of files rather than the whole tree.
    """
    out: dict[str, set[str]] = {}
    for relpath in relpaths:
        path = source_root / relpath
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update(a.asname or a.name.split(".")[0] for a in node.names)
        if names:
            out[relpath] = names
    return out


def _relpaths_losing_symbols(pkg: PackageData, prior_json: dict | None) -> set[str]:
    """Modules whose recorded symbols shrank -- the only ones worth reparsing."""
    if not prior_json:
        return set()
    live = _flatten_signatures(pkg)
    return {
        key.split("::", 1)[0]
        for key in (
            set(_flatten_signatures(_package_data_from_json(prior_json))) - set(live)
        )
    }


def _deprecation_section(pkg: PackageData, version: str) -> list[str]:
    """The retirement-debt section: everything deprecated, earliest deadline first.

    It rides in API_CHANGES.md because that is the file a reviewer reads before
    a release, and a deadline nobody reads is the failure this exists to end.
    The hard stop is separate (``--check`` exits non-zero on an EXPIRED row);
    this is what shows the deadline coming BEFORE the release that trips it.
    """
    rows = deprecations(pkg)
    if not rows:
        return []
    expired = {
        (relpath, qualname)
        for relpath, qualname, _ in expired_deprecations(pkg, version)
    }
    lines = [f"## Deprecations ({len(rows)})", ""]
    lines.append(
        "_Live retirement debt, earliest deadline first. An **EXPIRED** row has "
        "outlived its one-release window: delete the alias and its tests rather "
        "than moving the date._"
    )
    lines.append("")
    for relpath, qualname, remove_in in rows:
        mark = "**EXPIRED** " if (relpath, qualname) in expired else ""
        due = (
            f"remove in {remove_in}" if remove_in else "**no removal version recorded**"
        )
        lines.append(f"- {mark}`{relpath}::{qualname}` — {due}")
    lines.append("")
    return lines


#: Directory names whose modules are exec PAYLOAD, not an import contract. A
#: template is read as source and run inside ANOTHER application (Blender,
#: Marmoset, Substance Painter), so nothing imports its names and renaming one
#: breaks no consumer -- the root CLAUDE.md exempts "exec-templates" from the
#: encapsulation rule for the same reason. Every ``templates/`` directory in
#: the ecosystem is of this kind (the two bridge template sets, both marmoset
#: sets, both substance sets, extapps' marmoset workflow). They stay IN the
#: registry, which documents them; they simply never owe a version bump.
SEMVER_EXEMPT_DIRS = ("templates",)


def _is_semver_exempt(key: str) -> bool:
    """Whether ``relpath::symbol`` lives under a :data:`SEMVER_EXEMPT_DIRS` dir."""
    relpath = key.split("::", 1)[0]
    return any(part in SEMVER_EXEMPT_DIRS for part in relpath.split("/")[:-1])


@dataclass(frozen=True)
class ApiDelta:
    """One package's public-API delta against a prior registry sidecar.

    The DATA behind ``API_CHANGES.md``. Rendering it is one consumer
    (:func:`emit_changes_markdown`); deciding what version it owes is another
    (:func:`required_bump`), which is why the computation stopped living
    inside the renderer: the release tool needs the verdict, and re-parsing
    generated prose to recover it would be a second, drifting source of truth.
    """

    added: list[str]
    removed: list[str]
    changed: list[str]
    moved: list[str]
    #: Flat ``relpath::symbol -> signature`` maps, kept so a renderer can show
    #: what a symbol WAS as well as what it is.
    prior: dict[str, str]
    new: dict[str, str]

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.moved)


def required_bump(delta: ApiDelta | None) -> tuple[str, list[str]]:
    """``(bump, reasons)`` -- the smallest release this delta may ship as.

    ``"minor"`` when the delta REMOVES a public symbol, naming each removal;
    ``"patch"`` otherwise. The rule is the root CLAUDE.md's ("public APIs are
    contracts (break -> ``ptk.Deprecation`` alias + real ``remove_in`` +
    ``CHANGELOG.md`` line + minor bump)"), which until now nothing enforced --
    the cascade stepped a patch from PyPI whatever the delta said, so a removal
    could ship under a floor that resolves it as a bugfix.

    Only ``removed`` counts. A ``moved`` symbol still resolves at the same call
    site, and a ``changed`` signature is ambiguous on its face -- dropping a
    parameter breaks, adding an optional one does not -- so neither is read as
    a break here; a genuine signature break is the author's call to declare by
    hand-raising ``__version__``. Symbols under :data:`SEMVER_EXEMPT_DIRS` are
    not contract and are skipped.
    """
    if delta is None:
        return "patch", []
    reasons = [k for k in delta.removed if not _is_semver_exempt(k)]
    return ("minor" if reasons else "patch"), reasons


def compute_api_delta(
    pkg: PackageData,
    prior_json: dict | None,
    foreign_members: dict[str, set[str]] | None = None,
    reexports: dict[str, set[str]] | None = None,
) -> ApiDelta | None:
    """The public-API delta of *pkg* against *prior_json*, or None when there
    is no baseline to diff against.

    Parameters:
        foreign_members: ``{class name: members it resolves}`` for bases that
            live in a sibling ecosystem package (`sibling_class_members`).
        reexports: ``{module relpath: names it imports}``, so a class hoisted
            elsewhere and re-exported from its old home is not read as removed
            (`module_reexports`). Both are passed IN rather than read off disk
            so that diffing a synthetic package cannot reach the real tree.
    """
    if prior_json is None:
        return None
    new = _flatten_signatures(pkg)

    # Reconstruct a flat map from prior JSON (which mirrors PackageData shape).
    prior: dict[str, str] = {}
    for mod in prior_json.get("modules", []):
        prefix = mod["relpath"]
        for fn in mod.get("functions", []):
            prior[f"{prefix}::{fn['qualname']}"] = fn["signature"]
        for const in mod.get("constants", []):
            prior[f"{prefix}::{const['name']}"] = "(constant)"
        for cls in mod.get("classes", []):
            prior[f"{prefix}::{cls['name']}"] = "(class)"
            for member in cls.get("members", []):
                prior[f"{prefix}::{member['qualname']}"] = member["signature"]

    added = sorted(set(new) - set(prior))
    removed = sorted(set(prior) - set(new))
    if not any("constants" in m for m in prior_json.get("modules", [])):
        # This baseline predates constant tracking, so every constant in the
        # package would read as new: 653 of them across the seven packages,
        # burying that release's real changes under an upgrade artefact. The
        # test suppresses only ADDITIONS and only on this one diff -- the next
        # baseline records the field, and removals are never suppressed.
        added = [k for k in added if new[k] != "(constant)"]
    changed = sorted(k for k in set(new) & set(prior) if new[k] != prior[k])

    # A symbol that MOVED is not a symbol that went away. Split the removals:
    # a member the class still resolves through a base, or a class that turns
    # up ADDED in another module, is reported as moved instead. Anything
    # unresolved stays in Removed, so a real removal still fires the
    # alias-plus-minor-bump rule (:func:`required_bump`).
    foreign_members = foreign_members or {}
    reexports = reexports or {}
    resolved, by_name = _class_index(_pkg_class_entries(pkg), foreign_members)
    # A class only counts as moved if it actually appeared somewhere new. Its
    # name merely surviving proves nothing -- five bridges ship a `Parameters`.
    reappeared = {key.split("::", 1)[1] for key in added if new.get(key) == "(class)"}
    moved: list[str] = []
    still_removed: list[str] = []
    for key in removed:
        relpath, symbol = key.split("::", 1)
        parts = symbol.split(".")
        if len(parts) >= 2:
            owner, member = parts[-2], parts[-1]
            names = resolved.get((relpath, owner))
            if names is None and owner in reexports.get(relpath, ()):
                # The owner moved out but the module still imports it, so the
                # old path resolves; ask the package that now defines it.
                names = foreign_members.get(owner)
            if names is None:
                # The class left this module too; follow it only when its name
                # is unambiguous package-wide.
                candidates = by_name.get(owner, ())
                names = resolved[candidates[0]] if len(candidates) == 1 else set()
            gone = member not in names
        else:
            # A module-level class that turned up elsewhere in the package, or
            # that this very module still re-exports. A module-level FUNCTION
            # is never forgiven -- its import path really did change.
            gone = not (
                prior.get(key) == "(class)"
                and (symbol in reappeared or symbol in reexports.get(relpath, ()))
            )
        (still_removed if gone else moved).append(key)

    return ApiDelta(
        added=added,
        removed=still_removed,
        changed=changed,
        moved=moved,
        prior=prior,
        new=new,
    )


def emit_changes_markdown(
    pkg: PackageData,
    prior_json: dict | None,
    baseline_label: str = "prior baseline",
    foreign_members: dict[str, set[str]] | None = None,
    reexports: dict[str, set[str]] | None = None,
    version: str = "",
) -> str:
    """Render :func:`compute_api_delta`'s result as ``API_CHANGES.md``."""
    delta = compute_api_delta(pkg, prior_json, foreign_members, reexports)
    if delta is None:
        # No baseline to diff against, but the retirement debt is a
        # property of THIS tree, not of the delta -- a package whose first
        # registry generation is also the release that retires something
        # would otherwise report none of it.
        head = [
            f"# {pkg.name} — API Changes",
            "",
            "_Initial registry. No prior baseline — diff will appear on next "
            "regeneration._",
        ]
        debt = _deprecation_section(pkg, version)
        if debt:
            head.extend(["", *debt])
        return "\n".join(head).rstrip() + "\n"

    added, removed = delta.added, delta.removed
    changed, moved = delta.changed, delta.moved
    prior, new = delta.prior, delta.new

    lines = [f"# {pkg.name} — API Changes", ""]
    lines.append(f"_Diff vs {baseline_label}._")
    lines.append("")
    # Built before the early return: retirement debt is reported whether or not
    # this release changed anything else, which is the point -- an alias runs
    # out of time during a release that touched nothing near it.
    deprecation_lines = _deprecation_section(pkg, version)
    if delta.is_empty():
        lines.append(f"No public API changes since {baseline_label}.")
        if deprecation_lines:
            lines.append("")
            lines.extend(deprecation_lines)
        return "\n".join(lines) + "\n"

    if removed:
        lines.append(f"## Removed ({len(removed)})")
        lines.append("")
        for key in removed:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}` — was `{prior[key]}`")
        lines.append("")
    if added:
        lines.append(f"## Added ({len(added)})")
        lines.append("")
        for key in added:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}{new[key]}`")
        lines.append("")
    lines.extend(deprecation_lines)
    if moved:
        lines.append(f"## Moved ({len(moved)})")
        lines.append("")
        lines.append(
            "_Still resolvable at the same call site -- hoisted to a base class "
            "or re-exported from another module. NOT a removal: no alias or "
            "minor bump is owed._"
        )
        lines.append("")
        for key in moved:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}`")
        lines.append("")
    if changed:
        lines.append(f"## Signature changed ({len(changed)})")
        lines.append("")
        for key in changed:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}`")
            lines.append(f"  - was: `{prior[key]}`")
            lines.append(f"  - now: `{new[key]}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------- Cross-package shadow detection -----------------------------------


def emit_shadow_report(packages: list[PackageData]) -> str:
    """Find simple-name collisions across packages — DRY review surface.

    Only top-level functions and classes are tracked. Methods are scoped to
    their class, so repeating `apply` / `as_dict` / `b000` (slot convention)
    across different classes is not a meaningful collision.

    Collisions whose ONLY two packages are {mayatk, blendertk} are the
    deliberate port mirror (blendertk mirrors mayatk's public names to keep the
    tentacle slots branch-free) and are bucketed separately so they don't drown
    the genuine cross-layer duplications (anything touching pythontk, or
    spanning 3+ packages).
    """
    from collections import defaultdict

    occurrences: dict[str, list[tuple[str, str, str, int]]] = defaultdict(list)
    # name -> [(pkg, module, qualname, line), ...]

    for pkg in packages:
        for mod in pkg.modules:
            for fn in mod.functions:
                occurrences[fn.name].append(
                    (pkg.name, mod.relpath, fn.qualname, fn.line)
                )
            for cls in mod.classes:
                occurrences[cls.name].append(
                    (pkg.name, mod.relpath, cls.name, cls.line)
                )

    cross_pkg = {
        name: occ
        for name, occ in occurrences.items()
        if len({entry[0] for entry in occ}) > 1
    }

    def _is_parity(occ: list[tuple[str, str, str, int]]) -> bool:
        return {entry[0] for entry in occ} == {"mayatk", "blendertk"}

    genuine = {n: o for n, o in cross_pkg.items() if not _is_parity(o)}
    parity = {n: o for n, o in cross_pkg.items() if _is_parity(o)}

    lines = [
        "# API Shadows — Cross-Package Name Collisions",
        "",
        "_Symbols whose simple name is defined in more than one ecosystem "
        "package. Review for DRY violations: a downstream wrapper that just "
        "re-exposes upstream behavior should be deleted; if it adds value, "
        "name it differently or document why._",
        "",
    ]
    if not cross_pkg:
        lines.append("No cross-package name collisions detected.")
        return "\n".join(lines) + "\n"

    lines.append(f"## Genuine cross-layer collisions ({len(genuine)})")
    lines.append("")
    lines.append(
        "_Touch `pythontk` or span 3+ packages — the real DRY review surface._"
    )
    lines.append("")
    if genuine:
        for name in sorted(genuine):
            occs = genuine[name]
            pkgs = ", ".join(sorted({e[0] for e in occs}))
            lines.append(f"### `{name}` — {pkgs}")
            lines.append("")
            for pkg_name, relpath, qualname, line in occs:
                lines.append(
                    f"- `{pkg_name}` — [`{qualname}`]({pkg_name}/{relpath}#L{line})"
                )
            lines.append("")
    else:
        lines.append("_None._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"## Intentional mayatk↔blendertk port parity ({len(parity)})")
    lines.append("")
    lines.append(
        "_blendertk deliberately mirrors mayatk's public names (branch-free "
        "tentacle slots). Expected — not DRY violations. Names only:_"
    )
    lines.append("")
    for name in sorted(parity):
        lines.append(f"- `{name}`")
    return "\n".join(lines).rstrip() + "\n"


# ---------- Driver ------------------------------------------------------------


def _prune_empty_remove_in(node):
    """Drop ``remove_in``/``deprecated`` keys that carry no information.

    ``asdict`` would write ``"remove_in": ""`` against every symbol in the
    ecosystem -- tens of thousands of lines of committed machine file saying
    nothing, and a one-time diff big enough to bury the surface change it
    shipped with. Absent reads back as the dataclass default, so the sidecar
    grows only where a retirement was actually recorded. ``deprecated`` is
    pruned on CLASSES only: it is new there, whereas every symbol row has
    carried it since the sidecar was first written and dropping it now would
    churn exactly what this avoids.
    """
    if isinstance(node, dict):
        if not node.get("remove_in", None):
            node.pop("remove_in", None)
        if "members" in node and not node.get("deprecated", False):
            node.pop("deprecated", None)
        for value in node.values():
            _prune_empty_remove_in(value)
    elif isinstance(node, list):
        for value in node:
            _prune_empty_remove_in(value)
    return node


def _to_jsonable(pkg: PackageData) -> dict:
    return _prune_empty_remove_in(asdict(pkg))


class StalenessGate:
    """Content-hash staleness comparison behind ``--check`` (the CI gate).

    The gate answers one question: *does the committed registry still describe
    the package's current public surface?* It compares a SHA-256 of the
    normalized committed text against the same hash of a fresh generation —
    never an mtime, which is meaningless in a fresh CI checkout and flapped
    locally on a cloud-synced drive.

    The gated per-package artifacts (:attr:`GATED_FILES`) are the two hand-read
    docs: ``API_INDEX.md`` and ``API_REGISTRY.md``. Deliberately NOT gated:

    * ``API_REGISTRY.json`` — the machine sidecar records a ``line`` for every
      member, so inserting one import at the top of a module rewrites hundreds
      of numbers while the public surface is untouched. Gating it made
      ``--check`` a line-shift tripwire that went red on commits it had nothing
      to say about.
    * ``API_CHANGES.md`` — a generation-time diff narrative against the last
      release; it legitimately differs from a re-diff against a moved baseline.
    * ``m3trik/docs/API_SHADOWS.md`` — cross-package by construction, so it can
      only be validated when every ecosystem package was walked in one run (see
      :meth:`covers_ecosystem`). A per-package CI checkout has no siblings.

    :meth:`normalize` additionally drops three cosmetics that are not public API:

    * a legacy ``_Generated: <date>_`` stamp — the generator no longer writes
      one, but registries committed before 2026-08-23 still carry it;
    * BLANK LINES — the old generator wrote that stamp BETWEEN two blanks, so
      filtering the stamp line alone left a committed file one line longer than
      anything written now (measured in a clean worktree: pythontk's
      ``API_INDEX.md`` normalized to 549 lines against a generated 548). Both
      filters are needed together, or every package's "API registry up to date"
      check goes red at once with no source change behind it;
    * the ``#L<line>`` fragment of source deep-links (a class that moved down
      three lines is the same class).

    Everything that IS surface — module set and order, names, bases,
    signatures, kinds, summaries — still fails the gate. Normalization applies
    to the COMPARISON only; the written artifacts keep their blank lines and
    real line numbers.
    """

    GATED_FILES = ("API_INDEX.md", "API_REGISTRY.md")

    _DATE_LINE_PREFIX = "_Generated:"
    _SRC_LINE_FRAGMENT = re.compile(r"#L\d+")

    @classmethod
    def normalize(cls, text: str | None) -> str | None:
        """Strip the non-surface cosmetics (see the class docstring)."""
        if text is None:
            return None
        kept = "\n".join(
            ln
            for ln in text.splitlines()
            # Blank lines are pure layout, never public API -- and dropping them
            # is what lets a registry written by the pre-2026-08-23 generator
            # (which emitted `_Generated: <date>_` between two blanks) compare
            # equal to one written now. Filtering only the date LINE left the old
            # file one blank line longer, so every committed registry read stale
            # the moment the date was removed from the generator: `API registry
            # up to date` would have gone red on every package PR at once.
            if ln.strip() and not ln.startswith(cls._DATE_LINE_PREFIX)
        )
        return cls._SRC_LINE_FRAGMENT.sub("#L", kept)

    @classmethod
    def digest(cls, text: str | None) -> str | None:
        """SHA-256 of the normalized text; ``None`` for a missing artifact."""
        normalized = cls.normalize(text)
        if normalized is None:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def is_stale(cls, existing: str | None, generated: str) -> bool:
        """True when the committed text no longer matches a fresh generation."""
        return cls.digest(existing) != cls.digest(generated)

    @staticmethod
    def covers_ecosystem(walked: Iterable[str]) -> bool:
        """True when a run walked every package the shadow report spans."""
        return set(walked) >= set(ECOSYSTEM_PACKAGES)


def regenerate(
    package_names: list[str],
    repo_root: Path = REPO_ROOT,
    check_only: bool = False,
    shadows: bool = True,
) -> int:
    """Walk ``package_names`` and write (or, with ``check_only``, gate) their registries.

    Parameters:
        package_names: Ecosystem package directory names to walk.
        repo_root: Monorepo root holding the package dirs and ``m3trik/``.
        check_only: Compare content hashes and write nothing; exit 1 when stale.
        shadows: Also refresh ``m3trik/docs/API_SHADOWS.md``. A per-package
            release commit passes ``False`` — the shadow report is cross-package
            and lives in m3trik's tree, which a package release must not dirty.

    Returns:
        Process exit code: 0 clean, 1 stale or unwalkable.
    """
    packages: list[PackageData] = []
    stale: list[str] = []
    unwalkable: list[str] = []
    overdue: list[str] = []

    for name in package_names:
        pkg_dir = repo_root / name
        if not pkg_dir.is_dir():
            print(f"warning: skipping {name} — directory not found", file=sys.stderr)
            unwalkable.append(name)
            continue
        try:
            data = walk_package(pkg_dir, repo_root)
        except FileNotFoundError as exc:
            print(f"warning: skipping {name} — {exc}", file=sys.stderr)
            unwalkable.append(name)
            continue
        packages.append(data)

        # The one-release alias window, enforced rather than remembered: a
        # retirement that named ``remove_in`` and then shipped past it is caught
        # by comparing it against the package's own ``__version__``.
        pkg_version = package_version(pkg_dir, name)
        dated = [row for row in deprecations(data) if row[2]]
        if dated and not pkg_version:
            # A gate that passes because it compared against NOTHING is worse
            # than no gate (the same rule the unwalkable-package check exists
            # for). Without a readable __version__ nothing here can expire, so
            # say so rather than reporting a clean bill of health.
            print(
                f"warning: {name} has {len(dated)} dated deprecation(s) but no "
                f"readable __version__ in {name}/{name}/__init__.py -- the "
                "one-release window is UNCHECKED for this package",
                file=sys.stderr,
            )
        for relpath, qualname, remove_in in expired_deprecations(
            data, pkg_version
        ) + _expired(retired_forms(pkg_dir, name), pkg_version):
            overdue.append(f"{name}/{relpath}::{qualname} (was due in {remove_in})")

        targets = {
            pkg_dir / "API_INDEX.md": emit_symbol_index(data),
            pkg_dir / "API_REGISTRY.md": emit_registry_markdown(data),
        }
        if not check_only:
            # The sidecar and the changes narrative are written, never gated
            # (see StalenessGate). Building the narrative shells out to git for
            # the release baseline, so skipping it keeps ``--check`` fast and
            # independent of a shallow CI checkout's missing origin/main.
            prior, baseline_label = _baseline_registry_json(pkg_dir)
            registry_json = json.dumps(_to_jsonable(data), indent=2, ensure_ascii=False)
            targets[pkg_dir / "API_REGISTRY.json"] = registry_json + "\n"
            targets[pkg_dir / "API_CHANGES.md"] = emit_changes_markdown(
                data,
                prior,
                baseline_label,
                foreign_members=sibling_class_members(data.name, repo_root),
                reexports=module_reexports(
                    repo_root / data.source_root,
                    _relpaths_losing_symbols(data, prior),
                ),
                version=pkg_version,
            )

        for path, content in targets.items():
            existing = path.read_text(encoding="utf-8") if path.exists() else None
            if check_only:
                # GATED_FILES is the authority, not this loop's membership: a
                # later artifact added to `targets` stays ungated until it is
                # listed there deliberately.
                if path.name in StalenessGate.GATED_FILES and StalenessGate.is_stale(
                    existing, content
                ):
                    stale.append(path.relative_to(repo_root).as_posix())
                continue
            if existing != content:
                path.write_text(content, encoding="utf-8")
            else:
                # Content already current — still refresh the mtime.
                # generate_parity_audit.py's freshness guard compares the
                # JSON sidecar's mtime against package source, so a
                # source edit that doesn't change the public surface
                # (import-path sync, comment) would otherwise trip it
                # with no way to clear it by running this generator.
                os.utime(path, None)

    # Cross-package shadow report. Build the FULL ecosystem picture even on a
    # partial/single-package run: freshly walked packages plus the rest
    # reconstructed from their committed JSON sidecars. Previously this only ran
    # when every package was walked in one invocation, so the documented manual
    # single-package refresh silently left the shadow report stale.
    #
    # Under --check it is gated ONLY when this run walked the whole ecosystem: a
    # per-package CI checkout has no sibling packages on disk, so the report it
    # would compute spans one package and could never match the committed
    # cross-package one. Skipping keeps the per-package gate deterministic.
    shadow_in_scope = shadows and (
        not check_only or StalenessGate.covers_ecosystem(p.name for p in packages)
    )

    shadow_inputs: dict[str, PackageData] = {p.name: p for p in packages}
    if shadow_in_scope:
        for name in ECOSYSTEM_PACKAGES:
            if name in shadow_inputs:
                continue
            sidecar = repo_root / name / "API_REGISTRY.json"
            if sidecar.exists():
                try:
                    shadow_inputs[name] = _package_data_from_json(
                        json.loads(sidecar.read_text(encoding="utf-8"))
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    if shadow_inputs and shadow_in_scope:
        # Derived from repo_root so a test repo_root never writes into the
        # real monorepo's docs.
        docs_root = repo_root / "m3trik" / "docs"
        if not check_only:
            docs_root.mkdir(parents=True, exist_ok=True)
        shadow_path = docs_root / "API_SHADOWS.md"
        shadow_md = emit_shadow_report(
            [shadow_inputs[n] for n in sorted(shadow_inputs)]
        )
        existing = (
            shadow_path.read_text(encoding="utf-8") if shadow_path.exists() else None
        )
        if check_only:
            if StalenessGate.is_stale(existing, shadow_md):
                stale.append(shadow_path.relative_to(repo_root).as_posix())
        elif existing != shadow_md:
            shadow_path.write_text(shadow_md, encoding="utf-8")

    # A gate that passes because it walked NOTHING is worse than no gate: a typo
    # in the workflow's package name, a wrong `path:` on the checkout, or a
    # renamed source root would all read green. So a SCOPED check (the CI form,
    # which names its package) must walk everything it was asked for. The
    # full-ecosystem sweep stays tolerant: refresh-api-registry.yml clones the
    # siblings best-effort and warns on a failed clone, and a monorepo checkout
    # may legitimately lack a package.
    scoped_run = set(package_names) != set(ECOSYSTEM_PACKAGES)
    if check_only and unwalkable and (scoped_run or not packages):
        print(
            "Nothing to check for: "
            + ", ".join(unwalkable)
            + " (wrong package name, or checked out at the wrong path?)",
            file=sys.stderr,
        )
        return 1

    if overdue:
        # Printed on every run, fatal only under --check. A plain regeneration is
        # also what the registry refresh bot runs, and failing that would block
        # the very commit carrying this report; CI is where a red gate reaches a
        # person who can delete the alias.
        stream = sys.stderr if check_only else sys.stdout
        print(
            f"{len(overdue)} deprecation(s) outlived the one-release window. "
            "Delete the alias and its tests, or -- if it genuinely must stay -- "
            "raise remove_in deliberately and say why in CHANGELOG.md:",
            file=stream,
        )
        for entry in overdue:
            print(f"  expired: {entry}", file=stream)
        if check_only:
            return 1

    if check_only and stale:
        print("Stale - regenerate with:", file=sys.stderr)
        print(
            "  python m3trik/scripts/generate_api_registry.py "
            + " ".join(p.name for p in packages),
            file=sys.stderr,
        )
        for path in stale:
            print(f"  stale: {path}", file=sys.stderr)
        return 1

    if not check_only:
        total_modules = sum(len(p.modules) for p in packages)
        total_symbols = sum(
            len(m.functions)
            + len(m.constants)
            + sum(1 + len(c.members) for c in m.classes)
            for p in packages
            for m in p.modules
        )
        print(
            f"Regenerated registries for {len(packages)} package(s): "
            f"{total_modules} modules, {total_symbols} public symbols."
        )
    return 0


def semver_verdict(name: str, repo_root: Path = REPO_ROOT) -> dict:
    """``{package, bump, reasons}`` -- the smallest release *name* may ship as.

    The release tool's view of :func:`required_bump`, computed from the SAME
    walk and baseline the ``API_CHANGES.md`` narrative is built from, so the
    verdict cannot drift from the document that explains it. Emitted as JSON
    (``--semver``) rather than read out of the rendered markdown: parsing
    generated prose to recover a decision the generator already made would be
    a second source of truth, and a brittle one.

    ``bump`` is ``"patch"`` for an unwalkable package or one with no baseline
    -- neither is evidence of a break, and a gate that guessed here would
    refuse releases it cannot justify.
    """
    pkg_dir = repo_root / name
    try:
        data = walk_package(pkg_dir, repo_root)
    except (FileNotFoundError, NotADirectoryError):
        return {"package": name, "bump": "patch", "reasons": []}
    prior, _label = _baseline_registry_json(pkg_dir)
    delta = compute_api_delta(
        data,
        prior,
        foreign_members=sibling_class_members(data.name, repo_root),
        reexports=module_reexports(
            repo_root / data.source_root, _relpaths_losing_symbols(data, prior)
        ),
    )
    bump, reasons = required_bump(delta)
    return {"package": name, "bump": bump, "reasons": reasons}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        help=f"Packages to walk. Default: {', '.join(ECOSYSTEM_PACKAGES)}.",
    )
    parser.add_argument(
        "--semver",
        action="store_true",
        help=(
            "Print, as JSON, the smallest release each package may ship as "
            "('minor' when the delta removes a public symbol, else 'patch') "
            "with the removals that force it. Writes nothing."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any registry is stale; do not write.",
    )
    parser.add_argument(
        "--no-shadows",
        action="store_true",
        help=(
            "Skip m3trik/docs/API_SHADOWS.md. For a per-package release commit: "
            "the shadow report is cross-package and lives in m3trik's tree."
        ),
    )
    args = parser.parse_args(argv)

    names = list(args.packages) or list(ECOSYSTEM_PACKAGES)
    if args.semver:
        verdicts = [semver_verdict(n, REPO_ROOT) for n in names]
        print(json.dumps(verdicts, indent=2))
        return 0
    return regenerate(names, check_only=args.check, shadows=not args.no_shadows)


if __name__ == "__main__":
    sys.exit(main())
