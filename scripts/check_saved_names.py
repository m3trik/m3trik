#!/usr/bin/python
# coding=utf-8
"""Freeze the names saved data reads, so a move cannot orphan a user's settings
or a scene's records.

CODE_STANDARD section 5, keep saved names: a panel's settings live under its
window's name -- the ``.ui`` file's stem -- and each widget's ``objectName``
(uitk's ``StateManager``: ``QSettings(org, <stem>)``, key ``<objectName>/<signal>``),
and presets store the same names; a scene stores its records under their
``SceneRecords`` keys, and an older scene under each key's ``renamed_from``
names. A move changes paths, never these, so they are frozen by name, not by
path: a ``.ui`` may move between packages (a panel into tentacle, two twins into
one shared panel) and pass, while a stem or a widget name that disappears from
every package fails, and so does a record key or an old name (a rename passes
when the old key goes into ``renamed_from``). A panel renamed or merged into
another passes the same way: tentacle's ``slots.tools.RENAMED_FROM`` lists it
under the tool that took its name, whose ``.ui`` carries each of its widget
names (under its new name where the table renames it), and whose launcher
carries the users' values across (uitk's ``PanelRenames``). A name two former
panels of one tool both keep would merge their values on one key, so it passes
only when ``RENAMED_HOSTS`` puts the two in separate hosts (each stored values
in its own host's store) or the table renames one.

New names are not failures; ``--update`` freezes them, and its diff is the
review, as is the reason for a name that goes on purpose. A partial checkout
judges only what it can see: a stem when every package that carried it at the
freeze is present, the record keys when pythontk is, and ``--update`` keeps
each frozen entry it cannot see. A run that names packages judges only the
stems they carry, at the freeze or now, and the record keys when pythontk is
among them, so another package's uncommitted edit never stops its release. A baseline describes the workspace it was
frozen from, so ``--workspace`` reads that workspace's own ``m3trik/scripts``
copy; a workspace that carries saved names without one fails.

Usage:
    python check_saved_names.py [--check] [pkg ...]   # exit 1 when a frozen name is gone
    python check_saved_names.py --update              # freeze the current names
"""

import argparse
import ast
import json
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Dict, List, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]
BASELINE = SCRIPTS / "saved_names_baseline.json"
#: The record registry, workspace-relative: every key a scene stores is declared there.
RECORDS_FILE = "pythontk/pythontk/core_utils/engines/scene_export/scene_records.py"
SKIP_DIRS = {"__pycache__", "templates", "temp_tests"}
#: The panel-rename table, workspace-relative: ``RENAMED_FROM = {tool: {former
#: panel: {former widget name: its name now}}}``, read as a literal.
RENAMES_FILE = "tentacle/tentacle/slots/tools/__init__.py"
RENAMES_NAME = "RENAMED_FROM"
#: ``{former panel: (hosts it served,)}`` beside it, read as a literal too.
RENAMED_HOSTS_NAME = "RENAMED_HOSTS"


def _registry_set() -> Sequence[str]:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import sync_workspace

    return sync_workspace.ecosystem_packages()


def ui_names(path: Path) -> List[str]:
    """Every widget ``name`` in a ``.ui`` file, the window's own included."""
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError):
        return []
    return sorted({w.get("name") for w in root.iter("widget") if w.get("name")})


#: ``SceneRecords`` attributes naming keys an older scene or file may still hold.
RETIRED_NAMES = ("RETIRED", "RETIRED_BLOCKS")


def record_keys(path: Path) -> List[str]:
    """The keys a scene may store records under: each ``RecordSpec("<key>",
    ...)`` in ``SceneRecords``, a wrapped one (a deprecated record) included,
    with its ``renamed_from`` names, and the retired keys it still clears."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    keys = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "SceneRecords"):
            continue
        for stmt in node.body:
            value = getattr(stmt, "value", None)
            if value is None:
                continue
            targets = getattr(stmt, "targets", None) or [getattr(stmt, "target", None)]
            if any(getattr(t, "id", None) in RETIRED_NAMES for t in targets):
                keys.update(_strings(value))
                continue
            for call in ast.walk(value):
                if (
                    isinstance(call, ast.Call)
                    and getattr(call.func, "id", None) == "RecordSpec"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                ):
                    keys.add(call.args[0].value)
                    for keyword in call.keywords:
                        if keyword.arg == "renamed_from":
                            keys.update(_strings(keyword.value))
    return sorted(keys)


def _strings(node: ast.AST) -> List[str]:
    """The string constants a literal string, tuple or list holds."""
    items = node.elts if isinstance(node, (ast.Tuple, ast.List)) else [node]
    return [
        item.value
        for item in items
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    ]


def _module_literal(path: Path, name: str) -> object:
    """The literal *path* assigns to *name* at module level, else None. Parsed,
    never imported: the gate runs without the package's dependencies."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if any(getattr(t, "id", None) == name for t in targets):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                return None
    return None


