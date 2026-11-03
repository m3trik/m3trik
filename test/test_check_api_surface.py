"""Tests for check_api_surface.py: the shadow report, the static read it
checks, the delta against the last release tag and the semver verdict from
it, and the ``--check`` retirement gate each ecosystem package's CI runs."""

import ast
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_api_surface as g  # noqa: E402
from pythontk import ApiSurface, ClassSurface, ModuleSurface, PackageSurface, SymbolRecord  # noqa: E402


def _cls(name: str) -> "ClassSurface":
    return ClassSurface(name=name, summary="", line=1, bases=["object"], members=[])


def _mod(relpath: str, classes: list) -> "ModuleSurface":
    return ModuleSurface(relpath=relpath, summary="", functions=[], classes=classes)


def _pkg(name: str, modules: list) -> "PackageSurface":
    return PackageSurface(name=name, source_root=f"{name}/{name}", modules=modules)


class TestShadowBucketing(unittest.TestCase):
    def test_parity_vs_genuine_split(self):
        # Bevel: mayatk + blendertk only -> intentional port parity.
        # CoreUtils: pythontk + mayatk    -> genuine cross-layer collision.
        mayatk = _pkg(
            "mayatk",
            [_mod("edit_utils/_edit_utils.py", [_cls("Bevel"), _cls("CoreUtils")])],
        )
        blendertk = _pkg(
            "blendertk", [_mod("edit_utils/_edit_utils.py", [_cls("Bevel")])]
        )
        pythontk = _pkg(
            "pythontk", [_mod("core_utils/_core_utils.py", [_cls("CoreUtils")])]
        )

        md = g.emit_shadow_report([pythontk, mayatk, blendertk])
        self.assertIn("Intentional mayatk", md, "parity bucket header missing")
        genuine, parity = md.split("Intentional mayatk", 1)

        self.assertIn(
            "CoreUtils",
            genuine,
            "genuine cross-layer collision should be in the top section",
        )
        self.assertNotIn(
            "Bevel", genuine, "intentional parity must NOT pollute the genuine section"
        )
        self.assertIn(
            "Bevel", parity, "mayatk<->blendertk parity should be bucketed separately"
        )

    def test_no_collisions_message(self):
        md = g.emit_shadow_report([_pkg("pythontk", [_mod("m.py", [_cls("Solo")])])])
        self.assertIn("No cross-package name collisions", md)


class TestJsonReconstruction(unittest.TestCase):
    def test_roundtrip_preserves_symbols(self):
        pkg = _pkg("pythontk", [_mod("m.py", [_cls("CoreUtils")])])
        rebuilt = PackageSurface.from_dict(asdict(pkg))
        self.assertEqual(rebuilt.name, "pythontk")
        names = [c.name for mod in rebuilt.modules for c in mod.classes]
        self.assertIn("CoreUtils", names)

    def test_reconstructed_package_feeds_shadow_report(self):
        # A package reconstructed from JSON must collide like a walked one.
        walked = _pkg("mayatk", [_mod("m.py", [_cls("CoreUtils")])])
        from_json = PackageSurface.from_dict(
            asdict(_pkg("pythontk", [_mod("m.py", [_cls("CoreUtils")])]))
        )
        md = g.emit_shadow_report([walked, from_json])
        self.assertIn("CoreUtils", md)
        self.assertIn("pythontk", md)


