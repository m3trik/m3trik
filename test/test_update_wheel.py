"""
Test suite for update_wheel scripts.

Tests the push.ps1 functionality and package structure
without actually publishing to PyPI.
"""

import subprocess
import sys
import os
import tempfile
from pathlib import Path
import unittest

ROOT = Path(r"O:\Cloud\Code\_scripts")
M3TRIK_DIR = ROOT / "m3trik"
PACKAGES = ["pythontk", "uitk", "mayatk", "tentacle"]


class TestPushScript(unittest.TestCase):
    """Tests for push.ps1"""

    def test_script_exists(self):
        """Verify push.ps1 exists"""
        script = M3TRIK_DIR / "push.ps1"
        self.assertTrue(script.exists(), f"Script not found: {script}")

    def test_dry_run_validates_builds(self):
        """Test dry run validates builds (hermetic).

        Uses temporary repos via -Root so local workspace state (e.g. an
        in-progress rebase) can't break the test.
        """
        script = M3TRIK_DIR / "push.ps1"

        # Create a hermetic root with dummy git repos
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # Minimal strict package set (just enough to exercise the script)
            reg = TestPushScriptRegressions()
            for pkg, ver in zip(PACKAGES, ["0.1.0", "0.2.0", "0.3.0", "0.4.0"]):
                reg._init_dummy_repo(root, pkg, ver, ["qtpy"])

            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-DryRun",
                    "-Strict",
                    "-All",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=60,
            )

        output = result.stdout + result.stderr
        # Should complete without errors
        self.assertEqual(result.returncode, 0, f"Dry run failed: {output}")
        self.assertIn("[DRY RUN MODE]", output)
        self.assertIn("[STRICT MODE ENABLED]", output)

        # Verify it skips packages with no changes
        self.assertIn("No changes to push and fully merged", output)


