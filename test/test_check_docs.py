"""Tests for check_docs.py's workspace-mode "no [Unreleased] ritual" check
(root CLAUDE.md: "Keep curating CHANGELOG.md — no [Unreleased] ritual").

Regression coverage for the guard added alongside that policy: a repo
CHANGELOG.md carrying a top-level ``## [Unreleased]`` heading must FAIL the
workspace sweep, a normal (year/version-headed) changelog must stay clean,
and the check must not be fooled by an inline/backticked mention of the
literal text or by the same words under a deeper ``###`` heading.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_docs  # noqa: E402


class TestUnreleasedChangelogGuard(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.ws_root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _repo(self, name: str, changelog_text: str) -> Path:
        repo = self.ws_root / name
        (repo / ".git").mkdir(parents=True)
        (repo / "CHANGELOG.md").write_text(changelog_text, encoding="utf-8")
        return repo

    def _changelog_fails(self):
        report = check_docs.Report()
        check_docs.run_workspace(self.ws_root, report)
        return [f for f in report.fails if "changelog" in f]

    def test_unreleased_header_fails(self):
        self._repo(
            "pkgrepo",
            "# Changelog\n\n## [Unreleased]\n- wip fix\n\n## [1.0.0] - 2026-01-01\n- initial release\n",
        )
        fails = self._changelog_fails()
        self.assertTrue(
            any("pkgrepo/CHANGELOG.md" in f and "[Unreleased]" in f for f in fails),
            f"expected a changelog FAIL naming pkgrepo/CHANGELOG.md, got: {fails}",
        )

    def test_normal_changelog_is_clean(self):
        self._repo(
            "pkgrepo",
            "# Changelog\n\n## [1.1.0] - 2026-02-01\n- new feature\n\n## [1.0.0] - 2026-01-01\n- initial release\n",
        )
        self.assertEqual(self._changelog_fails(), [])

    def test_inline_mention_does_not_trigger(self):
        # The literal text appearing mid-line (inline code, prose) must not be
        # mistaken for an actual `## [Unreleased]` heading — the guard is
        # anchored to the start of a line.
        self._repo(
            "pkgrepo",
            "# Changelog\n\n"
            "Notes: this repo does not use a `## [Unreleased]` section by policy.\n\n"
            "## [1.0.0] - 2026-01-01\n- initial release\n",
        )
        self.assertEqual(self._changelog_fails(), [])

    def test_nested_heading_does_not_trigger(self):
        # A deeper heading (### or more #s) is a different section, not the
        # top-level `## [Unreleased]` ritual the policy forbids.
        self._repo(
            "pkgrepo",
            "# Changelog\n\n### [Unreleased]\n- wip, not yet promoted\n\n"
            "## [1.0.0] - 2026-01-01\n- initial release\n",
        )
        self.assertEqual(self._changelog_fails(), [])


class TestSkipUnversioned(unittest.TestCase):
    """``--skip-unversioned``: the CI form, whose workspace holds the repos but
    never the unversioned root.  A missing link target outside every checked-
    out repo is a named SKIP; everything inside a repo is still checked."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.ws_root = Path(self._td.name)
        repo = self.ws_root / "pkg"
        (repo / ".git").mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "README.md").write_text("[guide](docs/guide.md)\n", encoding="utf-8")
        (repo / "docs" / "guide.md").write_text(
            "# Guide\n\n"
            "[root](../../CLAUDE.md)\n"  # the unversioned workspace root
            "[sibling](../../other/CLAUDE.md)\n"  # a repo this checkout lacks
            "[broken](missing.md)\n"  # inside the repo: a real break
            "[anchor](../README.md#nope)\n",  # inside the repo: a real break
            encoding="utf-8",
        )

    def tearDown(self):
        self._td.cleanup()

    def _run(self, skip):
        report = check_docs.Report()
        check_docs.run_workspace(self.ws_root, report, skip_unversioned=skip)
        return report

    def test_without_the_flag_every_missing_target_fails(self):
        links = [f for f in self._run(False).fails if f.startswith("[FAIL] links")]
        self.assertEqual(len(links), 4, links)

    def test_the_flag_skips_only_what_no_checkout_can_hold(self):
        report = self._run(True)
        links = [f for f in report.fails if f.startswith("[FAIL] links")]
        self.assertEqual(len(links), 2, links)
        self.assertTrue(any("missing.md" in f for f in links))
        self.assertTrue(any("#nope" in f for f in links))
        # Every skip is named, so a skip cannot hide a break.
        self.assertEqual(len(report.skips), 2, report.skips)
        self.assertTrue(any("../../CLAUDE.md" in s for s in report.skips))
        self.assertTrue(any("../../other/CLAUDE.md" in s for s in report.skips))

    def test_an_existing_root_target_is_still_checked(self):
        """The flag skips what is MISSING outside the repos; a root file that is
        there is checked like any other (its anchors included)."""
        (self.ws_root / "CLAUDE.md").write_text("# Root\n", encoding="utf-8")
        report = self._run(True)
        self.assertFalse(any("../../CLAUDE.md" in s for s in report.skips))

    def test_the_verdict_line_counts_the_skips(self):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_docs.main(
                ["--workspace", str(self.ws_root), "--skip-unversioned"]
            )
        self.assertEqual(code, 1)  # the two in-repo breaks
        self.assertIn("2 SKIP", out.getvalue())


if __name__ == "__main__":
    unittest.main()
