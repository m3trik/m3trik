"""Check the ecosystem packages' public API against its rules, from source.

Nothing is written: the surface is read live (``pythontk.ApiSurface.read``:
``ast``, nothing imported), so no generated API file is committed. Agents and
people search it with ``api.search`` (MCP ``api_search``, ``python -m pythontk
ops search``) before writing a helper.

Usage:
    python check_api_surface.py --check            # every package: the gate
    python check_api_surface.py uitk --check       # one package (its own CI)
    python check_api_surface.py mayatk --semver    # JSON for push.ps1's semver
                                                   # gate ('minor' when the delta
                                                   # removes a public symbol)
    python check_api_surface.py mayatk --changes   # the delta since the last
                                                   # release, and retirement debt
    python check_api_surface.py --shadows          # names two packages define
    python check_api_surface.py mayatk --semver --since v0.30.0   # another baseline

``--check`` fails on a retirement past its window: a ``ptk.Deprecation`` alias
or retired keyword whose ``remove_in`` the package's ``__version__`` has
reached and whose calendar window (``since``) has closed. It reads source alone
(no install, no git history), so a per-package CI checkout of the package, this
repo and pythontk runs it -- pythontk does the reading (this module puts the
sibling first on ``sys.path``), so that sibling is a hard requirement.

The delta (``--semver``, ``--changes``) is read against the package's last
release: its newest ``v*`` tag (push.ps1 tags each release ``v<version>``),
read through ``ApiSurface.read`` from a ``git archive`` copy of the tag's
source. A removal is accounted for by a ``ptk.Deprecation`` alias (it retires)
or a ``MOVED_NAMES`` entry (it moved to another package); one that is neither
is a break push.ps1 refuses. With no baseline (no tag, or a ``--since`` naming
no commit) there is no verdict: ``--semver`` says so and exits 2, and
``--changes`` says there is no release to compare with.

A package that declares C# (``CSHARP_SOURCES`` in its root ``__init__.py``:
unitytk) is read and judged twice, with the same reader and the same rules:
its Python, then its C# (``ApiSurface.read_csharp``: a module per namespace,
keys ``Namespace::Type.Member``). A removed public C# name is a break unless
a ``MOVED_NAMES`` row (its name or full name) or an ``[Obsolete]`` forwarder
in the release accounts for it; an ``[Obsolete]`` naming the release it goes
in is held to the window a ``Deprecation`` is. Overloads of a name are one
key, their signatures joined: one added or dropped while the name stays is a
changed signature, never a removal.

Design notes:
  * It walks <pkg>/<pkg>/ only: top-level functions, classes and ALL_CAPS
    constants whose names do not start with `_`, the classes' public members,
    those inherited from private bases included; and the C# folder the
    package declares.
  * A member hoisted to a base, or a class re-exported from its old home, is
    moved, not removed (:func:`compute_api_delta`).
  * Adopted, not built (CODE_STANDARD section 15): the release is read by the
    ``ApiSurface`` that answers ``api.search``, from a ``git archive`` of its
    tag's ``.py`` files -- griffe's ``check`` would be a second reader with
    its own rules and no ``MOVED_NAMES`` / ``Deprecation`` accounting, the
    published wheel needs the network and an install per package, and a
    ``git worktree`` writes a whole checkout where the sources suffice.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import datetime
import functools
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]


# The reading is pythontk's: the sibling checkout first on sys.path, so this
# repo's checks always read with the pythontk it ships beside (never an older
# installed one). pythontk's root imports nothing until a name is used.
sys.path.insert(0, str(REPO_ROOT / "pythontk"))
from pythontk import ApiSurface, PackageSurface, TempArtifacts  # noqa: E402


def _load_version_key():
    """Load ``Deprecation.version_key`` from pythontk source, as above.

    The expiry gate and the runtime roster must agree on what a removal version
    IS; a second parser here would be free to drift into accepting something
    the other rejects, and the failure mode of that drift is an alias that
    never expires -- the exact bug the gate exists to catch. So when the
    sibling cannot supply one, this does NOT fall back to a local parser.

    A pythontk checkout predating ``core_utils/deprecation.py`` is a real and
    ROUTINE state, not a broken one: ``m3trik/AGENTS.md`` requires this repo to
    reach main BEFORE the packages land their side of a cross-repo change, so
    between those two pushes every sibling is a pythontk without the module --
    and this import runs at module scope, where a raise takes down the whole
    script, which every package's PR runs as ``--check``. Measured
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
            f"[api-surface] NOTE: {path} is absent (a pythontk predating "
            "ptk.Deprecation), so the deprecation EXPIRY GATE is inactive for "
            "this run; an overdue alias will not be reported until the "
            "sibling carries the module.",
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


def _load_window_rule():
    """``(Deprecation.window_expired, Deprecation.MIN_WINDOW_DAYS)`` from the
    module :func:`_load_version_key` just loaded -- the calendar half of the
    expiry rule, from the same source for the same reason: the static gate and
    the runtime roster must not be able to disagree about when a name is due.

    A pythontk sibling predating the calendar window (``since``) has neither:
    then a retirement is due by version alone, which is exactly what that
    sibling's own roster says -- the version comparison is still
    :func:`_version_key`'s, so this adds no second parser.
    """
    module = sys.modules.get("_ptk_deprecation")
    owner = getattr(module, "Deprecation", None)
    rule = getattr(owner, "window_expired", None)
    if rule is not None:
        return rule, int(getattr(owner, "MIN_WINDOW_DAYS", 0))

    def version_only(remove_in, version, since="", today=None):
        return _version_key(version) >= _version_key(remove_in)

    return version_only, 0


_window_expired, _MIN_WINDOW_DAYS = _load_window_rule()

#: ``__version__ = "1.2.3"`` in a package root, read with a regex rather than an
#: import: this script runs on a bare CI box where the package it is walking
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


