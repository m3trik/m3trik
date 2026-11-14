#!/usr/bin/python
# coding=utf-8
"""A producer's delivery into Unity: unitytk's samples, made again by another DCC.

unitytk's samples are Maya-made (``m3trik/scripts/sync_unity_samples.py``)
and its Edit Mode tests check them (``Features/<F>/Tests/<F>SampleTests.cs``).
What only a real export proves -- Blender's Z-up frame and its split of one
action into takes, Maya's Arnold surface through its FBX writer, an
assembly's stray carriers -- is proved here the same way: a **twin** is a
second delivery of a sample, the same scene made another way, and the
sample's own tests must pass on it unchanged. So a producer is held to one
contract, stated once, in the package.

A twin is a module in ``twins/`` (the recipes' shape, ``unity_samples/``):
``NAME`` (the twin), ``SAMPLE`` (the sample it delivers again), ``PRODUCER``
(``"maya"`` or ``"blender"``) and ``build(out_dir) -> [file names]``, run in a
new, empty scene of its producer; a twin builds from its sample's recipe
(``from unity_samples import shots as recipe``), so the two never drift. A
defect a twin found and the backlog holds is declared, not hidden:
``KNOWN_FAILURES`` (``{sample test name: why}``) must fail as stated, and
one that passes fails the run until it is dropped.

Each test:

1. runs the twin in a producer this run launches and waits on, never one a
   person opened: a headless mayapy (the samples' own driver,
   ``sync_unity_samples.export``, ``MAYA_DEBUG_NO_SAVE_ON_CRASH`` set), or a
   background Blender through blendertk's ``BlenderConnection``;
2. builds the end-to-end project (``ProjectBuilder.build(key=KEY)``: a URP
   project of its own beside the package's, which the package's suites use),
   the twin's files delivered in place of the sample's own;
3. runs that sample's tests there (``ProjectBuilder.test``), in a batch editor
   the call starts, and requires every one to pass but the twin's known failures.

A later build without the twin imports the sample's own files again. A test
skips, saying why, where Maya, Blender, unitytk or a Unity editor is missing
(the Linux CI has none of them).
"""

import importlib.util
import json
import logging
import os
import re
import shutil
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
SCRIPTS = WORKSPACE / "m3trik" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import sync_unity_samples as samples  # noqa: E402 -- the samples' recipes, driver and mayapy

logger = logging.getLogger(__name__)

#: The twins, one module each.
TWINS = HERE / "twins"
#: This workspace's Unity package: its sample tests, which a twin is checked by.
PACKAGE = WORKSPACE / "unitytk" / "com.m3trik.unitytk"
#: The end-to-end project's key: never the package's own project.
KEY = "e2e"
#: The pipeline the sample tests run on (each Assumes a pipeline unitytk serves).
PIPELINE = "urp"
#: The checkouts a background Blender imports (it ignores ``PYTHONPATH``).
BLENDER_CHECKOUTS = ("pythontk", "uitk", "blendertk")
#: Seconds a producer's run may take.
TIMEOUT = 900

BLENDER_DRIVER = '''\
import importlib.util, json, os, sys
for root in reversed({roots!r}):
    if root not in sys.path:
        sys.path.insert(0, root)
if {scripts!r} not in sys.path:
    sys.path.append({scripts!r})  # the samples' recipes, which a twin builds from: last, it shadows nothing
import bpy
import pythontk as ptk
done = {{}}
for name, path, out in {jobs!r}:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ptk.ShotStore.clear_active()
    spec = importlib.util.spec_from_file_location("unity_twin_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    os.makedirs(out, exist_ok=True)
    done[name] = list(module.build(out))
with open({artifact!r}, "w", encoding="utf-8") as fh:
    json.dump(done, fh)
'''


