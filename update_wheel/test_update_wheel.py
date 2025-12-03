"""
Test suite for update_wheel scripts.

Tests the push_and_merge.ps1 functionality and package structure
without actually publishing to PyPI.
"""

import subprocess
import sys
import os
from pathlib import Path
import unittest

ROOT = Path(r"O:\Cloud\Code\_scripts")
UPDATE_WHEEL_DIR = ROOT / "m3trik" / "update_wheel"
PACKAGES = ["pythontk", "uitk", "mayatk", "tentacle"]


class TestPushAndMergeScript(unittest.TestCase):
    """Tests for push_and_merge.ps1"""

    def test_script_exists(self):
        """Verify push_and_merge.ps1 exists"""
        script = UPDATE_WHEEL_DIR / "push_and_merge.ps1"
        self.assertTrue(script.exists(), f"Script not found: {script}")

    def test_dry_run_validates_builds(self):
        """Test dry run validates all package builds"""
        script = UPDATE_WHEEL_DIR / "push_and_merge.ps1"
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-DryRun",
                "-SkipBuild",
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )

        output = result.stdout + result.stderr
        # Should complete without errors when skipping build
        self.assertEqual(result.returncode, 0, f"Dry run failed: {output}")


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
        """Workflows should bump version after publish"""
        for pkg in PACKAGES:
            workflow = ROOT / pkg / ".github" / "workflows" / "publish.yml"
            content = workflow.read_text(encoding="utf-8")
            self.assertIn(
                "Bump version", content, f"{pkg} workflow missing version bump"
            )
            self.assertIn("[skip ci]", content, f"{pkg} workflow missing [skip ci]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
