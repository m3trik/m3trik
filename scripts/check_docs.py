"""Docs sweep: per-package DOCMAP ledgers + workspace-wide link/orphan checks.

Two modes, one script. Deterministic, stdlib-only, CI-friendly: FAIL exits 1,
WARN is advisory. Companion to ``check_doc_line_refs.py`` (which owns
``.py#L<line>`` drift).

Mode 1 — package (``--root <pkg>``)
-----------------------------------
Validates a package's hand-written docs against its ``docs/DOCMAP.md`` ledger
(the docs SSoT — currently uitk). Checks: ledger↔disk sync, link + ``#anchor``
integrity (GitHub slug rules), ``**Nav**:`` presence, ``DOC-TODO`` census vs.
ledger status, cross-file ``sync:`` block identity, and API_INDEX→doc coverage
triage (longest-prefix rules; an UNTRIAGED module fails — fix-or-ledger).
Ledger/coverage table formats are documented in uitk/docs/MAINTAINING.md.

Mode 2 — workspace (``--workspace <dir>``)
------------------------------------------
Sweeps every child git repo (plus root-level ``*.md``) with the universal
contract that keeps the monorepo's markdown wired without per-repo ceremony:

links     relative links + ``#anchor`` fragments in hand-written files resolve
          (http(s)/mailto and cross-repo links that escape the workspace are
          skipped; targets may be files or directories).
orphans   every hand-written ``.md`` has ≥1 inbound link from somewhere in the
          workspace, unless self-describing: any ``README.md`` / ``CLAUDE.md``
          / ``CHANGELOG.md`` / ``DOCMAP.md``, anything under ``.github/``, and
          license files. An unreachable doc is invisible doc-rot → FAIL
          (wire it into a hub, or archive/remove it).
tracked   a file that other docs link to but git doesn't track renders 404 on
          GitHub → WARN.
empty     near-empty (<20 B) hand-written files → WARN.
docmaps   any repo shipping ``docs/DOCMAP.md`` also gets the full Mode-1 suite.

Exemptions (constants below): vendored trees (``comfyui/app``,
``www/www/assets``), any ``archive``/``.archive`` directory (parked-by-design,
often deliberately untracked), and generated files (``API_*``, ``PARITY_*``,
``workspace_repo_inventory.md``, server's generated ``docs/README.md``) —
generated files still *provide* inbound links but are never linted; fix their
generators, not the output.

Usage::

    python check_docs.py --root uitk            # one package's DOCMAP suite
    python check_docs.py --workspace .          # whole-monorepo sweep

Exit 0 = clean (WARNs allowed), 1 = at least one FAIL, 2 = cannot run.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------- constants

VALID_ROLES = {"landing", "guide", "reference", "meta"}
VALID_STATUSES = {"current", "needs-verify", "stub"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LEDGER_ROW_RE = re.compile(
    r"^\|\s*\[(?P<name>[^\]]+)\]\((?P<path>[^)]+)\)\s*"
    r"\|\s*(?P<role>[^|]+?)\s*"
    r"\|\s*(?P<status>[^|]+?)\s*"
    r"\|\s*(?P<verified>[^|]+?)\s*"
    r"\|\s*(?P<sources>[^|]*?)\s*\|\s*$"
)
COVERAGE_ROW_RE = re.compile(
    r"^\|\s*`(?P<prefix>[^`]+)`\s*"
    r"\|\s*(?:\[(?P<docname>[^\]]+)\]\((?P<docpath>[^)]+)\)|(?P<optout>—|-))\s*"
    r"\|\s*(?P<note>[^|]*?)\s*\|\s*$"
)
# text alternation admits one nested image, so badge links [![alt](img)](target)
# resolve to the OUTER target instead of being skipped entirely.
LINK_RE = re.compile(
    r"\[(?P<text>!\[[^\]]*\]\([^)\s]*\)|[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
# Inbound-reachability targets: .md links with or without a #fragment.
MD_TARGET_RE = re.compile(r"\]\((?P<target>[^)#\s]+\.md)(?:#[^)\s]*)?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*$")
DOC_TODO_RE = re.compile(r"<!--\s*DOC-TODO", re.IGNORECASE)
SYNC_BLOCK_RE = re.compile(
    r"<!--\s*sync:(?P<name>[\w-]+)\s*-->(?P<body>.*?)<!--\s*/sync:(?P=name)\s*-->",
    re.DOTALL,
)
NAV_RE = re.compile(r"^\*\*Nav\*\*:")
API_INDEX_MODULE_RE = re.compile(r"^### `(?P<module>[^`]+)`")
FENCE_RE = re.compile(r"^(```|~~~)")
NAV_SEARCH_LINES = 12

# Workspace-mode config. Directory names pruned during the walk (an `archive`
# dir is parked-by-design; vendored/venv trees are not ours to lint):
WS_PRUNE_DIRS = {
    ".git", ".archive", "archive", "node_modules", "__pycache__", ".venv",
    "venv", ".pytest_cache", "build", "dist", ".idea", ".vscode", "temp_tests",
}
# repo name -> repo-relative posix prefixes holding vendored/third-party trees
WS_VENDORED: Dict[str, Tuple[str, ...]] = {
    "comfyui": ("app/",),
    "www": ("www/assets/",),
}
# Generated markdown: never linted, but still provides inbound links.
WS_GENERATED_NAMES = {
    "API_INDEX.md", "API_REGISTRY.md", "API_CHANGES.md", "API_SHADOWS.md",
    "PARITY_SURFACE.md", "PARITY_AUDIT.md", "workspace_repo_inventory.md",
}
# History files describe the tree as it was when each entry landed; their links
# rot by design and are never retro-edited, so they are exempt from link checks
# (they still count for orphan exemption via WS_ORPHAN_EXEMPT_NAMES).
WS_LINKCHECK_EXEMPT_NAMES = {"changelog.md"}
# repo name -> repo-relative posix paths of generated files with generic names
WS_GENERATED_PATHS: Dict[str, Set[str]] = {
    "server": {"docs/README.md"},  # emitted by run-tests.ps1 -UpdateReadme
}
WS_ORPHAN_EXEMPT_NAMES = {"readme.md", "claude.md", "changelog.md", "docmap.md"}


@dataclass
class LedgerRow:
    name: str
    path: Path  # resolved absolute path
    rel: str  # as written in the ledger
    role: str
    status: str
    verified: str
    sources: str
    line_no: int


@dataclass
class CoverageRule:
    prefix: str
    doc_rel: Optional[str]  # None = explicit opt-out
    note: str
    line_no: int
    hits: int = 0


@dataclass
class Report:
    fails: List[str] = field(default_factory=list)
    warns: List[str] = field(default_factory=list)

    def fail(self, check: str, msg: str) -> None:
        self.fails.append(f"[FAIL] {check}: {msg}")

    def warn(self, check: str, msg: str) -> None:
        self.warns.append(f"[WARN] {check}: {msg}")


# ---------------------------------------------------------------- md parsing

def strip_fenced_blocks(text: str) -> str:
    """Blank out fenced code blocks so their contents are never parsed."""
    return "\n".join(
        "" if fenced else line
        for line, fenced in zip(text.splitlines(), fenced_line_mask(text))
    )


def strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`\n]*`", "", text)


def strip_html_comments(text: str) -> str:
    # Preserve line count so reported line numbers stay accurate.
    return re.sub(
        r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL
    )


def fenced_line_mask(text: str) -> List[bool]:
    """Per-line: is this line a fence marker or inside a fenced block?"""
    mask: List[bool] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            mask.append(True)
        else:
            mask.append(in_fence)
    return mask


def github_slug(heading: str, seen: Counter) -> str:
    """Approximate GitHub's heading→anchor slugification."""
    text = LINK_RE.sub(lambda m: m.group("text"), heading)  # unwrap links
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    slug = text.replace(" ", "-")
    n = seen[slug]
    seen[slug] += 1
    return slug if n == 0 else f"{slug}-{n}"


