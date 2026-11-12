#!/usr/bin/python
# coding=utf-8
"""Set up the workspace around this clone: the repos beside it, an environment,
the root's instructions.

A clone of ``m3trik`` holds the workspace's declaration (``workspace.json``),
its rules and the tooling, and nothing else. This makes the rest, each step
only where it is missing:

1. Each unit's repo beside this one (default: the cascade and the products;
   ``--units all`` every declared unit, ``--units a,b`` the named ones),
   cloned from the remote this clone came from. A folder that exists is left
   as it is: never fetched, reset or overwritten.
2. The workspace's ``.venv``, with every ecosystem package present installed
   editable (``editable_mode=compat``: ``docs/AGENT_INSTRUCTIONS.md``, Set
   up). An existing ``.venv`` is left as it is.
3. The root's instruction files: ``AGENTS.md`` rendered from
   ``agents/workspace.md``, its stub and its packs
   (``sync_workspace.write_root``), once the cascade's first package is
   beside this clone. An ``AGENTS.md`` already there that is another
   project's stops the run; it is never overwritten.

Without ``--apply`` it prints that plan and changes nothing. In the folder
holding this clone it makes only those clones, the ``.venv`` and the root's
three kinds of file: no other folder there is read or written. It never
configures a person's tools: the Claude Code plugin and its permissions are
theirs to add, so it prints those commands and runs none of them.

Usage:
    python m3trik/scripts/setup_workspace.py            # the plan
    python m3trik/scripts/setup_workspace.py --apply    # make it
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_workspace as sw  # noqa: E402

#: The oldest Python the MCP servers run on (the packages themselves: 3.9).
MIN_PYTHON = (3, 10)


def remote_base(repo: Path = sw.M3TRIK) -> str:
    """Where *repo*'s ``origin`` keeps its repos: its URL up to and including
    the last separator, so ``base + name`` is a sibling's (an HTTPS URL, an
    ``scp``-style ``host:owner/repo``, a local path).

    Raises:
        ValueError: *repo* has no ``origin`` to clone the others from.
    """
    done = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True
    )
    url = done.stdout.strip().replace("\\", "/").rstrip("/")
    if done.returncode or not url:
        raise ValueError(f"{repo.name} has no 'origin' remote to clone the other repos from")
    cut = max(url.rfind("/"), url.rfind(":"))
    if cut < 0:
        raise ValueError(f"cannot tell where {url!r} keeps its repos")
    return url[: cut + 1]


def default_units(data: Optional[dict] = None) -> List[str]:
    """The cascade and the products, in manifest order: what one install of
    the ecosystem holds (``m3trik/pyproject.toml`` names the same set)."""
    data = data or sw.load()
    wanted = set(data["cascade"]) | set(sw.products(data))
    return [unit["path"] for unit in data["units"] if unit["path"] in wanted]


def named_units(names: str, data: Optional[dict] = None) -> List[str]:
    """The repos *names* asks for: ``""`` the default, ``all`` every declared
    unit's repo, else the comma-separated ones (a unit inside a repo, like
    ``m3trik/scripts``, is its repo's).

    Raises:
        ValueError: A name is no declared unit.
    """
    data = data or sw.load()
    declared = []
    for unit in data["units"]:
        top = unit["path"].split("/")[0]
        if top not in declared:
            declared.append(top)
    if not names.strip():
        return default_units(data)
    if names.strip() == "all":
        return declared
    asked = [name.strip() for name in names.split(",") if name.strip()]
    unknown = [name for name in asked if name not in declared]
    if unknown:
        raise ValueError(f"not declared in workspace.json: {', '.join(unknown)}")
    return asked


def venv_python(venv: Path) -> Path:
    """The interpreter inside *venv*."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def plan(
    workspace: Path, units: Sequence[str], base: str, venv: bool = True
) -> List[Dict[str, object]]:
    """The steps that bring *workspace* up, each ``{"do", "what", "command"}``:
    a clone per missing repo, the environment and its installs when there is
    no ``.venv``, then the root's instruction files (``command`` None: made
    here). Nothing is planned for what already exists."""
    steps: List[Dict[str, object]] = []
    present = []
    for unit in units:
        folder = workspace / unit
        if unit == sw.UNIT:
            continue  # this clone, whatever its folder is called
        if folder.exists():
            present.append(unit)
            continue
        steps.append(
            {
                "do": "clone",
                "what": f"{unit}/ from {base}{unit}",
                "command": ["git", "clone", f"{base}{unit}", str(folder)],
            }
        )
        present.append(unit)
    target = workspace / ".venv"
    if venv and not target.exists():
        steps.append(
            {
                "do": "venv",
                "what": f"{target.name}/ (Python {sys.version_info.major}.{sys.version_info.minor})",
                "command": [sys.executable, "-m", "venv", str(target)],
            }
        )
        editable = [name for name in sw.ecosystem_packages() if name in present]
        if editable:
            command = [str(venv_python(target)), "-m", "pip", "install"]
            command += ["--config-settings", "editable_mode=compat"]
            for name in editable:
                command += ["-e", str(workspace / name)]
            steps.append(
                {"do": "install", "what": "editable: " + " ".join(editable), "command": command}
            )
    # The root is built only where this is the workspace: the cascade's first
    # package beside this clone (sync_workspace.is_workspace). Any other
    # folder is someone's, and nothing but the clones asked for goes there.
    if sw.load()["cascade"][0] in present or sw.is_workspace(workspace):
        steps.append(
            {
                "do": "root",
                "what": "AGENTS.md, CLAUDE.md and .agents/packs at the workspace root, no other folder",
                "command": None,
            }
        )
    return steps


