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
        mayatk = _pkg("mayatk", [_mod("edit_utils/_edit_utils.py", [_cls("Bevel"), _cls("CoreUtils")])])
        blendertk = _pkg("blendertk", [_mod("edit_utils/_edit_utils.py", [_cls("Bevel")])])
        pythontk = _pkg("pythontk", [_mod("core_utils/_core_utils.py", [_cls("CoreUtils")])])

        md = g.emit_shadow_report([pythontk, mayatk, blendertk])
        self.assertIn("Intentional mayatk", md, "parity bucket header missing")
        genuine, parity = md.split("Intentional mayatk", 1)

        self.assertIn("CoreUtils", genuine, "genuine cross-layer collision should be in the top section")
        self.assertNotIn("Bevel", genuine, "intentional parity must NOT pollute the genuine section")
        self.assertIn("Bevel", parity, "mayatk<->blendertk parity should be bucketed separately")

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
        from_json = g._package_data_from_json(asdict(_pkg("pythontk", [_mod("m.py", [_cls("CoreUtils")])])))
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
        self.assertTrue(g._is_property_accessor(self._func("@x.setter\ndef x(self, v): ...")))

    def test_deleter_is_accessor(self):
        self.assertTrue(g._is_property_accessor(self._func("@x.deleter\ndef x(self): ...")))

    def test_getter_is_not_accessor(self):
        self.assertFalse(g._is_property_accessor(self._func("@property\ndef x(self): ...")))

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
        self.assertEqual(
            {"own", "mid", "deep"}, {n for n, _ in members}
        )

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
            "class Public(_NotInThisFile, ptk.HelpMixin):\n"
            "    def own(self): pass\n"
        )
        self.assertEqual({("own", "method")}, members)


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
                "git", "-C", str(repo),
                "-c", "user.email=test@test", "-c", "user.name=test",
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
        (pkg / "API_REGISTRY.json").write_text(
            json.dumps(baseline), encoding="utf-8"
        )
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
                        "Added", changes,
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
        before = {
            p.name: p.read_bytes() for p in pkg.glob("API_*") if p.is_file()
        }
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


if __name__ == "__main__":
    unittest.main()
