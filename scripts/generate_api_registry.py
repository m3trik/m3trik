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
from datetime import datetime, timezone
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


@dataclass
class ModuleEntry:
    relpath: str  # POSIX-style relative path inside the package source root
    summary: str
    functions: list[SymbolRecord] = field(default_factory=list)
    classes: list[ClassEntry] = field(default_factory=list)


@dataclass
class PackageData:
    name: str
    source_root: str  # POSIX relpath from monorepo root
    generated_at: str
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


def _decorator_kinds(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, bool]:
    """Return (kind, deprecated). kind is method/staticmethod/classmethod/property."""
    kind = "method"
    deprecated = False
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
        elif name == "deprecated":
            deprecated = True
    return kind, deprecated


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


def _own_members(node: ast.ClassDef, owner: str) -> list[SymbolRecord]:
    """Public methods declared directly in *node*'s body."""
    out: list[SymbolRecord] = []
    for member in node.body:
        if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_public(member.name) or _is_property_accessor(member):
            continue
        kind, deprecated = _decorator_kinds(member)
        out.append(
            SymbolRecord(
                name=member.name,
                qualname=f"{owner}.{member.name}",
                kind=kind,
                signature=_format_signature(member),
                summary=_first_sentence(ast.get_docstring(member)),
                line=member.lineno,
                deprecated=deprecated,
            )
        )
    return out


