#!/usr/bin/python
# coding=utf-8
"""Which tests does a change reach? Select them -- and run them, headless.

The everyday verification step (root ``CLAUDE.md`` Testing, CODE_STANDARD
section 9): after a change, run the tests that exercise what changed. A
package's FULL suite is for a full code review and the release preflight
(``push.ps1``'s ``tests`` receipt): a sweep of the workspace runs for hours
(mayatk ~1 h, uitk ~45 min, pythontk ~13 min), while the tests one edit reaches
usually run in seconds to minutes.

What a changed file selects, in its own package:

- a test file: itself;
- a source module: every test that imports it or a name from it, or names one of
  its distinctive top-level classes / functions (``mtk.EditUtils``,
  ``ptk.StatusBadge``), plus the ``test_<stem>.py`` convention, plus the tests
  that still name a name the change removed (vs ``HEAD``). A module no test
  reaches directly (a private helper) is followed up through the modules that
  import it, one level at a time, until some test does; one that only a few
  modules import (``IMPORTER_FANOUT``) also selects their tests -- a base class
  is exercised through its subclass;
- an asset (``.ui``, ``.json``, ``.glsl`` ...): the tests of its same-stem module,
  else the tests whose name carries the stem;
- anything under a ``GATES`` pattern (tentacle ``ui/`` / ``slots/``, a blendertk
  panel ``.ui``): also that package's structural suites, which read the files
  themselves so no import reaches them -- plus a note naming the host-only manual
  checks (tentacle ``test/blender``) that import the change's stem family;
- the test harness (``conftest.py``, ``base_test.py``, ``run_tests.py``,
  ``_suite_driver.py``, ``_host.py``): the runner's own tests;
- docs, changelogs and generated sidecars: nothing (``check_docs.py`` is their gate).

A relative path resolves as the shell would (the current directory, then the
workspace); one on disk at neither maps as a deletion only when its repo knew it
at ``HEAD`` -- otherwise it is reported, never guessed at.

Downstream packages (a ``mayatk`` test that names a ``pythontk`` class) are
counted, and selected only with ``--downstream``: a core edit reaches hundreds of
DCC modules, which is the full suite's job at review time.

Each package runs through its own ``test/run_tests.py``: the runner stays the
execution contract (sandboxing, fresh DCC processes, mayatk's GUI pass); this
script only picks the modules. ``--run`` runs them one package at a time (never
two suites at once), headless (``QT_QPA_PLATFORM=offscreen``) -- a GUI session
starts only where the runner requires one (mayatk's ``GUI_REQUIRED`` modules,
tentacle's Maya-hosted suites: those reading ``_host.MAYA_AVAILABLE`` or importing
the Maya host, ``Runner.host_modules``) -- never stamps a badge, and keeps each
runner's full output in ``<repo>/test/temp_tests/affected_<time>.log``. A run
whose tally shows no test executed (every one skipped) reads RAN NOTHING, not PASS.

Usage:
    python affected_tests.py <changed files...>          # print the plan
    python affected_tests.py <files> --run                # ...and run it
    python affected_tests.py                              # dirty files touched in the last 3 h
    python affected_tests.py --since 45m --run
    python affected_tests.py <files> -k mirror --run      # narrow (runners with -k)
    python affected_tests.py <files> --explain            # why each module was picked

Exit: 0 every selected run passed (or plan only), 1 a selected run failed or ran
nothing, 2 usage.
"""

import argparse
import ast
import datetime
import fnmatch
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import check_layers  # noqa: E402  (sibling script: the AST import resolver)
import sync_workspace  # noqa: E402  (sibling script: the declared unit set)

#: Directories never scanned: caches, build copies, scratch.
SKIP_DIRS = {"__pycache__", "build", "dist", "temp_tests", ".git", "node_modules", "logs"}
#: Test-harness files: a change selects the runner's own tests.
HARNESS = {"conftest.py", "base_test.py", "run_tests.py", "_suite_driver.py", "_host.py"}
HARNESS_TESTS = ("test_run_tests", "test_base_test", "test_suite_driver")
#: Test subdirectories a package's runner resolves module names in.
TEST_SUBDIRS = {"mayatk": ("mock_tests", "extended"), "tentacle": ("slots",)}
#: Text the gates own, not the tests.
DOC_SUFFIXES = {".md", ".rst", ".txt"}
#: A name defined in this many source modules says nothing about one of them.
GENERIC_SPREAD = 3
#: How many importer levels a module no test reaches directly (a private
#: helper) is followed up before giving up.
MAX_DEPTH = 3
#: A module with at most this many importers also selects the importers' tests.
IMPORTER_FANOUT = 5
#: Generated sidecars and changelogs: never a test input, never "dirty work".
GENERATED = re.compile(r"(^|/)(API_[A-Z_]+\.(md|json)|PARITY_[A-Z_]+\.md|CHANGELOG\.md)$")


# ---------------------------------------------------------------- packages
@dataclass
class Package:
    """One unit with a ``test/`` directory."""

    name: str
    repo: Path
    import_root: Path  # the directory on sys.path (repo, or m3trik/scripts)
    source: Optional[Path]  # the importable package dir, if any
    deps: Set[str] = field(default_factory=set)

    @property
    def test_dir(self) -> Path:
        return self.repo / "test"


