"""Tests for generate_parity_audit.py — the Maya<->Blender parity scoreboard.

Layers 2-3 read the parity gate (``TestGateLayers``). The rest is regression coverage
for the `hollow` metric. It is meant to count *parity theater* — a
visible control whose handler only pops a message box and does nothing. The original
substring heuristic ("body mentions message_box and contains no `btk.`/`bpy.ops`/`cmds.`
call") flagged two shapes that are not defects at all:

  * a **guard clause** (`if not selection: message_box(...); return`) on a handler that goes
    on to do real work through plain attribute writes / helper calls (`o.modifiers.new(...)`,
    `c.data.bevel_depth = ...`) — all 13 of blendertk's flagged handlers were this;
  * a control correctly retired via `<name>_init -> setVisible(False)` (a control one host
    cannot serve is hidden there, never a stub: CODE_STANDARD section 15).

That reported "13 hollow handlers" in PARITY_AUDIT.md's headline scorecard where there are
none. These tests pin both directions: the metric must still fire on a genuinely dead
visible control, and must stay silent on the two false-positive shapes."""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_parity_audit as gpa  # noqa: E402


class TestHollowHandlerMetric(unittest.TestCase):
    def _metrics(self, source):
        d = Path(tempfile.mkdtemp(prefix="gpa_"))
        self.addCleanup(shutil.rmtree, d, True)
        p = d / "probe_slots.py"
        p.write_text(source, encoding="utf-8")
        return gpa.code_metrics(str(p))

    def test_message_only_visible_handler_is_hollow(self):
        # The one real defect shape: a visible button that only says "not applicable".
        m = self._metrics(
            'class S:\n'
            '    def b000(self):\n'
            '        """Dead control."""\n'
            '        self.sb.message_box("Not applicable in Blender.")\n'
        )
        self.assertEqual(m["hollow"], 1)

    def test_message_box_arguments_are_not_work(self):
        # Composing the message (f-string / .format() / str()) is not doing work.
        m = self._metrics(
            'class S:\n'
            '    def b000(self):\n'
            '        self.sb.message_box("<b>{}</b>".format(str(self.name)))\n'
        )
        self.assertEqual(m["hollow"], 1)

    def test_guard_clause_handler_is_not_hollow(self):
        # blendertk's actual shape: bail with a message, otherwise do real work through
        # plain attribute writes -- no btk./bpy.ops call for a substring heuristic to see.
        m = self._metrics(
            'class S:\n'
            '    def b058(self):\n'
            '        """Curve to Tube."""\n'
            '        curves = self._selected_curves()\n'
            '        if not curves:\n'
            '            self.sb.message_box("Curve to Tube requires selected curve(s).")\n'
            '            return\n'
            '        for c in curves:\n'
            '            c.data.bevel_depth = 0.1\n'
        )
        self.assertEqual(m["hollow"], 0)

    def test_attribute_write_alone_counts_as_work(self):
        # A handler whose entire action is a property write still is not hollow.
        m = self._metrics(
            'class S:\n'
            '    def chk000(self, state):\n'
            '        if state is None:\n'
            '            self.sb.message_box("No state.")\n'
            '            return\n'
            '        self.ui.overlay.show_wire = state\n'
        )
        self.assertEqual(m["hollow"], 0)

    def test_hidden_control_is_not_hollow(self):
        # The documented treatment for a no-equivalent control: hide it in _init and keep a
        # defensive message. That is correct, not a defect.
        m = self._metrics(
            'class S:\n'
            '    def b038_init(self, widget):\n'
            '        """No Blender concept."""\n'
            '        widget.setVisible(False)\n'
            '    def b038(self):\n'
            '        self.sb.message_box("Assign Invisible is not applicable in Blender.")\n'
        )
        self.assertEqual(m["hollow"], 0)

    def test_hidden_control_is_not_hollow_regardless_of_definition_order(self):
        # The hide-check resolves against the whole file, so a handler defined before its
        # _init must not be miscounted on the way past.
        m = self._metrics(
            'class S:\n'
            '    def b038(self):\n'
            '        self.sb.message_box("Not applicable.")\n'
            '    def b038_init(self, widget):\n'
            '        widget.setVisible(False)\n'
        )
        self.assertEqual(m["hollow"], 0)

    def test_shipped_slots_report_no_hollow_handlers(self):
        # End-to-end: the shipped marking-menu slots (one composed class per category,
        # both hosts') contain no parity theater.
        slots = Path(gpa.rp("tentacle", "tentacle", "slots"))
        if not slots.is_dir():
            self.skipTest(f"{slots} not present")
        files = sorted(p for p in slots.glob("*.py") if not p.name.startswith("_"))
        self.assertTrue(files, f"no composed slot modules in {slots}")
        for path in files:
            with self.subTest(slot=path.name):
                self.assertEqual(gpa.code_metrics(str(path))["hollow"], 0)

    def test_other_metrics_unaffected(self):
        # The rewrite must not disturb the sibling counters it shares a pass with.
        m = self._metrics(
            'class S:\n'
            '    def tb000_init(self, widget):\n'
            '        widget.option_box.menu.add("QCheckBox", setObjectName="chk000")\n'
            '    def tb000(self, widget):\n'
            '        v = widget.option_box.menu.chk000.isChecked()\n'
            '        return v\n'
        )
        self.assertEqual(m["opt_boxes"], 2)  # both the _init and the handler reference it
        self.assertEqual(m["handlers"], 1)  # _init is not a handler
        self.assertEqual(m["controls"], 1)  # one .add( that is not a Separator


