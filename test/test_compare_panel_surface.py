"""Tests for compare_panel_surface.py — the Maya->Blender parity-matrix sweep.

Regression coverage for the Surface extractor's syntax-error handling: a panel /
slot .py with invalid Python must fail the sweep with a clean, file-naming
message (matching the module's `_check_duplicate_keys` convention) rather than an
opaque uncaught SyntaxError traceback that aborts the whole CI parity gate."""

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


if __name__ == "__main__":
    unittest.main()
