#!/usr/bin/python
# coding=utf-8
"""Export unitytk's samples from their recipes -- and fail when they are stale.

A unitytk feature's sample is one set of content with three uses: what a user
imports from the Package Manager to try the feature, what its demo scene is
built from, and what its Edit Mode tests check. It is a plain delivery in
``com.m3trik.unitytk/Samples~/<Sample>/`` (synthetic, client-free, small),
made the way a user makes one: a recipe (``unity_samples/<feature>.py``)
builds a scene through the producer's public API and exports it through the
Scene Exporter. unitytk never runs a producer and no producer imports
unitytk: this workspace script joins them.

**Maya is the canonical producer.** One producer per sample keeps one file of
record: Maya is where the shot tools, the Scene Exporter and the records were
first written, and Blender mirrors mayatk by name and behaviour, so a sample a
Blender export would also satisfy is proven by the workspace's end-to-end
suite (Blender parity), not by a second copy here.

The recipes run in ONE owned headless mayapy this script launches (never a
Maya a person opened), each in a new scene, exporting into a temp folder
(``ptk.TempArtifacts``). An FBX's bytes are not reproducible (the writer
stamps its time), so staleness is semantic: each generated file's committed
copy and its fresh export are described alike by what the sample is FOR
(:func:`describe`: the records its feature reads, as the recipe's
``RECORDS`` names them, their JSON parsed; the take names and windows; each
take's animated values; the node hierarchy; each mesh's counts; a digest of
each embedded file's bytes) and compared. The ``handoff`` record is
never part of it: it is the contract's prose and the producer's provenance,
held by pythontk's own tests, so a wording edit there is no sample drift. Write mode copies a fresh file in only when its
description changed, so a rerun on an unchanged recipe touches nothing. A
file at the top of a sample folder no export wrote (and a ``.meta`` whose
file is gone) is drift too, removed in write mode; the sample's own code
(:data:`SAMPLE_SOURCES`) and its subfolders are kept.

Also written: ``package.json``'s ``samples`` entries, one per recipe (its
display name, description and path), never by hand; and a ``.meta`` beside
each generated file (Unity's rule: every file ships its meta), made once with
a fresh GUID and kept after, so references to the file hold.

**Where it runs**: locally and in the release gate (``push.ps1``), on a
machine with Maya; never in the Maya-less CI. Without Maya it does not report
green: it says why and exits 2.

Usage:
    python sync_unity_samples.py              # export, write what changed (idempotent)
    python sync_unity_samples.py --check      # exit 1 on drift, 2 when it cannot run
    python sync_unity_samples.py --describe   # print the committed samples' descriptions
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_public_hygiene as hygiene  # noqa: E402  -- the machine-path pattern
import sync_scene_records as records  # noqa: E402  -- the shared paths and sync_text

REPO_ROOT = records.REPO_ROOT
#: The recipes, one module per sample.
RECIPES = SCRIPTS / "unity_samples"
#: The package's samples folder (Unity imports no ``~`` folder; the Package
#: Manager copies a sample out of it on request).
SAMPLES = "Samples~"
#: The workspace checkouts the producer's interpreter imports from.
CHECKOUTS = ("pythontk", "uitk", "mayatk")
#: Seconds the one mayapy run may take.
TIMEOUT = 900
#: What the one mayapy's environment adds to the inherited one: its teardown
#: crashed after the work (``os._exit`` still runs every DLL's detach; the
#: driver now leaves through ``ptk.ProcessExit.hard_exit``), and Maya's crash handler
#: then saved the open scene as ``<scene>[Recovered-...].ma`` in the user's
#: temp folder on every run. Maya reads this at launch (measured, Maya 2025: set
#: from the driver it saves the scene still), so it goes in the child's env.
#: ``MAYA_DISABLE_CER``: a crash that still happens opens no Error Report
#: dialog for the user to close (measured 2026-11-12, Maya 2025: none, no dump).
CHILD_ENV = {"MAYA_DEBUG_NO_SAVE_ON_CRASH": "1", "MAYA_DISABLE_CER": "1"}
#: The exit code of a run that could not answer (no Maya): never green.
CANNOT_RUN = 2
SCRIPT = "sync_unity_samples.py"
#: A ``.meta`` this script writes for a generated file Unity has not met yet;
#: the importer's settings are Unity's defaults until a project writes them,
#: given the importer's version (:data:`IMPORTER_META`).
META = "fileFormatVersion: 2\nguid: {guid}\n"
#: What a generated file's ``.meta`` states of its importer, by suffix: its
#: serialized version, so Unity gives it the defaults of a new file. A model's
#: ``.meta`` that names no version reads as one from before the importer had
#: versions, and imports as such -- measured in Unity 6000.3 (2026-11-05): a
#: Legacy rig, whose clips an Animator Controller refuses, and External
#: (Legacy) materials, a ``Materials`` folder and a ``.fbm`` written beside the
#: sample; the version 6000.3's ModelImporter writes (24200) gives a Generic rig
#: and materials in the model, as no ``.meta`` at all does. A newer editor
#: upgrades from it as from any ``.meta`` 6000.3 wrote.
IMPORTER_META = {".fbx": "ModelImporter:\n  serializedVersion: 24200\n"}


# ------------------------------------------------------------------ recipes
def recipes(folder: Path = RECIPES) -> list:
    """Every recipe module under *folder*, by ``NAME``.

    Raises:
        ValueError: A recipe lacks ``NAME``, ``DESCRIPTION``, ``RECORDS`` or
            ``build``, or two share a name.
    """
    found, names = [], set()
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"unity_sample_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        missing = [a for a in ("NAME", "DESCRIPTION", "RECORDS", "build") if not hasattr(module, a)]
        if missing:
            raise ValueError(f"{path.name} declares no {', '.join(missing)}: see unity_samples/__init__.py")
        if module.NAME in names:
            raise ValueError(f"two recipes are named {module.NAME!r}")
        names.add(module.NAME)
        module.PATH = path
        found.append(module)
    return sorted(found, key=lambda m: m.NAME)


def sample_entries(found) -> list:
    """``package.json``'s ``samples``: per recipe, what the Package Manager lists."""
    return [
        {"displayName": r.NAME, "description": r.DESCRIPTION, "path": f"{SAMPLES}/{r.NAME}"}
        for r in found
    ]


