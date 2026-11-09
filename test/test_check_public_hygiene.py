#!/usr/bin/python
# coding=utf-8
"""Tests for scripts/check_public_hygiene.py -- the client-identifier gate.

Synthetic denylist and synthetic repos only: a real identifier in this public
repo would be the very leak the gate exists to stop.
"""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import check_public_hygiene as gate  # noqa: E402

DENYLIST = "# private\n\nZORK_?WIDGET\n\\bQUUX\\b\n"


def _rmtree(path):
    """Remove *path*, including the read-only objects git writes on Windows."""

    def force(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=force)
    else:
        shutil.rmtree(path, onerror=force)


class _RepoCase(unittest.TestCase):
    """One throwaway git repo beside a throwaway denylist."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hygiene_gate_test_")
        self.addCleanup(_rmtree, self.root)
        self.repo = os.path.join(self.root, "pubrepo")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.denylist = os.path.join(self.root, "denylist.txt")
        self.write_denylist(DENYLIST)

    def write_denylist(self, text, encoding="utf-8"):
        with open(self.denylist, "w", encoding=encoding) as handle:
            handle.write(text)

    def write(self, rel, content, track=True):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content if isinstance(content, bytes) else content.encode())
        if track:
            subprocess.run(["git", "-C", self.repo, "add", "--", rel], check=True)

    def scan(self):
        return gate.scan_repo(self.repo, gate.load_denylist(self.denylist), "pubrepo")

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main(
                ["--workspace", self.root, "--denylist", self.denylist, *argv]
            )
        return code, out.getvalue()


class TestScan(_RepoCase):
    def test_a_tracked_text_file_is_reported_at_its_line(self):
        self.write("docs/notes.md", "clean\nsee Zork_Widget here\n")
        self.assertEqual(
            self.scan(), [gate.Finding("pubrepo", "docs/notes.md", 2, "Zork_Widget")]
        )

    def test_every_match_in_one_file_reports_its_own_line(self):
        self.write("notes.md", "x\nZORKWIDGET\n\n\nquux and zork_widget\n")
        self.assertEqual(
            [(f.line, f.text) for f in self.scan()],
            [(2, "ZORKWIDGET"), (5, "quux"), (5, "zork_widget")],
        )

    def test_an_untracked_file_is_published_by_add_all_so_it_is_scanned(self):
        self.write("draft.py", "# zorkwidget\n", track=False)
        self.assertEqual([f.path for f in self.scan()], ["draft.py"])

    def test_an_ignored_file_is_never_published_so_it_is_not_scanned(self):
        self.write(".gitignore", "local.txt\n")
        self.write("local.txt", "ZORK_WIDGET\n", track=False)
        self.assertEqual(self.scan(), [])

    def test_a_binary_file_is_skipped(self):
        self.write("asset.bin", b"\x00\x01ZORK_WIDGET")
        self.assertEqual(self.scan(), [])

    def test_a_utf16_file_is_text_not_a_binary(self):
        """What Windows PowerShell 5.1's ``>`` writes: a byte order mark, then
        a NUL in every ASCII character -- read as text, never skipped."""
        for codec in ("utf-16-le", "utf-16-be"):
            with self.subTest(codec=codec):
                bom = "﻿".encode(codec)
                self.write("ps.log", bom + "x\nZORK_WIDGET\n".encode(codec))
                self.assertEqual(
                    self.scan(), [gate.Finding("pubrepo", "ps.log", 2, "ZORK_WIDGET")]
                )

    def test_a_path_that_names_a_client_is_reported_without_a_line(self):
        self.write("test/test_zork_widget_case.py", "clean\n")
        self.assertEqual(
            self.scan(),
            [
                gate.Finding(
                    "pubrepo", "test/test_zork_widget_case.py", None, "zork_widget"
                )
            ],
        )

    def test_boundaries_are_the_denylist_s_own(self):
        self.write("a.txt", "quuxly\n")
        self.write("b.txt", "a quux b\n")
        self.assertEqual([f.path for f in self.scan()], ["b.txt"])


class TestDenylist(_RepoCase):
    def test_no_file_means_no_verdict(self):
        self.assertIsNone(gate.load_denylist(os.path.join(self.root, "absent.txt")))

    def test_a_bad_expression_names_its_line(self):
        self.write_denylist("# header\nfine\n(unclosed\n")
        with self.assertRaisesRegex(ValueError, r"denylist\.txt:3:"):
            gate.load_denylist(self.denylist)

    def test_a_global_inline_flag_names_its_line(self):
        """``(?i)`` compiles on its own line but not inside the joined alternation."""
        self.write_denylist("fine\n(?i)other\n")
        with self.assertRaisesRegex(ValueError, r"denylist\.txt:2:"):
            gate.load_denylist(self.denylist)

    def test_a_byte_order_mark_does_not_disable_the_first_pattern(self):
        """Windows PowerShell 5.1 writes UTF-8 with a BOM."""
        self.write_denylist("ZORK_?WIDGET\n", encoding="utf-8-sig")
        self.assertTrue(gate.load_denylist(self.denylist).search("zork_widget"))

    def test_a_list_of_only_comments_is_an_error_not_a_pass(self):
        self.write_denylist("# nothing\n\n")
        with self.assertRaises(ValueError):
            gate.load_denylist(self.denylist)


class TestMain(_RepoCase):
    def test_a_match_fails_and_prints_where(self):
        self.write("x.md", "ZORKWIDGET\n")
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 1)
        self.assertIn("pubrepo/x.md:1:", out)

    def test_a_clean_repo_passes(self):
        self.write("x.md", "clean\n")
        self.assertEqual(self.run_main("pubrepo")[0], 0)

    def test_without_a_denylist_it_skips_rather_than_passes(self):
        os.remove(self.denylist)
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 0)
        self.assertIn("SKIP", out)

    def test_a_missing_repo_is_an_error(self):
        self.assertEqual(self.run_main("nope")[0], 2)

    def test_public_only_skips_a_private_repo_it_was_handed(self):
        """push.ps1 hands over every repo a run touches, private ones included."""
        self.write("x.md", "ZORKWIDGET\n")
        code, out = self.run_main("--public-only", "pubrepo")
        self.assertEqual(code, 0)
        self.assertIn("private", out)

    def test_public_only_still_scans_a_public_repo(self):
        self.write("x.md", "ZORKWIDGET\n")
        with mock.patch.object(gate, "PUBLIC_REPOS", ("pubrepo",)):
            self.assertEqual(self.run_main("--public-only", "pubrepo")[0], 1)

    def test_a_git_failure_is_an_error_not_a_match(self):
        """1 means "a leak"; a repo git refuses to read must not say that."""
        broken = os.path.join(self.root, "broken")
        os.makedirs(broken)
        with open(os.path.join(broken, ".git"), "w", encoding="utf-8") as handle:
            handle.write("gitdir: nowhere\n")
        code, out = self.run_main("broken")
        self.assertEqual(code, 2)
        self.assertIn("git", out)


class TestMachinePaths(_RepoCase):
    """A committed sample binary carries no folder of the machine that made it.

    Bug: every unitytk sample FBX held its producer's user name and folders
    (the staging file under the user's temp folder, the Maya project folder,
    each map's source), and the gate passed: it reads text and skips binaries.
    Fixed: 2026-11-08 -- each binary under a ``Samples~`` folder is searched
    for a user-home or machine path, with or without the denylist."""

    FBX_HEAD = b"Kaydara FBX Binary  \x00\x1a\x00"

    def test_a_user_home_inside_a_sample_binary_is_reported(self):
        for leaked in (
            b"C:\\Users\\someone\\AppData\\Local\\Temp\\stage\\room.fbx",
            b"C:/Users/someone/proj/sourceimages/wood.png",
            b"/home/someone/proj/wood.png",
            b"/Users/someone/proj/wood.png",
            b"D:\\projects\\room\\sourceimages\\wood.png",
        ):
            with self.subTest(leaked=leaked):
                self.write("pkg/Samples~/Room/Room.fbx", self.FBX_HEAD + b"\x00\x05" + leaked + b"\x00")
                found = gate.scan_machine_paths(self.repo, "pubrepo")
                self.assertEqual([f.path for f in found], ["pkg/Samples~/Room/Room.fbx"], found)
                self.assertIn("someone" if b"someone" in leaked else "projects", found[0].text)

    def test_a_bare_file_name_and_a_relative_path_are_not_machine_paths(self):
        self.write(
            "pkg/Samples~/Room/Room.fbx",
            self.FBX_HEAD + b"\x00wood.png\x00..\\maps\\wood.png\x00\x89PNG\x01C:\x02",
        )
        self.assertEqual(gate.scan_machine_paths(self.repo, "pubrepo"), [])

    def test_every_publishable_binary_is_searched_and_text_is_the_denylists(self):
        """A committed test fixture publishes as a sample does (the repo, its
        sdist): a Maya-written fixture FBX named the workspace's own drive
        folders while the gate searched ``Samples~`` alone. Text is the
        denylist's. Widened: 2026-11-08"""
        self.write("test/assets/fixture.bin", b"\x00D:\\work\\repo\\test_assets\\x.png\x00")
        self.write("pkg/Samples~/README.md", "C:\\Users\\someone\\x.png\n")
        found = gate.scan_machine_paths(self.repo, "pubrepo")
        self.assertEqual([f.path for f in found], ["test/assets/fixture.bin"], found)

    def test_a_drive_letter_by_chance_in_compressed_bytes_is_no_path(self):
        """Measured in two committed PNGs' compressed streams: ``K:/9/j8`` and
        ``i:\\./KmN``. A folder of a path is a name of two characters or more."""
        self.write(
            "test/assets/noise.png",
            b"\x89PNG\r\n\x1a\n\x00K:/9/j8\x00i:\\./KmN\x00",
        )
        self.assertEqual(gate.scan_machine_paths(self.repo, "pubrepo"), [])

    def test_main_fails_on_one_even_without_a_denylist(self):
        self.write("pkg/Samples~/Room/Room.fbx", self.FBX_HEAD + b"\x00C:\\Users\\someone\\a.fbx\x00")
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 1)
        self.assertIn("pubrepo/pkg/Samples~/Room/Room.fbx", out)
        os.remove(self.denylist)
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 1, out)
        self.assertIn("machine path", out)

    def test_clean_samples_pass_and_a_missing_denylist_still_skips(self):
        self.write("pkg/Samples~/Room/Room.fbx", self.FBX_HEAD + b"\x00Room.png\x00")
        self.assertEqual(self.run_main("pubrepo")[0], 0)
        os.remove(self.denylist)
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 0)
        self.assertIn("SKIP", out)


