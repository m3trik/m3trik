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

    def test_a_twin_file_gone_from_a_checked_out_sibling_is_missing(self):
        """A renamed or deleted twin FILE is not an unchecked-out sibling.

        It read ``absent`` -- "sibling not checked out", a skip that passes --
        so moving one side's file silently retired its guard.
        """
        os.remove(os.path.join(self.root, "blendertk", "blendertk", "pkg", "mod.py"))
        status, detail = gate.compare(self.spec())
        self.assertEqual(status, "missing")
        self.assertIn("blendertk", detail[0])


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
            sorted(gate.extract_symbols(path, self.rel)),
            ["C", "C.diverged", "C.shared"],
        )

    def test_a_whole_class_is_a_symbol_including_its_fields(self):
        """A small shared type (a dataclass) is guarded whole: a field added on
        one side is drift, though no method changed."""
        body = "@dataclass\nclass R:\n    maps: dict = None\n"
        for pkg in ("mayatk", "blendertk"):
            path = os.path.join(self.root, pkg, pkg, "pkg", "mod.py")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n\n" + body)
        self.assertEqual(gate.compare(self.spec(symbols=["R"]))[0], "ok")
        path = os.path.join(self.root, "blendertk", "blendertk", "pkg", "mod.py")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("    rects: dict = None\n")
        self.assertEqual(gate.compare(self.spec(symbols=["R"]))[0], "drift")


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