def panel_renames(path: Path) -> Dict[str, list]:
    """``{former panel: [tool, {former widget name: its name now}]}`` from the
    ``RENAMED_FROM`` literal *path* declares ({} when it holds none)."""
    table = _module_literal(path, RENAMES_NAME) or {}
    return {
        former: [tool, dict(widgets or {})]
        for tool, formers in table.items()
        for former, widgets in formers.items()
    }


def renamed_hosts(path: Path) -> Dict[str, list]:
    """``{former panel: [hosts it served]}`` from the ``RENAMED_HOSTS`` literal
    *path* declares ({} when it holds none)."""
    table = _module_literal(path, RENAMED_HOSTS_NAME) or {}
    return {former: sorted(hosts) for former, hosts in table.items()}


def scan(
    workspace: Path = WORKSPACE, packages: Optional[Sequence[str]] = None
) -> Dict[str, object]:
    """``{"ui": {stem: [names]}, "homes": {stem: [packages]}, "records":
    [keys], "renamed": {former stem: [tool, {name: name now}]},
    "renamed_hosts": {former stem: [hosts]}, "present": [packages]}`` over every
    package: a stem's names are the union of every ``.ui`` that carries it,
    wherever."""
    ui: Dict[str, set] = {}
    homes: Dict[str, set] = {}
    present = []
    for package in packages or _registry_set():
        root = workspace / package / package
        if not root.is_dir():
            continue  # partial checkout
        present.append(package)
        for path in sorted(root.rglob("*.ui")):
            if SKIP_DIRS & set(path.relative_to(root).parts):
                continue
            ui.setdefault(path.stem, set()).update(ui_names(path))
            homes.setdefault(path.stem, set()).add(package)
    registry = records_file(workspace)
    return {
        "ui": {stem: sorted(names) for stem, names in sorted(ui.items())},
        "homes": {stem: sorted(pkgs) for stem, pkgs in sorted(homes.items())},
        "records": record_keys(registry) if registry else None,
        "renamed": panel_renames(workspace / RENAMES_FILE),
        "renamed_hosts": renamed_hosts(workspace / RENAMES_FILE),
        "present": present,
    }


def records_file(workspace: Path) -> Optional[Path]:
    """The module declaring ``SceneRecords``: its known path, else wherever in
    pythontk it now lives; None when no checked-out pythontk declares it."""
    known = workspace / RECORDS_FILE
    if known.is_file():
        return known
    root = workspace / "pythontk" / "pythontk"
    for path in sorted(root.rglob("*.py")) if root.is_dir() else ():
        try:
            if "class SceneRecords" in path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                return path
        except OSError:
            continue
    return None


def lost(
    baseline: Dict[str, object],
    current: Dict[str, object],
    packages: Optional[Sequence[str]] = None,
) -> List[str]:
    """Each frozen name *current* no longer carries, judged where *current*
    can see: a stem whose frozen packages are all present, the record keys
    when a checked-out pythontk declares ``SceneRecords``. Naming *packages*
    narrows it to the stems they carry, at the freeze or now, and to the
    record keys when pythontk is among them."""
    present = set(current["present"])
    homes = baseline.get("homes", {})
    run = None if not packages else set(packages)
    found = []
    for stem, names in baseline.get("ui", {}).items():
        if not set(homes.get(stem, ())) <= present:
            continue
        carriers = set(homes.get(stem, ())) | set(current["homes"].get(stem, ()))
        if run is not None and not carriers & run:
            continue
        now = current["ui"].get(stem)
        renamed = (current.get("renamed") or {}).get(stem)
        if now is None and renamed and renamed[0] in current["ui"]:
            found += _lost_into(stem, names, renamed, current["ui"][renamed[0]])
            continue
        if now is None:
            found.append(f"{stem}.ui: (the whole panel)")
            continue
        found += [f"{stem}.ui: {name}" for name in names if name not in set(now)]
    found += _kept_twice(baseline, current, run)
    if current["records"] is not None and (run is None or "pythontk" in run):
        found += [
            f"SceneRecords: {key}"
            for key in baseline.get("records", [])
            if key not in set(current["records"])
        ]
    return found


