#!/usr/bin/python
# coding=utf-8
"""Hold every package to its declared layer order, and the workspace to its declared dependencies and names.

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

Two more rules are strict from their first file and are never frozen (CODE_STANDARD
section 3):

3. **The product.** No other package imports a unit ``workspace.json`` marks
   ``"role": "product"`` (tentacle, extapps): a library stays usable without it.
4. **Roles.** A package that declares ``[tool.m3trik.roles]`` names import groups
   and, per path, the groups that path may not import::

       [tool.m3trik.roles.groups]
       maya = ["maya", "pymel", "mayatk"]
       [tool.m3trik.roles.forbid]
       "tools/*/model" = ["maya", "blender", "qt"]
       "tools/legacy" = []                  # exempt until it merges

   A path segment ``*`` matches any one segment and the most specific path wins;
   a group lists dotted roots (``maya`` covers ``maya.cmds``, never ``mayatk``),
   ``*`` again matching one segment. Imports through a package root name no
   module and are not counted, as in rule 2.

Counted: every runtime import, deferred ones included (a function-level import is
still a dependency), except those under ``if TYPE_CHECKING:``. Imports through the
package root (``from pythontk import X``) name no part and are not counted.
Exec-templates (``templates/``) and in-app ``plugin_src/`` run inside another host
and are exempt, as ruff already treats them.

5. **C# assemblies.** A package that ships a Unity package declares its parts in
   the same table, and each assembly definition's ``references`` are held to them::

       [tool.m3trik.layers.csharp]
       root = "com.m3trik.unitytk"   # the Unity package, repo-relative
       order = [
           "Features/*/Editor",                # top: each feature's editor half
           "Features/*/Runtime",
           ".",                                # the root folder's own assembly
           "Contracts | Kernel/Editor",        # peers of one rank
           "Core",                             # lowest
       ]
       kernel = "Kernel/Editor"                # check_csharp.py reads it

   An asmdef's part is the most specific declared folder pattern its folder lies
   in (most segments, then fewest ``*``); ``*`` is any one folder, and folders
   bound to different names by one ``*`` of a shared pattern prefix are peers at
   any rank (``Features/A/Editor`` may reference ``Features/A/Runtime``, never
   ``Features/B/Runtime``). A reference, by name or ``GUID:``, points to its own
   part or one ranked below; peers never. A reference outside the package (one
   no asmdef under ``root`` declares) is a door's alone (``autoReferenced: false``,
   compiled only when its package is present: a ``versionDefines`` define in its
   ``defineConstraints``), plus the Unity Test Framework's from a test assembly
   (``UNITY_INCLUDE_TESTS`` in its ``defineConstraints``); one to the repo's own
   assembly outside the package (the sandbox) is never allowed. Folders Unity
   skips (a ``.`` prefix, a ``~`` suffix) and build output are not read. Its
   violations name the asmdef (``<name>.asmdef -> <reference> (<rule>)``), so a
   move keeps them frozen; each rule's fix is printed with it (``CSHARP_FIXES``).

6. **Names.** Knowledge points down as imports do (CODE_STANDARD section 0,
   Parts): a package's code, tests and shipped files (its package folder,
   ``test/``, and the ``[tool.m3trik.layers.csharp]`` root) name no ecosystem
   package it does not depend on, directly or through another
   (``pyproject.toml`` dependencies and extras), save its twin
   (``workspace.json`` ``"twin"``: mayatk and blendertk). A package may also
   declare application names it never uses::

       [tool.m3trik.names]
       forbid = ["Maya", "Blender"]          # unitytk: what produces its assets

   Words are read with identifiers split at case and underscores, so
   ``MayaSurface`` and ``maya_surface`` name Maya while ``mayatk`` names only
   mayatk. History and agent maps (``CHANGELOG.md``, ``AGENTS.md``,
   ``CLAUDE.md``) name their neighbours by design and are not read; nor are
   exec-templates, ``plugin_src/``, build output or test scratch. A violation
   reads ``<repo-relative path> names <word> (names)``.

A new check starts by freezing today's violations: ``check_layers_baseline.json``
lists them, ``--check`` fails only on a violation it does not list, and reports
listed ones that no longer occur so the baseline can shrink. ``--update``
rewrites the baseline, keeping a package it could not read; its diff is the
review. A baseline describes the
workspace it was frozen from, so ``--workspace`` reads and rewrites that
workspace's own ``m3trik/scripts`` copy.

Usage:
    python check_layers.py [--check] [pkg ...]   # exit 1 on a new violation
    python check_layers.py --update              # freeze the current violations
"""

