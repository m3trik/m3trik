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
publishable file. A file with a NUL byte in its first 8 KB is binary and skipped,
unless it opens with a UTF-16 byte order mark: that is text (:func:`read_text`).

Machine paths in published binaries
-----------------------------------
A published binary -- a sample under a ``Samples~`` folder (unitytk's
deliveries), a committed test fixture, an icon -- ships with the repo and its
source tarball, so it must not name the machine that made it: a user's home,
its ``AppData``, a drive-letter folder (:data:`MACHINE_PATH`). An FBX writer
stamps exactly those (the staging file, the project folder, each map's source)
and the producer strips them (pythontk ``FbxMedia.strip_machine_paths``); this
checks the bytes of every publishable binary, needs no denylist and runs
without one (:func:`scan_machine_paths`).

This machine's folders in published text
----------------------------------------
Text naming the scanning machine's own folders -- the workspace's absolute
root, the user's home, in any of their spellings -- ships with the repo too
(m3trik's inventory, agent briefs and push.ps1 named the workspace root,
measured 2026-11-08). The pattern is derived where the gate runs
(:func:`personal_paths`), so no personal path is written here; it runs with
or without the denylist, and push.ps1 runs it on the releasing machine.

Usage
-----
    python m3trik/scripts/check_public_hygiene.py                  # every public repo
    python m3trik/scripts/check_public_hygiene.py mayatk tentacle  # named repos
    python m3trik/scripts/check_public_hygiene.py --denylist PATH
    python m3trik/scripts/check_public_hygiene.py --public-only server mayatk

``--public-only`` skips the named repos that are not in :data:`PUBLIC_REPOS`:
push.ps1 hands over every repo a run touches, and a private one may name clients.

Exit code 0 = clean (or no denylist and clean samples, or nothing public to
check), 1 = a match or a sample naming a machine path,
2 = an unreadable denylist or a repo git cannot list.
"""

from __future__ import annotations

import argparse
import codecs
import os
import re
import subprocess
import sys
from typing import List, NamedTuple, Optional, Sequence

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DENYLIST = os.path.join(WORKSPACE, ".claude", "public_hygiene.txt")

#: The workspace repos that publish anything: those GitHub serves publicly
#: (``gh repo view <name> --json visibility``), and any whose package reaches
#: PyPI, since its source tarball carries the tests and the CHANGELOG whatever
#: the repo's visibility (unitytk). server, comfyui and www are private and
#: publish nothing, so they may name clients; add a repo the day it publishes.
PUBLIC_REPOS = (
    "pythontk",
    "uitk",
    "mayatk",
    "blendertk",
    "tentacle",
    "extapps",
    "unitytk",
    "m3trik",
)

BINARY_SNIFF_BYTES = 8192

#: A folder of the machine that wrote a file: a user's home (Windows, Linux,
#: macOS), Windows' per-user ``AppData``, Maya's per-user projects folder, or
#: any absolute drive-letter path with a folder in it. A bare file name or a
#: relative path is no machine's. A drive path's every name is two characters
#: or more, from a word character, and it has two separators: a drive letter
#: a compressed stream holds by chance (``K:/9/j8``, ``i:\./KmN``, measured in
#: two committed PNGs) is no path.
MACHINE_PATH = re.compile(
    rb"[A-Za-z]:[\\/]Users[\\/][^\\/\x00\"]{1,64}"
    rb"|/(?:home|Users)/[\w.-]{1,64}/"
    rb"|[\\/]AppData[\\/]"
    rb"|Documents[\\/]maya"
    rb"|(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:\w[\w .()-]{1,63}[\\/])+\w[\w .()-]{1,63}",
    re.IGNORECASE,
)


_DRIVE_ROOT = re.compile(r"^([A-Za-z]):[\\/]+(.*)$")


def personal_paths(
    workspace: str = "", home: Optional[str] = None
) -> Optional["re.Pattern[str]"]:
    """This machine's own folders as text spells them: *workspace*'s absolute
    root and the user's *home* (default ``~``), with either separator,
    doubled or not (JSON), any case, and Git Bash's ``/c/...`` form for a
    drive; a name continuing past the folder's (``jdoe2``) is another's.
    Derived from the machine that scans, so no personal path is written in
    this repo; the releasing machine runs it (push.ps1), which is the one
    whose folders could leak. None when neither names a folder."""
    sep = r"[\\/]+"
    forms = []
    for raw in (workspace, os.path.expanduser("~") if home is None else home):
        drive = _DRIVE_ROOT.match(raw or "")
        rest = drive.group(2) if drive else (raw if (raw or "").startswith("/") else "")
        parts = [re.escape(p) for p in re.split(r"[\\/]+", rest) if p]
        if not parts:
            continue  # a bare drive or "/" is everyone's
        body = sep.join(parts) + r"(?![\w-])"
        if drive:
            letter = drive.group(1)
            forms.append(rf"(?<![\w]){letter}:{sep}{body}")
            forms.append(rf"(?<![\w.]){sep}{letter}{sep}{body}")
        else:
            forms.append(rf"(?<![\w.]){sep}{body}")
    return re.compile("|".join(forms), re.IGNORECASE) if forms else None


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


def read_text(path: str) -> Optional[str]:
    """*path*'s text; None for a binary file, or one that cannot be read.

    UTF-8, an undecodable byte read as U+FFFD -- except a file opening with a
    UTF-16 byte order mark (what Windows PowerShell 5.1's ``>`` writes), whose
    NUL bytes would otherwise read as binary. Binary: a NUL byte in the first
    :data:`BINARY_SNIFF_BYTES`. Shared with ``check_english_only.py``, so the
    two text gates read one set of files one way.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(BINARY_SNIFF_BYTES)
            if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
                return (head + handle.read()).decode("utf-16", "replace")
            if b"\0" in head:
                return None
            return (head + handle.read()).decode("utf-8", "replace")
    except OSError:  # a staged deletion, a gitlink directory
        return None


def scan_repo(repo_dir: str, pattern: "re.Pattern[str]", label: str) -> List[Finding]:
    """Every denylisted match in *repo_dir*'s publishable paths and text."""
    findings = []
    for rel in publishable_files(repo_dir):
        named = pattern.search(rel)
        if named:
            findings.append(Finding(label, rel, None, named.group(0)))
        text = read_text(os.path.join(repo_dir, rel))
        if text is None:
            continue
        line, counted = 1, 0
        for match in pattern.finditer(text):
            line += text.count("\n", counted, match.start())
            counted = match.start()
            findings.append(Finding(label, rel, line, match.group(0)))
    return findings


def scan_machine_paths(repo_dir: str, label: str) -> List[Finding]:
    """Each publishable binary of *repo_dir* -- a sample under a
    ``Samples~`` folder, a test fixture, any other -- that holds a
    :data:`MACHINE_PATH`: one finding per file, its ``line`` the first
    match's byte offset, its text that match and how many more the file
    holds. Text is the denylist's (:func:`scan_repo`)."""
    findings = []
    for rel in publishable_files(repo_dir):
        path = os.path.join(repo_dir, rel)
        if read_text(path) is not None:
            continue
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:  # a staged deletion
            continue
        matches = list(MACHINE_PATH.finditer(data))
        if matches:
            first = matches[0]
            text = first.group(0).decode("utf-8", "replace")
            more = f" (+{len(matches) - 1} more)" if len(matches) > 1 else ""
            findings.append(Finding(label, rel, first.start(), f"machine path {text}{more}"))
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
    machine: List[Finding] = []
    own: List[Finding] = []
    personal = personal_paths(os.path.abspath(args.workspace))
    for name in names:
        repo_dir = os.path.join(args.workspace, name)
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            print(f"[hygiene] not a git repo: {repo_dir}")
            return 2
        try:
            # The machine paths need no denylist: they are checked either way.
            machine.extend(scan_machine_paths(repo_dir, name))
            if personal is not None:  # neither needs the denylist
                own.extend(scan_repo(repo_dir, personal, name))
            if pattern is not None:
                findings.extend(scan_repo(repo_dir, pattern, name))
        except subprocess.CalledProcessError as error:
            reason = (error.stderr or b"").decode("utf-8", "replace").strip()
            print(f"[hygiene] git could not list {repo_dir}: {reason or error}")
            return 2
        except OSError as error:  # no git on PATH
            print(f"[hygiene] could not run git: {error}")
            return 2

    for finding in machine + own + findings:
        print(f"  {finding}")
    if own:
        print(
            f"[hygiene] FAIL: {len(own)} line(s) name this machine's own folders (the "
            "workspace's absolute root or the user's home): name them relative or derived."
        )
    if machine:
        print(
            f"[hygiene] FAIL: {len(machine)} binary(ies) name a machine "
            "path (a user's home or folder) that would be published."
        )
    paths_failed = bool(machine or own)  # neither needs the denylist
    if pattern is None:
        print(f"[hygiene] SKIP: no denylist at {args.denylist} -- cannot judge.")
        return 1 if paths_failed else 0
    if findings:
        print(
            f"[hygiene] FAIL: {len(findings)} denylisted identifier(s) would be published."
        )
        return 1
    if paths_failed:
        return 1
    print(f"[hygiene] OK: no denylisted identifier in {', '.join(names)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