def deprecations(pkg: PackageSurface) -> list[tuple[str, str, str, str]]:
    """Every retired symbol in *pkg* as ``(relpath, qualname, remove_in, since)``.

    *since* is the date the notice first shipped (``""`` when it names none),
    read off the decorator by the walk (:func:`_stamp_since`) -- carried beside
    the record rather than in it (a value, never a field).
    Sorted by removal version so the oldest debt reads first.
    """
    found: list[tuple[str, str, str, str]] = []

    def row(relpath: str, qualname: str, symbol) -> tuple[str, str, str, str]:
        return (relpath, qualname, symbol.remove_in, getattr(symbol, "since", ""))

    for mod in pkg.modules:
        for fn in mod.functions:
            if fn.deprecated:
                found.append(row(mod.relpath, fn.qualname, fn))
        for cls in mod.classes:
            if cls.deprecated:
                found.append(row(mod.relpath, cls.name, cls))
            for member in cls.members:
                if member.deprecated:
                    found.append(row(mod.relpath, member.qualname, member))

    def order(row: tuple[str, str, str, str]) -> tuple:
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


def expired_deprecations(
    pkg: PackageSurface, version: str, today: datetime.date | None = None
) -> list[tuple[str, str, str, str]]:
    """Retired symbols past their window: *version* has reached their removal
    release AND, where they name ``since``, the calendar window has closed.

    An empty *version*, or a symbol with no ``remove_in``, can never expire --
    both are reported by :func:`deprecations` instead, where they read as debt
    rather than as a passing gate.
    """
    return _expired(deprecations(pkg), version, today)


def _expired(rows, version: str, today: datetime.date | None = None) -> list[tuple]:
    """The ``(relpath, what, remove_in[, since])`` *rows* past their window
    (``Deprecation.window_expired``: *version* has reached ``remove_in`` AND a
    ``since`` is :data:`_MIN_WINDOW_DAYS` old); nothing when *version* (or a
    row's ``remove_in``) is absent or unparseable -- see
    :func:`_load_version_key` for why that stays quiet. A ``since`` the rule
    refuses is judged by version alone, never skipped: the runtime refuses that
    notice at construction, which a body-level ``Deprecation.warn`` meets only
    when its branch runs."""
    if not version:
        return []
    try:
        _version_key(version)
    except ValueError:
        return []
    out = []
    for row in rows:
        if not row[2]:
            continue
        since = row[3] if len(row) > 3 else ""
        try:
            due = _window_expired(row[2], version, since, today)
        except ValueError:
            try:
                due = bool(since) and _window_expired(row[2], version, "", today)
            except ValueError:
                continue
        if due:
            out.append(row)
    return out


def retired_forms(pkg_dir: Path, name: str) -> list[tuple[str, str, str, str]]:
    """Every sub-symbol retirement in the package source, as ``(relpath, what,
    remove_in, since)``: a ``Deprecation.<parameter|values|warn|attributes>(...)``
    call naming ``remove_in`` anywhere in a module (``ApiSurface.retirements``),
    read statically like the symbol walk, so an unimported module is covered too.
    One whose ``remove_in`` the read cannot resolve is said on stderr rather than
    left to ship past its window."""
    rows = ApiSurface.retirements(pkg_dir / name)
    unreadable = [f"{relpath}: {what}" for relpath, what, remove_in, _ in rows if not remove_in]
    if unreadable:
        print(
            f"warning: {name} has {len(unreadable)} retirement(s) whose remove_in is "
            "not a literal -- their one-release window is UNCHECKED: "
            + "; ".join(unreadable),
            file=sys.stderr,
        )
    return [row for row in rows if row[2]]


def _declared_ecosystem() -> tuple:
    """The ecosystem packages as ``m3trik/workspace.json`` declares them (``sync_workspace``)."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import sync_workspace

    return sync_workspace.ecosystem_packages()


#: The cascade, then the standalone packages. Declared once, in workspace.json.
ECOSYSTEM_PACKAGES = _declared_ecosystem()

def walk_package(pkg_dir: Path, repo_root: Path = REPO_ROOT) -> PackageSurface:
    """The public surface of ``<repo>/<pkg>/<pkg>/`` (``ApiSurface.read``), its
    ``source_root`` relative to *repo_root*.

    Raises:
        FileNotFoundError: The package has no source root there.
    """
    source_root = pkg_dir / pkg_dir.name
    if not source_root.is_dir():
        raise FileNotFoundError(f"Expected package source root at {source_root}, not found.")
    return ApiSurface.read(source_root, root=repo_root)


@functools.lru_cache(maxsize=None)
def _reads_csharp() -> bool:
    """Whether the pythontk sibling reads C# (``ApiSurface.read_csharp``).

    One predating it is a routine state, as :func:`_load_version_key` says of
    ``Deprecation``: this repo reaches main before the packages land their
    side, so C# goes unread, said once on stderr, rather than failing every
    package's ``--check``."""
    if hasattr(ApiSurface, "read_csharp"):
        return True
    print(
        "[api-surface] NOTE: the pythontk sibling reads no C# (no "
        "ApiSurface.read_csharp): a package's C# is unchecked this run.",
        file=sys.stderr,
    )
    return False


def walk_csharp(pkg_dir: Path, repo_root: Path = REPO_ROOT) -> PackageSurface | None:
    """The public C# surface of the folder ``<repo>/<pkg>/<pkg>/__init__.py``
    declares (``ApiSurface.csharp_root``), named ``<pkg> (C#)``, its
    ``source_root`` relative to *repo_root*; None when it declares none (or
    the pythontk sibling reads no C#).

    Raises:
        FileNotFoundError: The package has no source root there.
    """
    source_root = pkg_dir / pkg_dir.name
    if not source_root.is_dir():
        raise FileNotFoundError(f"Expected package source root at {source_root}, not found.")
    if not _reads_csharp() or not ApiSurface.csharp_sources(source_root):
        return None
    folder = ApiSurface.csharp_root(source_root)
    if folder is None:
        return None
    surface = ApiSurface.read_csharp(folder, root=repo_root)
    return dataclasses.replace(surface, name=f"{pkg_dir.name} (C#)")


