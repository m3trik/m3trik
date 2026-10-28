# !/usr/bin/python
# coding=utf-8
"""Fail on unowned artifacts: unmanaged temp allocations, and stray files in a package.

Two halves, one defect -- an artifact nobody is responsible for. The first half
reads code that *mints* one; the second walks the tree for one that is simply
lying there.

Why this gate exists
--------------------
A raw ``tempfile.mkstemp`` / ``mkdtemp`` / ``NamedTemporaryFile(delete=False)`` has
no owner. If the ``finally`` is forgotten, an exception escapes it, or the process
dies (a DCC crash is routine in this ecosystem), the artifact leaks with nothing
left to reclaim it. Auditing this by hand does not hold: the leaks found when this
script was written were all in code that *looked* fine, and several wrote a file
whose success path simply never deleted anything.

``pythontk.TempArtifacts`` is the one home for the pattern. Every allocation joins a
prefix namespace that a later run sweeps by age, so the worst case is delayed
collection rather than a permanent leak::

    path = ptk.TempArtifacts("my_prefix").path(extension=".fbx")   # a file
    work = ptk.TempArtifacts("my_prefix").dir_path()               # a directory

The AST half cannot see an artifact with no code behind it: a ``cProfile -o prof``
dump written into the package directory, a hand-made ``.bak``, an experiment saved
next to the module it was testing. Nothing imports them and no wheel ships them,
so they are residue by definition -- and a ``.gitignore`` entry only hides them.
The second half finds those by walking the package tree instead.

Scope
-----
Production source only. Tests are exempt: a test harness owns its own teardown and
is not what leaks on a user's machine.

Naming the system temp folder is flagged too, outside pythontk: a
``tempfile.gettempdir()`` call or a read of ``TEMP`` / ``TMP`` / ``TMPDIR`` from the
environment. ``TempArtifacts.root()`` is the one spelling of "temp" -- it honours
``PYTHONTK_TEMP_ROOT``, a test sandbox and the store sweep, and a hand-joined
``<gettempdir>/<name>`` folder escapes all three. A durable location wants
``ptk.UserConfig.cache_dir()`` or the scene's ``ptk.Workspace`` instead. Setting
``TEMP`` for a child process (a store) is not a read and is not flagged. A string
that spells the variable for later expansion (``"${TEMP}/x"``, ``"%TEMP%"``) is
flagged too; docstrings are not.

An allowlist entry that no longer matches anything is reported as stale, so the
list cannot outlive the code it excused. A file that does not parse is reported
rather than skipped: an unscanned file is not a clean one.

Usage
-----
    python m3trik/scripts/check_temp_artifacts.py            # all packages
    python m3trik/scripts/check_temp_artifacts.py mayatk     # one package
    python m3trik/scripts/check_temp_artifacts.py --list     # show allowlists

Exit code 0 = clean, 1 = an unallowed allocation or a stray artifact was found.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Package -> source subdirectory scanned. Tests are deliberately excluded.
# Only OUR source. comfyui/app and comfyui/venv are the vendored upstream
# application -- scanning them reports dozens of hits in code we do not own and
# cannot fix, which is exactly how a gate gets ignored.
PACKAGES: Dict[str, str] = {
    "pythontk": "pythontk/pythontk",
    "uitk": "uitk/uitk",
    "mayatk": "mayatk/mayatk",
    "blendertk": "blendertk/blendertk",
    "tentacle": "tentacle/tentacle",
    "unitytk": "unitytk/unitytk",
    "extapps": "extapps/extapps",
    "comfyui": "comfyui/comfyui",
    "comfyui-src": "comfyui/src",
    "androidtk": "androidtk/androidtk",
    "m3trik-scripts": "m3trik/scripts",
}

# Packages allowed to NAME the system temp folder: the owner of TempArtifacts.
TEMP_OWNERS = {"pythontk"}

# Allocations with NO automatic reclamation. The self-cleaning forms are absent:
#
#   * ``TemporaryDirectory()``      -- removes its tree on context exit / finalize
#   * ``NamedTemporaryFile()``      -- removes on close (delete=True is the default)
#
# Those already guarantee what this gate is for. ``NamedTemporaryFile(delete=False)``
# opts OUT of that guarantee, so it is flagged like a raw mkstemp.
ALWAYS_FLAGGED = {("tempfile", "mkstemp"), ("tempfile", "mkdtemp")}
FLAGGED_WHEN_DELETE_FALSE = {("tempfile", "NamedTemporaryFile")}
# Naming the system temp folder (flagged outside TEMP_OWNERS).
NAMING_CALLS = {("tempfile", "gettempdir"), ("tempfile", "gettempdirb")}
TEMP_ENV_VARS = {"TEMP", "TMP", "TMPDIR"}  # compared upper-case (Windows ignores case)
# A temp variable spelled for later expansion: %TEMP% (any case, as Windows
# reads it), $TMP / ${TMPDIR} (case-sensitive, as POSIX reads it -- a MEL `$tmp`
# is a local variable, not the environment).
TEMP_TOKEN = re.compile(r"(?i:%(?:TEMP|TMP)%)|\$\{?(?:TEMP|TMPDIR|TMP)\b\}?")

# Justified exceptions: "<repo-relative path>::<function>" -> reason.
# Keep this list SHORT and each entry argued. A growing allowlist means the
# primitive is missing a capability -- add it there instead.
ALLOWLIST: Dict[str, str] = {
    "blendertk/blendertk/env_utils/_env_utils.py::get_recent_autosave": (
        "names BLENDER's autosave folder (its documented OS-temp fallback when "
        "the preference is empty) -- reads Blender's files, writes nothing"
    ),
    "blendertk/blendertk/env_utils/_env_utils.py::scene_status": (
        "the HUD's autosave-folder test, the same as get_recent_autosave; read-only"
    ),
    "mayatk/mayatk/mat_utils/texture_baker.py::_exr_trouble": (
        "names OPENCV's own temp folder in a diagnostic message (cv2 resolves it "
        "from the OS, not from TempArtifacts); allocates nothing"
    ),
}

# Directories skipped anywhere in the walk.
SKIP_DIRS = {
    "test",
    "tests",
    "temp_tests",
    "build",
    "dist",
    "__pycache__",
    ".git",
    ".venv",
    ".archive",
    "node_modules",
    "site-packages",
}

# A file inside an importable package is legitimate only if Python loads it
# (.py/.pyi/py.typed) or the package DECLARES it as shipped data. Declaration is
# the right yardstick because it is already load-bearing: an undeclared file is
# absent from the wheel, so it cannot be something the installed package needs.
# That also makes the check self-maintaining -- a new data type has to be declared
# for the wheel anyway, and declaring it satisfies this gate for free. Packages
# declaring nothing at all are skipped: with no contract there is nothing to
# check against, and inventing one produces noise, not findings.
LOADED_SUFFIXES = (".py", ".pyi")
LOADED_NAMES = {"py.typed"}

# Extension-less files at a package repo ROOT. Each is a sentinel some tool looks
# up by exact name. Anything else with no extension there is almost always a
# mistyped output path -- `-o prof` run one directory up lands exactly here.
ROOT_SENTINELS = {
    "LICENSE",
    "LICENCE",
    "COPYING",
    "NOTICE",
    "AUTHORS",
    "Makefile",
    "Dockerfile",
    "CODEOWNERS",
    "Procfile",
}

# Justified strays: "<repo-relative path>" -> reason; a key ending in "/" excuses
# the tree under it. Same discipline as ALLOWLIST above -- if this grows, the file
# probably wants declaring, not excusing.
STRAY_ALLOWLIST: Dict[str, str] = {
    "androidtk/androidtk/bin/platform-tools/": (
        "Google's platform-tools, downloaded at runtime by "
        "install_tools.install_platform_tools (gitignored); adb.py / fastboot.py "
        "resolve the binaries beside the package"
    ),
}


def _stray_allowed(rel: str) -> bool:
    return rel in STRAY_ALLOWLIST or any(
        key.endswith("/") and rel.startswith(key) for key in STRAY_ALLOWLIST
    )


# --------------------------------------------------------------- workspace root
#
# The workspace root is not itself a git repo, so no repo's .gitignore covers it
# and no CI checkout can ever contain it -- it is the one place in the tree with
# no gate at all. Measured 2026-09-16 it held 132 MB of residue: a
# ``pythontk.zip`` full repo snapshot (including .git, every commit of which was
# already in the live checkout) and a 66 KB copy of mayatk's ``mat_updater.py``
# that had drifted 179 lines behind its source.
#
# Opt-in via ``--workspace-root`` rather than on by default: this scan is
# meaningful only where the whole monorepo is checked out side by side, which is
# a developer machine and push.ps1's Prepare phase, never a CI runner. Left on
# by default it would fail every CI invocation for the wrong reason.
#
# The directory rule is POSITIVE and self-maintaining: a directory holding a
# ``.git`` is a repo checkout and belongs, so adding a repo needs no edit here.
# The alternative -- a hardcoded roster of the twelve current repos -- is
# precisely the stable-path edit the ecosystem's own design rules exist to
# avoid.
WORKSPACE_DIRS_ALLOWED = {
    ".git",
    ".claude",  # agent ledgers, hooks, settings
    ".github",  # workspace-level agent/skill config (not a repo's CI)
    ".vscode",
    ".archive",  # DOCS_STANDARD.md: completed one-shot reports are parked here
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
}

WORKSPACE_FILES_ALLOWED: Dict[str, str] = {
    "CLAUDE.md": "monorepo instruction file; root of the dispatch table",
    "_residue_archive_2026-09-16.zip": (
        "one-time recoverable holding the 34 files removed by the 2026-09-16 "
        "residue sweep. DELETE it once the contents are confirmed unwanted, "
        "and drop this entry with it -- it is a receipt, not a fixture."
    ),
}


def scan_workspace_root() -> List[str]:
    """Flag anything at the workspace root that is neither a repo nor allowed.

    Returns:
        A list of human-readable violation strings, empty when clean.
    """
    violations: List[str] = []
    try:
        entries = sorted(os.listdir(REPO))
    except OSError:
        return violations
    for name in entries:
        full = os.path.join(REPO, name)
        if os.path.isdir(full):
            if name in WORKSPACE_DIRS_ALLOWED or os.path.isdir(
                os.path.join(full, ".git")
            ):
                continue
            violations.append(f"{name}/  (workspace root; not a repo checkout)")
        elif os.path.isfile(full):
            if name in WORKSPACE_FILES_ALLOWED:
                continue
            size = os.path.getsize(full)
            violations.append(
                f"{name}  (workspace root; {size:,} B, outside every repo)"
            )
    return violations


class _Visitor(ast.NodeVisitor):
    """Collect flagged allocation calls with their enclosing function name.

    Import-alias aware. Matching only ``tempfile.mkdtemp`` as written would let
    two ordinary spellings through -- ``from tempfile import mkdtemp`` and
    ``import tempfile as tf`` -- and a gate that a plain refactor can silently
    defeat is worse than none, because it reads as proof of compliance.
    """

    def __init__(self, flag_naming: bool = False) -> None:
        self.flag_naming = flag_naming
        self.stack: List[str] = []
        self.found: List[Tuple[int, str, str]] = []  # (line, call, function)
        # local name -> "tempfile"            (import tempfile [as tf])
        self.module_aliases: Dict[str, str] = {}
        # local name -> ("tempfile", "mkdtemp")  (from tempfile import mkdtemp [as m])
        self.func_aliases: Dict[str, Tuple[str, str]] = {}

    def visit_Import(self, node) -> None:
        for alias in node.names:
            if alias.name in ("tempfile", "os"):
                self.module_aliases[alias.asname or alias.name] = alias.name
            elif alias.name.startswith("os.") and not alias.asname:
                self.module_aliases["os"] = "os"  # `import os.path` binds `os`
        self.generic_visit(node)

    def visit_ImportFrom(self, node) -> None:
        if node.module == "os":
            for alias in node.names:
                if alias.name in ("environ", "getenv"):
                    self.func_aliases[alias.asname or alias.name] = ("os", alias.name)
        if node.module == "tempfile":
            for alias in node.names:
                self.func_aliases[alias.asname or alias.name] = (
                    "tempfile",
                    alias.name,
                )
        self.generic_visit(node)

    def _visit_scope(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope

    @staticmethod
    def _opts_out_of_autodelete(node) -> bool:
        """True for ``NamedTemporaryFile(delete=False)`` -- the leaking form."""
        for kw in node.keywords:
            if kw.arg == "delete":
                return not (isinstance(kw.value, ast.Constant) and kw.value.value)
        return False

    def _resolve(self, func) -> Optional[Tuple[Tuple[str, str], str]]:
        """``(canonical key, as-written label)`` for a call, or None."""
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = self.module_aliases.get(func.value.id)
            if module:
                return (module, func.attr), f"{func.value.id}.{func.attr}"
        elif isinstance(func, ast.Name):
            key = self.func_aliases.get(func.id)
            if key:
                return key, func.id
        return None

    def _record(self, node, label: str) -> None:
        self.found.append(
            (node.lineno, label, self.stack[-1] if self.stack else "<module>")
        )

    def _is_environ(self, node) -> bool:
        """True for an expression spelling ``os.environ`` (any alias)."""
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return (
                self.module_aliases.get(node.value.id) == "os"
                and node.attr == "environ"
            )
        return isinstance(node, ast.Name) and self.func_aliases.get(node.id) == (
            "os",
            "environ",
        )

    @staticmethod
    def _temp_var(node) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.upper() in TEMP_ENV_VARS:
                return node.value
        return None

    def visit_Expr(self, node) -> None:
        """A bare string statement is a docstring: prose, never scanned."""
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return
        self.generic_visit(node)

    def visit_Constant(self, node) -> None:
        """A string spelling a temp variable for later expansion."""
        if (
            self.flag_naming
            and isinstance(node.value, str)
            and TEMP_TOKEN.search(node.value)
        ):
            self._record(node, f"{TEMP_TOKEN.search(node.value).group(0)!r} token")

    def visit_Subscript(self, node) -> None:
        """An ``os.environ["TEMP"]`` read (a store sets a child's temp: allowed)."""
        if self.flag_naming and isinstance(node.ctx, ast.Load):
            var = self._temp_var(node.slice)
            if var and self._is_environ(node.value):
                self._record(node, f'os.environ["{var}"]')
        self.generic_visit(node)

    def _env_read(self, node) -> Optional[str]:
        """Label for ``os.environ.get|setdefault|pop("TEMP")`` / ``os.getenv("TMP")``
        (positional or ``key=``), or None."""
        first = node.args[0] if node.args else None
        if first is None:
            first = next((kw.value for kw in node.keywords if kw.arg == "key"), None)
        var = self._temp_var(first)
        if not var:
            return None
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("get", "setdefault", "pop")
            and self._is_environ(func.value)
        ):
            return f'os.environ.{func.attr}("{var}")'
        resolved = self._resolve(func)
        if resolved is not None and resolved[0] == ("os", "getenv"):
            return f'os.getenv("{var}")'
        return None

    def visit_Call(self, node) -> None:
        if self.flag_naming:
            env = self._env_read(node)
            if env:
                self._record(node, env)
        resolved = self._resolve(node.func)
        if resolved is not None:
            key, label = resolved
            if self.flag_naming and key in NAMING_CALLS:
                self._record(node, f"{label}()")
            elif key in ALWAYS_FLAGGED or (
                key in FLAGGED_WHEN_DELETE_FALSE and self._opts_out_of_autodelete(node)
            ):
                label = (
                    f"{label}(delete=False)"
                    if key in FLAGGED_WHEN_DELETE_FALSE
                    else f"{label}()"
                )
                self._record(node, label)
        self.generic_visit(node)


