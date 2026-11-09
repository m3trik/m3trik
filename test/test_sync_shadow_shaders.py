#!/usr/bin/python
# coding=utf-8
"""Tests for sync_shadow_shaders.py -- where its mirrors are found.

The mirrors' content is pinned by ``pythontk/test/test_sync_shadow_shaders.py``;
this holds :func:`mirrors` to the workspace it is handed: a fixture workspace
finds its own mirrors, the Unity package's by its declared root.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_shadow_shaders as ssh  # noqa: E402


class TestMirrors(unittest.TestCase):
    def test_each_mirror_is_found_in_the_workspace_it_is_handed(self):
        """Bug: the unitytk mirror was looked up in this checkout whatever
        ``repo_root`` said, and the lookup edited ``sys.path`` on each call.
        Fixed: 2026-11-08"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            js = root / "pythontk" / "pythontk/net_utils/preview/features/shadow_rig/shadow_rig.js"
            hlsl = root / "unitytk" / "Pkg" / "Features" / "ShadowPlane" / "ShadowPlaneHorizon.hlsl"
            for path in (js, hlsl):
                path.parent.mkdir(parents=True)
                path.write_text("// mirror\n", encoding="utf-8")
            (root / "unitytk" / "pyproject.toml").write_text(
                '[project]\nname = "unitytk"\n\n[tool.m3trik.layers.csharp]\nroot = "Pkg"\n',
                encoding="utf-8",
            )
            before = list(sys.path)
            found = ssh.mirrors(root)
            self.assertEqual(sys.path, before)
        self.assertEqual(found, [(js, "glsl"), (hlsl, "hlsl")])

    def test_a_package_not_checked_out_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ssh.mirrors(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
