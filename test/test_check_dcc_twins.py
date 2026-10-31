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

import json
import os
import sys
import shutil
import tempfile
import textwrap
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


    PROPERTY = (
        "class P:\n"
        "    @property\n    def v(self):\n        return {get}\n"
        "    @v.setter\n    def v(self, value):\n        self._v = value\n"
    )

    def test_each_property_half_is_a_symbol_of_its_own(self):
        """A getter and its setter share a name; keyed apart, neither stands in
        for the other (the last def used to take the name)."""
        self.write("mayatk", self.PROPERTY.format(get=1))
        path = os.path.join(self.root, "mayatk", "mayatk", "pkg", "mod.py")
        symbols = gate.extract_symbols(path, self.rel)
        self.assertEqual(sorted(symbols), ["P", "P.v", "P.v.setter"])
        self.assertIn("return 1", "\n".join(symbols["P.v"]))

    def test_a_ledgered_property_compares_both_halves(self):
        self.write("mayatk", self.PROPERTY.format(get=1))
        self.write("blendertk", self.PROPERTY.format(get=2))
        self.assertEqual(gate.compare(self.spec(symbols=["P.v"]))[0], "drift", "the getter drifted")
        drifted_setter = self.PROPERTY.format(get=1).replace("self._v = value", "self._v = -value")
        self.write("blendertk", drifted_setter)
        self.assertEqual(gate.compare(self.spec(symbols=["P.v"]))[0], "drift", "the setter drifted")
        self.write("blendertk", self.PROPERTY.format(get=1))
        self.assertEqual(gate.compare(self.spec(symbols=["P.v"]))[0], "ok")
        self.write("blendertk", self.PROPERTY.format(get=1).split("    @v.setter")[0])
        self.assertEqual(gate.compare(self.spec(symbols=["P.v"]))[0], "missing", "a half gone from one side")


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