def _allowed(rel: str, function: str, used: Optional[set] = None) -> bool:
    rel = rel.replace(os.sep, "/")
    for key in (f"{rel}::*", f"{rel}::{function}"):
        if key in ALLOWLIST:
            if used is not None:
                used.add(key)
            return True
    return False


def scan(packages: List[str]) -> List[str]:
    """Return one violation line per unallowed allocation or temp naming, per
    unscannable file, and per stale allowlist entry.

    An entry is stale when its file sits under a scanned package present on disk
    and nothing in it matched -- a package a CI runner never checked out is
    never judged.
    """
    violations: List[str] = []
    used: set = set()
    scanned_roots: List[str] = []
    for pkg in packages:
        root = os.path.join(REPO, PACKAGES[pkg])
        if not os.path.isdir(root):
            continue
        scanned_roots.append(PACKAGES[pkg].replace(os.sep, "/").rstrip("/") + "/")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, REPO).replace(os.sep, "/")
                try:
                    # Bytes, so ast honours a BOM and a `# coding:` line as
                    # Python does (PS 5.1's Out-File writes a BOM).
                    with open(full, "rb") as fh:
                        tree = ast.parse(fh.read())
                except (OSError, SyntaxError, ValueError) as exc:
                    # Exec templates' __TOKEN__ placeholders are plain names and
                    # parse; a file that does not is unscanned, not clean.
                    violations.append(f"{rel}  could not be scanned ({exc})")
                    continue
                visitor = _Visitor(flag_naming=pkg not in TEMP_OWNERS)
                visitor.visit(tree)
                for line, call, function in visitor.found:
                    if _allowed(rel, function, used):
                        continue
                    violations.append(f"{rel}:{line}  {call}  in {function}()")
    for key in sorted(ALLOWLIST):
        path = key.split("::", 1)[0]
        if key in used or not any(path.startswith(r) for r in scanned_roots):
            continue
        violations.append(f"{key}  stale ALLOWLIST entry (nothing matches it)")
    return violations


