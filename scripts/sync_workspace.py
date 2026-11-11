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

1. The workspace root's ``AGENTS.md``. The root is not a repo, so it holds no
   source: its rules are written in ``m3trik/agents/workspace.md`` (versioned,
   links valid where it sits, its Dispatch table rewritten from the manifest)
   and rendered to the root with each link re-based. ``--check`` builds the
   root's instruction files in a temporary folder and checks that build, so a
   CI checkout checks them with no root; where a root exists it must be the
   build. A lone ``m3trik`` clone writes nothing outside itself.
2. The ecosystem sibling loops in ``m3trik/.github/workflows/*.yml`` (a
   ``for repo in ...; do`` naming ``pythontk``), which must list
   :func:`ecosystem_packages` in order.
3. The charter rule: every declared unit present on disk carries its ``AGENTS.md``,
   and the instruction tree keeps its layout and its declared packs, vendored and
   current (``pythontk.AgentInstructions``).
4. Each package's committed operation catalog (``<package>/operations.json``)
   against the declarations it is generated from (``pythontk.OperationCatalog``).
5. The dependency chain the prose states (:data:`CHAIN_STATEMENTS`: the
   workspace's rules and ``docs/CODEBASE_MANIFEST.md``) against the ecosystem
   packages' pyproject dependencies, each direction, through other packages
   too; skipped where a pyproject is absent (a partial checkout).
6. The ``m3trik`` distribution (``m3trik/pyproject.toml``): dependencies only,
   whose closure through the packages' pyprojects is the cascade and the
   products, and which names nothing else (:func:`meta_drift`).

Usage:
    python sync_workspace.py            # write every restatement (idempotent)
    python sync_workspace.py --check    # exit 1 on any drift
"""

import argparse
import json
import posixpath
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

# This file: _scripts/m3trik/scripts/sync_workspace.py
M3TRIK = Path(__file__).resolve().parents[1]
WORKSPACE = M3TRIK.parent
#: This repo's declared unit path: what the workspace's layout names its
#: folder, whatever a clone or a worktree of it happens to be called.
UNIT = "m3trik"
MANIFEST = M3TRIK / "workspace.json"
#: The workspace's rules, written once: the root ``AGENTS.md`` is its render.
ROOT_SOURCE = M3TRIK / "agents" / "workspace.md"
ROOT_AGENTS = WORKSPACE / "AGENTS.md"
#: The ``m3trik`` distribution: one install of the cascade and the products.
META = M3TRIK / "pyproject.toml"
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
    (ROOT_SOURCE, "## Ecosystem chain"),
    (M3TRIK / "docs" / "CODEBASE_MANIFEST.md", "The dependency chain is "),
)
#: A code span holding an arrow: one stated chain.
CHAIN_SPAN = re.compile(r"`([^`]*→[^`]*)`")
#: A Markdown link's target.
LINK_TARGET = re.compile(r"(\]\()([^)\s]+)(\))")
#: A target that is no path beside the file: a URL, ``mailto:``, a drive.
LINK_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
#: A requirement's distribution name and its extras: ``name[a,b]>=1``.
REQUIREMENT = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")


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


def _folder(path: Path) -> str:
    """The folder *path* sits in, as a link names it from the workspace root
    (``/``-separated). Inside this repo that is its declared unit path
    (:data:`UNIT`) and the folders under it, whatever a clone or a worktree
    is called; a file at the workspace root, or anywhere else, is ``""``."""
    try:
        inside = path.resolve().parent.relative_to(M3TRIK.resolve()).as_posix()
    except ValueError:
        return ""
    return UNIT if inside == "." else f"{UNIT}/{inside}"


def _link(target: str, start: str) -> str:
    """The workspace-relative *target* as a link written in the folder *start*."""
    here = [part for part in start.split("/") if part]
    there = target.split("/")
    shared = 0
    while shared < min(len(here), len(there) - 1) and here[shared] == there[shared]:
        shared += 1
    return "/".join([".."] * (len(here) - shared) + there[shared:])


def render_dispatch(data: Optional[dict] = None, start: str = "") -> str:
    """The Dispatch table, one row per unit in manifest order, its links
    written for a file in the folder *start* (default: the workspace root)."""
    rows = ["| Unit | Domain |", "|:---|:---|"]
    for unit in (data or load())["units"]:
        path = unit["path"]
        rows.append(f"| [`{path}/`]({_link(f'{path}/AGENTS.md', start)}) | {unit['domain']} |")
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


def dispatch_drift(path: Path = ROOT_SOURCE) -> Optional[str]:
    """Why the Dispatch table in *path* disagrees with the manifest, or None.
    Its links are held to *path*'s own folder: the workspace's rules where
    they are written, or their render at the root."""
    text, _ = _read(path)
    try:
        wanted = splice_dispatch(text, render_dispatch(start=_folder(path)))
    except ValueError as exc:
        return f"{path.name}: {exc}"
    if wanted != text:
        return (
            f"{path.name}: the Dispatch table differs from workspace.json "
            "-- run m3trik/scripts/sync_workspace.py"
        )
    return None


def write_dispatch(path: Path = ROOT_SOURCE) -> bool:
    """Rewrite *path*'s Dispatch table from the manifest; True when it changed."""
    text, crlf = _read(path)
    wanted = splice_dispatch(text, render_dispatch(start=_folder(path)))
    if wanted == text:
        return False
    path.write_bytes((wanted.replace("\n", "\r\n") if crlf else wanted).encode())
    return True


def rebase_links(text: str, start: str) -> str:
    """*text*, written in the folder *start* (workspace-relative), with each
    relative Markdown link written from the workspace root instead. A URL, an
    anchor and a target inside a code span or a fenced block stay as written."""

    def rebase(match: "re.Match[str]") -> str:
        path, mark, fragment = match.group(2).partition("#")
        if not path or path.startswith("/") or LINK_SCHEME.match(path):
            return match.group(0)
        moved = posixpath.normpath(posixpath.join(start, path))
        if path.endswith("/"):
            moved += "/"
        return f"{match.group(1)}{moved}{mark}{fragment}{match.group(3)}"

    lines, fenced = [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            # Odd parts sit inside a code span; a link's own text may hold one.
            parts = line.split("`")
            parts[::2] = [LINK_TARGET.sub(rebase, part) for part in parts[::2]]
            line = "`".join(parts)
        lines.append(line)
    return "\n".join(lines)


def render_root(source: Path = ROOT_SOURCE) -> str:
    """The workspace root's ``AGENTS.md`` as *source* renders it: the same
    rules, each link written from the root."""
    return rebase_links(_read(source)[0], _folder(source))


def _is_render(text: str) -> bool:
    """Whether *text* is a root ``AGENTS.md`` of this workspace: it links into
    the folder its source sits in. Another project's never does, so a file
    that fails this is never overwritten."""
    return f"]({_folder(ROOT_SOURCE)}/" in text


def is_workspace(workspace: Path = WORKSPACE) -> bool:
    """Whether *workspace* is the workspace: the cascade's first package is
    checked out beside this repo, or the folder already holds this
    workspace's root ``AGENTS.md``. Any other folder only happens to hold a
    clone: nothing is written there, whatever else it holds."""
    if (workspace / load()["cascade"][0] / ".git").exists():
        return True
    root = workspace / "AGENTS.md"
    return root.is_file() and _is_render(_read(root)[0])


def _stub_imports(stub: Path) -> str:
    """*stub*'s text, to seed a build with (the engine keeps whatever else it
    imports); ``""`` when there is none.

    Raises:
        ValueError: It holds rules of its own: they are merged by hand.
    """
    if not stub.is_file():
        return ""
    text = _read(stub)[0]
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines[:1] != ["@AGENTS.md"] or not all(line.startswith("@") for line in lines):
        raise ValueError(
            f"{stub} holds rules of its own: move them into the workspace's rules "
            f"({_folder(ROOT_SOURCE)}/{ROOT_SOURCE.name}), leave '@AGENTS.md', then sync"
        )
    return text


def build_root(folder: Path, source: Path = ROOT_SOURCE, stub: str = "") -> Path:
    """Build the workspace root's instruction files in the empty *folder*: the
    rendered ``AGENTS.md``, then its pointer block, its stub (seeded with
    *stub*, a root's current one, so what else that imports is kept) and its
    packs (``AgentInstructions.sync``). The ``AGENTS.md`` built."""
    folder.mkdir(parents=True, exist_ok=True)
    built = folder / "AGENTS.md"
    built.write_bytes(render_root(source).encode("utf-8"))
    if stub:
        (folder / "CLAUDE.md").write_bytes(stub.encode("utf-8"))
    _instructions().sync(str(folder), str(PACKS), packs=list(load().get("packs", [])), mode="import")
    return built


def _foreign(root: Path) -> str:
    """Why the ``AGENTS.md`` at *root* is left alone: it is another project's."""
    return (
        f"{root}: not this workspace's (it links nothing under {_folder(ROOT_SOURCE)}/), "
        "so it is never overwritten -- move it aside, then run m3trik/scripts/sync_workspace.py"
    )


def root_problems(workspace: Path = WORKSPACE, source: Path = ROOT_SOURCE) -> List[str]:
    """Every way the workspace root's instruction files break the layout as
    their sources build them (in a temporary folder, so a checkout with no
    root checks them too), and, where *workspace* is the workspace, a root
    ``AGENTS.md`` that is not that build."""
    agent = _instructions()
    with tempfile.TemporaryDirectory() as tmp:
        built = build_root(Path(tmp) / "root", source)
        result = agent.check(str(built.parent), source=str(PACKS), standard=str(STANDARD), mode="import")
        wanted = _read(built)[0]
    out = [f"the workspace root, as {source.name} builds it: {p['message']}" for p in result["problems"]]
    root = workspace / "AGENTS.md"
    if not root.is_file() or not is_workspace(workspace):
        return out
    text = _read(root)[0]
    if not _is_render(text):
        out.append(_foreign(root))
    elif text != wanted:
        out.append(
            f"{root.name}: the workspace root's is not the render of "
            f"{_folder(source) or '.'}/{source.name} -- edit that source (never the "
            "render), then run m3trik/scripts/sync_workspace.py"
        )
    return out


def write_root(workspace: Path = WORKSPACE, source: Path = ROOT_SOURCE) -> List[str]:
    """Bring *workspace*'s root instruction files in line with their build:
    ``AGENTS.md``, the ``CLAUDE.md`` stub (what else it imports is kept) and
    the packs, each written only where it differs and in the newlines it has;
    a pack file the root no longer takes is removed. Nothing else is touched:
    the build is made in a temporary folder and copied over, so no other
    folder of the workspace is walked or written. The files written and removed.

    Raises:
        ValueError: *workspace* is not the workspace (:func:`is_workspace`),
            its ``AGENTS.md`` is another project's, or its ``CLAUDE.md`` holds
            rules of its own. Nothing is written.
    """
    if not is_workspace(workspace):
        raise ValueError(
            f"{workspace} is not the workspace (no {load()['cascade'][0]} beside this "
            "repo): nothing is written outside this repo"
        )
    root = workspace / "AGENTS.md"
    if root.is_file() and not _is_render(_read(root)[0]):
        raise ValueError(_foreign(root))
    seed = _stub_imports(workspace / "CLAUDE.md")
    packs_dir = _instructions().PACKS_DIR
    changed = []
    with tempfile.TemporaryDirectory() as tmp:
        built = build_root(Path(tmp) / "root", source, seed).parent
        for made in sorted(path for path in built.rglob("*") if path.is_file()):
            target = workspace / made.relative_to(built)
            wanted = _read(made)[0]
            text, crlf = _read(target) if target.is_file() else (None, False)
            if text == wanted:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((wanted.replace("\n", "\r\n") if crlf else wanted).encode("utf-8"))
            changed.append(str(target))
        taken = {path.name for path in (built / packs_dir).glob("*.md")}
    for stale in sorted((workspace / packs_dir).glob("*.md")):
        if stale.name not in taken:
            stale.unlink()
            changed.append(str(stale))
    return changed


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


def _units(workspace: Path = WORKSPACE) -> List[dict]:
    """The declared units to look for in *workspace*: all of them where it is
    the workspace (:func:`is_workspace`), else this repo's own. A lone clone's
    parent is someone's folder, and a ``www`` or ``server`` there is theirs:
    never checked as a unit, never written."""
    units = load()["units"]
    if is_workspace(workspace):
        return list(units)
    return [unit for unit in units if unit["path"].split("/")[0] == UNIT]


def missing_charters(workspace: Path = WORKSPACE) -> List[str]:
    """Declared units present on disk that carry no ``AGENTS.md``."""
    return [
        unit["path"]
        for unit in _units(workspace)
        if (workspace / unit["path"]).is_dir()
        and not (workspace / unit["path"] / "AGENTS.md").is_file()
    ]


def instruction_roots(workspace: Path = WORKSPACE) -> List[Tuple[Path, List[str], str]]:
    """``(folder, packs, mode)`` for each instruction root present: the
    workspace root where it holds its ``AGENTS.md`` (its packs imported once,
    ``import``; :func:`write_root` builds a missing one first) and every
    declared unit (its packs added by its own hook in a session rooted there,
    ``hook``). Beside a lone clone, only this repo's own units (:func:`_units`)."""
    data = load()
    rooted = (workspace / "AGENTS.md").is_file() and is_workspace(workspace)
    roots = [(workspace, list(data.get("packs", [])), "import")] if rooted else []
    for unit in _units(workspace):
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
    """Bring every unit's instruction root in line (``AgentInstructions.sync``);
    the files written. The workspace root's are :func:`write_root`'s."""
    agent = _instructions()
    written = []
    for folder, packs, mode in instruction_roots(workspace):
        if folder == workspace:
            continue
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


def _requirement(text: str) -> Tuple[str, List[str]]:
    """A requirement's distribution name (lower case, ``_`` for ``-`` and
    ``.``) and the extras it asks for."""
    match = REQUIREMENT.match(text)
    if not match:
        return "", []
    extras = [extra.strip() for extra in (match.group(2) or "").split(",") if extra.strip()]
    return re.sub(r"[-_.]+", "_", match.group(1)).lower(), extras


def meta_drift(
    meta: Path = META, workspace: Path = WORKSPACE, data: Optional[dict] = None
) -> List[str]:
    """Where the ``m3trik`` distribution (*meta*, a pyproject) is not one
    install of the cascade and the products: a package it leaves out or adds
    (followed through the packages' pyprojects, each extra it asks for
    included), a requirement of its own, in an extra too, that is no ecosystem
    package (it is installed into a host's Python, where a Qt binding would
    shadow the host's), an extra a package does not declare, or code of its
    own (it holds dependencies only)."""
    layers = _layers()
    data = data or load()
    table = {}  # distribution name -> (unit, its pyproject)
    for unit in ecosystem_packages(data):
        if (workspace / unit / "pyproject.toml").is_file():
            read = layers.pyproject(workspace / unit)
            table[_requirement(read.get("project", {}).get("name", unit))[0]] = (unit, read)
    own = layers.pyproject(meta.parent)
    drift = []
    tool = own.get("tool", {}).get("setuptools", {})
    if tool.get("packages") != [] or tool.get("py-modules") != []:
        drift.append(
            f"{meta.name}: the distribution holds dependencies only -- declare "
            "[tool.setuptools] packages = [] and py-modules = []"
        )
    def undeclared(unit: str, read: dict, extras: Sequence[str]) -> List[str]:
        declared = read.get("project", {}).get("optional-dependencies", {})
        return [
            f"{meta.name}: asks {unit} for the extra {extra!r}, which it does not declare"
            for extra in extras
            if extra not in declared
        ]

    for extra, texts in own.get("project", {}).get("optional-dependencies", {}).items():
        for text in texts:
            name, asked = _requirement(text)
            if name in table:
                drift += undeclared(*table[name], asked)
            else:
                drift.append(
                    f"{meta.name}: its extra {extra!r} requires {text.strip()!r}, no ecosystem package"
                )
    installed: Set[str] = set()
    queue = [(text, None) for text in own.get("project", {}).get("dependencies", [])]
    while queue:
        text, parent = queue.pop()
        name, extras = _requirement(text)
        if name not in table:
            if parent is None:
                drift.append(
                    f"{meta.name}: requires {text.strip()!r}, no ecosystem package "
                    "(the distribution adds no dependency of its own)"
                )
            continue
        unit, read = table[name]
        wanted = (unit, tuple(sorted(extras)))
        if wanted in installed:
            continue
        installed.add(wanted)
        project = read.get("project", {})
        optional = project.get("optional-dependencies", {})
        drift += undeclared(unit, read, extras)
        queue += [(dep, unit) for dep in project.get("dependencies", [])]
        queue += [(dep, unit) for extra in extras for dep in optional.get(extra, [])]
    units = {unit for unit, _extras in installed}
    expected = set(data["cascade"]) | set(products(data))
    drift += [
        f"{meta.name}: does not install {unit} (the cascade and the products)"
        for unit in sorted(expected - units)
    ]
    drift += [
        f"{meta.name}: installs {unit}, neither a cascade package nor a product"
        for unit in sorted(units - expected)
    ]
    return drift


def unclassified(workspace: Path = WORKSPACE) -> List[str]:
    """Child repos (a folder holding ``.git``, not a hidden one: tooling
    state, like ``.claude``'s ledger history, is no unit) with no manifest
    entry. None beside a lone clone: the repos there are someone else's."""
    if not is_workspace(workspace):
        return []
    declared = {unit["path"] for unit in load()["units"]}
    return sorted(
        child.name
        for child in workspace.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and (child / ".git").exists()
        and child.name not in declared
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
    # The Dispatch table first: the root's build renders the file that holds it.
    if args.check:
        drift = dispatch_drift()
        if drift:
            failures.append(drift)
    else:
        try:
            changed = write_dispatch()
        except ValueError as exc:
            failures.append(f"{ROOT_SOURCE.name}: {exc}")
        else:
            print(f"[{'WROTE' if changed else 'OK'}] dispatch table")
    try:
        if args.check:
            failures += root_problems()
            if not (ROOT_AGENTS.is_file() and is_workspace()):
                print("[SKIP] root: no workspace root here (its build is checked)")
            failures += instruction_problems()
            failures += catalog_problems()
        else:
            written = []
            if is_workspace():
                written += write_root()
            else:
                print("[SKIP] root: this clone stands alone, so nothing is written outside it")
            for path in written + write_instructions() + write_catalogs():
                print(f"[WROTE] {path}")
    except ImportError as exc:
        print(f"[SKIP] instructions: pythontk is not importable here ({exc})")
    except ValueError as exc:
        failures.append(f"instructions: {exc}")
    failures += workflow_drift()
    absent = [p for p in ecosystem_packages() if not (WORKSPACE / p / "pyproject.toml").is_file()]
    for path, anchor in CHAIN_STATEMENTS:
        if not path.is_file() or absent:
            print(f"[SKIP] chain: no {path.name if not path.is_file() else absent} here")
            continue
        failures += chain_drift(path, anchor)
    if absent or not META.is_file():
        print(f"[SKIP] m3trik distribution: no {absent or META.name} here")
    else:
        failures += meta_drift()
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
