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


if __name__ == "__main__":
    unittest.main()
