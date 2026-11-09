#!/usr/bin/python
# coding=utf-8
"""The workspace declared as data -- read it, derive from it, fail when a restatement drifts.

``m3trik/workspace.json`` is the one declaration of the workspace (CODE_STANDARD
section 0): the cascade (``push.ps1``'s release order) and, per unit -- every front
door that carries an ``AGENTS.md`` -- its release mode and its domain line. It
declares only what cannot be measured. Membership IS measured: a folder holding
``.git`` belongs (``check_temp_artifacts.py``'s positive rule), so a new repo needs
no roster edit to exist; one without an entry is reported as unclassified, never
failed.

Readers take the declaration directly -- ``push.ps1`` (``$RELEASE_ORDER``,
``$STRICT_PACKAGES``), ``check_api_surface.ECOSYSTEM_PACKAGES``,
``generate_workspace_inventory`` (domains) and ``check_context_budget`` -- so none of
them spells the package set. What cannot read JSON is checked here:

1. The root ``AGENTS.md`` Dispatch table, rewritten from the manifest. The
   workspace root is not a repo, so a CI checkout has no such file and that part
   is reported as skipped there.
2. The ecosystem sibling loops in ``m3trik/.github/workflows/*.yml`` (a
   ``for repo in ...; do`` naming ``pythontk``), which must list
   :func:`ecosystem_packages` in order.
3. The charter rule: every declared unit present on disk carries its ``AGENTS.md``,
   and the instruction tree keeps its layout and its declared packs, vendored and
   current (``pythontk.AgentInstructions``).
4. Each package's committed operation catalog (``<package>/operations.json``)
   against the declarations it is generated from (``pythontk.OperationCatalog``).
5. The dependency chain the prose states (:data:`CHAIN_STATEMENTS`: the root
   ``AGENTS.md`` and ``docs/CODEBASE_MANIFEST.md``) against the ecosystem
   packages' pyproject dependencies, each direction, through other packages
   too; skipped where a statement or a pyproject is absent (a CI checkout).

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
from typing import Dict, List, Optional, Sequence, Set, Tuple

# This file: _scripts/m3trik/scripts/sync_workspace.py
M3TRIK = Path(__file__).resolve().parents[1]
WORKSPACE = M3TRIK.parent
MANIFEST = M3TRIK / "workspace.json"
ROOT_AGENTS = WORKSPACE / "AGENTS.md"
WORKFLOWS = M3TRIK / ".github" / "workflows"
#: The packs' source: every unit's vendored copy is checked against it.
PACKS = M3TRIK / "agents" / "packs"
#: The standard the instructions cite as ``§N``.
STANDARD = M3TRIK / "docs" / "CODE_STANDARD.md"

RELEASE_MODES = ("cascade", "standalone", "none")
ROLES = ("product",)
DISPATCH_HEADING = "## Dispatch"
SIBLING_LOOP = re.compile(r"for repo in ([\w ]+); do")
#: Where the prose states the dependency chain: (file, anchor). A heading
#: anchors the line under it; other text, the line it starts.
CHAIN_STATEMENTS = (
    (ROOT_AGENTS, "## Ecosystem chain"),
    (M3TRIK / "docs" / "CODEBASE_MANIFEST.md", "The dependency chain is "),
)
#: A code span holding an arrow: one stated chain.
CHAIN_SPAN = re.compile(r"`([^`]*→[^`]*)`")


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
        if "role" in unit and unit["role"] not in ROLES:
            problems.append(f"{unit.get('path')}: role must be one of {ROLES}")
        twin = unit.get("twin")
        if twin is not None and (twin not in paths or twin == unit.get("path")):
            problems.append(f"{unit.get('path')}: twin {twin!r} names no other unit")
        packs = unit.get("packs", [])
        if not isinstance(packs, list) or not all(isinstance(p, str) for p in packs):
            problems.append(f"{unit.get('path')}: packs must be a list of pack names")
    root_packs = data.get("packs", [])
    if not isinstance(root_packs, list) or not all(isinstance(p, str) for p in root_packs):
        problems.append("packs (the workspace root's) must be a list of pack names")
    budget = data.get("line_budget")
    if budget is not None and (type(budget) is not int or budget <= 0):
        problems.append("line_budget must be a positive integer")
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
    """The ecosystem set: the cascade in release order, then the standalone
    packages in manifest order."""
    data = data or load()
    standalone = [u["path"] for u in data["units"] if u["release"] == "standalone"]
    return tuple(data["cascade"]) + tuple(standalone)


def twins(data: Optional[dict] = None) -> Dict[str, str]:
    """Unit path -> its mirror in another host (``"twin"``, declared on one
    side), in both directions."""
    pairs: Dict[str, str] = {}
    for unit in (data or load())["units"]:
        if unit.get("twin"):
            pairs[unit["path"]] = unit["twin"]
            pairs[unit["twin"]] = unit["path"]
    return pairs


def products(data: Optional[dict] = None) -> Tuple[str, ...]:
    """The units no other package may import (``"role": "product"``)."""
    return tuple(u["path"] for u in (data or load())["units"] if u.get("role") == "product")


def domains(data: Optional[dict] = None) -> Dict[str, str]:
    """Unit path -> its declared domain line."""
    return {u["path"]: u["domain"] for u in (data or load())["units"]}


def render_dispatch(data: Optional[dict] = None) -> str:
    """The root Dispatch table, one row per unit in manifest order."""
    rows = ["| Unit | Domain |", "|:---|:---|"]
    for unit in (data or load())["units"]:
        path = unit["path"]
        rows.append(f"| [`{path}/`]({path}/AGENTS.md) | {unit['domain']} |")
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


def dispatch_drift(path: Path = ROOT_AGENTS) -> Optional[str]:
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


def write_dispatch(path: Path = ROOT_AGENTS) -> bool:
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
    """Declared units present on disk that carry no ``AGENTS.md``."""
    return [
        unit["path"]
        for unit in load()["units"]
        if (workspace / unit["path"]).is_dir()
        and not (workspace / unit["path"] / "AGENTS.md").is_file()
    ]


def instruction_roots(workspace: Path = WORKSPACE) -> List[Tuple[Path, List[str], str]]:
    """``(folder, packs, mode)`` for each instruction root present: the
    workspace root (its packs imported once, ``import``) and every declared
    unit (its packs added by its own hook in a session rooted there, ``hook``)."""
    data = load()
    roots = [(workspace, list(data.get("packs", [])), "import")] if workspace.is_dir() else []
    for unit in data["units"]:
        folder = workspace / unit["path"]
        if folder.is_dir():
            roots.append((folder, list(unit.get("packs", [])), "hook"))
    return roots


def _instructions():
    """pythontk's ``AgentInstructions``, from the sibling checkout when not installed."""
    sibling = str(WORKSPACE / "pythontk")
    if (WORKSPACE / "pythontk" / "pythontk").is_dir() and sibling not in sys.path:
        sys.path.insert(0, sibling)
    from pythontk import AgentInstructions

    return AgentInstructions