import argparse
import ast
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

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


def roles(data: dict) -> Optional[dict]:
    """The declared ``{"groups": {...}, "forbid": {...}}``, or None."""
    return data.get("tool", {}).get("m3trik", {}).get("roles")


def role_problems(declared: dict) -> List[str]:
    """What is wrong with a roles declaration itself."""
    groups = declared.get("groups", {})
    return [
        f"role {path!r} forbids unknown group {name!r}"
        for path, names in declared.get("forbid", {}).items()
        for name in names
        if name not in groups
    ]


def _segments_match(segments: Sequence[str], pattern: Sequence[str]) -> bool:
    return len(pattern) <= len(segments) and all(
        want in ("*", have) for have, want in zip(segments, pattern)
    )


def role_of(relative: str, forbid: dict) -> Optional[str]:
    """The most specific declared role path *relative* (package-relative posix,
    no suffix) falls under: most segments, then fewest wildcards."""
    segments = relative.split("/")
    matches = [
        path for path in forbid if _segments_match(segments, path.split("/"))
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: (p.count("/"), -p.count("*")))


def dotted_match(target: str, pattern: str) -> bool:
    """Whether import *target* is *pattern* or inside it, segment by segment."""
    return _segments_match(target.split("."), pattern.split("."))


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


def product_violations(repo: Path, package: str, products: Set[str]) -> Set[str]:
    """Imports of a product by any package other than that product."""
    found = set()
    for path, parts in iter_modules(repo, package):
        for target in module_imports(repo, path, parts):
            head = target.split(".")[0]
            if head in products and head != package:
                found.add(f"{_rel(repo, package, path)} -> {target}")
    return found


def role_violations(repo: Path, package: str, declared: dict) -> Set[str]:
    """Imports a module's role forbids, each named with the role that forbids it."""
    groups, forbid = declared.get("groups", {}), declared.get("forbid", {})
    found = set()
    for path, dotted in iter_modules(repo, package):
        role = role_of(_rel(repo, package, path, suffix=False), forbid)
        if role is None:
            continue
        patterns = [p for name in forbid[role] for p in groups.get(name, [])]
        for target in module_imports(repo, path, dotted):
            if any(dotted_match(target, p) for p in patterns):
                found.add(f"{_rel(repo, package, path)} -> {target} ({role})")
    return found


# ---------------------------------------------------------------------- C#
#: Folders no asmdef walk enters: build output, Unity's caches, tool state.
#: Unity's own skip rule (a ``.`` prefix, a ``~`` suffix) is applied besides.
CS_PRUNE = {
    "Library", "Temp", "Logs", "obj", "UserSettings", "Build", "Builds",
    "build", "dist", "node_modules", "__pycache__",
}
#: The Unity Test Framework's assemblies (by name, and by the GUID form Unity
#: writes) and its precompiled NUnit: a test assembly's outside references.
TEST_FRAMEWORK = {
    "UnityEngine.TestRunner",
    "UnityEditor.TestRunner",
    "GUID:27619889b8ba8c24980f49ee34dbb44a",
    "GUID:0acc523941302664db1f4e527237feb3",
    "nunit.framework.dll",
}
#: Each C# reference rule: the tag its violation ends with, and the fix it names.
CSHARP_FIXES = {
    "up the order": (
        "reference only its own part or one below: move what it needs down, or "
        "reach it through a contract"
    ),
    "a peer": (
        "peers never reference each other: share the type through a contract, "
        "never a reference"
    ),
    "outside the package": (
        "only a door references an outside package: move the use into one "
        "(autoReferenced false, a versionDefines define in its defineConstraints)"
    ),
    "the repo's own assembly": (
        "nothing in the package references the repo's other assemblies (the "
        "sandbox, a test project): move what it needs into the package"
    ),
    "the test framework outside a test assembly": (
        "a test assembly carries UNITY_INCLUDE_TESTS in its defineConstraints: "
        "add it, or drop the reference"
    ),
}


