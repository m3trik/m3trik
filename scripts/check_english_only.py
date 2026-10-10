# !/usr/bin/python
# coding=utf-8
"""Fail when a repo's text holds a letter from a non-Latin script.

Why this gate exists
--------------------
The house rule (2026-10-05): nothing but English in the codebase -- code,
comments, docstrings, docs, test names and test DATA. It was prompted by a test
fixture's Japanese window name turning up in a user's settings. Non-ASCII test
data is still welcome, built from English: words with diacritics (café, Zoë),
a symbol outside the ANSI code page (★), fullwidth Latin for East-Asian-width
cases, emoji for 4-byte UTF-8.

What fails
----------
A LETTER (Unicode category L) from any script but Latin, in the text or the
path of every file ``git add -A`` would commit (tracked plus untracked-not-
ignored, the listing ``check_public_hygiene.py`` uses), in every repo of the
workspace. A letter is judged by its own name and by its compatibility
decomposition (NFKD), so accented, fullwidth and modifier Latin letters (é, Ｗ,
ᵀ) pass, and so do the shared notation blocks: spacing modifier letters,
letterlike symbols (ℹ, ℓ, ℵ) and number forms.

Greek is notation, one letter at a time: a lone Greek letter passes (``1/π``,
``Δt``, ``covφ``, ``µs``); two or more in a row read as a word and fail.
Combining marks ride their letter, so an accent never splits a word.

A backslash escape that spells a character -- backslash-u with four hex
digits, backslash-U with eight, backslash-N with a name in braces -- is
decoded first: the string is the same text at run time. To name a code point
range in code, write integers (``chr(0x3040)``).

What it cannot see: a foreign word spelled in Latin letters. That stays a
review question; this gate checks scripts, not languages.

Exempt: generated files (``API_*``, ``PARITY_*``; fix their source, never the
output), the third-party trees in :data:`VENDORED`, and binaries (a NUL byte in
the first 8 KB; a UTF-16 byte order mark makes it text -- the public-hygiene
gate's ``read_text``).

Usage
-----
    python m3trik/scripts/check_english_only.py               # every repo
    python m3trik/scripts/check_english_only.py uitk mayatk   # named repos
    python m3trik/scripts/check_english_only.py --workspace DIR

Exit code 0 = clean, 1 = a finding, 2 = a repo git cannot list, or no repo at all.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from typing import List, NamedTuple, Optional, Sequence

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(SCRIPTS))

#: File-name prefixes of generated files: their text is their source's.
GENERATED_PREFIXES = ("API_", "PARITY_")

#: Repo name -> repo-relative prefixes of third-party trees: not ours to translate.
VENDORED = {
    "comfyui": ("app/",),
    "www": ("www/assets/", "www/js/lib/"),
}

#: Blocks of shared notation rather than of one script: spacing modifier
#: letters (ʼ, ː), letterlike symbols and number forms (ℓ, ℵ), modifier tone
#: letters. Their letters name no script, so the name rule cannot judge them.
NOTATION_BLOCKS = ((0x02B0, 0x02FF), (0x2100, 0x218F), (0xA700, 0xA71F))

ESCAPE = re.compile(r"\\(?:u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8})|N\{([A-Za-z0-9 \-]+)\})")


class Finding(NamedTuple):
    repo: str
    path: str
    line: Optional[int]  # None: the path itself holds the run
    text: str

    def __str__(self) -> str:
        where = f"{self.repo}/{self.path}"
        if self.line is not None:
            where += f":{self.line}"
        script = unicodedata.name(self.text[0], "?").split(" ")[0]
        return f"{where}: {script} {self.text!r}"


def letter_kind(ch: str) -> Optional[str]:
    """``"foreign"`` for a letter of a non-Latin script, ``"greek"`` for a Greek
    letter, None for anything this gate passes (ASCII, Latin, notation, and
    every character that is not a letter).
    """
    if ch.isascii() or not unicodedata.category(ch).startswith("L"):
        return None
    code = ord(ch)
    if any(low <= code <= high for low, high in NOTATION_BLOCKS):
        return None
    parts = [
        part
        for part in unicodedata.normalize("NFKD", ch)
        if not part.isascii() and unicodedata.category(part).startswith("L")
    ]
    if not parts:  # plain ASCII underneath: fullwidth Latin, a superscript letter
        return None
    names = [unicodedata.name(ch, "")] + [unicodedata.name(p, "") for p in parts]
    if any("LATIN" in name.split() for name in names):
        return None
    if any(name.startswith("GREEK ") for name in names):
        return "greek"
    return "foreign"


def decode_escapes(text: str) -> str:
    """*text* with every escape that spells a character replaced by it."""

    def decoded(match):
        short, long, name = match.groups()
        try:
            return (
                chr(int(short or long, 16))
                if name is None
                else unicodedata.lookup(name)
            )
        except (KeyError, ValueError, OverflowError):  # no such character
            return match.group(0)

    return ESCAPE.sub(decoded, text)


def offending_runs(text: str) -> List[str]:
    """The runs of *text* this gate fails: letters of a non-Latin script, and
    Greek words (two or more Greek letters in a row). Escapes are decoded first.
    """
    if "\\" in text:
        text = decode_escapes(text)
    if text.isascii():
        return []
    runs: List[str] = []
    run: List[str] = []
    run_kind, letters = None, 0
    for ch in text + " ":  # the trailing space ends the last run
        if run and unicodedata.category(ch).startswith("M"):
            run.append(ch)  # a combining mark rides its letter
            continue
        kind = letter_kind(ch)
        if kind != run_kind:
            if run_kind == "foreign" or (run_kind == "greek" and letters > 1):
                runs.append("".join(run))
            run, run_kind, letters = [], kind, 0
        if kind is not None:
            run.append(ch)
            letters += 1
    return runs


def _hygiene():
    """``check_public_hygiene``, whose listing and reader this gate shares, so
    the two text gates judge one set of files, read one way."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import check_public_hygiene

    return check_public_hygiene


