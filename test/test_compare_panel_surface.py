"""Tests for compare_panel_surface.py -- the Maya/Blender toolkit parity gate.

One Slots class per category and per tool serves both hosts through ``self.tk``,
so parity is: every toolkit chain a shared Slots class reads resolves on mayatk
AND blendertk (same name, a signature that takes the call's arguments), unless
the host that lacks it never runs the call. Each test builds a small workspace
(pythontk / mayatk / blendertk sources, a tentacle ``slots/`` + ``ui/`` tree) and
runs the static sweep over it -- nothing is imported, no DCC is needed.

The cases pin both directions: a chain one host cannot resolve, an arity
mismatch and a moved name fail; a call its widget's ``requires`` tag hides, a
``slots.tools.HOSTS`` tool and a STANDALONE panel pass. A capability check
(``hasattr`` / ``getattr``, directly or through a helper) is a HOST LIMIT: the
code it guards is excused on exactly the hosts where the checked name is missing,
read with its polarity, so a check on another name, on an owner, or the wrong
way round excuses nothing. ``<widget>_init`` is NOT hidden by ``requires``: uitk
runs it on every host (``MainWindow.register_widget`` applies the visibility
policy, then calls ``init_slot``). ``TestReviewScenarios`` holds the shapes an
independent review found the first version of the gate missing."""

import contextlib
import io
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compare_panel_surface as cps  # noqa: E402

BOOT = (
    "from pythontk.core_utils.module_resolver import bootstrap_package\n"
    "DEFAULT_INCLUDE = {include}\n"
    "MOVED_NAMES = {moved}\n"
    "bootstrap_package(globals(), include=DEFAULT_INCLUDE, moved=MOVED_NAMES)\n"
)

PTK_CORE = """
class CoreUtils:
    @staticmethod
    def selected_objects():
        return []
"""

# The two host halves: ``shared`` takes ``mode`` on Maya only, ``maya_only``
# and ``Engine.maya_member`` exist on Maya only.
MTK_CORE = """
import pythontk as ptk


class CoreUtils(ptk.CoreUtils):
    @classmethod
    def shared(cls, objects, mode="a"):
        return objects

    @classmethod
    def maya_only(cls):
        return None


class Engine:
    def __init__(self, name=None):
        self.result = None

    def run(self):
        return self.result

    def maya_member(self):
        return None
"""

BTK_CORE = """
import pythontk as ptk


class CoreUtils(ptk.CoreUtils):
    @classmethod
    def shared(cls, objects):
        return objects


class Engine:
    def __init__(self, name=None):
        self.result = None

    def run(self):
        return self.result
"""

#: The base Slots class's widget helpers, as tentacle's ``slots/_slots.py`` has them.
BASE_SLOTS = """
class Slots:
    def requires(self, widget, host):
        if not host:
            return True
        widget.setProperty("requires", host)
        return not self.sb.apply_visibility_policy(widget)

    def hide_unless(self, widget, available):
        if available:
            return True
        self.sb.FieldVisibility.set_widget_visible(widget, False)
        widget.hidden_by_policy = "requires"
        return False
"""

UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{name}</class>
 <widget class="QWidget" name="{name}">
{widgets} </widget>
</ui>
"""


def _widget(name, requires=None):
    tag = (
        f'   <property name="requires" stdset="0">\n'
        f"    <string>{requires}</string>\n"
        f"   </property>\n"
        if requires
        else ""
    )
    return f'  <widget class="QPushButton" name="{name}">\n{tag}  </widget>\n'


class Workspace:
    """A throwaway workspace the sweep reads instead of the real one."""

    def __init__(self, case):
        self.root = Path(tempfile.mkdtemp(prefix="cps_"))
        case.addCleanup(shutil.rmtree, self.root, True)
        moved = '{"OldUtils": ("pythontk.OldUtils", "1.0.0")}'
        self.write("pythontk/pythontk/__init__.py",
                   BOOT.format(include='{"core_utils._core_utils": "*"}', moved="{}"))
        self.write("pythontk/pythontk/core_utils/__init__.py", "")
        self.write("pythontk/pythontk/core_utils/_core_utils.py", PTK_CORE)
        for pkg, core in (("mayatk", MTK_CORE), ("blendertk", BTK_CORE)):
            self.write(f"{pkg}/{pkg}/__init__.py",
                       BOOT.format(include='{"core_utils._core_utils": "*"}', moved=moved))
            self.write(f"{pkg}/{pkg}/core_utils/__init__.py", "")
            self.write(f"{pkg}/{pkg}/core_utils/_core_utils.py", core)
        self.tools(hosts="{}", standalone="()")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def tools(self, hosts, standalone):
        self.write("tentacle/tentacle/slots/tools/__init__.py",
                   f"STANDALONE = {standalone}\nHOSTS = {hosts}\n")

    def slots(self, rel, body):
        """A Slots module at ``slots/<rel>`` whose one class has *body*."""
        cls = "".join(p.capitalize() for p in Path(rel).stem.split("_")) + "Slots"
        self.write(f"tentacle/tentacle/slots/{rel}",
                   f"class {cls}:\n" + textwrap.indent(textwrap.dedent(body), "    "))

    def base(self):
        """The base ``Slots`` with its ``requires`` / ``hide_unless`` helpers."""
        self.write("tentacle/tentacle/slots/_slots.py", BASE_SLOTS)

    def lib(self, pkg, members):
        """Add *members* (class-body source) to *pkg*'s ``CoreUtils``."""
        path = self.root / pkg / pkg / "core_utils" / "_core_utils.py"
        head, sep, tail = path.read_text(encoding="utf-8").partition("\n\nclass Engine")
        body = textwrap.indent(textwrap.dedent(members), "    ")
        path.write_text(head.rstrip("\n") + "\n\n" + body + sep + tail, encoding="utf-8")

    def ui(self, rel, *widgets):
        name = Path(rel).stem.split("#")[0]
        self.write(f"tentacle/tentacle/ui/{rel}",
                   UI.format(name=name, widgets="".join(widgets)))

    def sweep(self):
        return cps.sweep(self.root)


def _gaps(result):
    """``{(chain, host)}`` of every gap the sweep reported."""
    return {(g.chain, g.host) for g in result.gaps}


class TestUnresolvedChain(unittest.TestCase):
    def test_a_chain_one_host_lacks_is_a_gap(self):
        ws = Workspace(self)
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), {("CoreUtils.maya_only", "blender")})

    def test_the_cli_fails_on_a_gap_and_names_it(self):
        ws = Workspace(self)
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        out = io.StringIO()
        with mock.patch.object(cps, "ROOT", ws.root), contextlib.redirect_stdout(out):
            rc = cps.main(["--all"])
        self.assertEqual(rc, 1)
        self.assertIn("CoreUtils.maya_only", out.getvalue())
        self.assertIn("blender", out.getvalue())

    def test_a_chain_both_hosts_resolve_passes(self):
        # ``selected_objects`` is inherited from pythontk's class through the
        # ``ptk`` alias: the MRO is followed across packages.
        ws = Workspace(self)
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.shared(self.tk.CoreUtils.selected_objects())
        """)
        result = ws.sweep()
        self.assertEqual(_gaps(result), set())
        self.assertEqual(len(result.sites), 2)
        out = io.StringIO()
        with mock.patch.object(cps, "ROOT", ws.root), contextlib.redirect_stdout(out):
            self.assertEqual(cps.main(["--all"]), 0)

    def test_a_moved_name_is_a_gap_naming_its_new_home(self):
        ws = Workspace(self)
        ws.slots("edit.py", """
            def b000(self):
                self.tk.OldUtils.run()
        """)
        result = ws.sweep()
        self.assertEqual({g.host for g in result.gaps}, {"maya", "blender"})
        self.assertTrue(all("pythontk.OldUtils" in g.problem for g in result.gaps))

    def test_a_non_literal_default_include_exits_2(self):
        # The resolver's include map is read as a literal; a built one would be
        # resolved as "everything", so the gate refuses rather than guess.
        ws = Workspace(self)
        ws.write("blendertk/blendertk/__init__.py",
                 BOOT.format(include="dict([('core_utils._core_utils', '*')])", moved="{}"))
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.shared([])
        """)
        with self.assertRaises(cps.GateError):
            ws.sweep()
        err = io.StringIO()
        with mock.patch.object(cps, "ROOT", ws.root), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cps.main(["--all"]), 2)
        self.assertIn("DEFAULT_INCLUDE", err.getvalue())