def csharp(data: dict) -> Optional[dict]:
    """The declared ``[tool.m3trik.layers.csharp]`` table, or None."""
    return data.get("tool", {}).get("m3trik", {}).get("layers", {}).get("csharp")


def _segments(folder: str) -> List[str]:
    """A root-relative posix folder (or part pattern) as segments; ``.`` and
    ``""`` are the root itself."""
    return [] if folder in ("", ".") else folder.split("/")


def unity_walk(top: Path, suffix: str, skip: Optional[Path] = None) -> Iterator[Path]:
    """Every ``*<suffix>`` file under *top* that Unity would import, sorted:
    hidden and ``~`` folders, :data:`CS_PRUNE` and *skip* are not entered."""
    found = []
    for folder, dirs, files in os.walk(top):
        here = Path(folder)
        dirs[:] = [
            d for d in dirs
            if d not in CS_PRUNE
            and not d.startswith(".")
            and not d.endswith("~")
            and not d.endswith(".egg-info")
            and (skip is None or here / d != skip)
        ]
        found += [here / f for f in files if f.endswith(suffix)]
    return iter(sorted(found))


class Asmdef:
    """One assembly definition: its file, its folder under the C# root (posix,
    ``""`` for the root), its ``.meta`` GUID and the fields the rules read."""

    def __init__(self, path: Path, folder: str, data: dict, guid: Optional[str]):
        self.path, self.folder, self.data, self.guid = path, folder, data, guid
        self.name = str(data.get("name") or path.stem)

    def _list(self, key: str) -> List[str]:
        value = self.data.get(key) or []
        return [str(v).strip() for v in value] if isinstance(value, list) else []

    @property
    def references(self) -> List[str]:
        return self._list("references")

    @property
    def precompiled(self) -> List[str]:
        return self._list("precompiledReferences")

    @property
    def is_test(self) -> bool:
        """The Unity Test Framework's shape: ``UNITY_INCLUDE_TESTS`` keeps it out
        of players (or the legacy ``optionalUnityReferences``)."""
        return "UNITY_INCLUDE_TESTS" in self._list("defineConstraints") or (
            "TestAssemblies" in self._list("optionalUnityReferences")
        )

    @property
    def is_door(self) -> bool:
        """Not auto-referenced, and compiled only when its package is present."""
        if self.data.get("autoReferenced", True) is not False:
            return False
        constraints = set(self._list("defineConstraints"))
        defines = self.data.get("versionDefines") or []
        return any(
            isinstance(d, dict) and str(d.get("define", "")).strip() in constraints
            for d in defines
        )

    @property
    def editor_only(self) -> bool:
        return self._list("includePlatforms") == ["Editor"]


