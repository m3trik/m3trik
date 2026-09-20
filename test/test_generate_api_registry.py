"""Tests for generate_api_registry.py — the shadow-report parity bucketing and
JSON reconstruction added in the context-budget pass, and the ``--check``
staleness gate each ecosystem package's CI now runs per package
(``StalenessGate`` + the end-to-end fixture-tree cases at the bottom)."""

import ast
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_api_registry as g  # noqa: E402


def _cls(name: str) -> "g.ClassEntry":
    return g.ClassEntry(name=name, summary="", line=1, bases=["object"], members=[])


def _mod(relpath: str, classes: list) -> "g.ModuleEntry":
    return g.ModuleEntry(relpath=relpath, summary="", functions=[], classes=classes)


def _pkg(name: str, modules: list) -> "g.PackageData":
    return g.PackageData(name=name, source_root=f"{name}/{name}", modules=modules)


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
        rebuilt = g._package_data_from_json(asdict(pkg))
        self.assertEqual(rebuilt.name, "pythontk")
        names = [c.name for mod in rebuilt.modules for c in mod.classes]
        self.assertIn("CoreUtils", names)

    def test_reconstructed_package_feeds_shadow_report(self):
        # A package reconstructed from JSON must collide like a walked one.
        walked = _pkg("mayatk", [_mod("m.py", [_cls("CoreUtils")])])
        from_json = g._package_data_from_json(
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
            g._is_property_accessor(self._func("@x.setter\ndef x(self, v): ..."))
        )

    def test_deleter_is_accessor(self):
        self.assertTrue(
            g._is_property_accessor(self._func("@x.deleter\ndef x(self): ..."))
        )

    def test_getter_is_not_accessor(self):
        self.assertFalse(
            g._is_property_accessor(self._func("@property\ndef x(self): ..."))
        )

    def test_plain_method_is_not_accessor(self):
        self.assertFalse(g._is_property_accessor(self._func("def x(self): ...")))

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
            mod = g._walk_module(f, root)
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
    across four packages were unfindable in ``API_INDEX.md`` — which defeats
    the "grep the registry before writing a helper" rule.
    """

    @staticmethod
    def _walk(src: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "m.py"
            f.write_text(src, encoding="utf-8")
            return g._walk_module(f, root)

    def _members(self, src: str, cls_index: int = 0):
        mod = self._walk(src)
        return {(m.name, m.kind) for m in mod.classes[cls_index].members}

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
        g._PARSED.clear()

    @staticmethod
    def _members(files: dict) -> set:
        with tempfile.TemporaryDirectory() as td:
            pkg = Path(td) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            for name, src in files.items():
                (pkg / name).write_text(src, encoding="utf-8")
            mod = g._walk_module(pkg / "public.py", pkg)
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
        g._PARSED.clear()
        return g.walk_package(pkg, root)

    def _tree(self, before: dict[str, str], after: dict[str, str]):
        """``(data, prior)`` -- *after* walked, and *before* as its baseline
        sidecar. Both walked for real, so the fixtures exercise the same path
        a release does."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            prior = g._to_jsonable(self._walk(Path(td) / "a", "pkg", before))
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
        """An initial registry is not evidence of a break."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            data = self._walk(Path(td) / "p", "pkg", {"mod.py": self.WIDGET_1})
        self.assertIsNone(g.compute_api_delta(data, None))
        self.assertEqual(g.required_bump(None), ("patch", []))

    def test_the_verdict_cannot_drift_from_the_document_that_explains_it(self):
        """Both come from one computation -- the point of extracting it. The
        rendered `## Removed (N)` and the delta must agree on N, or the
        release tool and the changelog would disagree about the same release."""
        data, prior = self._tree({"mod.py": self.WIDGET_2}, {"mod.py": self.WIDGET_1})
        delta = g.compute_api_delta(data, prior)
        md = g.emit_changes_markdown(data, prior)
        self.assertIn(f"## Removed ({len(delta.removed)})", md)
        for key in delta.removed:
            self.assertIn(key, md)

    def test_an_unwalkable_package_is_not_a_break(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            verdict = g.semver_verdict("nope", Path(td))
        self.assertEqual(verdict, {"package": "nope", "bump": "patch", "reasons": []})


class TestChangesBaseline(unittest.TestCase):
    """API_CHANGES.md must diff against the last RELEASE (origin/main), not
    the working-tree JSON the run is about to rewrite. The working-tree
    baseline advanced on every regeneration, so a second run in one session
    (or a subset run, or a release-time conflict resolution) reported "no
    changes" and silently erased the recorded delta — including 4 of 5
    packages shipping empty API_CHANGES on the 2026-08-10 release."""

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.email=test@test",
                "-c",
                "user.name=test",
                *args,
            ],
            check=True,
            capture_output=True,
        )

    @staticmethod
    def _make_pkg(root: Path, name: str) -> Path:
        pkg = root / name
        (pkg / name).mkdir(parents=True)
        (pkg / name / "mod.py").write_text(
            '"""Mod."""\n\n\nclass Widget:\n    def spin(self):\n        pass\n',
            encoding="utf-8",
        )
        return pkg

    def _commit_empty_baseline(self, pkg: Path) -> None:
        """Point origin/main at a sidecar that predates Widget."""
        baseline = {
            "name": pkg.name,
            "source_root": f"{pkg.name}/{pkg.name}",
            "modules": [],
        }
        (pkg / "API_REGISTRY.json").write_text(json.dumps(baseline), encoding="utf-8")
        self._git(pkg, "init")
        self._git(pkg, "add", "API_REGISTRY.json")
        self._git(pkg, "commit", "-m", "release baseline")
        self._git(pkg, "update-ref", "refs/remotes/origin/main", "HEAD")

    def test_repeated_and_multi_package_regens_keep_the_delta(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            for name in ("pkga", "pkgb"):
                self._commit_empty_baseline(self._make_pkg(root, name))
            for run in (1, 2):  # the second run must NOT absorb the delta
                g.regenerate(["pkga", "pkgb"], repo_root=root)
                for name in ("pkga", "pkgb"):
                    changes = (root / name / "API_CHANGES.md").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn(
                        "Added",
                        changes,
                        f"{name} run {run}: the delta was absorbed",
                    )
                    self.assertIn("Widget", changes)
                    self.assertIn("origin/main", changes)

    def test_no_git_falls_back_to_working_tree_sidecar(self):
        """Without a resolvable origin/main (fresh public clone, no remote)
        the pre-anchor behavior is preserved: diff vs the working-tree
        sidecar, labeled as such."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            self._make_pkg(root, "pkga")  # no git repo at all
            g.regenerate(["pkga"], repo_root=root)
            first = (root / "pkga" / "API_CHANGES.md").read_text(encoding="utf-8")
            self.assertIn("No prior baseline", first)
            g.regenerate(["pkga"], repo_root=root)
            second = (root / "pkga" / "API_CHANGES.md").read_text(encoding="utf-8")
            self.assertIn("No public API changes", second)
            self.assertIn("origin/main unresolvable", second)


