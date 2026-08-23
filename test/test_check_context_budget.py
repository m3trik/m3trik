"""Tests for check_context_budget.py — the context-budget guard.

A guard that cannot fail is worse than no guard. These verify it actually
CATCHES the regressions it exists to prevent (an over-cap / inconsistent
MEMORY.md) and passes a clean memory dir, plus that the live root dispatch table
still covers every ECOSYSTEM_PACKAGES member.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

M3TRIK_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = M3TRIK_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_context_budget as guard  # noqa: E402


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


class TestMemoryGuard(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _run(self) -> guard.Report:
        rep = guard.Report()
        guard.check_memory(self.dir, rep)
        return rep

    def test_clean_dir_passes(self):
        _write(self.dir, "reference_a.md", "a")
        _write(self.dir, "feedback_b.md", "b")
        _write(
            self.dir,
            "MEMORY.md",
            "# Memory Index\n\n- [A](reference_a.md) — hook a\n- [B](feedback_b.md) — hook b\n",
        )
        self.assertEqual(self._run().fails, [])

    def test_over_cap_fails(self):
        _write(self.dir, "reference_a.md", "a")
        pad = "x" * (guard.MEMORY_BYTE_CAP + 100)
        _write(
            self.dir,
            "MEMORY.md",
            f"# Memory Index\n\n- [A](reference_a.md) — hook\n<!-- {pad} -->\n",
        )
        self.assertTrue(
            any("cap" in f and "TRUNCATED" in f for f in self._run().fails),
            "an over-cap MEMORY.md must FAIL — that is the exact regression this guard exists for",
        )

    def test_over_long_entry_fails(self):
        _write(self.dir, "reference_a.md", "a")
        long_hook = "y" * (guard.MEMORY_ENTRY_CHAR_CAP + 50)
        _write(self.dir, "MEMORY.md", f"# Memory Index\n\n- [A](reference_a.md) — {long_hook}\n")
        self.assertTrue(any("chars >" in f for f in self._run().fails))

    def test_broken_link_fails(self):
        _write(self.dir, "reference_a.md", "a")
        _write(
            self.dir,
            "MEMORY.md",
            "# Memory Index\n\n- [A](reference_a.md) — ok\n- [X](does_not_exist.md) — broken\n",
        )
        self.assertTrue(any("missing files" in f for f in self._run().fails))

    def test_orphan_topic_fails(self):
        _write(self.dir, "reference_a.md", "a")
        _write(self.dir, "reference_orphan.md", "no index entry points here")
        _write(self.dir, "MEMORY.md", "# Memory Index\n\n- [A](reference_a.md) — ok\n")
        self.assertTrue(any("NO index entry" in f for f in self._run().fails))

    def test_hub_linked_topic_is_not_orphan(self):
        # An indexed HUB topic covers the sibling files its body links — a
        # cap-managed family costs MEMORY.md one entry (the live-pass pattern).
        _write(self.dir, "project_hub.md", "Hub.\n\n- [Child](project_child.md) — detail\n")
        _write(self.dir, "project_child.md", "child detail")
        _write(self.dir, "MEMORY.md", "# Memory Index\n\n- [Hub](project_hub.md) — family hub\n")
        self.assertEqual(self._run().fails, [])

    def test_hub_link_to_missing_file_fails(self):
        _write(self.dir, "project_hub.md", "Hub.\n\n- [Gone](project_gone.md) — dangling\n")
        _write(self.dir, "MEMORY.md", "# Memory Index\n\n- [Hub](project_hub.md) — family hub\n")
        self.assertTrue(any("hub link" in f for f in self._run().fails))

    def test_unindexed_hub_confers_no_coverage(self):
        # One level only: links in a topic that is NOT itself indexed cover nothing.
        _write(self.dir, "project_hub.md", "- [Child](project_child.md)\n")
        _write(self.dir, "project_child.md", "child")
        _write(self.dir, "MEMORY.md", "# Memory Index\n")
        fails = self._run().fails
        self.assertTrue(any("project_hub.md" in f and "un-recallable" in f for f in fails))
        self.assertTrue(any("project_child.md" in f for f in fails))

    def test_missing_memory_dir_warns_not_fails(self):
        rep = self._run()  # empty dir, no MEMORY.md
        self.assertEqual(rep.fails, [])
        self.assertTrue(any("not found" in w for w in rep.warns))


class TestLinkChecker(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_resolving_and_broken_links(self):
        (self.dir / "good.md").write_text("ok", encoding="utf-8")
        text = (
            "[a](good.md) [b](missing.md) [c](https://x.com) [d](#anchor) "
            "[e](good.md#L3) [f](sub/none.md)"
        )
        broken = guard._broken_links(text, self.dir)
        self.assertIn("missing.md", broken)
        self.assertIn("sub/none.md", broken)
        self.assertNotIn("good.md", broken)        # resolves
        self.assertNotIn("good.md#L3", broken)     # anchor stripped, file exists
        self.assertNotIn("https://x.com", broken)  # external skipped
        self.assertNotIn("#anchor", broken)        # pure anchor skipped


class TestLiveDispatch(unittest.TestCase):
    def test_dispatch_covers_ecosystem_packages(self):
        """The live root dispatch table must reference every ECOSYSTEM_PACKAGES
        member — the regression that misrouted blendertk work."""
        rep = guard.Report()
        guard.check_dispatch(rep)
        self.assertEqual([f for f in rep.fails if "DISPATCH" in f], [])


class TestClaudeAdvisoryCap(unittest.TestCase):
    def test_root_gets_the_larger_advisory_cap(self):
        """Root carries the ecosystem-wide one-line rules; a sub-repo file keeps
        the lean cap. Both stay under the hard cap."""
        self.assertEqual(guard._claude_advisory_cap(guard.REPO_ROOT / "CLAUDE.md"), guard.CLAUDE_WARN_ROOT)
        self.assertEqual(guard._claude_advisory_cap(guard.REPO_ROOT / "mayatk" / "CLAUDE.md"), guard.CLAUDE_WARN)
        self.assertGreater(guard.CLAUDE_WARN_ROOT, guard.CLAUDE_WARN)
        self.assertLess(guard.CLAUDE_WARN_ROOT, guard.CLAUDE_FAIL)


class TestNavDeps(unittest.TestCase):
    """The hand-written `**Deps**:` Nav segment must name every ecosystem package
    the pyproject declares - the drift the 2026-08 guideline audit found in four
    packages."""

    ECO = ("pythontk", "uitk", "mayatk")

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _pkg(self, deps, nav):
        _write(
            self.dir,
            "pyproject.toml",
            "[project]\nname = \"x\"\ndependencies = [\n" + "".join(f'    "{d}",\n' for d in deps) + "]\n",
        )
        _write(self.dir, "CLAUDE.md", f"# x\n\n**Nav**: {nav}\n")
        return self.dir

    def test_declared_dep_named_in_nav_passes(self):
        d = self._pkg(["pythontk>=1", "uitk"], "[← root](../CLAUDE.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md)")
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), [])

    def test_declared_dep_missing_from_nav_is_reported(self):
        d = self._pkg(["pythontk", "uitk"], "[← root](../CLAUDE.md) · **Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md)")
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), ["uitk"])

    def test_segment_stops_at_the_next_label(self):
        """A link after `**Used by**:` is not a dep - mayatk here is a consumer."""
        d = self._pkg(["pythontk", "mayatk"], "**Deps**: [pythontk](../pythontk/CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md)")
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), ["mayatk"])

    def test_extras_pins_and_third_party_are_normalised(self):
        d = self._pkg(["pythontk[mesh]>=0.9", "qtpy>=2.0", "UITK ~= 1.3"], "**Deps**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md)")
        self.assertEqual(guard._pyproject_ecosystem_deps(d / "pyproject.toml", self.ECO), ["pythontk", "uitk"])
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), [])

    def test_no_deps_segment_reports_every_declared_dep(self):
        d = self._pkg(["pythontk", "uitk"], "[← root](../CLAUDE.md) · **Used by**: [mayatk](../mayatk/CLAUDE.md)")
        self.assertIsNone(guard._nav_deps(d / "CLAUDE.md"))
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), ["pythontk", "uitk"])

    def test_package_without_ecosystem_deps_passes_without_a_nav(self):
        d = self._pkg(["qtpy"], "[← root](../CLAUDE.md)")
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), [])

    def test_link_text_is_free_the_path_names_the_package(self):
        """`[the Qt lib](../uitk/CLAUDE.md)` still counts as uitk."""
        d = self._pkg(["uitk"], "**Deps**: [the Qt lib](../uitk/CLAUDE.md) · **Used by**: [t](../tentacle/CLAUDE.md)")
        self.assertEqual(guard._nav_deps(d / "CLAUDE.md"), ["uitk"])
        self.assertEqual(guard._nav_deps_missing(d, self.ECO), [])


class TestLiveNavDeps(unittest.TestCase):
    def test_live_nav_deps_cover_declared_ecosystem_deps(self):
        """Every checked-out registry-set package's Nav Deps line must cover its
        pyproject's ecosystem dependencies."""
        rep = guard.Report()
        guard.check_nav_deps(rep)
        self.assertEqual([f for f in rep.fails if "NAVDEPS" in f], [])


