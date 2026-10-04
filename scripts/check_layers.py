#!/usr/bin/python
# coding=utf-8
"""Hold every package to its declared layer order, and the workspace to its declared dependencies.

CODE_STANDARD section 0, Parts: a unit's parts sit in a declared order and depend
only downward. One rule, checked at two scales:

1. **Workspace.** An ecosystem package (the set ``m3trik/workspace.json`` declares)
   imports another ecosystem package only when its ``pyproject.toml`` declares it,
   as a dependency or in an optional extra. The declaration already exists; this
   is the check that it tells the truth.
2. **Package.** A package that declares ``[tool.m3trik.layers]`` in its
   ``pyproject.toml`` has its parts checked::

       [tool.m3trik.layers]
       order = [
           "file_utils/mesh_convert",          # top
           "core_utils/engines | core_utils/handoff",
           ...
           "core_utils",                       # the kernel: lowest
       ]

   A part is a package-relative path, and the longest declared prefix wins, so a
   tenant can rank above the folder it lives in. A module may import its own part
   or any part ranked below it; ``" | "`` joins peers of one rank, which may not
   import each other. Every top-level subpackage must be covered by a part.

Counted: every runtime import, deferred ones included (a function-level import is
still a dependency), except those under ``if TYPE_CHECKING:``. Imports through the
package root (``from pythontk import X``) name no part and are not counted.
Exec-templates (``templates/``) and in-app ``plugin_src/`` run inside another host
and are exempt, as ruff already treats them.

A new check starts by freezing today's violations: ``check_layers_baseline.json``
lists them, ``--check`` fails only on a violation it does not list, and reports
listed ones that no longer occur so the baseline can shrink. ``--update``
rewrites the baseline; its diff is the review.

Usage:
    python check_layers.py [--check]    # exit 1 on a new violation
    python check_layers.py --update     # freeze the current violations
"""

import argparse
import ast
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]
BASELINE = SCRIPTS / "check_layers_baseline.json"
EXEMPT_DIRS = {"templates", "plugin_src", "__pycache__"}
REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9_.\-]+")


def _sync_workspace():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import sync_workspace

    return sync_workspace


# ------------------------------------------------------------------ scanning
class _Imports(ast.NodeVisitor):
    """Collect the dotted target of every runtime import in one module."""

    def __init__(self, package_parts: List[str], exists) -> None:
        self.package_parts = package_parts
        self.exists = exists
        self.targets: List[str] = []

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        name = getattr(test, "id", None) or getattr(test, "attr", None)
        if name == "TYPE_CHECKING":
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.targets.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            keep = len(self.package_parts) - (node.level - 1)
            base = self.package_parts[: max(keep, 0)]
        else:
            base = []
        module = base + (node.module.split(".") if node.module else [])
        for alias in node.names:
            candidate = module + [alias.name]
            # ``from pkg.sub import mod`` names the module ``mod`` when it is one.
            self.targets.append(
                ".".join(candidate if self.exists(candidate) else module)
            )


def iter_modules(repo: Path, package: str) -> Iterator[Tuple[Path, List[str]]]:
    """(file, its dotted parts) for every module of *package* outside exempt dirs."""
    root = repo / package
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(repo)
        if EXEMPT_DIRS & set(rel.parts[:-1]):
            continue
        parts = list(rel.with_suffix("").parts)
        yield path, parts


#: A static ES-module import or re-export: ``import x from './a.js'`` (braces
#: may span lines), ``export { y } from '../b.js'``, ``import './c.js'``.
#: Dynamic ``import(...)`` is a runtime seam (a feature the manifest names),
#: not a dependency, and is not matched.
_JS_IMPORT = re.compile(
    r"^\s*(?:import|export)\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]"
    r"|^\s*import\s*['\"]([^'\"]+)['\"]",
    re.M,
)
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def iter_js_modules(repo: Path, package: str) -> Iterator[Path]:
    """Every ES module (``*.js``) of *package* outside exempt dirs: a web
    runtime the package serves, held to the same declared order."""
    for path in sorted((repo / package).rglob("*.js")):
        if not EXEMPT_DIRS & set(path.relative_to(repo).parts[:-1]):
            yield path