class HostCopiesTest(unittest.TestCase):
    """CODE_STANDARD section 14: host-free logic both DCC packages carry is
    written once, in pythontk. A body of 8+ lines mayatk and blendertk both
    write over no host is a copy unless the ledger guards it as a twin; the
    copies older than the rule sit in a baseline that only shrinks."""

    LOGIC = WrittenOnceTest.LOGIC
    #: Other bodies of the same length: equal text pairs across fixtures too.
    OTHER = LOGIC.replace("* count", "+ count")
    INNER = LOGIC.replace("* count", "- count")
    ADAPTER = WrittenOnceTest.ADAPTER
    PLANNER = "class Planner:\n    def plan(self, count):\n" + textwrap.indent(LOGIC, "    ")
    KEY = "mayatk/core/plan.py::Planner.plan = blendertk/core/plan.py::Planner.plan"

    def setUp(self):
        # Fixtures judge an empty ledger; the live-tree case puts it back.
        self._live = gate.LEDGER, gate.GUARDED_ELSEWHERE
        gate.LEDGER, gate.GUARDED_ELSEWHERE = [], {}
        self.addCleanup(self._restore)

    def _restore(self):
        gate.LEDGER, gate.GUARDED_ELSEWHERE = self._live

    def tree(self, files, frozen=None):
        root = tempfile.mkdtemp(prefix="host_copies_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, text in files.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        if frozen is not None:
            self.freeze(root, frozen)
        return root

    @staticmethod
    def freeze(root, copies):
        path = os.path.join(root, "m3trik", "scripts", "check_dcc_twins_baseline.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"_doc": "fixture", "copies": copies}, fh)
        return path

    @staticmethod
    def both(rel, text, b_rel=None):
        return {f"mayatk/mayatk/{rel}": text, f"blendertk/blendertk/{b_rel or rel}": text}

    def test_a_host_free_body_both_packages_write_is_a_copy(self):
        """Keyed by the qualified name in each package, never by line number."""
        new, frozen, paid = gate.host_copy_findings(self.tree(self.both("core/plan.py", self.PLANNER)))
        self.assertEqual((new, frozen, paid), ([self.KEY], [], []))

    def test_a_copy_at_two_different_paths_is_still_a_copy(self):
        files = self.both("env/manager/_manager.py", "def is_current(count):\n" + self.LOGIC, "env/manager.py")
        new, _, _ = gate.host_copy_findings(self.tree(files))
        self.assertEqual(
            new, ["mayatk/env/manager/_manager.py::is_current = blendertk/env/manager.py::is_current"]
        )

    def test_the_two_halves_of_a_mirror_are_not_a_copy(self):
        """Each half calls its own host: identical once mtk/btk fold, the mirror."""
        root = self.tree({
            "mayatk/mayatk/core/run.py": "import mayatk as mtk\ndef run(objects):\n" + self.ADAPTER.format(tk="mtk"),
            "blendertk/blendertk/core/run.py": "import blendertk as btk\ndef run(objects):\n" + self.ADAPTER.format(tk="btk"),
        })
        self.assertEqual(gate.host_copy_findings(root), ([], [], []))

    def test_a_ledgered_twin_is_guarded_not_a_copy(self):
        """A ledger symbol covers what it encloses: a class its methods, a
        method its inner functions."""
        nested = (
            "class Utils:\n    def selected(self, count):\n"
            "        def wrapped(count):\n" + textwrap.indent(self.INNER, "        ")
            + "        return wrapped\n"
        )
        root = self.tree({**self.both("core/plan.py", self.PLANNER), **self.both("core/utils.py", nested)})
        self.assertEqual(
            gate.host_copy_findings(root)[0],
            [
                self.KEY,
                "mayatk/core/utils.py::Utils.selected = blendertk/core/utils.py::Utils.selected",
                "mayatk/core/utils.py::Utils.selected.wrapped = blendertk/core/utils.py::Utils.selected.wrapped",
            ],
        )
        gate.LEDGER = [
            gate.TwinSpec(rel="core/plan.py", reason="fixture " * 8, symbols=("Planner",)),
            gate.TwinSpec(rel="core/utils.py", reason="fixture " * 8, symbols=("Utils.selected",)),
        ]
        self.assertEqual(gate.host_copy_findings(root), ([], [], []))

    def test_a_ledger_entry_for_another_symbol_guards_nothing(self):
        root = self.tree(self.both("core/plan.py", self.PLANNER))
        gate.LEDGER = [gate.TwinSpec(rel="core/plan.py", reason="fixture " * 8, symbols=("Planner.plan_sizes",))]
        self.assertEqual(gate.host_copy_findings(root)[0], [self.KEY])

    def test_a_whole_file_twin_is_guarded(self):
        root = self.tree(self.both("core/plan.py", self.PLANNER))
        gate.LEDGER = [gate.TwinSpec(rel="core/plan.py", reason="fixture " * 8)]
        self.assertEqual(gate.host_copy_findings(root), ([], [], []))

    def test_a_file_another_guard_holds_is_left_to_it(self):
        root = self.tree(self.both("env/doctor.py", "def scan(count):\n" + self.LOGIC))
        gate.GUARDED_ELSEWHERE = {"env/doctor.py": "sync_shared_bat.py"}
        self.assertEqual(gate.host_copy_findings(root), ([], [], []))

    def test_a_frozen_copy_passes_and_a_moved_one_is_paid(self):
        root = self.tree(self.both("core/plan.py", self.PLANNER), frozen=[self.KEY])
        self.assertEqual(gate.host_copy_findings(root), ([], [self.KEY], []))
        os.remove(os.path.join(root, "blendertk", "blendertk", "core", "plan.py"))
        self.assertEqual(gate.host_copy_findings(root), ([], [], [self.KEY]))

    def test_a_new_copy_beside_frozen_ones_fails(self):
        files = {**self.both("core/plan.py", self.PLANNER), **self.both("core/spin.py", "def spin(count):\n" + self.OTHER)}
        new, frozen, _ = gate.host_copy_findings(self.tree(files, frozen=[self.KEY]))
        self.assertEqual(new, ["mayatk/core/spin.py::spin = blendertk/core/spin.py::spin"])
        self.assertEqual(frozen, [self.KEY])

    def test_a_third_copy_of_a_frozen_body_fails(self):
        """The unit is a pair: one more place makes a pair the baseline lacks."""
        files = {**self.both("core/plan.py", self.PLANNER), "blendertk/blendertk/core/again.py": self.PLANNER}
        new, frozen, _ = gate.host_copy_findings(self.tree(files, frozen=[self.KEY]))
        self.assertEqual(new, ["mayatk/core/plan.py::Planner.plan = blendertk/core/again.py::Planner.plan"])
        self.assertEqual(frozen, [self.KEY])

    def test_short_bodies_and_exec_templates_are_out_of_scope(self):
        short = "def f(count):\n    a = count\n    return a\n"
        files = {**self.both("core/short.py", short), **self.both("bridge/templates/run.py", "def run(count):\n" + self.LOGIC)}
        self.assertEqual(gate.host_copy_findings(self.tree(files)), ([], [], []))

    def test_a_run_for_other_packages_judges_no_host_copy(self):
        """tentacle's release never stops on the two libraries' copies."""
        root = self.tree(self.both("core/plan.py", self.PLANNER))
        self.assertEqual(gate.host_copy_findings(root, ["tentacle"]), ([], [], []))
        self.assertEqual(gate.host_copy_findings(root, ["blendertk"])[0], [self.KEY])

    def test_a_missing_sibling_reads_nothing_and_pays_nothing(self):
        root = self.tree({"mayatk/mayatk/core/plan.py": self.PLANNER}, frozen=[self.KEY])
        self.assertEqual(gate.host_copy_findings(root), ([], [], []))

    def test_check_fails_on_a_new_copy_only(self):
        root = self.tree(self.both("core/plan.py", self.PLANNER))
        args = ["--check", "--written-once", "--workspace", root]
        self.assertEqual(gate.main(args), 1)
        self.freeze(root, [self.KEY])
        self.assertEqual(gate.main(args), 0)

    def test_update_drops_paid_copies_and_never_freezes_a_new_one(self):
        gone = "mayatk/core/old.py::old = blendertk/core/old.py::old"
        root = self.tree(self.both("core/plan.py", self.PLANNER), frozen=[gone])
        self.assertEqual(gate.main(["--written-once", "--update", "--workspace", root]), 1)
        path = os.path.join(root, "m3trik", "scripts", "check_dcc_twins_baseline.json")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["copies"], [])

    GETTER = "class C:\n    @property\n    def v(self, count=1):\n" + textwrap.indent(LOGIC, "    ")
    SETTER = "    @v.setter\n    def v(self, count):\n" + textwrap.indent(OTHER, "    ")
    V_KEY = "mayatk/core/p.py::C.v = blendertk/core/p.py::C.v"

    def test_a_setter_copy_beside_a_frozen_getter_is_a_new_copy(self):
        """A getter and its setter shared one name, so the setter's copy hid
        behind the getter's frozen pair."""
        root = self.tree(self.both("core/p.py", self.GETTER + self.SETTER), frozen=[self.V_KEY])
        self.assertEqual(
            gate.host_copy_findings(root),
            (["mayatk/core/p.py::C.v.setter = blendertk/core/p.py::C.v.setter"], [self.V_KEY], []),
        )

    def test_a_def_repeated_in_branches_is_one_place_each(self):
        text = (
            "if FLAG:\n    def f(count):\n" + textwrap.indent(self.LOGIC, "    ")
            + "else:\n    def f(count):\n" + textwrap.indent(self.OTHER, "    ")
        )
        new, _, _ = gate.host_copy_findings(self.tree(self.both("core/r.py", text)))
        self.assertEqual(
            new,
            [
                "mayatk/core/r.py::f = blendertk/core/r.py::f",
                "mayatk/core/r.py::f#2 = blendertk/core/r.py::f#2",
            ],
        )

    def test_a_copy_between_two_guarded_files_is_still_a_copy(self):
        """Each guard holds its own twin, never a copy of one in another file."""
        body = "def visible(count):\n" + self.LOGIC
        root = self.tree({
            "mayatk/mayatk/a/params.py": body,
            "blendertk/blendertk/a/params.py": "y = 2\n",
            "mayatk/mayatk/b/other.py": "x = 1\n",
            "blendertk/blendertk/b/other.py": body,
        })
        gate.LEDGER = [gate.TwinSpec(rel="a/params.py", reason="fixture " * 8)]
        gate.GUARDED_ELSEWHERE = {"b/other.py": "some_guard.py"}
        self.assertEqual(
            gate.host_copy_findings(root)[0],
            ["mayatk/a/params.py::visible = blendertk/b/other.py::visible"],
        )

    def test_a_ledger_symbol_exempts_its_own_twin_only(self):
        """Two ledgered symbols of one file are two twins; one host's ``a``
        written as the other's ``b`` is a copy."""
        mine = "class C:\n    def a(self, count):\n" + textwrap.indent(self.LOGIC, "    ")
        theirs = (
            "class C:\n    def a(self, count):\n" + textwrap.indent(self.OTHER, "    ")
            + "    def b(self, count):\n" + textwrap.indent(self.LOGIC, "    ")
        )
        root = self.tree({"mayatk/mayatk/core/c.py": mine, "blendertk/blendertk/core/c.py": theirs})
        gate.LEDGER = [gate.TwinSpec(rel="core/c.py", reason="fixture " * 8, symbols=("C.a", "C.b"))]
        self.assertEqual(
            gate.host_copy_findings(root)[0],
            ["mayatk/core/c.py::C.a = blendertk/core/c.py::C.b"],
        )

    def test_a_file_a_guard_names_but_never_compares_is_held_by_none(self):
        """Read from the guards: vendor-sync names the Rizom registry as a
        host half it never compares, and compares the Unity one."""
        if not os.path.isdir(os.path.join(gate.REPO, "extapps", "test")):
            self.skipTest("extapps not checked out")
        compared = gate.compared_elsewhere(gate.REPO)
        held = compared[gate._VENDOR_SYNC]
        self.assertIn("env_utils/unity_bridge/parameters.py", held)
        self.assertIn("mat_utils/marmoset_bridge/marmoset_rpc/", held)
        self.assertNotIn("uv_utils/rizom_bridge/parameters.py", held)
        self.assertIn("env_utils/pm_doctor.py", compared["m3trik/scripts/sync_shared_bat.py"])

    def test_every_file_left_to_another_guard_is_one_it_compares(self):
        """An exemption names a file both packages have, and its guard compares
        it -- read from the guard, not grepped: a name a guard only lists is
        not one it holds."""
        if not os.path.isdir(os.path.join(gate.REPO, "blendertk", "blendertk")):
            self.skipTest("DCC siblings not checked out")
        compared = gate.compared_elsewhere(gate.REPO)
        for rel, guard in self._live[1].items():
            with self.subTest(rel=rel):
                parts = rel.rstrip("/").split("/")
                for package in gate.HOST_PACKAGES:
                    self.assertTrue(os.path.exists(os.path.join(gate.REPO, package, package, *parts)))
                self.assertIn(rel, compared.get(guard, set()), f"{guard} does not compare it")

    def test_the_tree_holds_no_unfrozen_host_copy(self):
        """The gate must pass on the tree that ships."""
        if not os.path.isdir(os.path.join(gate.REPO, "blendertk", "blendertk")):
            self.skipTest("DCC siblings not checked out")
        gate.LEDGER, gate.GUARDED_ELSEWHERE = self._live
        new, _, _ = gate.host_copy_findings(gate.REPO)
        self.assertEqual(new, [], "\n".join(new))


class _BindingTreeCase(unittest.TestCase):
    """A workspace of a pythontk root, its shared class and two libraries."""

    SHARED = (
        "class Shared:\n"
        "    HOST = None\n"
        "    def build(self):\n        return 1\n"
        "    def _close(self, paths):\n        return paths\n"
        "    _clean = staticmethod(lambda paths: set(paths))\n"
    )
    #: The root the bindings reach the shared class through (``ptk.Shared``).
    ROOT = 'DEFAULT_INCLUDE = {"core.shared": ["Shared"]}\n'
    #: Each binding module's head: the pythontk root, as the libraries import it.
    HEAD = "import pythontk as ptk\n\n\n"
    #: The pair the fixture declares (:data:`HOST_BINDINGS`).
    ROWS = (
        (
            "core/shared.py",
            "Shared",
            (("mayatk", "host.py", "Bound"), ("blendertk", "host.py", "Bound")),
        ),
    )

    def tree(self, binding, shared=None, files=None):
        root = tempfile.mkdtemp(prefix="host_bindings_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        written = {
            "pythontk/pythontk/__init__.py": self.ROOT,
            "pythontk/pythontk/core/shared.py": self.SHARED if shared is None else shared,
            "mayatk/mayatk/host.py": self.HEAD + binding,
            "blendertk/blendertk/host.py": self.HEAD + "class Bound(ptk.Shared):\n    HOST = 2\n",
        }
        written.update(files or {})
        for rel, text in written.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def run_on(self, root, rows=None, shadowed=None):
        saved = gate.HOST_BINDINGS
        gate.HOST_BINDINGS = self.ROWS if rows is None else rows
        try:
            if shadowed is None:
                return gate.host_binding_overrides(root)
            return gate.host_binding_overrides(root, shadowed=shadowed)
        finally:
            gate.HOST_BINDINGS = saved


class HostBindingsTest(_BindingTreeCase):
    """A library's binding of a shared pythontk class is configuration and
    additions: it overrides nothing the shared class defines."""

    def test_configuration_and_additions_pass(self):
        binding = (
            "class Bound(ptk.Shared):\n    HOST = 1\n"
            "    def perform_export(self):\n        return 2\n"
        )
        self.assertEqual(self.run_on(self.tree(binding)), ([], 2, []))

    def test_an_override_of_the_shared_class_fails(self):
        binding = "class Bound(ptk.Shared):\n    def _close(self, paths):\n        return set()\n"
        overrides, checked, _ = self.run_on(self.tree(binding))
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 1)
        self.assertIn("mayatk/host.py::Bound._close", overrides[0])

    def test_an_override_by_assignment_fails(self):
        """``_close = classmethod(lambda ...)`` is an override as much as a def."""
        binding = (
            "class Bound(ptk.Shared):\n"
            "    _close = classmethod(lambda cls, paths: set())\n"
            "    build: object = staticmethod(lambda: 2)\n"
        )
        overrides, checked, _ = self.run_on(self.tree(binding))
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 2, overrides)
        self.assertIn("Bound._close", overrides[0] + overrides[1])
        self.assertIn("Bound.build", overrides[0] + overrides[1])

    def test_a_method_the_shared_class_assigns_cannot_be_overridden(self):
        binding = "class Bound(ptk.Shared):\n    def _clean(paths):\n        return paths\n"
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
        root = self.tree(
            "class Bound(ptk.Shared):\n    HOST = 1\n", shared="class Renamed:\n    pass\n"
        )
        overrides, checked, absent = self.run_on(root)
        self.assertEqual(absent, [])
        self.assertEqual(checked, 2)
        self.assertEqual(len(overrides), 2, overrides)
        self.assertTrue(all("shared class" in o for o in overrides), overrides)

    def test_only_a_missing_checkout_is_absent(self):
        root = self.tree("class Bound(ptk.Shared):\n    HOST = 1\n")
        shutil.rmtree(os.path.join(root, "blendertk"))
        overrides, checked, absent = self.run_on(root)
        self.assertEqual((overrides, checked), ([], 1))
        self.assertEqual(absent, ["blendertk/host.py::Bound"])

    def test_the_declared_bindings_hold_today(self):
        overrides, checked, absent = gate.host_binding_overrides()
        self.assertEqual(overrides, [], "\n".join(overrides))
        self.assertEqual(absent, [], "every repo is checked out in the monorepo")
        declared = {
            f"{package}/{rel}::{name}"
            for _, _, rows in gate.HOST_BINDINGS
            for package, rel, name in rows
        }
        self.assertGreaterEqual(checked, len(declared))


