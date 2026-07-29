# !/usr/bin/python
# coding=utf-8
"""Tests for scripts/check_tooltips.py — the rich-text tooltip gate.

The bugs this gate exists for are all silent: Qt's rich-text parser swallows a
bare ``<`` (or a bogus ``<placeholder>``) up to the next ``>`` and logs nothing,
so a tooltip renders with its tail missing and nobody notices. The regressions
below are the real ones it caught on introduction.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_tooltips as ct  # noqa: E402


class TestIsWellFormed(unittest.TestCase):
    """Structural breakage must fail; HTML that is merely laxer than XML must not."""

    def test_balanced_markup_passes(self):
        self.assertIsNone(ct.is_well_formed("<p><b>Title</b></p><ul><li>one</li></ul>"))

    def test_bare_lt_is_flagged(self):
        # Regression: blendertk render_opacity's Fade Direction bullet read
        # "if < 0.5 or no key -> fade in." and Qt ate the rest of the sentence.
        self.assertIsNotNone(ct.is_well_formed("<li>if < 0.5 or no key.</li>"))

    def test_escaped_lt_passes(self):
        self.assertIsNone(ct.is_well_formed("<li>if &lt; 0.5 or no key.</li>"))

    def test_pseudo_tag_placeholder_is_flagged(self):
        # Regression: "(becomes <prefix>_BS)" rendered as "(becomes _BS)".
        self.assertIsNotNone(ct.is_well_formed("<p>becomes <prefix>_BS</p>"))

    def test_void_elements_are_not_flagged(self):
        """``<br>`` is legal HTML and renders fine; only XML demands ``<br/>``."""
        self.assertIsNone(ct.is_well_formed("<b>a</b><br>\ntext<br><hr>"))

    def test_named_entities_are_not_flagged(self):
        """Qt renders the full HTML entity set; XML predefines only five."""
        self.assertIsNone(ct.is_well_formed("<p>a&nbsp;b &mdash; c</p>"))

    def test_unbalanced_tag_is_flagged(self):
        self.assertIsNotNone(ct.is_well_formed("<p><b>unclosed</p>"))


class TestTooltipCallDetection(unittest.TestCase):
    """Only real tooltip builders are evaluated, however they were reached."""

    @staticmethod
    def _call(src):
        import ast

        return next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call))

    def test_switchboard_passthrough(self):
        self.assertTrue(ct._is_tooltip_call(self._call("self.sb.tooltip.fmt(title='x')")))

    def test_widget_proxy(self):
        self.assertTrue(ct._is_tooltip_call(self._call("w.tooltip.fmt(title='x')")))

    def test_direct_import(self):
        self.assertTrue(ct._is_tooltip_call(self._call("TooltipFormat.fmt(title='x')")))

    def test_placeholder_preview(self):
        self.assertTrue(
            ct._is_tooltip_call(self._call("self.sb.tooltip.placeholder_preview('a', {})"))
        )

    def test_unrelated_call_ignored(self):
        self.assertFalse(ct._is_tooltip_call(self._call("self.sb.message_box('x')")))
        self.assertFalse(ct._is_tooltip_call(self._call("obj.fmt(title='x')")))


class TestWorkspaceSweep(unittest.TestCase):
    """The gate must pass on the workspace it ships in."""

    def test_workspace_is_clean(self):
        workspace = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        if not os.path.isdir(os.path.join(workspace, "uitk")):
            self.skipTest("not running inside the monorepo workspace")
        self.assertEqual(ct.main(["--workspace", workspace]), 0)


if __name__ == "__main__":
    unittest.main()