# ---------- The last release --------------------------------------------------

#: A release tag: push.ps1 tags each release ``v<major>.<minor>.<patch>``.
_RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")


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


def release_tag(pkg_dir: Path, since: str | None = None) -> str | None:
    """The ref a delta is read against: *since*, when given, else the newest
    ``v<major>.<minor>.<patch>`` tag in *pkg_dir*'s repo (by version); None
    when that names no commit here. A *since* that names none is never
    swapped for another tag: a delta against an older release would answer a
    different question (a removal released in between reads as new). Tags
    are read as this checkout has them: one never fetched is not seen."""
    if since:
        found = _git_output(pkg_dir, "rev-parse", "--verify", "-q", f"{since}^{{commit}}")
        return since if found else None
    tags = (_git_output(pkg_dir, "tag", "--list", "v*", "--sort=-v:refname") or "").split()
    return next((t for t in tags if _RELEASE_TAG_RE.fullmatch(t)), None)


def release_surface(pkg_dir: Path, ref: str) -> PackageSurface | None:
    """*pkg_dir*'s public surface as of *ref*: its source's ``.py`` files from a
    ``git archive`` of *ref*, read from a scoped temp copy that is gone after;
    None when git cannot produce them. Read as ``<name>/<name>`` like the
    working tree, wherever the package sits inside its git root."""
    name = pkg_dir.name
    try:
        proc = subprocess.run(
            # Run in pkg_dir, git archive reads the pathspec and writes the paths
            # relative to it: "<name>/...", wherever pkg_dir sits in its repo.
            ["git", "-C", str(pkg_dir), "archive", "--format=tar", ref, "--", name],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    # Removed however the read ends: a scoped store keeps its files when an
    # exception leaves its ``with`` (for debugging), and a copy of a release
    # is nothing to debug.
    tmp = TempArtifacts.scoped("api_release")
    try:
        root = Path(tmp.dir_path()).resolve()
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
            for member in tar.getmembers():
                if not (member.isfile() and member.name.endswith(".py")):
                    continue
                target = (root / name / member.name).resolve()
                if root not in target.parents:
                    continue  # a path that would leave the copy
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
        source = root / name / name
        if not source.is_dir():
            return None
        return ApiSurface.read(source, root=root, cache=False)
    finally:
        tmp.cleanup()


def release_csharp_surface(pkg_dir: Path, ref: str) -> PackageSurface | None:
    """*pkg_dir*'s public C# surface as of *ref*: its ``.cs`` files and its
    root ``__init__.py`` from a ``git archive`` of *ref*, laid out as the
    repo had them in a scoped temp copy, read in the folder the release
    declared (or, a release predating the declaration, the folders today's
    declares). A release with no C# there is an empty surface: all of
    today's is new. None when git cannot produce them."""
    name = pkg_dir.name
    init = f"{name}/__init__.py"
    archive = None
    for pathspecs in (["*.cs", init], [init]):  # the second: a release with no C#
        try:
            proc = subprocess.run(
                ["git", "-C", str(pkg_dir), "archive", "--format=tar", ref, "--", *pathspecs],
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode == 0 and proc.stdout:
            archive = proc.stdout
            break
    if archive is None:
        return None
    tmp = TempArtifacts.scoped("api_release_cs")
    try:
        root = Path(tmp.dir_path()).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if not (member.isfile() and member.name.endswith((".cs", ".py"))):
                    continue
                target = (root / name / member.name).resolve()
                if root not in target.parents:
                    continue  # a path that would leave the copy
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
        released = root / name / name
        released.mkdir(parents=True, exist_ok=True)
        sources = ApiSurface.csharp_sources(released) or ApiSurface.csharp_sources(
            pkg_dir / name
        )
        folder = ApiSurface.csharp_root(released, sources)
        if folder is None:
            return PackageSurface(name=f"{name} (C#)", source_root="", modules=[])
        surface = ApiSurface.read_csharp(folder, root=root, cache=False)
        return dataclasses.replace(surface, name=f"{name} (C#)")
    finally:
        tmp.cleanup()


def release_baseline(
    pkg_dir: Path, since: str | None = None, read=None
) -> tuple[dict | None, str]:
    """``(surface mapping, label)`` of the last release (:func:`release_tag`),
    or ``(None, why there is none)``; *read* reads it (default
    :func:`release_surface`; :func:`release_csharp_surface` for the C#)."""
    tag = release_tag(pkg_dir, since)
    if tag is None and since:
        return None, f"none ({since} names no commit in {pkg_dir.name}: fetch its tags)"
    if tag is None:
        return None, "none (no release tag)"
    surface = (read or release_surface)(pkg_dir, tag)
    if surface is None:
        return None, f"none ({tag} could not be read)"
    return surface.to_dict(), f"the last release ({tag})"


def _symbol_key(qualname: str) -> str:
    """*qualname* as the delta keys it: a C# overload's (``Json.Write(object,
    bool)``) without its parameter types, so a name's overloads are one key."""
    return qualname.split("(", 1)[0]


def _flatten_signatures(pkg: PackageSurface) -> dict[str, str]:
    """{module:qualname: signature} for all public callables."""
    return _flatten_mapping(pkg.to_dict())


def _flatten_mapping(data: dict) -> dict[str, str]:
    """{module:qualname: signature} of a surface's mapping: a name's C#
    overloads one key, their signatures joined in order, so one added or
    dropped while the name stays reads as a changed signature."""
    groups: dict[str, list[str]] = {}
    for mod in data.get("modules", []):
        prefix = mod["relpath"]
        for fn in mod.get("functions", []):
            groups.setdefault(f"{prefix}::{_symbol_key(fn['qualname'])}", []).append(
                fn["signature"]
            )
        for const in mod.get("constants", []):
            groups.setdefault(f"{prefix}::{const['name']}", []).append("(constant)")
        for cls in mod.get("classes", []):
            groups.setdefault(f"{prefix}::{cls['name']}", []).append("(class)")
            for member in cls.get("members", []):
                key = f"{prefix}::{_symbol_key(member['qualname'])}"
                groups.setdefault(key, []).append(member["signature"])
    return {key: " | ".join(sorted(set(sigs))) for key, sigs in groups.items()}


def _class_index(
    entries: "Iterable[tuple[str, str, list[str], set[str]]]",
    foreign: dict[str, set[str]] | None = None,
) -> tuple[dict[tuple[str, str], set[str]], dict[str, list[tuple[str, str]]]]:
    """What each class STILL resolves, keyed by the module that defines it.

    The static read records a member at its DEFINING class, so hoisting a method
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

    Bases must still match on simple name, because that is all the read
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
        bases.setdefault(key, []).extend(base_names)
        by_name.setdefault(name, []).append(key)

    def walk(key: tuple[str, str], seen: set) -> set[str]:
        if key in seen:  # a cycle in recorded bases must not hang the diff
            return set()
        seen.add(key)
        out = set(own.get(key, ()))
        relpath = key[0]
        for full in bases.get(key, ()):
            base = full.split(".")[-1]
            if (relpath, base) in own and (relpath, base) != key:
                target = (relpath, base)  # a sibling in the same module wins
            else:
                candidates = [c for c in by_name.get(base, ()) if c != key]
                target = candidates[0] if len(candidates) == 1 else None
            # A class is never its own base: ``class ShotSequencer(ptk.ShotSequencer)``
            # names a same-named class in a sibling package, so it falls through.
            if target is not None:
                out |= walk(target, seen)
            else:
                # ``pythontk.ShotSequencer`` first: blendertk defines a
                # ShotSequencer too, so the bare name is ambiguous across siblings.
                qualified = f"{full.split('.')[0]}.{base}" if "." in full else None
                out |= foreign.get(qualified, foreign.get(base, set()))
        return out

    return {key: walk(key, set()) for key in own}, by_name


def _pkg_class_entries(
    pkg: PackageSurface,
) -> "Iterable[tuple[str, str, list[str], set[str]]]":
    """`_class_index` entries for a walked package."""
    for mod in pkg.modules:
        for cls in mod.classes:
            yield (
                mod.relpath,
                cls.name,
                list(cls.bases or []),
                {_symbol_key(m.qualname).split(".")[-1] for m in cls.members},
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
    it unfixed. Each sibling on disk is read live (``ApiSurface.read``, cached
    until its source changes); one absent here (a per-package checkout) simply
    leaves its bases unresolved.

    A name carried by more than one sibling with differing members is DROPPED,
    not merged. Nothing resolving is the safe direction: the member stays in
    Removed, where a human sees it.
    """
    seen: dict[str, set[str]] = {}
    ambiguous: set[str] = set()
    for name in packages:
        if name == exclude:
            continue
        try:
            surface = walk_package(repo_root / name, repo_root)
        except (FileNotFoundError, NotADirectoryError):
            continue
        resolved, _ = _class_index(_pkg_class_entries(surface))
        for (_, cls_name), members in resolved.items():
            # Bare (any sibling) and package-qualified (``pythontk.ShotSequencer``):
            # a name two siblings define is ambiguous bare, never qualified.
            for key in (cls_name, f"{name}.{cls_name}"):
                if key in seen and seen[key] != members:
                    ambiguous.add(key)
                seen.setdefault(key, set()).update(members)
    for name in ambiguous:
        seen.pop(name, None)
    return seen


def module_reexports(
    source_root: Path, relpaths: "Iterable[str]"
) -> dict[str, set[str]]:
    """``{module relpath: names it imports}`` for the given modules.

    A hoisted class is usually re-exported from its old home so the import path
    consumers hold keeps working -- `playblast_exporter.py` does exactly this
    for `CaptureResult`, `ExportResult` and `ExportTarget`. The read walks
    definitions, not imports, so without this the re-export is invisible and a
    still-importable name reads as removed.

    A module promoted to a package (``tube_rig.py`` -> ``tube_rig/``) keeps
    its import path, so its ``__init__.py`` is read in its place, and the names
    a ``lazy_exports`` call publishes count as served (CODE_STANDARD section 4:
    a subpackage re-exports that way, never by a plain import).

    The keys of a module-level ``Deprecation.attributes(globals(), {...})`` stub
    do NOT count, on purpose: an aliased move is still the break CODE_STANDARD
    section 5 prices at a minor bump, and ``required_bump`` reads that off the
    Removed section (the retirement-debt section lists the alias beside it).

    Only the modules that actually lost a symbol are parsed, so this costs a
    handful of files rather than the whole tree.
    """
    out: dict[str, set[str]] = {}
    for relpath in relpaths:
        path = source_root / relpath
        if not path.is_file() and path.suffix == ".py":
            path = path.with_suffix("") / "__init__.py"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update(a.asname or a.name.split(".")[0] for a in node.names)
            else:
                names.update(_lazy_exported_names(node))
        if names:
            out[relpath] = names
    return out


def _lazy_exported_names(node: ast.stmt) -> set[str]:
    """The names a top-level ``lazy_exports(globals(), {...})`` publishes."""
    call = node.value if isinstance(node, ast.Expr) else None
    if not (
        isinstance(call, ast.Call)
        and getattr(call.func, "id", getattr(call.func, "attr", None)) == "lazy_exports"
        and len(call.args) >= 2
        and isinstance(call.args[1], ast.Dict)
    ):
        return set()
    names: set[str] = set()
    for value in call.args[1].values:
        items = value.elts if isinstance(value, (ast.Tuple, ast.List)) else [value]
        names.update(
            item.value
            for item in items
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
    return names


def _relpaths_losing_symbols(pkg: PackageSurface, prior_json: dict | None) -> set[str]:
    """Modules whose recorded symbols shrank -- the only ones worth reparsing."""
    if not prior_json:
        return set()
    live = _flatten_signatures(pkg)
    return {
        key.split("::", 1)[0]
        for key in (
            set(_flatten_signatures(PackageSurface.from_dict(prior_json))) - set(live)
        )
    }


def _not_before(since: str) -> str:
    """The earliest removal date a notice first shipped on *since* allows
    (``since`` + :data:`_MIN_WINDOW_DAYS`), for the debt section; ``""`` when
    there is no readable date or no window."""
    if not since or not _MIN_WINDOW_DAYS:
        return ""
    try:
        start = datetime.date.fromisoformat(since)
    except ValueError:
        return ""
    return (start + datetime.timedelta(days=_MIN_WINDOW_DAYS)).isoformat()


def _deprecation_section(pkg: PackageSurface, version: str) -> list[str]:
    """The retirement-debt section: everything deprecated, earliest deadline first.

    It rides in the ``--changes`` report because that is what a reviewer reads
    before a release, and a deadline nobody reads is the failure this exists
    to end.
    The hard stop is separate (``--check`` exits non-zero on an EXPIRED row);
    this is what shows the deadline coming BEFORE the release that trips it.
    """
    rows = deprecations(pkg)
    if not rows:
        return []
    expired = {(row[0], row[1]) for row in expired_deprecations(pkg, version)}
    # Due by version, but its calendar window is still open: it stays.
    due = {(row[0], row[1]) for row in _expired(rows, version, datetime.date.max)}
    lines = [f"## Deprecations ({len(rows)})", ""]
    lines.append(
        "_Live retirement debt, earliest deadline first. An **EXPIRED** row has "
        "outlived its window: delete the alias and its tests rather than moving "
        "the date. A **HELD** row is due by version, but its notice has not yet "
        "had its calendar window._"
    )
    lines.append("")
    for relpath, qualname, remove_in, since in rows:
        key = (relpath, qualname)
        mark = "**EXPIRED** " if key in expired else "**HELD** " if key in due else ""
        text = (
            f"remove in {remove_in}" if remove_in else "**no removal version recorded**"
        )
        not_before = _not_before(since)
        if remove_in and not_before:
            text += f", not before {not_before}"
        lines.append(f"- {mark}`{relpath}::{qualname}` — {text}")
    lines.append("")
    return lines


#: Directory names whose modules are exec PAYLOAD, not an import contract. A
#: template is read as source and run inside ANOTHER application (Blender,
#: Marmoset, Substance Painter), so nothing imports its names and renaming one
#: breaks no consumer -- the root CLAUDE.md exempts "exec-templates" from the
#: encapsulation rule for the same reason. Every ``templates/`` directory in
#: the ecosystem is of this kind (the two bridge template sets, both marmoset
#: sets, both substance sets, extapps' marmoset workflow). They stay IN the
#: surface, which documents them; they simply never owe a version bump.
SEMVER_EXEMPT_DIRS = ("templates",)


def _is_semver_exempt(key: str) -> bool:
    """Whether ``relpath::symbol`` lives under a :data:`SEMVER_EXEMPT_DIRS` dir."""
    relpath = key.split("::", 1)[0]
    return any(part in SEMVER_EXEMPT_DIRS for part in relpath.split("/")[:-1])


@dataclass(frozen=True)
class ApiDelta:
    """One package's public-API delta against its last release.

    The DATA behind the ``--changes`` report. Rendering it is one consumer
    (:func:`emit_changes_markdown`); deciding what version it owes is another
    (:func:`required_bump`), which is why the computation stopped living
    inside the renderer: the release tool needs the verdict, and re-parsing
    generated prose to recover it would be a second, drifting source of truth.
    """

    added: list[str]
    #: Removals nothing accounts for: a break with no alias and no moved-names
    #: entry.
    removed: list[str]
    changed: list[str]
    moved: list[str]
    #: Flat ``relpath::symbol -> signature`` maps, kept so a renderer can show
    #: what a symbol WAS as well as what it is.
    prior: dict[str, str]
    new: dict[str, str]
    #: Removals the package's ``MOVED_NAMES`` table lists: the name left for
    #: another package, and its old home says where (pythontk's
    #: ``MovedNameError``).
    moved_out: list[str] = field(default_factory=list)
    #: Removals of names the baseline already marked deprecated: an alias whose
    #: window ran out.
    retired: list[str] = field(default_factory=list)
    #: ``key -> (new home, version)`` for each :attr:`moved_out` key.
    destinations: dict[str, tuple[str, str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            self.added
            or self.removed
            or self.changed
            or self.moved
            or self.moved_out
            or self.retired
        )


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
    removals = delta.removed + delta.moved_out + delta.retired
    reasons = [k for k in sorted(removals) if not _is_semver_exempt(k)]
    return ("minor" if reasons else "patch"), reasons


def moved_names(source_dir: Path) -> dict[str, tuple[str, str]]:
    """The package's moved-names table: the ``MOVED_NAMES`` literal its
    ``__init__.py`` declares, ``{name: (new home, version)}``, read with
    ``ast`` so nothing is imported. Empty when absent or not a literal."""
    try:
        tree = ast.parse((source_dir / "__init__.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    for node in tree.body:
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if not any(getattr(t, "id", None) == "MOVED_NAMES" for t in targets):
            continue
        try:
            table = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            return {}
        if not isinstance(table, dict):
            return {}
        return {
            str(name): (str(entry[0]), str(entry[1]))
            for name, entry in table.items()
            if isinstance(entry, (tuple, list)) and len(entry) == 2
        }
    return {}


def _retired_keys(prior_json: dict) -> set[str]:
    """Every ``relpath::symbol`` the baseline marked deprecated; a deprecated
    class retires its members with it."""
    keys: set[str] = set()
    for mod in prior_json.get("modules", []):
        prefix = mod["relpath"]
        for fn in mod.get("functions", []):
            if fn.get("deprecated"):
                keys.add(f"{prefix}::{_symbol_key(fn['qualname'])}")
        for cls in mod.get("classes", []):
            whole = bool(cls.get("deprecated"))
            if whole:
                keys.add(f"{prefix}::{cls['name']}")
            for member in cls.get("members", []):
                if whole or member.get("deprecated"):
                    keys.add(f"{prefix}::{_symbol_key(member['qualname'])}")
    return keys


def _moved_entry(
    symbol: str, table: dict[str, tuple[str, str]], namespace: str = ""
) -> tuple[str, str] | None:
    """The moved-names entry that covers *symbol* (``Name`` or
    ``Class.member``): the symbol itself, its whole class, or a member's flat
    name (a wildcard module's methods are exposed flat); a C# one also by its
    full name in *namespace* (``M3trik.Unitytk.Core.Json.Parse``)."""
    parts = symbol.split(".")
    candidates = [symbol, parts[0], parts[-1] if len(parts) == 2 else None]
    if namespace:
        candidates += [f"{namespace}.{symbol}", f"{namespace}.{parts[0]}"]
    for candidate in candidates:
        if candidate in table:
            return table[candidate]
    return None


def compute_api_delta(
    pkg: PackageSurface,
    prior_json: dict | None,
    foreign_members: dict[str, set[str]] | None = None,
    reexports: dict[str, set[str]] | None = None,
    moved_table: dict[str, tuple[str, str]] | None = None,
) -> ApiDelta | None:
    """The public-API delta of *pkg* against *prior_json*, or None when there
    is no baseline to diff against.

    A removal is one of three kinds: listed in *moved_table* (the package's
    ``MOVED_NAMES``, :func:`moved_names`), so it moved out; deprecated in the
    baseline, so it retired; or neither, a break nothing accounts for.

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

    # The same flat map from the prior JSON (which mirrors PackageSurface shape).
    prior = _flatten_mapping(prior_json)

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
            if names is None:
                # The class left this module; follow it within the package
                # when its name is unambiguous here.
                candidates = by_name.get(owner, ())
                if len(candidates) == 1:
                    names = resolved[candidates[0]]
            if names is None and owner in reexports.get(relpath, ()):
                # The module still imports it from a sibling package, so the
                # old path resolves; ask the package that now defines it.
                names = foreign_members.get(owner)
            gone = member not in (names or ())
        else:
            # A module-level class that turned up elsewhere in the package, or
            # a class or constant this very module still re-exports. A
            # module-level FUNCTION is never forgiven -- its import path really
            # did change.
            kind = prior.get(key)
            gone = not (
                (kind == "(class)" and symbol in reappeared)
                or (
                    kind in ("(class)", "(constant)")
                    and symbol in reexports.get(relpath, ())
                )
            )
        (still_removed if gone else moved).append(key)

    table = moved_table or {}
    retired_keys = _retired_keys(prior_json)
    moved_out: list[str] = []
    retired: list[str] = []
    unaccounted: list[str] = []
    destinations: dict[str, tuple[str, str]] = {}
    for key in still_removed:
        relpath, symbol = key.split("::", 1)
        entry = _moved_entry(symbol, table, "" if relpath.endswith(".py") else relpath)
        if entry is not None:
            moved_out.append(key)
            destinations[key] = entry
        elif key in retired_keys:
            retired.append(key)
        else:
            unaccounted.append(key)

    return ApiDelta(
        added=added,
        removed=unaccounted,
        changed=changed,
        moved=moved,
        prior=prior,
        new=new,
        moved_out=moved_out,
        retired=retired,
        destinations=destinations,
    )


def emit_changes_markdown(
    pkg: PackageSurface,
    prior_json: dict | None,
    baseline_label: str = "prior baseline",
    foreign_members: dict[str, set[str]] | None = None,
    reexports: dict[str, set[str]] | None = None,
    version: str = "",
    moved_table: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Render :func:`compute_api_delta`'s result as the ``--changes`` report."""
    delta = compute_api_delta(
        pkg, prior_json, foreign_members, reexports, moved_table=moved_table
    )
    if delta is None:
        # No release to diff against, but the retirement debt is a
        # property of THIS tree, not of the delta -- a package whose first
        # release also retires something would otherwise report none of it.
        head = [
            f"# {pkg.name} — API Changes",
            "",
            f"_No release to compare with: {baseline_label}._",
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
        lines.append(
            "_A break: each owes a `ptk.Deprecation` alias, or a `MOVED_NAMES` "
            "entry when the name left for another package._"
        )
        lines.append("")
        for key in removed:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}` — was `{prior[key]}`")
        lines.append("")
    if delta.moved_out:
        lines.append(f"## Moved out ({len(delta.moved_out)})")
        lines.append("")
        for key in delta.moved_out:
            mod, sym = key.split("::", 1)
            home, since = delta.destinations[key]
            lines.append(f"- `{mod}::{sym}` → `{home}` (from {since})")
        lines.append("")
    if delta.retired:
        lines.append(f"## Retired ({len(delta.retired)})")
        lines.append("")
        lines.append("_Deprecated aliases whose window ran out._")
        lines.append("")
        for key in delta.retired:
            mod, sym = key.split("::", 1)
            lines.append(f"- `{mod}::{sym}`")
        lines.append("")
    if added:
        lines.append(f"## Added ({len(added)})")
        lines.append("")
        for key in added:
            mod, sym = key.split("::", 1)
            sig = new[key]
            if not sig or sig.startswith("("):  # Python's ``(args) -> result``
                lines.append(f"- `{mod}::{sym}{sig}`")
            else:  # a C# declaration, which names the member itself
                lines.append(f"- `{mod}::{sym}` — `{sig}`")
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


def emit_shadow_report(packages: list[PackageSurface]) -> str:
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
    # name -> [(pkg, file from the workspace root, qualname, line), ...]

    for pkg in packages:
        for mod in pkg.modules:
            path = f"{pkg.source_root}/{mod.relpath}"
            for fn in mod.functions:
                occurrences[fn.name].append((pkg.name, path, fn.qualname, fn.line))
            for cls in mod.classes:
                occurrences[cls.name].append((pkg.name, path, cls.name, cls.line))

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
            for pkg_name, path, qualname, line in occs:
                lines.append(f"- `{pkg_name}` — `{qualname}` ({path}:{line})")
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


def check(package_names: list[str], repo_root: Path = REPO_ROOT) -> int:
    """The gate: exit 1 when a retirement in *package_names* outlived its
    window, or when a run naming its packages found one it could not walk.

    Parameters:
        package_names: Ecosystem package directory names to walk.
        repo_root: Monorepo root holding the package dirs and ``m3trik/``.

    Returns:
        Process exit code: 0 clean, 1 overdue or unwalkable.
    """
    walked: list[str] = []
    unwalkable: list[str] = []
    overdue: list[str] = []

    for name in package_names:
        pkg_dir = repo_root / name
        try:
            data = walk_package(pkg_dir, repo_root)
        except (FileNotFoundError, NotADirectoryError) as exc:
            print(f"warning: skipping {name} — {exc}", file=sys.stderr)
            unwalkable.append(name)
            continue
        walked.append(name)

        # The one-release alias window, enforced rather than remembered: a
        # retirement that named ``remove_in`` and then shipped past it is caught
        # by comparing it against the package's own ``__version__``.
        pkg_version = package_version(pkg_dir, name)
        # Its C# ``[Obsolete]`` names, when it declares C#, by the same rule.
        csharp = walk_csharp(pkg_dir, repo_root)
        symbols = deprecations(data) + (deprecations(csharp) if csharp else [])
        dated = [row for row in symbols if row[2]]
        if dated and not pkg_version:
            # A gate that passes because it compared against NOTHING is worse
            # than no gate: without a readable __version__ nothing here can
            # expire, so say so rather than reporting a clean bill of health.
            print(
                f"warning: {name} has {len(dated)} dated deprecation(s) but no "
                f"readable __version__ in {name}/{name}/__init__.py -- the "
                "one-release window is UNCHECKED for this package",
                file=sys.stderr,
            )
        forms = retired_forms(pkg_dir, name)
        # The calendar half of the window reads ``since``; a retirement naming
        # none is judged by version alone, the rule under which a run of
        # releases retired names 15 days after their first warning.
        undated = [f"{row[0]}::{row[1]}" for row in dated + forms if not row[3]]
        if undated and _MIN_WINDOW_DAYS:
            print(
                f"warning: {name} has {len(undated)} retirement(s) naming no "
                "since= date, judged by version alone: " + "; ".join(undated),
                file=sys.stderr,
            )
        for relpath, qualname, remove_in, *_ in _expired(dated, pkg_version) + _expired(
            forms, pkg_version
        ):
            overdue.append(f"{name}/{relpath}::{qualname} (was due in {remove_in})")

    # A gate that passes because it walked NOTHING is worse than no gate: a typo
    # in the workflow's package name, a wrong `path:` on the checkout, or a
    # renamed source root would all read green. So a SCOPED check (the CI form,
    # which names its package) must walk everything it was asked for; a sweep
    # of the whole ecosystem tolerates a checkout that lacks a package.
    scoped_run = set(package_names) != set(ECOSYSTEM_PACKAGES)
    if unwalkable and (scoped_run or not walked):
        print(
            "Nothing to check for: "
            + ", ".join(unwalkable)
            + " (wrong package name, or checked out at the wrong path?)",
            file=sys.stderr,
        )
        return 1
    if overdue:
        print(
            f"{len(overdue)} deprecation(s) outlived the one-release window. "
            "Delete the alias and its tests, or -- if it genuinely must stay -- "
            "raise remove_in deliberately and say why in CHANGELOG.md:",
            file=sys.stderr,
        )
        for entry in overdue:
            print(f"  expired: {entry}", file=sys.stderr)
        return 1
    print(f"API retirements on time: {', '.join(walked)}.")
    return 0


def _delta(
    name: str, repo_root: Path, since: str | None
) -> tuple[PackageSurface, ApiDelta | None, dict | None, str]:
    """``(surface, delta, baseline mapping, baseline label)`` of *name* against
    its last release.

    Raises:
        FileNotFoundError: The package has no source root here.
    """
    pkg_dir = repo_root / name
    data = walk_package(pkg_dir, repo_root)
    prior, label = release_baseline(pkg_dir, since)
    delta = compute_api_delta(
        data,
        prior,
        foreign_members=sibling_class_members(data.name, repo_root),
        reexports=module_reexports(
            repo_root / data.source_root, _relpaths_losing_symbols(data, prior)
        ),
        moved_table=moved_names(repo_root / data.source_root),
    )
    return data, delta, prior, label


def _csharp_delta(
    name: str, repo_root: Path, since: str | None
) -> tuple[PackageSurface, ApiDelta | None, dict | None, str] | None:
    """:func:`_delta` of *name*'s C#, or None when it declares none: read
    against the same release, accounted for by the same ``MOVED_NAMES``
    (no base resolves across packages, no Python module re-exports).

    Raises:
        FileNotFoundError: The package has no source root here.
    """
    pkg_dir = repo_root / name
    data = walk_csharp(pkg_dir, repo_root)
    if data is None:
        return None
    prior, label = release_baseline(pkg_dir, since, read=release_csharp_surface)
    moved_table = moved_names(pkg_dir / name)
    return data, compute_api_delta(data, prior, moved_table=moved_table), prior, label


def semver_verdict(name: str, repo_root: Path = REPO_ROOT, since: str | None = None) -> dict:
    """``{package, bump, reasons, unaccounted, baseline}`` -- the smallest
    release *name* may ship as (:func:`required_bump`) against its last
    release: the delta ``--changes`` prints, so the verdict cannot drift from
    the report that explains it.

    With no baseline -- no package here, no release tag, a *since* naming no
    commit -- there is no verdict: ``bump`` is None and ``baseline`` says why
    (``"none (...)"``). A gate must refuse that, never read it as a clean
    patch: a missing tag is how a removal would ship unseen.
    """
    none = {"package": name, "bump": None, "reasons": [], "unaccounted": []}
    try:
        _data, delta, _prior, label = _delta(name, repo_root, since)
        csharp = _csharp_delta(name, repo_root, since)
    except (FileNotFoundError, NotADirectoryError):
        return {**none, "baseline": "none (no package here)"}
    if delta is None:
        return {**none, "baseline": label}
    deltas = [delta]
    if csharp is not None:
        if csharp[1] is None:  # its C# could not be read at the release
            return {**none, "baseline": f"{label}; its C#: {csharp[3]}"}
        deltas.append(csharp[1])
    reasons = [r for d in deltas for r in required_bump(d)[1]]
    bump = "minor" if reasons else "patch"
    unaccounted = [k for d in deltas for k in d.removed if not _is_semver_exempt(k)]
    return {
        "package": name,
        "bump": bump,
        "reasons": reasons,
        "unaccounted": unaccounted,
        "baseline": label,
    }


def changes_report(name: str, repo_root: Path = REPO_ROOT, since: str | None = None) -> str:
    """*name*'s public-API changes since its last release, and its retirement
    debt, as markdown.

    Raises:
        FileNotFoundError: The package has no source root here.
    """
    pkg_dir = repo_root / name
    data = walk_package(pkg_dir, repo_root)
    prior, label = release_baseline(pkg_dir, since)
    return emit_changes_markdown(
        data,
        prior,
        label,
        foreign_members=sibling_class_members(data.name, repo_root),
        reexports=module_reexports(
            repo_root / data.source_root, _relpaths_losing_symbols(data, prior)
        ),
        version=package_version(pkg_dir, name),
        moved_table=moved_names(repo_root / data.source_root),
    ) + _csharp_changes(name, repo_root, since)


def _csharp_changes(name: str, repo_root: Path, since: str | None) -> str:
    """*name*'s C# changes and retirement debt (:func:`changes_report`'s
    second part), or ``""`` when it declares no C#."""
    csharp = _csharp_delta(name, repo_root, since)
    if csharp is None:
        return ""
    data, _delta_cs, prior, label = csharp
    report = emit_changes_markdown(
        data,
        prior,
        label,
        version=package_version(repo_root / name, name),
        moved_table=moved_names(repo_root / name / name),
    )
    return f"\n{report}"


def shadow_report(package_names: list[str], repo_root: Path = REPO_ROOT) -> str:
    """The cross-package name collisions among *package_names*, as markdown."""
    packages = []
    for name in package_names:
        try:
            packages.append(walk_package(repo_root / name, repo_root))
        except (FileNotFoundError, NotADirectoryError):
            print(f"warning: skipping {name} — not found", file=sys.stderr)
    return emit_shadow_report(packages)


def main(argv: list[str] | None = None) -> int:
    # The reports quote source text (arrows, dashes); a piped Windows console is
    # cp1252, which must not crash them. The --semver JSON is ASCII either way.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "packages",
        nargs="*",
        help=f"Packages to read. Default: {', '.join(ECOSYSTEM_PACKAGES)}.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when a retirement outlived its window (the gate).",
    )
    mode.add_argument(
        "--semver",
        action="store_true",
        help=(
            "Print, as JSON, the smallest release each package may ship as "
            "('minor' when the delta since its last release removes a public "
            "symbol, else 'patch') with the removals that force it; exit 2 "
            "when a package has no baseline to judge against (bump null)."
        ),
    )
    mode.add_argument(
        "--changes",
        action="store_true",
        help="Print each package's API changes since its last release, and its retirement debt.",
    )
    mode.add_argument(
        "--shadows",
        action="store_true",
        help="Print the names more than one package defines (a DRY review).",
    )
    parser.add_argument(
        "--since",
        metavar="REF",
        help="Read the delta against REF instead of the newest v* release tag "
        "(a REF naming no commit is no baseline, never another one).",
    )
    args = parser.parse_args(argv)

    names = list(args.packages) or list(ECOSYSTEM_PACKAGES)
    if args.semver:
        verdicts = [semver_verdict(n, REPO_ROOT, args.since) for n in names]
        print(json.dumps(verdicts, indent=2))
        missing = [v for v in verdicts if v["bump"] is None]
        for verdict in missing:
            print(f"no verdict for {verdict['package']}: {verdict['baseline']}", file=sys.stderr)
        return 2 if missing else 0
    if args.changes:
        for name in names:
            try:
                print(changes_report(name, REPO_ROOT, args.since))
            except (FileNotFoundError, NotADirectoryError) as exc:
                print(f"warning: skipping {name} — {exc}", file=sys.stderr)
        return 0
    if args.shadows:
        print(shadow_report(names, REPO_ROOT), end="")
        return 0
    return check(names)


if __name__ == "__main__":
    sys.exit(main())