class TestStalenessGate(unittest.TestCase):
    """The ``--check`` comparison itself.

    The gate is a CONTENT HASH of the two hand-read docs, never an mtime (a
    fresh CI checkout has no meaningful mtimes) and never the JSON sidecar
    (which records a line for every member, so one inserted import rewrites
    hundreds of numbers while the public surface is untouched)."""

    def test_generation_date_is_not_staleness(self):
        old = "# pkg\n\n_Generated: 2026-01-01_\n\n- `class Widget`\n"
        new = "# pkg\n\n_Generated: 2026-08-17_\n\n- `class Widget`\n"
        self.assertFalse(g.StalenessGate.is_stale(old, new))

    def test_a_registry_from_the_dated_generator_is_not_stale(self):
        """A registry written BEFORE the date was removed must still gate clean.

        The pre-2026-08-23 generator emitted the stamp between two blank
        lines. Filtering only the date LINE left such a file one blank line
        longer than anything the current generator writes, so every
        committed registry in the ecosystem read STALE the moment the stamp
        was dropped -- `API registry up to date` would have gone red on all
        seven packages' PRs at once, with no source change behind it.
        Caught against a real committed registry in a clean worktree.
        """
        dated = "# pkg\n\n_Generated: 2026-01-01_\n\n## Index\n\n- `class Widget`\n"
        undated = "# pkg\n\n## Index\n\n- `class Widget`\n"
        self.assertFalse(g.StalenessGate.is_stale(dated, undated))
        # ...and a real surface change is still caught through the same filter.
        moved = "# pkg\n\n## Index\n\n- `class Gadget`\n"
        self.assertTrue(g.StalenessGate.is_stale(dated, moved))

    def test_source_line_numbers_are_not_staleness(self):
        old = "- [`class Widget(object)`](pkg/pkg/mod.py#L12) — spins.\n"
        new = "- [`class Widget(object)`](pkg/pkg/mod.py#L340) — spins.\n"
        self.assertFalse(g.StalenessGate.is_stale(old, new))

    def test_base_change_is_staleness(self):
        old = "- [`class Widget(object)`](pkg/pkg/mod.py#L12)\n"
        new = "- [`class Widget(Base)`](pkg/pkg/mod.py#L12)\n"
        self.assertTrue(g.StalenessGate.is_stale(old, new))

    def test_signature_change_is_staleness(self):
        self.assertTrue(
            g.StalenessGate.is_stale(
                "  - `Widget.spin(self)`\n", "  - `Widget.spin(self, n=1)`\n"
            )
        )

    def test_missing_artifact_is_staleness(self):
        self.assertTrue(g.StalenessGate.is_stale(None, "- `class Widget`\n"))

    def test_digest_is_a_hash(self):
        digest = g.StalenessGate.digest("- `class Widget`\n")
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertIsNone(g.StalenessGate.digest(None))

    def test_covers_ecosystem(self):
        self.assertTrue(g.StalenessGate.covers_ecosystem(g.ECOSYSTEM_PACKAGES))
        self.assertFalse(g.StalenessGate.covers_ecosystem(["pythontk"]))


