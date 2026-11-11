#!/usr/bin/python
# coding=utf-8
"""Tests for setup_workspace.py -- a clone of m3trik brings the workspace up.

The plan is data (what is missing, and the command that makes it); applying it
is run here over local bare repos, so the clones are real and nothing reaches
a network. The environment's steps are held as commands: making a virtual
environment and installing into it is pip's own work.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import setup_workspace as setup  # noqa: E402
import sync_workspace as sw  # noqa: E402

FIXTURE = {
    "cascade": ["core", "app"],
    "units": [
        {"path": "core", "release": "cascade", "domain": "Core"},
        {"path": "app", "release": "cascade", "role": "product", "domain": "App"},
        {"path": "infra", "release": "none", "domain": "Infra"},
        {"path": "tools", "release": "none", "domain": "Tools"},
        {"path": "tools/scripts", "release": "none", "domain": "Scripts"},
        {"path": "kit", "release": "standalone", "role": "product", "domain": "Kit"},
        {"path": "side", "release": "standalone", "domain": "Side"},
    ],
}


def _git(folder: Path, *args: str) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(folder), *identity, *args], check=True, capture_output=True)


class TestRemoteBase(unittest.TestCase):
    def test_the_siblings_are_cloned_from_where_this_clone_came_from(self):
        cases = {
            "https://github.com/owner/m3trik.git": "https://github.com/owner/",
            "https://github.com/owner/m3trik/": "https://github.com/owner/",
            "git@github.com:owner/m3trik.git": "git@github.com:owner/",
            "git@host:m3trik.git": "git@host:",
            r"C:\remotes\m3trik.git": "C:/remotes/",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "-q")
            with self.assertRaises(ValueError):
                setup.remote_base(repo)  # no origin: nowhere to clone from
            _git(repo, "remote", "add", "origin", "https://example.com/x.git")
            for url, base in cases.items():
                _git(repo, "remote", "set-url", "origin", url)
                with self.subTest(url=url):
                    self.assertEqual(setup.remote_base(repo), base)


class TestUnits(unittest.TestCase):
    def test_the_default_is_the_cascade_and_the_products_in_manifest_order(self):
        self.assertEqual(setup.default_units(FIXTURE), ["core", "app", "kit"])
        self.assertEqual(setup.named_units("", FIXTURE), ["core", "app", "kit"])

    def test_the_real_default_is_what_the_m3trik_distribution_installs(self):
        self.assertEqual(
            setup.default_units(),
            ["pythontk", "uitk", "mayatk", "blendertk", "tentacle", "extapps"],
        )

    def test_all_names_each_declared_repo_once_and_an_unknown_name_is_refused(self):
        self.assertEqual(
            setup.named_units("all", FIXTURE), ["core", "app", "infra", "tools", "kit", "side"]
        )
        self.assertEqual(setup.named_units(" side , infra ", FIXTURE), ["side", "infra"])
        with self.assertRaises(ValueError):
            setup.named_units("core,nowhere", FIXTURE)


class TestPlan(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.workspace = Path(self._td.name) / "workspace"
        self.workspace.mkdir()

    def test_only_what_is_missing_is_planned_and_the_root_comes_last(self):
        (self.workspace / "uitk").mkdir()
        steps = setup.plan(self.workspace, ["pythontk", "uitk"], "https://host/owner/", venv=False)
        self.assertEqual([step["do"] for step in steps], ["clone", "root"])
        self.assertEqual(
            steps[0]["command"],
            ["git", "clone", "https://host/owner/pythontk", str(self.workspace / "pythontk")],
        )
        self.assertIsNone(steps[-1]["command"])

    def test_a_new_environment_installs_each_ecosystem_package_present_editable(self):
        steps = setup.plan(self.workspace, ["pythontk", "uitk"], "https://host/owner/")
        self.assertEqual([step["do"] for step in steps], ["clone", "clone", "venv", "install", "root"])
        venv, install = steps[2]["command"], steps[3]["command"]
        self.assertEqual(venv, [sys.executable, "-m", "venv", str(self.workspace / ".venv")])
        self.assertEqual(install[0], str(setup.venv_python(self.workspace / ".venv")))
        self.assertEqual(install[1:6], ["-m", "pip", "install", "--config-settings", "editable_mode=compat"])
        self.assertEqual(
            install[6:], ["-e", str(self.workspace / "pythontk"), "-e", str(self.workspace / "uitk")]
        )

    def test_an_existing_environment_is_left_as_it_is(self):
        (self.workspace / ".venv").mkdir()
        steps = setup.plan(self.workspace, ["pythontk"], "https://host/owner/")
        self.assertEqual([step["do"] for step in steps], ["clone", "root"])

    def test_the_root_is_planned_only_where_this_is_the_workspace(self):
        """Without the cascade's first package beside the clone the folder is
        someone's: the clones asked for go there, the root's files do not."""
        steps = setup.plan(self.workspace, ["uitk"], "https://host/owner/", venv=False)
        self.assertEqual([step["do"] for step in steps], ["clone"])

    def test_this_clone_is_never_cloned_again_whatever_its_folder_is_called(self):
        steps = setup.plan(self.workspace, [sw.UNIT, "pythontk"], "https://host/owner/", venv=False)
        self.assertEqual([step["what"].split("/")[0] for step in steps if step["do"] == "clone"], ["pythontk"])


class TestApply(unittest.TestCase):
    """The whole run over local bare repos: real clones, no network."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        top = Path(self._td.name)
        self.workspace = top / "workspace"
        self.workspace.mkdir()
        self.remotes = top / "remotes"
        work = top / "work"
        work.mkdir()
        _git(work, "init", "-q")
        (work / "README.md").write_text("# pythontk\n", encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-qm", "x")
        self.remotes.mkdir()
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(work), str(self.remotes / "pythontk.git")],
            check=True, capture_output=True,
        )
        self.base = self.remotes.as_posix() + "/"

    def test_missing_repos_are_cloned_a_present_folder_is_untouched_and_the_root_is_built(self):
        mine = self.workspace / "uitk" / "mine.txt"
        mine.parent.mkdir()
        mine.write_text("a person's own work", encoding="utf-8")
        # A folder that is no unit at all, holding another project's rules.
        theirs = self.workspace / "other" / "CLAUDE.md"
        theirs.parent.mkdir()
        theirs.write_text("Use tabs.\n", encoding="utf-8")
        steps = setup.plan(self.workspace, ["pythontk", "uitk"], self.base, venv=False)
        self.assertEqual(setup.apply(steps, self.workspace), [])
        self.assertEqual(theirs.read_text(encoding="utf-8"), "Use tabs.\n")
        self.assertEqual(sorted(p.name for p in theirs.parent.iterdir()), ["CLAUDE.md"])
        self.assertTrue((self.workspace / "pythontk" / "README.md").is_file())
        self.assertTrue((self.workspace / "pythontk" / ".git").exists())
        self.assertEqual(mine.read_text(encoding="utf-8"), "a person's own work")
        self.assertFalse((self.workspace / "uitk" / ".git").exists())
        for name in ("AGENTS.md", "CLAUDE.md", ".agents/packs/principles.md"):
            self.assertTrue((self.workspace / name).is_file(), name)
        self.assertEqual(sw.root_problems(self.workspace), [])
        # Run again: nothing is left to do but the root, which is already in line.
        again = setup.plan(self.workspace, ["pythontk", "uitk"], self.base, venv=False)
        self.assertEqual([step["do"] for step in again], ["root"])
        self.assertEqual(setup.apply(again, self.workspace), [])

    def test_a_clone_that_fails_stops_the_run_before_anything_else_is_made(self):
        steps = setup.plan(self.workspace, ["nowhere", "pythontk"], self.base, venv=False)
        (problem,) = setup.apply(steps, self.workspace)
        self.assertIn("clone failed", problem)
        self.assertFalse((self.workspace / "pythontk").exists())
        self.assertFalse((self.workspace / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