def collect_anchors(md_path: Path, cache: Dict[Path, set]) -> set:
    if md_path not in cache:
        seen: Counter = Counter()
        anchors = set()
        text = strip_fenced_blocks(md_path.read_text(encoding="utf-8", errors="replace"))
        for line in text.splitlines():
            m = HEADING_RE.match(line)
            if m:
                anchors.add(github_slug(m.group("text"), seen))
        cache[md_path] = anchors
    return cache[md_path]


# ------------------------------------------------------------- shared checks

def check_links(
    entries: Iterable[Tuple[str, Path]],
    boundary: Path,
    report: Report,
    anchor_cache: Optional[Dict[Path, set]] = None,
) -> None:
    """Verify relative links + anchors in each (label, path) entry.

    ``boundary`` is the root links may not escape (package repo in DOCMAP
    mode, the whole workspace in workspace mode); links resolving outside it
    are someone else's jurisdiction and skipped.
    """
    cache: Dict[Path, set] = anchor_cache if anchor_cache is not None else {}
    for label, path in entries:
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = strip_inline_code(strip_html_comments(strip_fenced_blocks(raw)))
        for line_no, line in enumerate(text.splitlines(), 1):
            for m in LINK_RE.finditer(line):
                target = m.group("target")
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path_part, _, fragment = target.partition("#")
                if not path_part:  # same-file anchor
                    dest = path
                else:
                    dest = (path.parent / path_part).resolve()
                    try:
                        dest.relative_to(boundary)
                    except ValueError:
                        continue  # escapes the boundary — outside our jurisdiction
                    if not dest.exists():
                        report.fail("links", f"{label}:{line_no} → {target} (target not found)")
                        continue
                if fragment and dest.suffix == ".md" and not re.match(r"^L\d+", fragment):
                    # GitHub slugs are lowercase and fragments are case-sensitive,
                    # so '#Backlog' is broken even when '#backlog' exists.
                    if fragment not in collect_anchors(dest, cache):
                        report.fail("links", f"{label}:{line_no} → {target} (anchor '#{fragment}' not found)")


