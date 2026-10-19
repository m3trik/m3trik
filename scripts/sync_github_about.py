#!/usr/bin/python
# coding=utf-8
"""Hold each package repo's GitHub About box to its ``pyproject.toml``.

A package's ``[project]`` table is the one declaration of its public metadata: it
ships to PyPI with every release. GitHub's About box restates three parts of it --
the ``description``, the ``keywords`` (as repository topics) and a homepage (the
package's PyPI page, ``https://pypi.org/project/<name>/``) -- and a restatement
drifts: measured 2026-10-17, every repo's About text was older than its pyproject and
no repo carried a topic. This reads the declaration and compares or rewrites the
restatement.

A repo whose pyproject declares no ``keywords`` is not managed: it is reported and
skipped, never failed, so a sibling cloned before its metadata lands stays green.
The package set is ``workspace.json``'s (``sync_workspace.ecosystem_packages``) and
each owner/repo comes from ``[project.urls] Repository``.

Writing topics needs admin rights on the repo, which an Actions token never has, so
CI runs ``--check`` (read-only, any token) and a drift names the local ``--apply``,
which uses the maintainer's own ``gh`` login. Topics are written as an exact set
(``PUT /topics``): ``gh repo edit --add-topic`` could never drop a stale one.

Usage:
    python sync_github_about.py [--check] [pkg ...]   # report; exit 1 on drift
    python sync_github_about.py --apply [pkg ...]     # rewrite the drifted boxes

Exit: 0 in sync (or applied), 1 drift, 2 could not run (no ``gh``, a keyword GitHub
rejects as a topic, a non-GitHub ``Repository`` URL, a failed ``gh api`` call).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]
FIELDS = ("description", "homepage", "topics")
# GitHub's topic rule: lowercase letters, digits and hyphens, at most 50 characters.
TOPIC = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
MAX_TOPICS = 20
REPO_URL = re.compile(r"github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$")


def _sync_workspace():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import sync_workspace

    return sync_workspace


def declared(pkg_dir: Path) -> Optional[dict]:
    """The About box *pkg_dir*'s pyproject declares, or None when it declares no keywords.

    Raises:
        ValueError: Unparsable TOML (``TOMLDecodeError`` is one), a keyword GitHub
            would reject as a topic, or a ``Repository`` URL that names no github.com
            repo.
    """
    text = (pkg_dir / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(text).get("project", {})
    keywords = project.get("keywords")
    if not keywords:
        return None
    bad = [k for k in keywords if not TOPIC.match(k)]
    if bad or len(keywords) > MAX_TOPICS:
        raise ValueError(
            "keywords double as GitHub topics (lowercase, digits, hyphens, <=50 "
            f"chars, <={MAX_TOPICS} of them); rejected: {bad or len(keywords)}"
        )
    match = REPO_URL.search(project.get("urls", {}).get("Repository", ""))
    if not match:
        raise ValueError("[project.urls] Repository is not a github.com repo URL")
    return {
        "slug": f"{match[1]}/{match[2]}",
        "description": project.get("description", ""),
        "homepage": f"https://pypi.org/project/{project['name']}/",
        "topics": sorted(set(keywords)),
    }


def _gh(args: list, payload: Optional[dict] = None):
    """Run ``gh api`` with *args* (a JSON *payload* goes to stdin); return parsed JSON."""
    cmd = ["gh", "api", *args] + (["--input", "-"] if payload is not None else [])
    done = subprocess.run(
        cmd,
        input=None if payload is None else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(done.stdout) if done.stdout.strip() else None


def published(slug: str) -> dict:
    """The About box GitHub currently shows for *slug*, normalized like :func:`declared`."""
    repo = _gh([f"repos/{slug}"])
    return {
        "description": repo.get("description") or "",
        "homepage": repo.get("homepage") or "",
        "topics": sorted(repo.get("topics") or []),
    }


def apply(slug: str, want: dict, fields: list) -> None:
    """Rewrite the drifted *fields* of *slug*'s About box to *want*."""
    if {"description", "homepage"} & set(fields):
        _gh(
            ["-X", "PATCH", f"repos/{slug}"],
            {"description": want["description"], "homepage": want["homepage"]},
        )
    if "topics" in fields:
        _gh(["-X", "PUT", f"repos/{slug}/topics"], {"names": want["topics"]})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="report drift, exit 1 on any (default)"
    )
    mode.add_argument(
        "--apply", action="store_true", help="rewrite drifted boxes (your gh login)"
    )
    ap.add_argument(
        "packages",
        nargs="*",
        help="limit to these packages (default: the registry set)",
    )
    args = ap.parse_args(argv)
    if shutil.which("gh") is None:
        print(
            "gh CLI not found: install GitHub CLI to read or write About boxes",
            file=sys.stderr,
        )
        return 2
    drifted = 0
    for pkg in args.packages or _sync_workspace().ecosystem_packages():
        pkg_dir = WORKSPACE / pkg
        if not (pkg_dir / "pyproject.toml").is_file():
            print(f"SKIP  {pkg}: no pyproject.toml checked out")
            continue
        try:
            want = declared(pkg_dir)
            if want is None:
                print(f"SKIP  {pkg}: declares no keywords (not managed)")
                continue
            have = published(want["slug"])
            fields = [f for f in FIELDS if want[f] != have[f]]
            if not fields:
                print(f"OK    {pkg}")
            elif args.apply:
                apply(want["slug"], want, fields)
                print(f"SET   {pkg}: {', '.join(fields)}")
            else:
                drifted += 1
                print(f"DRIFT {pkg}: {', '.join(fields)}")
                for f in fields:
                    print(f"      {f}: GitHub {have[f]!r} != pyproject {want[f]!r}")
        except ValueError as exc:
            print(f"ERROR {pkg}: {exc}", file=sys.stderr)
            return 2
        except subprocess.CalledProcessError as exc:
            print(
                f"ERROR {pkg}: gh api failed: {(exc.stderr or '').strip()}",
                file=sys.stderr,
            )
            return 2
    if drifted:
        print(
            f"{drifted} About box(es) drifted from pyproject. Run locally (needs your gh "
            "login): python m3trik/scripts/sync_github_about.py --apply"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
