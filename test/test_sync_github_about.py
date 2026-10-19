"""Tests for sync_github_about.py -- a repo's GitHub About box held to its pyproject.

The pyproject ``[project]`` table is the declaration (description, keywords, the
package name that names its PyPI page); the About box is the restatement. These
pin the mapping, the "no keywords = not managed" rule that keeps a sibling cloned
before its metadata lands green, the exact-set topic write (``--add-topic`` could
never remove a stale one), and the exit codes the CI step reads.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_github_about as sga  # noqa: E402

PYPROJECT = """\
[project]
name = "probetk"
description = "A probe package."
{keywords}
[project.urls]
Homepage = "https://github.com/someone/probetk"
Repository = "{repository}"
"""


class _Workspace(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sga_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = mock.patch.object(sga, "WORKSPACE", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(
        self,
        keywords='keywords = ["maya", "dcc"]',
        repository="https://github.com/someone/probetk",
    ):
        pkg = self.root / "probetk"
        pkg.mkdir(exist_ok=True)
        (pkg / "pyproject.toml").write_text(
            PYPROJECT.format(keywords=keywords, repository=repository), encoding="utf-8"
        )
        return pkg


class TestDeclared(_Workspace):
    def test_maps_keywords_to_sorted_topics_and_pypi_homepage(self):
        want = sga.declared(self.write())
        self.assertEqual(
            want,
            {
                "slug": "someone/probetk",
                "description": "A probe package.",
                "homepage": "https://pypi.org/project/probetk/",
                "topics": ["dcc", "maya"],
            },
        )

    def test_no_keywords_is_not_managed(self):
        self.assertIsNone(sga.declared(self.write(keywords="")))

    def test_slug_tolerates_a_git_suffix(self):
        pkg = self.write(repository="https://github.com/someone/probetk.git")
        self.assertEqual(sga.declared(pkg)["slug"], "someone/probetk")

    def test_keyword_github_rejects_is_an_error(self):
        for bad in ('"Maya"', '"two words"', '"-lead"'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    sga.declared(self.write(keywords=f"keywords = [{bad}]"))

    def test_no_project_table_is_not_managed(self):
        pkg = self.root / "probetk"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text("[tool.x]\ny = 1\n", encoding="utf-8")
        self.assertIsNone(sga.declared(pkg))

    def test_missing_description_clears_the_about_text(self):
        pkg = self.write()
        text = (pkg / "pyproject.toml").read_text(encoding="utf-8")
        (pkg / "pyproject.toml").write_text(
            text.replace('description = "A probe package."\n', ""), encoding="utf-8"
        )
        self.assertEqual(sga.declared(pkg)["description"], "")

    def test_non_github_repository_is_an_error(self):
        with self.assertRaises(ValueError):
            sga.declared(self.write(repository="https://gitlab.com/someone/probetk"))


class TestMain(_Workspace):
    def published(self, **overrides):
        repo = {
            "description": "A probe package.",
            "homepage": "https://pypi.org/project/probetk/",
            "topics": ["maya", "dcc"],
        }
        repo.update(overrides)
        return repo

    def run_main(self, *args, repo=None):
        calls = []

        def fake_gh(gh_args, payload=None):
            calls.append((gh_args, payload))
            return repo if len(gh_args) == 1 else None

        out = io.StringIO()
        with (
            mock.patch.object(sga, "_gh", side_effect=fake_gh),
            mock.patch.object(sga.shutil, "which", return_value="gh"),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(out),
        ):
            code = sga.main([*args, "probetk"])
        return code, calls, out.getvalue()

    def test_in_sync_exits_zero(self):
        self.write()
        code, calls, _ = self.run_main("--check", repo=self.published())
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)  # one read, no write

    def test_drift_exits_one_and_names_the_apply_command(self):
        self.write()
        code, _, out = self.run_main("--check", repo=self.published(description="Old."))
        self.assertEqual(code, 1)
        self.assertIn("--apply", out)

    def test_check_is_the_default(self):
        self.write()
        code, calls, _ = self.run_main(repo=self.published(topics=[]))
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)

    def test_apply_writes_the_exact_topic_set(self):
        self.write()
        code, calls, _ = self.run_main("--apply", repo=self.published(topics=["stale"]))
        self.assertEqual(code, 0)
        self.assertEqual(
            calls[1:],
            [
                (
                    ["-X", "PUT", "repos/someone/probetk/topics"],
                    {"names": ["dcc", "maya"]},
                )
            ],
        )

    def test_apply_patches_description_and_homepage_together(self):
        self.write()
        _, calls, _ = self.run_main("--apply", repo=self.published(homepage=""))
        self.assertEqual(
            calls[1:],
            [
                (
                    ["-X", "PATCH", "repos/someone/probetk"],
                    {
                        "description": "A probe package.",
                        "homepage": "https://pypi.org/project/probetk/",
                    },
                )
            ],
        )

    def test_unmanaged_repo_never_queries_github(self):
        self.write(keywords="")
        code, calls, out = self.run_main("--check", repo=self.published())
        self.assertEqual((code, calls), (0, []))
        self.assertIn("SKIP", out)

    def test_missing_gh_exits_two(self):
        self.write()
        with (
            mock.patch.object(sga.shutil, "which", return_value=None),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(sga.main(["--check", "probetk"]), 2)

    def test_unreadable_pyproject_exits_two_naming_the_package(self):
        pkg = self.root / "probetk"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text("[project\n", encoding="utf-8")
        err = io.StringIO()
        with (
            mock.patch.object(sga.shutil, "which", return_value="gh"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(sga.main(["--check", "probetk"]), 2)
        self.assertIn("probetk", err.getvalue())

    def test_gh_failure_exits_two(self):
        self.write()
        err = sga.subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404")
        with (
            mock.patch.object(sga, "_gh", side_effect=err),
            mock.patch.object(sga.shutil, "which", return_value="gh"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(sga.main(["--check", "probetk"]), 2)


class TestGh(unittest.TestCase):
    def test_payload_goes_to_stdin_as_json(self):
        done = mock.Mock(stdout="")
        with mock.patch.object(sga.subprocess, "run", return_value=done) as run:
            self.assertIsNone(
                sga._gh(["-X", "PUT", "repos/a/b/topics"], {"names": ["x"]})
            )
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:2], ["gh", "api"])
        self.assertEqual(cmd[-2:], ["--input", "-"])
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"names": ["x"]})


if __name__ == "__main__":
    unittest.main()
