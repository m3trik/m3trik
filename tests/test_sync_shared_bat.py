#!/usr/bin/python
# coding=utf-8
"""Tests for sync_shared_bat.py — the mirror of the shared package-manager.bat.

The shared menu (m3trik/package-manager.bat) is the SSoT; the mayatk / blendertk
wrappers hand off to it and need a copy shipped next to them in the wheel (there
is no m3trik/ on disk after a bare pip install). These tests guard that:
  - the SSoT exists,
  - every declared mirror exists and matches the SSoT (drift guard == the `--check` gate),
  - sync() is idempotent and self-heals a stale/missing mirror.
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_shared_bat as s  # noqa: E402


class TestSharedBatMirrors(unittest.TestCase):
    def test_source_exists(self):
        self.assertTrue(s.SOURCE.is_file(), f"SSoT missing: {s.SOURCE}")

    def test_mirrors_land_next_to_each_wrapper(self):
        # Each mirror must sit in the same env_utils/ dir as its DCC wrapper, so the
        # wrapper's `%~dp0package-manager.bat` sibling lookup resolves post-install.
        wrappers = {
            "mayatk": "mayapy-package-manager.bat",
            "blendertk": "blenderpy-package-manager.bat",
        }
        for mirror in s.MIRRORS:
            self.assertEqual(mirror.name, s.SOURCE.name, f"unexpected mirror name: {mirror}")
            pkg = mirror.parents[2].name  # env_utils -> <pkg> -> <repo>/<pkg>
            self.assertIn(pkg, wrappers, f"mirror in unexpected package: {mirror}")
            self.assertTrue(
                (mirror.parent / wrappers[pkg]).is_file(),
                f"wrapper missing next to mirror: {mirror.parent / wrappers[pkg]}",
            )

    def test_mirrors_in_sync_with_source(self):
        # This is the committed-state drift guard — equivalent to `sync_shared_bat.py --check`.
        drift = s.out_of_sync()
        self.assertEqual(
            drift, [], "Mirror(s) out of sync — run `python m3trik/scripts/sync_shared_bat.py`:\n"
            + "\n".join(f"  - {m}" for m in drift),
        )

    def test_check_mode_passes(self):
        self.assertEqual(s.main(["--check"]), 0)

    def test_sync_writes_then_is_idempotent(self):
        # Exercise sync()/out_of_sync() against a throwaway tree so the real repo
        # mirrors are never touched by the test run.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "package-manager.bat"
            src.write_bytes(b"@ECHO off\r\n:: shared menu\r\n")
            mirror = Path(tmp) / "pkg" / "env_utils" / "package-manager.bat"

            # A missing parent dir means the target repo isn't checked out — sync must
            # refuse to fabricate the tree rather than drop a .bat in a wrong location.
            self.assertEqual(s.out_of_sync(src, [mirror]), [mirror], "missing mirror = drift")
            with self.assertRaises(FileNotFoundError):
                s.sync(src, [mirror])

            mirror.parent.mkdir(parents=True)
            self.assertEqual(s.sync(src, [mirror]), [mirror], "first sync writes the mirror")
            self.assertEqual(mirror.read_bytes(), src.read_bytes())
            self.assertEqual(s.out_of_sync(src, [mirror]), [], "in sync after write")
            self.assertEqual(s.sync(src, [mirror]), [], "second sync is a no-op")

            # A drifted mirror is detected and self-healed.
            mirror.write_bytes(b"stale\r\n")
            self.assertEqual(s.out_of_sync(src, [mirror]), [mirror])
            self.assertEqual(s.sync(src, [mirror]), [mirror])
            self.assertEqual(s.out_of_sync(src, [mirror]), [])

            # An EOL-only difference is not drift and must not cause a rewrite: --check and
            # sync() share one comparison, so neither reports nor churns on line-ending changes.
            mirror.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
            self.assertEqual(s.out_of_sync(src, [mirror]), [], "EOL-only difference is not drift")
            self.assertEqual(s.sync(src, [mirror]), [], "sync must not churn on EOL-only difference")


if __name__ == "__main__":
    unittest.main(verbosity=2)