class TestPropertyAccessorSkip(unittest.TestCase):
    """A property setter/deleter must not be emitted as a phantom member (it
    re-defines the property already emitted by its getter; recording it
    double-lists the property and mislabels the setter as a plain method)."""

    @staticmethod
    def _func(src: str):
        return ast.parse(src).body[0]

    def test_setter_is_accessor(self):
        self.assertTrue(
            ApiSurface._is_property_accessor(self._func("@x.setter\ndef x(self, v): ..."))
        )

    def test_deleter_is_accessor(self):
        self.assertTrue(
            ApiSurface._is_property_accessor(self._func("@x.deleter\ndef x(self): ..."))
        )

    def test_getter_is_not_accessor(self):
        self.assertFalse(
            ApiSurface._is_property_accessor(self._func("@property\ndef x(self): ..."))
        )

    def test_plain_method_is_not_accessor(self):
        self.assertFalse(ApiSurface._is_property_accessor(self._func("def x(self): ...")))

    def test_walk_module_emits_property_once(self):
        src = (
            "class C:\n"
            "    @property\n"
            "    def val(self): return self._v\n"
            "    @val.setter\n"
            "    def val(self, v): self._v = v\n"
            "    def plain(self): pass\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "m.py"
            f.write_text(src, encoding="utf-8")
            mod = ApiSurface._walk_module(f, root)
            members = {(m.name, m.kind) for m in mod.classes[0].members}
            self.assertIn(("val", "property"), members)
            self.assertIn(("plain", "method"), members)
            # the setter must NOT appear as a separate (phantom) member
            self.assertNotIn(("val", "method"), members)
            self.assertEqual(sum(1 for n, _ in members if n == "val"), 1)


class TestPrivateBaseMembersResolved(unittest.TestCase):
    """A public class must expose members it inherits from a PRIVATE base
    declared in the same module.

    The repo composes its public classes from private capability mixins
    (``Matrices(_MatrixMath, ...)``, ``TaskManager(_TaskChecksMixin, ...)``,
    ``PackageManager(_PackageManagerHelperMixin, ...)``). A private class is
    never emitted on its own, so before this ~100 genuinely public members
    across four packages were unfindable by a search — which defeats the
    "search before writing a helper" rule.
    """

    @staticmethod
    def _walk(src: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "m.py"
            f.write_text(src, encoding="utf-8")
            return ApiSurface._walk_module(f, root)

    def _members(self, src: str, cls_index: int = 0):
        mod = self._walk(src)
        return {(m.name, m.kind) for m in mod.classes[cls_index].members}

    def test_an_aliased_base_is_recorded_under_its_real_name(self):
        """``from pythontk import ShotSequencer as _Core`` then
        ``class ShotSequencer(_Core)``: recorded as ``_Core``, the hoisted
        members could never be matched to the sibling package's class, and every
        one of them read as a removal."""
        mod = self._walk(
            "from pythontk import ShotSequencer as _ShotSequencerCore\n"
            "from ._local import _Mixin as _Renamed\n"
            "class ShotSequencer(_ShotSequencerCore, _Renamed):\n"
            "    def own(self):\n"
            "        pass\n"
        )
        self.assertEqual(mod.classes[0].bases, ["pythontk.ShotSequencer", "_Renamed"])

    def test_a_module_alias_base_is_recorded_under_its_package(self):
        """``import pythontk as ptk`` + ``class X(ptk.SceneExporterBase)``: the
        base is recorded package-qualified, so the diff can tell pythontk's
        class from a same-named one in another sibling."""
        mod = self._walk(
            "import pythontk as ptk\n"
            "class SceneExporter(ptk.SceneExporterBase):\n"
            "    def own(self):\n"
            "        pass\n"
        )
        self.assertEqual(mod.classes[0].bases, ["pythontk.SceneExporterBase"])

    def test_private_base_members_are_pulled_up(self):
        members = self._members(
            "class _Mixin:\n"
            "    def helper(self): pass\n"
            "    @property\n"
            "    def prop(self): pass\n"
            "    def _hidden(self): pass\n"
            "class Public(_Mixin):\n"
            "    def own(self): pass\n"
        )
        self.assertIn(("own", "method"), members)
        self.assertIn(("helper", "method"), members)
        self.assertIn(("prop", "property"), members)
        # a private member of a private base stays private
        self.assertNotIn(("_hidden", "method"), {(n, k) for n, k in members})

    def test_public_base_members_are_not_duplicated(self):
        """A public base documents itself — pulling it up would duplicate."""
        mod = self._walk(
            "class Base:\n"
            "    def shared(self): pass\n"
            "class Derived(Base):\n"
            "    def own(self): pass\n"
        )
        derived = next(c for c in mod.classes if c.name == "Derived")
        self.assertNotIn("shared", {m.name for m in derived.members})

    def test_override_wins_over_private_base(self):
        """The class's own definition shadows the mixin's, and appears once."""
        members = self._members(
            "class _Mixin:\n"
            "    def dupe(self): pass\n"
            "class Public(_Mixin):\n"
            "    @staticmethod\n"
            "    def dupe(): pass\n"
        )
        self.assertIn(("dupe", "staticmethod"), members)
        self.assertEqual(sum(1 for n, _ in members if n == "dupe"), 1)

    def test_nested_private_bases_resolve(self):
        """A private base's own private base is walked too."""
        members = self._members(
            "class _Deep:\n"
            "    def deep(self): pass\n"
            "class _Mid(_Deep):\n"
            "    def mid(self): pass\n"
            "class Public(_Mid):\n"
            "    def own(self): pass\n"
        )
        self.assertEqual({"own", "mid", "deep"}, {n for n, _ in members})

    def test_self_referential_base_does_not_recurse(self):
        """A looping base graph must not crash the whole registry build.

        Python could never run ``class _A(_A)``, but this walker parses
        whatever is on disk (``_walk_module`` already swallows SyntaxError for
        half-written files) and an uncaught RecursionError would take the CI
        gate down over one bad file.
        """
        members = self._members(
            "class _A(_A):\n"
            "    def looped(self): pass\n"
            "class Public(_A):\n"
            "    def own(self): pass\n"
        )
        self.assertEqual({"own", "looped"}, {n for n, _ in members})

    def test_mutually_referential_bases_do_not_recurse(self):
        members = self._members(
            "class _A(_B):\n"
            "    def a(self): pass\n"
            "class _B(_A):\n"
            "    def b(self): pass\n"
            "class Public(_A):\n"
            "    def own(self): pass\n"
        )
        self.assertEqual({"own", "a", "b"}, {n for n, _ in members})

    def test_diamond_private_bases_emit_once(self):
        """A shared private base reached twice is traversed once."""
        members = self._members(
            "class _Base:\n"
            "    def shared(self): pass\n"
            "class _Left(_Base):\n"
            "    def left(self): pass\n"
            "class _Right(_Base):\n"
            "    def right(self): pass\n"
            "class Public(_Left, _Right):\n"
            "    def own(self): pass\n"
        )
        names = [n for n, _ in members]
        self.assertEqual({"own", "left", "right", "shared"}, set(names))
        self.assertEqual(names.count("shared"), 1)

    def test_cross_module_base_is_ignored(self):
        """An unresolvable base name must not crash or invent members."""
        members = self._members(
            "class Public(_NotInThisFile, ptk.HelpMixin):\n    def own(self): pass\n"
        )
        self.assertEqual({("own", "method")}, members)


class TestImportedPrivateBasesResolve(unittest.TestCase):
    """A public class resolves members from private mixins in SIBLING modules.

    The scene exporters split ``TaskManager(TaskFactory, _SceneTasksMixin, ...)``
    with each mixin in its own ``_task_*.py``; resolving same-file bases only
    read that split as 44 removed methods. The import walk is transitive, so the
    modules it reaches form a graph -- where two mixins sharing a base module is
    a diamond, not a cycle.
    """

    def setUp(self):
        # ASTs are cached per path for the whole run; never serve a fixture
        # another test's tree.
        ApiSurface._PARSED.clear()

    @staticmethod
    def _members(files: dict) -> set:
        with tempfile.TemporaryDirectory() as td:
            pkg = Path(td) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            for name, src in files.items():
                (pkg / name).write_text(src, encoding="utf-8")
            mod = ApiSurface._walk_module(pkg / "public.py", pkg)
            public = next(c for c in mod.classes if c.name == "Public")
            return {m.name for m in public.members}

    def test_a_diamond_resolves_the_shared_module_on_both_paths(self):
        """Two mixins importing their bases from one module both resolve.

        The walk kept ONE visited set for the whole traversal, so the shared
        module was skipped the second time it was reached -- as though it were a
        cycle -- and the second mixin's base stayed unresolved.
        """
        members = self._members(
            {
                "public.py": (
                    "from ._left import _LeftMixin\n"
                    "from ._right import _RightMixin\n"
                    "class Public(_LeftMixin, _RightMixin):\n"
                    "    def own(self): pass\n"
                ),
                "_left.py": (
                    "from ._shared import _LeftBase\n"
                    "class _LeftMixin(_LeftBase):\n"
                    "    def left(self): pass\n"
                ),
                # The absolute form of the same package-internal import.
                "_right.py": (
                    "from pkg._shared import _RightBase\n"
                    "class _RightMixin(_RightBase):\n"
                    "    def right(self): pass\n"
                ),
                "_shared.py": (
                    "class _LeftBase:\n"
                    "    def left_base(self): pass\n"
                    "class _RightBase:\n"
                    "    def right_base(self): pass\n"
                ),
            }
        )
        self.assertEqual({"own", "left", "left_base", "right", "right_base"}, members)

    def test_an_import_cycle_is_still_cut(self):
        """Only a module already on the current import path is skipped."""
        members = self._members(
            {
                "public.py": (
                    "from ._a import _AMixin\n"
                    "class Public(_AMixin):\n"
                    "    def own(self): pass\n"
                ),
                "_a.py": (
                    "from ._b import _BBase\n"
                    "class _AMixin(_BBase):\n"
                    "    def a(self): pass\n"
                ),
                "_b.py": (
                    "from ._a import _AMixin\nclass _BBase:\n    def b(self): pass\n"
                ),
            }
        )
        self.assertEqual({"own", "a", "b"}, members)


class TestSemverVerdict(unittest.TestCase):
    """What version a delta OWES, derived from the delta itself.

    The release cascade stepped a patch from PyPI whatever the change set
    said, so a removal could ship under a floor that resolves it as a bugfix
    -- measured 2026-09-19, when blendertk's removal of the public
    ``smart_bake=`` keyword would have shipped as 0.8.1 and was caught by
    hand. The generator already computed the removals AND documented the rule
    in its own comments ("a real removal still fires the alias-plus-minor-bump
    rule"); it simply never emitted the conclusion as data.
    """

    @staticmethod
    def _walk(root: Path, name: str, files: dict[str, str]):
        pkg = root / name
        src = pkg / name
        for rel, text in files.items():
            path = src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        ApiSurface._PARSED.clear()
        return g.walk_package(pkg, root)

    def _tree(self, before: dict[str, str], after: dict[str, str]):
        """``(data, prior)`` -- *after* walked, and *before* as its baseline
        mapping. Both walked for real, so the fixtures exercise the same path
        a release does."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            prior = self._walk(Path(td) / "a", "pkg", before).to_dict()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            data = self._walk(Path(td) / "b", "pkg", after)
        return data, prior

    def _delta(self, before: dict[str, str], after: dict[str, str]):
        """The delta from *before* to *after*."""
        return g.compute_api_delta(*self._tree(before, after))

    WIDGET_2 = '"""Mod."""\n\n\nclass Widget:\n    """W."""\n\n    def spin(self):\n        """S."""\n\n    def hop(self):\n        """H."""\n'
    WIDGET_1 = '"""Mod."""\n\n\nclass Widget:\n    """W."""\n\n    def hop(self):\n        """H."""\n'

    def test_a_removal_owes_a_minor_and_names_what_forces_it(self):
        delta = self._delta({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        bump, reasons = g.required_bump(delta)
        self.assertEqual(bump, "minor")
        self.assertEqual(reasons, ["mod.py::Widget.spin"])

    def test_an_addition_alone_is_a_patch(self):
        delta = self._delta({"mod.py": self.WIDGET_1}, {"mod.py": self.WIDGET_2})
        self.assertEqual(g.required_bump(delta), ("patch", []))

    def test_an_exec_template_is_not_contract(self):
        """A ``templates/`` module is read as source and run inside ANOTHER
        application, so nothing imports its names -- renaming one breaks no
        consumer. Without this, mayatk's 2026-09-19 delta (18 removed, 2 of
        them bridge templates) would force a minor for a template rename, and
        a guard that cries wolf gets bypassed on reflex."""
        fn2 = '"""T."""\n\n\ndef shots_section(bpy):\n    """S."""\n\n\ndef keep(bpy):\n    """K."""\n'
        fn1 = '"""T."""\n\n\ndef keep(bpy):\n    """K."""\n'
        delta = self._delta({"templates/_import.py": fn2}, {"templates/_import.py": fn1})
        self.assertIn("templates/_import.py::shots_section", delta.removed)
        self.assertEqual(
            g.required_bump(delta),
            ("patch", []),
            "a template removal is still REPORTED, it just owes nothing",
        )

    def test_no_baseline_owes_nothing(self):
        """A package with no release is not evidence of a break."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            data = self._walk(Path(td) / "p", "pkg", {"mod.py": self.WIDGET_1})
        self.assertIsNone(g.compute_api_delta(data, None))
        self.assertEqual(g.required_bump(None), ("patch", []))

    def test_the_verdict_cannot_drift_from_the_document_that_explains_it(self):
        """Both come from one computation -- the point of extracting it. The
        rendered `## Removed (N)` and the delta must agree on N, or the
        release gate and the report would disagree about the same release."""
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        delta = g.compute_api_delta(data, prior)
        md = g.emit_changes_markdown(data, prior)
        self.assertIn(f"## Removed ({len(delta.removed)})", md)
        for key in delta.removed:
            self.assertIn(key, md)

    def test_an_unwalkable_package_has_no_verdict(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            verdict = g.semver_verdict("nope", Path(td))
        self.assertEqual(
            verdict,
            {
                "package": "nope",
                "bump": None,
                "reasons": [],
                "unaccounted": [],
                "baseline": "none (no package here)",
            },
        )

    MOVED = {"Widget.spin": ("tentacle.tools.spin.Spin.spin", "0.30.0")}

    def test_a_name_in_the_moved_table_moved_out_and_is_no_break(self):
        """A move gets no alias, so its removal is accounted for by the
        package's MOVED_NAMES entry; it still owes the minor."""
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        delta = g.compute_api_delta(data, prior, moved_table=self.MOVED)
        self.assertEqual(delta.removed, [])
        self.assertEqual(delta.moved_out, ["mod.py::Widget.spin"])
        self.assertEqual(g.required_bump(delta), ("minor", ["mod.py::Widget.spin"]))

    def test_a_whole_class_moved_out_takes_its_members(self):
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": '"""Mod."""\n'})
        delta = g.compute_api_delta(data, prior, moved_table={"Widget": ("tentacle.W", "0.30.0")})
        self.assertEqual(delta.removed, [])
        self.assertEqual(
            delta.moved_out,
            ["mod.py::Widget", "mod.py::Widget.hop", "mod.py::Widget.spin"],
        )

    def test_a_deprecated_alias_retires_and_a_plain_removal_is_a_break(self):
        deprecated = self.WIDGET_2.replace(
            "    def spin(self):",
            '    @Deprecation.symbol(replacement="hop", remove_in="1.0.0")\n    def spin(self):',
        )
        data, prior = self._tree({"mod.py": deprecated}, {"mod.py": self.WIDGET_1})
        delta = g.compute_api_delta(data, prior)
        self.assertEqual((delta.removed, delta.retired), ([], ["mod.py::Widget.spin"]))
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        self.assertEqual(g.compute_api_delta(data, prior).removed, ["mod.py::Widget.spin"])

    def test_the_moved_table_is_read_from_the_package_init(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            src = Path(td)
            (src / "__init__.py").write_text(
                'MOVED_NAMES = {"Spin": ("tentacle.Spin", "0.30.0")}\n', encoding="utf-8"
            )
            self.assertEqual(g.moved_names(src), {"Spin": ("tentacle.Spin", "0.30.0")})
            (src / "__init__.py").write_text("MOVED_NAMES = dict(build())\n", encoding="utf-8")
            self.assertEqual(g.moved_names(src), {})

    def test_the_changes_document_names_each_destination(self):
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        md = g.emit_changes_markdown(data, prior, moved_table=self.MOVED)
        self.assertIn("## Moved out (1)", md)
        self.assertIn(
            "- `mod.py::Widget.spin` → `tentacle.tools.spin.Spin.spin` (from 0.30.0)", md
        )
        self.assertNotIn("## Removed", md)


class TestReleaseBaseline(unittest.TestCase):
    """The delta is read against the package's last release: its newest ``v*``
    tag, read from a ``git archive`` copy of the tag's source -- never the
    working tree, which is what the delta is OF. A baseline that advanced with
    every run reported "no changes" and erased the recorded delta (4 of 5
    packages shipped an empty API_CHANGES on the 2026-08-10 release)."""

    WIDGET = '"""Mod."""\n\n\nclass Widget:\n    """W."""\n\n    def spin(self):\n        """S."""\n'
    GADGET = '\n\nclass Gadget:\n    """G."""\n'

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=test@test", "-c", "user.name=test", *args],
            check=True,
            capture_output=True,
        )

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def _write(self, name: str, files: dict) -> Path:
        pkg = self.root / name
        for rel, text in files.items():
            path = pkg / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        ApiSurface._PARSED.clear()
        return pkg

    def _release(self, name: str, files: dict, tag: str, repo: Path = None) -> Path:
        """*files* written into ``<root>/<name>/<name>/``, committed and tagged
        *tag* in *repo* (the package's own repo by default)."""
        pkg = self._write(name, files)
        repo = repo or pkg
        if not (repo / ".git").exists():
            self._git(repo, "init")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "--allow-empty", "-m", tag)
        self._git(repo, "tag", tag)
        return pkg

    def _quiet(self, fn, *args, **kwargs):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            return fn(*args, **kwargs), err.getvalue()

    def test_a_change_since_the_tag_is_reported_against_it_run_after_run(self):
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        self._write("pkga", {"mod.py": self.WIDGET + self.GADGET})
        for run in (1, 2):  # nothing a run does moves the baseline
            md = g.changes_report("pkga", self.root)
            self.assertIn("_Diff vs the last release (v0.1.0)._", md, f"run {run}")
            self.assertIn("## Added (1)", md, f"run {run}")
            self.assertIn("mod.py::Gadget", md, f"run {run}")

    def test_the_newest_release_by_version_is_the_baseline(self):
        """By version, not by name: ``v0.10.0`` is newer than ``v0.9.0``."""
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.9.0")
        self._release("pkga", {"mod.py": self.WIDGET + self.GADGET}, "v0.10.0")
        md = g.changes_report("pkga", self.root)
        self.assertIn("No public API changes since the last release (v0.10.0).", md)

    def test_since_names_another_baseline(self):
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.9.0")
        self._release("pkga", {"mod.py": self.WIDGET + self.GADGET}, "v0.10.0")
        md = g.changes_report("pkga", self.root, since="v0.9.0")
        self.assertIn("(v0.9.0)", md)
        self.assertIn("mod.py::Gadget", md)

    def test_a_since_naming_no_commit_is_no_baseline_never_an_older_one(self):
        """Measured by the review: with v0.2.0 missing from the checkout, a
        removal released in 0.2.0 shipped as a patch against v0.1.0. A ref the
        caller named and git cannot find is no verdict, said plainly."""
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        self._write("pkga", {"mod.py": '"""Mod."""\n'})
        verdict = g.semver_verdict("pkga", self.root, since="v0.2.0")
        self.assertIsNone(verdict["bump"])
        self.assertEqual(
            verdict["baseline"], "none (v0.2.0 names no commit in pkga: fetch its tags)"
        )
        md = g.changes_report("pkga", self.root, since="v0.2.0")
        self.assertIn("_No release to compare with: none (v0.2.0 names no commit", md)
        self.assertNotIn("v0.1.0", md)

    def test_semver_exits_2_with_no_verdict_and_says_why(self):
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        for argv, want in (
            (["pkga", "--semver"], 0),
            (["pkga", "--semver", "--since", "v0.2.0"], 2),
        ):
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(g, "REPO_ROOT", self.root):
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        rc = g.main(argv)
                self.assertEqual(rc, want, err.getvalue())
                verdict = json.loads(out.getvalue())[0]
                self.assertEqual(verdict["bump"] is None, want == 2)
                self.assertEqual("no verdict for pkga" in err.getvalue(), want == 2)

    def test_only_a_three_part_version_tag_is_a_release(self):
        """push.ps1 tags ``v<major>.<minor>.<patch>``; a two-part or a
        suffixed tag is someone else's and never the baseline."""
        pkg = self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        for tag in ("v0.2", "v0.3.0rc1", "v1"):
            self._git(pkg, "tag", tag)
        self.assertEqual(g.release_tag(pkg), "v0.1.0")

    def test_a_removal_since_the_tag_owes_a_minor_and_nothing_accounts_for_it(self):
        self._release("pkga", {"mod.py": self.WIDGET}, "v1.0.0")
        self._write("pkga", {"mod.py": '"""Mod."""\n\n\nclass Widget:\n    """W."""\n'})
        verdict = g.semver_verdict("pkga", self.root)
        self.assertEqual(
            verdict,
            {
                "package": "pkga",
                "bump": "minor",
                "reasons": ["mod.py::Widget.spin"],
                "unaccounted": ["mod.py::Widget.spin"],
                "baseline": "the last release (v1.0.0)",
            },
        )

    def test_no_release_tag_is_no_delta_and_no_verdict(self):
        for tagged in (False, True):
            with self.subTest(git_without_tags=tagged):
                pkg = self._write("pkga", {"mod.py": self.WIDGET})
                if tagged:  # a repo with history but no release tag
                    self._git(pkg, "init")
                    self._git(pkg, "add", "-A")
                    self._git(pkg, "commit", "-m", "work")
                verdict = g.semver_verdict("pkga", self.root)
                self.assertEqual((verdict["bump"], verdict["baseline"]), (None, "none (no release tag)"))
                md = g.changes_report("pkga", self.root)
                self.assertIn("_No release to compare with: none (no release tag)._", md)

    def test_the_tag_is_read_never_the_working_tree(self):
        pkg = self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        self._write("pkga", {"mod.py": self.WIDGET + self.GADGET, "new.py": '"""New."""\n'})
        surface = g.release_surface(pkg, "v0.1.0")
        self.assertEqual([m.relpath for m in surface.modules], ["mod.py"])
        self.assertEqual([c.name for c in surface.modules[0].classes], ["Widget"])
        self.assertEqual(surface.source_root, "pkga/pkga")

    def test_a_package_inside_a_larger_repo_reads_its_own_folder(self):
        """A test fixture or a monorepo holds the package below its git root:
        the archive's paths carry the prefix, the read does not."""
        self._git(self.root, "init")
        self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0", repo=self.root)
        surface = g.release_surface(self.root / "pkga", "v0.1.0")
        self.assertEqual(surface.source_root, "pkga/pkga")
        self.assertEqual([m.relpath for m in surface.modules], ["mod.py"])

    def test_the_release_copy_is_gone_after_the_read_even_a_failed_one(self):
        pkg = self._release("pkga", {"mod.py": self.WIDGET}, "v0.1.0")
        temp_root = self.root / "temp_root"
        temp_root.mkdir()
        with mock.patch.dict(os.environ, {"PYTHONTK_TEMP_ROOT": str(temp_root)}):
            self.assertIsNotNone(g.release_surface(pkg, "v0.1.0"))
            self.assertEqual(list(temp_root.rglob("*.py")), [])
            with mock.patch.object(g.ApiSurface, "read", side_effect=RuntimeError("read failed")):
                with self.assertRaises(RuntimeError):
                    g.release_surface(pkg, "v0.1.0")
        self.assertEqual(list(temp_root.rglob("*.py")), [])


class TestCheckGate(unittest.TestCase):
    """``--check`` end to end: source only -- nothing written, no git history,
    no generated file to go stale -- and a run that names its package must
    walk it (a typo or a wrong checkout path never reads green)."""

    SOURCE = (
        '"""Mod."""\n'
        "\n"
        "\n"
        "class Widget:\n"
        '    """A widget."""\n'
        "\n"
        "    def spin(self):\n"
        '        """Spin it."""\n'
    )

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def _make_pkg(self, name: str = "pythontk") -> Path:
        pkg = self.root / name
        (pkg / name).mkdir(parents=True)
        (pkg / name / "mod.py").write_text(self.SOURCE, encoding="utf-8")
        return pkg

    def _check(self, names: list) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = g.check(names, repo_root=self.root)
        return rc, out.getvalue() + err.getvalue()

    def test_a_clean_tree_passes_and_writes_nothing(self):
        self._make_pkg()
        before = sorted(self.root.rglob("*"))
        rc, text = self._check(["pythontk"])
        self.assertEqual(0, rc, text)
        self.assertIn("API retirements on time: pythontk.", text)
        self.assertEqual(before, sorted(self.root.rglob("*")))

    def test_the_gate_never_touches_git(self):
        """CI runs it in a shallow checkout with no tags."""
        self._make_pkg()
        with mock.patch.object(g, "_git_output", side_effect=AssertionError("git touched")):
            rc, text = self._check(["pythontk"])
        self.assertEqual(0, rc, text)

    def test_scoped_check_of_an_absent_package_fails(self):
        rc, text = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("Nothing to check", text)

    def test_scoped_check_of_a_package_without_a_source_root_fails(self):
        (self.root / "pythontk").mkdir()
        rc, text = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("Nothing to check", text)

    def test_full_sweep_tolerates_a_missing_sibling(self):
        """A checkout may lack a package; the unscoped sweep warns instead."""
        for name in g.ECOSYSTEM_PACKAGES:
            if name != "unitytk":
                self._make_pkg(name)
        rc, text = self._check(list(g.ECOSYSTEM_PACKAGES))
        self.assertEqual(0, rc, text)
        self.assertIn("unitytk", text)

    def test_a_mode_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                g.main(["pythontk"])

    def test_a_report_prints_through_a_cp1252_pipe(self):
        """A piped Windows console is cp1252, and a report quotes dashes and
        arrows: printing one crashed with UnicodeEncodeError."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_api_surface.py"), "pythontk", "--shadows"],
            capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("API Shadows", proc.stdout.decode("utf-8"))


def _member(owner: str, name: str) -> "SymbolRecord":
    return SymbolRecord(
        name=name,
        qualname=f"{owner}.{name}",
        kind="method",
        signature="(self)",
        summary="",
        line=1,
    )


class TestModuleReexports(unittest.TestCase):
    """What an OLD import path still serves, read off the source."""

    def test_a_module_promoted_to_a_package_serves_its_lazy_exports(self):
        """``rig_utils/tube_rig.py`` -> ``rig_utils/tube_rig/``: the import path
        is unchanged and the package ``__init__`` publishes the names through
        ``lazy_exports`` (CODE_STANDARD section 4), never a plain import."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            init = Path(td) / "rig_utils" / "tube_rig" / "__init__.py"
            init.parent.mkdir(parents=True)
            init.write_text(
                "from pythontk.core_utils.module_resolver import lazy_exports\n"
                "lazy_exports(\n"
                "    globals(),\n"
                '    {"_tube_rig": ("TubeRig",), "slots": ["RIG_MODES"], "one": "Single"},\n'
                ")\n",
                encoding="utf-8",
            )
            out = g.module_reexports(Path(td), ["rig_utils/tube_rig.py"])
        self.assertLessEqual(
            {"TubeRig", "RIG_MODES", "Single"}, out.get("rig_utils/tube_rig.py", set())
        )

    def test_a_deprecation_stub_does_not_hide_a_removal(self):
        """An aliased move is still the break CODE_STANDARD section 5 prices at a
        minor bump, and ``required_bump`` reads that off the Removed section: a
        stub's keys must stay Removed (the alias is listed as retirement debt
        beside them), in every ``<x>.Deprecation`` spelling. Counting them as
        served would let an aliased move ship as a patch."""
        files = {
            "stub.py": (
                "from pythontk.core_utils.deprecation import Deprecation\n"
                "Deprecation.attributes(\n"
                "    globals(),\n"
                '    {"SEND_TO": "pkg.new.SEND_TO", "AppSpec": "pkg.new.AppSpec"},\n'
                '    remove_in="0.13.0",\n'
                ")\n"
            ),
            "aliased.py": (
                "import pythontk as ptk\n"
                'ptk.Deprecation.attributes(globals(), {"CHANNELS": "pkg.X.CHANNELS"}, '
                'remove_in="0.13.0")\n'
            ),
            "private.py": (
                "import pythontk as _ptk\n"
                '_ptk.Deprecation.attributes(globals(), moved={"LEGACY": "pkg.X.L"}, '
                'remove_in="0.13.0")\n'
            ),
            "elsewhere.py": (
                "import sys\n"
                "from pythontk import Deprecation\n"
                'Deprecation.attributes(sys.modules["pkg.other"].__dict__, '
                '{"NOT_HERE": "pkg.X.Y"}, remove_in="0.13.0")\n'
            ),
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            for name, source in files.items():
                (Path(td) / name).write_text(source, encoding="utf-8")
            out = g.module_reexports(Path(td), list(files))
        served = set().union(*out.values()) if out else set()
        for name in ("SEND_TO", "AppSpec", "CHANNELS", "LEGACY", "NOT_HERE"):
            self.assertNotIn(name, served)


def _const(name: str) -> "SymbolRecord":
    return SymbolRecord(
        name=name, qualname=name, kind="constant", signature="", summary="", line=1
    )


class TestReexportedConstantIsMoved(unittest.TestCase):
    """A constant its old module still serves is not a removal."""

    def _prior(self, pkg):
        return json.loads(json.dumps(asdict(pkg)))

    def test_a_constant_the_module_still_serves_is_moved(self):
        relpath = "anim_utils/_anim_utils.py"
        before = _pkg("mayatk", [_mod(relpath, [])])
        before.modules[0].constants = [_const("TIED_KEYS_ATTR")]
        after = _pkg("mayatk", [_mod(relpath, [])])

        md = g.emit_changes_markdown(
            after, self._prior(before), reexports={relpath: {"TIED_KEYS_ATTR"}}
        )
        self.assertNotIn(
            "## Removed", md, f"a re-exported constant read as removed:\n{md}"
        )

    def test_a_constant_nothing_serves_is_still_removed(self):
        relpath = "anim_utils/_anim_utils.py"
        before = _pkg("mayatk", [_mod(relpath, [])])
        before.modules[0].constants = [_const("TIED_KEYS_ATTR")]
        after = _pkg("mayatk", [_mod(relpath, [])])

        md = g.emit_changes_markdown(after, self._prior(before), reexports={})
        self.assertIn("## Removed", md)


class TestHoistIsMovedNotRemoved(unittest.TestCase):
    """Hoisting a member onto a base must not read as a removal.

    The registry records a member at its DEFINING class, so moving one to a
    base changed its key and the diff called it removed even though the
    subclass still resolves it. Measured three times: 4 false entries in
    `blendertk/API_CHANGES.md` (2026-09-01) and 9 in `mayatk` (2026-09-08),
    every one still resolvable.

    The damage is not the noise. The repo's own rule turns a removal into
    alias-plus-minor-bump work, so a false positive either buys a deprecation
    cycle nobody owed or teaches reviewers that Removed is noise -- which is
    exactly how a REAL removal gets waved through.
    """

    def _prior(self, pkg):
        return json.loads(json.dumps(asdict(pkg)))

    def test_a_member_hoisted_to_a_base_is_reported_as_moved(self):
        sub = _cls("SubstanceBridgeSlots")
        sub.members = [_member("SubstanceBridgeSlots", "select_bake_source")]
        before = _pkg("blendertk", [_mod("mat_utils/slots.py", [sub])])

        base = _cls("BlenderBridgeSlotsBase")
        base.members = [_member("BlenderBridgeSlotsBase", "select_bake_source")]
        moved_sub = ClassSurface(
            name="SubstanceBridgeSlots",
            summary="",
            line=1,
            bases=["BlenderBridgeSlotsBase"],
            members=[],
        )
        after = _pkg(
            "blendertk",
            [
                _mod("mat_utils/bridge_slots_base.py", [base]),
                _mod("mat_utils/slots.py", [moved_sub]),
            ],
        )

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertNotIn("## Removed", md, f"a hoist was reported as a removal:\n{md}")
        self.assertIn("## Moved", md)
        self.assertIn("select_bake_source", md)

    def test_a_class_re_exported_from_another_module_is_moved_not_removed(self):
        """The 2026-09-08 shape: a module-level CLASS moved packages.

        `mayatk.PlayblastExporter`'s dataclasses were hoisted to pythontk and
        re-exported by name, and all three read as removed.
        """
        before = _pkg(
            "mayatk", [_mod("anim_utils/playblast.py", [_cls("ExportTarget")])]
        )
        after = _pkg("mayatk", [_mod("anim_utils/sequence.py", [_cls("ExportTarget")])])

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertNotIn(
            "## Removed", md, f"a re-export was reported as removed:\n{md}"
        )
        self.assertIn("## Moved", md)

    def test_a_REAL_removal_is_still_reported(self):
        """The guard must not forgive everything -- that is the whole risk."""
        gone = _cls("Slots")
        gone.members = [_member("Slots", "deleted_method")]
        before = _pkg("mayatk", [_mod("a.py", [gone])])
        after = _pkg("mayatk", [_mod("a.py", [_cls("Slots")])])

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn("## Removed", md, f"a real removal was swallowed:\n{md}")
        self.assertIn("deleted_method", md)

    def test_a_base_outside_the_package_does_not_forgive_its_members(self):
        """Only bases recorded in THIS package can resolve a member.

        An unresolvable base must leave the member in Removed rather than being
        silently forgiven, or a genuine deletion under a foreign base vanishes.
        """
        sub = _cls("Panel")
        sub.members = [_member("Panel", "on_show")]
        before = _pkg("mayatk", [_mod("a.py", [sub])])
        after_sub = ClassSurface(
            name="Panel", summary="", line=1, bases=["QtWidgets.QWidget"], members=[]
        )
        after = _pkg("mayatk", [_mod("a.py", [after_sub])])

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn("## Removed", md)
        self.assertIn("on_show", md)


class TestANamesakeDoesNotForgiveARemoval(unittest.TestCase):
    """A same-named class in ANOTHER module must not excuse a removal.

    Bases are recorded by simple name, so resolution has to match on simple
    name -- but ownership must not. `mayatk` and `blendertk` each carry five
    classes called `Parameters` (one per bridge: blender, unity, marmoset,
    substance, rizom) plus paired `Installer` / `OpRegistry` / `RpcPlugin` /
    `MainThreadMarshaller` across the two RPC plugin trees. Merging every
    namesake into one member set means deleting `affix_parts` from the
    substance bridge is forgiven by the blender bridge's copy, and a real
    removal is waved through -- the exact failure the Moved split exists to
    avoid making easier.
    """

    def _prior(self, pkg):
        return json.loads(json.dumps(asdict(pkg)))

    def _bridges(self, substance_members):
        """The real shape: five `Parameters`, only two of which share a member."""
        blender = _cls("Parameters")
        blender.members = [
            _member("Parameters", "affix_parts"),
            _member("Parameters", "defaults"),
        ]
        substance = _cls("Parameters")
        substance.members = [_member("Parameters", m) for m in substance_members]
        return [
            _mod("env_utils/blender_bridge/parameters.py", [blender]),
            _mod("mat_utils/substance_bridge/parameters.py", [substance]),
        ]

    def test_a_member_deleted_from_one_bridge_is_still_reported(self):
        before = _pkg("mayatk", self._bridges(["affix_parts", "defaults"]))
        after = _pkg("mayatk", self._bridges(["defaults"]))

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn(
            "## Removed",
            md,
            f"a namesake in another module forgave a real removal:\n{md}",
        )
        self.assertIn("mat_utils/substance_bridge/parameters.py", md)

    def test_a_class_deleted_while_namesakes_remain_is_still_reported(self):
        """The same hole one level up: the NAME surviving is not the class surviving."""
        before = _pkg("mayatk", self._bridges(["defaults"]))
        after = _pkg("mayatk", self._bridges(["defaults"])[:1])

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn(
            "## Removed",
            md,
            f"four surviving namesakes forgave a deleted class:\n{md}",
        )
        self.assertIn("mat_utils/substance_bridge/parameters.py::Parameters", md)

    def test_a_base_shared_by_two_rpc_trees_resolves_within_its_own_tree(self):
        """`_rpc_core.py` is duplicated per bridge; each must resolve locally.

        Both trees define `OpRegistry(_OpRegistryInternal)`. Hoisting a member
        onto the substance tree's base must be forgiven from the substance
        subclass -- and matching a base by bare name has to reach the copy in
        the same module, not an arbitrary one.
        """
        sub_path = "mat_utils/substance_bridge/.../plugin_src/_rpc_core.py"
        mar_path = "mat_utils/marmoset_bridge/.../plugin_src/_rpc_core.py"

        def tree(path, hoisted):
            base = _cls("_OpRegistryInternal")
            reg = ClassSurface(
                name="OpRegistry",
                summary="",
                line=1,
                bases=["_OpRegistryInternal"],
                members=[],
            )
            (base if hoisted else reg).members = [_member("OpRegistry", "describe")]
            if hoisted:
                base.members = [_member("_OpRegistryInternal", "describe")]
            return _mod(path, [base, reg])

        before = _pkg("mayatk", [tree(sub_path, False), tree(mar_path, False)])
        after = _pkg("mayatk", [tree(sub_path, True), tree(mar_path, False)])

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertNotIn(
            "## Removed", md, f"a hoist within one tree read as removed:\n{md}"
        )
        self.assertIn("## Moved", md)


class TestACrossPackageHoistIsMoved(unittest.TestCase):
    """The measured mayatk case: the base lives in ANOTHER ecosystem package.

    On 2026-09-08 the host-independent half of `PlayblastExporter` was hoisted
    to `pythontk.SequenceExporter` and all nine symbols read as removed. Every
    one is still reachable from the same import path -- four as inherited
    methods, and the three dataclasses because the module re-exports them by
    name (`from pythontk import CaptureResult, ExportResult, ExportTarget`).
    Resolving only within the package leaves this, the largest of the three
    measured instances, entirely unfixed.

    Both inputs are passed in rather than read off disk, so the diff of a fake
    package cannot reach the real registries.
    """

    def _prior(self, pkg):
        return json.loads(json.dumps(asdict(pkg)))

    def test_a_base_in_a_sibling_package_resolves_its_members(self):
        exporter = _cls("PlayblastExporter")
        exporter.members = [
            _member("PlayblastExporter", "export"),
            _member("PlayblastExporter", "capture_still"),
        ]
        before = _pkg("mayatk", [_mod("anim_utils/playblast_exporter.py", [exporter])])

        hoisted = ClassSurface(
            name="PlayblastExporter",
            summary="",
            line=1,
            bases=["ptk.SequenceExporter"],
            members=[_member("PlayblastExporter", "capture_still")],
        )
        after = _pkg("mayatk", [_mod("anim_utils/playblast_exporter.py", [hoisted])])

        md = g.emit_changes_markdown(
            after, self._prior(before), foreign_members={"SequenceExporter": {"export"}}
        )
        self.assertNotIn(
            "## Removed", md, f"a cross-package hoist read as a removal:\n{md}"
        )
        self.assertIn("## Moved", md)
        self.assertIn("PlayblastExporter.export", md)

    def test_a_same_named_sibling_package_base_resolves_its_members(self):
        """``class ShotSequencer(pythontk.ShotSequencer)``: the base's bare name
        is the subclass's own, so a same-module lookup found the class ITSELF,
        the cycle guard returned nothing, and every hoisted member still read as
        a removal."""
        seq = _cls("ShotSequencer")
        seq.members = [
            _member("ShotSequencer", "slide_shot"),
            _member("ShotSequencer", "move_content"),
        ]
        before = _pkg("mayatk", [_mod("anim_utils/_shot_sequencer.py", [seq])])

        hoisted = ClassSurface(
            name="ShotSequencer",
            summary="",
            line=1,
            bases=["pythontk.ShotSequencer"],
            members=[_member("ShotSequencer", "move_content")],
        )
        after = _pkg("mayatk", [_mod("anim_utils/_shot_sequencer.py", [hoisted])])

        md = g.emit_changes_markdown(
            after,
            self._prior(before),
            foreign_members={"ShotSequencer": {"slide_shot"}},
        )
        self.assertNotIn("## Removed", md, f"a same-named hoist read as removed:\n{md}")
        self.assertIn("ShotSequencer.slide_shot", md)

    def test_a_base_named_in_two_siblings_resolves_by_its_package(self):
        """``ShotSequencer`` is defined by pythontk AND by blendertk, so the bare
        name is ambiguous and dropped; the package-qualified base still resolves
        mayatk's hoisted members to pythontk's class."""
        seq = _cls("ShotSequencer")
        seq.members = [
            _member("ShotSequencer", "slide_shot"),
            _member("ShotSequencer", "move_content"),
        ]
        before = _pkg("mayatk", [_mod("anim_utils/_shot_sequencer.py", [seq])])
        hoisted = ClassSurface(
            name="ShotSequencer",
            summary="",
            line=1,
            bases=["pythontk.ShotSequencer"],
            members=[_member("ShotSequencer", "move_content")],
        )
        after = _pkg("mayatk", [_mod("anim_utils/_shot_sequencer.py", [hoisted])])

        md = g.emit_changes_markdown(
            after,
            self._prior(before),
            foreign_members={"pythontk.ShotSequencer": {"slide_shot"}},
        )
        self.assertNotIn("## Removed", md, f"a qualified hoist read as removed:\n{md}")

    def test_a_class_the_module_still_re_exports_is_moved(self):
        """`from pythontk import ExportTarget` keeps the old path importable."""
        relpath = "anim_utils/playblast_exporter.py"
        before = _pkg("mayatk", [_mod(relpath, [_cls("ExportTarget")])])
        after = _pkg("mayatk", [_mod(relpath, [])])

        md = g.emit_changes_markdown(
            after, self._prior(before), reexports={relpath: {"ExportTarget"}}
        )
        self.assertNotIn(
            "## Removed", md, f"a re-exported class read as a removal:\n{md}"
        )
        self.assertIn("## Moved", md)

    def test_a_member_of_a_re_exported_owner_resolves_in_the_sibling(self):
        """`CaptureResult.pattern`: the OWNER left, the member went with it.

        The class is re-exported so the old path still resolves, which means
        its members do too -- but they have to be looked up in the package that
        now defines the class, not in this one.
        """
        relpath = "anim_utils/playblast_exporter.py"
        owner = _cls("CaptureResult")
        owner.members = [_member("CaptureResult", "pattern")]
        before = _pkg("mayatk", [_mod(relpath, [owner])])
        after = _pkg("mayatk", [_mod(relpath, [])])

        md = g.emit_changes_markdown(
            after,
            self._prior(before),
            foreign_members={"CaptureResult": {"pattern"}},
            reexports={relpath: {"CaptureResult"}},
        )
        self.assertNotIn(
            "## Removed", md, f"a re-exported owner's member read as removed:\n{md}"
        )
        self.assertIn("CaptureResult.pattern", md)

    def test_a_re_exported_owner_that_moved_within_the_package_resolves_here(self):
        """``shot_sequencer_slots.py`` re-exports ``ShotSequencerController``,
        which now lives in ``shot_sequencer_controller.py`` of the SAME package
        and inherits ``tangent_from_handle`` from a sibling mixin. A sibling
        package defines a same-named controller without that member, so asking
        the foreign map alone read the hoist as a removal."""
        old = "anim_utils/shots/shot_sequencer/shot_sequencer_slots.py"
        ctrl = _cls("ShotSequencerController")
        ctrl.members = [_member("ShotSequencerController", "tangent_from_handle")]
        before = _pkg("mayatk", [_mod(old, [ctrl])])
        mixin = _cls("KeyMenuMixin")
        mixin.members = [_member("KeyMenuMixin", "tangent_from_handle")]
        moved = ClassSurface(
            name="ShotSequencerController",
            summary="",
            line=1,
            bases=["KeyMenuMixin"],
            members=[],
        )
        after = _pkg(
            "mayatk",
            [
                _mod(old, []),
                _mod("anim_utils/shots/shot_sequencer/key_menu.py", [mixin]),
                _mod(
                    "anim_utils/shots/shot_sequencer/shot_sequencer_controller.py",
                    [moved],
                ),
            ],
        )

        md = g.emit_changes_markdown(
            after,
            self._prior(before),
            foreign_members={"ShotSequencerController": {"place_dragged_handle"}},
            reexports={old: {"ShotSequencerController"}},
        )
        self.assertNotIn(
            "## Removed", md, f"an in-package hoist read as removed:\n{md}"
        )

    def test_an_unlisted_sibling_name_is_still_removed(self):
        """The foreign map is a whitelist, not a blanket pardon."""
        exporter = _cls("PlayblastExporter")
        exporter.members = [_member("PlayblastExporter", "deleted_method")]
        before = _pkg("mayatk", [_mod("a.py", [exporter])])
        after_cls = ClassSurface(
            name="PlayblastExporter",
            summary="",
            line=1,
            bases=["ptk.SequenceExporter"],
            members=[],
        )
        after = _pkg("mayatk", [_mod("a.py", [after_cls])])

        md = g.emit_changes_markdown(
            after, self._prior(before), foreign_members={"SequenceExporter": {"export"}}
        )
        self.assertIn("## Removed", md, f"a real removal was swallowed:\n{md}")
        self.assertIn("deleted_method", md)

    def test_a_re_export_in_a_DIFFERENT_module_does_not_forgive(self):
        """The old import path is what consumers hold -- another module is not it."""
        before = _pkg(
            "mayatk", [_mod("a.py", [_cls("ExportTarget")]), _mod("b.py", [])]
        )
        after = _pkg("mayatk", [_mod("a.py", []), _mod("b.py", [])])

        md = g.emit_changes_markdown(
            after, self._prior(before), reexports={"b.py": {"ExportTarget"}}
        )
        self.assertIn("## Removed", md, f"a foreign module's import forgave it:\n{md}")


class TestModuleConstantsAreTracked(unittest.TestCase):
    """A public module constant is public API and must diff like one.

    The release that removed `cli.DEFAULT_HOST` and `cli.DEFAULT_USER` read as
    purely ADDITIVE, because the walk collected classes and functions only. The
    repo's rule keys alias-plus-minor-bump work off exactly that diff, so a
    removal nothing reports is a removal nobody handles.
    """

    @staticmethod
    def _walk(src: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "m.py"
            f.write_text(src, encoding="utf-8")
            return ApiSurface._walk_module(f, root)

    def _prior(self, pkg):
        return json.loads(json.dumps(asdict(pkg)))

    def test_public_all_caps_are_collected_and_private_ones_are_not(self):
        mod = self._walk(
            "DEFAULT_HOST = 'localhost'\n"
            "DEFAULT_PORT: int = 4434\n"
            "_PRIVATE_CACHE = {}\n"
            "lowercase_default = 1\n"
            "class Keep:\n"
            "    INNER_CONSTANT = 2\n"
        )
        names = {c.name for c in mod.constants}
        self.assertEqual({"DEFAULT_HOST", "DEFAULT_PORT"}, names)

    def test_a_module_of_only_constants_is_still_recorded(self):
        """Previously such a module vanished entirely -- no funcs, no classes."""
        mod = self._walk("MAX_RETRIES = 3\n")
        self.assertIsNotNone(mod)
        self.assertEqual(["MAX_RETRIES"], [c.name for c in mod.constants])

    def _pkg_with(self, *names):
        mod = _mod("cli.py", [])
        mod.constants = [
            SymbolRecord(
                name=n, qualname=n, kind="constant", signature="", summary="", line=1
            )
            for n in names
        ]
        return _pkg("pythontk", [mod])

    def test_a_removed_constant_is_reported(self):
        before = self._pkg_with("DEFAULT_HOST", "DEFAULT_USER", "TIMEOUT")
        after = self._pkg_with("TIMEOUT")

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn("## Removed", md, f"a removed constant went unreported:\n{md}")
        self.assertIn("DEFAULT_HOST", md)
        self.assertIn("DEFAULT_USER", md)

    def test_a_new_constant_is_reported_once_the_baseline_tracks_them(self):
        before = self._pkg_with("TIMEOUT")
        after = self._pkg_with("TIMEOUT", "RETRIES")

        md = g.emit_changes_markdown(after, self._prior(before))
        self.assertIn("## Added", md)
        self.assertIn("RETRIES", md)

    def test_a_baseline_predating_the_field_does_not_report_653_additions(self):
        """The upgrade itself must not flood one release's diff.

        653 constants become visible across the seven packages the moment this
        lands. Reporting them all as Added would bury that release's real
        changes -- the same "teach reviewers to skim" failure this entry is
        about -- so a baseline with no `constants` recorded ANYWHERE is treated
        as predating the field, and only removals and signature changes are
        reported for that one diff.
        """
        after = self._pkg_with("TIMEOUT", "RETRIES")
        prior = self._prior(self._pkg_with("TIMEOUT"))
        for mod in prior["modules"]:  # a baseline read before constants existed
            mod.pop("constants", None)

        md = g.emit_changes_markdown(after, prior)
        self.assertNotIn("RETRIES", md, f"the upgrade flooded the diff:\n{md}")

    def test_a_pre_field_baseline_still_reports_class_changes_both_ways(self):
        """Suppression is scoped to added CONSTANTS, not to the whole diff.

        The risk it guards against is the opposite of the one it creates: an
        upgrade rule that quietly swallowed the release's genuine additions
        would be worse than the flood it prevents.
        """
        before = _pkg("pythontk", [_mod("cli.py", [_cls("Gone")])])
        after = _pkg("pythontk", [_mod("cli.py", [_cls("Fresh")])])
        prior = self._prior(before)
        for mod in prior["modules"]:
            mod.pop("constants", None)

        md = g.emit_changes_markdown(after, prior)
        self.assertIn("## Removed", md, f"suppression swallowed a class:\n{md}")
        self.assertIn("Gone", md)
        self.assertIn("## Added", md, f"suppression swallowed an addition:\n{md}")
        self.assertIn("Fresh", md)


class TestDeprecationRecognition(unittest.TestCase):
    """The static half of the deprecation clock: which decorators retire a
    symbol, and the removal version read off the call.

    The reader this replaces took only ``dec.id``/``dec.attr``, so it matched a
    bare ``@deprecated`` and nothing else -- while every deprecation in the
    ecosystem is written through a class namespace, because the encapsulation
    rule leaves no other spelling. Nothing in seven packages was ever marked.
    """

    def _walk(self, source: str) -> "ModuleSurface":
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pythontk"
            (pkg / "pythontk").mkdir(parents=True)
            (pkg / "pythontk" / "mod.py").write_text(source, encoding="utf-8")
            data = g.walk_package(pkg, root)
        return data.modules[0]

    def test_decorator_path_renders_the_dotted_spelling(self):
        for source, expected in (
            ("@deprecated\ndef f(): pass", "deprecated"),
            ("@Deprecation.symbol('x')\ndef f(): pass", "Deprecation.symbol"),
            ("@ptk.Deprecation.symbol('x')\ndef f(): pass", "ptk.Deprecation.symbol"),
        ):
            with self.subTest(source=source):
                node = ast.parse(source).body[0]
                self.assertEqual(ApiSurface._decorator_path(node.decorator_list[0]), expected)

    def test_symbol_decorator_marks_a_method_with_its_deadline(self):
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "\n"
            "    @classmethod\n"
            "    @Deprecation.symbol('Widget.spin', remove_in='0.11.0')\n"
            "    def whirl(cls):\n"
            '        """Old."""\n'
        )
        member = mod.classes[0].members[0]
        self.assertTrue(member.deprecated)
        self.assertEqual(member.remove_in, "0.11.0")
        self.assertEqual(member.kind, "classmethod")

    def test_a_namespaced_spelling_is_recognised(self):
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "@ptk.Deprecation.symbol('NewThing', remove_in='1.3.0')\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "1.3.0")

    def test_the_bare_legacy_marker_still_counts(self):
        """A symbol retired with PEP 702's own decorator reads the same, just
        without a deadline this walker can check."""
        mod = self._walk('"""Mod."""\n\n\n@deprecated\ndef old_fn():\n    """Old."""\n')
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "")

    def test_a_retired_parameter_does_not_retire_its_owner(self):
        """The method stays; only the keyword goes. Marking the owner would
        have the registry announce the removal of a live method -- the same
        false positive the Removed/Moved split exists to prevent."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "@Deprecation.parameter('old_kw', new='new_kw', remove_in='0.11.0')\n"
            "def live_fn(new_kw=None):\n"
            '    """Live."""\n'
        )
        self.assertFalse(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "")

    def test_a_retired_class_is_marked(self):
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "@Deprecation.symbol('NewThing', remove_in='0.11.0')\n"
            "class OldThing:\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.classes[0].deprecated)
        self.assertEqual(mod.classes[0].remove_in, "0.11.0")

    def test_a_live_class_is_not(self):
        mod = self._walk('"""Mod."""\n\n\nclass Live:\n    """Live."""\n')
        self.assertFalse(mod.classes[0].deprecated)

    def test_the_registry_row_states_the_deadline(self):
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "\n"
            "    @Deprecation.symbol('Widget.spin', remove_in='0.11.0')\n"
            "    def whirl(self):\n"
            '        """Old."""\n'
        )
        row = mod.classes[0].members[0].to_registry_row()
        self.assertIn("**DEPRECATED (remove in 0.11.0)**", row)


class TestSymbolRemoveInReadsTheSharedConstant(unittest.TestCase):
    """A ``remove_in`` handed as the module's shared constant is read, not lost.

    The DRY spelling a module with many retirements uses -- ``_REMOVE_IN =
    "0.18.0"`` once, then ``remove_in=_REMOVE_IN`` (or ``cls._REMOVE_IN``) on
    each -- is what mayatk's ``FbxUtils`` and ``DataNodes`` are written in.
    Reading only a literal recorded ``""`` for all of them, and a symbol with
    no ``remove_in`` can never expire (:func:`expired_deprecations`), so 23
    retirements across mayatk and blendertk were invisible to the very gate
    that exists to catch a retirement shipping past its window -- the failure
    that let blendertk's ``smart_bake=`` keyword ship two releases late.
    ``retired_forms`` already resolved the constant for retired KEYWORDS; the
    symbol walk did not.
    """

    def _walk(self, source: str, **siblings: str) -> "ModuleSurface":
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pythontk"
            (pkg / "pythontk").mkdir(parents=True)
            (pkg / "pythontk" / "mod.py").write_text(source, encoding="utf-8")
            for stem, text in siblings.items():
                (pkg / "pythontk" / f"{stem}.py").write_text(text, encoding="utf-8")
            ApiSurface._PARSED.clear()
            data = g.walk_package(pkg, root)
        return next(m for m in data.modules if m.relpath.endswith("mod.py"))

    def test_a_module_scope_constant_resolves(self):
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            '_REMOVE_IN = "0.18.0"\n'
            "\n"
            "\n"
            "@ptk.Deprecation.symbol('NewThing', remove_in=_REMOVE_IN)\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "0.18.0")

    def test_a_class_scope_constant_resolves(self):
        """The shape mayatk's ``DataNodes`` / ``FbxUtils`` are written in: the
        constant declared in the class body, named bare on each decorator just
        below it (a decorator cannot say ``cls.`` -- there is no ``cls`` in a
        class body; that spelling belongs to ``Deprecation.warn`` inside a
        method, which ``retired_forms`` reads)."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "\n"
            '    _REMOVE_IN = "0.18.0"\n'
            "\n"
            "    @classmethod\n"
            "    @ptk.Deprecation.symbol('Widget.spin', remove_in=_REMOVE_IN)\n"
            "    def whirl(cls):\n"
            '        """Old."""\n'
        )
        member = mod.classes[0].members[0]
        self.assertTrue(member.deprecated)
        self.assertEqual(member.remove_in, "0.18.0")
        self.assertEqual(member.kind, "classmethod")

    def test_an_owner_attribute_spelling_resolves(self):
        """``remove_in=Widget._REMOVE_IN`` on a module-scope symbol -- an
        attribute, and valid Python because the owner is already defined."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "\n"
            '    _REMOVE_IN = "0.18.0"\n'
            "\n"
            "\n"
            "@ptk.Deprecation.symbol('Widget.spin', remove_in=Widget._REMOVE_IN)\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "0.18.0")

    def test_the_resolved_deadline_reaches_the_expiry_gate(self):
        """The point of reading it: an overdue retirement spelled this way is
        now caught, where before it reported no deadline and passed."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            '_REMOVE_IN = "0.18.0"\n'
            "\n"
            "\n"
            "@ptk.Deprecation.symbol('NewThing', remove_in=_REMOVE_IN)\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        rows = [("mod.py", f.qualname, f.remove_in) for f in mod.functions]
        self.assertEqual(
            g._expired(rows, "0.18.0"),
            [("mod.py", "old_fn", "0.18.0")],
        )
        self.assertEqual(g._expired(rows, "0.17.9"), [])

    def test_an_ambiguous_name_stays_unreadable_rather_than_guessing(self):
        """Bound to two different strings in one module: report no deadline
        (today's behaviour) rather than pick one and print a wrong version."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            '_REMOVE_IN = "0.18.0"\n'
            '_REMOVE_IN = "0.19.0"\n'
            "\n"
            "\n"
            "@ptk.Deprecation.symbol('NewThing', remove_in=_REMOVE_IN)\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "")

    def test_a_private_base_keeps_its_own_module_deadline(self):
        """A member inherited from a private base in ANOTHER file is resolved
        against a map that includes that file's constants, so the base's own
        ``_REMOVE_IN`` is not silently read as the importer's."""
        mod = self._walk(
            '"""Mod."""\n'
            "\n"
            "from pythontk._base import _Mixin\n"
            "\n"
            "\n"
            "class Widget(_Mixin):\n"
            '    """A widget."""\n',
            _base=(
                '"""Base."""\n'
                "\n"
                '_BASE_REMOVE_IN = "0.20.0"\n'
                "\n"
                "\n"
                "class _Mixin:\n"
                '    """Mixin."""\n'
                "\n"
                "    @ptk.Deprecation.symbol('x', remove_in=_BASE_REMOVE_IN)\n"
                "    def whirl(self):\n"
                '        """Old."""\n'
            ),
        )
        member = next(m for m in mod.classes[0].members if m.name == "whirl")
        self.assertTrue(member.deprecated)
        self.assertEqual(member.remove_in, "0.20.0")


class TestTheStaticGateCountsTheCalendarWindow(unittest.TestCase):
    """The static gate judges a retirement by the runtime roster's own rule
    (``Deprecation.window_expired``, BACKLOG 2026-09-19): due once the version
    reaches ``remove_in`` AND the notice's ``since`` is
    ``Deprecation.MIN_WINDOW_DAYS`` old. Counted in versions alone, seven
    releases in two weeks retired names 15 days after their first warning --
    and a gate that kept the version rule would fail ``--check`` on a name the
    roster still holds."""

    def setUp(self):
        if not g._MIN_WINDOW_DAYS:
            self.skipTest("pythontk sibling predates the calendar window")
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def _write_pkg(self, version: str, decorator: str, name: str = "pythontk") -> Path:
        pkg = self.root / name
        (pkg / name).mkdir(parents=True, exist_ok=True)
        (pkg / name / "__init__.py").write_text(
            f'"""Root."""\n\n__version__ = "{version}"\n', encoding="utf-8"
        )
        (pkg / name / "mod.py").write_text(
            '"""Mod."""\n\n\nclass Widget:\n    """A widget."""\n\n'
            f"    {decorator}\n"
            "    def whirl(self, **kwargs):\n"
            '        """Old."""\n',
            encoding="utf-8",
        )
        ApiSurface._PARSED.clear()
        return pkg

    def test_a_symbol_due_by_version_is_held_until_its_window_closes(self):
        pkg = self._write_pkg(
            "0.18.0",
            "@Deprecation.symbol('Widget.spin', remove_in='0.18.0', since='2026-09-04')",
        )
        rows = g.deprecations(g.walk_package(pkg, self.root))
        self.assertEqual(rows, [("mod.py", "Widget.whirl", "0.18.0", "2026-09-04")])
        self.assertEqual(g._expired(rows, "0.18.0", datetime.date(2026, 9, 19)), [])
        self.assertEqual(g._expired(rows, "0.18.0", datetime.date(2026, 10, 4)), rows)
        self.assertEqual(g._expired(rows, "0.17.9", datetime.date(2030, 1, 1)), [])

    def test_a_retired_keyword_reads_its_since_too(self):
        pkg = self._write_pkg(
            "0.18.0",
            "@Deprecation.parameter('old', remove_in='0.18.0', since='2026-09-04')",
        )
        rows = g.retired_forms(pkg, "pythontk")
        self.assertEqual([r[2:] for r in rows], [("0.18.0", "2026-09-04")])
        self.assertEqual(g._expired(rows, "0.18.0", datetime.date(2026, 9, 19)), [])

    def test_a_retired_class_attribute_is_read_by_the_gate_too(self):
        """``Deprecation.class_attribute`` (2026-10-19) is a retirement with a
        ``remove_in`` like the others; one the gate cannot see ships past its
        window, as blendertk's ``smart_bake=`` once did."""
        pkg = self._write_pkg(
            "0.18.0",
            "OLD = Deprecation.class_attribute({}, 'nothing', remove_in='0.18.0', "
            "since='2026-09-04')",
        )
        rows = g.retired_forms(pkg, "pythontk")
        self.assertEqual([r[2:] for r in rows], [("0.18.0", "2026-09-04")])
        self.assertEqual(g._expired(rows, "0.18.0", datetime.date(2026, 10, 4)), rows)

    def test_the_date_never_reaches_the_mapping(self):
        """Carried beside the record, not in it: a new field would change the
        shape every reader of the mapping shares, for a value only the gate reads."""
        pkg = self._write_pkg(
            "0.18.0",
            "@Deprecation.symbol('Widget.spin', remove_in='0.18.0', since='2026-09-04')",
        )
        member = g.walk_package(pkg, self.root).modules[0].classes[0].members[0]
        self.assertEqual(member.since, "2026-09-04")
        self.assertNotIn("since", asdict(member))

    def test_check_passes_a_held_name_and_fails_an_expired_one(self):
        """End to end through ``--check``: dates relative to today, so the
        verdicts never flip with the calendar."""
        today = datetime.date.today()
        cases = {
            today.isoformat(): (0, "**HELD**"),
            (today - datetime.timedelta(days=400)).isoformat(): (1, "**EXPIRED**"),
        }
        for since, (want_rc, mark) in cases.items():
            with self.subTest(since=since):
                self._write_pkg(
                    "0.18.0",
                    f"@Deprecation.symbol('Widget.spin', remove_in='0.18.0', "
                    f"since='{since}')",
                )
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = g.check(["pythontk"], repo_root=self.root)
                    changes = g.changes_report("pythontk", self.root)
                self.assertEqual(rc, want_rc, out.getvalue() + err.getvalue())
                self.assertIn(f"- {mark} `mod.py::Widget.whirl`", changes)

    def test_a_since_the_rule_refuses_is_judged_by_version_not_skipped(self):
        """A ``since`` the rule cannot read (the runtime refuses that notice at
        construction) degrades to the version rule. Skipped instead, its row
        could never be reported, however far past ``remove_in`` the version
        moved -- and a body-level ``Deprecation.warn`` only meets the runtime
        check when its branch runs."""
        rows = [("mod.py", "Widget.whirl", "0.18.0", "2026-9-4")]
        late = datetime.date(2030, 1, 1)
        self.assertEqual(g._expired(rows, "0.18.0", late), rows)
        self.assertEqual(g._expired(rows, "0.17.9", late), [])

    def test_a_retirement_naming_no_since_is_said_on_stderr(self):
        """pythontk's own suite requires ``since``; for every other package the
        walk is the one place an undated notice -- judged by version alone, the
        rule that retired names 15 days after their first warning -- is named.
        Advisory only: the version half of the gate still holds it."""
        for decorator, named in (
            ("@Deprecation.symbol('Widget.spin', remove_in='0.18.0')", True),
            ("@Deprecation.parameter('old', remove_in='0.18.0')", True),
            (
                "@Deprecation.symbol('Widget.spin', remove_in='0.18.0', "
                "since='2026-09-04')",
                False,
            ),
        ):
            with self.subTest(decorator=decorator):
                self._write_pkg("0.17.0", decorator)
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(err):
                        g.check(["pythontk"], repo_root=self.root)
                said = err.getvalue()
                self.assertEqual("naming no since=" in said, named, said)
                if named:
                    self.assertIn("mod.py::", said)


class TestDeprecationExpiryGate(unittest.TestCase):
    """The one-release alias window, enforced instead of remembered.

    ``UvUtils.flip_uvs`` was deprecated on 2025-12-17 and shipped in 50
    releases afterwards. Nothing was broken: "removed in the next release" was
    a sentence, and no tool could compare a sentence to a version.
    """

    def setUp(self):
        # The gate is only ACTIVE when the pythontk sibling supplies
        # ``Deprecation.version_key``; without it the script deliberately
        # degrades to a stand-in that raises ValueError, so every deadline
        # reads as "cannot expire" and these expectations do not apply. That
        # is a routine state, not a broken one -- m3trik must reach main
        # BEFORE the packages land their side of a cross-repo change, so in
        # that window CI clones a pythontk with no deprecation.py. Skip, never
        # fail: the rest of this module needs no sibling at all.
        try:
            g._version_key("1.0.0")
        except ValueError:
            self.skipTest(
                "pythontk sibling predates core_utils/deprecation.py; the "
                "expiry gate is inactive (see _load_version_key)"
            )

        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def _make_pkg(self, version: str, remove_in: str, name: str = "pythontk") -> Path:
        pkg = self.root / name
        (pkg / name).mkdir(parents=True)
        (pkg / name / "__init__.py").write_text(
            f'"""Root."""\n\n__version__ = "{version}"\n', encoding="utf-8"
        )
        (pkg / name / "mod.py").write_text(
            '"""Mod."""\n'
            "\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "\n"
            f"    @Deprecation.symbol('Widget.spin', remove_in='{remove_in}')\n"
            "    def whirl(self):\n"
            '        """Old."""\n',
            encoding="utf-8",
        )
        return pkg

    def _run(self) -> tuple[int, str]:
        """The gate: ``(exit code, what it printed)``."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = g.check(["pythontk"], repo_root=self.root)
        return rc, out.getvalue() + err.getvalue()

    def _changes(self) -> str:
        """The ``--changes`` report."""
        with contextlib.redirect_stderr(io.StringIO()):
            return g.changes_report("pythontk", self.root)

    def _tag(self, pkg: Path, tag: str) -> None:
        """Release *pkg* as it stands: commit it and tag *tag*."""
        for args in (("init",), ("add", "-A"), ("commit", "-m", tag), ("tag", tag)):
            subprocess.run(
                ["git", "-C", str(pkg), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                check=True,
                capture_output=True,
            )

    def test_debt_is_reported_with_no_release_to_compare_with(self):
        """A package with no release has no delta, but the debt is a property
        of the tree rather than of the delta."""
        self._make_pkg("0.12.0", "0.11.0")
        changes = self._changes()
        self.assertIn("No release to compare with", changes)
        self.assertIn("- **EXPIRED** `mod.py::Widget.whirl`", changes)

    def test_package_version_is_read_without_importing(self):
        """The gate runs on a CI box where the package it walks is not
        installed and its dependencies are absent."""
        self._make_pkg("0.10.0", "0.11.0")
        self.assertEqual(
            g.package_version(self.root / "pythontk", "pythontk"), "0.10.0"
        )

    def test_an_annotated_version_is_read(self):
        """``__version__: str = "1.2.3"`` is valid Python and was invisible to
        the first regex, which silently left that package's window unchecked."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        (pkg / "pythontk" / "__init__.py").write_text(
            '"""Root."""\n\n__version__: str = "0.12.0"\n', encoding="utf-8"
        )
        self.assertEqual(g.package_version(pkg, "pythontk"), "0.12.0")

    def test_a_commented_out_version_is_not_read(self):
        pkg = self._make_pkg("0.10.0", "0.11.0")
        (pkg / "pythontk" / "__init__.py").write_text(
            '"""Root."""\n\n# __version__ = "9.9.9"\n', encoding="utf-8"
        )
        self.assertEqual(g.package_version(pkg, "pythontk"), "")

    def test_an_unreadable_version_says_the_window_is_unchecked(self):
        """A gate that passes because it compared against NOTHING is worse than
        no gate. Without a version nothing can expire, so the run must not read
        as a clean bill of health."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        (pkg / "pythontk" / "__init__.py").write_text('"""Root."""\n', encoding="utf-8")
        rc, text = self._run()
        self.assertEqual(0, rc)
        self.assertIn("UNCHECKED", text)
        self.assertIn("1 dated deprecation(s)", text)

    def test_a_package_with_no_dated_deprecations_is_quiet(self):
        """The warning is about unchecked DEBT, not about a missing version."""
        pkg = self.root / "pythontk"
        (pkg / "pythontk").mkdir(parents=True)
        (pkg / "pythontk" / "mod.py").write_text(
            '"""Mod."""\n\n\nclass Live:\n    """Live."""\n', encoding="utf-8"
        )
        rc, text = self._run()
        self.assertEqual(0, rc)
        self.assertNotIn("UNCHECKED", text)

    def test_a_missing_version_is_not_an_error(self):
        pkg = self.root / "nover"
        (pkg / "nover").mkdir(parents=True)
        self.assertEqual(g.package_version(pkg, "nover"), "")

    def test_a_future_deadline_passes(self):
        self._make_pkg("0.10.0", "0.11.0")
        rc, text = self._run()
        self.assertEqual(0, rc)
        self.assertNotIn("expired:", text)

    def test_a_reached_deadline_fails_the_check(self):
        self._make_pkg("0.11.0", "0.11.0")
        rc, text = self._run()
        self.assertEqual(1, rc)
        self.assertIn("Widget.whirl", text)
        self.assertIn("was due in 0.11.0", text)

    def test_a_passed_deadline_fails_the_check(self):
        self._make_pkg("0.12.0", "0.11.0")
        rc, _ = self._run()
        self.assertEqual(1, rc)

    def test_the_comparison_is_numeric_not_lexical(self):
        """``"0.9.40" > "0.10.0"`` as strings, and the reverse as releases."""
        self._make_pkg("0.9.40", "0.10.0")
        rc, _ = self._run()
        self.assertEqual(0, rc)

    def _add_retired_keyword(self, pkg: Path, remove_in: str) -> None:
        """A keyword retired through a helper that builds the decorator -- the
        shape of blendertk's ``_smart_bake_alias`` -- on a function that stays."""
        (pkg / "pythontk" / "kw.py").write_text(
            '"""Mod."""\n'
            "\n"
            "\n"
            "def _alias(func):\n"
            f"    return ptk.Deprecation.parameter('old', new='new', remove_in='{remove_in}')(func)\n"
            "\n"
            "\n"
            "@_alias\n"
            "def live(new=None):\n"
            '    """Live."""\n',
            encoding="utf-8",
        )

    def test_an_expired_retired_keyword_fails_the_check(self):
        """``Deprecation.parameter`` / ``values`` / ``warn`` / ``attributes``
        retire something smaller than a symbol, so the registry marks no symbol
        for them -- but their ``remove_in`` is the same promise, and blendertk's
        ``smart_bake=`` (``remove_in="0.7.0"``) shipped in 0.8.0 because the
        gate read decorators on symbols only."""
        pkg = self._make_pkg("0.12.0", "0.13.0")  # its symbol is not yet due
        self._add_retired_keyword(pkg, "0.12.0")
        rc, text = self._run()
        self.assertEqual(1, rc)
        self.assertIn("kw.py::Deprecation.parameter('old')", text)
        self.assertIn("was due in 0.12.0", text)

    def test_a_live_retired_keyword_passes(self):
        pkg = self._make_pkg("0.12.0", "0.13.0")
        self._add_retired_keyword(pkg, "0.13.0")
        rc, text = self._run()
        self.assertEqual(0, rc, text)

    def test_a_remove_in_bound_to_a_module_constant_still_expires(self):
        """The DRY form -- mayatk's `remove_in=cls._REMOVE_IN` -- is one
        string bound once in the module, so the gate reads it as the literal
        it stands for; the same retirement written twice counts once."""
        pkg = self._make_pkg("0.12.0", "0.13.0")
        (pkg / "pythontk" / "kw.py").write_text(
            '"""Mod."""\n\n_REMOVE_IN = "0.12.0"\n\n\n'
            "class Owner:\n"
            "    _REMOVE_IN = _REMOVE_IN\n\n"
            "    @classmethod\n"
            "    def go(cls, old=None):\n"
            "        ptk.Deprecation.warn('Owner.go(old=)', 'new=', remove_in=cls._REMOVE_IN)\n"
            "        ptk.Deprecation.warn('Owner.go(old=)', 'new=', remove_in=_REMOVE_IN)\n",
            encoding="utf-8",
        )
        rc, text = self._run()
        self.assertEqual(1, rc)
        overdue = "expired: pythontk/kw.py::Deprecation.warn('Owner.go(old=)')"
        self.assertEqual(1, text.count(overdue), text)
        self.assertIn("was due in 0.12.0", text)

    def test_an_unreadable_remove_in_warns_instead_of_passing_silently(self):
        """A `remove_in` this walk cannot read (a helper's result) is named as
        UNCHECKED on stderr -- never a clean bill of health it did not earn."""
        pkg = self._make_pkg("0.12.0", "0.13.0")
        (pkg / "pythontk" / "kw.py").write_text(
            '"""Mod."""\n\n\ndef _when():\n    return "0.12.0"\n\n\n'
            "def go(old=None):\n"
            "    ptk.Deprecation.warn('go(old=)', 'new=', remove_in=_when())\n",
            encoding="utf-8",
        )
        rc, text = self._run()
        self.assertEqual(0, rc, text)
        self.assertIn("UNCHECKED", text)
        self.assertIn("Deprecation.warn('go(old=)')", text)

    def test_the_report_marks_an_overdue_alias_without_failing(self):
        """``--changes`` explains; only ``--check`` fails, in CI, where the red
        gate reaches someone who can delete the alias."""
        self._make_pkg("0.12.0", "0.11.0")
        self.assertIn("- **EXPIRED** `mod.py::Widget.whirl`", self._changes())
        rc, text = self._run()
        self.assertEqual(1, rc)
        self.assertIn("expired:", text)

    def test_the_report_lists_the_debt_and_marks_the_overdue(self):
        pkg = self._make_pkg("0.12.0", "0.11.0")
        self._tag(pkg, "v0.12.0")  # a release to compare with
        changes = self._changes()
        self.assertIn("## Deprecations (1)", changes)
        self.assertIn("- **EXPIRED** `mod.py::Widget.whirl`", changes)

    def test_debt_is_listed_even_when_nothing_else_changed(self):
        """An alias runs out of time during a release that touched nothing
        near it, so the section cannot sit behind the has-changes guard."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        self._tag(pkg, "v0.10.0")  # released as it stands: no surface delta
        changes = self._changes()
        self.assertIn("No public API changes", changes)
        self.assertIn("## Deprecations (1)", changes)
        # The legend names EXPIRED whether or not anything is; only a ROW
        # carrying the marker means a deadline has actually passed.
        self.assertIn("- `mod.py::Widget.whirl`", changes)
        self.assertNotIn("- **EXPIRED**", changes)

    def test_the_mapping_does_not_grow_a_key_for_live_symbols(self):
        """``asdict`` would write ``"remove_in": ""`` against every symbol in
        the ecosystem: tens of thousands of keys saying nothing, in every read
        kept in the cache and every release read."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        (pkg / "pythontk" / "live.py").write_text(
            '"""Live."""\n\n\nclass Live:\n    """Live."""\n\n'
            "    def go(self):\n"
            '        """Go."""\n',
            encoding="utf-8",
        )
        ApiSurface._PARSED.clear()
        mapping = g.walk_package(pkg, self.root).to_dict()
        rows = {
            member["qualname"]: member
            for mod in mapping["modules"]
            for cls in mod["classes"]
            for member in cls["members"]
        }
        self.assertNotIn("remove_in", rows["Live.go"])
        self.assertEqual(rows["Widget.whirl"]["remove_in"], "0.11.0")

    def test_a_mapping_round_trips(self):
        pkg = self._make_pkg("0.10.0", "0.11.0")
        ApiSurface._PARSED.clear()
        mapping = json.loads(json.dumps(g.walk_package(pkg, self.root).to_dict()))
        rebuilt = PackageSurface.from_dict(mapping)
        member = rebuilt.modules[0].classes[0].members[0]
        self.assertTrue(member.deprecated)
        self.assertEqual(member.remove_in, "0.11.0")


if __name__ == "__main__":
    unittest.main()