def _read_asmdef(path: Path, root: Path) -> Tuple[Optional[Asmdef], Optional[str]]:
    """``(asmdef, None)``, or ``(None, problem)`` for one that does not parse."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as error:
        return None, f"{path.name} does not parse ({error}): fix its JSON"
    guid = None
    meta = path.with_name(path.name + ".meta")
    if meta.is_file():
        match = re.search(r"^guid:\s*([0-9a-fA-F]+)", meta.read_text(errors="ignore"), re.M)
        guid = match.group(1).lower() if match else None
    try:
        folder = path.parent.relative_to(root).as_posix()
    except ValueError:
        folder = path.parent.as_posix()
    return Asmdef(path, "" if folder == "." else folder, data, guid), None


class CSharpLayout:
    """A package's C# parts as ``[tool.m3trik.layers.csharp]`` declares them:
    its assemblies, the part and rank of each, and the reference rules (module
    docstring, rule 5). ``problems`` lists what is wrong with the declaration or
    an asmdef itself; check_csharp.py reads the same layout."""

    def __init__(self, repo: Path, declared: dict) -> None:
        self.repo = repo
        self.root = (repo / str(declared.get("root", "."))).resolve()
        order = declared.get("order") or []
        self.order = [[p.strip() for p in str(tier).split("|")] for tier in order]
        self.rank = {p: i for i, tier in enumerate(self.order) for p in tier}
        self.kernel = declared.get("kernel")
        self.problems: List[str] = []
        self.asmdefs: List[Asmdef] = []
        if not self.root.is_dir():
            self.problems.append(
                f"csharp root {declared.get('root')!r} is not a folder: declare "
                "the Unity package's folder, relative to pyproject.toml"
            )
            return
        for path in unity_walk(self.root, ".asmdef"):
            asmdef, problem = _read_asmdef(path, self.root)
            if problem:
                self.problems.append(problem)
            else:
                self.asmdefs.append(asmdef)
        self.problems += self._declaration_problems()

    def _declaration_problems(self) -> List[str]:
        problems = []
        flat = [p for tier in self.order for p in tier]
        if not flat:
            problems.append("csharp declares no order: list its parts, top first")
        dupes = sorted({p for p in flat if flat.count(p) > 1})
        if dupes:
            problems.append(f"C# parts declared twice: {dupes}")
        for part in flat:
            if "*" not in part and not (self.root / part).is_dir():
                problems.append(f"declared C# part {part!r} does not exist")
        if self.kernel is not None and self.kernel not in self.rank:
            problems.append(
                f"csharp kernel {self.kernel!r} is not a declared part: name one of its order"
            )
        names = [a.name for a in self.asmdefs]
        for name in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"two assemblies are named {name!r}: Unity compiles one")
        for asmdef in self.asmdefs:
            if self.part_of(asmdef.folder) is None:
                problems.append(
                    f"{self.rel(asmdef.path)} is in no declared C# part: add its "
                    "folder (or '.') to the order"
                )
        return problems

    def rel(self, path: Path) -> str:
        """*path* relative to the C# root (posix)."""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def part_of(self, folder: str) -> Optional[str]:
        """The most specific declared pattern *folder* lies in: most segments,
        then fewest wildcards."""
        segments = _segments(folder)
        # "." is the root folder alone, never a catch-all: an assembly in a
        # folder no part declares is a declaration problem, not the root's.
        matches = [
            p for p in self.rank
            if (_segments_match(segments, _segments(p)) if _segments(p) else not segments)
        ]
        if not matches:
            return None
        return max(
            matches, key=lambda p: (len(_segments(p)), -_segments(p).count("*"))
        )

    def assembly_of(self, path: Path) -> Optional[Asmdef]:
        """The asmdef a ``.cs`` file compiles into: the nearest one above it."""
        folder = _segments(self.rel(path.parent))
        best = None
        for asmdef in self.asmdefs:
            own = _segments(asmdef.folder)
            if own == folder[: len(own)] and (
                best is None or len(own) > len(_segments(best.folder))
            ):
                best = asmdef
        return best

    def at_or_below_kernel(self, asmdef: Asmdef) -> bool:
        """Whether *asmdef* is the kernel's or ranks below it."""
        part = self.part_of(asmdef.folder)
        if self.kernel not in self.rank or part is None:
            return False
        return self.rank[part] >= self.rank[self.kernel]

    def reference_rule(self, source: Asmdef, target: Asmdef) -> Optional[str]:
        """The rule a reference from *source* to *target* (both in the package)
        breaks, or None."""
        ps, pd = self.part_of(source.folder), self.part_of(target.folder)
        if ps is None or pd is None:
            return None  # a declaration problem, reported once
        fs, fd = _segments(source.folder), _segments(target.folder)
        for index, (mine, theirs) in enumerate(zip(_segments(ps), _segments(pd))):
            if mine != theirs:
                break
            if mine == "*" and fs[index] != fd[index]:
                return "a peer"
        if ps == pd or self.rank[pd] > self.rank[ps]:
            return None
        return "a peer" if self.rank[pd] == self.rank[ps] else "up the order"

    def _repo_own(self) -> Dict[str, str]:
        """``{name or GUID: name}`` of the repo's asmdefs outside the package."""
        own = {}
        for path in unity_walk(self.repo, ".asmdef", skip=self.root):
            asmdef, _ = _read_asmdef(path, self.repo)
            if asmdef is not None:
                own[asmdef.name] = asmdef.name
                if asmdef.guid:
                    own[f"GUID:{asmdef.guid}"] = asmdef.name
        return own

    def violations(self) -> Set[str]:
        """``<name>.asmdef -> <reference> (<rule>)`` for every reference a rule
        forbids (:data:`CSHARP_FIXES` names each rule's fix)."""
        known = {a.name: a for a in self.asmdefs}
        known.update({f"GUID:{a.guid}": a for a in self.asmdefs if a.guid})
        own = self._repo_own()
        found = set()
        for source in self.asmdefs:
            for ref in source.references + source.precompiled:
                key = f"GUID:{ref[5:].lower()}" if ref.startswith("GUID:") else ref
                target = known.get(key)
                if target is source:
                    continue
                if target is not None:
                    rule = self.reference_rule(source, target)
                elif key in own:
                    rule = "the repo's own assembly"
                elif source.is_door:
                    rule = None
                elif key in TEST_FRAMEWORK:
                    rule = None if source.is_test else (
                        "the test framework outside a test assembly"
                    )
                else:
                    rule = "outside the package"
                if rule:
                    label = target.name if target else own.get(key, ref)
                    found.add(f"{source.name}.asmdef -> {label} ({rule})")
        return found


