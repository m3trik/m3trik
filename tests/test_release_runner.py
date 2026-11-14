#!/usr/bin/python
# coding=utf-8
"""Tests for the release runner: scripts/Invoke-RunnerRelease.ps1, scripts/Install-ReleaseRunner.ps1
and release_runner/release.yml (docs/RELEASE_RUNNER.md).

The driver resets and cleans every repo under its root, and its workflow runs on a
self-hosted machine, so the refusals are what these pin first: no marker, no review,
a typo in the package set, the installer pointed at a live workspace, and a workflow
anything but a hand dispatch could start. The sync runs against local bare repos.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRIVER = os.path.join(REPO, "scripts", "Invoke-RunnerRelease.ps1")
INSTALLER = os.path.join(REPO, "scripts", "Install-ReleaseRunner.ps1")
WORKFLOW = os.path.join(REPO, "release_runner", "release.yml")
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
CASCADE = ["pythontk", "uitk", "mayatk", "blendertk", "tentacle"]


def _ps(script, *, cwd=None):
    """Run *script* in a fresh PowerShell; ``(exit code, stdout + stderr)``."""
    proc = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=180,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _quote(path):
    return "'" + path.replace("'", "''") + "'"


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(POWERSHELL, "no PowerShell on PATH")
class TestDriverFunctions(unittest.TestCase):
    """The pure functions, dot-sourced (dot-sourcing runs nothing)."""

    def _call(self, expr):
        code, out = _ps(f". {_quote(DRIVER)}; {expr} | ConvertTo-Json -Compress")
        self.assertEqual(code, 0, out)
        return json.loads(out.strip().splitlines()[-1])

    def test_packages_come_back_in_cascade_order(self):
        got = self._call(
            f"Resolve-ReleasePackages 'tentacle, pythontk,mayatk' @({','.join(repr(c) for c in CASCADE)})"
        )
        self.assertEqual(got, ["pythontk", "mayatk", "tentacle"])

    def test_no_names_is_the_whole_cascade(self):
        got = self._call(f"Resolve-ReleasePackages ' ' @({','.join(repr(c) for c in CASCADE)})")
        self.assertEqual(got, CASCADE)
        self.assertNotIn("uitk", open(DRIVER, encoding="utf-8").read().split("$SUITES = @{")[0])

    def test_a_name_outside_the_cascade_is_refused(self):
        code, out = _ps(
            f". {_quote(DRIVER)}; Resolve-ReleasePackages 'pythontk,mayatkk' @({','.join(repr(c) for c in CASCADE)})"
        )
        self.assertNotEqual(code, 0)
        self.assertIn("Not cascade packages: mayatkk", out)

    def test_a_review_is_attested_per_package_at_its_commit(self):
        sha = "aade873c0ffee0000000000000000000000000000"
        cases = [
            ("pythontk@aade873", "pythontk", True),
            ("mayatk@170be25, pythontk@AADE873C0FFEE", "pythontk", True),
            ("pythontk@aade874", "pythontk", False),  # another commit
            ("mayatk@aade873", "pythontk", False),  # another package
            ("pythontk@aade", "pythontk", False),  # too short to name a commit
            ("pythontk", "pythontk", False),
            ("true", "pythontk", False),
            ("", "pythontk", False),
        ]
        expr = ",".join(f"(Test-Attested {r!r} {p!r} {sha!r})" for r, p, _ in cases)
        self.assertEqual(self._call(f"@({expr})"), [want for _, _, want in cases])

    def test_the_driver_restates_none_of_push_ps1s_delta_rules(self):
        text = open(DRIVER, encoding="utf-8").read()
        self.assertIn("-GateReport", text)
        for restated in ("CHANGELOG", "'^tests/'", ".github", "diff --name-only"):
            self.assertNotIn(restated, text)

    def test_the_workspace_repos_are_the_cascade_the_standalones_and_m3trik(self):
        got = self._call(f"Get-WorkspaceRepos (Read-Manifest {_quote(os.path.dirname(REPO))})")
        self.assertEqual(got[: len(CASCADE)], CASCADE)
        self.assertEqual(set(got[len(CASCADE):]), {"unitytk", "extapps", "m3trik"})

    def test_the_hygiene_denylist_is_copied_where_push_reads_it(self):
        tmp = tempfile.mkdtemp(prefix="release_runner_deny_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        source = os.path.join(tmp, "denylist.txt")
        with open(source, "w") as f:
            f.write("client\n")
        root = os.path.join(tmp, "root")
        os.makedirs(root)
        code, out = _ps(f". {_quote(DRIVER)}; Copy-HygieneDenylist {_quote(root)} {_quote(source)}")
        self.assertEqual(code, 0, out)
        with open(os.path.join(root, ".claude", "public_hygiene.txt")) as f:
            self.assertEqual(f.read(), "client\n")
        code, out = _ps(f". {_quote(DRIVER)}; Copy-HygieneDenylist {_quote(root)} ''")
        self.assertEqual(code, 0, out)
        self.assertIn("no hygiene denylist", out)

    def test_every_cascade_package_has_a_full_suite(self):
        got = self._call("$SUITES.Keys | Sort-Object")
        self.assertEqual(got, sorted(CASCADE))
        self.assertEqual(self._call("$SUITES['mayatk']"), ["mayatk/tests/run_tests.py", "--all"])
        self.assertEqual(self._call("$SUITES['tentacle']"), ["tentacle/tests/run_tests.py", "--in-maya"])


@unittest.skipUnless(POWERSHELL, "no PowerShell on PATH")
class TestDriverRefusals(unittest.TestCase):
    """A run refuses before it touches anything."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="release_runner_")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "m3trik"))
        shutil.copy(os.path.join(REPO, "workspace.json"), os.path.join(self.root, "m3trik"))

    def _run(self, *args):
        return _ps(f"& {_quote(DRIVER)} -Root {_quote(self.root)} -RemoteBase 'file:///nowhere' " + " ".join(args))

    def test_a_root_without_the_marker_is_refused(self):
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("is not a release-runner workspace", out)
        self.assertEqual(os.listdir(self.root), ["m3trik"])

    def test_a_typo_in_the_package_set_is_refused_before_the_sync(self):
        open(os.path.join(self.root, ".release-runner"), "w").close()
        code, out = self._run("-Packages", "'pythontk,tentacel'")
        self.assertEqual(code, 1, out)
        self.assertIn("Not cascade packages: tentacel", out)
        self.assertEqual(sorted(os.listdir(self.root)), [".release-runner", "m3trik"])


