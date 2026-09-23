#!/usr/bin/python
# coding=utf-8
"""Refuse a push to main that changes what ships without bumping the version.

The off-chain packages (``unitytk``, ``extapps``) are not released by
``push.ps1``: a push to their ``main`` runs ``publish.yml``, which uploads only
when ``__version__`` differs from what PyPI already has. When it does not, the
job used to print "already on PyPI" and go GREEN -- so a merge carrying real
changes at an unchanged version uploaded nothing and nothing said so (extapps,
2026-09-18: a push changing 8 launchers at 0.1.18 == PyPI 0.1.18 ran green, and
the changes stayed off PyPI until 0.1.19).

This gate splits that one green outcome into the three it was hiding:

- ``__version__`` differs from PyPI's     -> ``publish=true``
- nothing that ships changed in the push -> ``publish=false``, pass
- something that ships changed and the version did not:
    - the push's ``CHANGELOG.md`` additions say ``no version bump``
      (a deliberate hold, the phrase unitytk's CHANGELOG already uses) -> pass
    - otherwise -> exit 1, naming the files and the two ways out

A push that DID move ``__version__`` to what PyPI now serves is a re-run of a
push that already published, and passes.

"What ships" is ``<pkg>/**`` and ``pyproject.toml`` -- the same set each
``publish.yml``'s ``paths`` filter triggers on. The push range is
``github.event.before..HEAD``; every check reads only those two commits
(tree diffs and ``git show``), never the history between them. With no range
(``workflow_dispatch``) there is nothing to judge and the gate only reports; a
range it cannot resolve fails, because "cannot tell" must not read as "nothing
shipped".

Stdout is ``key=value`` lines for ``$GITHUB_OUTPUT``; diagnostics go to stderr
as workflow annotations.

Usage:
    python check_version_bump.py <pkg> --published <ver> [--repo DIR] [--base SHA]
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

#: An added CHANGELOG line containing this declares a deliberate hold.
HOLD_MARKER = re.compile(r"no version bump", re.IGNORECASE)

_VERSION_RE = re.compile(r"""__version__\s*=\s*["']([^"']+)["']""")
_ZERO_SHA = re.compile(r"^0+$")


@dataclass
class Verdict:
    """The gate's decision for one push.

    Parameters:
        version: ``__version__`` as committed.
        publish: Whether the workflow should build and upload.
        ok: False only for a shipped change at an unbumped version.
        message: One human-readable line explaining the decision.
    """

    version: str
    publish: bool
    ok: bool
    message: str


def _git(repo: Path, *args: str) -> Optional[str]:
    """Run git in ``repo``; return stdout, or None when git fails."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else None


def version_at(repo: Path, rev: str, package: str) -> Optional[str]:
    """Return ``__version__`` as committed at ``rev``, or None if unreadable."""
    text = _git(repo, "show", f"{rev}:{package}/__init__.py")
    match = _VERSION_RE.search(text or "")
    return match.group(1) if match else None


def is_artifact(path: str, package: str) -> bool:
    """Whether a repo-relative path ships (mirrors publish.yml's ``paths``)."""
    return path.startswith(f"{package}/") or path == "pyproject.toml"


def changed_files(repo: Path, base: str, head: str) -> Optional[List[str]]:
    """Return the paths changed between two commits, or None if unresolvable."""
    if _ZERO_SHA.match(base):
        return None
    out = _git(repo, "diff", "--name-only", "--no-renames", base, head)
    return None if out is None else [line for line in out.splitlines() if line]


def hold_declared(repo: Path, base: str, head: str) -> bool:
    """Whether the push ADDS a CHANGELOG.md declaration of a version hold.

    Counted at both ends, not read off the diff: a ``+`` line carrying the
    phrase is also what an EDIT of an old hold line looks like (a word fixed in
    last week's entry), and reading that as a new declaration silently skipped
    the publish this gate exists to force. A hold is declared when head carries
    more of them than base.
    """

    def holds(rev: str) -> int:
        return len(HOLD_MARKER.findall(_git(repo, "show", f"{rev}:CHANGELOG.md") or ""))

    return holds(head) > holds(base)


def decide(
    repo: Path,
    package: str,
    published: str,
    base: Optional[str] = None,
    head: str = "HEAD",
) -> Verdict:
    """Decide whether a push publishes, passes without publishing, or fails.

    Parameters:
        repo: The package repo's checkout.
        package: Import name; also the source dir that ships.
        published: The version PyPI serves (``none`` when unpublished).
        base: The commit main pointed at before the push; empty/None = no range.
        head: The pushed revision.

    Returns:
        The :class:`Verdict`.

    Raises:
        ValueError: ``head`` declares no ``__version__``.
    """
    version = version_at(repo, head, package)
    if version is None:
        raise ValueError(f"no __version__ in {package}/__init__.py at {head}")
    if version != published:
        return Verdict(version, True, True, f"{package} {version} (PyPI: {published})")
    if not base:
        return Verdict(
            version,
            False,
            True,
            f"{package} {version} is already on PyPI; no push range to check",
        )
    files = changed_files(repo, base, head)
    if files is None:
        return Verdict(
            version,
            False,
            False,
            f"cannot diff {base[:12]}..{head}: unable to prove this push ships "
            f"nothing at the published {version}",
        )
    shipped = [f for f in files if is_artifact(f, package)]
    if not shipped:
        return Verdict(
            version,
            False,
            True,
            f"{package} {version} is already on PyPI; nothing that ships changed",
        )
    if version_at(repo, base, package) != version:
        return Verdict(
            version,
            False,
            True,
            f"{package} {version} is already on PyPI and this push is what set it "
            f"(a re-run after its upload)",
        )
    if hold_declared(repo, base, head):
        return Verdict(
            version,
            False,
            True,
            f"{package} held at {version}: CHANGELOG.md declares 'no version bump' "
            f"({len(shipped)} shipped file(s) changed)",
        )
    listed = ", ".join(shipped[:8]) + (" ..." if len(shipped) > 8 else "")
    return Verdict(
        version,
        False,
        False,
        f"{len(shipped)} shipped file(s) changed but {package}.__version__ is still "
        f"{version}, which PyPI already has, so nothing would upload: {listed}. "
        f"Bump __version__, or declare a deliberate hold by adding a CHANGELOG.md "
        f"line that says 'no version bump'.",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package")
    parser.add_argument("--published", required=True, help="version on PyPI, or 'none'")
    parser.add_argument("--repo", default=".", help="package repo checkout")
    parser.add_argument("--base", default="", help="github.event.before (empty = none)")
    args = parser.parse_args(argv)

    verdict = decide(Path(args.repo), args.package, args.published, args.base)
    print(f"version={verdict.version}")
    print(f"publish={'true' if verdict.publish else 'false'}")
    level = "notice" if verdict.ok else "error"
    print(f"::{level}::{verdict.message}", file=sys.stderr)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
