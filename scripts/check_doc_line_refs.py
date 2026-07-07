"""Detect line-ref drift in markdown docs.

Scans markdown files for ``[text](relative/path.py#L<line>)`` patterns. For each
match resolves the target relative to the doc's location, then verifies:

  * the file exists,
  * the referenced line is in range.

Exits 1 when any drift is found, 0 otherwise. The output format is one issue
per line and is suitable for piping into a GitHub Actions log or an issue body.

Usage:

    python check_doc_line_refs.py --root <repo>                # scan all .md
    python check_doc_line_refs.py --root <repo> a.md b.md      # scan specific files
    python check_doc_line_refs.py --root <repo> --exclude 'API_REGISTRY.md'

This is the deterministic subset of the prior LLM-based drift check; it covers
the highest-priority class of drift (line numbers) without requiring an LLM
in CI. Cross-document and factual-claim checks are intentionally not handled.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


# [text](relative/path.py#Lstart) or [text](relative/path.py#Lstart-Lend)
REF_PATTERN = re.compile(
    r'\[(?P<text>[^\]]*)\]\((?P<path>[^)#?]+\.py)#L(?P<start>\d+)(?:-L(?P<end>\d+))?\)'
)

DEFAULT_DOC_GLOBS = ("*.md", "docs/**/*.md")

# Auto-generated docs that the API registry generator emits with paths assuming
# the cross-package sibling layout (e.g. uitk/uitk/file.py). Those refs look
# "broken" when the script runs from inside a single repo but are correct under
# the layout the generator targets. Excluding by default keeps the deterministic
# check focused on hand-written docs.
DEFAULT_EXCLUDES = ("API_REGISTRY.md", "API_CHANGES.md", "API_SHADOWS.md")


def _exclude_matches(rel_path: Path, pat: str) -> bool:
    # Match against both the basename (so 'API_REGISTRY.md' catches the file
    # anywhere under root) and the full relative path (so 'docs/internal.md'
    # targets a specific location). Python 3.11's fnmatch has no recursive
    # '**' semantics, so we cover both shapes explicitly.
    return fnmatch.fnmatch(rel_path.name, pat) or fnmatch.fnmatch(
        rel_path.as_posix(), pat
    )


def iter_docs(
    root: Path, explicit: Iterable[Path], excludes: Iterable[str]
) -> List[Path]:
    if explicit:
        candidates = [p.resolve() for p in explicit if p.suffix == ".md"]
    else:
        found: List[Path] = []
        for pattern in DEFAULT_DOC_GLOBS:
            found.extend(root.glob(pattern))
        candidates = sorted({p.resolve() for p in found})

    if not excludes:
        return candidates

    filtered: List[Path] = []
    for doc in candidates:
        try:
            rel = doc.relative_to(root)
        except ValueError:
            rel = doc
        if any(_exclude_matches(rel, pat) for pat in excludes):
            continue
        filtered.append(doc)
    return filtered


def _line_count(path: Path, cache: Dict[Path, int]) -> int:
    if path not in cache:
        with path.open(encoding="utf-8", errors="replace") as fh:
            cache[path] = sum(1 for _ in fh)
    return cache[path]


def scan_doc(
    doc_path: Path, repo_root: Path, line_cache: Dict[Path, int]
) -> List[Tuple[Path, int, str, str]]:
    issues: List[Tuple[Path, int, str, str]] = []
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in REF_PATTERN.finditer(line):
            rel_path = m.group("path")
            start = int(m.group("start"))
            end = int(m.group("end")) if m.group("end") else start

            # Skip absolute URLs — handled by the GitHub renderer.
            if rel_path.startswith(("http://", "https://")):
                continue

            target = (doc_path.parent / rel_path).resolve()

            # Skip refs that escape the repo (cross-repo references).
            try:
                target.relative_to(repo_root)
            except ValueError:
                continue

            if not target.exists():
                issues.append(
                    (
                        doc_path,
                        line_no,
                        m.group(0),
                        f"target not found: {target}",
                    )
                )
                continue

            try:
                target_line_count = _line_count(target, line_cache)
            except OSError as exc:
                issues.append(
                    (doc_path, line_no, m.group(0), f"unreadable target: {exc}")
                )
                continue

            if start > target_line_count or end > target_line_count:
                bad = start if start > target_line_count else end
                issues.append(
                    (
                        doc_path,
                        line_no,
                        m.group(0),
                        f"line {bad} > file length {target_line_count} in "
                        f"{target.relative_to(repo_root)}",
                    )
                )
    return issues


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help=(
            "Glob to skip. Matched against both the basename and the path "
            "relative to --root, so 'API_REGISTRY.md' catches the file under "
            "any directory while 'docs/internal.md' targets one location. "
            f"Repeatable. Defaults to {list(DEFAULT_EXCLUDES)} when no "
            "--exclude is passed; pass '--exclude=' (empty) to disable defaults."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Specific .md files to scan (default: every .md under root and docs/).",
    )
    args = parser.parse_args(argv)

    if args.exclude is None:
        excludes = list(DEFAULT_EXCLUDES)
    else:
        # Empty strings disable the defaults; non-empty entries add to the list.
        excludes = [e for e in args.exclude if e]

    repo_root = args.root.resolve()
    docs = iter_docs(repo_root, args.paths, excludes)
    if not docs:
        print(f"No markdown files found under {repo_root}.")
        return 0

    line_cache: Dict[Path, int] = {}
    all_issues: List[Tuple[Path, int, str, str]] = []
    for doc in docs:
        all_issues.extend(scan_doc(doc, repo_root, line_cache))

    if not all_issues:
        print(f"Scanned {len(docs)} doc(s). No broken line refs.")
        return 0

    print(f"Found {len(all_issues)} broken line ref(s) in {len(docs)} doc(s):")
    for doc, line_no, ref, problem in all_issues:
        try:
            rel_doc = doc.relative_to(repo_root)
        except ValueError:
            rel_doc = doc
        print(f"  {rel_doc}:{line_no}: {ref}  -- {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