@unittest.skipUnless(POWERSHELL and shutil.which("git"), "no PowerShell or git on PATH")
class TestSync(unittest.TestCase):
    """Sync-ReleaseRepo and Get-ArtifactDelta over local bare repos."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="release_runner_sync_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remotes = os.path.join(self.tmp, "remotes")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.remotes)
        os.makedirs(self.root)

    def _remote(self, name, dev_files=None):
        """A bare *name* with ``main`` (src.py) and, given *dev_files*, ``dev`` adding them."""
        work = os.path.join(self.tmp, "work_" + name)
        os.makedirs(work)
        _git("init", "-q", "-b", "main", cwd=work)
        _git("config", "user.email", "test@example.com", cwd=work)
        _git("config", "user.name", "test", cwd=work)
        with open(os.path.join(work, "src.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(work, ".gitignore"), "w") as f:
            f.write("*.ignored\n")
        _git("add", "-A", cwd=work)
        _git("commit", "-q", "-m", "main", cwd=work)
        if dev_files is not None:
            _git("checkout", "-q", "-b", "dev", cwd=work)
            for rel, text in dev_files.items():
                path = os.path.join(work, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(text)
            _git("add", "-A", cwd=work)
            _git("commit", "-q", "-m", "dev", cwd=work)
        _git("clone", "-q", "--bare", work, os.path.join(self.remotes, name), cwd=self.tmp)

    def _sync(self, name):
        base = "file://" + self.remotes.replace(os.sep, "/")
        code, out = _ps(f". {_quote(DRIVER)}; Sync-ReleaseRepo {_quote(self.root)} {name} {_quote(base)}")
        self.assertEqual(code, 0, out)
        return out.strip().splitlines()[-1]

    def test_dev_is_checked_out_and_a_repo_without_dev_takes_main(self):
        self._remote("withdev", {"lib/new.py": "y = 2\n"})
        self._remote("nodev")
        self.assertEqual(self._sync("withdev"), "dev")
        self.assertEqual(self._sync("nodev"), "main")
        self.assertTrue(os.path.exists(os.path.join(self.root, "withdev", "lib", "new.py")))

    def test_a_resync_discards_edits_and_strays_and_keeps_ignored_files(self):
        self._remote("pkg", {"lib/new.py": "y = 2\n"})
        self._sync("pkg")
        repo = os.path.join(self.root, "pkg")
        with open(os.path.join(repo, "src.py"), "w") as f:
            f.write("edited\n")
        for stray in ("stray.py", "cache.ignored"):
            open(os.path.join(repo, stray), "w").close()
        self._sync("pkg")
        with open(os.path.join(repo, "src.py")) as f:
            self.assertEqual(f.read(), "x = 1\n")
        self.assertFalse(os.path.exists(os.path.join(repo, "stray.py")))
        self.assertTrue(os.path.exists(os.path.join(repo, "cache.ignored")))

    def _tooling(self):
        code, out = _ps(f". {_quote(DRIVER)}; Merge-ToolingRepo {_quote(self.root)}")
        return code, out.strip().splitlines()[-1] if out.strip() else ""

    def _heads(self):
        bare = os.path.join(self.remotes, "m3trik")
        return [
            subprocess.run(["git", "rev-parse", ref], cwd=bare, capture_output=True, text=True).stdout.strip()
            for ref in ("main", "dev")
        ]

    def test_tooling_main_is_fast_forwarded_to_dev(self):
        self._remote("m3trik", {"scripts/new.py": ""})
        self._sync("m3trik")
        main, dev = self._heads()
        self.assertNotEqual(main, dev)
        self.assertEqual(self._tooling(), (0, "fast-forwarded"))
        self.assertEqual(len(set(self._heads())), 1)
        self.assertEqual(self._tooling(), (0, "level"))

    def test_tooling_main_ahead_of_dev_stops_the_run(self):
        self._remote("m3trik", {"scripts/new.py": ""})
        work = os.path.join(self.tmp, "work_m3trik")
        _git("checkout", "-q", "main", cwd=work)
        open(os.path.join(work, "hotfix.py"), "w").close()
        _git("add", "-A", cwd=work)
        _git("commit", "-q", "-m", "hotfix", cwd=work)
        _git("push", "-q", os.path.join(self.remotes, "m3trik"), "main", cwd=work)
        self._sync("m3trik")
        before = self._heads()
        code, out = _ps(f". {_quote(DRIVER)}; Merge-ToolingRepo {_quote(self.root)}")
        self.assertNotEqual(code, 0)
        self.assertIn("main holds commits dev lacks", out)
        self.assertEqual(self._heads(), before)

STUB_PUSH = r"""
param([string]$Root, [string]$Packages, [switch]$Strict, [switch]$Merge, [switch]$UsePR,
      [switch]$DryRun, [switch]$SkipReview, [switch]$GateReport, [string]$RecordReceipt)