class TestRequiresHides(unittest.TestCase):
    def test_a_handler_its_widget_hides_needs_only_its_host(self):
        ws = Workspace(self)
        ws.ui("edit.ui", _widget("b000", requires="maya"))
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        result = ws.sweep()
        self.assertEqual(_gaps(result), set())
        (site,) = result.sites
        self.assertIn("requires", site.excused["blender"])

    def test_a_submenu_ui_tags_the_category_class_too(self):
        ws = Workspace(self)
        ws.ui("edit#submenu.ui", _widget("b000", requires="maya"))
        ws.slots("edit.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), set())

    def test_the_widget_init_still_runs_on_every_host(self):
        ws = Workspace(self)
        ws.ui("edit.ui", _widget("b000", requires="maya"))
        ws.slots("edit.py", """
            def b000_init(self, widget):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), {("CoreUtils.maya_only", "blender")})

    def test_a_private_helper_takes_its_callers_hosts(self):
        ws = Workspace(self)
        ws.ui("edit.ui", _widget("b000", requires="maya"))
        ws.slots("edit.py", """
            def b000(self):
                self._helper()

            def _helper(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), set())

    def test_a_helper_another_handler_reaches_is_required_there(self):
        ws = Workspace(self)
        ws.ui("edit.ui", _widget("b000", requires="maya"), _widget("b001"))
        ws.slots("edit.py", """
            def b000(self):
                self._helper()

            def b001(self):
                self._helper()

            def _helper(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), {("CoreUtils.maya_only", "blender")})

    def test_a_code_built_widget_tagged_for_one_host(self):
        # The rigging shape: a helper tags the widget ``requires`` and the
        # method returns on the host it hides; what follows needs that host only.
        ws = Workspace(self)
        ws.slots("rigging.py", """
            def _host_only(self, widget, host):
                widget.setProperty("requires", host)
                return not self.sb.apply_visibility_policy(widget)

            def tb000_init(self, widget):
                served = [self._host_only(w, "maya") for w in (widget,)]
                if not all(served):
                    return
                widget.clicked.connect(lambda: self.tk.CoreUtils.maya_only())
        """)
        self.assertEqual(_gaps(ws.sweep()), set())

    def test_the_base_class_requires_helper_tags_for_one_host(self):
        # ``Slots.requires(widget, host)`` (slots/_slots.py), called from a category.
        ws = Workspace(self)
        ws.base()
        ws.slots("rigging.py", """
            ROWS = (("Bind", "b001", "maya"),)

            def tb000_init(self, widget):
                if not self.requires(widget, "maya"):
                    return
                widget.clicked.connect(lambda: self.tk.CoreUtils.maya_only())

            def list000_init(self, widget):
                for label, name, host in self.ROWS:
                    self.requires(widget.add(label, setObjectName=name), host)

            def b001(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), set())


class TestHostScopedTools(unittest.TestCase):
    def test_a_hosts_listed_tool_needs_only_its_hosts(self):
        ws = Workspace(self)
        ws.tools(hosts='{"rigger": ("maya",)}', standalone="()")
        ws.slots("tools/rigger.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        ws.write("tentacle/tentacle/slots/tools/_rigger/helper.py",
                 "def run(slots):\n    return slots.tk.CoreUtils.maya_only()\n")
        result = ws.sweep()
        self.assertEqual(_gaps(result), set())
        self.assertEqual(len(result.sites), 2)
        self.assertTrue(all("HOSTS" in s.excused["blender"] for s in result.sites))

    def test_the_same_tool_unlisted_serves_both(self):
        ws = Workspace(self)
        ws.slots("tools/rigger.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), {("CoreUtils.maya_only", "blender")})

    def test_a_standalone_panel_has_no_host_contract(self):
        ws = Workspace(self)
        ws.tools(hosts="{}", standalone='("packer",)')
        ws.slots("tools/packer.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), set())


class TestHostLimits(unittest.TestCase):
    """A capability check excuses what it dominates on the hosts where the
    checked name is missing -- and only there, and only the right way round."""

    def _sweep(self, body, rel="edit.py", base=False):
        ws = Workspace(self)
        if base:
            ws.base()
        ws.slots(rel, body)
        return ws.sweep()

    def test_a_hasattr_block_excuses_the_host_lacking_the_name(self):
        result = self._sweep("""
            def b000(self):
                if hasattr(self.tk.CoreUtils, "maya_only"):
                    self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(result), set())
        site = next(s for s in result.sites if s.chain == "CoreUtils.maya_only")
        self.assertIn("CoreUtils.maya_only", site.excused["blender"])
        self.assertNotIn("maya", site.excused)  # the name exists there: it runs

    def test_an_early_exit_on_getattr_excuses_what_follows(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                if getattr(self.tk.CoreUtils, "maya_only", None) is None:
                    return
                self.tk.CoreUtils.maya_only()
        """)), set())

    def test_a_helper_handed_the_name_through_a_table(self):
        # The old tube_rig shape: ``_unsupported`` looks the operation up by name.
        self.assertEqual(_gaps(self._sweep("""
            HOST_ONLY = {"b000": "maya_only"}

            def _unsupported(self, button):
                return getattr(self.tk.CoreUtils, self.HOST_ONLY[button], None) is None

            def b000(self):
                if self._unsupported("b000"):
                    return
                self.tk.CoreUtils.maya_only()
        """)), set())

    def test_a_check_on_another_name_excuses_nothing(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                if hasattr(self.tk.CoreUtils, "shared"):
                    self.tk.CoreUtils.maya_only()
        """)), {("CoreUtils.maya_only", "blender")})

    def test_a_checked_reference_hides_the_private_method_it_wires(self):
        # The blendshape shape: the menu row (and the action it connects) only
        # exists where the check holds.
        self.assertEqual(_gaps(self._sweep("""
            def b000_init(self, widget):
                if getattr(self.tk.CoreUtils, "maya_only", None) is not None:
                    widget.clicked.connect(self._action)

            def _action(self):
                self.tk.CoreUtils.maya_only()
        """)), set())

    def test_hide_unless_over_a_capability_hides_the_handler(self):
        # The audio_clips shape: ``hide_unless(item, self._has(*ops))``.
        self.assertEqual(_gaps(self._sweep("""
            def _has(self, *operations):
                return all(getattr(self.tk.CoreUtils, op, None) is not None for op in operations)

            def b000_init(self, widget):
                self.hide_unless(widget, self._has("shared", "maya_only"))

            def b000(self):
                self.tk.CoreUtils.maya_only()
        """, base=True)), set())

    def test_hide_unless_over_a_class_table_loop(self):
        # The tube_rig shape: ``{button: operation}``, hidden in ``__init__``.
        result = self._sweep("""
            HOST_ONLY = {"b000": "maya_only"}

            def __init__(self, switchboard):
                for button, method in self.HOST_ONLY.items():
                    served = getattr(self.tk.CoreUtils, method, None) is not None
                    self.hide_unless(getattr(self.ui, button), served)

            def b000(self):
                self.tk.CoreUtils.maya_only()
                self.tk.Engine().maya_member()
        """, rel="tools/rigger.py", base=True)
        self.assertEqual(_gaps(result), set())
        member = next(s for s in result.sites if s.chain == "Engine().maya_member")
        self.assertIn("CoreUtils.maya_only", member.excused["blender"])

    def test_hide_unless_over_a_name_both_hosts_have_hides_nothing(self):
        self.assertEqual(_gaps(self._sweep("""
            def _has(self, operation):
                return getattr(self.tk.CoreUtils, operation, None) is not None

            def b000_init(self, widget):
                self.hide_unless(widget, self._has("shared"))

            def b000(self):
                self.tk.CoreUtils.maya_only()
        """, base=True)), {("CoreUtils.maya_only", "blender")})

    def test_a_disabled_widget_is_not_hidden(self):
        # ``setEnabled`` leaves the control there (a repeat-last can still run
        # its slot): only hiding it excuses the handler.
        self.assertEqual(_gaps(self._sweep("""
            def _has(self, operation):
                return getattr(self.tk.CoreUtils, operation, None) is not None

            def b000_init(self, widget):
                widget.setEnabled(self._has("maya_only"))

            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)), {("CoreUtils.maya_only", "blender")})

    def test_a_requires_table_row_hides_its_method(self):
        # The scene shape: code-built rows ``(label, name, tip, requires)``.
        ws = Workspace(self)
        ws.slots("scene.py", """
            ROWS = (("Cleanup", "b006", "Remove unknown nodes.", "maya"),
                    ("Purge", "b007", "Purge orphans.", None))

            def list000_init(self, widget):
                for label, name, tip, requires in self.ROWS:
                    item = widget.add(label, setObjectName=name)
                    if requires:
                        item.setProperty("requires", requires)

            def b006(self):
                self.tk.CoreUtils.maya_only()

            def b007(self):
                self.tk.CoreUtils.maya_only()
        """)
        result = ws.sweep()
        self.assertEqual(_gaps(result), {("CoreUtils.maya_only", "blender")})
        self.assertEqual({s.where for g in result.gaps for s in g.sites}, {"SceneSlots.b007"})

    def test_an_init_returning_where_its_widget_is_hidden(self):
        # ``if widget.hidden_by_policy == "requires": return`` -- what follows
        # runs where the widget shows.
        ws = Workspace(self)
        ws.ui("scene.ui", _widget("b014", requires="maya"))
        ws.slots("scene.py", """
            def b014_init(self, widget):
                if getattr(widget, "hidden_by_policy", None) == "requires":
                    return
                self.tk.CoreUtils.maya_only()
        """)
        self.assertEqual(_gaps(ws.sweep()), set())

    def test_an_attribute_error_handler_guards_its_body(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                try:
                    self.tk.CoreUtils.maya_only()
                except AttributeError:
                    pass
        """)), set())

    def test_the_arnold_shape_is_a_host_limit(self):
        # rendering.py: the renderer list is the host's, so the Arnold steps are
        # checked on the toolkit -- excused on the host lacking Arnold, run where
        # it has it.
        ws = Workspace(self)
        ws.lib("mayatk", """
            @classmethod
            def prepare_arnold_preview(cls):
                return None
        """)
        ws.slots("rendering.py", """
            def tb001(self, widget):
                render_utils = self.tk.CoreUtils
                renderer = widget.currentData()
                if renderer == "arnold" and hasattr(render_utils, "prepare_arnold_preview"):
                    render_utils.prepare_arnold_preview()
        """)
        result = ws.sweep()
        self.assertEqual(_gaps(result), set())
        site = next(s for s in result.sites if s.chain == "CoreUtils.prepare_arnold_preview")
        self.assertIn("CoreUtils.prepare_arnold_preview", site.excused["blender"])
        self.assertNotIn("maya", site.excused)
        self.assertIn(("CoreUtils.prepare_arnold_preview", "blender"),
                      {(c, h) for c, h, _ in result.one_host})


class TestArity(unittest.TestCase):
    def _sweep(self, body):
        ws = Workspace(self)
        ws.slots("edit.py", body)
        return ws.sweep()

    def test_an_unknown_keyword_on_one_host_is_a_gap(self):
        result = self._sweep("""
            def b000(self):
                self.tk.CoreUtils.shared([], mode="b")
        """)
        self.assertEqual(_gaps(result), {("CoreUtils.shared", "blender")})
        self.assertIn("mode", result.gaps[0].problem)

    def test_too_many_positionals_on_one_host_is_a_gap(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.shared([], "b")
        """)), {("CoreUtils.shared", "blender")})

    def test_a_missing_required_argument_is_a_gap(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.shared()
        """)), {("CoreUtils.shared", "maya"), ("CoreUtils.shared", "blender")})

    def test_a_starred_call_is_not_checked_and_says_so(self):
        result = self._sweep("""
            def b000(self, *args):
                self.tk.CoreUtils.shared(*args)
        """)
        self.assertEqual(_gaps(result), set())
        self.assertIn(("CoreUtils.shared", "starred"),
                      {(c, why) for (c, why) in result.unchecked})


class TestEngineInstances(unittest.TestCase):
    def test_an_engine_instance_member_one_host_lacks_is_a_gap(self):
        ws = Workspace(self)
        ws.slots("tools/runner.py", """
            def __init__(self):
                self.engine = self.tk.Engine(name="x")

            def b000(self):
                self.engine.run()
                self.engine.result
                self.engine.maya_member()
        """)
        self.assertEqual(_gaps(ws.sweep()), {("Engine().maya_member", "blender")})

    def test_a_constructor_arity_mismatch_is_a_gap(self):
        ws = Workspace(self)
        ws.slots("tools/runner.py", """
            def b000(self):
                self.tk.Engine(bogus=1).run()
        """)
        self.assertEqual(
            _gaps(ws.sweep()), {("Engine", "maya"), ("Engine", "blender")}
        )


class TestReviewScenarios(unittest.TestCase):
    """Each a real gap on Blender (blendertk lacks ``CoreUtils.maya_only`` /
    ``Engine.maya_member``, or its signature differs), except the two marked:
    the hidden-widget control, and kwargs forwarding (an accepted static limit:
    listed, never failed)."""

    def _sweep(self, body=None, rel="edit.py", ui=None, extra=None, lib=None, base=False):
        ws = Workspace(self)
        if base:
            ws.base()
        for pkg, members in (lib or {}).items():
            ws.lib(pkg, members)
        if body is not None:
            ws.slots(rel, body)
        if ui:
            ws.ui(ui[0], *(_widget(n, r) for n, r in ui[1]))
        for path, text in (extra or {}).items():
            ws.write(path, text)
        return ws.sweep()

    def assertBlenderGap(self, result, chain="CoreUtils.maya_only"):
        self.assertIn((chain, "blender"), _gaps(result))

    def test_alias_other_name(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                t = self.tk
                t.CoreUtils.maya_only()
        """))

    def test_computed_getattr_table(self):
        self.assertBlenderGap(self._sweep("""
            OPS = {"go": "maya_only"}

            def b000(self):
                getattr(self.tk.CoreUtils, self.OPS["go"])()
        """))

    def test_wrong_polarity_block(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                if not hasattr(self.tk.CoreUtils, "maya_only"):
                    self.tk.CoreUtils.maya_only()
        """))

    def test_wrong_polarity_early_exit(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                if hasattr(self.tk.CoreUtils, "maya_only"):
                    return
                self.tk.CoreUtils.maya_only()
        """))

    def test_wrong_polarity_or(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                hasattr(self.tk.CoreUtils, "maya_only") or self.tk.CoreUtils.maya_only()
        """))

    def test_guard_on_parent_class(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                if hasattr(self.tk, "CoreUtils"):
                    self.tk.CoreUtils.maya_only()
        """))

    def test_guard_helper_other_name(self):
        self.assertBlenderGap(self._sweep("""
            def _has(self, op):
                return getattr(self.tk.CoreUtils, op, None) is not None

            def b000(self):
                if self._has("shared"):
                    self.tk.CoreUtils.maya_only()
        """))

    def test_guard_helper_other_name_early_exit(self):
        self.assertBlenderGap(self._sweep("""
            def _has(self, op):
                return getattr(self.tk.CoreUtils, op, None) is not None

            def b000(self):
                if not self._has("shared"):
                    return
                self.tk.CoreUtils.maya_only()
        """))

    def test_guard_helper_root_prefix_any_chain(self):
        self.assertBlenderGap(self._sweep("""
            def _has(self, op):
                return getattr(self.tk, op, None) is not None

            def b000(self):
                if self._has("CoreUtils"):
                    self.tk.Engine().maya_member()
        """), "Engine().maya_member")

    def test_class_wide_capability_leak(self):
        result = self._sweep("""
            def _has(self, *ops):
                return all(getattr(self.tk.CoreUtils, op, None) is not None for op in ops)

            def b000_init(self, widget):
                widget.setVisible(self._has("maya_only"))

            def b000(self):
                self.tk.CoreUtils.maya_only()

            def b001(self):
                self.tk.CoreUtils.maya_only()   # b001 shows on both hosts, ungated
        """)
        self.assertBlenderGap(result)
        self.assertEqual({s.where for g in result.gaps for s in g.sites}, {"EditSlots.b001"})

    def test_try_attributeerror_deferred_lambda(self):
        self.assertBlenderGap(self._sweep("""
            def b000_init(self, widget):
                try:
                    widget.clicked.connect(lambda: self.tk.CoreUtils.maya_only())
                except AttributeError:
                    pass
        """))

    def test_nested_class_in_slots(self):
        self.assertBlenderGap(self._sweep("""
            class _Row:
                def __init__(self, slots):
                    self.slots = slots

                def run(self):
                    self.slots.tk.CoreUtils.maya_only()

            def b000(self):
                self._Row(self).run()
        """))

    def test_cross_file_private_helper(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                self._apply()

            def _apply(self):
                self.tk.CoreUtils.maya_only()
        """, rel="tools/rigger.py", ui=("tools/rigger.ui", [("b000", "maya")]), extra={
            "tentacle/tentacle/slots/tools/_rigger/panel.py":
                "class Panel:\n    def __init__(self, slots):\n        self.slots = slots\n"
                "    def refresh(self):\n        self.slots._apply()\n"}))

    def test_lazy_property_engine(self):
        self.assertBlenderGap(self._sweep("""
            _engine = None

            @property
            def engine(self):
                if self._engine is None:
                    self._engine = self.tk.Engine()
                return self._engine

            def b000(self):
                self.engine.maya_member()
        """, rel="tools/runner.py"), "Engine().maya_member")

    def test_annassign_engine(self):
        self.assertBlenderGap(self._sweep("""
            def __init__(self):
                self.engine: object = self.tk.Engine()

            def b000(self):
                self.engine.maya_member()
        """, rel="tools/runner.py"), "Engine().maya_member")

    def test_cached_property_engine(self):
        self.assertBlenderGap(self._sweep("""
            @cached_property
            def engine(self):
                return self.tk.Engine()

            def b000(self):
                self.engine.maya_member()
        """, rel="tools/runner.py"), "Engine().maya_member")

    def test_engine_via_factory_lowercase(self):
        factory = """
            @classmethod
            def make_engine(cls):
                return Engine()
        """
        self.assertBlenderGap(self._sweep("""
            def __init__(self):
                self.engine = self.tk.CoreUtils.make_engine()

            def b000(self):
                self.engine.maya_member()
        """, rel="tools/runner.py", lib={"mayatk": factory, "blendertk": factory}),
            "CoreUtils.make_engine().maya_member")

    def test_empty_requires_string(self):
        # uitk shows a widget whose ``requires`` is blank on every host.
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """, ui=("edit.ui", [("b000", " ")])))

    def test_kwargs_forwarding_is_listed_not_failed(self):
        # An accepted static limit: the arguments go on through ``**kwargs``.
        result = self._sweep("""
            def b000(self):
                self.tk.CoreUtils.fwd([], mode="b")
        """, lib={
            "mayatk": """
                @classmethod
                def fwd(cls, objects, mode='a'):
                    return objects
            """,
            "blendertk": """
                @classmethod
                def fwd(cls, *args, **kwargs):
                    return cls.shared(*args, **kwargs)
            """})
        self.assertEqual(_gaps(result), set())
        self.assertIn(("CoreUtils.fwd", "forwarded"), set(result.unchecked))

    def test_CONTROL_hidden_widget_no_gap_expected(self):
        self.assertEqual(_gaps(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """, ui=("edit.ui", [("b000", "maya")]))), set())

    def test_second_class_shares_widget_name(self):
        # ``requires`` hides the Slots class's handler, not another class's
        # method of the same name.
        self.assertBlenderGap(self._sweep(ui=("edit.ui", [("b000", "maya")]), extra={
            "tentacle/tentacle/slots/edit.py":
                "class EditSlots:\n    def b000(self):\n        pass\n\n"
                "class _Dialog:\n    def __init__(self, slots):\n        self.slots = slots\n"
                "    def b000(self):  # the dialog's own button, every host\n"
                "        self.slots.tk.CoreUtils.maya_only()\n"}))

    def test_staticmethod_binding_vs_base(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.selected_objects(1)
        """, lib={"mayatk": """
                @classmethod
                def selected_objects(cls, flag=None):
                    return []
            """}), "CoreUtils.selected_objects")

    def test_moved_target_missing(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                self.tk.OldUtils.run()
        """), "OldUtils.run")

    def test_decorator_forwarder_on_blender(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                self.tk.CoreUtils.deco([], 1, 2)
        """, lib={
            "mayatk": """
                @classmethod
                def deco(cls, a, b, c):
                    return a
            """,
            "blendertk": """
                @classmethod
                @ptk.CoreUtils.undoable
                def deco(cls, a):
                    return a
            """}), "CoreUtils.deco")

    def test_partial_callback_hidden_vs_shown(self):
        # ``b000_init`` wires the callback on every host.
        self.assertBlenderGap(self._sweep("""
            def b000_init(self, widget):
                widget.clicked.connect(functools.partial(self._go, 1))

            def _go(self, n):
                self.tk.CoreUtils.maya_only()
        """, ui=("edit.ui", [("b000", "maya")])))

    def test_comprehension_nested_fn(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                def inner():
                    return [self.tk.CoreUtils.maya_only() for _ in range(2)]
                return inner()
        """))

    def test_getattr_default_called_unchecked(self):
        self.assertBlenderGap(self._sweep("""
            def b000(self):
                getattr(self.tk.CoreUtils, "maya_only", None)()
        """))

    def test_string_dispatched_private_also_hidden_ref(self):
        self.assertBlenderGap(self._sweep("""
            HANDLERS = {"Go": "_go"}

            def b000(self):
                self._go()

            def b001(self, item):
                getattr(self, self.HANDLERS[item.text()])()

            def _go(self):
                self.tk.CoreUtils.maya_only()
        """, ui=("edit.ui", [("b000", "maya"), ("b001", None)])))


class TestUiLint(unittest.TestCase):
    def test_a_promoted_class_missing_from_customwidgets_fails(self):
        ws = Workspace(self)
        ws.write("tentacle/tentacle/ui/edit.ui",
                 UI.format(name="edit", widgets='  <widget class="ComboBox" name="cmb000"/>\n'))
        result = ws.sweep()
        self.assertEqual(len(result.lint), 1)
        self.assertIn("ComboBox", result.lint[0])
        self.assertTrue(result.failed)


class TestCli(unittest.TestCase):
    def test_help_prints_usage_and_exits_zero(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cps.main(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--all --write", buf.getvalue())

    def test_panel_resolves_a_stem_or_a_class_name(self):
        ws = Workspace(self)
        ws.slots("tools/rigger.py", """
            def b000(self):
                self.tk.CoreUtils.maya_only()
        """)
        for name in ("rigger", "RiggerSlots", "Rigger"):
            with self.subTest(name=name):
                out = io.StringIO()
                with mock.patch.object(cps, "ROOT", ws.root), contextlib.redirect_stdout(out):
                    rc = cps.main(["--panel", name])
                self.assertEqual(rc, 1)
                self.assertIn("tools/rigger.py", out.getvalue())

    def test_an_unknown_panel_exits_naming_it(self):
        ws = Workspace(self)
        with mock.patch.object(cps, "ROOT", ws.root), self.assertRaises(SystemExit) as ctx:
            cps.main(["--panel", "no_such_panel"])
        self.assertIn("no_such_panel", str(ctx.exception.code))


if __name__ == "__main__":
    unittest.main()
