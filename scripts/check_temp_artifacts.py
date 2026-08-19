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

``tempfile.gettempdir()`` is NOT flagged on its own -- it is also how code names a
stable, deliberately durable location (a bridge output folder the user opens, an
icon cache). Only the *allocating* calls are flagged, because those are the ones
that mint a new artifact nobody is tracking.

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
}

# Allocations with NO automatic reclamation. gettempdir() is intentionally absent
# (see the docstring), and so are the self-cleaning forms:
#
#   * ``TemporaryDirectory()``      -- removes its tree on context exit / finalize
#   * ``NamedTemporaryFile()``      -- removes on close (delete=True is the default)
#
# Those already guarantee what this gate is for. ``NamedTemporaryFile(delete=False)``
# opts OUT of that guarantee, so it is flagged like a raw mkstemp.
ALWAYS_FLAGGED = {("tempfile", "mkstemp"), ("tempfile", "mkdtemp")}
FLAGGED_WHEN_DELETE_FALSE = {("tempfile", "NamedTemporaryFile")}

# Justified exceptions: "<repo-relative path>::<function>" -> reason.
# Keep this list SHORT and each entry argued. A growing allowlist means the
# primitive is missing a capability -- add it there instead.
ALLOWLIST: Dict[str, str] = {
    "pythontk/pythontk/file_utils/temp_artifacts.py::*": (
        "the primitive itself -- it is what everything else routes through"
    ),
    "pythontk/pythontk/file_utils/_file_utils.py::atomic_write_text": (
        "atomic replace: the temp file is created in the DESTINATION directory "
        "(not the temp dir) and is os.replace'd onto the target in a finally, so "
        "it is consumed rather than left behind"
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

# Justified strays: "<repo-relative path>" -> reason. Same discipline as ALLOWLIST
# above -- if this grows, the file probably wants declaring, not excusing.
STRAY_ALLOWLIST: Dict[str, str] = {}


class _Visitor(ast.NodeVisitor):
    """Collect flagged allocation calls with their enclosing function name.

    Import-alias aware. Matching only ``tempfile.mkdtemp`` as written would let
    two ordinary spellings through -- ``from tempfile import mkdtemp`` and
    ``import tempfile as tf`` -- and a gate that a plain refactor can silently
    defeat is worse than none, because it reads as proof of compliance.
    """

    def __init__(self) -> None:
        self.stack: List[str] = []
        self.found: List[Tuple[int, str, str]] = []  # (line, call, function)
        # local name -> "tempfile"            (import tempfile [as tf])
        self.module_aliases: Dict[str, str] = {}
        # local name -> ("tempfile", "mkdtemp")  (from tempfile import mkdtemp [as m])
        self.func_aliases: Dict[str, Tuple[str, str]] = {}

    def visit_Import(self, node) -> None:
        for alias in node.names:
            if alias.name == "tempfile":
                self.module_aliases[alias.asname or alias.name] = "tempfile"
        self.generic_visit(node)

    def visit_ImportFrom(self, node) -> None:
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

    def visit_Call(self, node) -> None:
        resolved = self._resolve(node.func)
        if resolved is not None:
            key, label = resolved
            if key in ALWAYS_FLAGGED or (
                key in FLAGGED_WHEN_DELETE_FALSE and self._opts_out_of_autodelete(node)
            ):
                if key in FLAGGED_WHEN_DELETE_FALSE:
                    label += "(delete=False)"
                self.found.append(
                    (node.lineno, label, self.stack[-1] if self.stack else "<module>")
                )
        self.generic_visit(node)


def _allowed(rel: str, function: str) -> bool:
    rel = rel.replace(os.sep, "/")
    return f"{rel}::*" in ALLOWLIST or f"{rel}::{function}" in ALLOWLIST


def scan(packages: List[str]) -> List[str]:
    """Return one violation line per unallowed allocation."""
    violations: List[str] = []
    for pkg in packages:
        root = os.path.join(REPO, PACKAGES[pkg])
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, REPO).replace(os.sep, "/")
                try:
                    with open(full, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read())
                except (OSError, SyntaxError):
                    continue  # templates carry __TOKEN__ placeholders
                visitor = _Visitor()
                visitor.visit(tree)
                for line, call, function in visitor.found:
                    if _allowed(rel, function):
                        continue
                    violations.append(f"{rel}:{line}  {call}()  in {function}()")
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
                    if rel in STRAY_ALLOWLIST:
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
            if rel in STRAY_ALLOWLIST:
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

    if not violations and not strays:
        print(
            f"OK: no unmanaged temp allocations or stray artifacts in "
            f"{len(packages)} package(s)."
        )
        return 0

    if violations:
        print(f"FAIL: {len(violations)} unmanaged temp allocation(s):")
        print("")
        for v in violations:
            print(f"  {v}")
        print(
            "\nRoute these through pythontk.TempArtifacts so an abandoned artifact is\n"
            "still reclaimed by a later run's age-gated sweep:\n"
            '    path = ptk.TempArtifacts("prefix").path(extension=".ext")\n'
            '    work = ptk.TempArtifacts("prefix").dir_path()\n'
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