$mode = if ($GateReport) { "gate" } elseif ($RecordReceipt) { "record=$RecordReceipt" } elseif ($DryRun) { "dry" } else { "release" }
Add-Content -LiteralPath (Join-Path $Root "calls.log") "$mode $Packages$(if ($SkipReview) { ' skipreview' })"
Write-Host "stub push: $mode"
if ($GateReport) {
    Write-Output "a line push.ps1 printed before its report"
    Write-Output (Get-Content -Raw -LiteralPath (Join-Path $Root "gate.json")).Trim()
    exit 0
}
if (Test-Path -LiteralPath (Join-Path $Root "fail_$mode")) { exit 3 }
exit 0
"""

STUB_SUITE = """
import pathlib, sys
repo = pathlib.Path(__file__).resolve().parents[1]
with open(repo.parent / "suites.log", "a") as f:
    f.write(" ".join([repo.name, *sys.argv[1:]]) + "\\n")
print("suite output of " + repo.name)
sys.exit(1 if (repo.parent / ("red_" + repo.name)).exists() else 0)
"""

SHA = {"pythontk": "aade873" + "0" * 33, "mayatk": "170be25" + "1" * 33}


@unittest.skipUnless(POWERSHELL and shutil.which("git"), "no PowerShell or git on PATH")
class TestRun(unittest.TestCase):
    """The whole run over local bare repos, with push.ps1 and the suites stubbed:
    what the driver calls, in what order, and what stops it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="release_runner_run_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remotes = os.path.join(self.tmp, "remotes")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.remotes)
        os.makedirs(self.root)
        open(os.path.join(self.root, ".release-runner"), "w").close()
        self._remote("m3trik", {
            "push.ps1": STUB_PUSH,
            "workspace.json": json.dumps({"cascade": ["pythontk", "mayatk"], "units": []}),
        })
        for name in ("pythontk", "mayatk"):
            self._remote(name, {"tests/run_tests.py": STUB_SUITE, "src.py": "x = 1\n"})
        # The workflow's first step: m3trik's clone, at dev.
        _git("clone", "-q", os.path.join(self.remotes, "m3trik"), os.path.join(self.root, "m3trik"), cwd=self.tmp)
        _git("checkout", "-q", "dev", cwd=os.path.join(self.root, "m3trik"))

    def _remote(self, name, files):
        work = os.path.join(self.tmp, "work_" + name)
        os.makedirs(work)
        _git("init", "-q", "-b", "main", cwd=work)
        _git("config", "user.email", "test@example.com", cwd=work)
        _git("config", "user.name", "test", cwd=work)
        for rel, text in files.items():
            path = os.path.join(work, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        _git("add", "-A", cwd=work)
        _git("commit", "-q", "-m", "main", cwd=work)
        _git("branch", "dev", cwd=work)
        _git("clone", "-q", "--bare", work, os.path.join(self.remotes, name), cwd=self.tmp)

    def _gate(self, **missing):
        """What the stubbed push.ps1 reports: each package's missing receipts."""
        rows = [
            {"package": name, "sha": SHA[name], "hash": "h", "class": "artifact" if owed is not None else "none",
             "exempt": None if owed is not None else "has nothing to release", "missing": owed or []}
            for name, owed in missing.items()
        ]
        with open(os.path.join(self.root, "gate.json"), "w") as f:
            json.dump(rows, f)

    def _run(self, *args):
        import sys

        # No -RemoteBase: the siblings are cloned from beside m3trik's own origin.
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", DRIVER, "-Root", self.root, *args],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "M3TRIK_PYTHON": sys.executable, "M3TRIK_HYGIENE_DENYLIST": ""},
        )
        return proc.returncode, proc.stdout + proc.stderr

    def _log(self, name):
        path = os.path.join(self.root, name)
        return open(path).read().split("\n")[:-1] if os.path.exists(path) else []

    def test_a_dry_run_plans_and_names_the_review_it_needs(self):
        self._gate(pythontk=["review", "tests"], mayatk=["review", "tests"])
        code, out = self._run("-DryRun")
        self.assertEqual(code, 0, out)
        self.assertEqual(self._log("calls.log"), ["dry pythontk,mayatk skipreview", "gate pythontk,mayatk skipreview"])
        self.assertIn("reviewed=pythontk@aade873,mayatk@170be25", out)
        self.assertIn("pythontk@aade873: owes review + tests", out)
        self.assertEqual(self._log("suites.log"), [])

    def test_a_reviewed_release_tests_records_and_releases_in_order(self):
        self._gate(pythontk=["review", "tests"], mayatk=None)
        code, out = self._run("-Reviewed", "pythontk@aade873")
        self.assertEqual(code, 0, out)
        self.assertEqual(self._log("calls.log"), [
            "dry pythontk,mayatk skipreview",
            "gate pythontk,mayatk",
            "record=review,tests pythontk",
            "release pythontk,mayatk",
        ])
        self.assertEqual(self._log("suites.log"), ["pythontk"])
        self.assertIn("suite output of pythontk", out)  # a suite's output reaches the log
        self.assertIn("mayatk@170be25: has nothing to release", out)
        self.assertIn("a line push.ps1 printed before its report", out)

    def test_each_package_runs_its_declared_full_suite(self):
        self._gate(pythontk=["tests"], mayatk=["tests"])
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertEqual(self._log("suites.log"), ["pythontk", "mayatk --all"])
        self.assertEqual(self._log("calls.log")[2:], [
            "record=tests pythontk", "record=tests mayatk", "release pythontk,mayatk"])

    def test_valid_receipts_run_no_suite_again(self):
        self._gate(pythontk=[], mayatk=[])
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertEqual(self._log("suites.log"), [])
        self.assertEqual(self._log("calls.log")[2:], ["release pythontk,mayatk"])

    def test_a_dev_that_moved_since_the_review_is_refused_before_any_suite(self):
        self._gate(pythontk=["review", "tests"], mayatk=["review", "tests"])
        code, out = self._run("-Reviewed", "pythontk@aade873,mayatk@0ldc0de")
        self.assertEqual(code, 1, out)
        self.assertIn("Not reviewed at the commit dev holds: mayatk", out)
        self.assertEqual(self._log("suites.log"), [])
        self.assertEqual(self._log("calls.log"), ["dry pythontk,mayatk skipreview", "gate pythontk,mayatk"])

    def test_a_red_suite_records_nothing_and_releases_nothing(self):
        self._gate(pythontk=["tests"], mayatk=["tests"])
        open(os.path.join(self.root, "red_pythontk"), "w").close()
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("pythontk's suite is red", out)
        self.assertEqual(self._log("suites.log"), ["pythontk"])
        self.assertEqual(self._log("calls.log"), ["dry pythontk,mayatk skipreview", "gate pythontk,mayatk"])

    def test_a_failed_preflight_stops_before_the_gate_and_the_suites(self):
        self._gate(pythontk=["tests"], mayatk=["tests"])
        open(os.path.join(self.root, "fail_dry"), "w").close()
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("The preflight failed", out)
        self.assertEqual(self._log("calls.log"), ["dry pythontk,mayatk skipreview"])
        self.assertEqual(self._log("suites.log"), [])

    def test_a_failed_release_fails_the_run(self):
        self._gate(pythontk=[], mayatk=[])
        open(os.path.join(self.root, "fail_release"), "w").close()
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("The release did not complete", out)


