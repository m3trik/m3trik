#!/usr/bin/python
# coding=utf-8
"""Tests for scripts/check_dcc_twins.py -- the mayatk<->blendertk drift guard.

The normalizer is the whole safety of this gate, and it has one property that
must never regress: host vocabulary is folded in PROSE but compared VERBATIM in
code. Fold it everywhere and ``import mayatk`` inside blendertk compares equal to
``import blendertk`` inside blendertk -- a real cross-wiring bug reported as
"in sync". The gate would still pass every run, which is precisely how a guard
becomes worse than no guard.
"""

import os
import sys
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import check_dcc_twins as gate  # noqa: E402


class FoldSafetyTest(unittest.TestCase):
    """The code-aware fold must not mask a cross-wiring bug."""

    def norm(self, src):
        return gate.twin_normalized(src.splitlines(), "x.py")

    def test_host_names_fold_in_comments(self):
        a = self.norm("x = 1  # the Maya side\n")
        b = self.norm("x = 1  # the Blender side\n")
        self.assertEqual(a, b)

    def test_host_names_fold_in_docstrings(self):
        a = self.norm('def f():\n    """Runs in Maya."""\n    return 1\n')
        b = self.norm('def f():\n    """Runs in Blender."""\n    return 1\n')
        self.assertEqual(a, b)

    def test_a_wrong_import_does_NOT_compare_equal(self):
        """The load-bearing case: code is compared verbatim."""
        a = self.norm("import mayatk\n")
        b = self.norm("import blendertk\n")
        self.assertNotEqual(a, b)

    def test_a_wrong_call_does_NOT_compare_equal(self):
        a = self.norm("mtk.do_thing()\n")
        b = self.norm("btk.do_thing()\n")
        self.assertNotEqual(a, b)

    def test_code_around_a_multiline_string_is_not_folded(self):
        """`x = mtk.f(\"\"\"Maya...` must keep its `mtk` unfolded."""
        a = self.norm('x = mtk.f("""Maya\nnotes\n""")\n')
        b = self.norm('x = btk.f("""Blender\nnotes\n""")\n')
        self.assertNotEqual(a, b)

    def test_real_code_differences_survive_the_fold(self):
        a = self.norm("def f():\n    return 1\n")
        b = self.norm("def f():\n    return 2\n")
        self.assertNotEqual(a, b)

    def test_unparseable_source_degrades_instead_of_raising(self):
        self.assertTrue(self.norm("def f(:\n"))

    def test_unparseable_source_does_NOT_mask_a_cross_wiring(self):
        """An unparseable twin must report drift, never a false ``ok``.

        The coarse whole-line fold used to be the fallback here, which folded
        ``import mayatk`` / ``import blendertk`` to the same placeholder -- so a
        cross-wired twin that also happened not to tokenize compared EQUAL and
        the entry reported ``ok``. That is the one failure this normalizer
        exists to prevent, arriving through its own error path.
        """
        a = self.norm("import mayatk\ndef f(:\n")
        b = self.norm("import blendertk\ndef f(:\n")
        self.assertNotEqual(a, b)


class _TwinTreeCase(unittest.TestCase):
    """Build a synthetic two-package tree and point the gate at it."""

    A_SRC = B_SRC = ""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="twins_test_")
        self._saved = gate.REPO
        gate.REPO = self.root
        self.rel = "pkg/mod.py"
        self.write("mayatk", self.A_SRC)
        self.write("blendertk", self.B_SRC)

    def tearDown(self):
        gate.REPO = self._saved
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, package, body):
        path = os.path.join(self.root, package, package, "pkg")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def spec(self, **kw):
        kw.setdefault("reason", "test fixture")
        return gate.TwinSpec(rel=self.rel, **kw)


class WholeFileCompareTest(_TwinTreeCase):
    A_SRC = "class C:\n    def f(self):\n        # Maya path\n        return 1\n"
    B_SRC = "class C:\n    def f(self):\n        # Blender path\n        return 1\n"

    def test_prose_only_difference_is_ok(self):
        self.assertEqual(gate.compare(self.spec())[0], "ok")

    def test_code_difference_is_drift(self):
        self.write("blendertk", self.B_SRC.replace("return 1", "return 2"))
        status, detail = gate.compare(self.spec())
        self.assertEqual(status, "drift")
        self.assertTrue(detail)

    def test_absent_sibling_is_not_a_failure(self):
        shutil.rmtree(os.path.join(self.root, "blendertk"))
        self.assertEqual(gate.compare(self.spec())[0], "absent")