class WrittenOnceTest(unittest.TestCase):
    """Guardrail 3: on the new layout (the shared tools' ``slots/tools/``) a body
    of 8+ lines exists once, unless the copies call different hosts (the mirror)."""

    #: Nine statements: long enough to count, after the docstring is dropped.
    LOGIC = (
        '    """Plan the copies."""\n'
        + "".join(f"    step{i} = {i} * count\n" for i in range(8))
        + "    return step7\n"
    )
    #: The same shape over each host's toolkit: identical once mtk/btk fold.
    ADAPTER = "".join(f"    {{tk}}.step{i}(objects)\n" for i in range(9))

    def tree(self, files):
        root = tempfile.mkdtemp(prefix="written_once_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, text in files.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def test_an_empty_layout_reads_no_library(self):
        root = self.tree({"mayatk/mayatk/a.py": "def plan(count):\n" + self.LOGIC})
        self.assertEqual(gate.written_once_violations(root), [])

    def test_logic_in_two_layout_modules_is_a_copy(self):
        root = self.tree({
            "tentacle/tentacle/slots/tools/spin_maya.py": "def plan(count):\n" + self.LOGIC,
            "tentacle/tentacle/slots/tools/spin_blender.py": "def plan(count):\n" + self.LOGIC,
        })
        found = gate.written_once_violations(root)
        self.assertEqual(len(found), 1)
        self.assertIn("slots/tools/spin_blender.py:1 plan", found[0])
        self.assertIn("slots/tools/spin_maya.py:1 plan", found[0])

    def test_only_files_a_release_commits_are_compared(self):
        """A gitignored copy (a generated ``*_ui.py``) is not compared, here or
        in CI, whose checkout never has it; the same copy committed is."""
        import subprocess

        root = self.tree({
            "tentacle/.gitignore": "*_ui.py\n",
            "tentacle/tentacle/slots/tools/spin_maya.py": "def plan(count):\n" + self.LOGIC,
            "tentacle/tentacle/slots/tools/spin_ui.py": "def plan(count):\n" + self.LOGIC,
        })
        subprocess.run(["git", "init", "-q", os.path.join(root, "tentacle")], check=True)
        self.assertEqual(gate.written_once_violations(root), [])
        os.remove(os.path.join(root, "tentacle", ".gitignore"))
        self.assertEqual(len(gate.written_once_violations(root)), 1)

    def test_a_run_judges_only_copies_its_packages_write(self):
        """A copy between tentacle's layout and mayatk stops a release of
        either, never one of blendertk, which wrote no part of it."""
        root = self.tree({
            "tentacle/tentacle/slots/tools/spin.py": "def plan(count):\n" + self.LOGIC,
            "mayatk/mayatk/a.py": "def plan(count):\n" + self.LOGIC,
        })
        self.assertEqual(gate.written_once_violations(root, ["blendertk"]), [])
        self.assertEqual(len(gate.written_once_violations(root, ["mayatk"])), 1)
        self.assertEqual(len(gate.written_once_violations(root, ["tentacle"])), 1)

    def test_a_layout_copy_of_library_code_is_a_copy(self):
        root = self.tree({
            "tentacle/tentacle/slots/tools/radial.py": "def lay_out(count):\n" + self.LOGIC,
            "pythontk/pythontk/math_utils/m.py": "def spread(count):\n" + self.LOGIC,
        })
        found = gate.written_once_violations(root)
        self.assertEqual(len(found), 1)
        self.assertIn("pythontk/pythontk/math_utils/m.py:1 spread", found[0])

    def test_copies_over_the_two_hosts_are_the_mirror_not_a_copy(self):
        root = self.tree({
            "tentacle/tentacle/slots/tools/spin_maya.py": (
                "import mayatk as mtk\ndef run(objects):\n" + self.ADAPTER.format(tk="mtk")
            ),
            "tentacle/tentacle/slots/tools/spin_blender.py": (
                "import blendertk as btk\ndef run(objects):\n" + self.ADAPTER.format(tk="btk")
            ),
        })
        self.assertEqual(gate.written_once_violations(root), [])

    def test_two_copies_over_one_host_are_a_copy(self):
        root = self.tree({
            "tentacle/tentacle/slots/tools/spin_maya.py": (
                "def run(objects):\n" + self.ADAPTER.format(tk="mtk")
            ),
            "mayatk/mayatk/edit_utils/spin.py": (
                "def spin(objects):\n" + self.ADAPTER.format(tk="mtk")
            ),
        })
        self.assertEqual(len(gate.written_once_violations(root)), 1)

    def test_legacy_slots_and_short_bodies_are_out_of_scope(self):
        short = "def f(count):\n    a = count\n    return a\n"
        root = self.tree({
            "tentacle/tentacle/slots/_mixin.py": "def plan(count):\n" + self.LOGIC,
            "tentacle/tentacle/slots/maya/edit.py": "def plan(count):\n" + self.LOGIC,
            "tentacle/tentacle/slots/normals.py": short,
            "tentacle/tentacle/ui/panels/spin/slots.py": short,
        })
        self.assertEqual(gate.written_once_violations(root), [])


class HostBindingsTest(unittest.TestCase):
    """A library's binding of a shared pythontk class is configuration and
    additions: it overrides nothing the shared class defines."""

    SHARED = (
        "class Shared:\n"
        "    HOST = None\n"
        "    def build(self):\n        return 1\n"
        "    def _close(self, paths):\n        return paths\n"
        "    _clean = staticmethod(lambda paths: set(paths))\n"
    )

    def tree(self, binding, shared=None):
        root = tempfile.mkdtemp(prefix="host_bindings_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        files = {
            "pythontk/pythontk/core/shared.py": self.SHARED if shared is None else shared,
            "mayatk/mayatk/host.py": binding,
            "blendertk/blendertk/host.py": "class Bound(Shared):\n    HOST = 2\n",
        }
        for rel, text in files.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def run_on(self, root):
        saved = gate.HOST_BINDINGS
        gate.HOST_BINDINGS = (
            (
                "core/shared.py",
                "Shared",
                (("mayatk", "host.py", "Bound"), ("blendertk", "host.py", "Bound")),
            ),
        )
        try:
            return gate.host_binding_overrides(root)
        finally:
            gate.HOST_BINDINGS = saved

    def test_configuration_and_additions_pass(self):
        binding = (
            "class Bound(Shared):\n    HOST = 1\n"
            "    def perform_export(self):\n        return 2\n"
        )
        self.assertEqual(self.run_on(self.tree(binding)), ([], 2, []))

    def test_an_override_of_the_shared_class_fails(self):
        binding = "class Bound(Shared):\n    def _close(self, paths):\n        return set()\n"
        overrides, checked, _ = self.run_on(self.tree(binding))
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 1)
        self.assertIn("mayatk/host.py::Bound._close", overrides[0])

    def test_an_override_by_assignment_fails(self):
        """``_close = classmethod(lambda ...)`` is an override as much as a def."""
        binding = (
            "class Bound(Shared):\n"
            "    _close = classmethod(lambda cls, paths: set())\n"
            "    build: object = staticmethod(lambda: 2)\n"
        )
        overrides, checked, _ = self.run_on(self.tree(binding))
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 2, overrides)
        self.assertIn("Bound._close", overrides[0] + overrides[1])
        self.assertIn("Bound.build", overrides[0] + overrides[1])

    def test_a_method_the_shared_class_assigns_cannot_be_overridden(self):
        binding = "class Bound(Shared):\n    def _clean(paths):\n        return paths\n"
        overrides, _, _ = self.run_on(self.tree(binding))
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("Bound._clean", overrides[0])

    def test_a_vanished_binding_class_is_not_a_silent_pass(self):
        overrides, _, _ = self.run_on(self.tree("class Other:\n    pass\n"))
        self.assertEqual(len(overrides), 1)
        self.assertIn("not found", overrides[0])

    def test_a_vanished_shared_class_is_a_failure_not_a_skip(self):
        """pythontk is checked out but the shared class moved or was renamed:
        the bindings can no longer be held to the rule."""
        root = self.tree("class Bound(Shared):\n    HOST = 1\n", shared="class Renamed:\n    pass\n")
        overrides, checked, absent = self.run_on(root)
        self.assertEqual(absent, [])
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 2, overrides)
        self.assertTrue(all("shared class" in o for o in overrides), overrides)

    def test_only_a_missing_checkout_is_absent(self):
        root = self.tree("class Bound(Shared):\n    HOST = 1\n")
        shutil.rmtree(os.path.join(root, "blendertk"))
        overrides, checked, absent = self.run_on(root)
        self.assertEqual((overrides, checked), ([], 1))
        self.assertEqual(absent, ["blendertk/host.py::Bound"])

    def test_the_declared_bindings_hold_today(self):
        overrides, checked, absent = gate.host_binding_overrides()
        self.assertEqual(overrides, [])
        self.assertEqual(absent, [], "every repo is checked out in the monorepo")
        self.assertEqual(
            checked, sum(len(bindings) for _, _, bindings in gate.HOST_BINDINGS)
        )


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
