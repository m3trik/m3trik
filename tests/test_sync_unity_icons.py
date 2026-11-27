#!/usr/bin/python
# coding=utf-8
"""Tests for sync_unity_icons.py -- unitytk's copy of uitk's icons.

The Unity Manifest draws the Shot Manifest's icons: uitk's SVGs, copied beside
unitytk's editor kernel. These tests pin that the committed copy is current
(the same check as ``--check``), that each ``.meta`` GUID is fixed by the
file's name, and that an icon uitk no longer has is reported, never kept.
"""

import contextlib
import io
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_unity_icons as icons  # noqa: E402


class TestUnityIcons(unittest.TestCase):
    def test_the_copy_is_current(self):
        wanted = icons.targets()
        self.assertGreater(len(wanted), 100)
        for path, text in wanted:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"missing {path}: run sync_unity_icons.py")
                self.assertEqual(path.read_bytes().decode("utf-8").replace("\r\n", "\n"), text)
        for path, new in icons.metas():
            with self.subTest(meta=path.name):
                self.assertIn(icons.guid_line(new), path.read_text(encoding="utf-8").splitlines())
        self.assertEqual(icons.stale(wanted), [], "a copy uitk no longer has")

    def test_the_icon_colour_is_written_white_for_the_tint(self):
        source = icons.SOURCE / "error.svg"
        self.assertIn(icons.TINT, source.read_text(encoding="utf-8"))
        text = icons.copied(source)
        self.assertNotIn(icons.TINT, text)
        self.assertIn(icons.WHITE, text)

    def test_each_meta_guid_is_fixed_by_the_files_name(self):
        guid = uuid.uuid5(uuid.NAMESPACE_URL, icons.GUID_NAMESPACE + "error.svg").hex
        self.assertEqual(icons.guid("error.svg"), guid)
        self.assertIn(f"guid: {guid}\n", icons.meta("error.svg"))
        self.assertIn("folderAsset: yes", icons.meta("Icons", folder=True))

    def test_a_meta_keeps_unitys_settings_and_its_guid_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.svg.meta"
            path.write_text("fileFormatVersion: 2\nguid: wrong\nScriptedImporter:\n  svgType: 3\n", encoding="utf-8")
            new = "fileFormatVersion: 2\nguid: abc\n"
            with mock.patch.object(icons, "REPO_ROOT", Path(tmp)):
                self.assertTrue(icons.sync_meta(path, new, check=True), "a check reports it")
                self.assertTrue(icons.sync_meta(path, new, check=False))
            self.assertEqual(path.read_text(encoding="utf-8"), "fileFormatVersion: 2\nguid: abc\nScriptedImporter:\n  svgType: 3\n")

    def test_an_icon_uitk_no_longer_has_is_reported_in_a_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Icons"
            folder.mkdir()
            gone = folder / "gone.svg"
            gone.write_text("<svg/>", encoding="utf-8")
            with mock.patch.object(icons, "icons_dir", return_value=folder):
                self.assertEqual(icons.stale([(folder / "kept.svg", "")]), [gone])


class TestMain(unittest.TestCase):
    """``main`` over a stand-in uitk and package: what a run writes and
    removes, and that a check writes nothing. Added: 2026-11-26"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.source, self.folder = root / "uitk_icons", root / "Kernel" / "Editor" / "Icons"
        self.source.mkdir()
        (self.source / "lock.svg").write_text(f'<svg fill="{icons.TINT}"/>\n', encoding="utf-8")
        self.folder.parent.mkdir(parents=True)
        for patcher in (
            mock.patch.object(icons, "SOURCE", self.source),
            mock.patch.object(icons, "icons_dir", return_value=self.folder),
            mock.patch.object(icons, "REPO_ROOT", root),
            mock.patch.object(icons.records, "REPO_ROOT", root),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = icons.main(list(argv))
        return code, out.getvalue()

    def test_a_check_of_a_missing_copy_writes_nothing_not_even_its_folder(self):
        """Bug: the folder was made before the check branch, so a check made it.
        Fixed: 2026-11-26"""
        code, said = self.run_main("--check")
        self.assertEqual(code, 1, said)
        self.assertIn("lock.svg", said)
        self.assertFalse(self.folder.exists(), "--check writes nothing")
        self.assertFalse(self.folder.with_name("Icons.meta").exists())

    def test_a_run_writes_the_copies_and_their_metas_and_a_check_then_passes(self):
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual((self.folder / "lock.svg").read_text(encoding="utf-8"), f'<svg fill="{icons.WHITE}"/>\n')
        self.assertEqual((self.folder / "lock.svg.meta").read_text(encoding="utf-8"), icons.meta("lock.svg"))
        self.assertEqual(self.folder.with_name("Icons.meta").read_text(encoding="utf-8"), icons.meta("Icons", folder=True))
        self.assertEqual(self.run_main("--check"), (0, "in sync: 1 icons\n"))

    def test_the_folders_meta_keeps_unitys_settings_and_its_guid_is_held(self):
        """The folder's ``.meta`` was held to its whole first text, so a setting
        Unity wrote into it was drift; its GUID is what references hold, as for
        a copy's. Fixed: 2026-11-26"""
        self.assertEqual(self.run_main()[0], 0)
        folder_meta = self.folder.with_name("Icons.meta")
        unity = icons.meta("Icons", folder=True) + "  labels: [ui]\n"
        folder_meta.write_text(unity, encoding="utf-8")
        self.assertEqual(self.run_main("--check")[0], 0, "Unity's settings are Unity's")
        folder_meta.write_text(unity.replace(icons.guid("Icons"), "0" * 32), encoding="utf-8")
        code, said = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("Icons.meta lacks guid:", said)
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(folder_meta.read_text(encoding="utf-8"), unity, "the GUID restored, Unity's settings kept")

    def test_an_icon_uitk_no_longer_has_goes_with_its_meta(self):
        self.assertEqual(self.run_main()[0], 0)
        gone = [self.folder / "gone.svg", self.folder / "gone.svg.meta"]
        for path in gone:
            path.write_text("x\n", encoding="utf-8")
        code, said = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertEqual(said.count("is no uitk icon"), 2)
        self.assertTrue(all(p.is_file() for p in gone), "--check removes nothing")
        code, said = self.run_main()
        self.assertEqual(code, 0, said)
        self.assertFalse(any(p.exists() for p in gone), said)
        self.assertEqual(self.run_main("--check"), (0, "in sync: 1 icons\n"))