@dataclass
class Runner:
    """How a package's runner takes a subset: ``argv`` + module names."""

    argv: Tuple[str, ...]
    modules_flag: Optional[str] = None  # None = positional
    k_flag: Optional[str] = "-k"  # None = the runner has no name filter
    extra: Tuple[str, ...] = ("--no-badge",)
    maya_flag: Optional[str] = None  # tentacle: run Maya-hosted modules in a fresh Maya
    #: With *maya_flag*: a test module is Maya-hosted when it reads one of these
    #: host probes, or imports one of these modules (or a module below one).
    host_probes: Tuple[str, ...] = ()
    host_modules: Tuple[str, ...] = ()


#: Each runner's subset contract. A package missing here runs its test files
#: through pytest (m3trik, www, comfyui, server, androidtk).
RUNNERS: Dict[str, Runner] = {
    "pythontk": Runner(("pythontk/test/run_tests.py",)),
    "uitk": Runner(("uitk/test/run_tests.py",), modules_flag="--modules"),
    "mayatk": Runner(("mayatk/test/run_tests.py",)),
    "blendertk": Runner(("blendertk/test/run_tests.py",), k_flag=None),
    # ``_host.MAYA_AVAILABLE`` is the suite's shared probe; the Maya host itself
    # (``TclMaya``, the Maya slots) builds only inside Maya, so a test importing
    # it skips everywhere else, under whatever guard it wrote locally.
    "tentacle": Runner(("tentacle/test/run_tests.py",), maya_flag="--in-maya",
                       host_probes=("MAYA_AVAILABLE",),
                       host_modules=("tentacle.tcl_maya", "tentacle.slots.maya")),
    "unitytk": Runner(("unitytk/test/run_tests.py",)),
    "extapps": Runner(("extapps/test/run_tests.py",)),
}


@dataclass(frozen=True)
class Gate:
    """Suites a change under one of *patterns* always selects: structural checks
    that read the files themselves (each ``.ui``'s widgets against its slot class),
    so no import reaches them. *host_checks* globs a package's manual checks only a
    real *host* runs: the ones importing the change's stem family get a note."""

    package: str
    patterns: Tuple[str, ...]  # fnmatch on the repo-relative path (``*`` crosses ``/``)
    suites: Tuple[str, ...]
    host_checks: Optional[str] = None
    host: str = ""


GATES: Tuple[Gate, ...] = (
    Gate("tentacle", ("tentacle/ui/*", "tentacle/slots/*"),
         ("test_slot_method_coverage", "test_ui_integrity", "test_slot_integrity",
          "test_dcc_invariants", "test_ui_footers"),
         host_checks="test/blender/*_check.py", host="Blender"),
    # Loads every co-located tool panel's .ui through BlenderUiHandler and wires its slots.
    Gate("blendertk", ("blendertk/*.ui",), ("test_blender_ui_handler",)),
)


@lru_cache(maxsize=None)
def packages(workspace: Path = WORKSPACE) -> Dict[str, Package]:
    """Every declared unit that has a ``test/`` dir, keyed by name."""
    found: Dict[str, Package] = {}
    names = set()
    for unit in sync_workspace.load()["units"]:
        names.add(unit["path"].split("/")[0])
    for name in sorted(names):
        repo = workspace / name
        if not (repo / "test").is_dir():
            continue
        source = repo / name if (repo / name / "__init__.py").is_file() else None
        import_root = repo
        if source is None and (repo / "scripts").is_dir():
            import_root = repo / "scripts"  # m3trik: tests import scripts flat
        deps: Set[str] = set()
        if (repo / "pyproject.toml").is_file():
            try:
                deps = check_layers.declared_dependencies(check_layers.pyproject(repo))
            except Exception:
                deps = set()
        found[name] = Package(name, repo, import_root, source, deps & names)
    return found


def package_of(path: Path, workspace: Path = WORKSPACE) -> Optional[Package]:
    try:
        rel = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return None
    return packages(workspace).get(rel.parts[0]) if rel.parts else None


# ---------------------------------------------------------------- AST index
class _Collector(check_layers._Imports):
    """check_layers' import resolver (relative imports, ``TYPE_CHECKING``), plus
    the names a file uses -- one pass per file.

    Built with an ``exists`` that answers no, so ``targets`` holds every
    ``import x.y`` name and every ``from`` module as written: whether
    ``from pkg.sub import mod`` named a module is settled at query time from
    ``pairs`` (:func:`_reaches`), so the index costs no filesystem probe. ``pairs``
    holds ``(module, name)`` per ``from module import name``; ``refs`` every
    identifier and attribute name; ``tests`` the ``def test*`` count.
    """

    def __init__(self, package_parts) -> None:
        super().__init__(package_parts, lambda _parts: False)
        self.pairs: Set[Tuple[str, str]] = set()
        self.refs: Set[str] = set()
        self.tests = 0
        #: Names this file binds to a literal anywhere (``HARNESS = "..."`` in a
        #: class body): its own constants, never a reference to another module's.
        self.literals: Set[str] = set()

    _LITERALS = (ast.Constant, ast.JoinedStr, ast.List, ast.Tuple, ast.Dict, ast.Set)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, self._LITERALS):
            self.literals.update(t.id for t in node.targets if isinstance(t, ast.Name))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, self._LITERALS) and isinstance(node.target, ast.Name):
            self.literals.add(node.target.id)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        before = len(self.targets)
        super().visit_ImportFrom(node)
        module = self.targets[before] if len(self.targets) > before else ""
        for alias in node.names:
            self.pairs.add((module, alias.name))
            self.refs.add(alias.name)

    def visit_Name(self, node: ast.Name) -> None:
        self.refs.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.refs.add(node.attr)
        self.generic_visit(node)

    def visit_FunctionDef(self, node) -> None:
        if node.name.startswith("test"):
            self.tests += 1
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