def _class_members(
    node: ast.ClassDef,
    owner: str,
    local_classes: dict[str, ast.ClassDef],
    _seen: set[str] | None = None,
    _visited: set[str] | None = None,
) -> list[SymbolRecord]:
    """Public members of *node*, including those inherited from PRIVATE bases
    declared in the same module.

    Without this the registry silently omits a large slice of the real public
    surface: the repo's convention puts capability groups on private mixins
    (``Matrices(_MatrixMath, …)``, ``TaskManager(_TaskChecksMixin, …)``,
    ``PackageManager(_PackageManagerHelperMixin, …)``), and a private class is
    never emitted on its own.  ``mtk.Matrices.inverse`` and
    ``ptk.PackageManager.install`` were both unfindable in ``API_INDEX.md``,
    which defeats the "grep the registry before writing a helper" rule.

    Only *private*, *same-module* bases are resolved.  A public base is
    already documented under its own entry, so pulling its members up would
    duplicate rather than reveal; a cross-module base can't be resolved from
    one file's AST (``verify_runtime_surface.py`` is the gate for that).
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
    for rec in _own_members(node, owner):
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
            _class_members(local_classes[name], owner, local_classes, seen, visited)
        )
    return out


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

    # Every class in the module, so a public class can resolve members it
    # inherits from a private base declared alongside it.
    local_classes = {
        n.name: n for n in tree.body if isinstance(n, ast.ClassDef)
    }

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name):
                continue
            kind, deprecated = "function", False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "deprecated":
                    deprecated = True
            funcs.append(
                SymbolRecord(
                    name=node.name,
                    qualname=node.name,
                    kind=kind,
                    signature=_format_signature(node),
                    summary=_first_sentence(ast.get_docstring(node)),
                    line=node.lineno,
                    deprecated=deprecated,
                )
            )
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name):
                continue
            if any(node.name.startswith(p) for p in GENERATED_CLASS_PREFIXES):
                continue
            members = _class_members(node, node.name, local_classes)
            bases = [
                ast.unparse(b) if not isinstance(b, ast.Name) else b.id
                for b in node.bases
            ]
            classes.append(
                ClassEntry(
                    name=node.name,
                    summary=_first_sentence(ast.get_docstring(node)),
                    line=node.lineno,
                    bases=bases,
                    members=members,
                )
            )

    if not funcs and not classes:
        return None
    return ModuleEntry(relpath=relpath, summary=summary, functions=funcs, classes=classes)


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
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        modules=modules,
    )


# ---------- Markdown emission -------------------------------------------------


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
    lines.append(f"_Generated: {pkg.generated_at}_")
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
            dep = " **DEPRECATED**" if fn.deprecated else ""
            summary = f" — {fn.summary}" if fn.summary else ""
            lines.append(f"- [`{fn.qualname}{fn.signature}`]({link}){dep}{summary}")
        for cls in mod.classes:
            link = _src_link(pkg, mod.relpath, cls.line)
            base = f"({', '.join(cls.bases)})" if cls.bases else ""
            summary = f" — {cls.summary}" if cls.summary else ""
            lines.append(f"- **[`class {cls.name}{base}`]({link})**{summary}")
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
        f"_Generated: {pkg.generated_at}_",
        "",
    ]
    for mod in pkg.modules:
        header = f"### `{mod.relpath}`"
        if mod.summary:
            header += f" — {mod.summary}"
        lines.append(header)
        for fn in mod.functions:
            dep = " **DEPRECATED**" if fn.deprecated else ""
            lines.append(f"- `{fn.name}{fn.signature}`{dep}")
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
                )
            )
        modules.append(
            ModuleEntry(
                relpath=m["relpath"],
                summary=m.get("summary", ""),
                functions=funcs,
                classes=classes,
            )
        )
    return PackageData(
        name=d["name"],
        source_root=d.get("source_root", d["name"]),
        generated_at=d.get("generated_at", ""),
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
                    _git_output(pkg_dir, "rev-parse", "--short", BASELINE_REF)
                    or ""
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
                reason = (
                    f"the last refresh (working tree; {BASELINE_REF} unresolvable)"
                )
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
        for cls in mod.classes:
            out[f"{prefix}::{cls.name}"] = "(class)"
            for member in cls.members:
                out[f"{prefix}::{member.qualname}"] = member.signature
    return out


def emit_changes_markdown(
    pkg: PackageData,
    prior_json: dict | None,
    baseline_label: str = "prior baseline",
) -> str:
    new = _flatten_signatures(pkg)
    if prior_json is None:
        return (
            f"# {pkg.name} — API Changes\n\n"
            f"_Initial registry generated {pkg.generated_at}. "
            "No prior baseline — diff will appear on next regeneration._\n"
        )

    # Reconstruct a flat map from prior JSON (which mirrors PackageData shape).
    prior: dict[str, str] = {}
    for mod in prior_json.get("modules", []):
        prefix = mod["relpath"]
        for fn in mod.get("functions", []):
            prior[f"{prefix}::{fn['qualname']}"] = fn["signature"]
        for cls in mod.get("classes", []):
            prior[f"{prefix}::{cls['name']}"] = "(class)"
            for member in cls.get("members", []):
                prior[f"{prefix}::{member['qualname']}"] = member["signature"]

    added = sorted(set(new) - set(prior))
    removed = sorted(set(prior) - set(new))
    changed = sorted(k for k in set(new) & set(prior) if new[k] != prior[k])

    lines = [f"# {pkg.name} — API Changes", ""]
    lines.append(
        f"_Diff vs {baseline_label}. Generated {pkg.generated_at}._"
    )
    lines.append("")
    if not (added or removed or changed):
        lines.append(f"No public API changes since {baseline_label}.")
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
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}_",
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


def _to_jsonable(pkg: PackageData) -> dict:
    return asdict(pkg)


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

    :meth:`normalize` additionally drops the two cosmetics that are not public
    API: the ``_Generated: <date>_`` stamp (a new day is not a change) and the
    ``#L<line>`` fragment of source deep-links (a class that moved down three
    lines is the same class). Everything that IS surface — module set and
    order, names, bases, signatures, kinds, summaries — still fails the gate.
    Normalization applies to the COMPARISON only; the written artifacts keep
    real dates and real line numbers.
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
            if not ln.startswith(cls._DATE_LINE_PREFIX)
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
) -> int:
    packages: list[PackageData] = []
    stale: list[str] = []
    unwalkable: list[str] = []

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
            registry_json = json.dumps(
                _to_jsonable(data), indent=2, ensure_ascii=False
            )
            targets[pkg_dir / "API_REGISTRY.json"] = registry_json + "\n"
            targets[pkg_dir / "API_CHANGES.md"] = emit_changes_markdown(
                data, prior, baseline_label
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
    shadow_in_scope = not check_only or StalenessGate.covers_ecosystem(
        p.name for p in packages
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
        existing = shadow_path.read_text(encoding="utf-8") if shadow_path.exists() else None
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
            "Nothing to check for: " + ", ".join(unwalkable)
            + " (wrong package name, or checked out at the wrong path?)",
            file=sys.stderr,
        )
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
            len(m.functions) + sum(1 + len(c.members) for c in m.classes)
            for p in packages
            for m in p.modules
        )
        print(
            f"Regenerated registries for {len(packages)} package(s): "
            f"{total_modules} modules, {total_symbols} public symbols."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        help=f"Packages to walk. Default: {', '.join(ECOSYSTEM_PACKAGES)}.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any registry is stale; do not write.",
    )
    args = parser.parse_args(argv)

    names = list(args.packages) or list(ECOSYSTEM_PACKAGES)
    return regenerate(names, check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