def csharp_fix(violation: str) -> str:
    """The fix a C# reference violation names, or ``""`` for any other."""
    for tag, fix in CSHARP_FIXES.items():
        if violation.endswith(f"({tag})"):
            return fix
    return ""


def _rel(repo: Path, package: str, path: Path, suffix: bool = True) -> str:
    rel = path.relative_to(repo / package)
    if not suffix:
        rel = rel.with_suffix("")
        if rel.name == "__init__":
            rel = rel.parent
    return rel.as_posix()


def scan(
    workspace: Path = WORKSPACE, packages: Optional[Sequence[str]] = None
) -> Tuple[Dict[str, List[str]], List[str], Dict[str, List[str]]]:
    """({package: sorted violations}, [declaration problems], {package: sorted
    strict violations}) over the ecosystem set, or the *packages* named from it.
    Strict ones are never frozen."""
    sync = _sync_workspace()
    ecosystem = sync.ecosystem_packages()
    products = set(sync.products())
    closure = ecosystem_closure(workspace, ecosystem)
    twins = sync.twins()
    violations: Dict[str, List[str]] = {}
    strict: Dict[str, List[str]] = {}
    problems: List[str] = []
    for package in ecosystem:
        if packages and package not in packages:
            continue
        repo = workspace / package
        if not (repo / "pyproject.toml").is_file():
            continue  # partial checkout
        try:
            data = pyproject(repo)
        except tomllib.TOMLDecodeError as error:
            # A merge left markers in it, say: nothing here can be checked, and
            # the release's safety preflight names the cause.
            problems.append(f"{package}: pyproject.toml does not parse ({error})")
            continue
        found = chain_violations(repo, package, ecosystem)
        above = set(ecosystem) - closure.get(package, set()) - {package, twins.get(package)}
        found |= name_violations(repo, package, data, above | name_forbid(data))
        order = layer_order(data)
        if order is not None:
            problems += [
                f"{package}: {p}" for p in order_problems(repo, package, order)
            ]
            found |= layer_violations(repo, package, order)
        declared_cs = csharp(data)
        if declared_cs is not None:
            layout = CSharpLayout(repo, declared_cs)
            problems += [f"{package}: {p}" for p in layout.problems]
            found |= layout.violations()
        violations[package] = sorted(found)
        hard = product_violations(repo, package, products)
        declared = roles(data)
        if declared is not None:
            problems += [f"{package}: {p}" for p in role_problems(declared)]
            hard |= role_violations(repo, package, declared)
        strict[package] = sorted(hard)
    return violations, problems, strict