def js_imports(repo: Path, package: str, path: Path) -> List[str]:
    """Package-relative paths (posix) of the modules *path* imports by a
    relative specifier; a bare one (``'three'``) names no part of *package*."""
    text = _JS_BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8", errors="ignore"))
    root = (repo / package).resolve()
    targets = []
    for match in _JS_IMPORT.finditer(text):
        spec = match.group(1) or match.group(2)
        if not spec.startswith("."):
            continue
        target = (path.parent / spec).resolve()
        try:
            targets.append(target.relative_to(root).as_posix())
        except ValueError:
            continue  # outside the package
    return targets


def module_imports(repo: Path, path: Path, parts: List[str]) -> List[str]:
    """Dotted targets of *path*'s runtime imports (each file parsed once a run:
    both scales read the same imports)."""
    return list(_module_imports(repo, path, tuple(parts)))


@lru_cache(maxsize=None)
def _module_imports(repo: Path, path: Path, parts: Tuple[str, ...]) -> Tuple[str, ...]:
    package_parts = list(parts[:-1])  # a package's __init__ and a module share this

    def exists(candidate: List[str]) -> bool:
        target = repo.joinpath(*candidate)
        return target.with_suffix(".py").is_file() or target.is_dir()

    collector = _Imports(package_parts, exists)
    try:
        collector.visit(ast.parse(path.read_text(encoding="utf-8", errors="ignore")))
    except SyntaxError:
        return ()
    return tuple(collector.targets)


# ------------------------------------------------------------ declarations
def pyproject(repo: Path) -> dict:
    return tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))


def declared_dependencies(data: dict) -> Set[str]:
    """Distribution names in ``dependencies`` and every optional extra."""
    project = data.get("project", {})
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    names = set()
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement.strip())
        if match:
            names.add(match.group(0).split("[")[0].lower().replace("-", "_"))
    return names


def layer_order(data: dict) -> Optional[List[List[str]]]:
    """The declared ranks (top first), each a list of peer parts, or None."""
    order = data.get("tool", {}).get("m3trik", {}).get("layers", {}).get("order")
    if order is None:
        return None
    return [[part.strip() for part in tier.split("|")] for tier in order]


def expand_order(root: Path, order: List[List[str]]) -> List[List[str]]:
    """*order* with every ``"<folder>/*"`` part made one part per child of
    that folder -- each file (named without its suffix) or subfolder -- all
    peers of the wildcard's rank. A plug-in folder declares its parts once:
    a new child is a new peer with no edit to the declaration."""
    expanded = []
    for tier in order:
        parts = []
        for part in tier:
            if not part.endswith("/*"):
                parts.append(part)
                continue
            folder = part[:-2]
            children = (
                sorted(
                    (
                        child.relative_to(root).with_suffix("")
                        if child.is_file()
                        else child.relative_to(root)
                    ).as_posix()
                    for child in (root / folder).iterdir()
                    if child.name not in EXEMPT_DIRS
                    and not child.name.startswith((".", "_"))
                )
                if (root / folder).is_dir()
                else []
            )
            parts.extend(children)
        expanded.append(parts)
    return expanded


def part_of(relative: str, parts: Sequence[str]) -> Optional[str]:
    """The longest declared part that *relative* (package-relative posix) is in."""
    best = None
    for part in parts:
        if relative == part or relative.startswith(part + "/"):
            if best is None or len(part) > len(best):
                best = part
    return best


# ------------------------------------------------------------------ checks
def chain_violations(repo: Path, package: str, ecosystem: Sequence[str]) -> Set[str]:
    """Imports of an ecosystem package that *package*'s pyproject does not declare."""
    allowed = declared_dependencies(pyproject(repo)) | {package}
    found = set()
    for path, parts in iter_modules(repo, package):
        for target in module_imports(repo, path, parts):
            head = target.split(".")[0]
            if head in ecosystem and head not in allowed:
                found.add(f"{_rel(repo, package, path)} -> {target}")
    return found