class DerivedBindingsTest(_BindingTreeCase):
    """The roster is derived, never hand-listed (CODE_STANDARD section 6):
    every mayatk / blendertk class with a pythontk class for a base is a
    binding, declared in :data:`HOST_BINDINGS` or not, unless its base is a
    reasoned exemption."""

    ROOT = (
        'DEFAULT_INCLUDE = {"core.shared": ["Shared"], "core.kit": '
        '["HandoffBridge", "PureThingHost", "TraceMixin"], "core.gone": ["Gone"]}\n'
    )

    def library(self, text, files=None):
        """A tree whose mayatk also holds *text* in ``tool.py`` (and *files*)."""
        files = dict(files or {})
        files["mayatk/mayatk/tool.py"] = self.HEAD + text
        return self.tree("class Bound(ptk.Shared):\n    HOST = 1\n", files=files)

    def test_an_unlisted_binding_that_overrides_fails(self):
        root = self.library(
            "class Tool(ptk.Shared):\n    def build(self):\n        return 2\n"
        )
        overrides, checked, _ = self.run_on(root)
        self.assertEqual(checked, 3)  # the two declared, and the one nobody listed
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("mayatk/tool.py::Tool.build", overrides[0])
        self.assertIn("overrides pythontk Shared.build", overrides[0])

    def test_an_unlisted_binding_that_only_adds_passes(self):
        root = self.library(
            "class Tool(ptk.Shared):\n    HOST = 3\n    def stash(self):\n        return 2\n"
        )
        self.assertEqual(self.run_on(root, rows=()), ([], 3, []))

    def test_a_base_imported_from_a_pythontk_module_is_a_binding_too(self):
        root = self.library(
            "from pythontk.core.shared import Shared as Base\n\n\n"
            "class Tool(Base):\n    def _close(self, paths):\n        return paths\n"
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("Tool._close", overrides[0])

    def test_a_method_the_shared_class_inherits_cannot_be_overridden(self):
        """The rule covers the shared class's whole pythontk lineage: its
        ``_<Class>Internal`` base and a base it imports from another module."""
        root = self.library(
            "class Tool(ptk.Shared):\n"
            "    def _helper(self):\n        return 1\n"
            "    def encode(self):\n        return 2\n",
            files={
                "pythontk/pythontk/core/shared.py": (
                    "from .grand import Grand\n\n\n"
                    "class _SharedInternal:\n    def _helper(self):\n        return 0\n\n\n"
                    "class Shared(_SharedInternal, Grand):\n    HOST = None\n"
                ),
                "pythontk/pythontk/core/grand.py": (
                    "class Grand:\n    def encode(self):\n        return 0\n"
                ),
            },
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 2, overrides)
        self.assertIn("Tool._helper", overrides[0] + overrides[1])
        self.assertIn("Tool.encode", overrides[0] + overrides[1])

    def test_a_lazily_exported_shared_class_resolves(self):
        root = self.library(
            "from pythontk.core.lazy import Lazy\n\n\n"
            "class Tool(Lazy):\n    def build(self):\n        return 2\n",
            files={
                "pythontk/pythontk/core/lazy/__init__.py": (
                    "lazy_exports(globals(), {'_lazy': 'Lazy'})\n"
                ),
                "pythontk/pythontk/core/lazy/_lazy.py": (
                    "class Lazy:\n    def build(self):\n        return 1\n"
                ),
            },
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("Tool.build", overrides[0])

    def test_a_subclass_of_a_binding_is_a_binding_too(self):
        """(A) The rule follows the inheritance: a library class over a
        binding reaches the shared class just the same."""
        root = self.library(
            "class Tool(ptk.Shared):\n    HOST = 3\n\n\n"
            "class Sub(Tool):\n    def build(self):\n        return 2\n"
        )
        overrides, checked, _ = self.run_on(root, rows=())
        self.assertEqual(checked, 4)  # Bound twice, Tool, Sub
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("mayatk/tool.py::Sub.build", overrides[0])

    def test_an_imported_library_mixin_ahead_of_the_shared_class_overrides(self):
        """(B) A mixin from another module of the library, ahead of the shared
        class in the MRO, wins: its ``build`` replaces pythontk's."""
        root = self.library(
            "from mayatk.mixins import _Builds\n\n\n"
            "class Tool(_Builds, ptk.Shared):\n    HOST = 3\n",
            files={
                "mayatk/mayatk/mixins.py": (
                    "class _Builds:\n    def build(self):\n        return 2\n"
                ),
            },
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("mayatk/tool.py::Tool.build", overrides[0])
        self.assertIn("mayatk/mixins.py::_Builds", overrides[0])

    def test_a_mixin_behind_the_shared_class_is_shadowed_not_an_override(self):
        """(C) pythontk's ``build`` wins the MRO over a mixin listed after it:
        the mixin's copy is dead code, reported as shadowed, not an override."""
        root = self.library(
            "class _ToolInternal:\n    def build(self):\n        return 2\n\n\n"
            "class Tool(ptk.Shared, _ToolInternal):\n    HOST = 3\n"
        )
        shadowed = []
        overrides, _, _ = self.run_on(root, rows=(), shadowed=shadowed)
        self.assertEqual(overrides, [])
        self.assertEqual(len(shadowed), 1, shadowed)
        self.assertIn("mayatk/tool.py::Tool.build", shadowed[0])
        self.assertIn("shadowed by pythontk Shared.build", shadowed[0])

    def test_a_member_bound_under_a_branch_still_counts(self):
        """(D) A ``def`` or an assignment nested in the class body (``if``,
        ``try``) binds the class member as much as a top-level one."""
        root = self.library(
            "class Tool(ptk.Shared):\n"
            "    if True:\n"
            "        def build(self):\n            return 2\n"
            "    try:\n"
            "        _close = staticmethod(lambda paths: paths)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 2, overrides)
        self.assertIn("Tool.build", overrides[0] + overrides[1])
        self.assertIn("Tool._close", overrides[0] + overrides[1])

    #: A uitk root and shared class, as ``uitk.PreviewController`` is.
    UITK = {
        "uitk/uitk/__init__.py": 'DEFAULT_INCLUDE = {"managers.ctrl": ["Controller"]}\n',
        "uitk/uitk/managers/ctrl.py": (
            "class Controller:\n    SESSION_CLASS = None\n"
            "    def preview(self):\n        return 0\n"
        ),
    }

    def test_a_binding_of_a_uitk_shared_class_is_held_to_the_rule(self):
        """uitk's generic Qt classes are shared too (``mtk.Preview`` binds
        ``uitk.PreviewController``): configuring and adding pass, an override
        fails, through the root or a module import alike."""
        root = self.library(
            "import uitk\n\n\n"
            "class Preview(uitk.Controller):\n    SESSION_CLASS = 1\n"
            "    def apply_host(self):\n        return 1\n\n\n"
            "from uitk.managers.ctrl import Controller\n\n\n"
            "class Eager(Controller):\n    def preview(self):\n        return 2\n",
            files=dict(self.UITK),
        )
        overrides, checked, _ = self.run_on(root, rows=())
        self.assertEqual(checked, 4)  # Bound twice, Preview, Eager
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("mayatk/tool.py::Eager.preview", overrides[0])
        self.assertIn("overrides uitk Controller.preview", overrides[0])

    def test_a_declared_uitk_pair_names_its_package(self):
        """A ``HOST_BINDINGS`` row over a uitk class spells its module
        ``uitk:<path>``; a missing uitk checkout is absent, not a failure."""
        root = self.library(
            "import uitk\n\n\nclass Preview(uitk.Controller):\n    SESSION_CLASS = 1\n",
            files=dict(self.UITK),
        )
        rows = (("uitk:managers/ctrl.py", "Controller", (("mayatk", "tool.py", "Preview"),)),)
        self.assertEqual(self.run_on(root, rows=rows), ([], 3, []))
        shutil.rmtree(os.path.join(root, "uitk"))
        overrides, _, absent = self.run_on(root, rows=rows)
        self.assertEqual((overrides, absent), ([], ["mayatk/tool.py::Preview"]))

    def test_its_own_modules_mixin_cannot_override_either(self):
        root = self.library(
            "class _ToolInternal:\n    def build(self):\n        return 2\n\n\n"
            "class Tool(_ToolInternal, ptk.Shared):\n    HOST = 3\n"
        )
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("Tool.build", overrides[0])

    def test_kits_pure_host_adapters_and_mixins_are_exempt(self):
        """A kit's hooks are its extension points, an adapter on a seam's pure
        defaults overrides them by design, and a capability mixin's user is no
        host half of it: none is a binding."""
        root = self.library(
            "class Bridge(ptk.HandoffBridge):\n    def _produce(self):\n        return 1\n\n\n"
            "class MayaThingHost(ptk.PureThingHost):\n    def thing(self):\n        return 1\n\n\n"
            "class Traced(ptk.TraceMixin):\n    def trace(self):\n        return 1\n",
            files={
                "pythontk/pythontk/core/kit.py": (
                    "class HandoffBridge:\n    def _produce(self):\n        return 0\n\n\n"
                    "class PureThingHost:\n    def thing(self):\n        return 0\n\n\n"
                    "class TraceMixin:\n    def trace(self):\n        return 0\n"
                ),
            },
        )
        overrides, checked, _ = self.run_on(root, rows=())
        self.assertEqual((overrides, checked), ([], 2))
        _, _, exempt = gate.derived_bindings(root)
        self.assertEqual(len(exempt), 3, exempt)
        self.assertTrue(any("Bridge <- HandoffBridge  (kit:" in e for e in exempt), exempt)
        self.assertTrue(any("<- PureThingHost  (an adapter" in e for e in exempt), exempt)
        self.assertTrue(any("<- TraceMixin  (a capability mixin" in e for e in exempt), exempt)

    def test_a_base_naming_a_pythontk_class_the_source_lacks_fails(self):
        root = self.library("class Tool(ptk.Gone):\n    HOST = 3\n")
        overrides, _, _ = self.run_on(root, rows=())
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn(
            "mayatk/tool.py::Tool  (shared class pythontk core.gone::Gone", overrides[0]
        )

    def test_a_declared_pair_the_derivation_cannot_see_fails(self):
        """A declared binding whose base the derivation cannot resolve means the
        derived roster has a blind spot: say so, never pass it silently."""
        root = self.tree(
            "from somewhere import Shared\n\n\nclass Bound(Shared):\n    HOST = 1\n"
        )
        overrides, _, _ = self.run_on(root)
        self.assertEqual(len(overrides), 1, overrides)
        self.assertIn("mayatk/host.py::Bound  (declared, but no base", overrides[0])

    def test_every_exemption_says_what_kind_and_why(self):
        for base, reason in gate.BINDING_EXEMPT.items():
            kind, _, why = reason.partition(": ")
            self.assertIn(kind, ("kit", "unconverted"), base)
            self.assertGreater(len(why), 20, base)

    def test_the_libraries_bindings_are_derived_today(self):
        """The key stash and the emissive groups were bindings the hand roster
        never held to the rule; the derivation finds every declared pair too."""
        bindings, failures, _ = gate.derived_bindings()
        self.assertEqual(failures, [])
        for package in ("mayatk", "blendertk"):
            self.assertIn(f"{package}/anim_utils/key_stash/_key_stash.py::KeyStash", bindings)
            self.assertIn(
                f"{package}/mat_utils/emissive_groups.py::EmissiveGroups", bindings
            )
        for _, shared, rows in gate.HOST_BINDINGS:
            for package, rel, name in rows:
                label = f"{package}/{rel}::{name}"
                self.assertIn(label, bindings)
                self.assertIn(shared, bindings[label]["lineage"], label)
        # uitk's shared classes bind too: the preview controller.
        for package in ("mayatk", "blendertk"):
            self.assertIn(
                "PreviewController",
                bindings[f"{package}/core_utils/preview.py::Preview"]["lineage"],
            )
        # A declarative spec is a kit (``SchemaSpec`` invites from_dict / to_dict).
        self.assertNotIn("mayatk/edit_utils/rack_builder.py::RackSpec", bindings)


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