class TestGateLayers(unittest.TestCase):
    """Layers 2-3 read the parity gate (``compare_panel_surface.sweep``): one Slots
    class serves both hosts, so a tool's or a category's verdict is the gate's."""

    def _result(self):
        cps = gpa.cps
        tool = cps.Site("tools/rigger.py", "RiggerSlots.b000", 1, ("CoreUtils", "maya_only"), None)
        helper = cps.Site("tools/_rigger/helper.py", "run", 1, ("CoreUtils", "shared"), None)
        shared = cps.Site("tools/_app_bridge/host.py", "run", 1, ("CoreUtils", "shared"), None)
        category = cps.Site("edit.py", "EditSlots.b000", 1, ("CoreUtils", "shared"), None)
        sites = [tool, helper, shared, category]
        return cps.SweepResult(
            files={s.rel: [s] for s in sites},
            sites=sites,
            gaps=[cps.Gap("CoreUtils.maya_only", "blender", "does not resolve", [tool])],
            unverified={},
            lint=[],
            tools={"rigger": "both"},
        )

    def test_a_tool_gap_reaches_its_row(self):
        rows = gpa.gate_rows(self._result())
        self.assertEqual(rows["tools/rigger"]["gaps"], 1)
        self.assertEqual(rows["edit.py"]["gaps"], 0)

    def test_a_tools_helpers_count_toward_it(self):
        rows = gpa.gate_rows(self._result())
        self.assertEqual(rows["tools/rigger"]["sites"], 2)
        self.assertEqual(rows["tools/rigger"]["chains"], {"CoreUtils.maya_only", "CoreUtils.shared"})

    def test_a_helper_package_no_tool_owns_is_its_own_row(self):
        rows = gpa.gate_rows(self._result())
        self.assertIn("tools/_app_bridge", rows)