class TestPushScriptRegressions(unittest.TestCase):
    """Regression tests for release safety and ordering.

    These tests run against temporary git repos using -Root to avoid
    mutating the real workspace repos.
    """

    @staticmethod
    def _have_git() -> bool:
        try:
            r = subprocess.run(["git", "--version"], capture_output=True, text=True)
            return r.returncode == 0
        except FileNotFoundError:
            return False

    def _run(self, args, cwd: Path, timeout=120):
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )

    def _git(self, repo: Path, *args):
        r = self._run(["git", *args], cwd=repo)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stdout}{r.stderr}")
        return r

    def _init_dummy_repo(self, root: Path, name: str, version: str, requirements_lines):
        """Create a local repo with origin remote and main/dev branches."""
        repo = root / name
        repo.mkdir(parents=True, exist_ok=True)

        # Init repo
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "ci@example.com")
        self._git(repo, "config", "user.name", "CI")

        # Package structure
        pkg_dir = repo / name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text(
            f'__package__ = "{name}"\n__version__ = "{version}"\n', encoding="utf-8"
        )
        (repo / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "{version}"\n', encoding="utf-8"
        )
        (repo / "requirements.txt").write_text(
            "\n".join(requirements_lines) + "\n", encoding="utf-8"
        )

        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-m", "init")
        self._git(repo, "branch", "-M", "main")
        self._git(repo, "checkout", "-b", "dev")

        # Create bare origin remote
        remotes = root / "_remotes"
        remotes.mkdir(exist_ok=True)
        origin = remotes / f"{name}.git"
        self._git(remotes, "init", "--bare", str(origin))

        self._git(repo, "remote", "add", "origin", str(origin))
        self._git(repo, "push", "-u", "origin", "main")
        self._git(repo, "push", "-u", "origin", "dev")

        return repo, origin

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_enforces_release_order_in_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for pkg, ver in zip(PACKAGES, ["0.1.0", "0.2.0", "0.3.0", "0.4.0"]):
                self._init_dummy_repo(root, pkg, ver, ["qtpy"])

            script = M3TRIK_DIR / "push.ps1"
            # Intentionally scrambled input order
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-DryRun",
                    "-Strict",
                    "-Merge",
                    "-Packages",
                    "tentacle,mayatk,pythontk,uitk",
                ],
                cwd=root,
                timeout=60,
            )

            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)

            # Verify processing order follows canonical release order
            order = []
            for line in out.splitlines():
                if line.strip().startswith("Processing ") and line.strip().endswith(
                    "..."
                ):
                    order.append(line.strip().split()[1].rstrip("..."))
            self.assertEqual(order[:4], ["pythontk", "uitk", "mayatk", "tentacle"], out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pushdev_commits_before_pull_when_behind(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(
                root, "uitk", "0.2.0", ["qtpy", "pythontk==0.1.0"]
            )

            # Advance remote dev by one commit from a separate clone
            other = root / "_other"
            self._git(root, "clone", str(origin), str(other))
            self._git(other, "config", "user.email", "ci@example.com")
            self._git(other, "config", "user.name", "CI")
            self._git(other, "checkout", "dev")
            (other / "bump.txt").write_text("remote bump\n", encoding="utf-8")
            self._git(other, "add", "-A")
            self._git(other, "commit", "-m", "remote bump")
            self._git(other, "push", "origin", "dev")

            # Create local uncommitted change (dirty tree)
            req = repo / "requirements.txt"
            req.write_text(
                req.read_text(encoding="utf-8") + "# local edit\n", encoding="utf-8"
            )

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "uitk",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Staging uncommitted changes", out)
            self.assertTrue(
                ("Rebasing onto origin/dev" in out) or ("Pushing dev branch" in out),
                out,
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_strict_merge_stops_on_first_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p_repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._init_dummy_repo(root, "uitk", "0.2.0", ["qtpy", "pythontk==0.1.0"])

            # Create a real merge conflict between main and dev (non-auto-resolvable)
            self._git(p_repo, "checkout", "main")
            (p_repo / "docs").mkdir(exist_ok=True)
            (p_repo / "docs" / "README.md").write_text("main\n", encoding="utf-8")
            self._git(p_repo, "add", "-A")
            self._git(p_repo, "commit", "-m", "main change")
            self._git(p_repo, "push", "origin", "main")

            self._git(p_repo, "checkout", "dev")
            (p_repo / "docs").mkdir(exist_ok=True)
            (p_repo / "docs" / "README.md").write_text("dev\n", encoding="utf-8")
            self._git(p_repo, "add", "-A")
            self._git(p_repo, "commit", "-m", "dev change")
            self._git(p_repo, "push", "origin", "dev")

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "pythontk,uitk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Processing pythontk", out)
            # Should stop and not continue to uitk
            self.assertNotIn("Processing uitk", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_strict_merge_skips_dev_bump_only_ahead(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # Simulate an automated dev-bump: only version metadata changes on dev.
            self._git(repo, "checkout", "dev")
            (repo / "pyproject.toml").write_text(
                '[project]\nname = "pythontk"\nversion = "0.1.1"\n',
                encoding="utf-8",
            )
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n',
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "dev bump")
            self._git(repo, "push", "origin", "dev")

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "pythontk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Dev is ahead only due to dev bump (skipping merge)", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_syncs_internal_requirements_pins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            self._init_dummy_repo(
                root, "uitk", "1.0.51", ["qtpy", "pythontk==0.0.1"]
            )  # wrong pin
            self._init_dummy_repo(
                root, "mayatk", "0.9.54", ["qtpy", "pythontk==0.0.1", "uitk==0.0.1"]
            )
            self._init_dummy_repo(
                root,
                "tentacle",
                "0.9.60",
                ["qtpy", "pythontk==0.0.1", "uitk==0.0.1", "mayatk==0.0.1"],
            )

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "uitk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Synced requirements.txt pins", out)

            req = (root / "uitk" / "requirements.txt").read_text(encoding="utf-8")
            self.assertIn("pythontk==0.7.51", req)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_fails_when_conflict_markers_in_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(
                root, "uitk", "1.0.52", ["qtpy", "pythontk==0.7.51"]
            )

            # Introduce conflict markers in requirements.txt
            req = repo / "requirements.txt"
            req.write_text(
                "qtpy\n<<<<<<< HEAD\npythontk==0.7.51\n=======\npythontk==0.7.50\n>>>>>>> dev\n",
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "bad conflict markers")

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "uitk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Conflict markers found in requirements.txt", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_fails_when_remote_main_has_conflict_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(
                root, "uitk", "1.0.52", ["qtpy", "pythontk==0.7.51"]
            )

            # Commit conflict markers on main and push to origin/main
            self._git(repo, "checkout", "main")
            (repo / "requirements.txt").write_text(
                "qtpy\n<<<<<<< HEAD\npythontk==0.7.51\n=======\npythontk==0.7.50\n>>>>>>> dev\n",
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "main has conflict markers")
            self._git(repo, "push", "origin", "main")

            # Ensure local dev file is clean (so only remote check catches it)
            self._git(repo, "checkout", "dev")
            (repo / "requirements.txt").write_text(
                "qtpy\npythontk==0.7.51\n# dev clean\n", encoding="utf-8"
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "dev clean")
            self._git(repo, "push", "origin", "dev")

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "uitk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Conflict markers found in origin/main:requirements.txt", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_fails_for_non_github_origin(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # Make dev ahead of main so merge is attempted.
            self._git(repo, "checkout", "dev")
            (repo / "note.txt").write_text("dev ahead\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "dev ahead")
            self._git(repo, "push", "origin", "dev")

            script = M3TRIK_DIR / "push.ps1"
            result = self._run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Root",
                    str(root),
                    "-Packages",
                    "pythontk",
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                    "-UsePR",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Origin remote is not a GitHub URL; cannot use PR mode", out)


class TestPackageStructure(unittest.TestCase):
    """Tests that packages have required structure for publishing"""

    def test_packages_have_init(self):
        """All packages should have __init__.py with __version__"""
        for pkg in PACKAGES:
            init_file = ROOT / pkg / pkg / "__init__.py"
            self.assertTrue(init_file.exists(), f"{pkg}/__init__.py not found")

            content = init_file.read_text(encoding="utf-8")
            self.assertIn("__version__", content, f"{pkg} missing __version__")

    def test_packages_have_pyproject(self):
        """All packages should have pyproject.toml"""
        for pkg in PACKAGES:
            pyproject_file = ROOT / pkg / "pyproject.toml"
            self.assertTrue(pyproject_file.exists(), f"{pkg}/pyproject.toml not found")

    def test_packages_have_requirements(self):
        """All packages should have requirements.txt"""
        for pkg in PACKAGES:
            req_file = ROOT / pkg / "requirements.txt"
            self.assertTrue(req_file.exists(), f"{pkg}/requirements.txt not found")

    def test_versions_are_valid_semver(self):
        """All package versions should be valid semantic versions"""
        import re

        semver_pattern = r"^\d+\.\d+\.\d+$"

        for pkg in PACKAGES:
            init_file = ROOT / pkg / pkg / "__init__.py"
            content = init_file.read_text(encoding="utf-8")
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            self.assertIsNotNone(match, f"{pkg} missing __version__")

            version = match.group(1)
            self.assertRegex(
                version,
                semver_pattern,
                f"{pkg} version '{version}' is not valid semver (X.Y.Z)",
            )


class TestRequirementsPins(unittest.TestCase):
    """Validate requirements.txt pins remain installable.

    These files are used for `pip install -r requirements.txt` and are also
    edited by our publish workflows. A regression here can break installs.
    """

    def _read_pins(self, pkg: str) -> dict:
        req_file = ROOT / pkg / "requirements.txt"
        pins = {}
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, ver = line.split("==", 1)
                pins[name.strip()] = ver.strip()
        return pins

    def test_internal_pins_present(self):
        expectations = {
            "uitk": ["pythontk"],
            "mayatk": ["pythontk", "uitk"],
            "tentacle": ["pythontk", "uitk", "mayatk"],
        }

        for pkg, deps in expectations.items():
            pins = self._read_pins(pkg)
            for dep in deps:
                self.assertIn(dep, pins, f"{pkg} missing pin for {dep}")

    def test_pinned_versions_exist_on_pypi(self):
        """Ensure pinned internal versions are actually on PyPI.

        Skips if pip cannot query indexes (offline environments).
        """

        pinned = []
        for pkg in ["uitk", "mayatk", "tentacle"]:
            pins = self._read_pins(pkg)
            for dep in ["pythontk", "uitk", "mayatk"]:
                if dep in pins:
                    pinned.append((dep, pins[dep]))

        for dep, ver in pinned:
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "index", "versions", dep],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception:
                self.skipTest("pip index versions unavailable")

            if r.returncode != 0:
                self.skipTest("pip index versions failed (offline?)")

            out = r.stdout + r.stderr
            self.assertIn(ver, out, f"{dep} pinned version {ver} not found on PyPI")


class TestGitHubWorkflows(unittest.TestCase):
    """Tests that GitHub workflow files are properly configured"""

    def test_workflows_exist(self):
        """All packages should have publish workflow"""
        for pkg in PACKAGES:
            workflow = ROOT / pkg / ".github" / "workflows" / "publish.yml"
            self.assertTrue(workflow.exists(), f"{pkg} missing publish.yml workflow")

    def test_workflows_have_push_trigger(self):
        """Workflows should have push trigger"""
        for pkg in PACKAGES:
            workflow = ROOT / pkg / ".github" / "workflows" / "publish.yml"
            content = workflow.read_text(encoding="utf-8")
            self.assertIn("push:", content, f"{pkg} workflow missing push trigger")

    def test_workflows_reference_secrets(self):
        """Workflows should use PYPI_TOKEN and REPO_DISPATCH_TOKEN"""
        for pkg in PACKAGES:
            workflow = ROOT / pkg / ".github" / "workflows" / "publish.yml"
            content = workflow.read_text(encoding="utf-8")

            self.assertIn("PYPI_TOKEN", content, f"{pkg} workflow missing PYPI_TOKEN")
            self.assertIn(
                "REPO_DISPATCH_TOKEN",
                content,
                f"{pkg} workflow missing REPO_DISPATCH_TOKEN",
            )

    def test_workflows_bump_version(self):
        """Workflows should trigger dev bump after publish"""
        for pkg in PACKAGES:
            workflow = ROOT / pkg / ".github" / "workflows" / "publish.yml"
            content = workflow.read_text(encoding="utf-8")

            # Check for either "Bump version" (old) or "Trigger dev bump" (new)
            has_bump = "Bump version" in content or "Trigger dev bump" in content
            self.assertTrue(has_bump, f"{pkg} workflow missing version bump/trigger")

            # Check for skip ci if it's a direct commit, or just ensure the mechanism exists
            # The new mechanism uses repository_dispatch which doesn't need [skip ci] in the workflow file itself
            # but the commit message in the script usually has it.
            # Let's just check for the trigger for now.


if __name__ == "__main__":
    unittest.main(verbosity=2)
