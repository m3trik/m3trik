#!/usr/bin/python
# coding=utf-8
"""Tests for affected_tests.py -- the change -> test-module selector.

Fixture packages (in a throwaway workspace) prove each selection rule: a direct
import, a re-export through the package, a distinctive name, the naming
convention, a private helper reached through its importer, a deleted module,
downstream counting, and what selects nothing (generic names, docs). The real
workspace is held to one known mapping so a regression in the scanner shows up
against the code it exists for.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import affected_tests as at  # noqa: E402


def _clear_caches():
    for fn in (at.packages, at.test_files, at.source_files, at.name_spread, at._parse,
               at.gui_required, at.last_seconds):
        fn.cache_clear()
    at._INDEX.clear()


def _write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")


def _commit(repo: Path) -> None:
    """Make *repo* a git repo whose HEAD holds its current files."""
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(git + args, check=True, capture_output=True)


#: tentacle's structural suites, as fixture files (the gate selects them by stem).
_STRUCTURAL = {
    f"tentacle/test/{stem}.py": "def test_s():\n    pass\n"
    for stem in ("test_slot_method_coverage", "test_ui_integrity", "test_slot_integrity",
                 "test_dcc_invariants", "test_ui_footers")
}


class _Fixture(unittest.TestCase):
    """A two-package workspace: ``pythontk`` (core) and ``mayatk`` (depends on it)."""

    FILES = {
        "pythontk/pythontk/__init__.py": "",
        "pythontk/pythontk/core_utils/__init__.py": "from .badge import StatusBadge\n",
        "pythontk/pythontk/core_utils/badge.py": "class StatusBadge:\n    pass\n\ndef update():\n    pass\n",
        "pythontk/pythontk/core_utils/_helper.py": "def _h():\n    return 1\n",
        "pythontk/pythontk/core_utils/feature.py": (
            "from ._helper import _h\n\nclass FeatureThing:\n    def go(self):\n        return _h()\n"
        ),
        "pythontk/pythontk/core_utils/lonely.py": "class NobodyTestsMe:\n    pass\n",
        "pythontk/test/run_tests.py": "",
        "pythontk/test/test_run_tests.py": "def test_x():\n    pass\n",
        "pythontk/test/test_badge.py": (
            "from pythontk.core_utils.badge import StatusBadge\n\ndef test_a():\n    pass\n"
        ),
        "pythontk/test/test_reexport.py": (
            "from pythontk.core_utils import StatusBadge\n\ndef test_b():\n    pass\n"
        ),
        "pythontk/test/test_named.py": (
            "import pythontk as ptk\n\ndef test_c():\n    ptk.StatusBadge()\n"
        ),
        "pythontk/test/test_generic.py": (
            "def test_d():\n    d = {}\n    d.update({})\n"
        ),
        "pythontk/test/test_feature_user.py": (
            "import pythontk as ptk\n\ndef test_e():\n    ptk.FeatureThing().go()\n"
        ),
        "mayatk/pyproject.toml": '[project]\nname = "mayatk"\ndependencies = ["pythontk>=1"]\n',
        "mayatk/mayatk/__init__.py": "",
        "mayatk/test/test_uses_badge.py": (
            "import pythontk as ptk\n\ndef test_f():\n    ptk.StatusBadge()\n"
        ),
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name).resolve()
        _write(self.ws, self.FILES)
        _clear_caches()
        # Never read or write the user's persistent index from a test.
        patcher = mock.patch.object(at, "_index_path", lambda: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(_clear_caches)
        self.addCleanup(self._tmp.cleanup)

    def picks(self, *rels, downstream=False):
        sel = at.select([self.ws / r for r in rels], workspace=self.ws, downstream=downstream)
        return sel, {pkg: set(mods) for pkg, mods in sel.picks.items()}


class TestSelection(_Fixture):
    def test_a_module_selects_its_importers_reexporters_and_namers(self):
        sel, picks = self.picks("pythontk/pythontk/core_utils/badge.py")
        self.assertEqual(picks["pythontk"], {"test_badge", "test_reexport", "test_named"})

    def test_a_plain_lowercase_name_selects_nothing_by_mention_alone(self):
        sel, picks = self.picks("pythontk/pythontk/core_utils/badge.py")
        self.assertNotIn("test_generic", picks["pythontk"])  # d.update() is not badge.update

    def test_a_test_using_its_own_same_named_constant_is_not_selected(self):
        _write(self.ws, {
            "pythontk/pythontk/core_utils/limits.py": "MAX_SPAN_FRAMES = 9\n",
            "pythontk/test/test_own_constant.py": (
                "MAX_SPAN_FRAMES = 3\n\ndef test_h():\n    assert MAX_SPAN_FRAMES == 3\n"
            ),
        })
        _clear_caches()
        _, picks = self.picks("pythontk/pythontk/core_utils/limits.py")
        self.assertNotIn("test_own_constant", picks.get("pythontk", set()))

    def test_a_class_attribute_constant_of_the_same_name_is_not_ours_either(self):
        _write(self.ws, {
            "pythontk/pythontk/core_utils/limits.py": "MAX_SPAN_FRAMES = 9\n",
            "pythontk/test/test_class_constant.py": (
                "import unittest\n\nclass T(unittest.TestCase):\n    MAX_SPAN_FRAMES = 3\n\n"
                "    def test_i(self):\n        assert self.MAX_SPAN_FRAMES == 3\n"
            ),
        })
        _clear_caches()
        _, picks = self.picks("pythontk/pythontk/core_utils/limits.py")
        self.assertNotIn("test_class_constant", picks.get("pythontk", set()))

    def test_a_private_helper_is_followed_through_its_importer(self):
        sel, picks = self.picks("pythontk/pythontk/core_utils/_helper.py")
        self.assertEqual(picks["pythontk"], {"test_feature_user"})
        self.assertIn("via pythontk.core_utils.feature", next(iter(sel.picks["pythontk"]["test_feature_user"])))

    def test_a_module_with_few_importers_also_selects_their_tests(self):
        """A base dialog is exercised through its subclass, whose tests never
        name the base (uitk's ColorMappingDialog -> AttributeColorDialog)."""
        _write(self.ws, {
            "pythontk/pythontk/core_utils/base_dialog.py": "class BaseDialogThing:\n    pass\n",
            "pythontk/pythontk/core_utils/sub_dialog.py": (
                "from .base_dialog import BaseDialogThing\n\n"
                "class SubDialogThing(BaseDialogThing):\n    pass\n"
            ),
            "pythontk/test/test_base_dialog.py": "def test_k():\n    pass\n",
            "pythontk/test/test_sub_dialog_user.py": (
                "import pythontk as ptk\n\ndef test_l():\n    ptk.SubDialogThing()\n"
            ),
        })
        _clear_caches()
        sel, picks = self.picks("pythontk/pythontk/core_utils/base_dialog.py")
        self.assertEqual(picks["pythontk"], {"test_base_dialog", "test_sub_dialog_user"})
        self.assertIn("via pythontk.core_utils.sub_dialog", next(iter(sel.picks["pythontk"]["test_sub_dialog_user"])))

    def test_an_untested_module_is_named_not_guessed(self):
        sel, picks = self.picks("pythontk/pythontk/core_utils/lonely.py")
        self.assertEqual(picks, {})
        self.assertTrue(any("no test reaches pythontk.core_utils.lonely" in n for n in sel.notes))

    def test_packaging_metadata_selects_the_packaging_suite_not_its_namesakes(self):
        """The packaging suite reads ``MANIFEST.in`` / ``pyproject.toml`` directly, so
        no import reaches it; and ``MANIFEST`` names no feature (blendertk's shot
        manifest suites were picked for a ``MANIFEST.in`` edit)."""
        _write(self.ws, {
            "pythontk/MANIFEST.in": "include LICENSE\n",
            "pythontk/pyproject.toml": '[project]\nname = "pythontk"\n',
            "pythontk/test/test_packaging_metadata.py": "def test_m():\n    pass\n",
            "pythontk/test/test_shot_manifest.py": "def test_n():\n    pass\n",
        })
        _clear_caches()
        for rel in ("pythontk/MANIFEST.in", "pythontk/pyproject.toml"):
            _, picks = self.picks(rel)
            self.assertEqual(picks, {"pythontk": {"test_packaging_metadata"}}, rel)

    def test_a_license_text_selects_nothing_and_says_so(self):
        _write(self.ws, {
            "mayatk/COPYING.LESSER": "text\n",
            "mayatk/test/test_copying_tool.py": "def test_o():\n    pass\n",
        })
        _clear_caches()
        sel, picks = self.picks("mayatk/COPYING.LESSER")
        self.assertEqual(picks, {})
        self.assertIn("license text, no tests: mayatk/COPYING.LESSER", sel.notes)

    def test_a_changed_test_selects_itself(self):
        _, picks = self.picks("pythontk/test/test_generic.py")
        self.assertEqual(picks, {"pythontk": {"test_generic"}})

    def test_the_harness_selects_the_runners_own_tests(self):
        sel, picks = self.picks("pythontk/test/run_tests.py")
        self.assertEqual(picks, {"pythontk": {"test_run_tests"}})
        self.assertEqual(sel.harness, {"pythontk": ["run_tests.py"]})

    def test_a_test_helper_selects_the_tests_that_import_it(self):
        _write(self.ws, {
            "pythontk/test/_probe_helpers.py": "def make():\n    return 1\n",
            "pythontk/test/test_uses_helper.py": (
                "from _probe_helpers import make\n\ndef test_j():\n    assert make() == 1\n"
            ),
        })
        _clear_caches()
        _, picks = self.picks("pythontk/test/_probe_helpers.py")
        self.assertEqual(picks, {"pythontk": {"test_uses_helper"}})

    def test_docs_select_nothing_and_report_as_one_note(self):
        _write(self.ws, {"pythontk/docs/README.md": "# x\n", "pythontk/API_INDEX.md": "x\n"})
        sel, picks = self.picks("pythontk/docs/README.md", "pythontk/API_INDEX.md")
        self.assertEqual(picks, {})
        self.assertEqual(sel.docs, ["pythontk/docs/README.md", "pythontk/API_INDEX.md"])
        report = at.report(sel, [], explain=False, workspace=self.ws)
        self.assertEqual(report.count("docs/generated"), 1)

    def test_a_deleted_module_selects_what_still_imports_it(self):
        _commit(self.ws / "pythontk")  # a deletion is a path git knew at HEAD
        (self.ws / "pythontk/pythontk/core_utils/badge.py").unlink()
        sel, picks = self.picks("pythontk/pythontk/core_utils/badge.py")
        self.assertIn("test_badge", picks["pythontk"])  # the import that now breaks
        self.assertIn("deleted: imports pythontk.core_utils.badge", sel.picks["pythontk"]["test_badge"])
        # ...and, through the package __init__ that re-exports it, its users.
        self.assertIn("test_reexport", picks["pythontk"])
        # HEAD supplies the names a deleted module took with it (no index entry here).
        self.assertIn("deleted: names removed StatusBadge", sel.picks["pythontk"]["test_named"])

    def test_a_relative_path_resolves_against_the_current_directory_first(self):
        """Bug: ``cd uitk; affected_tests.py uitk/widgets/table_actions.py``
        resolved the path against the workspace, found nothing there, and mapped
        it as a DELETED module: 1 module selected instead of 11. Fixed: 2026-10-24"""
        old = os.getcwd()
        os.chdir(self.ws / "pythontk")
        self.addCleanup(os.chdir, old)
        sel = at.select([Path("pythontk/core_utils/badge.py")], workspace=self.ws)
        self.assertEqual(set(sel.picks.get("pythontk", {})), {"test_badge", "test_reexport", "test_named"})
        reasons = {r for why in sel.picks["pythontk"].values() for r in why}
        self.assertFalse(any(r.startswith("deleted") for r in reasons), reasons)
        # The workspace stays the fallback for a path the current directory lacks.
        sel = at.select([Path("pythontk/pythontk/core_utils/badge.py")], workspace=self.ws)
        self.assertIn("test_badge", sel.picks.get("pythontk", {}))

    def test_a_path_on_disk_nowhere_and_unknown_to_git_is_named_not_mapped(self):
        """A typo is not a deletion: only a path git knew at HEAD maps as one.
        Fixed: 2026-10-24"""
        _commit(self.ws / "pythontk")
        sel, picks = self.picks("pythontk/pythontk/core_utils/typo.py")
        self.assertEqual(picks, {})
        self.assertIn("no such file: " + str(self.ws / "pythontk/pythontk/core_utils/typo.py"), sel.notes)

    def test_a_removed_name_selects_the_tests_that_still_call_it(self):
        """Moving ``fold_lines`` onto a class breaks every caller of the old name
        at runtime; the module's current names cannot find them, HEAD's can."""
        repo = self.ws / "pythontk"
        module = repo / "pythontk/core_utils/text.py"
        _write(self.ws, {
            "pythontk/pythontk/core_utils/text.py": "def fold_lines(s):\n    return s\n",
            "pythontk/test/test_old_caller.py": (
                "from pythontk.core_utils import fold_lines\n\ndef test_g():\n    fold_lines('x')\n"
            ),
        })
        _commit(repo)
        module.write_text("class Text:\n    @staticmethod\n    def fold_lines(s):\n        return s\n", encoding="utf-8")
        _clear_caches()
        sel, picks = self.picks("pythontk/pythontk/core_utils/text.py")
        self.assertIn("test_old_caller", picks.get("pythontk", set()))
        self.assertIn("names removed fold_lines", sel.picks["pythontk"]["test_old_caller"])

    def test_downstream_is_counted_and_selected_only_on_request(self):
        sel, picks = self.picks("pythontk/pythontk/core_utils/badge.py")
        self.assertNotIn("mayatk", picks)
        self.assertEqual(sel.downstream, {"mayatk": {"test_uses_badge"}})
        _, picks = self.picks("pythontk/pythontk/core_utils/badge.py", downstream=True)
        self.assertEqual(picks["mayatk"], {"test_uses_badge"})

    def test_a_widely_defined_name_is_not_distinctive(self):
        extra = {f"pythontk/pythontk/core_utils/m{i}.py": "class StatusBadge:\n    pass\n" for i in range(3)}
        _write(self.ws, extra)
        _clear_caches()
        self.assertNotIn("StatusBadge", at.distinctive({"StatusBadge"}, self.ws))

    def test_a_ui_or_slot_change_always_selects_the_structural_suites(self):
        """Bug: a ``ui/materials.ui`` + slots change selected only the tests named
        after ``materials``: the suites that hold every ``.ui`` against its slot
        class read the files themselves, so no import reached them, and the
        Blender-only check of those slots went unmentioned. Fixed: 2026-10-24"""
        _write(self.ws, {
            "tentacle/tentacle/__init__.py": "",
            "tentacle/tentacle/tcl.py": "class Tcl:\n    pass\n",
            "tentacle/tentacle/ui/materials.ui": "<ui/>\n",
            "tentacle/tentacle/slots/blender/materials.py": "class MaterialsSlots:\n    pass\n",
            "tentacle/test/test_materials_blender.py": "def test_m():\n    pass\n",
            "tentacle/test/test_tcl.py": "from tentacle.tcl import Tcl\n\ndef test_t():\n    Tcl()\n",
            "tentacle/test/blender/deepened_slots_check.py": (
                "def run():\n    from tentacle.slots.blender.materials import MaterialsSlots\n"
            ),
            "tentacle/test/blender/uv_slot_check.py": (
                "def run():\n    from tentacle.slots.blender.uv import UvSlots\n"
            ),
            **_STRUCTURAL,
        })
        _clear_caches()
        structural = {Path(rel).stem for rel in _STRUCTURAL}
        for changed in ("tentacle/tentacle/ui/materials.ui", "tentacle/tentacle/slots/blender/materials.py"):
            sel, picks = self.picks(changed)
            self.assertLessEqual(structural, picks.get("tentacle", set()), changed)
            report = at.report(sel, [], explain=False, workspace=self.ws)
            hosts = [ln for ln in report.splitlines() if "host-only" in ln]
            self.assertEqual(len(hosts), 1, report)
            self.assertIn("tentacle/test/blender/deepened_slots_check.py", hosts[0])
            self.assertNotIn("uv_slot_check", hosts[0])
        # Outside ui/ and slots/ the gate stays out of it.
        _, picks = self.picks("tentacle/tentacle/tcl.py")
        self.assertEqual(picks, {"tentacle": {"test_tcl"}})

    def test_a_blendertk_panel_ui_selects_its_panel_load_suite(self):
        _write(self.ws, {
            "blendertk/blendertk/__init__.py": "",
            "blendertk/blendertk/edit_utils/mirror.ui": "<ui/>\n",
            "blendertk/test/test_blender_ui_handler.py": "def test_load():\n    pass\n",
        })
        _clear_caches()
        _, picks = self.picks("blendertk/blendertk/edit_utils/mirror.ui")
        self.assertIn("test_blender_ui_handler", picks.get("blendertk", set()))


class TestCommands(_Fixture):
    def test_each_runner_gets_its_own_subset_form_and_no_badge(self):
        sel = at.Selection()
        for pkg, mod in (("uitk", "test_a"), ("mayatk", "test_b"), ("blendertk", "test_c"), ("pythontk", "test_d")):
            sel.add(pkg, mod, "x")
        out = {name: argv[1:] for name, argv, _ in at.commands(sel, k="foo", workspace=self.ws)}
        self.assertEqual(out["uitk"], ["uitk/test/run_tests.py", "--modules", "test_a", "-k", "foo", "--no-badge"])
        self.assertEqual(out["mayatk"], ["mayatk/test/run_tests.py", "test_b", "-k", "foo", "--no-badge"])
        self.assertEqual(out["blendertk"], ["blendertk/test/run_tests.py", "test_c", "--no-badge"])  # no -k there
        self.assertEqual(out["pythontk"], ["pythontk/test/run_tests.py", "test_d", "-k", "foo", "--no-badge"])

    def test_a_runner_without_k_says_so_instead_of_dropping_it_silently(self):
        _write(self.ws, {"blendertk/test/test_c.py": "def test_c():\n    pass\n"})
        _clear_caches()
        sel = at.Selection()
        sel.add("blendertk", "test_c", "x")
        cmds = at.commands(sel, k="foo", workspace=self.ws)
        self.assertIn("no -k in this runner", at.report(sel, cmds, explain=False, workspace=self.ws, k="foo"))

    def test_no_gui_keeps_mayatk_off_its_gui_pass(self):
        sel = at.Selection()
        sel.add("mayatk", "test_b", "x")
        (_, argv, _), = at.commands(sel, gui=False, workspace=self.ws)
        self.assertIn("--no-gui-pass", argv)
        (_, argv, _), = at.commands(sel, gui=True, workspace=self.ws)
        self.assertNotIn("--no-gui-pass", argv)

    def test_a_test_of_the_maya_host_runs_in_maya_whatever_its_local_guard(self):
        """Bug: ``test_marking_menu_gui`` gates on its own
        ``_can_run_marking_menu_tests()``, a name the probe list lacked, so a
        ``tcl_maya.py`` change ran it in plain Python: 12/12 skipped, PASS.
        A test that imports the Maya host builds only inside Maya. A test that
        imports ``maya.cmds`` only to rule batch Maya OUT still runs plain.
        Fixed: 2026-10-24"""
        _write(self.ws, {
            "tentacle/tentacle/__init__.py": "",
            "tentacle/tentacle/tcl_maya.py": "class TclMaya:\n    pass\n",
            "tentacle/test/test_menu_gui.py": (
                "import unittest\n\n"
                "def _can_run_menu_tests():\n"
                "    try:\n        import maya.cmds\n    except ImportError:\n        return False\n"
                "    return True\n\n"
                "@unittest.skipUnless(_can_run_menu_tests(), 'needs Maya')\n"
                "class T(unittest.TestCase):\n"
                "    def test_menu(self):\n"
                "        from tentacle.tcl_maya import TclMaya\n        TclMaya()\n"
            ),
            "tentacle/test/test_widgets_anywhere.py": (
                "def _can_create_widgets():\n"
                "    try:\n        import maya.cmds as cmds\n    except ImportError:\n        return True\n"
                "    return not cmds.about(batch=True)\n\n"
                "def test_w():\n    assert _can_create_widgets() in (True, False)\n"
            ),
        })
        _clear_caches()
        sel = at.Selection()
        sel.add("tentacle", "test_menu_gui", "x")
        sel.add("tentacle", "test_widgets_anywhere", "x")
        groups = {tuple(mods): argv for _, argv, mods in at.commands(sel, workspace=self.ws)}
        self.assertEqual(set(groups), {("test_widgets_anywhere",), ("test_menu_gui",)})
        self.assertIn("--in-maya", groups[("test_menu_gui",)])
        self.assertNotIn("--in-maya", groups[("test_widgets_anywhere",)])
        (_, argv, _), = at.commands(sel, gui=False, workspace=self.ws)  # --no-gui: plain, one run
        self.assertNotIn("--in-maya", argv)

    def test_a_run_that_executed_no_test_is_not_a_pass(self):
        """Bug: a selected run whose every test skipped (no host) printed PASS
        and exited 0 -- nothing was verified. Fixed: 2026-10-24"""
        _write(self.ws, {"m3trik/test/test_tool.py": "def test_z():\n    pass\n"})
        _clear_caches()

        def fake(text):
            return ("m3trik", [sys.executable, "-c", f"print({text!r})"], ["test_tool"])

        all_skipped = "Ran 12 tests in 0.000s\n\nOK (skipped=12)\n"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = at.run([fake(all_skipped)], workspace=self.ws)
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("RAN NOTHING", out.getvalue())
        self.assertNotIn("m3trik: PASS", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = at.run([fake("Ran 12 tests in 0.000s\n\nOK (skipped=11)\n")], workspace=self.ws)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("m3trik: PASS", out.getvalue())

    def test_every_runner_tally_counts_its_executed_tests(self):
        """The tallies the runners print, as logged (unittest, the PASSED/Total
        summaries, pytest, blendertk's checks); None when no tally is known."""
        cases = {
            "Ran 12 tests in 0.000s\n\nOK (skipped=12)\n\n"
            "PASSED: 12 tests, 0 passed, 0 failed, 0 errors, 12 skipped (0.00s)\n": 0,
            "Ran 0 tests in 0.000s\n\nOK\n": 0,  # -k matched nothing
            "Ran 3 tests in 0.1s\n\nFAILED (failures=1, skipped=1)\n": 2,
            "Total: 7031 tests, 0 failures, 0 errors, 66 skipped\n": 6965,
            "Total: 6899 checks, 6899 passed, 0 failed across 92 suites (396.5s)\n": 6899,
            "========== 12 skipped in 0.12s ==========\n": 0,
            "19 passed, 40 subtests passed in 0.38s\n": 19,
            "PASSED: 48 passed, 0 failed, 0 skipped\n": 48,
            "no tally here\n": None,
        }
        for text, executed in cases.items():
            self.assertEqual(at.executed(text), executed, text)

    def test_a_passing_digest_names_the_modules_that_only_skipped(self):
        text = ("[WARNING] 1 module(s) contributed only skips: test_gui\n"
                "Ran 4 tests in 0.1s\n\nOK (skipped=2)\n")
        self.assertIn("[WARNING] 1 module(s) contributed only skips: test_gui", at.digest(text, failed=False))

    def test_a_package_without_a_runner_goes_through_pytest(self):
        _write(self.ws, {"m3trik/test/test_tool.py": "def test_z():\n    pass\n"})
        _clear_caches()
        sel = at.Selection()
        sel.add("m3trik", "test_tool", "x")
        (name, argv, mods), = at.commands(sel, workspace=self.ws)
        self.assertEqual(argv[1:4], ["-m", "pytest", "-q"])
        self.assertTrue(argv[-1].replace("\\", "/").endswith("m3trik/test/test_tool.py"))

    def test_a_passing_digest_is_the_tally_not_the_slowest_list(self):
        mayatk_tail = (
            "SUMMARY\n  test_x: PASS (3 tests) [1.0s]\nTotal: 3 tests, 0 failures, 0 errors, 0 skipped\n"
            "SLOWEST MODULES\n   1.0s  test_x\n   0.5s  test_y\n   0.4s  test_z\n   0.3s  test_w\n"
        )
        self.assertEqual(at.digest(mayatk_tail, failed=False),
                         ["Total: 3 tests, 0 failures, 0 errors, 0 skipped"])
        unittest_tail = "...\n------\nRan 4 tests in 0.1s\n\nOK\n===\nPASSED: 4 tests, 4 passed\n"
        self.assertEqual(at.digest(unittest_tail, failed=False),
                         ["Ran 4 tests in 0.1s", "OK", "PASSED: 4 tests, 4 passed"])

    def test_a_failing_digest_keeps_the_tail(self):
        text = "\n".join(f"line {i}" for i in range(100))
        self.assertEqual(at.digest(text, failed=True)[-1], "line 99")
        self.assertEqual(len(at.digest(text, failed=True)), 40)

    def test_durations_parse_with_minutes_as_the_bare_unit(self):
        self.assertEqual(at._duration("90s"), 90)
        self.assertEqual(at._duration("45"), 45 * 60)
        self.assertEqual(at._duration("3h"), 3 * 3600)
        with self.assertRaises(Exception):
            at._duration("soon")


class TestOutput(unittest.TestCase):
    def test_a_childs_tail_never_crashes_a_legacy_code_page(self):
        """Bug: a blendertk run's tail held a banner's box drawing ('\\u2551'),
        and printing it to a cp1252 redirect raised UnicodeEncodeError --
        the runner died and the packages after it never ran. Fixed:
        2026-10-21"""
        import io

        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        with mock.patch.object(sys, "stdout", stream):
            at._tolerant_output()
            print("    ║ FAIL test_scene_exporter.py")
            stream.flush()
        self.assertIn(b"FAIL test_scene_exporter.py", raw.getvalue())


class TestRealWorkspace(unittest.TestCase):
    def setUp(self):
        _clear_caches()
        self.addCleanup(_clear_caches)

    def test_status_badge_selects_its_own_test_module(self):
        sel = at.select([at.WORKSPACE / "pythontk/pythontk/core_utils/status_badge.py"])
        self.assertIn("test_status_badge", sel.picks.get("pythontk", {}))

    def test_mayatks_gui_modules_are_read_from_its_runner(self):
        self.assertIn("test_shot_manifest", at.gui_required())


if __name__ == "__main__":
    unittest.main()
