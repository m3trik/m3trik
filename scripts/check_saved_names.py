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
when the old key goes into ``renamed_from``).

New names are not failures; ``--update`` freezes them, and its diff is the
review, as is the reason for a name that goes on purpose. A partial checkout
judges only what it can see: a stem when every package that carried it at the
freeze is present, the record keys when pythontk is, and ``--update`` keeps
each frozen entry it cannot see. A baseline describes the workspace it was
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


def record_keys(path: Path) -> List[str]:
    """The keys a scene may store records under: each ``RecordSpec("<key>",
    ...)`` in ``SceneRecords``, with its ``renamed_from`` names."""
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
            if (
                isinstance(value, ast.Call)
                and getattr(value.func, "id", None) == "RecordSpec"
                and value.args
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                keys.add(value.args[0].value)
                for keyword in value.keywords:
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


def scan(
    workspace: Path = WORKSPACE, packages: Optional[Sequence[str]] = None
) -> Dict[str, object]:
    """``{"ui": {stem: [names]}, "homes": {stem: [packages]}, "records":
    [keys], "present": [packages]}`` over every package: a stem's names are the
    union of every ``.ui`` that carries it, wherever."""
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


def lost(baseline: Dict[str, object], current: Dict[str, object]) -> List[str]:
    """Each frozen name *current* no longer carries, judged where *current*
    can see: a stem whose frozen packages are all present, the record keys
    when a checked-out pythontk declares ``SceneRecords``."""
    present = set(current["present"])
    homes = baseline.get("homes", {})
    found = []
    for stem, names in baseline.get("ui", {}).items():
        if not set(homes.get(stem, ())) <= present:
            continue
        now = current["ui"].get(stem)
        if now is None:
            found.append(f"{stem}.ui: (the whole panel)")
            continue
        found += [f"{stem}.ui: {name}" for name in names if name not in set(now)]
    if current["records"] is not None:
        found += [
            f"SceneRecords: {key}"
            for key in baseline.get("records", [])
            if key not in set(current["records"])
        ]
    return found


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
    data.update({k: v for k, v in current.items() if k != "present"})
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
    gone = lost(baseline, current)
    for line in gone:
        print(f"[FAIL] {line}")
    frozen = sum(len(v) for v in baseline.get("ui", {}).values())
    print(
        f"[{'FAIL' if gone else 'OK'}] saved names: {len(gone)} lost, {frozen} frozen"
    )
    return 1 if gone else 0


if __name__ == "__main__":
    sys.exit(main())