def render_package_json(text: str, entries: list) -> str:
    """*text* (a ``package.json``) with its ``samples`` set to *entries*, every
    other key kept in its place (a new key goes last); none when *entries* is
    empty."""
    data = json.loads(text)
    if entries:
        data["samples"] = entries
    else:
        data.pop("samples", None)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------- the producer
def find_mayapy():
    """The mayapy beside the newest Maya (mayatk's discovery: ``$MAYA_EXE``,
    ``$MAYA_LOCATION``, PATH, then the installs), or ``None``."""
    for name in reversed(CHECKOUTS):
        root = str(REPO_ROOT / name)
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        from mayatk import MayaSceneFiles
    except ImportError:
        return None
    return MayaSceneFiles.find_mayapy()


DRIVER = '''\
import importlib.util, json, os, sys
for root in reversed({roots!r}):
    if root not in sys.path:
        sys.path.insert(0, root)
if {scripts!r} not in sys.path:
    sys.path.append({scripts!r})  # the recipes' shared helpers (unity_samples._images), last: it shadows nothing
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
cmds.loadPlugin("fbxmaya", quiet=True)
import pythontk as ptk
done = {{}}
for name, path, out in {jobs!r}:
    spec = importlib.util.spec_from_file_location("unity_sample_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cmds.file(new=True, force=True)
    # A new scene drops the last one's shots: a standalone Maya runs no scene-opened
    # job, so the store a recipe made active would split the next one's takes.
    ptk.ShotStore.clear_active()
    os.makedirs(out, exist_ok=True)
    done[name] = list(module.build(out))
with open({artifact!r}, "w", encoding="utf-8") as fh:
    json.dump(done, fh)
sys.stdout.flush()
ptk.ProcessExit.hard_exit(0)  # the artifact is the verdict; TerminateProcess skips Maya's crashing teardown
'''