def apply(steps: Sequence[Dict[str, object]], workspace: Path) -> List[str]:
    """Run *steps* in order, stopping at the first that fails; the problems
    (empty when every step succeeded)."""
    for step in steps:
        print(f"[{step['do']}] {step['what']}")
        command = step["command"]
        if command is None:
            try:
                for path in sw.write_root(workspace):
                    print(f"  wrote {path}")
            except (ImportError, ValueError, OSError) as exc:
                return [f"root: {exc}"]
            continue
        done = subprocess.run(command)
        if done.returncode:
            return [f"{step['do']} failed (exit {done.returncode}): {step['what']}"]
    return []


def next_steps(workspace: Path) -> str:
    """What is left to the person: their own tools' configuration."""
    return (
        "Left to you (docs/AGENT_INSTRUCTIONS.md, Set up, steps 2 to 6): uv on PATH, then, "
        f"from {workspace}:\n"
        f"  claude plugin marketplace add {sw.M3TRIK} --scope project\n"
        "  claude plugin install m3trik@m3trik --scope project"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the plan (default: print it)")
    parser.add_argument(
        "--units", default="", help="repos to clone: a,b or 'all' (default: cascade and products)"
    )
    parser.add_argument("--no-venv", action="store_true", help="leave the environment to you")
    args = parser.parse_args(argv)
    workspace = sw.WORKSPACE
    try:
        steps = plan(workspace, named_units(args.units), remote_base(), venv=not args.no_venv)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    if sys.version_info < MIN_PYTHON and not args.no_venv:
        print(
            f"[WARN] Python {sys.version_info.major}.{sys.version_info.minor}: the MCP servers "
            f"need {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or later (run this with one, or --no-venv)"
        )
    if not args.apply:
        print(f"The plan for {workspace} (nothing is changed; --apply makes it):")
        for step in steps:
            print(f"  [{step['do']}] {step['what']}")
        return 0
    problems = apply(steps, workspace)
    for problem in problems:
        print(f"[FAIL] {problem}")
    if not problems:
        print(f"[OK] {workspace} is set up")
        print(next_steps(workspace))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