class TestRegistryFreshnessGuard(unittest.TestCase):
    """The L4 layer reads API_REGISTRY.json, so the guard refuses a registry older than the
    package source. But its glob saw `*_ui.py` too -- uitk's compiler rewrites those every
    time a panel's `.ui` changes (i.e. every time a tool is opened in a DCC), while the
    registry deliberately skips them. So `--check` failed with STALE INPUT after any panel
    had been opened, pointing the caller at a generator with nothing to regenerate."""

    #: Arbitrary fixed epoch — the guard compares mtimes, so only the delta matters,
    #: and a literal keeps the fixture independent of wall-clock resolution.
    REGISTRY_MTIME = 1_700_000_000

    def _pkg(self, sources, sources_newer_by=0):
        """Build ROOT/<pkg>/{API_REGISTRY.json, <pkg>/...} and point `gpa.ROOT` at it.

        Every source file is stamped `sources_newer_by` seconds AFTER the registry, so
        the `newest > reg_m` comparison is exact rather than racing the filesystem's
        timestamp resolution (0 = same instant, i.e. not stale).
        """
        root = Path(tempfile.mkdtemp(prefix="gpa_fresh_"))
        self.addCleanup(shutil.rmtree, root, True)
        pkg_dir = root / "probetk" / "probetk"
        pkg_dir.mkdir(parents=True)

        reg = root / "probetk" / "API_REGISTRY.json"
        reg.write_text("{}", encoding="utf-8")
        os.utime(reg, (self.REGISTRY_MTIME, self.REGISTRY_MTIME))

        stamp = self.REGISTRY_MTIME + sources_newer_by
        for name in sources:
            f = pkg_dir / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x = 1\n", encoding="utf-8")
            os.utime(f, (stamp, stamp))

        patcher = mock.patch.object(gpa, "ROOT", str(root))
        patcher.start()
        self.addCleanup(patcher.stop)
        return root

    def test_newer_ui_py_does_not_gate_freshness(self):
        # The regression: a compiler-regenerated `*_ui.py` is not registry input.
        self._pkg(["panel_ui.py"], sources_newer_by=500)
        gpa.check_registry_freshness("probetk")  # must not SystemExit

    def test_newer_nested_ui_py_does_not_gate_freshness(self):
        # The glob is recursive; the exclusion must hold at any depth.
        self._pkg(["rig_utils/telescope_rig_ui.py"], sources_newer_by=500)
        gpa.check_registry_freshness("probetk")

    def test_newer_real_source_still_gates_freshness(self):
        # The guard's whole point: a real source edit must still refuse the run.
        self._pkg(["telescope_rig.py"], sources_newer_by=500)
        with self.assertRaises(SystemExit) as cm:
            gpa.check_registry_freshness("probetk")
        self.assertIn("STALE INPUT", str(cm.exception))

    def test_ui_py_exclusion_does_not_mask_a_sibling_edit(self):
        # A `_ui.py` sitting next to a genuinely stale module must not hide it.
        self._pkg(["panel_ui.py", "panel.py"], sources_newer_by=500)
        with self.assertRaises(SystemExit):
            gpa.check_registry_freshness("probetk")

    def test_missing_registry_is_reported(self):
        root = self._pkg(["panel.py"])
        (root / "probetk" / "API_REGISTRY.json").unlink()
        with self.assertRaises(SystemExit) as cm:
            gpa.check_registry_freshness("probetk")
        self.assertIn("missing", str(cm.exception))


class TestCli(unittest.TestCase):
    """`--help` once fell through the hand-parsed argv and regenerated the doc."""

    def _run(self, *args, out_text=None):
        """Run ``main`` on *args* against a temp doc; return (doc path, freshness mock, exit code)."""
        d = Path(tempfile.mkdtemp(prefix="gpa_cli_"))
        self.addCleanup(shutil.rmtree, d, True)
        out = d / "PARITY_AUDIT.md"
        if out_text is not None:
            out.write_text(out_text, encoding="utf-8")
        code = None
        with mock.patch.object(gpa, "OUT", str(out)), mock.patch.object(
            gpa, "build", return_value="report\n"
        ), mock.patch.object(gpa, "check_registry_freshness") as fresh, mock.patch.object(
            sys, "argv", ["generate_parity_audit.py", *args]
        ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                gpa.main()
            except SystemExit as e:
                code = e.code
        return out, fresh, code

    def test_help_exits_zero_and_writes_nothing(self):
        out, _, code = self._run("--help")
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())

    def test_check_and_allow_stale_still_parse(self):
        _, fresh, code = self._run("--check", "--allow-stale", out_text="report\n")
        self.assertIsNone(code)
        fresh.assert_not_called()

    def test_unknown_flag_is_a_usage_error(self):
        out, _, code = self._run("--chek")
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
