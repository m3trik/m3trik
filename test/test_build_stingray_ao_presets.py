#!/usr/bin/python
# coding=utf-8
"""Tests for build_stingray_ao_presets.py — mayatk's AO-capable StingrayPBS presets.

The shipped `mayatk/mat_utils/shaderfx/*_AO.sfx` are generated from Maya's own
presets; these tests guard that:
  - the shipped files match a fresh build (drift guard == the `--check` gate),
  - a merge adds exactly the AO chain: three records, three JSON nodes, four
    connections, renumbered onto the target graph, with the `Custom` identity
    that keeps the graph self-contained in a scene.

Env-gated on a Maya install with the ShaderFX presets.
"""

import os
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_stingray_ao_presets as b  # noqa: E402


def _stock_dir():
    try:
        return b.stock_presets_dir(None)
    except SystemExit:
        return None


@unittest.skipUnless(_stock_dir(), "no Maya install with ShaderFX presets")
class TestAoPresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = _stock_dir()
        cls.std = b.read(os.path.join(cls.stock, b.SOURCE))
        cls.built = b.build(None)

    def test_shipped_presets_match_a_fresh_build(self):
        for name, text in self.built.items():
            shipped = os.path.join(b.OUT_DIR, name)
            self.assertTrue(os.path.exists(shipped), f"missing {shipped}")
            self.assertEqual(
                b.read(shipped).replace("\r\n", "\n"),
                text,
                f"{name} drifted; regenerate",
            )

    def test_merge_adds_exactly_the_ao_chain(self):
        for src, out in b.PRESETS:
            with self.subTest(preset=src):
                dst = b.read(os.path.join(self.stock, src))
                merged = self.built[out]
                n = int(re.search(r"NumberOfNodes=(\d+)", dst).group(1))
                self.assertEqual(
                    int(re.search(r"NumberOfNodes=(\d+)", merged).group(1)), n + 3
                )
                recs = lambda t: len(re.findall(r"(?m)^#NT=", t[: t.index("*/")]))  # noqa: E731
                self.assertEqual(recs(merged), recs(dst) + 3)
                for name in ("use_ao_map", "ao_map", "Ao_Map_Swtich"):
                    self.assertRegex(merged, r"name=1 v=5000 " + name + r"\s")
                # Renumbered onto the target: switch -> base socket 8, and the
                # three records address each other at the appended indices.
                self.assertIn(f"C={n + 2} 0 5 ", merged)
                self.assertIn(f"C={n} 0 1 {n + 2} 0 1 0", merged)
                self.assertIn(f"C={n + 1} 0 3 {n + 2} 2 3 0", merged)
                self.assertIn(
                    f" {n + 1} 0 1 0", merged, "the UV chain must feed the new sampler"
                )
                for cid in b.CONNECTOR.values():
                    self.assertGreater(
                        merged.count(cid),
                        dst.count(cid),
                        f"JSON connection {cid} missing",
                    )
                self.assertIn("preset_path=1 v=5000 Custom", merged)
                self.assertIn("ParentMaterial=Custom", merged)
                self.assertNotIn("preset_path=1 v=5000 presets/", merged)

    def test_check_gate_is_green_on_the_shipped_files(self):
        self.assertEqual(b.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