def export(found, out_root: Path, mayapy: str) -> dict:
    """Run every recipe in one owned mayapy, each exporting into
    ``<out_root>/<NAME>``; ``{NAME: [file names]}``.

    Raises:
        RuntimeError: The run wrote no result (a recipe failed; the message
            carries the child's output).
    """
    import pythontk as ptk

    artifact = out_root / "exported.json"
    jobs = [(r.NAME, str(r.PATH), str(out_root / r.NAME)) for r in found]
    roots = [str(REPO_ROOT / name) for name in CHECKOUTS]
    script = DRIVER.format(roots=roots, scripts=str(SCRIPTS), jobs=jobs, artifact=str(artifact))
    ptk.ScriptRunner.run_script_to_artifact(
        mayapy,
        script,
        artifact=str(artifact),
        timeout=TIMEOUT,
        script_prefix="unity_samples",
        env=dict(ptk.AppLauncher.process_environ(), **CHILD_ENV),
    )
    return json.loads(artifact.read_text(encoding="utf-8"))


# ------------------------------------------------------------ the description
def _text(value):
    """An FBX string value as text (a record's JSON parsed), else as stored."""
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", "replace")
        try:
            return json.loads(value)
        except ValueError:
            return value
    if isinstance(value, (list, tuple)):
        return [_text(v) for v in value]
    return value


def _seconds(value):
    """*value* (seconds) to four places, or ``None``."""
    return None if value is None else round(value, 4)


def _value(value):
    """An animated value to four places, ``-0.0`` read as ``0.0``: what a
    re-export of the same keys writes again."""
    return round(float(value), 4) + 0.0


def _digest(content: bytes) -> str:
    """What an embedded file holds, as a SHA-256: an image's texels (its mode,
    size and decoded pixels: a re-encode, or a provenance chunk its packer
    stamps, is no change to what the sample shows), else its bytes."""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            head = f"{image.mode}:{image.width}x{image.height}:".encode("ascii")
            return "texels:" + hashlib.sha256(head + image.tobytes()).hexdigest()
    except (OSError, ValueError, SyntaxError):  # not an image Pillow reads (a sound, an EXR): its bytes
        return "bytes:" + hashlib.sha256(content).hexdigest()


#: The node channels whose keys a sample's description holds, beside every
#: animated user property: a transform's (a curve proxy's ``scale.x`` is the
#: animated-value transport's FBX carrier) and the node's own visibility.
ANIMATED = ("Lcl Translation", "Lcl Rotation", "Lcl Scaling", "Visibility")