@dataclass
class FileInfo:
    path: Path
    module: str  # dotted, relative to the import root
    targets: Set[str]
    pairs: Set[Tuple[str, str]]
    refs: Set[str]
    defines: Set[str]  # top-level classes, functions, UPPER_CASE constants
    tests: int  # ``def test*`` count (test files)
    members: Set[str] = field(default_factory=set)  # ``Class.method`` per top-level class
    literals: Set[str] = field(default_factory=set)  # names bound to a literal anywhere


def _reaches(info: FileInfo, module: str, names: Set[str]) -> Optional[str]:
    """Why *info* imports *module* (dotted) or one of its *names*, else None."""
    if module in info.targets:
        return f"imports {module}"
    for m, n in info.pairs:
        if f"{m}.{n}" == module:  # ``from pkg.sub import mod``
            return f"imports {module}"
        if n in names and module.startswith(m + "."):  # re-exported by a parent
            return f"imports {n} from {m}"
    return None


def _imported(info: FileInfo) -> Set[str]:
    """Every module *info* imports, ``from pkg import mod`` spelled ``pkg.mod``."""
    return set(info.targets) | {f"{m}.{n}" for m, n in info.pairs}


#: Bump when :class:`FileInfo` or the collector changes: the on-disk index is
#: then rebuilt instead of read.
INDEX_VERSION = 3
_INDEX: Dict[str, Tuple[int, int, FileInfo]] = {}
_INDEX_DIRTY = False


def _index_path() -> Optional[Path]:
    """The persistent index (``ptk.UserConfig.cache_dir``), or None without pythontk."""
    try:
        if str(WORKSPACE / "pythontk") not in sys.path:
            sys.path.insert(0, str(WORKSPACE / "pythontk"))
        from pythontk.core_utils.user_config import UserConfig

        return UserConfig.cache_dir("affected_tests", create=True) / f"index_v{INDEX_VERSION}.pickle"
    except Exception:
        return None


def _load_index() -> None:
    import pickle

    path = _index_path()
    if path is None or not path.is_file():
        return
    try:
        with open(path, "rb") as handle:
            _INDEX.update(pickle.load(handle))
    except Exception:
        _INDEX.clear()  # a corrupt or foreign index is rebuilt, never fatal


def save_index() -> None:
    """Persist what this run parsed (only when something new was parsed)."""
    import pickle

    path = _index_path()
    if path is None or not _INDEX_DIRTY:
        return
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "wb") as handle:
            pickle.dump(_INDEX, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        for stale in path.parent.glob("index_v*.pickle"):  # an older format's index
            if stale != path:
                stale.unlink()
    except OSError:
        pass


@lru_cache(maxsize=None)
def _parse(path: Path, import_root: Path) -> Optional[FileInfo]:
    global _INDEX_DIRTY
    try:
        stat = path.stat()
    except OSError:
        return None
    key = str(path)
    cached = _INDEX.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    try:
        rel = path.relative_to(import_root)
    except ValueError:
        rel = Path(path.name)
    parts = list(rel.with_suffix("").parts)
    module_parts = parts[:-1] if parts and parts[-1] == "__init__" else parts
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError, OSError):
        return None
    collector = _Collector(parts[:-1])
    collector.visit(tree)
    defines: Set[str] = set()
    members: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            defines.add(node.name)
        if isinstance(node, ast.ClassDef):
            members.update(
                f"{node.name}.{child.name}"
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    defines.add(target.id)
    info = FileInfo(
        path,
        ".".join(module_parts),
        set(collector.targets),
        collector.pairs,
        collector.refs,
        defines,
        collector.tests,
        members,
        collector.literals,
    )
    _INDEX[key] = (stat.st_mtime_ns, stat.st_size, info)
    _INDEX_DIRTY = True
    return info


def _walk(root: Path, pattern: str) -> Iterable[Path]:
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if Path(name).match(pattern):
                yield Path(dirpath) / name


@lru_cache(maxsize=None)
def test_files(name: str, workspace: Path = WORKSPACE) -> Tuple[FileInfo, ...]:
    """A package's runnable test modules: ``test/test_*.py`` plus the subdirs
    its runner reaches by name (mayatk ``mock_tests``/``extended``, tentacle
    ``slots``)."""
    pkg = packages(workspace)[name]
    roots = [pkg.test_dir] + [pkg.test_dir / sub for sub in TEST_SUBDIRS.get(name, ())]
    infos = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("test_*.py")):
            info = _parse(path, pkg.import_root)
            if info is not None:
                infos.append(info)
    return tuple(infos)


@lru_cache(maxsize=None)
def source_files(name: str, workspace: Path = WORKSPACE) -> Tuple[FileInfo, ...]:
    pkg = packages(workspace)[name]
    root = pkg.source or (pkg.import_root if pkg.import_root != pkg.repo else None)
    if root is None:
        return ()
    infos = []
    for path in _walk(root, "*.py"):
        info = _parse(path, pkg.import_root)
        if info is not None:
            infos.append(info)
    return tuple(infos)


