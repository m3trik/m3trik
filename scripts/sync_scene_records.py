#!/usr/bin/python
# coding=utf-8
"""Derive everything downstream of ``ptk.SceneRecords`` -- and fail when it drifts.

``pythontk.core_utils.scene_records.SceneRecords`` is the one declaration of
every tool-authored scene record (key, scope, version, kind, owner, readers,
description).  Two things outside pythontk used to restate it by hand and
drifted within weeks (the owner doc's channel tables were missing seven
records when measured 2026-09-18):

1. **The records table in the owner doc.**  ``mayatk/docs/data_nodes.md``
   carries a marker-spliced region (``<!-- scene-records:begin -->`` ...
   ``<!-- scene-records:end -->``) rendered from ``SceneRecords.describe()``.
   Everything outside the markers is hand-written; a missing marker pair is
   refused rather than guessed.
2. **The Unity importers' channel list.**  ``unitytk``'s
   ``UnitytkSettings.cs`` names one import channel per record it reads
   (``Audio, // "audio_manifest" channel``).  That set must equal the
   deliverable records declared with the ``"unity"`` consumer -- a record
   Unity reads but pythontk does not declare (or the reverse) is a contract
   nobody owns.
3. **The two DCC producer tables.**  ``mtk.FbxUtils.PRODUCERS`` and
   ``btk.FbxUtils.PRODUCERS`` must name the same records, except the ones
   :data:`PRODUCER_DIVERGENCES` ledgers with a reason (read from source by
   AST, so neither DCC needs to be importable here).

Usage:
    python sync_scene_records.py            # rewrite the doc region (idempotent)
    python sync_scene_records.py --check    # exit 1 on doc drift or a channel mismatch
"""

import argparse
import re
import sys
from pathlib import Path

# This file: _scripts/m3trik/scripts/sync_scene_records.py -> repo root is parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "mayatk" / "docs" / "data_nodes.md"
UNITY_SETTINGS = REPO_ROOT / "unitytk" / "unitytk" / "templates" / "UnitytkSettings.cs"
BEGIN = "<!-- scene-records:begin -->"
END = "<!-- scene-records:end -->"

FBX_UTILS = {
    "mayatk": REPO_ROOT / "mayatk" / "mayatk" / "env_utils" / "fbx_utils.py",
    "blendertk": REPO_ROOT / "blendertk" / "blendertk" / "env_utils" / "fbx_utils.py",
}
#: Records one DCC produces and the other deliberately does not: spec attribute
#: name -> (the DCC that lacks it, why). Delete a row when the port lands.
PRODUCER_DIVERGENCES = {
    "AUDIO": ("blendertk", "the Blender audio panel is VSE-only; port pending"),
}

#: ``Audio,      // "audio_manifest" channel -> AudioEventController``
_UNITY_CHANNEL = re.compile(r'//\s*"(?P<key>\w+)"\s+channel\b')


def _records():
    """``SceneRecords`` from the sibling pythontk checkout (not an installed copy)."""
    checkout = str(REPO_ROOT / "pythontk")
    if checkout not in sys.path:
        sys.path.insert(0, checkout)
    from pythontk.core_utils.scene_records import SceneRecords

    return SceneRecords


def render_table(records=None) -> str:
    """The generated region's body: one row per declared record."""
    records = records or _records()
    lines = [
        "| Record | Carrier | Version | Kind | Owner | Reads | Read by | Holds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    names = {"private": "`data_internal`", "deliverable": "`data_export`"}
    for row in records.describe():
        holds = row["description"]
        if row["deprecated_by"]:
            holds += f" -- *legacy: superseded by `{row['deprecated_by']}`*"
        lines.append(
            "| `{key}` | {carrier} | {version} | {kind} | {owner} | {reads} | {consumers} | {holds} |".format(
                key=row["key"],
                carrier=names[row["scope"]],
                version=row["version"]
                if row["envelope"]
                else f"{row['version']} (bare)",
                kind=row["kind"],
                owner=row["owner"],
                reads=", ".join(f"`{k}`" for k in row["after"]) or "--",
                consumers=", ".join(row["consumers"]) or "--",
                holds=holds.replace("|", "/"),
            )
        )
    return "\n".join(lines)


def splice(text: str, body: str) -> str:
    """*text* with the marker region replaced by *body*; refuses a missing pair."""
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"{DOC.name} has no '{BEGIN}' ... '{END}' region")
    return text[: start + len(BEGIN)] + "\n" + body + "\n" + text[end:]


def unity_mismatch(records=None) -> dict:
    """``{"undeclared": [...], "unread": [...]}`` -- channels Unity reads that no
    record declares for it, and records declared for Unity it does not read."""
    records = records or _records()
    read = set(_UNITY_CHANNEL.findall(UNITY_SETTINGS.read_text(encoding="utf-8")))
    declared = {s.key for s in records.deliverable() if "unity" in s.consumers}
    return {
        "undeclared": sorted(read - declared),
        "unread": sorted(declared - read),
    }


def producer_specs(path: Path) -> set:
    """The ``SceneRecords`` attribute names a ``FbxUtils.PRODUCERS`` table keys on."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = getattr(node, "target", None) or (
            node.targets[0] if isinstance(node, ast.Assign) and node.targets else None
        )
        if getattr(target, "id", None) != "PRODUCERS":
            continue
        value = getattr(node, "value", None)
        if isinstance(value, ast.Dict):
            return {k.attr for k in value.keys if isinstance(k, ast.Attribute)}
    raise ValueError(f"no PRODUCERS table in {path}")


def producer_parity() -> list:
    """Unledgered differences between the two DCC producer tables, as lines."""
    tables = {dcc: producer_specs(path) for dcc, path in FBX_UTILS.items()}
    problems = []
    for spec in sorted(set().union(*tables.values())):
        missing = [dcc for dcc, specs in tables.items() if spec not in specs]
        ledgered = PRODUCER_DIVERGENCES.get(spec, (None,))[0]
        for dcc in missing:
            if dcc != ledgered:
                problems.append(f"{dcc} does not produce SceneRecords.{spec}")
    for spec, (dcc, _why) in PRODUCER_DIVERGENCES.items():
        if spec in tables[dcc]:
            problems.append(f"stale ledger row: {dcc} now produces SceneRecords.{spec}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="exit 1 on drift")
    args = parser.parse_args(argv)

    records = _records()
    raw = DOC.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    wanted = splice(text, render_table(records))
    failed = False
    if wanted != text:
        if args.check:
            print(
                f"DRIFT: {DOC.relative_to(REPO_ROOT)} records table is stale;"
                " run sync_scene_records.py"
            )
            failed = True
        else:
            DOC.write_bytes(wanted.replace("\n", nl).encode("utf-8"))
            print(f"wrote {DOC.relative_to(REPO_ROOT)}")
    for problem in producer_parity():
        print(f"PRODUCERS: {problem}")
        failed = True
    mismatch = unity_mismatch(records)
    for kind, keys in mismatch.items():
        for key in keys:
            print(f"UNITY {kind.upper()}: {key}")
            failed = True
    if not failed:
        print(
            f"in sync: {len(records.all())} records, "
            f"{sum(1 for s in records.deliverable() if 'unity' in s.consumers)} read by Unity"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
