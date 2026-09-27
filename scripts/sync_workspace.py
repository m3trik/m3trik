#!/usr/bin/python
# coding=utf-8
"""The workspace declared as data -- read it, derive from it, fail when a restatement drifts.

``m3trik/workspace.json`` is the one declaration of the workspace (CODE_STANDARD
section 0): the cascade (``push.ps1``'s release order) and, per unit -- every front
door that carries a ``CLAUDE.md`` -- its release mode and its domain line. It
declares only what cannot be measured. Membership IS measured: a folder holding
``.git`` belongs (``check_temp_artifacts.py``'s positive rule), so a new repo needs
no roster edit to exist; one without an entry is reported as unclassified, never
failed.

Readers take the declaration directly -- ``push.ps1`` (``$RELEASE_ORDER``,
``$STRICT_PACKAGES``), ``generate_api_registry.ECOSYSTEM_PACKAGES``,
``generate_workspace_inventory`` (domains) and ``check_context_budget`` -- so none of
them spells the package set. What cannot read JSON is checked here:

1. The root ``CLAUDE.md`` Dispatch table, rewritten from the manifest. The
   workspace root is not a repo, so a CI checkout has no such file and that part
   is reported as skipped there.
2. The ecosystem sibling loops in ``m3trik/.github/workflows/*.yml`` (a
   ``for repo in ...; do`` naming ``pythontk``), which must list
   :func:`ecosystem_packages` in order.
3. The charter rule: every declared unit present on disk carries its ``CLAUDE.md``.

Usage:
    python sync_workspace.py            # rewrite the dispatch table (idempotent)
    python sync_workspace.py --check    # exit 1 on any drift
"""

import argparse
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# This file: _scripts/m3trik/scripts/sync_workspace.py
M3TRIK = Path(__file__).resolve().parents[1]
WORKSPACE = M3TRIK.parent
MANIFEST = M3TRIK / "workspace.json"
ROOT_CLAUDE = WORKSPACE / "CLAUDE.md"
WORKFLOWS = M3TRIK / ".github" / "workflows"

RELEASE_MODES = ("cascade", "standalone", "none")
DISPATCH_HEADING = "## Dispatch"
SIBLING_LOOP = re.compile(r"for repo in ([\w ]+); do")


def validate(data: dict) -> List[str]:
    """Every reason *data* is not a usable manifest; empty when it is."""
    problems = []
    units = data.get("units") or []
    paths = [unit.get("path") for unit in units]
    dupes = sorted({p for p in paths if paths.count(p) > 1})
    if dupes:
        problems.append(f"duplicate unit paths {dupes}")
    for unit in units:
        if unit.get("release") not in RELEASE_MODES:
            problems.append(
                f"{unit.get('path')}: release must be one of {RELEASE_MODES}"
            )
        if not unit.get("domain"):
            problems.append(f"{unit.get('path')}: no domain line")
    cascade = list(data.get("cascade") or [])
    if not cascade:
        # push.ps1 reads it raw: empty, it would release nothing in order.
        problems.append("no cascade declared")
    by_cascade = [u.get("path") for u in units if u.get("release") == "cascade"]
    if sorted(cascade) != sorted(by_cascade):
        problems.append(
            f"cascade {cascade} names other units than those released by "
            f"cascade {by_cascade}"
        )
    return problems


