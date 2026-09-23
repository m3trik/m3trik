#!/usr/bin/python
# coding=utf-8
"""Tests for check_version_bump.py -- the off-chain publish.yml's bump gate.

Each case builds a throwaway git repo shaped like unitytk/extapps (a package
dir, pyproject.toml, CHANGELOG.md, docs/, test/), makes one "push" on top of a
base commit, and asks the gate what that push means. The 2026-09-18 extapps
case -- shipped source changed at the version PyPI already has -- is the one
that must fail; a deliberate hold and a non-shipping push must not.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_version_bump as g  # noqa: E402

PKG = "extapps"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class TestCheckVersionBump(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "core.autocrlf", "false")
        self._write(f"{PKG}/__init__.py", '__version__ = "0.1.18"\n')
        self._write(f"{PKG}/converter.py", "x = 1\n")
        self._write("pyproject.toml", "[project]\nname = 'extapps'\n")
        self._write("CHANGELOG.md", "# Changelog\n\n- old entry, no version bump.\n")
        self._write("docs/notes.md", "notes\n")
        self.base = self._commit("base")

    def _write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _append(self, rel, text):
        path = self.repo / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def _commit(self, msg):
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", msg)
        return _git(self.repo, "rev-parse", "HEAD")

    def _decide(self, published="0.1.18", base=None):
        return g.decide(self.repo, PKG, published, self.base if base is None else base)

    # -- the trap ----------------------------------------------------------

    def test_shipped_change_at_published_version_fails(self):
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._commit("rdo rows")
        v = self._decide()
        self.assertFalse(v.ok)
        self.assertFalse(v.publish)
        self.assertIn(f"{PKG}/converter.py", v.message)
        self.assertIn("no version bump", v.message, "the message must name the hold")

    def test_pyproject_change_is_shipped(self):
        self._append("pyproject.toml", "dependencies = ['pythontk>=0.9.33']\n")
        self._commit("floor")
        self.assertFalse(self._decide().ok)

    def test_the_whole_push_range_is_judged_not_just_the_tip(self):
        # A shipped change in an EARLIER commit of the push, with a docs-only tip.
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._commit("code")
        self._append("docs/notes.md", "more\n")
        self._commit("docs")
        self.assertFalse(self._decide().ok)

    # -- the passes --------------------------------------------------------

    def test_bumped_version_publishes(self):
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._write(f"{PKG}/__init__.py", '__version__ = "0.1.19"\n')
        self._commit("bump")
        v = self._decide()
        self.assertEqual((v.ok, v.publish, v.version), (True, True, "0.1.19"))

    def test_unpublished_package_publishes(self):
        v = self._decide(published="none")
        self.assertEqual((v.ok, v.publish), (True, True))

    def test_non_shipping_push_passes_without_publishing(self):
        self._append("docs/notes.md", "more\n")
        self._write("test/test_x.py", "pass\n")
        self._write(".github/workflows/x.yml", "on: push\n")
        self._append("CHANGELOG.md", "- docs only.\n")
        self._commit("docs")
        v = self._decide()
        self.assertEqual((v.ok, v.publish), (True, False))

    def test_changelog_hold_passes(self):
        self._append(f"{PKG}/converter.py", "# comment\n")
        self._append("CHANGELOG.md", "- Comments only, so No Version Bump.\n")
        self._commit("held")
        v = self._decide()
        self.assertEqual((v.ok, v.publish), (True, False))
        self.assertIn("held", v.message)

    def test_hold_must_be_added_by_this_push(self):
        # The base CHANGELOG already says "no version bump" -- an OLD hold does
        # not cover a new shipped change.
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._append("CHANGELOG.md", "- new converter rows.\n")
        self._commit("code")
        self.assertFalse(self._decide().ok)

    def test_an_edited_old_hold_is_not_a_new_hold(self):
        """Fixing one word in an OLD hold line puts the phrase on a ``+`` line
        of the diff; read as a declaration, it skipped the publish."""
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._write(
            "CHANGELOG.md", "# Changelog\n\n- old entry (fixed), no version bump.\n"
        )
        self._commit("code + a typo fix in an old entry")
        self.assertFalse(self._decide().ok)

    def test_no_range_only_reports(self):
        # workflow_dispatch: github.event.before is empty.
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._commit("code")
        v = self._decide(base="")
        self.assertEqual((v.ok, v.publish), (True, False))

    def test_rerun_of_a_push_that_already_published_passes(self):
        # "Re-run all jobs" after the upload: PyPI now serves the version THIS
        # push moved to, so its shipped changes went out with it.
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._write(f"{PKG}/__init__.py", '__version__ = "0.1.19"\n')
        self._commit("bump")
        v = self._decide(published="0.1.19")
        self.assertEqual((v.ok, v.publish), (True, False))
        self.assertIn("re-run", v.message)

    # -- cannot tell is not "nothing shipped" ------------------------------

    def test_unresolvable_base_fails(self):
        for base in ("0" * 40, "deadbeef" * 5):
            with self.subTest(base=base):
                self.assertFalse(self._decide(base=base).ok)

    # -- CLI contract ------------------------------------------------------

    def test_main_writes_github_outputs_and_exit_code(self):
        self._append(f"{PKG}/converter.py", "y = 2\n")
        self._commit("code")
        cmd = [
            sys.executable,
            str(SCRIPTS / "check_version_bump.py"),
            PKG,
            "--repo",
            str(self.repo),
            "--published",
            "0.1.18",
            "--base",
            self.base,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.split(), ["version=0.1.18", "publish=false"])
        self.assertIn("::error::", proc.stderr)

        self._write(f"{PKG}/__init__.py", '__version__ = "0.1.19"\n')
        self._commit("bump")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.split(), ["version=0.1.19", "publish=true"])


if __name__ == "__main__":
    unittest.main()
