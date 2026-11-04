"""Tests for scripts/scaffold_unity_part.py: each kind writes its part, every
file and folder with a Unity-format .meta, and never writes over anything."""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pythontk as ptk  # noqa: E402

import scaffold_unity_part as scaffold  # noqa: E402

META = re.compile(r"\AfileFormatVersion: 2\nguid: [0-9a-f]{32}\n.*  assetBundleVariant: \n\Z", re.S)


class TestScaffoldUnityPart(unittest.TestCase):
    def setUp(self):
        store = ptk.TempArtifacts("scaffold_unity_part", policy="scoped")
        self.addCleanup(store.cleanup)
        self.root = Path(store.dir_path())

    def run_kind(self, *argv):
        self.assertEqual(scaffold.main([*argv, "--root", str(self.root)]), 0)

    def test_a_feature_has_its_parts_a_failing_test_and_every_meta(self):
        self.run_kind("feature", "Probe")
        editor = json.loads((self.root / "Features/Probe/Editor/M3trik.Unitytk.Probe.Editor.asmdef").read_text())
        self.assertEqual(editor["includePlatforms"], ["Editor"])
        self.assertIn("M3trik.Unitytk.Probe", editor["references"])
        tests = json.loads((self.root / "Features/Probe/Tests/M3trik.Unitytk.Probe.Tests.asmdef").read_text())
        self.assertEqual(tests["defineConstraints"], ["UNITY_INCLUDE_TESTS", "UNITYTK_TEST_FRAMEWORK"])
        self.assertIn("Assert.Fail", (self.root / "Features/Probe/Tests/ProbesTests.cs").read_text())
        self.assertIn("Prior art:", (self.root / "Features/Probe/Editor/Probes.cs").read_text())
        for path in self.root.rglob("*"):
            if not path.name.endswith(".meta"):
                meta = Path(str(path) + ".meta")
                self.assertTrue(meta.is_file(), path)
                self.assertRegex(meta.read_text(encoding="utf-8"), META)

    def test_a_door_compiles_only_with_its_package(self):
        self.run_kind("door", "Probe", "URP", "com.unity.render-pipelines.universal", "17.3.0")
        door = json.loads((self.root / "Features/Probe/URP/M3trik.Unitytk.Probe.URP.asmdef").read_text())
        self.assertFalse(door["autoReferenced"])
        define = door["versionDefines"][0]["define"]
        self.assertEqual(door["defineConstraints"], [define])
        self.assertEqual(door["versionDefines"][0]["expression"], "17.3.0")

    def test_a_contract_ships_with_its_stand_in(self):
        self.run_kind("contract", "IProbe", "--editor")
        text = (self.root / "Contracts/Editor/IProbe.cs").read_text()
        self.assertIn("public interface IProbe", text)
        self.assertIn("[Provides(typeof(IProbe), StandIn = true)]", text)
        self.assertIn("class PureProbe : IProbe", text)

    def test_it_never_writes_over_a_part(self):
        self.run_kind("feature", "Probe")
        with self.assertRaises(SystemExit):
            scaffold.main(["feature", "Probe", "--root", str(self.root)])
        with self.assertRaises(SystemExit):
            scaffold.main(["feature", "not_pascal", "--root", str(self.root)])


if __name__ == "__main__":
    unittest.main()
