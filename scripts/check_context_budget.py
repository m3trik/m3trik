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
  CLAUDE    each CLAUDE.md size (advisory + hard caps).
  TOPIC     memory topic-file soft size cap (flag oversized files to split).
  DISPATCH  root CLAUDE.md dispatch table covers every ECOSYSTEM_PACKAGES member
            (SSoT == the generator tuple; catches the blendertk-style drift).
  LINKS     every relative markdown link in a CLAUDE.md resolves (no broken nav).
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
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]  # m3trik/scripts -> repo root

# --- budgets -----------------------------------------------------------------
MEMORY_BYTE_CAP = 24_400  # hard harness load cap for MEMORY.md (conservative decimal-KB read)
MEMORY_ENTRY_CHAR_CAP = 280  # per index bullet (slug + link + ~200-char hook)
CLAUDE_WARN = 6_144  # advisory: keep CLAUDE.md lean
CLAUDE_FAIL = 10_240  # hard: a CLAUDE.md this big is paid on every adjacent query
TOPIC_WARN = 20_480  # advisory: split / compress oversized topic files

DEFAULT_MEMORY_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "o--Cloud-Code--scripts"
    / "memory"
)

_INDEX_ENTRY_RE = re.compile(r"^- \[.*?\]\(([^)]+\.md)\)")
_LINK_RE = re.compile(r"\]\(([^)]+)\)")


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
    orphan = sorted(topic_files - linked_set)
    if dups:
        report.fail(f"MEMORY.md: {len(dups)} topic file(s) linked more than once: {dups}")
    if broken:
        report.fail(f"MEMORY.md: {len(broken)} index link(s) point to missing files: {broken}")
    if orphan:
        report.fail(f"MEMORY.md: {len(orphan)} topic file(s) have NO index entry (un-recallable): {orphan}")
    if not (dups or broken or orphan):
        report.ok(
            f"MEMORY.md coverage clean: {len(linked)} entries == {len(topic_files)} "
            f"topic files (longest entry {longest} chars)"
        )

    big = [(p.name, p.stat().st_size) for p in topic_paths if p.stat().st_size > TOPIC_WARN]
    for name, sz in sorted(big, key=lambda x: -x[1]):
        report.warn(f"TOPIC {name} is {sz:,} B > {TOPIC_WARN:,} B soft cap — compress to durable lessons / split")


def _claude_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO_ROOT.rglob("CLAUDE.md"):
        s = str(p)
        if any(seg in s for seg in (".archive", "node_modules", ".git", "site-packages")):
            continue
        out.append(p)
    return sorted(out)


def check_claude_sizes(report: Report) -> None:
    files = _claude_files()
    for p in files:
        sz = p.stat().st_size
        rel = p.relative_to(REPO_ROOT).as_posix()
        if sz > CLAUDE_FAIL:
            report.fail(f"CLAUDE {rel} is {sz:,} B > {CLAUDE_FAIL:,} B hard cap — move runbook content into <subdir>/docs/")
        elif sz > CLAUDE_WARN:
            report.warn(f"CLAUDE {rel} is {sz:,} B > {CLAUDE_WARN:,} B advisory cap")
    report.ok(f"Scanned {len(files)} CLAUDE.md files (advisory>{CLAUDE_WARN:,} B, fail>{CLAUDE_FAIL:,} B)")


def check_dispatch(report: Report) -> None:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from generate_api_registry import ECOSYSTEM_PACKAGES  # type: ignore
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


def run_checks(memory_dir: Path, do_memory: bool, do_registry: bool) -> Report:
    report = Report()
    if do_memory:
        check_memory(memory_dir, report)
    check_claude_sizes(report)
    check_dispatch(report)
    check_claude_links(report)
    if do_registry:
        check_registry_fresh(report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    ap.add_argument("--no-registry", action="store_true", help="skip the (slower) registry --check walk")
    ap.add_argument("--no-memory", action="store_true", help="skip memory-dir checks (repo-only)")
    args = ap.parse_args(argv)

    report = run_checks(args.memory_dir, do_memory=not args.no_memory, do_registry=not args.no_registry)

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