@lru_cache(maxsize=None)
def load(path: Path = MANIFEST) -> dict:
    """The validated manifest at *path*.

    Raises:
        ValueError: The manifest is malformed (every problem named).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(data)
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems))
    return data


def ecosystem_packages(data: Optional[dict] = None) -> Tuple[str, ...]:
    """The registry set: the cascade in release order, then the standalone
    packages in manifest order."""
    data = data or load()
    standalone = [u["path"] for u in data["units"] if u["release"] == "standalone"]
    return tuple(data["cascade"]) + tuple(standalone)


def domains(data: Optional[dict] = None) -> Dict[str, str]:
    """Unit path -> its declared domain line."""
    return {u["path"]: u["domain"] for u in (data or load())["units"]}


def render_dispatch(data: Optional[dict] = None) -> str:
    """The root Dispatch table, one row per unit in manifest order."""
    rows = ["| Unit | Domain |", "|:---|:---|"]
    for unit in (data or load())["units"]:
        path = unit["path"]
        rows.append(f"| [`{path}/`]({path}/CLAUDE.md) | {unit['domain']} |")
    return "\n".join(rows)


def splice_dispatch(text: str, table: str) -> str:
    """*text* with the table under the Dispatch heading replaced by *table*.

    Raises:
        ValueError: *text* has no Dispatch heading, or no table directly under it.
    """
    lines = text.split("\n")
    try:
        head = lines.index(DISPATCH_HEADING)
    except ValueError:
        raise ValueError(f"no '{DISPATCH_HEADING}' heading") from None
    start = head + 1
    while start < len(lines) and not lines[start].startswith(("|", "#")):
        start += 1
    if start == len(lines) or not lines[start].startswith("|"):
        raise ValueError(f"no table under '{DISPATCH_HEADING}'")
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return "\n".join(lines[:start] + table.split("\n") + lines[end:])


def _read(path: Path) -> Tuple[str, bool]:
    """(*path*'s text with LF endings, whether it was CRLF)."""
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def dispatch_drift(path: Path = ROOT_CLAUDE) -> Optional[str]:
    """Why the Dispatch table in *path* disagrees with the manifest, or None."""
    text, _ = _read(path)
    try:
        wanted = splice_dispatch(text, render_dispatch())
    except ValueError as exc:
        return f"{path.name}: {exc}"
    if wanted != text:
        return (
            f"{path.name}: the Dispatch table differs from workspace.json "
            "-- run m3trik/scripts/sync_workspace.py"
        )
    return None


def write_dispatch(path: Path = ROOT_CLAUDE) -> bool:
    """Rewrite *path*'s Dispatch table from the manifest; True when it changed."""
    text, crlf = _read(path)
    wanted = splice_dispatch(text, render_dispatch())
    if wanted == text:
        return False
    path.write_bytes((wanted.replace("\n", "\r\n") if crlf else wanted).encode())
    return True


def workflow_drift(workflows: Path = WORKFLOWS) -> List[str]:
    """Each ecosystem sibling loop in *workflows* that lists another set or order."""
    wanted = list(ecosystem_packages())
    drift = []
    for workflow in sorted(workflows.glob("*.yml")):
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            match = SIBLING_LOOP.search(line)
            names = match.group(1).split() if match else []
            if "pythontk" in names and names != wanted:
                drift.append(
                    f"{workflow.name}:{number}: loops over {names}, "
                    f"workspace.json declares {wanted}"
                )
    return drift


def missing_charters(workspace: Path = WORKSPACE) -> List[str]:
    """Declared units present on disk that carry no ``CLAUDE.md``."""
    return [
        unit["path"]
        for unit in load()["units"]
        if (workspace / unit["path"]).is_dir()
        and not (workspace / unit["path"] / "CLAUDE.md").is_file()
    ]


def unclassified(workspace: Path = WORKSPACE) -> List[str]:
    """Child repos (a folder holding ``.git``) with no manifest entry."""
    declared = {unit["path"] for unit in load()["units"]}
    return sorted(
        child.name
        for child in workspace.iterdir()
        if child.is_dir() and (child / ".git").exists() and child.name not in declared
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="report drift; write nothing"
    )
    args = parser.parse_args(argv)
    try:
        load()
    except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError
        print(f"[FAIL] workspace.json: {exc}")
        return 1

    failures = []
    if not ROOT_CLAUDE.is_file():
        print("[SKIP] dispatch: no workspace root CLAUDE.md (a CI runner clones repos)")
    elif args.check:
        drift = dispatch_drift()
        if drift:
            failures.append(drift)
    else:
        try:
            changed = write_dispatch()
        except ValueError as exc:
            failures.append(f"{ROOT_CLAUDE.name}: {exc}")
        else:
            print(f"[{'WROTE' if changed else 'OK'}] dispatch table")
    failures += workflow_drift()
    failures += [
        f"{path}: declared in workspace.json but carries no CLAUDE.md (its charter)"
        for path in missing_charters()
    ]
    for name in unclassified():
        print(f"[WARN] {name}: a repo with no workspace.json entry (unclassified)")
    for failure in failures:
        print(f"[FAIL] {failure}")
    if not failures:
        print("[OK] workspace.json and its restatements agree")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