def instruction_problems(workspace: Path = WORKSPACE) -> List[str]:
    """Every way the instruction tree breaks its layout (once each), and each
    declared pack a root does not carry."""
    agent = _instructions()
    seen, out = set(), []
    for folder, packs, mode in instruction_roots(workspace):
        if folder == workspace and not (workspace / "AGENTS.md").is_file():
            continue  # no workspace root here: a CI runner clones the repos alone
        result = agent.check(str(folder), source=str(PACKS), standard=str(STANDARD), mode=mode)
        for problem in result["problems"]:
            key = (problem["code"], problem["location"])
            if key not in seen:
                seen.add(key)
                out.append(f"{problem['location']}: {problem['message']}")
        missing = sorted(set(packs) - set(agent.vendored(str(folder))))
        if missing:
            out.append(f"{folder}: declares packs {missing} it does not carry")
    return out


def write_instructions(workspace: Path = WORKSPACE) -> List[str]:
    """Bring every instruction root in line (``AgentInstructions.sync``); the files written."""
    agent = _instructions()
    written = []
    for folder, packs, mode in instruction_roots(workspace):
        result = agent.sync(str(folder), str(PACKS), packs=packs, mode=mode)
        written += result["written"] + result["removed"]
    return written


def catalog_modules(workspace: Path = WORKSPACE, data: Optional[dict] = None) -> List[Tuple[Path, str]]:
    """``(repo, module)`` for each declared unit whose package declares
    operations: ``<unit>/<package>/operations.py``, beside its committed catalog."""
    out = []
    for unit in (data or load())["units"]:
        repo = workspace / unit["path"]
        if (repo / repo.name / "operations.py").is_file():
            out.append((repo, f"{repo.name}.operations"))
    return out


def _operation_provider(repos: Sequence[Path]):
    """pythontk's ``OperationProvider``, each of *repos* importable ahead of
    whatever is installed (a repo folder off the path imports as an empty
    namespace, so its package would not be found)."""
    for repo in reversed(repos):
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
    _instructions()  # pythontk itself, from the sibling checkout
    from pythontk import OperationProvider

    return OperationProvider


def catalog_problems(workspace: Path = WORKSPACE, data: Optional[dict] = None) -> List[str]:
    """Every way the packages' operations break the rules
    (``OperationProvider.check``): a missing or stale catalog, a change that
    cannot plan, an untyped argument, twins that disagree."""
    modules = catalog_modules(workspace, data)
    provider = _operation_provider([repo for repo, _ in modules])
    return provider.check([module for _, module in modules])


def write_catalogs(workspace: Path = WORKSPACE, data: Optional[dict] = None) -> List[str]:
    """Rewrite every package's committed operation catalog; the files that changed."""
    modules = catalog_modules(workspace, data)
    provider = _operation_provider([repo for repo, _ in modules])
    written = []
    for _repo, module in modules:
        path = provider.catalog_path(module)
        before = path.read_bytes() if path.is_file() else None
        provider.write_catalog(module)
        if path.read_bytes() != before:
            written.append(str(path))
    return written