class TestPersonalPaths(_RepoCase):
    """Text naming the scanning machine's own folders -- the workspace's
    absolute root, the user's home -- is published with the repo. The
    binary scan read binaries alone and the denylist names clients, so
    m3trik shipped the workspace root in its inventory, its agent briefs and
    push.ps1 (measured 2026-11-08). The rule is derived, never listed: no
    personal path is written in this public repo. Added: 2026-11-08"""

    def test_each_spelling_of_the_roots_matches_and_a_neighbour_does_not(self):
        pattern = gate.personal_paths(workspace="D:/Work/Code/_ws", home="C:/Users/jdoe")
        for text in (
            r"D:\Work\Code\_ws\pythontk\test",
            "d:/work/code/_ws",
            "/d/Work/Code/_ws/x.py",
            r'"D:\\Work\\Code\\_ws"',
            r"C:\Users\jdoe\AppData",
            "/c/Users/jdoe/.claude",
        ):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))
        for text in (
            r"C:\Users\jdoe2\x",
            r"D:\Work\Code\_wsx",
            r"C:\Users\someone\x.png",
            r"C:\Program Files\Autodesk\Maya2025\bin\mayapy.exe",
            "Work/Code/_ws",
        ):
            with self.subTest(text=text):
                self.assertIsNone(pattern.search(text))

    def test_a_posix_root_matches_too(self):
        pattern = gate.personal_paths(workspace="/home/runner/work/ws", home="/home/runner")
        self.assertIsNotNone(pattern.search("cd /home/runner/work/ws/m3trik"))
        self.assertIsNone(pattern.search("/home/runner2/x"))

    def test_main_fails_on_its_own_root_in_text_with_or_without_a_denylist(self):
        self.write("docs/README.md", f"Generated from `{self.root}` today.\n")
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 1, out)
        self.assertIn("pubrepo/docs/README.md:1", out)
        self.assertIn("this machine's own", out)
        os.remove(self.denylist)
        code, out = self.run_main("pubrepo")
        self.assertEqual(code, 1, out)

    def test_a_relative_root_passes(self):
        self.write("docs/README.md", "Generated from `../..` today.\n")
        self.assertEqual(self.run_main("pubrepo")[0], 0)


class TestPublicRepos(unittest.TestCase):
    def test_every_repo_that_publishes_a_package_is_scanned(self):
        """A repo private on GitHub still publishes once its package reaches PyPI:
        the source tarball carries its tests and CHANGELOG. unitytk's did, in
        every release, while the gate skipped it as private."""
        manifest = os.path.join(os.path.dirname(HERE), "workspace.json")
        with open(manifest, encoding="utf-8") as handle:
            units = json.load(handle)["units"]
        published = sorted(u["path"] for u in units if u.get("release", "none") != "none")
        self.assertTrue(published, "workspace.json declares no released unit")
        skipped = [name for name in published if name not in gate.PUBLIC_REPOS]
        self.assertEqual(skipped, [], "these publish to PyPI, so the gate must scan them")


if __name__ == "__main__":
    unittest.main()