def order_problems(repo: Path, package: str, order: List[List[str]]) -> List[str]:
    """What is wrong with the declaration itself (not the code)."""
    problems = []
    flat = [part for tier in order for part in tier]
    dupes = sorted({p for p in flat if flat.count(p) > 1})
    if dupes:
        problems.append(f"parts declared twice: {dupes}")
    root = repo / package
    for part in flat:
        target = root / (part[:-2] if part.endswith("/*") else part)
        if not (target.is_dir() or target.with_suffix(".py").is_file()):
            problems.append(f"declared part {part!r} does not exist")
    for child in sorted(root.iterdir()):
        if (
            child.is_dir()
            and child.name not in EXEMPT_DIRS
            and any(child.rglob("*.py"))
        ):
            if part_of(child.name, flat) is None:
                problems.append(f"subpackage {child.name!r} is in no declared part")
    return problems


def layer_violations(repo: Path, package: str, order: List[List[str]]) -> Set[str]:
    """Imports that point up the declared order, or across peers of one rank --
    a Python module's, and an ES module's (``*.js``) by its relative imports."""
    order = expand_order(repo / package, order)
    rank = {part: index for index, tier in enumerate(order) for part in tier}
    parts = list(rank)
    found = set()

    def check(path: Path, dest_path: str, target: str) -> None:
        source = part_of(_rel(repo, package, path, suffix=False), parts)
        dest = part_of(dest_path, parts)
        if source is None or dest is None or dest == source:
            return
        if rank[dest] <= rank[source]:
            found.add(f"{_rel(repo, package, path)} -> {target}")

    for path, dotted in iter_modules(repo, package):
        for target in module_imports(repo, path, dotted):
            pieces = target.split(".")
            if pieces[0] == package and len(pieces) >= 2:
                check(path, "/".join(pieces[1:]), target)
    for path in iter_js_modules(repo, package):
        for target in js_imports(repo, package, path):
            check(path, str(Path(target).with_suffix("").as_posix()), target)
    return found


def _rel(repo: Path, package: str, path: Path, suffix: bool = True) -> str:
    rel = path.relative_to(repo / package)
    if not suffix:
        rel = rel.with_suffix("")
        if rel.name == "__init__":
            rel = rel.parent
    return rel.as_posix()


def scan(workspace: Path = WORKSPACE) -> Tuple[Dict[str, List[str]], List[str]]:
    """({package: sorted violations}, [declaration problems]) over the registry set."""
    ecosystem = _sync_workspace().ecosystem_packages()
    violations: Dict[str, List[str]] = {}
    problems: List[str] = []
    for package in ecosystem:
        repo = workspace / package
        if not (repo / "pyproject.toml").is_file():
            continue  # partial checkout
        found = chain_violations(repo, package, ecosystem)
        order = layer_order(pyproject(repo))
        if order is not None:
            problems += [
                f"{package}: {p}" for p in order_problems(repo, package, order)
            ]
            found |= layer_violations(repo, package, order)
        violations[package] = sorted(found)
    return violations, problems


# -------------------------------------------------------------------- CLI
def load_baseline(path: Path = BASELINE) -> Dict[str, List[str]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def write_baseline(violations: Dict[str, List[str]], path: Path = BASELINE) -> None:
    data = {
        "_doc": (
            "Violations frozen when check_layers.py started holding the line "
            "(CODE_STANDARD section 0, Parts). Shrink it; never grow it without "
            "a reason in the commit. Rewrite: check_layers.py --update."
        )
    }
    data.update({k: v for k, v in sorted(violations.items()) if v})
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="the default")
    mode.add_argument(
        "--update", action="store_true", help="freeze the current violations"
    )
    args = parser.parse_args(argv)

    violations, problems = scan()
    for problem in problems:
        print(f"[FAIL] declaration: {problem}")
    if args.update:
        write_baseline(violations)
        total = sum(len(v) for v in violations.values())
        print(f"[WROTE] {BASELINE.name}: {total} frozen violation(s)")
        return 1 if problems else 0

    baseline = load_baseline()
    new_total = 0
    for package, found in violations.items():
        frozen = set(baseline.get(package, []))
        new = [v for v in found if v not in frozen]
        paid = sorted(frozen - set(found))
        for violation in new:
            print(f"[FAIL] {package}: {violation}")
        for violation in paid:
            print(f"[PAID] {package}: {violation} no longer occurs (--update)")
        new_total += len(new)
        print(
            f"[{'FAIL' if new else 'OK'}] {package}: {len(new)} new, "
            f"{len(found) - len(new)} frozen"
        )
    return 1 if new_total or problems else 0


if __name__ == "__main__":
    sys.exit(main())
