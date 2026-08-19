#!/usr/bin/env python
"""Context-budget guard for the monorepo's agent-facing context surface.

Enforces the size + consistency invariants that keep Claude agent queries fast
and their recall intact. SILENT overflow of these budgets is the failure mode
that degrades query quality (an over-cap memory index is truncated every session
with no warning), so this fails the build before it ships.

Checks
------
  MEMORY    auto-memory index (MEMORY.md) byte cap + per-entry char cap +
            1-link-per-topic-file coverage (no orphans, no broken links).
            An indexed HUB topic covers the sibling files its body links, so
            a cap-managed family costs the index one entry (one level deep).
  CLAUDE    each CLAUDE.md size (advisory + hard caps; the root file gets a
            larger advisory cap - it carries the ecosystem-wide rules).
  TOPIC     memory topic-file soft size cap (flag oversized files to split).
  DISPATCH  root CLAUDE.md dispatch table covers every ECOSYSTEM_PACKAGES member
            (SSoT == the generator tuple; catches the blendertk-style drift).
  LINKS     every relative markdown link in a CLAUDE.md resolves (no broken nav).
  NAVDEPS   every registry-set package's CLAUDE.md `**Deps**:` line names each
            ecosystem package its pyproject.toml declares (hand-written nav
            must not lag the declared dependency graph).
  REGISTRY  generate_api_registry.py --check (registries fresh vs source).

FAIL exits non-zero (CI gate). WARN is advisory and never fails the build.

Usage
-----
  python check_context_budget.py                  # all checks
  python check_context_budget.py --no-registry    # skip the (slower) registry walk
  python check_context_budget.py --no-memory      # repo-only (e.g. on a CI box)
  python check_context_budget.py --memory-dir PATH
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import tomllib  # 3.11+ (CI and the workspace venv)
except ImportError:  # pragma: no cover
    tomllib = None

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]  # m3trik/scripts -> repo root

# --- budgets -----------------------------------------------------------------
MEMORY_BYTE_CAP = 24_400  # hard harness load cap for MEMORY.md (conservative decimal-KB read)
MEMORY_ENTRY_CHAR_CAP = 280  # per index bullet (slug + link + ~200-char hook)
CLAUDE_WARN = 6_144  # advisory: keep a sub-repo CLAUDE.md lean
CLAUDE_WARN_ROOT = 8_192  # advisory for the ROOT file: one-line rules for every sub-repo, no runbooks
CLAUDE_FAIL = 10_240  # hard: a CLAUDE.md this big is paid on every adjacent query
TOPIC_WARN = 20_480  # advisory: split / compress oversized topic files

def _default_memory_dir() -> Path:
    """The harness's auto-memory directory for THIS workspace.

    Claude Code names a project directory after the workspace path with the
    drive colon, the path separators and underscores all folded to ``-``
    (``c:\\work\\my_repo`` -> ``c--work-my-repo``), so derive it from
    :data:`REPO_ROOT` instead of hardcoding one machine's path into a public
    repo. ``CLAUDE_MEMORY_DIR`` overrides for a non-standard layout; a directory
    that does not exist is reported by :func:`check_memory` as a WARN, never a
    failure, so a wrong guess degrades to "skipped" rather than a false alarm.
    """
    override = os.environ.get("CLAUDE_MEMORY_DIR")
    if override:
        return Path(override)
    slug = re.sub(r"[:\\/_]", "-", str(REPO_ROOT))
    return Path.home() / ".claude" / "projects" / slug / "memory"


DEFAULT_MEMORY_DIR = _default_memory_dir()

_INDEX_ENTRY_RE = re.compile(r"^- \[.*?\]\(([^)]+\.md)\)")
_LINK_RE = re.compile(r"\]\(([^)]+)\)")
# Sibling-file link inside a topic body (no path separators / schemes) — how a
# HUB topic indexes a family of files on MEMORY.md's behalf.
_BODY_LINK_RE = re.compile(r"\]\(([\w.-]+\.md)\)")


def _broken_links(text: str, base_dir: Path) -> list[str]:
    """Relative markdown link targets in `text` that don't resolve under
    `base_dir`. Skips external (http/mailto) and pure-anchor (#…) links and
    strips any `#anchor` / `#Lnn` suffix before resolving."""
    out: list[str] = []
    for target in _LINK_RE.findall(text):
        t = target.strip()
        if t.startswith(("http://", "https://", "mailto:", "#")):
            continue
        t = t.split("#", 1)[0].strip()
        if not t:
            continue
        if not (base_dir / t).exists():
            out.append(target)
    return out


class Report:
    """Accumulates check results. Passed to each check (no global state) so the
    guard is reentrant and unit-testable."""

    def __init__(self) -> None:
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.oks: list[str] = []

    def fail(self, m: str) -> None:
        self.fails.append(m)

    def warn(self, m: str) -> None:
        self.warns.append(m)

    def ok(self, m: str) -> None:
        self.oks.append(m)


# --- checks ------------------------------------------------------------------


def check_memory(memory_dir: Path, report: Report) -> None:
    index = memory_dir / "MEMORY.md"
    if not index.exists():
        report.warn(f"MEMORY: {index} not found — skipping memory checks (expected on a CI box)")
        return

    raw = index.read_bytes()
    size = len(raw)
    if size > MEMORY_BYTE_CAP:
        report.fail(
            f"MEMORY.md is {size:,} B > {MEMORY_BYTE_CAP:,} B cap "
            f"(over by {size - MEMORY_BYTE_CAP:,}) — the index is SILENTLY "
            f"TRUNCATED every session, dropping tail entries from recall"
        )
    else:
        report.ok(f"MEMORY.md {size:,} B <= {MEMORY_BYTE_CAP:,} B cap (headroom {MEMORY_BYTE_CAP - size:,} B)")

    text = raw.decode("utf-8", errors="replace")
    linked: list[str] = []
    longest = 0
    for line in text.splitlines():
        if line.startswith("- ["):
            longest = max(longest, len(line))
            if len(line) > MEMORY_ENTRY_CHAR_CAP:
                report.fail(
                    f"MEMORY.md index entry is {len(line)} chars > {MEMORY_ENTRY_CHAR_CAP} cap "
                    f"(move detail to the topic file): {line[:70]}…"
                )
            m = _INDEX_ENTRY_RE.match(line)
            if m:
                linked.append(m.group(1))

    topic_paths = [p for p in memory_dir.glob("*.md") if p.name != "MEMORY.md"]
    topic_files = {p.name for p in topic_paths}
    linked_set = set(linked)
    dups = sorted(f for f in linked_set if linked.count(f) > 1)
    broken = sorted(linked_set - topic_files)

    # A topic file is also recallable through a HUB: an indexed topic whose body
    # links sibling topic files, indexing a whole family on MEMORY.md's behalf
    # (e.g. the live-pass queue's ~27 project files — per-family hubs are how the
    # index stays under its byte cap). One level only: a hub's links count solely
    # because the hub itself is indexed.
    hub_linked: set[str] = set()
    hub_broken: set[str] = set()
    for hub in linked_set & topic_files:
        body = (memory_dir / hub).read_text(encoding="utf-8", errors="replace")
        for name in _BODY_LINK_RE.findall(body):
            (hub_linked if name in topic_files else hub_broken).add(name)

    orphan = sorted(topic_files - linked_set - hub_linked)
    if dups:
        report.fail(f"MEMORY.md: {len(dups)} topic file(s) linked more than once: {dups}")
    if broken:
        report.fail(f"MEMORY.md: {len(broken)} index link(s) point to missing files: {broken}")
    if hub_broken:
        report.fail(
            f"MEMORY.md: {len(hub_broken)} hub link(s) point to missing files: {sorted(hub_broken)}"
        )
    if orphan:
        report.fail(
            f"MEMORY.md: {len(orphan)} topic file(s) have NO index entry and NO "
            f"hub link (un-recallable): {orphan}"
        )
    if not (dups or broken or hub_broken or orphan):
        hub_only = (topic_files - linked_set) & hub_linked
        report.ok(
            f"MEMORY.md coverage clean: {len(linked)} index entries + "
            f"{len(hub_only)} hub-covered == {len(topic_files)} topic files "
            f"(longest entry {longest} chars)"
        )

    big = [(p.name, p.stat().st_size) for p in topic_paths if p.stat().st_size > TOPIC_WARN]
    for name, sz in sorted(big, key=lambda x: -x[1]):
        report.warn(f"TOPIC {name} is {sz:,} B > {TOPIC_WARN:,} B soft cap — compress to durable lessons / split")


def _claude_files() -> list[Path]:
    out: list[Path] = []
    skip = (".archive", "node_modules", ".git", "site-packages")
    # os.walk instead of Path.rglob: a broken cloud-VFS placeholder anywhere
    # in the tree makes rglob raise OSError mid-traversal and kill the whole
    # check; os.walk lets us skip unreadable entries and keep scanning.
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, onerror=lambda e: None):
        if any(seg in dirpath for seg in skip):
            dirnames[:] = []  # prune the subtree
            continue
        if "CLAUDE.md" in filenames:
            p = Path(dirpath) / "CLAUDE.md"
            try:
                p.stat()
            except OSError:
                continue  # unreadable (e.g. dehydrated/broken cloud placeholder)
            out.append(p)
    return sorted(out)


def _claude_advisory_cap(path: Path) -> int:
    """The root CLAUDE.md carries the ecosystem-wide one-line rules for every
    sub-repo and no runbook content, so it gets the larger advisory cap; every
    sub-repo file loaded beside it keeps the lean one."""
    return CLAUDE_WARN_ROOT if path.resolve() == (REPO_ROOT / "CLAUDE.md").resolve() else CLAUDE_WARN


def check_claude_sizes(report: Report) -> None:
    files = _claude_files()
    for p in files:
        sz = p.stat().st_size
        rel = p.relative_to(REPO_ROOT).as_posix()
        warn_cap = _claude_advisory_cap(p)
        if sz > CLAUDE_FAIL:
            report.fail(f"CLAUDE {rel} is {sz:,} B > {CLAUDE_FAIL:,} B hard cap — move runbook content into <subdir>/docs/")
        elif sz > warn_cap:
            report.warn(f"CLAUDE {rel} is {sz:,} B > {warn_cap:,} B advisory cap")
    report.ok(
        f"Scanned {len(files)} CLAUDE.md files (advisory>{CLAUDE_WARN:,} B, root>{CLAUDE_WARN_ROOT:,} B, fail>{CLAUDE_FAIL:,} B)"
    )


# Distribution name only: the character class stops at the first `[`, `>`, `=`
# or space, so extras and version pins never reach the caller.
_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
# The `**Deps**:` segment of a Nav line runs until the next `· **Label**:` marker.
_NAV_DEPS_RE = re.compile(r"\*\*Deps\*\*:\s*(.*?)(?=\s·\s\*\*[A-Za-z][^*]*\*\*:|$)")
_NAV_LINK_RE = re.compile(r"\]\(\.\./([^/)]+)/CLAUDE\.md\)")  # the path names the package, the text is free


def _pyproject_ecosystem_deps(pyproject: Path, ecosystem: tuple[str, ...]) -> list[str]:
    """Ecosystem packages named in `[project] dependencies` (extras and pins stripped)."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = list(data.get("project", {}).get("dependencies", []))
    wanted = {e.lower() for e in ecosystem}
    names: list[str] = []
    for d in deps:
        m = _DEP_NAME_RE.match(d)
        if not m:
            continue
        name = m.group(1).lower().replace("_", "-")
        if name in wanted and name not in names:
            names.append(name)
    return names


def _nav_deps(claude_md: Path) -> list[str] | None:
    """Package names linked from the `**Deps**:` segment of the Nav line, or
    None when the file has no such segment."""
    for line in claude_md.read_text(encoding="utf-8").splitlines():
        if not line.startswith("**Nav**:"):
            continue
        m = _NAV_DEPS_RE.search(line)
        if not m:
            return None
        return [n.lower() for n in _NAV_LINK_RE.findall(m.group(1))]
    return None


def _nav_deps_missing(pkg_dir: Path, ecosystem: tuple[str, ...]) -> list[str]:
    """Ecosystem deps declared in pkg_dir/pyproject.toml that its CLAUDE.md Nav
    `**Deps**:` segment fails to name."""
    declared = _pyproject_ecosystem_deps(pkg_dir / "pyproject.toml", ecosystem)
    if not declared:
        return []
    named = _nav_deps(pkg_dir / "CLAUDE.md") or []
    return [d for d in declared if d not in named]


def check_nav_deps(report: Report) -> None:
    """A CLAUDE.md `**Deps**:` line is hand-maintained and used for routing; it
    must name every ecosystem package the pyproject declares (extra entries,
    e.g. host-provided engines, are fine)."""
    if tomllib is None:
        report.warn("NAVDEPS: needs Python 3.11+ (tomllib) - skipped")
        return
    try:
        ECOSYSTEM_PACKAGES = _ecosystem_packages()
    except Exception as exc:  # noqa: BLE001
        report.fail(f"NAVDEPS: cannot import ECOSYSTEM_PACKAGES from generate_api_registry: {exc}")
        return
    checked = 0
    for pkg in ECOSYSTEM_PACKAGES:
        pkg_dir = REPO_ROOT / pkg
        if not (pkg_dir / "pyproject.toml").exists() or not (pkg_dir / "CLAUDE.md").exists():
            continue  # partial checkout (CI) - nothing to compare
        checked += 1
        missing = _nav_deps_missing(pkg_dir, ECOSYSTEM_PACKAGES)
        if missing:
            report.fail(
                f"NAVDEPS: {pkg}/CLAUDE.md Nav `**Deps**:` omits declared ecosystem dep(s) {missing} "
                f"(pyproject.toml is the SSoT - add the link)"
            )
    if checked:
        report.ok(f"NAVDEPS: {checked} package CLAUDE.md Nav Deps lines cover their declared ecosystem deps")
    else:
        report.warn("NAVDEPS: no package pyproject/CLAUDE.md pairs found - skipped (partial checkout?)")


def _ecosystem_packages() -> tuple[str, ...]:
    """The package-set SSoT: generate_api_registry.ECOSYSTEM_PACKAGES."""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from generate_api_registry import ECOSYSTEM_PACKAGES  # type: ignore

    return tuple(ECOSYSTEM_PACKAGES)


def check_dispatch(report: Report) -> None:
    try:
        ECOSYSTEM_PACKAGES = _ecosystem_packages()
    except Exception as exc:  # noqa: BLE001
        report.fail(f"DISPATCH: cannot import ECOSYSTEM_PACKAGES from generate_api_registry: {exc}")
        return

    root = REPO_ROOT / "CLAUDE.md"
    if not root.exists():
        report.warn("DISPATCH: root CLAUDE.md not found at repo root — skipping (expected when only sub-repos are checked out, e.g. CI)")
        return
    text = root.read_text(encoding="utf-8")
    missing = [pkg for pkg in ECOSYSTEM_PACKAGES if f"`{pkg}/`" not in text]
    if missing:
        report.fail(
            f"DISPATCH: root CLAUDE.md dispatch table is missing ecosystem package(s) {missing} "
            f"(SSoT = ECOSYSTEM_PACKAGES = {list(ECOSYSTEM_PACKAGES)})"
        )
    else:
        report.ok(f"DISPATCH: all {len(ECOSYSTEM_PACKAGES)} ECOSYSTEM_PACKAGES present in root dispatch table")


def check_claude_links(report: Report) -> None:
    """Every relative markdown link in a CLAUDE.md must resolve — broken nav
    silently misroutes agents. Gated to the full local monorepo (cross-package
    and `← root` links can't be checked from a partial CI checkout)."""
    if not (REPO_ROOT / "CLAUDE.md").exists():
        report.warn("CLAUDE links: skipped (monorepo root not present — e.g. CI partial checkout)")
        return

    files = _claude_files()
    broken: list[str] = []
    for p in files:
        for target in _broken_links(p.read_text(encoding="utf-8"), p.parent):
            broken.append(f"{p.relative_to(REPO_ROOT).as_posix()} → {target}")
    if broken:
        for b in broken:
            report.fail(f"CLAUDE link broken: {b}")
    else:
        report.ok(f"CLAUDE links: all relative links resolve across {len(files)} files")


def check_registry_fresh(report: Report) -> None:
    gen = SCRIPT_DIR / "generate_api_registry.py"
    proc = None
    # Retry once: on a cloud-synced drive (O: Nextcloud VFS) reading a just-written
    # sidecar can transiently differ from disk and false-positive a single file. A
    # real staleness reproduces on the retry; a sync race settles.
    for attempt in (1, 2):
        try:
            proc = subprocess.run(
                [sys.executable, str(gen), "--check"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                timeout=300,
            )
        except Exception as exc:  # noqa: BLE001
            report.warn(f"REGISTRY: could not run generate_api_registry.py --check: {exc}")
            return
        if proc.returncode == 0:
            report.ok("REGISTRY: all registries fresh (generate_api_registry.py --check)")
            return
        if attempt == 1:
            time.sleep(2)

    detail = (proc.stderr.strip() or proc.stdout.strip()).splitlines() if proc else []
    head = "\n        ".join(detail[:12])
    report.fail("REGISTRY: stale — run `python m3trik/scripts/generate_api_registry.py`:\n        " + head)


def check_runtime_surface(report: Report) -> None:
    """Opt-in pythontk runtime-vs-static drift spot-check.

    ``verify_runtime_surface.py verify pythontk`` compares pythontk's live
    ``HelpMixin`` surface against its committed registry. It runs only when the
    guard is invoked WITHOUT ``--no-runtime`` in an env where pythontk is
    importable (its numpy/Pillow deps present) - a convenience for a manual local
    run. The automated runtime-drift gate across ALL packages (including the DCC
    ones CI cannot import) is ``Check-RuntimeSurface.ps1``, run weekly locally;
    cloud CI stays import-free. A registry that over-promises a member the live
    class lacks (a ``missing`` member) FAILs; ``added`` / ``kind_changed`` are
    advisory and never reach here as a failure."""
    tool = SCRIPT_DIR / "verify_runtime_surface.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "verify", "pythontk"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        report.warn(f"RUNTIME: could not run verify_runtime_surface.py: {exc}")
        return

    if proc.returncode == 0:
        report.ok("RUNTIME: pythontk live surface matches the static registry")
    elif proc.returncode == 2:
        # Import failed (e.g. numpy/Pillow absent on a minimal CI box) — advisory,
        # like the memory-dir skip; the registry --check still gates statically.
        tail = proc.stderr.strip().splitlines()
        report.warn(
            "RUNTIME: pythontk not importable in-process — skipped "
            f"({tail[-1] if tail else 'import error'})"
        )
    else:
        detail = (proc.stdout.strip() or proc.stderr.strip()).splitlines()
        head = "\n        ".join(detail[:12])
        report.fail(
            "RUNTIME: pythontk registry over-promises members the live class "
            "lacks — run `python m3trik/scripts/verify_runtime_surface.py verify "
            "pythontk`:\n        " + head
        )


def run_checks(
    memory_dir: Path, do_memory: bool, do_registry: bool, do_runtime: bool
) -> Report:
    report = Report()
    if do_memory:
        check_memory(memory_dir, report)
    check_claude_sizes(report)
    check_dispatch(report)
    check_claude_links(report)
    check_nav_deps(report)
    if do_registry:
        check_registry_fresh(report)
    if do_runtime:
        check_runtime_surface(report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    ap.add_argument("--no-registry", action="store_true", help="skip the (slower) registry --check walk")
    ap.add_argument("--no-runtime", action="store_true", help="skip the runtime-vs-static drift check (imports pythontk)")
    ap.add_argument("--no-memory", action="store_true", help="skip memory-dir checks (repo-only)")
    args = ap.parse_args(argv)

    report = run_checks(
        args.memory_dir,
        do_memory=not args.no_memory,
        do_registry=not args.no_registry,
        do_runtime=not args.no_runtime,
    )

    print("CONTEXT-BUDGET GUARD")
    print("=" * 64)
    for m in report.oks:
        print(f"  OK   {m}")
    for m in report.warns:
        print(f"  WARN {m}")
    for m in report.fails:
        print(f"  FAIL {m}")
    print("=" * 64)
    print(f"{len(report.oks)} ok, {len(report.warns)} warn, {len(report.fails)} fail")
    if report.fails:
        print("\nBUDGET EXCEEDED — see FAIL lines above.")
    return 1 if report.fails else 0


if __name__ == "__main__":
    sys.exit(main())