def _kept_twice(baseline, current, run) -> List[str]:
    """The names two gone panels of one tool both keep (as spelled now) while
    ``RENAMED_HOSTS`` puts them in no separate hosts: their users' values would
    land on one key of the tool's store, the second carry losing to the first."""
    renamed = current.get("renamed") or {}
    hosts = current.get("renamed_hosts") or {}
    present = set(current["present"])
    by_tool: Dict[str, list] = {}
    for stem, names in baseline.get("ui", {}).items():
        stem_homes = set(baseline.get("homes", {}).get(stem, ()))
        if stem in current["ui"] or stem not in renamed or not stem_homes <= present:
            continue
        if run is not None and not stem_homes & run:
            continue
        tool, widgets = renamed[stem]
        kept = {widgets.get(name, name) for name in names if name != stem}
        by_tool.setdefault(tool, []).append((stem, kept))
    found = []
    for tool, formers in sorted(by_tool.items()):
        formers.sort()
        for i, (first, kept_first) in enumerate(formers):
            for second, kept_second in formers[i + 1 :]:
                a, b = set(hosts.get(first, ())), set(hosts.get(second, ()))
                if a and b and not a & b:
                    continue  # per-host alternatives: never one store
                found += [
                    f"{tool}.ui: {name} (kept by {first} and {second}, which "
                    "RENAMED_HOSTS puts in no separate hosts: declare their hosts "
                    "or rename one)"
                    for name in sorted(kept_first & kept_second)
                ]
    return found


def _lost_into(stem: str, names, renamed, tool_names) -> List[str]:
    """The names of the gone panel *stem* its tool (``renamed`` = ``[tool,
    {name: name now}]``) does not carry. A name that is the panel's own is its
    root widget, which stores nothing: the window takes the panel's name."""
    tool, widgets = renamed
    carried = set(tool_names)
    return [
        f"{stem}.ui: {name} (renamed into {tool}.ui as {widgets.get(name, name)})"
        for name in names
        if name != stem and widgets.get(name, name) not in carried
    ]


def merged(baseline: Dict[str, object], current: Dict[str, object]) -> Dict[str, object]:
    """*current*, keeping each frozen entry it cannot see: a stem whose frozen
    packages are not all present keeps its frozen names (with any it now
    carries), and the record keys stay when no pythontk declares them."""
    present = set(current["present"])
    ui = dict(current["ui"])
    homes = dict(current["homes"])
    for stem, names in baseline.get("ui", {}).items():
        frozen_homes = baseline.get("homes", {}).get(stem, [])
        if not set(frozen_homes) <= present:
            ui[stem] = sorted(set(names) | set(ui.get(stem, ())))
            homes[stem] = sorted(set(frozen_homes) | set(homes.get(stem, ())))
    records = current["records"]
    return {
        "ui": dict(sorted(ui.items())),
        "homes": dict(sorted(homes.items())),
        "records": baseline.get("records", []) if records is None else records,
        "present": current["present"],
    }


def baseline_file(workspace: Path = WORKSPACE) -> Path:
    """The baseline frozen from *workspace*: its own copy of this one."""
    return workspace / BASELINE.relative_to(WORKSPACE)


def load_baseline(path: Path = BASELINE) -> Dict[str, object]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def write_baseline(current: Dict[str, object], path: Path = BASELINE) -> None:
    data = {
        "_doc": (
            "The names saved data reads, frozen by name (check_saved_names.py): "
            "each .ui stem's widget names and the SceneRecords keys with their "
            "renamed_from names. A name that "
            "goes on purpose leaves with a reason in the commit. Rewrite: "
            "check_saved_names.py --update."
        )
    }
    data.update(
        {
            k: v
            for k, v in current.items()
            if k not in ("present", "renamed", "renamed_hosts")
        }
    )
    data["records"] = current["records"] or []
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="the default")
    mode.add_argument("--update", action="store_true", help="freeze the current names")
    parser.add_argument(
        "--workspace", type=Path, default=WORKSPACE, help="the monorepo root"
    )
    parser.add_argument(
        "packages",
        nargs="*",
        help="the run's packages: checked when one is in the registry set "
        "(the scan always reads every package -- a move lands in two)",
    )
    args = parser.parse_args(argv)
    if args.packages and not set(args.packages) & set(_registry_set()):
        print("Saved names: none of these packages is in the registry set.")
        return 0

    current = scan(args.workspace)
    frozen_file = baseline_file(args.workspace)
    if args.update:
        current = merged(load_baseline(frozen_file), current)
        frozen_file.parent.mkdir(parents=True, exist_ok=True)
        write_baseline(current, frozen_file)
        print(
            f"[WROTE] {frozen_file}: {len(current['ui'])} panel(s), "
            f"{len(current['records'] or [])} record key(s)"
        )
        return 0

    if not frozen_file.is_file() and (current["ui"] or current["records"]):
        print(
            f"[FAIL] saved names: {len(current['ui'])} panel(s) and "
            f"{len(current['records'] or [])} record key(s) but no baseline at "
            f"{frozen_file}: freeze them with --update"
        )
        return 1
    baseline = load_baseline(frozen_file)
    gone = lost(baseline, current, args.packages)
    for line in gone:
        print(f"[FAIL] {line}")
    frozen = sum(len(v) for v in baseline.get("ui", {}).values())
    print(
        f"[{'FAIL' if gone else 'OK'}] saved names: {len(gone)} lost, {frozen} frozen"
    )
    return 1 if gone else 0


if __name__ == "__main__":
    sys.exit(main())
