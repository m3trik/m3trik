"""Tests for compare_panel_surface.py — the Maya->Blender parity-matrix sweep.

Regression coverage for two things the sweep must not get wrong:

- The Surface extractor's syntax-error handling: a panel / slot .py with invalid
  Python must fail the sweep with a clean, file-naming message (matching the
  module's `_check_duplicate_keys` convention) rather than an opaque uncaught
  SyntaxError traceback that aborts the whole CI parity gate.
- `--panel` resolution: it must land on the same file `--all` pairs by `*Slots`
  class. Resolving by filename alone picked blendertk's Qt-free ENGINE module
  over its real panel, diffing the Maya panel against an empty surface and
  reporting every real control as a phantom gap."""

import sys
import ast
import unittest
from pathlib import Path

SCRIPTS = Path(r"O:\Cloud\Code\_scripts\m3trik\scripts")
sys.path.insert(0, str(SCRIPTS))

import compare_panel_surface as cps  # noqa: E402


class TestSurfaceSyntaxGuard(unittest.TestCase):
    def _write(self, name, text):
        import tempfile

        d = Path(tempfile.mkdtemp(prefix="cps_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        p = d / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_syntax_error_exits_naming_file_not_raw_traceback(self):
        # A malformed panel/slot file (e.g. mid-refactor) must not abort the sweep
        # with an uncaught SyntaxError; it should sys.exit naming the offending file.
        bad = self._write("broken_slots.py", "def f(:\n    pass\n")
        with self.assertRaises(SystemExit) as ctx:
            cps.Surface(bad)
        msg = str(ctx.exception.code)
        self.assertIn(bad, msg)
        self.assertIn("invalid syntax", msg)

    def test_valid_file_still_extracts(self):
        # The guard must not disturb the happy path: a well-formed file parses fine.
        good = self._write(
            "ok_slots.py",
            "class OkSlots:\n"
            "    def b000(self):\n"
            "        pass\n",
        )
        surf = cps.Surface(good)
        self.assertIn("b000", surf.slots)

    def test_extract_reuses_loaded_source_no_second_read(self):
        # The parse now consumes the already-loaded self.src; a valid parse must
        # still yield an ast.Module (proves the reused-source path works).
        good = self._write("plain_slots.py", "x = 1\n")
        surf = cps.Surface(good)
        self.assertIsInstance(ast.parse(surf.src), ast.Module)


class TestPanelResolution(unittest.TestCase):
    """`--panel <name>` must resolve to the twin `--all` pairs by class.

    The exporter is the shape that broke it: blendertk ships BOTH
    `_scene_exporter.py` (the Qt-free engine, no controls) and
    `scene_exporter_slots.py` (the panel), and the panel does not share the
    Maya file's stem -- so a filename glob picked the engine and no
    `_scene_exporter*` pattern could have found the real twin at all.
    """

    SLOTS_SRC = "class WidgetSlots:\n    def b000(self):\n        pass\n"
    ENGINE_SRC = "class WidgetEngine:\n    pass\n"

    def setUp(self):
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="cps_resolve_"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        def write(rel, text):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return str(p)

        # mayatk: the panel IS `_widget.py` (mirrors mayatk's `_scene_exporter.py`).
        self.maya_panel = write("mayatk/mayatk/env_utils/_widget.py", self.SLOTS_SRC)
        # blendertk: same stem is the ENGINE; the panel lives under another name.
        self.blend_engine = write(
            "blendertk/blendertk/env_utils/_widget.py", self.ENGINE_SRC
        )
        self.blend_panel = write(
            "blendertk/blendertk/env_utils/widget_slots.py", self.SLOTS_SRC
        )

        original_root = cps.ROOT
        cps.ROOT = str(root)
        self.addCleanup(lambda: setattr(cps, "ROOT", original_root))

    def test_stem_match_skips_the_engine_for_the_real_panel(self):
        maya, blend = cps._resolve("_widget")
        self.assertEqual(maya, self.maya_panel)
        self.assertEqual(blend, self.blend_panel)
        self.assertNotEqual(blend, self.blend_engine)

    def test_class_name_form_resolves_the_same_pair(self):
        # The names --all prints (`Widget`) and the class itself must both work.
        for name in ("Widget", "WidgetSlots"):
            with self.subTest(name=name):
                self.assertEqual(cps._resolve(name), (self.maya_panel, self.blend_panel))

    def test_unresolvable_panel_exits_naming_the_package(self):
        with self.assertRaises(SystemExit) as ctx:
            cps._resolve("no_such_panel")
        self.assertIn("no_such_panel", str(ctx.exception.code))


if __name__ == "__main__":
    unittest.main()