@lru_cache(maxsize=None)
def name_spread(workspace: Path = WORKSPACE) -> Dict[str, int]:
    """Top-level name -> how many source modules (workspace-wide) define it."""
    spread: Dict[str, int] = {}
    for name in packages(workspace):
        for info in source_files(name, workspace):
            for defined in info.defines:
                spread[defined] = spread.get(defined, 0) + 1
    return spread


def distinctive(names: Iterable[str], workspace: Path = WORKSPACE) -> Set[str]:
    """The names that identify their module when a test merely mentions them.

    Dropped: short names, names many modules define (``main``, ``setUp``), and
    plain lowercase words (``update``, ``items``) -- an attribute access on a
    dict reads the same. Those still count when a test imports them by name.
    """
    spread = name_spread(workspace)
    keep = set()
    for name in names:
        if len(name) < 4 or spread.get(name, 0) >= GENERIC_SPREAD:
            continue
        if name.islower() and "_" not in name.strip("_"):
            continue
        keep.add(name)
    return keep


# ---------------------------------------------------------------- selection
@dataclass
class Selection:
    """Selected modules per package, with the reasons (for ``--explain``)."""

    picks: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)  # pkg -> module -> reasons
    downstream: Dict[str, Set[str]] = field(default_factory=dict)  # pkg -> modules
    notes: List[str] = field(default_factory=list)
    docs: List[str] = field(default_factory=list)  # changed files no test covers by design
    harness: Dict[str, List[str]] = field(default_factory=dict)  # pkg -> changed harness files
    #: (host, check path) -> the changed files it reaches: manual checks no runner runs.
    host_only: Dict[Tuple[str, str], Set[str]] = field(default_factory=dict)

    def add(self, pkg: str, module: str, reason: str) -> None:
        self.picks.setdefault(pkg, {}).setdefault(module, set()).add(reason)


def _hits(pkg: str, module: str, names: Set[str], workspace: Path) -> Dict[str, str]:
    """Test modules of *pkg* that reach *module* (dotted) or its *names*."""
    marks = distinctive(names, workspace)
    found: Dict[str, str] = {}
    for test in test_files(pkg, workspace):
        why = _reaches(test, module, names)
        if why is None:
            # A name the test defines itself (its own ``HARNESS``) is not ours.
            named = sorted((marks & test.refs) - test.defines - test.literals)
            why = "names " + ", ".join(named[:3]) if named else None
        if why:
            found[test.path.stem] = why
    return found


def _convention(pkg: str, path: Path, workspace: Path, folder: bool = False) -> List[str]:
    """``test_<stem>`` (and ``test_<stem minus _utils>``) when it exists; with
    *folder*, also the parent folder's -- a feature package's tests are often named
    after the package, but a grab-bag folder (``core_utils``) says little, so the
    caller asks for it only when nothing more specific matched."""
    stems = {t.path.stem for t in test_files(pkg, workspace)}
    base = path.stem.lstrip("_")
    candidates = [base, base.replace("_utils", "")]
    if folder:
        candidates.append(path.parent.name.lstrip("_"))
    return [f"test_{c}" for c in dict.fromkeys(candidates) if c and f"test_{c}" in stems]


def _importers(pkg: str, module: str, names: Set[str], workspace: Path) -> List[FileInfo]:
    return [
        info
        for info in source_files(pkg, workspace)
        if info.module != module and _reaches(info, module, names)
    ]


def known_at_head(pkg: Package, path: Path) -> bool:
    """Whether *path* exists at ``HEAD`` of its package's repo (a deletion, not a typo)."""
    try:
        rel = path.resolve().relative_to(pkg.repo.resolve()).as_posix()
        return subprocess.run(
            ["git", "-C", str(pkg.repo), "cat-file", "-e", f"HEAD:{rel}"],
            capture_output=True, timeout=30,
        ).returncode == 0
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


def locate(raw: Path, workspace: Path = WORKSPACE) -> Optional[Path]:
    """Where a changed path is, as a shell reads it: against the current directory,
    then the workspace. A path on disk at neither is a deletion only when its repo
    knew it at ``HEAD``; otherwise None (a typo maps nothing)."""
    raw = Path(raw)
    bases = [Path()] if raw.is_absolute() else [Path.cwd(), workspace]
    candidates = list(dict.fromkeys((base / raw).resolve() for base in bases))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in candidates:
        pkg = package_of(candidate, workspace)
        if pkg is not None and known_at_head(pkg, candidate):
            return candidate
    return None


def select(paths: Sequence[Path], workspace: Path = WORKSPACE, downstream: bool = False) -> Selection:
    """Map changed *paths* to the test modules that reach them."""
    if not _INDEX:
        _load_index()
    sel = Selection()
    for raw in paths:
        path = locate(Path(raw), workspace)
        if path is None:
            sel.notes.append(f"no such file: {raw}")
            continue
        pkg = package_of(path, workspace)
        if pkg is None:
            sel.notes.append(f"outside every tested unit: {raw}")
            continue
        _select_gates(sel, pkg, path, workspace)
        if not path.exists():  # deleted: its repo knew it at HEAD
            if path.suffix == ".py" and pkg.test_dir.resolve() not in path.parents:
                _select_source(sel, pkg, path, workspace, downstream, info=_vanished(pkg, path))
            else:
                sel.notes.append(f"deleted, nothing to map: {raw}")
            continue
        _select_one(sel, pkg, path, workspace, downstream)
    save_index()
    return sel