def describe_fbx(path: Path, records=()) -> dict:
    """What a sample's tests and its importers rely on in the FBX at *path*,
    with nothing its writer stamps per run (times, ids):

    - ``records``: each of *records* (the keys its feature reads, a recipe's
      ``RECORDS``) the ``data_export`` carrier holds, its JSON parsed --
      no other: the ``handoff`` record's prose and provenance, and a record
      no feature of the sample reads, change nothing the sample is for;
    - ``takes``: in file order, each take's name and declared window
      (``start``, ``end``, in seconds to four places);
    - ``animation``: per take, every key of each animated channel
      (:data:`ANIMATED` and the user properties), by ``<node path>:<property>.<component>``
      (``Box/Box__opacity:Lcl Scaling.X``), each ``[seconds, value,
      interpolation]``, times and values to four places;
    - ``nodes``: every model's path from the root (``Box``, ``data_export``),
      sorted;
    - ``meshes``: per mesh, its vertex and polygon-vertex counts;
    - ``media``: per embedded file, by its file name, a digest of what it
      holds (:func:`_digest`: an image's texels, another file's bytes);
    - ``machine_paths``: how many folders of the machine that wrote it the
      file names (``check_public_hygiene.MACHINE_PATH``: a user's home, a
      drive-letter folder) -- none in a delivery, so a committed sample that
      still carries its producer's is stale.
    """
    import pythontk as ptk

    fbx = ptk.FbxFile.load(str(path))
    wanted = set(records)
    carried, own = {}, set()
    # Each record as a reader applies it: the scene's own carrier's (the
    # root-level ``data_export``), else the first module's.
    for owner, name, value in fbx.user_property_items("Model", paths=True):
        if name not in wanted or name in own or not ptk.SceneStoreBase.is_carrier(owner):
            continue
        if ptk.SceneStoreBase.is_scene_carrier(owner):
            carried[name] = _text(value)
            own.add(name)
        else:
            carried.setdefault(name, _text(value))
    windows = fbx.take_windows()
    takes = []
    for take in fbx.take_names():
        start, end = windows.get(take, (None, None))
        takes.append({"take": take, "start": _seconds(start), "end": _seconds(end)})

    names, kinds = {}, {}
    for record in fbx.iter_objects():
        if record["props"]:
            names[record["props"][0]] = fbx.object_name(record)
            kinds[record["props"][0]] = record["name"]
    parent = {
        child: owner
        for kind, child, owner, _ in fbx.connections()
        if kind == "OO" and kinds.get(child) == "Model" and (owner == 0 or kinds.get(owner) == "Model")
    }

    def path_of(uid):
        steps = []
        while uid in parent and uid != 0:
            steps.append(names[uid])
            uid = parent[uid]
        return "/".join(reversed(steps))

    meshes = {}
    geometry_owner = {
        child: owner for kind, child, owner, _ in fbx.connections()
        if kind == "OO" and kinds.get(child) == "Geometry"
    }
    for record in fbx.iter_objects():
        if record["name"] != "Geometry":
            continue
        counts = {}
        for child in record["children"]:
            if child["name"] in ("Vertices", "PolygonVertexIndex") and child["props"]:
                placeholder = child["props"][0]
                count = placeholder[2] if isinstance(placeholder, tuple) else len(placeholder)
                counts["vertices" if child["name"] == "Vertices" else "polygon_vertices"] = (
                    count // 3 if child["name"] == "Vertices" else count
                )
        owner = geometry_owner.get(record["props"][0])
        meshes[path_of(owner) if owner in parent else fbx.object_name(record)] = counts

    models = {}
    for uid, kind in kinds.items():
        if kind == "Model":
            models.setdefault(names[uid], []).append(uid)

    def node(target):
        # take_keys' target: a model's name, ``name#uid`` where several share it.
        name, _, uid = target.partition("#")
        found = [int(uid)] if uid.isdigit() else models.get(name, [])
        return path_of(found[0]) if len(found) == 1 and found[0] in parent else target

    keyed = fbx.take_keys(properties=ANIMATED, user=True)
    animation = {}
    for take in fbx.take_names():
        channels = {}
        for (target, prop, component), keys in keyed.get(take, {}).items():
            label = f"{node(target)}:{prop}.{component.split('|')[-1]}"
            channels[label] = [
                [_seconds(ticks / ptk.FbxFile.TICKS_PER_SECOND), _value(value), interpolation]
                for ticks, value, interpolation in keys
            ]
        animation[take] = dict(sorted(channels.items()))

    media = {}
    for record in fbx.iter_objects():
        if record["name"] != "Video":
            continue
        fields = {child["name"]: child["props"] for child in record["children"]}
        content = (fields.get("Content") or [None])[0]
        filename = _text((fields.get("Filename") or fields.get("RelativeFilename") or [""])[0])
        if isinstance(content, (bytes, bytearray)) and content and isinstance(filename, str):
            media[re.split(r"[\\/]", filename)[-1]] = _digest(bytes(content))
    return {
        "records": carried,
        "takes": takes,
        "animation": animation,
        "nodes": sorted(path_of(uid) for uid in parent),
        "meshes": meshes,
        "media": dict(sorted(media.items())),
        "machine_paths": len(hygiene.MACHINE_PATH.findall(path.read_bytes())),
    }