def _shipped_globs(package_dir: str) -> List[Tuple[str, str]]:
    """Return (subtree, glob) pairs the owning project declares as shipped data.

    Both declaration sites count, because either one alone is incomplete: wheels
    are built from ``[tool.setuptools.package-data]``, sdists from ``MANIFEST.in``,
    and setuptools folds the manifest into the wheel when ``include-package-data``
    is on (the default for a pyproject build). Reading only one would flag files
    that genuinely ship -- uitk's icons are declared solely in its manifest.

    ``subtree`` is the package-relative directory the glob applies under, so a
    ``recursive-include`` aimed at one subdirectory does not whitelist the tree.
    """
    repo_dir = os.path.dirname(package_dir)
    pkg_name = os.path.basename(package_dir)
    pairs: List[Tuple[str, str]] = []

    pyproject = os.path.join(repo_dir, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            import tomllib

            with open(pyproject, "rb") as fh:
                data = tomllib.load(fh)
            package_data = (
                data.get("tool", {}).get("setuptools", {}).get("package-data", {})
            )
            for globs in package_data.values():
                pairs += [("", g) for g in globs]
        except (OSError, ImportError, ValueError):
            pass  # unreadable/old interpreter: fall back to the manifest alone

    manifest = os.path.join(repo_dir, "MANIFEST.in")
    if os.path.isfile(manifest):
        try:
            with open(manifest, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            lines = []
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            command, rest = parts[0], parts[1:]
            if command == "global-include":
                pairs += [("", g) for g in rest]
            elif command in ("recursive-include", "graft") and rest:
                target = rest[0].replace("\\", "/").strip("/")
                if target != pkg_name and not target.startswith(pkg_name + "/"):
                    continue  # aimed outside the package (docs/, examples/)
                subtree = target[len(pkg_name) :].strip("/")
                globs = rest[1:] if command == "recursive-include" else ["*"]
                pairs += [(subtree, g) for g in globs or ["*"]]
    return pairs


def _is_declared(rel_to_pkg: str, pairs: List[Tuple[str, str]]) -> bool:
    name = os.path.basename(rel_to_pkg)
    for subtree, glob in pairs:
        if subtree and not rel_to_pkg.startswith(subtree + "/"):
            continue
        if fnmatch.fnmatch(name, glob):
            return True
    return False


def scan_strays(packages: List[str]) -> List[str]:
    """Return one violation line per file that nothing loads, ships, or excuses."""
    violations: List[str] = []
    swept_roots: set = set()

    for pkg in packages:
        root = os.path.join(REPO, PACKAGES[pkg])
        if not os.path.isdir(root):
            continue

        pairs = _shipped_globs(root)
        if pairs:  # no declaration -> no contract -> nothing to check against
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for filename in filenames:
                    if filename.endswith(LOADED_SUFFIXES) or filename in LOADED_NAMES:
                        continue
                    full = os.path.join(dirpath, filename)
                    rel_to_pkg = os.path.relpath(full, root).replace(os.sep, "/")
                    if _is_declared(rel_to_pkg, pairs):
                        continue
                    rel = os.path.relpath(full, REPO).replace(os.sep, "/")
                    if _stray_allowed(rel):
                        continue
                    violations.append(
                        f"{rel}  (inside the package; not loaded, not shipped)"
                    )

        # Repo root, once per repo -- several packages can share one (comfyui).
        repo_dir = os.path.dirname(root)
        if repo_dir in swept_roots:
            continue
        swept_roots.add(repo_dir)
        try:
            entries = sorted(os.listdir(repo_dir))
        except OSError:
            continue
        for name in entries:
            full = os.path.join(repo_dir, name)
            if "." in name or name in ROOT_SENTINELS or not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, REPO).replace(os.sep, "/")
            if _stray_allowed(rel):
                continue
            violations.append(f"{rel}  (repo root; no extension, not a known sentinel)")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # No argparse `choices`: with nargs="*" it validates the default list too and
    # rejects the no-argument (scan-everything) form.
    parser.add_argument(
        "packages",
        nargs="*",
        help=f"packages to scan (default: all of {list(PACKAGES)})",
    )
    parser.add_argument("--list", action="store_true", help="print the allowlist")
    parser.add_argument(
        "--workspace-root",
        action="store_true",
        help=(
            "also sweep the workspace root for files and non-repo directories "
            "(local / push.ps1 only -- a CI runner has no workspace root)"
        ),
    )
    args = parser.parse_args()

    unknown = [p for p in args.packages if p not in PACKAGES]
    if unknown:
        parser.error(f"unknown package(s) {unknown}; expected any of {list(PACKAGES)}")

    if args.list:
        print("Allowlisted raw temp allocations:")
        for key, reason in sorted(ALLOWLIST.items()):
            print(f"  {key}\n      {reason}")
        print("")
        print("Allowlisted stray artifacts:")
        for key, reason in sorted(STRAY_ALLOWLIST.items()):
            print(f"  {key}")
            print(f"      {reason}")
        if not STRAY_ALLOWLIST:
            print("  (none)")
        return 0

    packages = args.packages or list(PACKAGES)
    violations = scan(packages)
    strays = scan_strays(packages)
    root_strays = scan_workspace_root() if args.workspace_root else []

    if not violations and not strays and not root_strays:
        print(
            f"OK: no unmanaged temp allocations or stray artifacts in "
            f"{len(packages)} package(s)."
            + (" Workspace root clean." if args.workspace_root else "")
        )
        return 0

    if violations:
        print(f"FAIL: {len(violations)} unmanaged temp allocation(s) / naming(s):")
        print("")
        for v in violations:
            print(f"  {v}")
        print(
            "\nRoute these through pythontk.TempArtifacts so an abandoned artifact is\n"
            "still reclaimed by a later run's age-gated sweep:\n"
            '    path = ptk.TempArtifacts("prefix").path(extension=".ext")\n'
            '    work = ptk.TempArtifacts("prefix").dir_path()\n'
            "A folder joined onto gettempdir()/TEMP wants TempArtifacts.root() (or\n"
            "UserConfig.cache_dir() / the scene Workspace when it must persist).\n"
            "Policies: scoped (delete on clean exit, keep on failure), session\n"
            "(delete at interpreter exit), detached (default -- the consumer outlives\n"
            "us; stale ones are swept).\n"
            "If a site genuinely cannot use it, add it to ALLOWLIST with a reason."
        )

    if strays:
        if violations:
            print("")
        print(f"FAIL: {len(strays)} stray artifact(s):")
        print("")
        for s in strays:
            print(f"  {s}")
        print(
            """
Nothing imports or ships these, so they are residue -- a profile dump, a .bak,
an experiment saved beside the module it was testing. Delete them. Scratch
belongs in test/temp_tests/ (gitignored, swept when done), so give the tool that
wrote it an explicit destination there rather than a bare -o:
    python -m cProfile -o test/temp_tests/<name>.prof -m <module>
If a file genuinely belongs, DECLARE it (pyproject package-data / MANIFEST.in)
so the wheel actually ships it -- an undeclared data file is simply missing at
runtime for every installed user. Last resort: STRAY_ALLOWLIST."""
        )

    if root_strays:
        if violations or strays:
            print("")
        print(f"FAIL: {len(root_strays)} workspace-root artifact(s):")
        print("")
        for s in root_strays:
            print(f"  {s}")
        print(
            """
The workspace root sits outside every git repo, so nothing else sees these --
not a .gitignore, not a repo's CI, not `git status`. That is exactly how a 132 MB
snapshot and a drifted module copy survived there unnoticed until 2026-09-16.
Delete them, or move them into the repo that owns them. A directory belongs here
only if it is a repo checkout (it holds a .git); a file belongs only if it is in
WORKSPACE_FILES_ALLOWED with a reason."""
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