def _family(path: Path) -> str:
    """The stem a ``.ui``, its compiled ``_ui.py`` and its slot modules share:
    ``materials#submenu.ui`` / ``materials_ui.py`` / ``slots/_materials.py`` ->
    ``materials``."""
    stem = path.name.split("#")[0].split(".")[0].lstrip("_")
    return stem[: -len("_ui")] if stem.endswith("_ui") else stem


def _select_gates(sel: Selection, pkg: Package, path: Path, workspace: Path) -> None:
    """The structural suites a change under a :data:`GATES` pattern always selects,
    and the host-only checks of its stem family (named, never run)."""
    rel = path.relative_to(pkg.repo.resolve()).as_posix()
    if path.suffix in DOC_SUFFIXES or GENERATED.search(rel):
        return
    stems = {t.path.stem for t in test_files(pkg.name, workspace)}
    family = _family(path)
    for gate in GATES:
        hit = next((p for p in gate.patterns if fnmatch.fnmatchcase(rel, p)), None)
        if gate.package != pkg.name or hit is None:
            continue
        for stem in gate.suites:
            if stem in stems:
                sel.add(pkg.name, stem, f"structural gate for {hit}")
        if not gate.host_checks:
            continue
        for check in sorted(pkg.repo.glob(gate.host_checks)):
            info = _parse(check, pkg.import_root)
            if info and any(
                m.startswith(pkg.name + ".") and m.rsplit(".", 1)[-1].lstrip("_") == family
                for m in _imported(info)
            ):
                key = (gate.host, check.relative_to(workspace.resolve()).as_posix())
                sel.host_only.setdefault(key, set()).add(path.name)


def _select_one(sel: Selection, pkg: Package, path: Path, workspace: Path, downstream: bool) -> None:
    name = pkg.name
    rel = path.relative_to(workspace.resolve()).as_posix()
    in_tests = pkg.test_dir.resolve() in path.parents

    if path.suffix in DOC_SUFFIXES or GENERATED.search(rel):
        sel.docs.append(rel)
        return
    if in_tests and path.name in HARNESS:
        stems = {t.path.stem for t in test_files(name, workspace)}
        for stem in (s for s in HARNESS_TESTS if s in stems):
            sel.add(name, stem, f"harness changed: {path.name}")
        sel.harness.setdefault(name, []).append(path.name)
        return
    if in_tests:
        if path.name.startswith("test_") and path.suffix == ".py":
            sel.add(name, path.stem, "changed test")
            return
        # A helper beside the tests (``slots/_helpers.py``): the tests that import
        # it, flat, as their siblings do.
        users = [
            t.path.stem for t in test_files(name, workspace)
            if path.stem in t.targets or any(m == path.stem for m, _ in t.pairs)
        ]
        for stem in users:
            sel.add(name, stem, f"imports test helper {path.name}")
        if not users:
            sel.notes.append(f"test-dir file no test imports: {rel}")
        return
    if path.suffix != ".py":
        sibling = path.with_suffix(".py")
        if sibling.is_file():
            _select_source(sel, pkg, sibling, workspace, downstream, via=path.name)
            return
        stems = [t.path.stem for t in test_files(name, workspace) if path.stem.lower() in t.path.stem.lower()]
        for stem in stems:
            sel.add(name, stem, f"named after asset {path.name}")
        if not stems:
            sel.notes.append(f"asset no test names: {rel}")
        return
    _select_source(sel, pkg, path, workspace, downstream)