def describe(path: Path, records=()) -> dict:
    """*path*'s description (:func:`describe_fbx` for an FBX, with the
    *records* its feature reads; else its bytes' length, a generated file of
    another kind being reproducible)."""
    if path.suffix.lower() == ".fbx":
        return describe_fbx(path, records)
    return {"bytes": path.stat().st_size}


def flatten(value, prefix: str = "") -> dict:
    """*value* as ``{path: leaf}``: ``records.animation.shots[0].clip``."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return out or {prefix: {}}
    if isinstance(value, list):
        out = {}
        for i, item in enumerate(value):
            out.update(flatten(item, f"{prefix}[{i}]"))
        return out or {prefix: []}
    return {prefix: value}


#: How many differing paths a drift line names before it says how many more.
SHOWN = 6


def differences(committed: dict, fresh: dict) -> list:
    """Each leaf two descriptions disagree on, ``path: committed -> fresh``
    (``absent`` where one has none), in path order."""
    old, new = flatten(committed), flatten(fresh)
    out = []
    for path in sorted(set(old) | set(new)):
        if old.get(path, ...) != new.get(path, ...):
            said = [json.dumps(d[path]) if path in d else "absent" for d in (old, new)]
            out.append(f"{path}: {said[0]} -> {said[1]}")
    return out


def summary(lines: list) -> str:
    """*lines* joined for one drift line, the first :data:`SHOWN` of them."""
    more = len(lines) - SHOWN
    return "; ".join(lines[:SHOWN]) + (f"; and {more} more" if more > 0 else "")


# ------------------------------------------------------------------- the sync
def _rel(path: Path) -> str:
    """*path* as the workspace names it (as given when outside it)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def ensure_meta(path: Path, check: bool) -> bool:
    """A ``.meta`` beside *path*, made once with a fresh GUID (as the package's
    scaffold makes them) and kept after, stating its importer's version
    (:data:`IMPORTER_META`): one that lacks it gains it, its GUID kept.
    Returns whether one was missing or lacked it; writes it unless *check*."""
    meta = path.with_name(path.name + ".meta")
    importer = IMPORTER_META.get(path.suffix.lower(), "")
    rel = _rel(meta)
    if meta.is_file():
        text = meta.read_bytes().decode("utf-8").replace("\r\n", "\n")
        if not importer or importer.split("\n", 1)[0] in text.split("\n"):
            return False
        if check:
            print(f"DRIFT: {rel} states no importer version, so Unity imports it as a legacy file; run {SCRIPT}")
            return True
        meta.write_bytes((text if text.endswith("\n") else text + "\n").encode("utf-8") + importer.encode("utf-8"))
        print(f"wrote {rel}")
        return False
    if check:
        print(f"DRIFT: {rel} is missing; run {SCRIPT}")
        return True
    meta.write_bytes((META.format(guid=uuid.uuid4().hex) + importer).encode("utf-8"))
    print(f"wrote {rel}")
    return False


#: What a sample folder holds beside its delivery, kept by hand: the sample's
#: own code at its top (a runtime demo, its assemblies). Its subfolders
#: (``Editor/``, the demo recipe) are its own too; every file keeps its ``.meta``.
SAMPLE_SOURCES = (".cs", ".asmdef", ".asmref")


