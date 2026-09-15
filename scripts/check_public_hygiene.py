# !/usr/bin/python
# coding=utf-8
"""Fail when a public repo would publish a client identifier.

Why this gate exists
--------------------
Most ecosystem repos are public (CODE_STANDARD section 11). A client program
identifier or a studio name in a published file -- a fixture's filename, a
comment citing a measured production scene, a CHANGELOG line -- leaks a business
relationship the moment it is pushed. A CI check runs after the push, so all it
can do is report a leak that already happened; this gate runs before it, over
exactly what ``push.ps1 -Merge`` would commit: the tracked files plus the
untracked ones git does not ignore.

The denylist is private
-----------------------
A pattern list in a public repo publishes the identifiers it guards -- the first
version of this check was a test holding the regex, copied into six public repos.
So the patterns live OUTSIDE every repo: ``<workspace>/.claude/public_hygiene.txt``
by default (the workspace root is not a repository), one regular expression per
line, ``#`` comments, matched case-insensitively. Without that file the gate
cannot judge, and says so without failing: a machine that lacks the list is not
evidence of a clean tree, and it must not block that machine's release either.

What is scanned
---------------
Each repo's publishable paths (a module named for a client leaks through any
listing, this workspace's own inventory included) and the text of every
publishable file. A file with a NUL byte in its first 8 KB is binary and skipped.

Usage
-----
    python m3trik/scripts/check_public_hygiene.py                  # every public repo
    python m3trik/scripts/check_public_hygiene.py mayatk tentacle  # named repos
    python m3trik/scripts/check_public_hygiene.py --denylist PATH
    python m3trik/scripts/check_public_hygiene.py --public-only unitytk mayatk

``--public-only`` skips the named repos that are not in :data:`PUBLIC_REPOS`:
push.ps1 hands over every repo a run touches, and a private one may name clients.

Exit code 0 = clean (or no denylist, or nothing public to check), 1 = a match,
2 = an unreadable denylist or a repo git cannot list.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import List, NamedTuple, Optional, Sequence

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DENYLIST = os.path.join(WORKSPACE, ".claude", "public_hygiene.txt")

#: The workspace repos GitHub serves publicly (``gh repo view <name> --json
#: visibility``). unitytk, server, comfyui and www are private and may name
#: clients; add a repo here the day it goes public.
PUBLIC_REPOS = (
    "pythontk",
    "uitk",
    "mayatk",
    "blendertk",
    "tentacle",
    "extapps",
    "m3trik",
)

BINARY_SNIFF_BYTES = 8192


class Finding(NamedTuple):
    repo: str
    path: str
    line: Optional[int]  # None: the path itself names the identifier
    text: str

    def __str__(self) -> str:
        where = f"{self.repo}/{self.path}"
        if self.line is None:
            return f"{where}: the path names {self.text!r}"
        return f"{where}:{self.line}: {self.text!r}"


def load_denylist(path: str) -> Optional["re.Pattern[str]"]:
    """The denylist as one case-insensitive alternation; None when there is none.

    Read as ``utf-8-sig``: Windows PowerShell 5.1 saves UTF-8 with a byte order
    mark, which would otherwise ride on the first pattern and stop it matching.

    Raises:
        ValueError: A line is not a valid expression -- alone, or inside the
            joined alternation, where a global inline flag like ``(?i)`` is
            refused -- or no line holds one.
    """
    if not os.path.isfile(path):
        return None
    alternatives = []
    with open(path, encoding="utf-8-sig") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            alternative = f"(?:{line})"
            try:
                re.compile(line)
                re.compile(alternative)
            except re.error as error:
                raise ValueError(f"{path}:{number}: {error}") from None
            alternatives.append(alternative)
    if not alternatives:
        raise ValueError(f"{path} holds no pattern")
    return re.compile("|".join(alternatives), re.IGNORECASE)


def publishable_files(repo_dir: str) -> List[str]:
    """What ``git add -A`` would commit: tracked plus untracked-not-ignored.

    Raises:
        subprocess.CalledProcessError: git could not list the repo.
    """
    listing = subprocess.run(
        [
            "git",
            "-C",
            repo_dir,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return sorted(
        {rel for rel in listing.decode("utf-8", "replace").split("\0") if rel}
    )


def scan_repo(repo_dir: str, pattern: "re.Pattern[str]", label: str) -> List[Finding]:
    """Every denylisted match in *repo_dir*'s publishable paths and text."""
    findings = []
    for rel in publishable_files(repo_dir):
        named = pattern.search(rel)
        if named:
            findings.append(Finding(label, rel, None, named.group(0)))
        try:
            with open(os.path.join(repo_dir, rel), "rb") as handle:
                head = handle.read(BINARY_SNIFF_BYTES)
                if b"\0" in head:
                    continue
                data = head + handle.read()
        except OSError:  # a staged deletion, a gitlink directory
            continue
        text = data.decode("utf-8", "replace")
        line, counted = 1, 0
        for match in pattern.finditer(text):
            line += text.count("\n", counted, match.start())
            counted = match.start()
            findings.append(Finding(label, rel, line, match.group(0)))
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "repos",
        nargs="*",
        help="repo folders under the workspace (default: every public repo)",
    )
    parser.add_argument("--denylist", default=DEFAULT_DENYLIST)
    parser.add_argument("--workspace", default=WORKSPACE)
    parser.add_argument(
        "--public-only",
        action="store_true",
        help="skip named repos that are not public (see PUBLIC_REPOS)",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    try:
        pattern = load_denylist(args.denylist)
    except (OSError, ValueError) as error:
        print(f"[hygiene] unreadable denylist: {error}")
        return 2
    if pattern is None:
        print(f"[hygiene] SKIP: no denylist at {args.denylist} -- cannot judge.")
        return 0

    names = list(args.repos) or list(PUBLIC_REPOS)
    if args.public_only:
        private = [name for name in names if name not in PUBLIC_REPOS]
        if private:
            print(f"[hygiene] skipped, private: {', '.join(private)}")
        names = [name for name in names if name in PUBLIC_REPOS]
        if not names:
            print("[hygiene] OK: no public repo to check.")
            return 0
    findings: List[Finding] = []
    for name in names:
        repo_dir = os.path.join(args.workspace, name)
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            print(f"[hygiene] not a git repo: {repo_dir}")
            return 2
        try:
            findings.extend(scan_repo(repo_dir, pattern, name))
        except subprocess.CalledProcessError as error:
            reason = (error.stderr or b"").decode("utf-8", "replace").strip()
            print(f"[hygiene] git could not list {repo_dir}: {reason or error}")
            return 2
        except OSError as error:  # no git on PATH
            print(f"[hygiene] could not run git: {error}")
            return 2

    if not findings:
        print(f"[hygiene] OK: no denylisted identifier in {', '.join(names)}.")
        return 0
    for finding in findings:
        print(f"  {finding}")
    print(
        f"[hygiene] FAIL: {len(findings)} denylisted identifier(s) would be published."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