@unittest.skipUnless(POWERSHELL, "no PowerShell on PATH")
class TestScriptsParse(unittest.TestCase):
    """A parse error surfaces only on the Windows machine otherwise, mid-setup."""

    def test_both_scripts_parse(self):
        for path in (DRIVER, INSTALLER):
            with self.subTest(script=os.path.basename(path)):
                code, out = _ps(
                    "$errors = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                    f"{_quote(path)}, [ref]$null, [ref]$errors); $errors | ForEach-Object {{ $_.Message }}; exit $errors.Count"
                )
                self.assertEqual(code, 0, out)


@unittest.skipUnless(POWERSHELL, "no PowerShell on PATH")
class TestInstaller(unittest.TestCase):
    def test_the_live_workspace_is_never_the_runners_root(self):
        live = os.path.dirname(REPO)
        code, out = _ps(f". {_quote(INSTALLER)} -Root {_quote(live)}; Initialize-Workspace")
        self.assertNotEqual(code, 0)
        self.assertIn("Pick a dedicated folder", out)
        self.assertFalse(os.path.exists(os.path.join(live, ".release-runner")))

    def test_it_publishes_the_files_the_release_repo_holds(self):
        text = open(INSTALLER, encoding="utf-8").read()
        for rel in ("release_runner/release.yml", "release_runner/README.md"):
            self.assertIn(rel, text)
            self.assertTrue(os.path.exists(os.path.join(REPO, *rel.split("/"))), rel)