# ------------------------------------------------------------------ names
#: The files rule 6 reads: code, shaders, UI and the docs a package ships.
NAME_SUFFIXES = {
    ".py", ".pyi", ".cs", ".hlsl", ".cginc", ".shader", ".compute",
    ".js", ".mjs", ".ts", ".md", ".asmdef", ".ui", ".uxml", ".uss",
}
#: History and agent maps name a unit's neighbours by design.
NAME_SKIP_FILES = {"CHANGELOG.md", "AGENTS.md", "CLAUDE.md"}
NAME_SKIP_DIRS = EXEMPT_DIRS | {
    "temp_tests", "test_output", "build", "dist", "node_modules",
    "Library", "Temp", "Logs",
}
NAMES_FIX = (
    "name only what sits below: say it in the contract's terms, or move what "
    "needs the name to a unit that may know it (CODE_STANDARD section 0, Parts)"
)
_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+\d*|[A-Z]+\d*")


def words(text: str) -> Set[str]:
    """The lower-cased words of *text*, identifiers split at case and
    underscores: ``MayaSurface`` holds ``maya``; ``mayatk`` is one word."""
    return {match.group(0).lower() for match in _WORD.finditer(text)}


def name_forbid(data: dict) -> Set[str]:
    """The application names a package declares it never uses
    (``[tool.m3trik.names] forbid``), lower-cased."""
    names = data.get("tool", {}).get("m3trik", {}).get("names", {})
    return {name.lower() for name in names.get("forbid", [])}


def ecosystem_closure(workspace: Path, ecosystem: Sequence[str]) -> Dict[str, Set[str]]:
    """Package -> every ecosystem package it depends on, directly or through
    another; a package with no readable pyproject depends on none."""
    members = set(ecosystem)
    direct: Dict[str, Set[str]] = {}
    for package in ecosystem:
        try:
            direct[package] = declared_dependencies(pyproject(workspace / package)) & members
        except (OSError, tomllib.TOMLDecodeError):
            direct[package] = set()
    closure: Dict[str, Set[str]] = {}
    for package in ecosystem:
        seen: Set[str] = set()
        stack = list(direct[package])
        while stack:
            dependency = stack.pop()
            if dependency not in seen:
                seen.add(dependency)
                stack.extend(direct.get(dependency, ()))
        closure[package] = seen
    return closure


def name_roots(repo: Path, package: str, data: dict) -> List[Path]:
    """The folders rule 6 reads: the package, its tests, its Unity package."""
    roots = [repo / package, repo / "test"]
    declared_cs = csharp(data)
    if declared_cs and declared_cs.get("root"):
        roots.append(repo / declared_cs["root"])
    return [root for root in roots if root.is_dir()]


def iter_named_files(roots: Sequence[Path]) -> Iterator[Path]:
    seen: Set[Path] = set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames if d not in NAME_SKIP_DIRS and not d.startswith(".")
            ]
            for name in filenames:
                path = Path(dirpath) / name
                if (
                    path.suffix.lower() in NAME_SUFFIXES
                    and name not in NAME_SKIP_FILES
                    and path not in seen
                ):
                    seen.add(path)
                    yield path