def removed_names(pkg: Package, path: Path, current: Set[str]) -> Set[str]:
    """Top-level names *path* defined at ``HEAD`` and no longer defines.

    The likeliest breakage of a change is the caller of a name it removed --
    moving ``foo`` onto ``Class.foo`` leaves every test that still calls
    ``foo`` failing at runtime (collection passes), and the module's CURRENT
    names cannot find those tests. Empty when the file is new, untracked or
    unreadable at ``HEAD``.
    """
    try:
        rel = path.resolve().relative_to(pkg.repo.resolve()).as_posix()
        old = subprocess.run(
            ["git", "-C", str(pkg.repo), "show", f"HEAD:{rel}"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30,
        )
        if old.returncode:
            return set()
        tree = ast.parse(old.stdout)
    except (ValueError, OSError, subprocess.SubprocessError, SyntaxError):
        return set()
    before = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return before - current


def _vanished(pkg: Package, path: Path) -> FileInfo:
    """A deleted / renamed module as the index last saw it: what still imports
    it is exactly what the change breaks. Its names come from the persistent
    index when it was ever parsed; the import path alone still finds importers."""
    cached = _INDEX.get(str(path))
    try:
        parts = list(path.relative_to(pkg.import_root).with_suffix("").parts)
    except ValueError:
        parts = [path.stem]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    defines = set(cached[2].defines) if cached else set()
    return FileInfo(path, ".".join(parts), set(), set(), set(), defines, 0)


def _select_source(sel: Selection, pkg: Package, path: Path, workspace: Path,
                   downstream: bool, via: Optional[str] = None,
                   info: Optional[FileInfo] = None) -> None:
    name = pkg.name
    deleted = info is not None
    info = info or _parse(path.resolve(), pkg.import_root)
    if info is None:
        sel.notes.append(f"unparsable, nothing selected: {path}")
        return
    prefix = "deleted: " if deleted else (f"{via}: " if via else "")
    found = _hits(name, info.module, info.defines, workspace)
    spread = name_spread(workspace)
    gone = {
        n for n in removed_names(pkg, path, info.defines)
        if len(n) >= 4 and spread.get(n, 0) < GENERIC_SPREAD
    }
    if gone:
        # A plain word counts here too (unlike distinctive()): a test still
        # naming a removed function is exactly the one that now breaks.
        for test in test_files(name, workspace):
            named = sorted((gone & test.refs) - test.defines - test.literals)
            if named and test.path.stem not in found:
                found[test.path.stem] = "names removed " + ", ".join(named[:3])
    for stem in _convention(name, path, workspace):
        found.setdefault(stem, "naming convention")
    # A module few others import is often exercised THROUGH them -- a dialog
    # class through its subclass (``AttributeColorDialog``), whose tests never
    # name the base. Cheap at a small fan-out; a core module's hundred
    # importers are the full suite's job.
    importers = _importers(name, info.module, info.defines, workspace)
    if found and len(importers) <= IMPORTER_FANOUT:
        for importer in importers:
            for stem, why in _hits(name, importer.module, importer.defines, workspace).items():
                found.setdefault(stem, f"via {importer.module} ({why})")
    frontier, seen, depth = [info], {info.module}, 0
    while not found and frontier and depth < MAX_DEPTH:
        depth += 1
        nxt = []
        for current in frontier:
            for importer in _importers(name, current.module, current.defines, workspace):
                if importer.module in seen:
                    continue
                seen.add(importer.module)
                nxt.append(importer)
                for stem, why in _hits(name, importer.module, importer.defines, workspace).items():
                    found.setdefault(stem, f"via {importer.module} ({why})")
        frontier = nxt
    if not found:
        for stem in _convention(name, path, workspace, folder=True):
            found[stem] = "naming convention (folder)"
    for stem, why in found.items():
        sel.add(name, stem, prefix + why)
    if not found:
        sel.notes.append(f"{name}: no test reaches {info.module} (untested?)")
    for other in packages(workspace).values():
        if name not in other.deps:
            continue
        hits = _hits(other.name, info.module, info.defines | gone, workspace)
        if not hits:
            continue
        if downstream:
            for stem, why in hits.items():
                sel.add(other.name, stem, f"downstream of {info.module}: {why}")
        else:
            sel.downstream.setdefault(other.name, set()).update(hits)


# ---------------------------------------------------------------- facts
@lru_cache(maxsize=None)
def gui_required(workspace: Path = WORKSPACE) -> Set[str]:
    """mayatk's ``GUI_REQUIRED`` keys, read statically (no import)."""
    path = workspace / "mayatk" / "test" / "run_tests.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "GUI_REQUIRED" for t in node.targets
        ):
            if isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    return set()


_RESULT_LINE = re.compile(r"^(test_\w+): [A-Z][A-Z ]+?\[(\d+(?:\.\d+)?)s\]", re.M)