def extras(sample_dir: Path, produced) -> list:
    """The files at the top of *sample_dir* no export wrote: a delivery file
    not in *produced* (its ``.meta`` goes with it), or a ``.meta`` whose file
    or folder is gone."""
    if not sample_dir.is_dir():
        return []
    found = []
    for path in sorted(p for p in sample_dir.iterdir() if p.is_file()):
        if path.suffix == ".meta":
            if not path.with_name(path.name[: -len(".meta")]).exists():
                found.append(path)
        elif path.suffix.lower() not in SAMPLE_SOURCES and path.name not in produced:
            found.append(path)
    return found


def sync_sample(recipe, produced: dict, fresh_dir: Path, sample_dir: Path, check: bool) -> bool:
    """Hold each file *recipe* produced (``produced[recipe.NAME]``) in
    *sample_dir* to its fresh export in *fresh_dir*, by description (the
    records its ``RECORDS`` names), and the folder to those files alone
    (:func:`extras`). Returns whether anything drifted; copies the fresh file
    in, and removes an extra one, unless *check*."""
    name, records = recipe.NAME, tuple(recipe.RECORDS)
    failed = False
    for path in extras(sample_dir, produced[name]) if name in produced else ():
        rel = _rel(path)
        if check:
            print(f"DRIFT: {name} {rel}: the recipe no longer produces it -- run {SCRIPT}")
            failed = True
            continue
        for stale in (path, path.with_name(path.name + ".meta")):
            if stale.is_file():
                stale.unlink()
                print(f"removed {_rel(stale)}")
    for file_name in produced.get(name, []):
        fresh, committed = fresh_dir / file_name, sample_dir / file_name
        rel = _rel(committed)
        if not committed.is_file():
            lines = ["missing"]
        else:
            lines = differences(describe(committed, records), describe(fresh, records))
        if lines:
            if check:
                print(f"DRIFT: {name} {rel}: {summary(lines)} -- run {SCRIPT}")
                failed = True
            else:
                sample_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(fresh, committed)
                print(f"wrote {rel}")
        failed |= ensure_meta(committed, check)
    return failed


def orphans(found, samples_dir: Path) -> list:
    """Sample folders no recipe makes."""
    names = {r.NAME for r in found}
    if not samples_dir.is_dir():
        return []
    return sorted(p.name for p in samples_dir.iterdir() if p.is_dir() and p.name not in names)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="exit 1 on drift, 2 when it cannot run")
    parser.add_argument("--describe", action="store_true", help="print the committed samples' descriptions")
    args = parser.parse_args(argv)

    found = recipes()
    package = records.unity_package()
    samples_dir = package / SAMPLES
    if args.describe:
        for recipe in found:
            folder = samples_dir / recipe.NAME
            for path in sorted(folder.glob("*.fbx")):
                print(json.dumps({_rel(path): describe(path, recipe.RECORDS)}, indent=2))
        return 0

    manifest = package / "package.json"
    text = manifest.read_bytes().decode("utf-8").replace("\r\n", "\n")
    failed = records.sync_text(
        manifest, render_package_json(text, sample_entries(found)), args.check, "samples entries", SCRIPT
    )
    for orphan in orphans(found, samples_dir):
        print(f"DRIFT: {SAMPLES}/{orphan} has no recipe in unity_samples/: add one or remove the folder")
        failed = True

    mayapy = find_mayapy()
    if not mayapy:
        print(
            f"FAIL: no Maya to export the samples with (mayatk found no mayapy: install Maya 2025+ or "
            f"set MAYA_LOCATION). {SCRIPT} runs locally and in the release gate, never in the Maya-less CI."
        )
        return CANNOT_RUN

    import pythontk as ptk

    scratch = ptk.TempArtifacts("unity_samples", policy="scoped")
    try:
        out_root = Path(scratch.dir_path())
        produced = export(found, out_root, mayapy)
        for recipe in found:
            failed |= sync_sample(
                recipe, produced, out_root / recipe.NAME, samples_dir / recipe.NAME, args.check
            )
    finally:
        scratch.cleanup()
    if not failed:
        print(f"in sync: {len(found)} sample(s) ({', '.join(r.NAME for r in found)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
