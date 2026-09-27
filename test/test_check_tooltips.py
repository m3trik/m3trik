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
        self.assertTrue(
            ct._is_tooltip_call(self._call("self.sb.tooltip.fmt(title='x')"))
        )

    def test_widget_proxy(self):
        self.assertTrue(ct._is_tooltip_call(self._call("w.tooltip.fmt(title='x')")))

    def test_direct_import(self):
        self.assertTrue(ct._is_tooltip_call(self._call("TooltipFormat.fmt(title='x')")))

    def test_placeholder_preview(self):
        self.assertTrue(
            ct._is_tooltip_call(
                self._call("self.sb.tooltip.placeholder_preview('a', {})")
            )
        )

    def test_unrelated_call_ignored(self):
        self.assertFalse(ct._is_tooltip_call(self._call("self.sb.message_box('x')")))
        self.assertFalse(ct._is_tooltip_call(self._call("obj.fmt(title='x')")))


class TestResetControls(unittest.TestCase):
    """A Reset to Defaults button goes through ResetGesture, or the build fails.

    The regressions are the real drift it caught on introduction: the uitk
    bridge (rizom among its panels) and fourteen mayatk/blendertk panels wired
    their own reset, so their tooltip never taught Shift+Click / Ctrl+Shift+Click.
    """

    PANEL = "mayatk/mayatk/edit_utils/curtain/curtain_slots.py"
    UI = (
        '<ui><widget class="QPushButton" name="b001">'
        '<property name="text"><string>Reset to Defaults</string></property>'
        "</widget></ui>"
    )
    WIRED = "class PanelSlots:\n    def b001_init(self, w):\n        ResetGesture(w)\n"
    HAND = "class PanelSlots:\n    def b001(self):\n        self.ui.state.reset_all()\n"

    @staticmethod
    def _scan(src, rel=PANEL):
        import ast

        failures = []
        ct.scan_reset_python(rel, ast.parse(src), failures)
        return failures

    @staticmethod
    def _write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _scan_ui(self, path):
        failures = []
        seen = ct.scan_reset_ui(path, "pkg/panel.ui", failures, {})
        return seen, failures

    def test_a_hand_wired_reset_all_is_flagged(self):
        src = "def b001(self):\n    self.ui.state.reset_all()\n"
        self.assertEqual(len(self._scan(src)), 1)

    def test_a_reset_all_handed_to_a_signal_is_flagged(self):
        src = (
            "def b001_init(self, w):\n    w.clicked.connect(self.ui.state.reset_all)\n"
        )
        self.assertEqual(len(self._scan(src)), 1)

    def test_a_labelled_button_without_the_gesture_is_flagged(self):
        # Regression: the bridge's own button, clicked straight to its reset.
        src = (
            "def build(self):\n    btn.setText('Reset to Defaults')\n"
            "    btn.clicked.connect(self.reset)\n"
        )
        self.assertEqual(len(self._scan(src)), 1)
        menu = "def header_init(self, w):\n    w.menu.add('QPushButton', setText='Restore Defaults')\n"
        self.assertEqual(len(self._scan(menu)), 1)
        # A label held for later (the widget combo's action row) is a control too.
        kept = "def __init__(self):\n    self._label = 'Restore Defaults'\n"
        self.assertEqual(len(self._scan(kept)), 1)

    def test_the_gesture_must_be_built_where_the_button_is(self):
        src = "def build(self):\n    btn.setText('Reset to Defaults')\n    ResetGesture(btn)\n"
        self.assertEqual(self._scan(src), [])
        elsewhere = (
            "def build(self):\n    btn.setText('Reset to Defaults')\n"
            "def other(self):\n    ResetGesture(other_btn)\n"
        )
        self.assertEqual(len(self._scan(elsewhere)), 1)

    def test_prose_about_a_reset_is_not_a_control(self):
        src = (
            "def header_init(self, w):\n"
            "    self.sb.tooltip.fmt(title='Reset to Defaults', body='x')\n"
            "    self.sb.message_box('Reset to Defaults')\n"
            '    """Reset to Defaults."""\n'
        )
        self.assertEqual(self._scan(src), [])

    def test_tests_and_the_primitives_are_exempt(self):
        src = "state.reset_all()\n"
        self.assertEqual(self._scan(src, "mayatk/test/test_curtain.py"), [])
        self.assertEqual(self._scan(src, "uitk/uitk/managers/reset_gesture.py"), [])

    def test_a_ui_button_needs_its_own_slots_to_wire_it(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "panel.ui")
            self._write(path, self.UI)
            self.assertEqual(len(self._scan_ui(path)[1]), 1, "no slots module")
            self._write(os.path.join(folder, "panel.py"), self.HAND)
            self.assertEqual(len(self._scan_ui(path)[1]), 1, "hand-wired")
            # Regression: a sibling wiring ITS b001 used to satisfy every .ui there.
            self._write(
                os.path.join(folder, "other.py"), self.WIRED.replace("Panel", "Other")
            )
            self.assertEqual(len(self._scan_ui(path)[1]), 1, "a sibling's wiring")
            self._write(os.path.join(folder, "panel.py"), self.WIRED)
            self.assertEqual(self._scan_ui(path), (1, []))

    def test_a_ui_binds_its_slots_class_before_a_same_named_engine(self):
        # lightmap_baker.ui: LightmapBakerSlots lives in *_slots.py; the engine
        # module shares the .ui's name and must not be asked to wire it.
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "panel.ui")
            self._write(path, self.UI)
            self._write(os.path.join(folder, "panel.py"), "class Panel:\n    pass\n")
            self._write(os.path.join(folder, "panel_slots.py"), self.WIRED)
            self.assertEqual(self._scan_ui(path), (1, []))

    def test_tentacle_ui_binds_each_dcc_slots_module(self):
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "ui", "panel.ui")
            self._write(path, self.UI)
            self._write(os.path.join(root, "slots", "maya", "panel.py"), self.WIRED)
            self._write(os.path.join(root, "slots", "blender", "panel.py"), self.HAND)
            seen, failures = self._scan_ui(path)
            self.assertEqual(len(failures), 1)
            self.assertIn("slots/blender/panel.py", failures[0][2])


class TestWorkspaceSweep(unittest.TestCase):
    """The gate must pass on the workspace it ships in."""

    def test_workspace_is_clean(self):
        workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if not os.path.isdir(os.path.join(workspace, "uitk")):
            self.skipTest("not running inside the monorepo workspace")
        self.assertEqual(ct.main(["--workspace", workspace]), 0)


if __name__ == "__main__":
    unittest.main()