class TestCheckGateOnFixtureTree(unittest.TestCase):
    """``--check`` end to end: a clean package tree passes, a genuinely stale
    one fails, and the churn classes that made the gate un-wireable (JSON
    line-number drift, a cross-package shadow report a per-package CI checkout
    cannot see) do not.

    Fixtures live in the system temp via ``TemporaryDirectory`` — the
    convention every m3trik test module already follows, and deliberately NOT
    the cloud-synced repo drive: these cases write an artifact and immediately
    hash it back, which is exactly the read-after-write that
    ``check_context_budget.check_registry_fresh`` had to add a retry for.
    """

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

    def _check(self, names: list[str]) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = g.regenerate(names, repo_root=self.root, check_only=True)
        return rc, err.getvalue()

    def _generate(self, names: list[str]) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            g.regenerate(names, repo_root=self.root)

    def test_clean_tree_passes(self):
        self._make_pkg()
        self._generate(["pythontk"])
        rc, _ = self._check(["pythontk"])
        self.assertEqual(0, rc)

    def test_regenerating_unchanged_source_is_byte_identical(self):
        """No clock in the outputs: a second run over the same tree writes
        nothing new. This is what keeps the registry bot, receipts and
        `git status` quiet on a day boundary -- before 2026-08-23 the JSON
        sidecar and API_CHANGES.md carried a generation date, so every first
        run of a UTC day was a 7-repo 'refresh' commit with no surface change."""
        pkg = self._make_pkg()
        # Run 1 bootstraps the baseline ("Initial registry"); run 2 is the
        # first steady-state output, which is what every real repo (always
        # holding an origin/main sidecar) produces. Runs 2 and 3 must match.
        self._generate(["pythontk"])
        self._generate(["pythontk"])
        names = (
            "API_INDEX.md",
            "API_REGISTRY.md",
            "API_REGISTRY.json",
            "API_CHANGES.md",
        )
        steady = {n: (pkg / n).read_bytes() for n in names}
        self._generate(["pythontk"])
        again = {n: (pkg / n).read_bytes() for n in names}
        self.assertEqual(steady, again)
        for n in names:
            self.assertNotIn(b"Generated", steady[n], n)

    def test_no_shadows_leaves_the_shadow_report_untouched(self):
        """A per-package release commit must not dirty m3trik's tree."""
        self._make_pkg()
        shadow = self.root / "m3trik" / "docs" / "API_SHADOWS.md"
        with contextlib.redirect_stdout(io.StringIO()):
            g.regenerate(["pythontk"], repo_root=self.root, shadows=False)
        self.assertFalse(shadow.exists())
        with contextlib.redirect_stdout(io.StringIO()):
            g.regenerate(["pythontk"], repo_root=self.root)
        self.assertTrue(shadow.exists())

    def test_added_public_class_is_stale(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        with (pkg / "pythontk" / "mod.py").open("a", encoding="utf-8") as fh:
            fh.write('\n\nclass Gadget:\n    """Undocumented in the registry."""\n')
        rc, err = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("API_INDEX.md", err)
        self.assertIn("API_REGISTRY.md", err)

    def test_removed_method_is_stale(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        (pkg / "pythontk" / "mod.py").write_text(
            '"""Mod."""\n\n\nclass Widget:\n    """A widget."""\n',
            encoding="utf-8",
        )
        rc, _ = self._check(["pythontk"])
        self.assertEqual(1, rc)

    def test_line_shift_alone_is_not_stale(self):
        """The regression this gate could not be wired without: an edit that
        moves every symbol down without touching the public surface."""
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        mod = pkg / "pythontk" / "mod.py"
        # Inserted AFTER the module docstring: nothing about the public surface
        # changes, every symbol below just moves down.
        mod.write_text(
            self.SOURCE.replace(
                '"""Mod."""\n',
                '"""Mod."""\n\n# a new comment block\nimport os  # noqa: F401\n',
                1,
            ),
            encoding="utf-8",
        )

        # Guard against a vacuous test: the committed artifacts really ARE
        # byte-different now (the #L deep links moved), so a plain equality
        # check would call this stale.
        fresh = g.emit_registry_markdown(g.walk_package(pkg, self.root))
        committed = (pkg / "API_REGISTRY.md").read_text(encoding="utf-8")
        self.assertNotEqual(fresh, committed)

        rc, err = self._check(["pythontk"])
        self.assertEqual(0, rc, err)

    def test_line_shifted_json_sidecar_alone_is_not_stale(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        sidecar = pkg / "API_REGISTRY.json"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        for mod in data["modules"]:
            for cls in mod["classes"]:
                cls["line"] += 7
                for member in cls["members"]:
                    member["line"] += 7
        sidecar.write_text(json.dumps(data, indent=2), encoding="utf-8")
        rc, err = self._check(["pythontk"])
        self.assertEqual(0, rc, err)

    def test_missing_index_is_stale(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        (pkg / "API_INDEX.md").unlink()
        rc, err = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("API_INDEX.md", err)

    def test_changes_narrative_is_not_gated(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        (pkg / "API_CHANGES.md").write_text("clobbered\n", encoding="utf-8")
        rc, err = self._check(["pythontk"])
        self.assertEqual(0, rc, err)

    def test_check_writes_nothing(self):
        pkg = self._make_pkg()
        self._generate(["pythontk"])
        (pkg / "pythontk" / "mod.py").write_text(
            '"""Mod."""\n\n\nclass Other:\n    """Different surface."""\n',
            encoding="utf-8",
        )
        before = {p.name: p.read_bytes() for p in pkg.glob("API_*") if p.is_file()}
        rc, _ = self._check(["pythontk"])
        self.assertEqual(1, rc)
        after = {p.name: p.read_bytes() for p in pkg.glob("API_*") if p.is_file()}
        self.assertEqual(before, after, "--check must not write")

    def test_check_does_not_shell_out_to_git(self):
        """The CI step runs in a shallow checkout with no origin/main, so the
        gate must not depend on the release-baseline lookup at all."""
        self._make_pkg()
        self._generate(["pythontk"])
        with mock.patch.object(
            g, "_baseline_registry_json", side_effect=AssertionError("git touched")
        ):
            rc, err = self._check(["pythontk"])
        self.assertEqual(0, rc, err)

    def test_single_package_check_ignores_the_shadow_report(self):
        """A per-package CI checkout holds one package plus m3trik, so the
        cross-package report it could compute is meaningless there."""
        self._make_pkg("pythontk")
        self._make_pkg("uitk")
        self._generate(["pythontk", "uitk"])
        shadow = self.root / "m3trik" / "docs" / "API_SHADOWS.md"
        self.assertTrue(shadow.exists())
        shadow.write_text("# clobbered\n", encoding="utf-8")
        rc, err = self._check(["pythontk"])
        self.assertEqual(0, rc, err)

    def test_scoped_check_of_an_absent_package_fails(self):
        """The CI step names its package; if the checkout put it somewhere
        else (or the name is a typo) the gate must not read green."""
        rc, err = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("Nothing to check", err)

    def test_scoped_check_of_a_package_without_a_source_root_fails(self):
        (self.root / "pythontk").mkdir()
        rc, err = self._check(["pythontk"])
        self.assertEqual(1, rc)
        self.assertIn("Nothing to check", err)

    def test_full_sweep_tolerates_a_missing_sibling(self):
        """refresh-api-registry.yml clones the siblings best-effort, so the
        unscoped sweep must warn rather than fail on one absent package."""
        present = [n for n in g.ECOSYSTEM_PACKAGES if n != "unitytk"]
        for name in present:
            self._make_pkg(name)
        self._generate(list(g.ECOSYSTEM_PACKAGES))
        rc, err = self._check(list(g.ECOSYSTEM_PACKAGES))
        self.assertEqual(0, rc, err)
        self.assertIn("unitytk", err)

    def test_full_ecosystem_check_still_gates_the_shadow_report(self):
        for name in g.ECOSYSTEM_PACKAGES:
            self._make_pkg(name)
        self._generate(list(g.ECOSYSTEM_PACKAGES))
        shadow = self.root / "m3trik" / "docs" / "API_SHADOWS.md"
        shadow.write_text("# clobbered\n", encoding="utf-8")
        rc, err = self._check(list(g.ECOSYSTEM_PACKAGES))
        self.assertEqual(1, rc)
        self.assertIn("API_SHADOWS.md", err)


def _member(owner: str, name: str) -> "g.SymbolRecord":
    return g.SymbolRecord(
        name=name,
        qualname=f"{owner}.{name}",
        kind="method",
        signature="(self)",
        summary="",
        line=1,
    )


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
        moved_sub = g.ClassEntry(
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
        after_sub = g.ClassEntry(
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
            reg = g.ClassEntry(
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

        hoisted = g.ClassEntry(
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

    def test_an_unlisted_sibling_name_is_still_removed(self):
        """The foreign map is a whitelist, not a blanket pardon."""
        exporter = _cls("PlayblastExporter")
        exporter.members = [_member("PlayblastExporter", "deleted_method")]
        before = _pkg("mayatk", [_mod("a.py", [exporter])])
        after_cls = g.ClassEntry(
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
            return g._walk_module(f, root)

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
            g.SymbolRecord(
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
        for mod in prior["modules"]:  # a sidecar written before constants existed
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

    def _walk(self, source: str) -> "g.ModuleEntry":
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
                self.assertEqual(g._decorator_path(node.decorator_list[0]), expected)

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
            "@ptk.Deprecation.symbol('NewThing', remove_in='1.2.3')\n"
            "def old_fn():\n"
            '    """Old."""\n'
        )
        self.assertTrue(mod.functions[0].deprecated)
        self.assertEqual(mod.functions[0].remove_in, "1.2.3")

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

    def _walk(self, source: str, **siblings: str) -> "g.ModuleEntry":
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pythontk"
            (pkg / "pythontk").mkdir(parents=True)
            (pkg / "pythontk" / "mod.py").write_text(source, encoding="utf-8")
            for stem, text in siblings.items():
                (pkg / "pythontk" / f"{stem}.py").write_text(text, encoding="utf-8")
            g._PARSED.clear()
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


class TestDeprecationExpiryGate(unittest.TestCase):
    """The one-release alias window, enforced instead of remembered.

    ``UvUtils.flip_uvs`` was deprecated on 2025-12-17 and shipped in 50
    releases afterwards. Nothing was broken: "removed in the next release" was
    a sentence, and no tool could compare a sentence to a version.
    """

    def setUp(self):
        # The gate is only ACTIVE when the pythontk sibling supplies
        # ``Deprecation.version_key``; without it the generator deliberately
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

    def _run(self, check_only: bool) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = g.regenerate(["pythontk"], repo_root=self.root, check_only=check_only)
        return rc, out.getvalue() + err.getvalue()

    def test_debt_is_reported_on_a_first_generation(self):
        """The first run has no baseline to diff, but the debt is a property of
        the tree rather than of the delta."""
        pkg = self._make_pkg("0.12.0", "0.11.0")
        self._run(check_only=False)
        changes = (pkg / "API_CHANGES.md").read_text(encoding="utf-8")
        self.assertIn("Initial registry", changes)
        self.assertIn("- **EXPIRED** `mod.py::Widget.whirl`", changes)

    def test_package_version_is_read_without_importing(self):
        """The generator runs on a CI box where the package it walks is not
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
        rc, text = self._run(check_only=False)
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
        rc, text = self._run(check_only=False)
        self.assertEqual(0, rc)
        self.assertNotIn("UNCHECKED", text)

    def test_a_missing_version_is_not_an_error(self):
        pkg = self.root / "nover"
        (pkg / "nover").mkdir(parents=True)
        self.assertEqual(g.package_version(pkg, "nover"), "")

    def test_a_future_deadline_passes(self):
        self._make_pkg("0.10.0", "0.11.0")
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
        self.assertEqual(0, rc)
        self.assertNotIn("expired:", text)

    def test_a_reached_deadline_fails_the_check(self):
        self._make_pkg("0.11.0", "0.11.0")
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
        self.assertEqual(1, rc)
        self.assertIn("Widget.whirl", text)
        self.assertIn("was due in 0.11.0", text)

    def test_a_passed_deadline_fails_the_check(self):
        self._make_pkg("0.12.0", "0.11.0")
        self._run(check_only=False)
        rc, _ = self._run(check_only=True)
        self.assertEqual(1, rc)

    def test_the_comparison_is_numeric_not_lexical(self):
        """``"0.9.40" > "0.10.0"`` as strings, and the reverse as releases."""
        self._make_pkg("0.9.40", "0.10.0")
        self._run(check_only=False)
        rc, _ = self._run(check_only=True)
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
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
        self.assertEqual(1, rc)
        self.assertIn("kw.py::Deprecation.parameter('old')", text)
        self.assertIn("was due in 0.12.0", text)

    def test_a_live_retired_keyword_passes(self):
        pkg = self._make_pkg("0.12.0", "0.13.0")
        self._add_retired_keyword(pkg, "0.13.0")
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
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
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
        self.assertEqual(1, rc)
        self.assertEqual(1, text.count("Deprecation.warn('Owner.go(old=)')"), text)
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
        self._run(check_only=False)
        rc, text = self._run(check_only=True)
        self.assertEqual(0, rc, text)
        self.assertIn("UNCHECKED", text)
        self.assertIn("Deprecation.warn('go(old=)')", text)

    def test_a_plain_regeneration_reports_but_does_not_fail(self):
        """The registry refresh bot runs the plain form; failing it would block
        the very commit that carries the report. CI is where the red gate
        reaches someone who can delete the alias."""
        self._make_pkg("0.12.0", "0.11.0")
        rc, text = self._run(check_only=False)
        self.assertEqual(0, rc)
        self.assertIn("expired:", text)

    def test_api_changes_lists_the_debt_and_marks_the_overdue(self):
        pkg = self._make_pkg("0.12.0", "0.11.0")
        self._run(check_only=False)
        self._run(check_only=False)  # second pass: a baseline now exists
        changes = (pkg / "API_CHANGES.md").read_text(encoding="utf-8")
        self.assertIn("## Deprecations (1)", changes)
        self.assertIn("- **EXPIRED** `mod.py::Widget.whirl`", changes)

    def test_debt_is_listed_even_when_nothing_else_changed(self):
        """An alias runs out of time during a release that touched nothing
        near it, so the section cannot sit behind the has-changes guard."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        self._run(check_only=False)
        self._run(check_only=False)  # second pass: no surface delta
        changes = (pkg / "API_CHANGES.md").read_text(encoding="utf-8")
        self.assertIn("No public API changes", changes)
        self.assertIn("## Deprecations (1)", changes)
        # The legend names EXPIRED whether or not anything is; only a ROW
        # carrying the marker means a deadline has actually passed.
        self.assertIn("- `mod.py::Widget.whirl`", changes)
        self.assertNotIn("- **EXPIRED**", changes)

    def test_the_sidecar_does_not_grow_a_key_for_live_symbols(self):
        """``asdict`` would write ``"remove_in": ""`` against every symbol in
        the ecosystem: tens of thousands of lines of committed machine file
        saying nothing, burying the surface change it shipped with."""
        pkg = self._make_pkg("0.10.0", "0.11.0")
        (pkg / "pythontk" / "live.py").write_text(
            '"""Live."""\n\n\nclass Live:\n    """Live."""\n\n'
            "    def go(self):\n"
            '        """Go."""\n',
            encoding="utf-8",
        )
        self._run(check_only=False)
        sidecar = json.loads((pkg / "API_REGISTRY.json").read_text(encoding="utf-8"))
        rows = {
            member["qualname"]: member
            for mod in sidecar["modules"]
            for cls in mod["classes"]
            for member in cls["members"]
        }
        self.assertNotIn("remove_in", rows["Live.go"])
        self.assertEqual(rows["Widget.whirl"]["remove_in"], "0.11.0")

    def test_a_reconstructed_sidecar_round_trips(self):
        pkg = self._make_pkg("0.10.0", "0.11.0")
        self._run(check_only=False)
        sidecar = json.loads((pkg / "API_REGISTRY.json").read_text(encoding="utf-8"))
        rebuilt = g._package_data_from_json(sidecar)
        member = rebuilt.modules[0].classes[0].members[0]
        self.assertTrue(member.deprecated)
        self.assertEqual(member.remove_in, "0.11.0")


if __name__ == "__main__":
    unittest.main()
