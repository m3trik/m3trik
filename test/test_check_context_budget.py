"""Tests for check_context_budget.py — the context-budget guard.

A guard that cannot fail is worse than no guard. These verify it actually
CATCHES the regressions it exists to prevent (an over-cap / inconsistent
MEMORY.md) and passes a clean memory dir, plus that the live root dispatch table
still covers every ECOSYSTEM_PACKAGES member.
"""

import io
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


class TestPipedConsole(unittest.TestCase):
    def test_a_report_prints_through_a_cp1252_pipe(self):
        """A piped Windows console is cp1252, and a broken link's FAIL line
        quotes an arrow (``a → b``): printing it crashed the guard."""
        report = guard.Report()
        report.fail("AGENTS link broken: unitytk/AGENTS.md → gone.md")
        out, err = io.BytesIO(), io.BytesIO()
        stdout = io.TextIOWrapper(out, encoding="cp1252")
        stderr = io.TextIOWrapper(err, encoding="cp1252")
        with patch.object(guard, "run_checks", return_value=report), patch.object(
            sys, "stdout", stdout
        ), patch.object(sys, "stderr", stderr):
            code = guard.main(["--no-runtime"])
            stdout.flush()
        self.assertEqual(code, 1)
        self.assertIn("unitytk/AGENTS.md → gone.md", out.getvalue().decode("utf-8"))


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

    def test_a_drifted_table_fails_where_it_is_written_and_where_it_is_rendered(self):
        """The table is held in the workspace rules' source (every checkout)
        and, where a workspace root exists, in its render too."""
        sync = guard._sync_workspace()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def fails(source_drift, render_drift):
                def answer(path=None):
                    return render_drift if path is not None else source_drift

                rep = guard.Report()
                with patch.object(guard, "REPO_ROOT", root), patch.object(sync, "dispatch_drift", answer):
                    guard.check_dispatch(rep)
                return rep.fails

            self.assertEqual(fails("source drifted", None), ["DISPATCH: source drifted"])
            self.assertEqual(fails(None, "render drifted"), [])  # no root here: none to ask
            (root / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
            self.assertEqual(fails(None, "render drifted"), ["DISPATCH: render drifted"])
            self.assertEqual(fails(None, None), [])


class TestClaudeAdvisoryCap(unittest.TestCase):
    def test_root_gets_the_larger_advisory_cap(self):
        """Root carries the ecosystem-wide one-line rules; a sub-repo file keeps
        the lean cap. Both stay under the hard cap."""
        self.assertEqual(guard._claude_advisory_cap(guard.REPO_ROOT / "AGENTS.md"), guard.CLAUDE_WARN_ROOT)
        self.assertEqual(guard._claude_advisory_cap(guard.REPO_ROOT / "mayatk" / "AGENTS.md"), guard.CLAUDE_WARN)
        self.assertGreater(guard.CLAUDE_WARN_ROOT, guard.CLAUDE_WARN)
        self.assertLess(guard.CLAUDE_WARN_ROOT, guard.CLAUDE_FAIL)

    def test_a_crlf_checkout_is_measured_as_its_blob(self):
        """Regression: with core.autocrlf the working copy gains a CR per line, so
        the local gate read m3trik/scripts/CLAUDE.md at 6,177 B (over the 6,144 B
        cap) while CI's LF checkout -- the blob -- read 6,138 B."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "CLAUDE.md"
            path.write_bytes(b"# t\r\n\r\nline\r\n")
            self.assertEqual(guard._blob_size(path), len(b"# t\n\nline\n"))


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
        """Every checked-out ecosystem-set package's Nav Deps line must cover its
        pyproject's ecosystem dependencies."""
        rep = guard.Report()
        guard.check_nav_deps(rep)
        self.assertEqual([f for f in rep.fails if "NAVDEPS" in f], [])


class TestLineBudget(unittest.TestCase):
    """The ecosystem's source lines against workspace.json's ``line_budget``:
    the guard reports the headroom, and the release gate refuses growth past
    it. Counted: non-blank lines of the .py files outside each repo's test/,
    a released package's as the release would commit them (tracked, or new
    and not ignored) and every other package's as committed."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        repo = self.root / "pythontk"
        (repo / "pythontk").mkdir(parents=True)
        (repo / "test").mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        _write(repo / "pythontk", "a.py", "x = 1\n\n\ny = 2\n")  # 2 counted
        _write(repo / "pythontk", "b.py", "z = 3\n")  # new, untracked: counted
        _write(repo / "test", "test_a.py", "t = 1\n" * 50)  # test/: never counted
        _write(repo, ".gitignore", "gen_ui.py\n")
        _write(repo / "pythontk", "gen_ui.py", "g = 1\n" * 50)  # ignored
        subprocess.run(["git", "-C", str(repo), "add", "pythontk/a.py", "test"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "a"],
            check=True,
        )

    def tearDown(self):
        self._td.cleanup()

    def _report(self, budget: int) -> guard.Report:
        rep = guard.Report()
        guard.check_line_budget(rep, self.root, budget=budget)
        return rep

    def test_only_the_released_source_lines_count(self):
        self.assertEqual(guard.source_lines(self.root), {"pythontk": 3})
        self.assertEqual(guard.source_lines(self.root, ["pythontk"]), {"pythontk": 3})

    def test_a_package_outside_the_release_counts_as_committed(self):
        """Another session's uncommitted file is not this release's growth."""
        self.assertEqual(guard.source_lines(self.root, ["uitk"]), {"pythontk": 2})

    def test_within_the_budget_reports_the_headroom(self):
        rep = self._report(10)
        self.assertEqual(rep.fails + rep.warns, [])
        self.assertIn("7 headroom", rep.oks[0])

    def test_past_the_budget_warns_and_the_gate_fails(self):
        rep = self._report(2)
        self.assertEqual(rep.fails, [])
        self.assertIn("over the line budget", rep.warns[0])
        with patch.object(guard, "_line_budget", return_value=2):
            self.assertEqual(
                guard.main(["--line-budget", "--workspace", str(self.root)]), 1
            )
            self.assertEqual(
                guard.main(["--line-budget", "--workspace", str(self.root), "pythontk"]), 1
            )
            self.assertEqual(
                guard.main(["--line-budget", "--workspace", str(self.root), "uitk"]), 0
            )

    def test_a_repo_git_cannot_read_fails_the_gate(self):
        """A broken checkout is not zero lines: the gate cannot answer, so it
        stops the run, as every other release gate does."""
        broken = self.root / "uitk"
        (broken / "uitk").mkdir(parents=True)
        _write(broken / "uitk", "big.py", "x = 1\n" * 1000)
        _write(broken, ".git", "gitdir: nowhere\n")
        with patch.object(guard, "_line_budget", return_value=100), \
                patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(
                guard.main(["--line-budget", "--workspace", str(self.root), "pythontk"]), 1
            )
            self.assertEqual(
                guard.main(["--line-budget", "--workspace", str(self.root), "uitk"]), 1
            )
        self.assertIn("cannot read", out.getvalue())

class TestDefaultMemoryDir(unittest.TestCase):
    """The memory dir is DERIVED, never a hardcoded machine path.

    m3trik is public, so a maintainer's workspace layout must not ship in it;
    Claude names a project directory after the workspace path with the drive
    colon, separators and underscores folded to '-'.
    """

    def test_slug_folds_colon_separators_and_underscores(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path(r"d:\Work\Code\_ws")):
                got = guard._default_memory_dir()
        self.assertEqual(got.parent.name, "d--Work-Code--ws")
        self.assertEqual(got.name, "memory")

    def test_posix_style_root_slugs_identically(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path("d:/Work/Code/_ws")):
                got = guard._default_memory_dir()
        self.assertEqual(got.parent.name.lower(), "d--work-code--ws")

    def test_every_non_alphanumeric_folds_like_claude_code(self):
        """Claude Code folds EVERY non-alphanumeric, so a Linux home with a dot
        or a space in it still lands on the real folder."""
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            with patch.object(guard, "REPO_ROOT", Path("/home/me/my.code dir/_scripts")):
                got = guard._default_memory_dir()
        self.assertEqual(got.parent.name, "-home-me-my-code-dir--scripts")

    def test_env_override_wins(self):
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": r"C:\elsewhere\mem"}, clear=False):
            self.assertEqual(guard._default_memory_dir(), Path(r"C:\elsewhere\mem"))

    def test_module_ships_no_hardcoded_workspace_path(self):
        """Regression guard: the literal slug must not come back. This
        workspace's own, derived here, never spelled in a public repo."""
        source = Path(guard.__file__).read_text(encoding="utf-8")
        with patch.dict(os.environ, {"CLAUDE_MEMORY_DIR": ""}, clear=False):
            slug = guard._default_memory_dir().parent.name
        self.assertNotIn(
            slug,
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
    ROOT = r"D:\Work\Code\_ws"

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


class TestRepoSideGuardInCi(unittest.TestCase):
    """The repo-side guard runs in m3trik's own CI over the seven siblings, and
    no workflow writes an API file: the surface is read live, so a bot pushing
    a refreshed registry into the packages' ``dev`` branches (the only source
    of commits no human made, which raced the release cascade) has no job."""

    WORKFLOWS = M3TRIK_DIR / ".github" / "workflows"

    def test_m3trik_ci_runs_the_repo_side_guard(self):
        text = (self.WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("python m3trik/scripts/check_context_budget.py --no-memory --no-runtime", text)

    def test_no_workflow_writes_an_api_file(self):
        for workflow in self.WORKFLOWS.glob("*.yml"):
            text = workflow.read_text(encoding="utf-8")
            with self.subTest(workflow=workflow.name):
                self.assertNotIn("generate_api_registry", text)
                self.assertNotIn("API_SHADOWS.md", text)


if __name__ == "__main__":
    unittest.main()