class TestWorkflow(unittest.TestCase):
    """The workflow a self-hosted machine runs: hand dispatch only, inputs as data."""

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.text = f.read()

    def test_only_a_hand_dispatch_starts_it(self):
        on = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+?)(?=^\S)", self.text, re.MULTILINE).group(1)
        triggers = re.findall(r"^  (\w+):", on, re.MULTILINE)
        self.assertEqual(triggers, ["workflow_dispatch"])

    def test_it_runs_on_the_release_runner_one_at_a_time(self):
        self.assertIn("runs-on: [self-hosted, Windows, m3trik-release]", self.text)
        self.assertRegex(self.text, r"concurrency:\n\s+group: release\n\s+cancel-in-progress: false")
        self.assertIn("permissions: {}", self.text)

    def test_the_review_input_is_the_commits_reviewed_not_a_checkbox(self):
        block = re.search(r"      reviewed:\n((?:        .*\n)+)", self.text).group(1)
        self.assertNotIn("boolean", block)
        self.assertIn("-Reviewed $env:REVIEWED", self.text)

    def test_inputs_reach_the_scripts_as_environment_never_as_code(self):
        for block in re.findall(r"run: \|\n((?:[ \t]{10}.*\n)+)", self.text):
            self.assertNotIn("${{", block)
        self.assertIn("PACKAGES: ${{ inputs.packages }}", self.text)

    def test_its_driver_and_marker_are_the_scripts(self):
        self.assertIn("m3trik/scripts/Invoke-RunnerRelease.ps1", self.text)
        self.assertIn(".release-runner", self.text)
        self.assertIn('$RUNNER_MARKER = ".release-runner"', open(DRIVER, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