class TestDefaultMemoryDir(unittest.TestCase):
    """The memory dir is DERIVED, never a hardcoded machine path.

    m3trik is public, so a maintainer's workspace layout must not ship in it;
    Claude names a project directory after the workspace path with the drive
    colon, separators and underscores folded to '-'.
    """

    def test_slug_folds_colon_separators_and_underscores(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path(r"o:\Cloud\Code\_scripts")):
                got = guard._default_memory_dir()
        self.assertEqual(got.parent.name, "o--Cloud-Code--scripts")
        self.assertEqual(got.name, "memory")

    def test_posix_style_root_slugs_identically(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path("o:/Cloud/Code/_scripts")):
                got = guard._default_memory_dir()
        self.assertEqual(got.parent.name.lower(), "o--cloud-code--scripts")

    def test_env_override_wins(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": r"C:\elsewhere\mem"}, clear=False):
            self.assertEqual(guard._default_memory_dir(), Path(r"C:\elsewhere\mem"))

    def test_module_ships_no_hardcoded_workspace_path(self):
        """Regression guard: the literal slug must not come back."""
        source = Path(guard.__file__).read_text(encoding="utf-8")
        self.assertNotIn(
            "o--Cloud-Code--scripts",
            source,
            "a machine-specific project slug is hardcoded in a public repo again",
        )


class TestPowerShellMemoryDirParity(unittest.TestCase):
    """The PowerShell wrapper must derive the SAME memory dir as the guard.

    `Invoke-ContextBudgetCheck.ps1` re-implements the slug rule for its near-cap
    early warning, and shipped it broken: in a .NET character class `\\/` is an
    identity-escaped forward slash, so `'[:\\/_]'` folds only `:`, `/` and `_` -
    the backslash survives, the derived path never resolves on Windows, and the
    whole `Test-Path $memFile` branch went silently dead while the Python twin
    resolved fine. Evaluate the SHIPPED expression, not a copy of it, so an edit
    to either implementation has to keep the two agreeing.
    """

    PS_GUARD = M3TRIK_DIR / "scripts" / "Invoke-ContextBudgetCheck.ps1"
    ROOT = r"O:\Cloud\Code\_scripts"

    def _shipped_slug_expression(self) -> str:
        m = re.search(
            r"^\s*\$slug\s*=.*$", self.PS_GUARD.read_text(encoding="utf-8"), re.M
        )
        self.assertIsNotNone(m, f"{self.PS_GUARD.name} no longer derives a $slug")
        return m.group(0).strip()

    def _python_slug(self) -> str:
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path(self.ROOT)):
                return guard._default_memory_dir().parent.name

    @unittest.skipUnless(sys.platform == "win32", "the PowerShell twin is Windows-only")
    def test_powershell_slug_matches_the_python_guard(self):
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$RepoRoot = '{self.ROOT}'; {self._shipped_slug_expression()}; "
                "Write-Output $slug",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        ps_slug = proc.stdout.strip()
        self.assertNotIn(
            "\\",
            ps_slug,
            "the derived project slug still carries a path separator — the memory "
            "file can never be found and the near-cap warning is dead",
        )
        self.assertEqual(ps_slug, self._python_slug())