def _publishable_files(repo_dir: str) -> List[str]:
    """What ``git add -A`` would commit.

    Raises:
        subprocess.CalledProcessError: git could not list the repo.
    """
    return _hygiene().publishable_files(repo_dir)


def _exempt(label: str, rel: str) -> bool:
    if os.path.basename(rel).startswith(GENERATED_PREFIXES):
        return True
    return rel.startswith(VENDORED.get(label, ()))


def scan_repo(repo_dir: str, label: str) -> List[Finding]:
    """Every failing run in *repo_dir*'s publishable paths and text.

    Raises:
        subprocess.CalledProcessError: git could not list the repo.
    """
    findings = []
    read_text = _hygiene().read_text
    for rel in _publishable_files(repo_dir):
        if _exempt(label, rel):
            continue
        findings.extend(Finding(label, rel, None, run) for run in offending_runs(rel))
        text = read_text(os.path.join(repo_dir, rel))
        if text is None or (text.isascii() and "\\" not in text):
            continue
        for number, line in enumerate(text.split("\n"), 1):
            if line.isascii() and "\\" not in line:
                continue
            findings.extend(
                Finding(label, rel, number, run) for run in offending_runs(line)
            )
    return findings


def workspace_repos(workspace: str) -> List[str]:
    """Every child folder holding ``.git``: membership is measured, not listed."""
    return sorted(
        name
        for name in os.listdir(workspace)
        if os.path.exists(os.path.join(workspace, name, ".git"))
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # before -h: the docstring holds a star
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "repos", nargs="*", help="repo folders under the workspace (default: all)"
    )
    parser.add_argument("--workspace", default=WORKSPACE)
    args = parser.parse_args(argv)

    names = list(args.repos) or workspace_repos(args.workspace)
    if not names:  # nothing checked is not clean
        print(f"[english] no git repo under {args.workspace}")
        return 2
    findings: List[Finding] = []
    for name in names:
        repo_dir = os.path.join(args.workspace, name)
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            print(f"[english] not a git repo: {repo_dir}")
            return 2
        try:
            findings.extend(scan_repo(repo_dir, name))
        except subprocess.CalledProcessError as error:
            reason = (error.stderr or b"").decode("utf-8", "replace").strip()
            print(f"[english] git could not list {repo_dir}: {reason or error}")
            return 2
        except OSError as error:  # no git on PATH
            print(f"[english] could not run git: {error}")
            return 2

    if not findings:
        print(f"[english] OK: no non-Latin letter or Greek word in {', '.join(names)}.")
        return 0
    for finding in findings:
        print(f"  {finding}")
    print(
        f"[english] FAIL: {len(findings)} run(s) of a non-Latin script or a Greek "
        "word. Rewrite them in English (see this script's docstring)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