# ------------------------------------------------------------- DOCMAP mode

def parse_docmap(docmap: Path, docs_dir: Path, report: Report) -> Tuple[List[LedgerRow], List[CoverageRule]]:
    rows: List[LedgerRow] = []
    rules: List[CoverageRule] = []
    section = None
    for line_no, line in enumerate(docmap.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            title = line[3:].strip().lower()
            if title.startswith("ledger"):
                section = "ledger"
            elif title.startswith("coverage"):
                section = "coverage"
            else:
                section = None
            continue
        if section == "ledger":
            m = LEDGER_ROW_RE.match(line)
            if m:
                role = m.group("role").strip()
                status = m.group("status").strip()
                verified = m.group("verified").strip()
                rel = m.group("path").strip()
                rows.append(
                    LedgerRow(
                        name=m.group("name").strip(),
                        path=(docs_dir / rel).resolve(),
                        rel=rel,
                        role=role,
                        status=status,
                        verified=verified,
                        sources=m.group("sources").strip(),
                        line_no=line_no,
                    )
                )
                if role not in VALID_ROLES:
                    report.fail("ledger-sync", f"DOCMAP.md:{line_no} invalid role '{role}' (valid: {sorted(VALID_ROLES)})")
                if status not in VALID_STATUSES:
                    report.fail("ledger-sync", f"DOCMAP.md:{line_no} invalid status '{status}' (valid: {sorted(VALID_STATUSES)})")
                if status == "current" and not DATE_RE.match(verified):
                    report.fail("ledger-sync", f"DOCMAP.md:{line_no} status 'current' requires a YYYY-MM-DD Verified date, got '{verified}'")
                if verified not in ("—", "-") and not DATE_RE.match(verified):
                    report.fail("ledger-sync", f"DOCMAP.md:{line_no} Verified must be YYYY-MM-DD or —, got '{verified}'")
        elif section == "coverage":
            m = COVERAGE_ROW_RE.match(line)
            if m:
                rules.append(
                    CoverageRule(
                        prefix=m.group("prefix").strip(),
                        doc_rel=None if m.group("optout") else m.group("docpath").strip(),
                        note=m.group("note").strip(),
                        line_no=line_no,
                    )
                )
    return rows, rules


def check_ledger_sync(rows: List[LedgerRow], docs_dir: Path, report: Report) -> None:
    ledgered = {r.path for r in rows}
    for row in rows:
        if not row.path.exists():
            report.fail("ledger-sync", f"ledger row '{row.rel}' (DOCMAP.md:{row.line_no}) — file not found")
    for md in sorted(docs_dir.glob("*.md")):
        if md.name.startswith("API_"):
            continue
        if md.resolve() not in ledgered:
            report.fail("ledger-sync", f"docs/{md.name} exists on disk but has no ledger row in DOCMAP.md")


def check_nav(rows: List[LedgerRow], report: Report) -> None:
    for row in rows:
        if row.role == "landing" or not row.path.exists():
            continue
        head = row.path.read_text(encoding="utf-8", errors="replace").splitlines()[:NAV_SEARCH_LINES]
        if not any(NAV_RE.match(line) for line in head):
            report.fail("nav", f"{row.rel} — no '**Nav**:' line in the first {NAV_SEARCH_LINES} lines")


def check_todos(rows: List[LedgerRow], report: Report) -> Dict[str, int]:
    census: Dict[str, int] = {}
    for row in rows:
        if not row.path.exists():
            continue
        # Markers inside fenced code blocks are documentation examples, not tasks.
        text = strip_fenced_blocks(row.path.read_text(encoding="utf-8", errors="replace"))
        n = len(DOC_TODO_RE.findall(text))
        census[row.rel] = n
        if row.status == "current" and n:
            report.fail("todos", f"{row.rel} is status 'current' but contains {n} DOC-TODO marker(s)")
        if row.status == "stub" and not n:
            report.warn("todos", f"{row.rel} is status 'stub' but has no DOC-TODO markers — promote it in the ledger?")
    return census


def check_sync_blocks(rows: List[LedgerRow], report: Report) -> None:
    blocks: Dict[str, List[Tuple[str, str]]] = {}
    for row in rows:
        if not row.path.exists():
            continue
        text = row.path.read_text(encoding="utf-8", errors="replace")
        # A marker whose opening tag sits inside a fenced code block is a
        # documentation example, not a real sync block.
        fenced = fenced_line_mask(text)
        for m in SYNC_BLOCK_RE.finditer(text):
            start_line = text[: m.start()].count("\n")
            if start_line < len(fenced) and fenced[start_line]:
                continue
            body = "\n".join(l.rstrip() for l in m.group("body").strip("\n").splitlines())
            blocks.setdefault(m.group("name"), []).append((row.rel, body))
    for name, entries in blocks.items():
        bodies = {body for _, body in entries}
        if len(bodies) > 1:
            files = ", ".join(rel for rel, _ in entries)
            report.fail("sync", f"sync block '{name}' differs across: {files}")


def check_coverage(rules: List[CoverageRule], rows: List[LedgerRow], repo_root: Path, report: Report) -> None:
    api_index = repo_root / "API_INDEX.md"
    if not api_index.exists():
        report.warn("coverage", f"{api_index.name} not found — coverage check skipped")
        return
    ledgered_rels = {r.rel for r in rows}
    for rule in rules:
        if rule.doc_rel and rule.doc_rel not in ledgered_rels:
            report.fail("coverage", f"rule `{rule.prefix}` (DOCMAP.md:{rule.line_no}) maps to '{rule.doc_rel}', which has no ledger row")
    modules = [
        m.group("module")
        for m in map(API_INDEX_MODULE_RE.match, api_index.read_text(encoding="utf-8").splitlines())
        if m
    ]
    for module in modules:
        best: Optional[CoverageRule] = None
        for rule in rules:
            matched = (
                module.startswith(rule.prefix) if rule.prefix.endswith("/") else module == rule.prefix
            )
            if matched and (best is None or len(rule.prefix) > len(best.prefix)):
                best = rule
        if best is None:
            report.fail("coverage", f"UNTRIAGED module `{module}` — add a Coverage rule in DOCMAP.md (map it to a doc, or opt out with — and a reason)")
        else:
            best.hits += 1
    for rule in rules:
        if rule.hits == 0:
            report.warn("coverage", f"rule `{rule.prefix}` (DOCMAP.md:{rule.line_no}) matches no module in API_INDEX.md — stale?")


def run_docmap_suite(
    repo_root: Path, report: Report, label_prefix: str = "", links: bool = True
) -> Optional[str]:
    """Run the full per-package DOCMAP checks. Returns a summary line, or None
    if the repo has no docs/DOCMAP.md (not an error in workspace mode).
    Pass ``links=False`` when the caller already link-checked these files
    (workspace mode does, against the wider workspace boundary)."""
    docs_dir = repo_root / "docs"
    docmap = docs_dir / "DOCMAP.md"
    if not docmap.exists():
        return None

    sub = Report()
    rows, rules = parse_docmap(docmap, docs_dir, sub)
    if not rows:
        sub.fail("ledger-sync", "no ledger rows parsed — check the '## Ledger' table format")
    else:
        check_ledger_sync(rows, docs_dir, sub)
        if links:
            check_links(((r.rel, r.path) for r in rows), repo_root.resolve(), sub)
        check_nav(rows, sub)
        census = check_todos(rows, sub)
        check_sync_blocks(rows, sub)
        check_coverage(rules, rows, repo_root, sub)

    report.fails.extend(f"[FAIL] {label_prefix}{m[len('[FAIL] '):]}" for m in sub.fails)
    report.warns.extend(f"[WARN] {label_prefix}{m[len('[WARN] '):]}" for m in sub.warns)
    if not rows:
        return f"{label_prefix}DOCMAP unparseable"
    by_status = Counter(r.status for r in rows)
    return (
        f"{label_prefix}{len(rows)} ledgered doc(s): "
        + ", ".join(f"{n} {s}" for s, n in sorted(by_status.items()))
        + f" · {sum(census.values())} open DOC-TODO(s) · {len(rules)} coverage rule(s)"
    )


# ---------------------------------------------------------- workspace mode

def _git_tracked_md(repo: Path) -> Optional[Set[str]]:
    """Lowercased resolved paths of tracked .md files, or None if not a repo."""
    if not (repo / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "*.md", "**/*.md"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except OSError:
        return None
    return {str((repo / l).resolve()).lower() for l in r.stdout.splitlines() if l.strip()}


def _iter_repo_md(repo: Path, repo_name: str) -> Iterable[Path]:
    vendored = WS_VENDORED.get(repo_name, ())
    stack = [repo]
    while stack:
        d = stack.pop()
        try:
            children = sorted(d.iterdir())
        except OSError:
            continue
        for c in children:
            if c.is_dir():
                if c.name in WS_PRUNE_DIRS:
                    continue
                rel = c.relative_to(repo).as_posix() + "/"
                if any(rel.startswith(v) for v in vendored):
                    continue
                stack.append(c)
            elif c.suffix.lower() == ".md":
                rel = c.relative_to(repo).as_posix()
                if any(rel.startswith(v) for v in vendored):
                    continue
                yield c


def _is_generated(repo_name: str, rel_posix: str, name: str) -> bool:
    if name in WS_GENERATED_NAMES:
        return True
    return rel_posix in WS_GENERATED_PATHS.get(repo_name, set())


def _orphan_exempt(rel_parts: Tuple[str, ...]) -> bool:
    name = rel_parts[-1].lower()
    if name in WS_ORPHAN_EXEMPT_NAMES:
        return True
    if "license" in name or "copying" in name:
        return True
    return ".github" in rel_parts


def run_workspace(ws_root: Path, report: Report) -> List[str]:
    """Workspace-wide sweep. Returns per-repo summary lines."""
    repos: List[Tuple[str, Path]] = [
        (c.name, c) for c in sorted(ws_root.iterdir())
        if c.is_dir() and (c / ".git").exists()
    ]

    # file -> (ws_rel_label, repo_name, is_generated)
    catalog: Dict[Path, Tuple[str, str, bool]] = {}
    for md in sorted(ws_root.glob("*.md")):  # workspace-root files (no repo)
        catalog[md.resolve()] = (md.name, "(root)", False)
    for repo_name, repo in repos:
        for md in _iter_repo_md(repo, repo_name):
            rel_posix = md.relative_to(repo).as_posix()
            catalog[md.resolve()] = (
                md.relative_to(ws_root).as_posix(),
                repo_name,
                _is_generated(repo_name, rel_posix, md.name),
            )

    # Inbound-link map: generated files count as sources (they render and
    # navigate), but are never linted themselves.
    inbound: Dict[Path, Set[str]] = defaultdict(set)
    for path, (label, _, _) in catalog.items():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in MD_TARGET_RE.finditer(text):
            t = m.group("target")
            if t.startswith(("http://", "https://")):
                continue
            try:
                dest = (path.parent / t).resolve()
            except OSError:
                continue
            if dest != path:
                inbound[dest].add(label)

    hand_written = [(label, path) for path, (label, repo, gen) in catalog.items() if not gen]
    hand_written.sort()

    check_links(
        [(l, p) for l, p in hand_written if p.name.lower() not in WS_LINKCHECK_EXEMPT_NAMES],
        ws_root.resolve(),
        report,
    )

    tracked_cache: Dict[str, Optional[Set[str]]] = {
        name: _git_tracked_md(repo) for name, repo in repos
    }
    for path, (label, repo_name, gen) in sorted(catalog.items(), key=lambda kv: kv[1][0]):
        if gen:
            continue
        rel_parts = Path(label).parts
        if not inbound.get(path) and not _orphan_exempt(rel_parts):
            report.fail(
                "orphans",
                f"{label} — no inbound links from anywhere in the workspace; "
                "wire it into a hub doc (or archive/remove it)",
            )
        tracked = tracked_cache.get(repo_name)
        if tracked is not None and inbound.get(path) and str(path).lower() not in tracked:
            srcs = ", ".join(sorted(inbound[path])[:3])
            report.warn("tracked", f"{label} is linked (from {srcs}) but not git-tracked — 404 on GitHub")
        try:
            if path.stat().st_size < 20:
                report.warn("empty", f"{label} is effectively empty ({path.stat().st_size} B)")
        except OSError:
            pass

    summaries = [f"{len(catalog)} md file(s) across {len(repos)} repo(s), {len(hand_written)} hand-written"]
    for repo_name, repo in repos:
        # links=False: the workspace pass above already checked these files
        # against the wider workspace boundary.
        s = run_docmap_suite(repo, report, label_prefix=f"{repo_name}/docs/", links=False)
        if s:
            summaries.append(s)
    return summaries


# ----------------------------------------------------------------- entrypoint

def main(argv: Optional[List[str]] = None) -> int:
    # Windows consoles default to cp1252, which can't encode the arrows/dashes
    # that doc content drags into our messages.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Docs sweep (see module docstring).")
    parser.add_argument("--root", type=Path, default=None, help="Package repo root containing docs/DOCMAP.md.")
    parser.add_argument("--workspace", type=Path, default=None, help="Monorepo root: sweep every child git repo.")
    args = parser.parse_args(argv)

    report = Report()
    summaries: List[str] = []

    if args.workspace:
        summaries = run_workspace(args.workspace.resolve(), report)
    else:
        repo_root = (args.root or Path.cwd()).resolve()
        s = run_docmap_suite(repo_root, report)
        if s is None:
            print(f"[ERROR] {repo_root / 'docs' / 'DOCMAP.md'} not found — nothing to sweep.")
            return 2
        summaries = [s]

    for line in report.fails + report.warns:
        print(line)
    for s in summaries:
        print(s)
    if report.fails:
        print(f"Result: {len(report.fails)} FAIL, {len(report.warns)} WARN → exit 1")
        return 1
    print(f"Result: clean ({len(report.warns)} WARN) → exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