def name_violations(repo: Path, package: str, data: dict, forbidden: Set[str]) -> Set[str]:
    """Each file of *package* naming a word of *forbidden*: an ecosystem package
    above it, or an application it declared it never uses."""
    found: Set[str] = set()
    if not forbidden:
        return found
    for path in iter_named_files(name_roots(repo, package, data)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.lower()
        if not any(name in lowered for name in forbidden):
            continue  # the cheap test first: most files name nothing
        for word in sorted(words(text) & forbidden):
            found.add(f"{path.relative_to(repo).as_posix()} names {word} (names)")
    return found


def layers_fix(violation: str) -> str:
    """The fix a violation names: a C# reference rule's, or rule 6's."""
    return csharp_fix(violation) or (NAMES_FIX if violation.endswith("(names)") else "")


# -------------------------------------------------------------------- CLI
def baseline_file(workspace: Path = WORKSPACE) -> Path:
    """The baseline frozen from *workspace*: its own copy of this one, so a
    fixture or another checkout is judged against itself."""
    return workspace / BASELINE.relative_to(WORKSPACE)


def load_baseline(path: Path = BASELINE) -> Dict[str, List[str]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


BASELINE_DOC = (
    "Violations frozen when check_layers.py started holding the line "
    "(CODE_STANDARD section 0, Parts). Shrink it; never grow it without "
    "a reason in the commit. Rewrite: check_layers.py --update."
)


def write_baseline(
    violations: Dict[str, List[str]], path: Path = BASELINE, doc: str = BASELINE_DOC
) -> None:
    data = {"_doc": doc}
    data.update({k: sorted(v) for k, v in sorted(violations.items()) if v})
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def compare(
    violations: Dict[str, List[str]],
    baseline: Dict[str, List[str]],
    detail: Callable[[str, str], str] = lambda package, violation: "",
) -> int:
    """Print each package's new violations (with *detail*'s fix, when it names
    one), the frozen ones that no longer occur, and a verdict line; return how
    many are new. check_csharp.py reports through it too."""
    new_total = 0
    for package, found in violations.items():
        frozen = set(baseline.get(package, []))
        new = [v for v in found if v not in frozen]
        paid = sorted(frozen - set(found))
        for violation in new:
            fix = detail(package, violation)
            print(f"[FAIL] {package}: {violation}" + (f" -- {fix}" if fix else ""))
        for violation in paid:
            print(f"[PAID] {package}: {violation} no longer occurs (--update)")
        new_total += len(new)
        print(
            f"[{'FAIL' if new else 'OK'}] {package}: {len(new)} new, "
            f"{len(found) - len(new)} frozen"
        )
    return new_total


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="the default")
    mode.add_argument(
        "--update", action="store_true", help="freeze the current violations"
    )
    parser.add_argument(
        "--workspace", type=Path, default=WORKSPACE, help="the monorepo root"
    )
    parser.add_argument(
        "packages", nargs="*", help="check only these (default: the ecosystem set)"
    )
    args = parser.parse_args(argv)
    if args.update and args.packages:
        parser.error("--update rewrites the whole baseline: name no packages")

    violations, problems, strict = scan(args.workspace, args.packages)
    for problem in problems:
        print(f"[FAIL] declaration: {problem}")
    for package, found in strict.items():
        for violation in found:
            print(f"[FAIL] {package}: {violation} (strict: never frozen)")
    strict_total = sum(len(v) for v in strict.values())
    frozen_file = baseline_file(args.workspace)
    if args.update:
        # A package the scan could not read (absent, or a pyproject that does
        # not parse) is not paid off: its frozen entries stay.
        violations = {**load_baseline(frozen_file), **violations}
        frozen_file.parent.mkdir(parents=True, exist_ok=True)
        write_baseline(violations, frozen_file)
        total = sum(len(v) for v in violations.values())
        print(f"[WROTE] {frozen_file}: {total} frozen violation(s)")
        return 1 if problems or strict_total else 0

    new_total = compare(violations, load_baseline(frozen_file), lambda _, v: layers_fix(v))
    return 1 if new_total or problems or strict_total else 0


if __name__ == "__main__":
    sys.exit(main())