def _layers():
    """``check_layers`` (beside this file): its pyproject reader is the one
    the import rules read dependencies with."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import check_layers

    return check_layers


def stated_edges(line: str) -> Set[Tuple[str, str]]:
    """``(lower, upper)`` -- *upper* depends on *lower* -- for each arrow in each
    code span of *line* holding one: ``a → b → {c, d}`` states ``(a, b)``,
    ``(b, c)`` and ``(b, d)``."""
    edges: Set[Tuple[str, str]] = set()
    for span in CHAIN_SPAN.findall(line):
        stages = [
            [name.strip() for name in stage.strip().strip("{}").split(",") if name.strip()]
            for stage in span.split("→")
        ]
        for lower, upper in zip(stages, stages[1:]):
            edges |= {(a, b) for a in lower for b in upper}
    return edges


def declared_edges(workspace: Path = WORKSPACE, data: Optional[dict] = None) -> Set[Tuple[str, str]]:
    """``(lower, upper)`` for each ecosystem package *upper*'s pyproject names
    (``dependencies`` and every extra). A dependency on a product is no edge:
    nothing imports a product (``check_layers.py``), so it pins an install."""
    layers = _layers()
    members = set(ecosystem_packages(data))
    lowers = members - set(products(data))
    edges = set()
    for upper in members:
        if not (workspace / upper / "pyproject.toml").is_file():
            continue
        named = layers.declared_dependencies(layers.pyproject(workspace / upper))
        edges |= {(lower, upper) for lower in named & lowers}
    return edges


def _closure(edges: Set[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    """*edges* with every pair a path of them joins."""
    closed = set(edges)
    while True:
        more = {(a, d) for a, b in closed for c, d in closed if b == c} - closed
        if not more:
            return closed
        closed |= more


def chain_statement(text: str, anchor: str) -> Optional[str]:
    """The chain's line in *text*: the first line starting with *anchor*, or,
    for a heading, the first non-blank line under it; None when absent."""
    lines = text.split("\n")
    for number, line in enumerate(lines):
        if line.startswith(anchor):
            if not anchor.startswith("#"):
                return line
            return next((rest for rest in lines[number + 1 :] if rest.strip()), None)
    return None


def chain_drift(
    path: Path, anchor: str, workspace: Path = WORKSPACE, data: Optional[dict] = None
) -> List[str]:
    """Where the chain *path* states at *anchor* and the pyprojects' dependencies
    disagree, each direction, through other packages too: a stated edge no
    dependency holds, a dependency the chain does not state, a name no
    ecosystem package bears."""
    line = chain_statement(_read(path)[0], anchor)
    if line is None:
        return [f"{path.name}: no chain statement at {anchor!r}"]
    stated = stated_edges(line)
    members = set(ecosystem_packages(data))
    unknown = sorted({name for edge in stated for name in edge} - members)
    if unknown:
        return [f"{path.name}: the chain names {name}, no ecosystem package" for name in unknown]
    said, held = _closure(stated), _closure(declared_edges(workspace, data))
    drift = [
        f"{path.name}: states {upper} depends on {lower}; its pyproject does not "
        "(directly or through another)"
        for lower, upper in sorted(said - held, key=lambda e: (e[1], e[0]))
    ]
    drift += [
        f"{path.name}: {upper} depends on {lower} (its pyproject); the chain does not state it"
        for lower, upper in sorted(held - said, key=lambda e: (e[1], e[0]))
    ]
    return drift


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
    # A rule may quote any character; a console's code page must not crash the report.
    sys.stdout.reconfigure(errors="backslashreplace")
    try:
        load()
    except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError
        print(f"[FAIL] workspace.json: {exc}")
        return 1

    failures = []
    try:
        if args.check:
            failures += instruction_problems()
            failures += catalog_problems()
        else:
            for path in write_instructions() + write_catalogs():
                print(f"[WROTE] {path}")
    except ImportError as exc:
        print(f"[SKIP] instructions: pythontk is not importable here ({exc})")
    except ValueError as exc:
        failures.append(f"instructions: {exc}")
    if not ROOT_AGENTS.is_file():
        print("[SKIP] dispatch: no workspace root AGENTS.md (a CI runner clones repos)")
    elif args.check:
        drift = dispatch_drift()
        if drift:
            failures.append(drift)
    else:
        try:
            changed = write_dispatch()
        except ValueError as exc:
            failures.append(f"{ROOT_AGENTS.name}: {exc}")
        else:
            print(f"[{'WROTE' if changed else 'OK'}] dispatch table")
    failures += workflow_drift()
    absent = [p for p in ecosystem_packages() if not (WORKSPACE / p / "pyproject.toml").is_file()]
    for path, anchor in CHAIN_STATEMENTS:
        if not path.is_file() or absent:
            print(f"[SKIP] chain: no {path.name if not path.is_file() else absent} here")
            continue
        failures += chain_drift(path, anchor)
    failures += [
        f"{path}: declared in workspace.json but carries no AGENTS.md (its charter)"
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