def twins(folder: Path = TWINS) -> dict:
    """Every twin module under *folder*, by ``NAME``.

    Raises:
        ValueError: A twin lacks ``NAME``, ``SAMPLE``, ``PRODUCER`` or
            ``build``, names an unknown producer, or two share a name.
    """
    found = {}
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"unity_twin_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        missing = [a for a in ("NAME", "SAMPLE", "PRODUCER", "build") if not hasattr(module, a)]
        if missing:
            raise ValueError(f"{path.name} declares no {', '.join(missing)}: see {Path(__file__).name}")
        if module.PRODUCER not in PRODUCERS:
            raise ValueError(f"{path.name}: no producer {module.PRODUCER!r}, only {sorted(PRODUCERS)}")
        if module.NAME in found:
            raise ValueError(f"two twins are named {module.NAME!r}")
        module.PATH = path
        found[module.NAME] = module
    return found


# --------------------------------------------------------------- producers
def find_blender():
    """blendertk's Blender (``$BLENDER_EXE``, PATH, the installs), or ``None``."""
    for name in reversed(BLENDER_CHECKOUTS):
        root = str(WORKSPACE / name)
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        from blendertk import BlenderConnection
    except ImportError:
        return None
    return BlenderConnection.find_blender()


def run_maya(twin, out_root: Path, mayapy: str) -> list:
    """*twin* built in one owned headless mayapy (the samples' own driver)."""
    return samples.export([twin], out_root, mayapy)[twin.NAME]


def run_blender(twin, out_root: Path, blender: str) -> list:
    """*twin* built in one owned background Blender (blendertk's
    ``BlenderConnection``: ``--background --factory-startup``), its preset
    store this run's, never the user's.

    Raises:
        RuntimeError: The run wrote no result (the message carries its log's tail).
    """
    import pythontk as ptk
    from blendertk import BlenderConnection

    artifact, script, log = out_root / "built.json", out_root / "driver.py", out_root / "blender.log"
    script.write_text(
        BLENDER_DRIVER.format(
            roots=[str(WORKSPACE / name) for name in BLENDER_CHECKOUTS],
            scripts=str(SCRIPTS),
            jobs=[(twin.NAME, str(twin.PATH), str(out_root / twin.NAME))],
            artifact=str(artifact),
        ),
        encoding="utf-8",
    )
    env = dict(ptk.AppLauncher.process_environ())
    env[ptk.UserConfig.CONFIG_ROOT_ENV_VAR] = str(out_root / "config")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = BlenderConnection(blender_exe=blender).run_script(
        str(script), extra_args=["--python-exit-code", "1"], timeout=TIMEOUT, output_file=str(log), env=env
    )
    if not artifact.is_file():
        tail = log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.is_file() else ""
        raise RuntimeError(f"Blender (exit {proc.returncode}) built no {twin.NAME}:\n{tail}")
    return json.loads(artifact.read_text(encoding="utf-8"))[twin.NAME]


#: Each producer: how it is found, how a twin runs in it, and what to install.
PRODUCERS = {
    "maya": (samples.find_mayapy, run_maya, "no Maya: install Maya 2025+ or set MAYA_LOCATION"),
    "blender": (find_blender, run_blender, "no Blender: install Blender 4.x+ or set BLENDER_EXE"),
}


# -------------------------------------------------------------------- Unity
def unity_builder():
    """``(ProjectBuilder, None)``, or ``(None, why)`` where Unity's half cannot run."""
    try:
        from unitytk import ProjectBuilder
    except ImportError as error:
        return None, f"unitytk is not importable ({error})"
    if ProjectBuilder.package_dir() is None:
        return None, "unitytk is no checkout: it has no Unity package to test"
    try:
        ProjectBuilder.newest_editor()
    except FileNotFoundError as error:
        return None, str(error)
    return ProjectBuilder, None


def sample_tests(sample: str) -> Path:
    """The file of the Edit Mode tests that check *sample*."""
    return PACKAGE / "Features" / sample / "Tests" / f"{sample}SampleTests.cs"


def fixture(sample: str) -> str:
    """The full name of the fixture that checks *sample*: its class, in the
    namespace its file declares (``M3trik.Unitytk.<F>.Tests``, mostly)."""
    declared = re.search(r"^namespace\s+([\w.]+)", sample_tests(sample).read_text(encoding="utf-8"), re.MULTILINE)
    return f"{declared.group(1)}.{sample}SampleTests"