@lru_cache(maxsize=None)
def last_seconds(workspace: Path = WORKSPACE, files: int = 40) -> Dict[str, float]:
    """mayatk module -> seconds, the newest observation in its results files."""
    temp = workspace / "mayatk" / "test" / "temp_tests"
    seen: Dict[str, float] = {}
    try:
        results = sorted(temp.glob("test_results_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return seen
    for path in results[:files]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for module, seconds in _RESULT_LINE.findall(text):
            seen.setdefault(module, float(seconds))
    return seen


def maya_gated(pkg: str, stem: str, workspace: Path = WORKSPACE) -> bool:
    """A test module whose tests skip without a Maya host: it reads the runner's
    host probe or imports the Maya host (:attr:`Runner.host_modules`). Whatever
    this misses, :func:`run` still reports a run that executed nothing."""
    runner = RUNNERS.get(pkg)
    if runner is None or not runner.maya_flag:
        return False
    info = next((t for t in test_files(pkg, workspace) if t.path.stem == stem), None)
    if info is None:
        return False
    if set(runner.host_probes) & info.refs:
        return True
    return any(m == h or m.startswith(h + ".") for m in _imported(info) for h in runner.host_modules)


# ---------------------------------------------------------------- commands
def commands(sel: Selection, k: Optional[str] = None, gui: bool = True,
             workspace: Path = WORKSPACE) -> List[Tuple[str, List[str], List[str]]]:
    """``(package, argv, modules)`` per package, in cascade-ish order."""
    order = list(sync_workspace.load()["cascade"])
    names = sorted(sel.picks, key=lambda n: (order.index(n) if n in order else len(order), n))
    out = []
    for name in names:
        modules = sorted(sel.picks[name])
        runner = RUNNERS.get(name)
        if runner is None:
            pkg = packages(workspace)[name]
            argv = [sys.executable, "-m", "pytest", "-q"]
            argv += [str((pkg.test_dir / f"{m}.py").relative_to(workspace)) for m in modules]
            if k:
                argv += ["-k", k]
            out.append((name, argv, modules))
            continue
        groups = [modules]
        if runner.maya_flag and gui:
            gated = [m for m in modules if maya_gated(name, m, workspace)]
            plain = [m for m in modules if m not in gated]
            groups = [g for g in (plain, gated) if g]
        for group in groups:
            argv = [sys.executable, *runner.argv]
            argv += [runner.modules_flag, *group] if runner.modules_flag else list(group)
            if runner.maya_flag and gui and maya_gated(name, group[0], workspace):
                argv.append(runner.maya_flag)
            if name == "mayatk":
                if any((workspace / "mayatk" / "test" / "mock_tests" / f"{m}.py").is_file() for m in group):
                    argv.append("--mocks")
                if any((workspace / "mayatk" / "test" / "extended" / f"{m}.py").is_file() for m in group):
                    argv.append("--extended")
                if not gui:  # its GUI_REQUIRED modules then report NOT RUN (exit 2), honestly
                    argv.append("--no-gui-pass")
            if k and runner.k_flag:
                argv += [runner.k_flag, k]
            argv += list(runner.extra)
            out.append((name, argv, group))
    return out


def _display(argv: Sequence[str]) -> str:
    shown = ["python" if a == sys.executable else a for a in argv]
    return " ".join(f'"{a}"' if " " in a else a for a in shown)


# ---------------------------------------------------------------- changed files
def _duration(text: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"not a duration: {text!r} (e.g. 30m, 3h)")
    scale = {"": 60, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return float(match.group(1)) * scale


def recent_dirty(seconds: float, workspace: Path = WORKSPACE) -> List[Path]:
    """Dirty (modified / untracked) files in every unit repo touched within *seconds*."""
    cutoff = time.time() - seconds
    found = []
    for pkg in packages(workspace).values():
        try:
            out = subprocess.run(
                ["git", "-C", str(pkg.repo), "status", "--porcelain", "-uall"],
                capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=60,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for line in out.splitlines():
            rel = line[3:].strip().strip('"')
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1]
            path = pkg.repo / rel
            try:
                if path.is_file() and path.stat().st_mtime >= cutoff and not GENERATED.search(rel):
                    found.append(path)
            except OSError:
                continue
    return sorted(set(found))


# ---------------------------------------------------------------- report / run
def report(sel: Selection, cmds, explain: bool, workspace: Path = WORKSPACE,
           k: Optional[str] = None) -> str:
    lines = []
    total_modules = sum(len(m) for m in sel.picks.values())
    if not total_modules:
        lines.append("No test module reaches these changes.")
    secs = last_seconds(workspace)
    gui = gui_required(workspace)
    for name, argv, modules in cmds:
        tests = {t.path.stem: t.tests for t in test_files(name, workspace)}
        count = sum(tests.get(m, 0) for m in modules)
        flags = []
        if name == "mayatk":
            known = [secs[m] for m in modules if m in secs]
            if known:
                flags.append(f"~{sum(known):.0f}s last run")
            heavy = [m for m in modules if m in gui]
            if heavy:
                flags.append("GUI pass: " + ", ".join(heavy))
        runner = RUNNERS.get(name)
        if runner and runner.maya_flag and runner.maya_flag in argv:
            flags.append("Maya-hosted: runs in a fresh GUI Maya")
        if k and runner and not runner.k_flag:
            flags.append("no -k in this runner: whole modules run")
        extra = f" ({'; '.join(flags)})" if flags else ""
        lines.append(f"{name}: {len(modules)} module(s), ~{count} test(s){extra}")
        if explain:
            for module in modules:
                lines.append(f"    {module}: " + "; ".join(sorted(sel.picks[name][module])))
        else:
            lines.append("    " + ", ".join(modules))
        lines.append("    $ " + _display(argv))
    if sel.downstream:
        parts = [f"{n} {len(m)}" for n, m in sorted(sel.downstream.items())]
        lines.append("downstream (not selected; --downstream adds them): " + ", ".join(parts))
    for name, files in sorted(sel.harness.items()):
        lines.append(
            f"note: {name} test harness changed ({', '.join(files)}) -- its own tests are "
            "selected; a harness change can reach every module, so sample more widely before review"
        )
    for (host, check), changed in sorted(sel.host_only.items()):
        lines.append(f"note: host-only, not run (a fresh {host} runs it by hand): {check} "
                     f"(reaches {', '.join(sorted(changed))})")
    if sel.docs:
        lines.append("note: docs/generated, no tests (check_docs.py is their gate): " + ", ".join(sel.docs))
    for note in sel.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


#: A runner's own tally lines, whatever its format (unittest, pytest, mayatk's
#: SUMMARY, blendertk's checks, the badge refusals), and the runners' own word
#: for a module that produced only skips (pythontk, uitk).
_TALLY = re.compile(
    r"^\s*(Ran \d+ tests?|Total:|PASSED|FAILED|OK\b|NOT RUN|\[INCOMPLETE\]|=+ .*(passed|failed)|"
    r"\d+ (passed|failed)|Passed:|Failed:|Errors:)|contributed only skips",
)


def digest(text: str, failed: bool) -> List[str]:
    """What a run's console needs from its log: the tally on a pass, the tail
    (tracebacks, failing ids) on a failure -- the log keeps the rest."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if failed:
        return lines[-40:]
    tally = [ln for ln in lines if _TALLY.search(ln)]
    return tally[-4:] or lines[-6:]


_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_UNITTEST_END = re.compile(r"^(?:OK|FAILED)\b(?: \((.*)\))?\s*$", re.M)
#: ``Total: 7031 tests, ... 66 skipped`` (mayatk), ``PASSED: 12 tests, ...`` (the
#: unittest runners), ``Total: 6899 checks, ...`` (blendertk), ``PASSED: 48 passed,
#: ...`` (extapps).
_SUMMARY = re.compile(r"^\s*(?:Total|PASSED|FAILED):\s+(.+)$", re.M)
#: pytest's closing line: ``3 passed, 1 skipped in 0.4s`` (``=`` rules optional).
_PYTEST = re.compile(
    r"^[=\s]*(\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b[^\n]*?) in [\d.]+s\b",
    re.M,
)
_COUNT = re.compile(r"(\d+) (passed|failed|errors?|xfailed|xpassed)\b")


def executed(text: str) -> Optional[int]:
    """How many tests a runner's log says EXECUTED (skips excluded) -- the most
    any one of its tallies reports -- or None when it prints no tally this knows."""
    counts = []
    for match in _RAN.finditer(text):
        end = _UNITTEST_END.search(text, match.end())
        skipped = re.search(r"skipped=(\d+)", (end.group(1) or "") if end else "")
        counts.append(int(match.group(1)) - (int(skipped.group(1)) if skipped else 0))
    for match in _SUMMARY.finditer(text):
        body = match.group(1)
        total = re.match(r"(\d+) (?:tests?|checks?)\b", body)
        if total:
            skipped = re.search(r"(\d+) skipped", body)
            counts.append(int(total.group(1)) - (int(skipped.group(1)) if skipped else 0))
        elif _COUNT.search(body):
            counts.append(sum(int(n) for n, _ in _COUNT.findall(body)))
    for match in _PYTEST.finditer(text):
        counts.append(sum(int(n) for n, _ in _COUNT.findall(match.group(1))))
    return max(counts) if counts else None


def run(cmds, workspace: Path = WORKSPACE) -> int:
    """Run *cmds* one at a time; print a digest each; 1 if any failed or ran
    nothing (every test skipped: no host, or a ``-k`` that matched none)."""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    failed, idle = [], []
    for index, (name, argv, modules) in enumerate(cmds):
        pkg = packages(workspace)[name]
        log_dir = pkg.test_dir / "temp_tests"
        log_dir.mkdir(exist_ok=True)
        for old in log_dir.glob("affected_*.log"):  # its own, after mayatk's 7-day sweep age
            try:
                if old.stat().st_mtime < time.time() - 7 * 86400:
                    old.unlink()
            except OSError:
                pass
        # One log per command: tentacle's plain and --in-maya groups share a package.
        log = log_dir / f"affected_{stamp}_{index}_{name}.log"
        print(f"\n=== {name}: {len(modules)} module(s) ===\n$ {_display(argv)}", flush=True)
        start = time.monotonic()
        with open(log, "w", encoding="utf-8", errors="replace") as handle:
            code = subprocess.run(
                argv, cwd=str(workspace), env=env, stdout=handle, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            ).returncode
        elapsed = time.monotonic() - start
        text = log.read_text(encoding="utf-8", errors="replace")
        tail = digest(text, failed=bool(code))
        if code:
            verdict = f"FAIL (exit {code})"
            failed.append(name)
        elif executed(text) == 0:
            # Green and verified nothing: a host-gated module run without its host.
            verdict = "RAN NOTHING (every selected test skipped)"
            idle.append(name)
        else:
            verdict = "PASS"
        print(f"--- {name}: {verdict} in {elapsed:.0f}s; full log: {log}")
        print("\n".join("    " + ln for ln in tail))
    outcome = []
    if failed:
        outcome.append("FAILED in " + ", ".join(failed))
    if idle:
        outcome.append("RAN NOTHING in " + ", ".join(idle))
    print(f"\n=== affected tests: {'; '.join(outcome) or 'all passed'} ===")
    return 1 if outcome else 0


def _tolerant_output() -> None:
    """Let stdout / stderr replace what their code page cannot encode.

    A child's log is read back as UTF-8 and its tail printed here, and a
    banner's box drawing ('\\u2551') on a cp1252 console or redirect raised
    UnicodeEncodeError mid-run: the runner died and the packages after the
    one it was printing never ran."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):  # not a TextIOWrapper; leave it
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _tolerant_output()
    parser = argparse.ArgumentParser(
        description="Select (and run) the tests a change reaches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:", 1)[1] if "Usage:" in __doc__ else None,
    )
    parser.add_argument("paths", nargs="*", help="changed files (default: dirty files touched within --since)")
    parser.add_argument("--since", type=_duration, default=None, help="with no paths: window, e.g. 45m, 3h (default 3h)")
    parser.add_argument("--run", action="store_true", help="run the selection (sequential, headless, no badge)")
    parser.add_argument("-k", dest="k", default=None, help="test-name filter passed to every runner that has one")
    parser.add_argument("--downstream", action="store_true", help="also select dependent packages' tests")
    parser.add_argument("--no-gui", action="store_true", help="never start a GUI host (tentacle runs plain; Maya-hosted tests skip, "
                             "and a run of only those reads RAN NOTHING)")
    parser.add_argument("--explain", action="store_true", help="say why each module was selected")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]
    if not paths:
        window = args.since if args.since is not None else 3 * 3600
        paths = recent_dirty(window)
        if not paths:
            print("No dirty file was touched in that window; pass the changed files.")
            return 2
        shown = [p.relative_to(WORKSPACE).as_posix() for p in paths]
        print(f"Changed (dirty, touched in the last {window / 3600:.1f} h): " + ", ".join(shown[:30])
              + (f" +{len(shown) - 30} more" if len(shown) > 30 else ""))
    elif args.since is not None:
        parser.error("--since applies only when no paths are given")

    sel = select(paths, downstream=args.downstream)
    cmds = commands(sel, k=args.k, gui=not args.no_gui)
    print(report(sel, cmds, args.explain, k=args.k))
    if not args.run or not cmds:
        return 0
    return run(cmds)


if __name__ == "__main__":
    sys.exit(main())