class SymbolCompareTest(_TwinTreeCase):
    A_SRC = (
        "class C:\n"
        "    def shared(self):\n        return 1\n"
        "    def diverged(self):\n        return 'maya'\n"
    )
    B_SRC = (
        "class C:\n"
        "    def shared(self):\n        return 1\n"
        "    def diverged(self):\n        return 'blender-specific-thing'\n"
    )

    def test_pinning_only_the_shared_symbol_passes(self):
        """The point of symbol mode: pin what IS shared, say nothing about the rest."""
        self.assertEqual(gate.compare(self.spec(symbols=["C.shared"]))[0], "ok")

    def test_pinning_a_diverged_symbol_is_drift(self):
        self.assertEqual(gate.compare(self.spec(symbols=["C.diverged"]))[0], "drift")

    def test_a_renamed_symbol_is_missing_not_ok(self):
        """A guard that silently stops covering a symbol is the worst outcome."""
        self.write("blendertk", self.B_SRC.replace("def shared", "def renamed"))
        status, detail = gate.compare(self.spec(symbols=["C.shared"]))
        self.assertEqual(status, "missing")
        self.assertIn("blendertk", detail[0])

    APPENDED = """

def %s():
    return 3
"""

    def test_extract_symbols_finds_module_level_functions(self):
        """A ledger may name one, and an invisible symbol reads as `missing`."""
        path = os.path.join(self.root, "mayatk", "mayatk", "pkg", "mod.py")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(self.APPENDED % "module_level")
        self.assertIn("module_level", gate.extract_symbols(path, self.rel))

    def test_a_module_level_twin_compares_rather_than_going_missing(self):
        """Before the fix this read as `missing`, which compare() fails on."""
        for pkg in ("mayatk", "blendertk"):
            path = os.path.join(self.root, pkg, pkg, "pkg", "mod.py")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(self.APPENDED % "shared_fn")
        self.assertEqual(gate.compare(self.spec(symbols=["shared_fn"]))[0], "ok")

    def test_extract_symbols_finds_class_methods(self):
        path = os.path.join(self.root, "mayatk", "mayatk", "pkg", "mod.py")
        self.assertEqual(
            sorted(gate.extract_symbols(path, self.rel)), ["C.diverged", "C.shared"]
        )


class LedgerTest(unittest.TestCase):
    def test_every_entry_carries_a_reason(self):
        for spec in gate.LEDGER:
            with self.subTest(twin=spec.rel):
                self.assertTrue(
                    spec.reason and len(spec.reason.split()) >= 8,
                    "%s needs a real §6 justification" % spec.rel,
                )

    def test_an_empty_symbol_list_is_rejected(self):
        """``symbols=[]`` must raise, not become a whole-file comparison.

        The first draft coerced a falsy sequence to ``None``, which is the
        WHOLE-FILE mode -- so a typo silently produced the strictest possible
        check instead of an empty one, and the test guarding it
        (``assertNotEqual(spec.symbols, ())``) could never fail, because the
        constructor had already made ``()`` unreachable.
        """
        with self.assertRaises(ValueError):
            gate.TwinSpec(rel="x.py", reason="r " * 10, symbols=[])

    def test_symbols_none_still_means_whole_file(self):
        self.assertIsNone(gate.TwinSpec(rel="x.py", reason="r " * 10).symbols)

    def test_the_declared_twins_are_currently_in_sync(self):
        """The gate must pass on the tree that ships."""
        if not os.path.isdir(os.path.join(gate.REPO, "blendertk", "blendertk")):
            self.skipTest("DCC siblings not checked out")
        for spec in gate.LEDGER:
            with self.subTest(twin=spec.rel):
                status, detail = gate.compare(spec)
                self.assertIn(status, ("ok", "absent"), "\n".join(detail[:10]))


class ZeroComparedTest(unittest.TestCase):
    def test_comparing_nothing_fails(self):
        """A run that checked nothing is not a pass -- same rule as test counts."""
        saved_repo, saved_ledger = gate.REPO, gate.LEDGER
        tmp = tempfile.mkdtemp(prefix="twins_empty_")
        try:
            gate.REPO = tmp
            gate.LEDGER = [gate.TwinSpec(rel="pkg/mod.py", reason="x " * 10)]
            self.assertEqual(gate.main([]), 1)
        finally:
            gate.REPO, gate.LEDGER = saved_repo, saved_ledger
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