class TestSampleTwins(unittest.TestCase):
    """Each twin's delivery passes its sample's tests. One test per twin
    module, made below. Added: 2026-11-08"""

    def check(self, name: str) -> None:
        twin = twins()[name]
        find, run, install = PRODUCERS[twin.PRODUCER]
        builder, why = unity_builder()
        if builder is None:
            self.skipTest(why)
        exe = find()
        if not exe:
            self.skipTest(install)
        import pythontk as ptk  # after the skips: a checkout without it skips, saying why

        scratch = ptk.TempArtifacts("unity_e2e", policy="scoped")
        passed = False
        try:
            out_root = Path(scratch.dir_path())
            produced = run(twin, out_root, exe)
            # Only what the twin delivers: a producer's project and scene stay behind.
            delivery = out_root / "delivery"
            delivery.mkdir()
            for file_name in produced:
                shutil.copy2(out_root / twin.NAME / file_name, delivery / file_name)
            project = builder.build(pipeline=PIPELINE, key=KEY, replacements={twin.SAMPLE: delivery})
            outcome = builder.test(project=project, test_filter=fixture(twin.SAMPLE))
            known = dict(getattr(twin, "KNOWN_FAILURES", {}))
            failed = {c["name"].rsplit(".", 1)[-1] for c in outcome["failures"]}
            said = "\n".join(
                f"  {c['name']}: {c['message']}"
                for c in outcome["failures"] + outcome["inconclusives"]
                if c["name"].rsplit(".", 1)[-1] not in known
            )
            log = f"log: {outcome['log']}"
            self.assertTrue(outcome["total"], f"{name}: no test of the {twin.SAMPLE} sample ran\n{log}")
            self.assertEqual(sorted(failed - set(known)), [], f"{name}: the {twin.SAMPLE} sample's tests failed on it:\n{said}\n{log}")
            # A known failure is a defect logged with its reason; one that passes now is fixed: drop it.
            self.assertEqual(sorted(set(known) - failed), [], f"{name}: these pass now: drop them from KNOWN_FAILURES")
            self.assertEqual(
                (outcome["passed"] + len(known), outcome["inconclusive"], outcome["skipped"]), (outcome["total"], 0, 0),
                f"{name}: every other test of the {twin.SAMPLE} sample must pass on it:\n{said}\n{log}",
            )
            logger.info("%s: %d of %s's tests passed, %d known failure(s)", name, outcome["passed"], twin.SAMPLE, len(known))
            passed = True
        finally:
            if passed or os.environ.get("UNITYTK_PRESERVE") != "1":
                scratch.cleanup()
            else:
                logger.warning("%s: kept its run at %s", name, scratch.dir_path())


class TestTwinModules(unittest.TestCase):
    """Every twin names a sample with a recipe and its tests, and every known
    failure a test of them: no app needed. Added: 2026-11-08"""

    def test_each_twin_delivers_a_sample_its_tests_check(self):
        recipes = {r.NAME for r in samples.recipes()}
        for name, twin in twins().items():
            self.assertIn(twin.SAMPLE, recipes, f"{name}: no recipe makes the {twin.SAMPLE} sample")
            tests = sample_tests(twin.SAMPLE)
            if not PACKAGE.is_dir():
                continue  # a checkout without unitytk: the recipes are checked, the tests where they are
            self.assertTrue(tests.is_file(), f"{name}: no {tests.name} checks the {twin.SAMPLE} sample")
            source = tests.read_text(encoding="utf-8")
            self.assertIn(f"class {twin.SAMPLE}SampleTests", source, f"{name}: no fixture of its own in {tests.name}")
            self.assertTrue(fixture(twin.SAMPLE).endswith(f".{twin.SAMPLE}SampleTests"))
            for test in getattr(twin, "KNOWN_FAILURES", {}):
                self.assertIn(f"public void {test}(", source, f"{name}: its known failure {test} is no test of {tests.name}")


def _test_for(name: str):
    def test(self):
        self.check(name)

    test.__name__ = f"test_{name}"
    test.__doc__ = (twins()[name].__doc__ or name).strip().splitlines()[0]
    return test


for _name in twins():
    setattr(TestSampleTwins, f"test_{_name}", _test_for(_name))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