class TestRefreshWorkflowStepOrder(unittest.TestCase):
    """The context-budget gate must run AFTER refresh-api-registry.yml's push.

    That job clones all seven ecosystem repos as siblings, so the guard judges
    hand-written docs (CLAUDE.md sizes, `**Deps**:` lines) in repos the
    job neither owns nor can fix — and `m3trik/scripts` reaches `main` before the
    packages land their half of any change, so a newly added cross-repo check is
    red by construction for the length of a cascade. In front of the push step
    that red blocks the shadow-report refresh this job exists to perform.

    Since 2026-08-23 the job pushes ONE file (the shadow report): per-package
    registries are written by push.ps1's Prepare phase inside each release
    commit, so the per-package push loop -- the only source of bot commits on
    the packages' dev branches -- is gone and must stay gone.
    """

    WORKFLOW = M3TRIK_DIR / ".github" / "workflows" / "refresh-api-registry.yml"
    PUSH_STEPS = ("Commit and push m3trik shadow report",)

    def test_bot_no_longer_writes_into_package_repos(self):
        text = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("Commit and push per-package registries", text)
        self.assertNotIn("chore: refresh API registry", text)

    def test_budget_gate_runs_after_every_push_step(self):
        text = self.WORKFLOW.read_text(encoding="utf-8")
        gate = text.index("run: python m3trik/scripts/check_context_budget.py")
        for step in self.PUSH_STEPS:
            self.assertLess(
                text.index(step),
                gate,
                f"the context-budget gate runs before '{step}' — a doc breach in any "
                "sibling repo would block the registry push this job exists to do",
            )


if __name__ == "__main__":
    unittest.main()
