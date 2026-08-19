"""
Test suite for push.ps1.

Tests push.ps1 functionality and package structure
without actually publishing to PyPI.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
M3TRIK_DIR = ROOT / "m3trik"
PACKAGES = ["pythontk", "uitk", "mayatk", "blendertk", "tentacle"]
DUMMY_VERSIONS = ["0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0"]

#: ``__version__ = "X.Y.Z"`` as written in every package ``__init__.py``. The
#: value is captured loosely on purpose: the semver check has to SEE a
#: malformed version to reject it, so this must not filter one out.
_VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')


def version_in(text):
    """The ``__version__`` declared in *text*.

    Parameters:
        text (str): Contents of a package ``__init__.py``.

    Returns:
        str | None: The declared version, or None when *text* declares none.
    """
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


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
            for pkg, ver in zip(PACKAGES, DUMMY_VERSIONS):
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

    def _run(self, args, cwd: Path, timeout=120, env=None):
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
            env=env,
        )

    def _git(self, repo: Path, *args):
        r = self._run(["git", *args], cwd=repo)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stdout}{r.stderr}")
        return r

    def _init_dummy_repo(self, root: Path, name: str, version: str, requirements_lines):
        """Create a local repo with origin remote and main/dev branches.

        Mirrors the real packages' shape: dynamic version (`{attr =
        "<pkg>.__version__"}`, read from `__init__.py`) and internal pins
        declared as `"pkg>=X.Y.Z"` entries in pyproject.toml's `dependencies`
        list — the exact format Sync-PyProjectDepsToLocalVersions' regex
        matches. `requirements.txt` is deprecated repo-wide and no longer
        created; any `==`-pinned entry is normalized to `>=` since that's the
        only operator the real sync logic understands.
        """
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
        deps = [line.replace("==", ">=") for line in requirements_lines]
        deps_toml = ",\n    ".join(f'"{d}"' for d in deps)
        (repo / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\n'
            f'version = {{attr = "{name}.__version__"}}\n'
            f"dependencies = [\n    {deps_toml}\n]\n",
            encoding="utf-8",
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
            for pkg, ver in zip(PACKAGES, DUMMY_VERSIONS):
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
                    "-SkipReview",
                    "-Packages",
                    "tentacle,blendertk,mayatk,pythontk,uitk",
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
            self.assertEqual(
                order[:5],
                ["pythontk", "uitk", "mayatk", "blendertk", "tentacle"],
                out,
            )

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
            pyproject = repo / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8") + "# local edit\n",
                encoding="utf-8",
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
                    "-SkipReview",
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

            # Simulate an automated dev-bump: only __init__.py changes on dev.
            # Real strict packages declare `version = {attr = "<pkg>.__version__"}`
            # (dynamic) in pyproject.toml, so a pure version bump never touches
            # that file — only rewriting __init__.py matches what
            # Test-OnlyDevBumpChanges actually allows.
            self._git(repo, "checkout", "dev")
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
                    "-SkipReview",
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
    def test_merges_local_changes_when_origin_dev_is_bump_only(self):
        """Real local changes must release even when origin/dev is bump-only ahead.

        Steady state after any release: origin/dev = origin/main + the bump-dev
        bot's version commit. A run that then absorbs real local work commits it
        LOCALLY first (push happens later, in step 3) — so the bump-only guard
        must diff local dev, not origin/dev, or it classifies the run as
        "nothing to release" and silently drops the merge while still reporting
        success.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # Simulate the bump-dev bot: version-only commit on origin/dev.
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n',
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "Bump version to 0.1.1 [skip ci]")
            self._git(repo, "push", "origin", "dev")

            # Real, not-yet-committed local work.
            (repo / "pythontk" / "feature.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
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
                    "pythontk",
                    "-Strict",
                    "-Merge",
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertNotIn("skipping merge", out)
            self.assertIn("Merged and pushed to main", out)

            # The local change must actually be on the released main branch.
            tree = self._git(origin, "ls-tree", "-r", "--name-only", "main").stdout
            self.assertIn("pythontk/feature.py", tree, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_strict_merge_skips_bump_plus_registry_churn(self):
        """Bot-generated registry commits must not defeat the phantom-publish guard.

        refresh-api-registry.yml pushes API_INDEX.md/API_REGISTRY.md/
        API_REGISTRY.json/API_CHANGES.md commits onto dev after every publish.
        None of those files ship in the wheel, so a dev that is ahead only by
        the bump commit + registry churn has nothing to release — merging it
        anyway phantom-publishes a new version with identical wheel content.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # bump-dev bot commit
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n',
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "Bump version to 0.1.1 [skip ci]")

            # api-registry-bot commit (repo-root artifacts, not wheel content)
            for name in (
                "API_INDEX.md",
                "API_REGISTRY.md",
                "API_REGISTRY.json",
                "API_CHANGES.md",
            ):
                (repo / name).write_text("# generated\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "chore: refresh API registry [skip ci]")
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
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Dev is ahead only due to dev bump (skipping merge)", out)

            # Nothing may have been merged to main.
            tree = self._git(origin, "ls-tree", "-r", "--name-only", "main").stdout
            self.assertNotIn("API_INDEX.md", tree, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_no_double_bump_after_dep_sync_commit(self):
        """A retry after a failed run must not bump the version a second time.

        The dependency-cascade path commits "Update dependencies & bump version
        to X [skip ci]". If a run fails after that commit (e.g. build failure),
        the retry sees dev ahead of origin/dev and must recognize that the last
        commit already carries a bump — otherwise every retry burns a patch
        version.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # Simulate a prior failed run's pin-sync commit: local-only,
            # touching __init__.py + pyproject.toml.
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n',
                encoding="utf-8",
            )
            pyproject = repo / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8") + "# pin sync\n",
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(
                repo,
                "commit",
                "-m",
                "Update dependencies & bump version to 0.1.1 [skip ci]",
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
                    "pythontk",
                    "-Strict",
                    "-Merge",
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertNotIn("[Auto-Bump]", out)
            content = (repo / "pythontk" / "__init__.py").read_text(encoding="utf-8")
            self.assertIn('__version__ = "0.1.1"', content, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_syncs_internal_pyproject_pins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Versions are real published releases whose successors also exist
            # on PyPI — the strict pipeline clamps/checks against the live
            # index, so invented versions would false-fail the PyPI pin check.
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            self._init_dummy_repo(
                root, "uitk", "1.0.51", ["qtpy", "pythontk==0.0.1"]
            )  # wrong pin
            self._init_dummy_repo(
                root, "mayatk", "0.9.54", ["qtpy", "pythontk==0.0.1", "uitk==0.0.1"]
            )
            self._init_dummy_repo(
                root, "blendertk", "0.5.0", ["qtpy", "pythontk==0.0.1", "uitk==0.0.1"]
            )
            self._init_dummy_repo(
                root,
                "tentacle",
                "0.9.60",
                [
                    "qtpy",
                    "pythontk==0.0.1",
                    "uitk==0.0.1",
                    "mayatk==0.0.1",
                    "blendertk==0.0.1",
                ],
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
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Synced dependencies & bumped version", out)

            toml = (root / "uitk" / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('"pythontk>=0.7.51"', toml)

            # The cascade must also have synced the parallel blendertk branch.
            btk_toml = (root / "blendertk" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn('"pythontk>=0.7.51"', btk_toml)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_fails_when_conflict_markers_in_pyproject(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(
                root, "uitk", "1.0.52", ["qtpy", "pythontk==0.7.51"]
            )

            # Introduce conflict markers in pyproject.toml
            pyproject = repo / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8")
                + "<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> dev\n",
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
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Conflict markers found in pyproject.toml", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_fails_when_remote_main_has_conflict_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(
                root, "uitk", "1.0.52", ["qtpy", "pythontk==0.7.51"]
            )

            # Commit conflict markers on main and push to origin/main
            self._git(repo, "checkout", "main")
            pyproject = repo / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8")
                + "<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> dev\n",
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "main has conflict markers")
            self._git(repo, "push", "origin", "main")

            # Ensure local dev file is clean (so only remote check catches it)
            self._git(repo, "checkout", "dev")

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
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Conflict markers found in origin/main:pyproject.toml", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_fails_when_remote_dev_has_conflict_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(
                root, "uitk", "1.0.52", ["qtpy", "pythontk==0.7.51"]
            )

            # Commit conflict markers on dev and push to origin/dev
            pyproject = repo / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8")
                + "<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> dev\n",
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "dev has conflict markers")
            self._git(repo, "push", "origin", "dev")

            # Ensure local checkout is clean main (so only remote check catches it)
            self._git(repo, "checkout", "main")

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
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Conflict markers found in origin/dev:pyproject.toml", out)

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
                    "-SkipReview",
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


    def test_review_gate_blocks_unreviewed_delta_then_receipt_releases_it(self):
        """The Strict+Merge review gate refuses a real code delta with no
        receipt, and a recorded receipt for that exact tree lets it through.

        Every other Strict+Merge test here passes ``-SkipReview`` because the
        gate is a pre-pass that would short-circuit the rail it is exercising —
        so without this test the gate itself ships uncovered. Both halves matter:
        blocking proves the rail exists, and releasing after ``-RecordReceipt``
        proves the tree hash the gate computes matches the one the recorder
        writes (a drift there would deadlock every release).
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # A real (non-housekeeping) delta on dev — what the gate guards.
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")

            script = M3TRIK_DIR / "push.ps1"
            base = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Root",
                str(root),
                "-Packages",
                "pythontk",
            ]
            release = base + [
                "-Strict",
                "-Merge",
                "-SkipBuild",
                "-SkipWorkflowWait",
                "-SkipPypiCheck",
            ]

            blocked = self._run(release, cwd=root, timeout=120)
            out = blocked.stdout + blocked.stderr
            self.assertNotEqual(blocked.returncode, 0, out)
            self.assertIn("No review receipt for the current tree", out)
            # The failure must carry the protocol, not just a refusal.
            self.assertIn("-RecordReceipt review", out)

            recorded = self._run(
                base + ["-RecordReceipt", "review,tests"], cwd=root, timeout=120
            )
            self.assertEqual(
                recorded.returncode, 0, recorded.stdout + recorded.stderr
            )

            passed = self._run(release, cwd=root, timeout=180)
            out2 = passed.stdout + passed.stderr
            self.assertIn("Review receipt valid", out2)
            self.assertNotIn("No review receipt for the current tree", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_m3trik_first_guard_blocks_release_on_scripts_drift(self):
        """A Strict+Merge release must refuse to run while m3trik/scripts
        differs from origin/main. The publish-triggered refresh-api-registry
        bot regenerates from m3trik@main, so local tooling drift means the
        bot force-pushes OLD-generator registries over the ones this release
        just produced (measured 2026-08-01: mayatk -495 / blendertk -234
        lines and a full re-release cycle)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # A real delta so a PASSING guard proceeds to the review gate.
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")

            # An m3trik repo whose scripts/ is pushed to origin/main...
            m3trik = root / "m3trik"
            (m3trik / "scripts").mkdir(parents=True)
            gen = m3trik / "scripts" / "generate_api_registry.py"
            gen.write_text("VERSION = 1\n", encoding="utf-8")
            self._git(m3trik, "init")
            self._git(m3trik, "config", "user.email", "ci@example.com")
            self._git(m3trik, "config", "user.name", "CI")
            self._git(m3trik, "add", "-A")
            self._git(m3trik, "commit", "-m", "init")
            self._git(m3trik, "branch", "-M", "main")
            remotes = root / "_remotes"
            remotes.mkdir(exist_ok=True)
            origin = remotes / "m3trik.git"
            self._git(remotes, "init", "--bare", str(origin))
            self._git(m3trik, "remote", "add", "origin", str(origin))
            self._git(m3trik, "push", "-u", "origin", "main")

            # ...then drifts locally (a generator edit the bot would not have).
            gen.write_text("VERSION = 2\n", encoding="utf-8")

            release = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(M3TRIK_DIR / "push.ps1"),
                "-Root",
                str(root),
                "-Packages",
                "pythontk",
                "-Strict",
                "-Merge",
                "-SkipBuild",
                "-SkipWorkflowWait",
                "-SkipPypiCheck",
            ]

            blocked = self._run(release, cwd=root, timeout=120)
            out = blocked.stdout + blocked.stderr
            self.assertNotEqual(blocked.returncode, 0, out)
            self.assertIn("m3trik/scripts differs from origin/main", out)
            # The guard must fire BEFORE the review gate.
            self.assertNotIn("No review receipt", out)

            # Pushing m3trik clears the guard; the run proceeds to the
            # review gate (the next pre-pass in line).
            self._git(m3trik, "add", "-A")
            self._git(m3trik, "commit", "-m", "generator change")
            self._git(m3trik, "push", "origin", "main")

            cleared = self._run(release, cwd=root, timeout=120)
            out2 = cleared.stdout + cleared.stderr
            self.assertIn(
                "m3trik-first guard: m3trik/scripts matches origin/main", out2
            )
            self.assertNotIn("m3trik/scripts differs from origin/main", out2)
            self.assertIn("No review receipt", out2)


    # ------------------------------------------------------------------
    # Release-gate / PR-gate helpers
    # ------------------------------------------------------------------

    def _push_cmd(self, root: Path, *extra):
        """The `powershell -File push.ps1 -Root <root>` prefix every run shares."""
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(M3TRIK_DIR / "push.ps1"),
            "-Root",
            str(root),
            *extra,
        ]

    def _retarget_origin_to_github(self, repo: Path, origin: Path, slug: str):
        """Report a github.com origin URL while transports stay local.

        push.ps1 derives the `gh` repo slug from `remote.origin.url`, so PR mode
        is unreachable from a file-path origin. `url.<local>.insteadOf` rewrites
        the URL at transport time only: the script reads a real slug, while
        fetch/push still hit the temp bare repo and the test stays offline.
        """
        url = f"https://github.com/{slug}.git"
        self._git(repo, "config", f"url.{origin.as_posix()}.insteadOf", url)
        self._git(repo, "remote", "set-url", "origin", url)

    # A `gh` stand-in. Dispatches on the subcommand and, for `pr view`, on
    # whether the --json field list asks for mergedAt (the merge-wait probe) or
    # the gate fields. Responses come from sibling files so each test can pick a
    # scenario without rewriting the shim. .cmd + CRLF: cmd.exe rejects LF-only
    # batch files, and PATHEXT resolution makes `gh` find it from PowerShell.
    _GH_SHIM_LINES = [
        "@echo off",
        "setlocal",
        'set "ARGS=%*"',
        'if "%1"=="auth" exit /b 0',
        'if "%2"=="list" goto :prlist',
        'if "%2"=="create" goto :prcreate',
        'if "%2"=="merge" exit /b 0',
        'if "%2"=="view" goto :prview',
        "exit /b 0",
        "",
        ":prlist",
        'type "%~dp0pr_list.json"',
        "exit /b 0",
        "",
        ":prcreate",
        'type "%~dp0pr_create.txt"',
        "exit /b 0",
        "",
        ":prview",
        'echo %ARGS% | findstr /C:"mergedAt" >nul',
        "if errorlevel 1 goto :prgates",
        'type "%~dp0pr_merged.json"',
        "exit /b 0",
        "",
        ":prgates",
        'type "%~dp0pr_gates.json"',
        "exit /b 0",
        "",
    ]

    def _install_fake_gh(self, root: Path, gates: str, slug: str = "m3trik/pythontk"):
        """Put a scripted `gh` first on PATH and return the env to run with."""
        bin_dir = root / "_bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "gh.cmd").write_bytes(
            ("\r\n".join(self._GH_SHIM_LINES)).encode("ascii")
        )
        (bin_dir / "pr_list.json").write_text("[]", encoding="ascii")
        (bin_dir / "pr_create.txt").write_text(
            f"https://github.com/{slug}/pull/7", encoding="ascii"
        )
        (bin_dir / "pr_gates.json").write_text(gates, encoding="ascii")
        (bin_dir / "pr_merged.json").write_text(
            '{"state":"MERGED","mergedAt":"2026-08-17T00:00:00Z"}', encoding="ascii"
        )
        env = os.environ.copy()
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        return env

    def _pr_release_repo(self, root: Path):
        """A pythontk repo with a real dev delta and a github.com origin."""
        repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
        self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
        self._git(repo, "checkout", "dev")
        (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-m", "feature")
        self._git(repo, "push", "origin", "dev")
        return repo, origin

    def _pr_release_cmd(self, root: Path):
        return self._push_cmd(
            root,
            "-Packages",
            "pythontk",
            "-Strict",
            "-Merge",
            "-SkipReview",
            "-SkipBuild",
            "-SkipWorkflowWait",
            "-SkipPypiCheck",
            "-UsePR",
            "-PRGateTimeoutSeconds",
            "0",
        )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_tests_receipt_is_a_hard_release_gate(self):
        """A "review" receipt alone must NOT release: "tests" is enforced too.

        mayatk and blendertk ship no pull_request-triggered tests workflow, so
        the local "tests" receipt is the only evidence that anything ever ran
        their suite against the tree being published. Recording it must clear
        the gate, or the receipt is decorative.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")

            base = self._push_cmd(root, "-Packages", "pythontk")
            release = base + [
                "-Strict",
                "-Merge",
                "-SkipBuild",
                "-SkipWorkflowWait",
                "-SkipPypiCheck",
            ]

            reviewed = self._run(base + ["-RecordReceipt", "review"], cwd=root)
            self.assertEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)

            blocked = self._run(release, cwd=root, timeout=120)
            out = blocked.stdout + blocked.stderr
            self.assertNotEqual(blocked.returncode, 0, out)
            self.assertIn("No tests receipt for the current tree", out)
            # The review half was satisfied, so only the tests half may complain.
            self.assertNotIn("No review receipt for the current tree", out)

            tested = self._run(base + ["-RecordReceipt", "tests"], cwd=root)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

            passed = self._run(release, cwd=root, timeout=180)
            out2 = passed.stdout + passed.stderr
            self.assertEqual(passed.returncode, 0, out2)
            self.assertIn("Tests receipt valid", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_skip_tests_receipt_bypasses_loudly(self):
        """-SkipTestsReceipt is the escape hatch, and it must be unmissable.

        A silent bypass switch is worse than no gate: the operator loses the one
        signal that the tree is untested. The run proceeds, but only after
        announcing what is being given up.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")

            base = self._push_cmd(root, "-Packages", "pythontk")
            recorded = self._run(base + ["-RecordReceipt", "review"], cwd=root)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            bypassed = self._run(
                base
                + [
                    "-Strict",
                    "-Merge",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                    "-SkipTestsReceipt",
                ],
                cwd=root,
                timeout=180,
            )
            out = bypassed.stdout + bypassed.stderr
            self.assertEqual(bypassed.returncode, 0, out)
            self.assertIn("TESTS RECEIPT GATE BYPASSED", out)
            self.assertIn("Releasing UNTESTED trees", out)
            self.assertNotIn("No tests receipt for the current tree", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_dev_bump_commit_is_not_marked_skip_ci(self):
        """The auto-bump commit heads the branch the release PR is opened from.

        GitHub skips every workflow for a "[skip ci]" head commit, so tagging it
        meant tests.yml never ran on any release PR and -UsePR merged code no
        check had ever seen.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            # Uncommitted: Sync-DevWithOrigin absorbs it, which is what puts the
            # branch ahead of origin/dev and triggers the auto-bump.
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._push_cmd(
                    root,
                    "-Packages",
                    "pythontk",
                    "-Strict",
                    "-Merge",
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ),
                cwd=root,
                timeout=180,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)

            subjects = self._git(origin, "log", "--pretty=%s", "dev").stdout
            self.assertIn("Bump version to 0.1.1", subjects, out)
            self.assertNotIn("Bump version to 0.1.1 [skip ci]", subjects, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pin_sync_commit_has_no_skip_ci(self):
        """The pin-sync bump must NOT carry "[skip ci]".

        For a package whose dependencies cascaded, this commit IS the version
        bump, so it heads the release PR. GitHub skips every workflow for a
        [skip ci] head, so the tag stripped the required check off the PR the
        gate exists to hold -- and once required status checks went live
        (2026-08-17) that PR could never merge at all. Nothing on dev triggers
        on push, so the tag never suppressed anything where it was made.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            _, uitk_origin = self._init_dummy_repo(
                root, "uitk", "1.0.51", ["qtpy", "pythontk==0.0.1"]
            )

            result = self._run(
                self._push_cmd(
                    root,
                    "-Packages",
                    "uitk",
                    "-Strict",
                    "-Merge",
                    "-SkipReview",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                    "-SkipPypiCheck",
                ),
                cwd=root,
                timeout=180,
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Synced dependencies & bumped version", out)

            subjects = self._git(uitk_origin, "log", "--pretty=%s", "dev").stdout
            self.assertIn(
                "Update dependencies & bump version to 1.0.52", subjects, out
            )
            self.assertNotIn(
                "[skip ci]",
                subjects,
                "a [skip ci] head strips the required check off the release PR",
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_fails_when_pr_has_no_check_runs(self):
        """Auto-merge on a PR with zero checks is a direct merge in disguise.

        GitHub lands it the instant auto-merge is armed, so -UsePR reported that
        it respected a test gate that never existed. It must refuse instead.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root, '{"mergeStateStatus":"CLEAN","statusCheckRollup":[]}'
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=180, env=env
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("ZERO check runs", out)
            self.assertIn("skip ci", out)  # names the cause
            self.assertNotIn("PR #7 merged", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_fails_when_merge_state_is_blocked(self):
        """BLOCKED means auto-merge can never fire (missing required review).

        The old code armed auto-merge and then waited out
        -PRMergeTimeoutSeconds (30 minutes) before reporting a generic timeout.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","conclusion":"SUCCESS"}]}',
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=180, env=env
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("mergeStateStatus=BLOCKED", out)
            self.assertNotIn("PR #7 merged", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_proceeds_when_pr_is_actually_gated(self):
        """The counterweight: a genuinely gated PR must still release.

        Without this, the two refusals above could be satisfied by a gate that
        rejects everything.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"CLEAN",'
                '"statusCheckRollup":[{"name":"test","conclusion":"SUCCESS"}]}',
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("gated by 1 check run", out)
            self.assertIn("PR #7 merged", out)


    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_waits_out_blocked_while_checks_still_run(self):
        """BLOCKED while a check is still running is what auto-merge is FOR.

        GitHub reports BLOCKED for a PR whose required check has not finished
        yet. Treating that as fatal would break every release the moment a
        required status check is configured, so only a BLOCKED PR whose checks
        have all settled (missing approval / failed check) may refuse.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","status":"IN_PROGRESS",'
                '"conclusion":null}]}',
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("still running", out)
            self.assertIn("PR #7 merged", out)

    def test_zero_poll_interval_is_refused_at_bind_time(self):
        """A 0 poll interval must be rejected, never accepted into a spin loop.

        `$elapsed += $PRGatePollSeconds` is the ONLY clock in Test-PRReleaseGate's
        check-run wait, so `-PRGatePollSeconds 0` re-probed `gh pr view` forever
        instead of ever reaching the "ZERO check runs" refusal. Wait-ForWorkflow
        advances on -WorkflowPollSeconds the same way. Both must fail at parameter
        binding, before the script touches a single repo.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for flag in ("-PRGatePollSeconds", "-WorkflowPollSeconds"):
                with self.subTest(flag=flag):
                    r = self._run(
                        self._push_cmd(
                            root, flag, "0", "-Packages", "pythontk", "-DryRun"
                        ),
                        cwd=root,
                        timeout=120,
                    )
                    out = r.stdout + r.stderr
                    self.assertNotEqual(r.returncode, 0, out)
                    self.assertIn(flag.lstrip("-"), out)
                    self.assertNotIn("[DRY RUN MODE]", out)


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

    def test_versions_are_valid_semver(self):
        """All package versions should be valid semantic versions"""
        semver_pattern = r"^\d+\.\d+\.\d+$"

        for pkg in PACKAGES:
            init_file = ROOT / pkg / pkg / "__init__.py"
            content = init_file.read_text(encoding="utf-8")
            version = version_in(content)
            self.assertIsNotNone(version, f"{pkg} missing __version__")

            self.assertRegex(
                version,
                semver_pattern,
                f"{pkg} version '{version}' is not valid semver (X.Y.Z)",
            )


class TestPyprojectPins(unittest.TestCase):
    """Validate internal pyproject.toml pins remain installable.

    Internal deps are pinned as `"pkg>=X.Y.Z"` entries in each package's
    `dependencies` list — the same format push.ps1's
    Sync-PyProjectDepsToLocalVersions reads/writes. A regression here can
    break installs.
    """

    def _read_pins(self, pkg: str) -> dict:
        import re

        toml_file = ROOT / pkg / "pyproject.toml"
        content = toml_file.read_text(encoding="utf-8")
        return dict(re.findall(r'"([A-Za-z0-9_.-]+)>=([0-9.]+)"', content))

    def _workspace_versions(self, pkg: str) -> set:
        """Every ``__version__`` the workspace holds for *pkg*.

        The working tree and ``origin/dev`` both count: the release bot bumps
        the branch, so a downstream's freshly synced pin can name a version
        that exists only there until the upload lands.

        Returns:
            set: version strings; empty when the package or ref is unreadable.
        """
        import subprocess as sp

        found = set()
        init = ROOT / pkg / pkg / "__init__.py"
        sources = []
        if init.is_file():
            sources.append(init.read_text(encoding="utf-8", errors="replace"))
        try:
            r = sp.run(
                ["git", "-C", str(ROOT / pkg), "show", f"origin/dev:{pkg}/__init__.py"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                sources.append(r.stdout)
        except Exception:  # noqa: BLE001 - absent git/ref is simply no candidate
            pass

        for text in sources:
            version = version_in(text)
            if version:
                found.add(version)
        return found

    def test_internal_pins_present(self):
        expectations = {
            "uitk": ["pythontk"],
            "mayatk": ["pythontk", "uitk"],
            "blendertk": ["pythontk", "uitk"],
            "tentacle": ["pythontk", "uitk", "mayatk", "blendertk"],
        }

        for pkg, deps in expectations.items():
            pins = self._read_pins(pkg)
            for dep in deps:
                self.assertIn(dep, pins, f"{pkg} missing pin for {dep}")

    def test_pinned_versions_exist_on_pypi(self):
        """Ensure pinned internal versions are installable.

        A pin that is not on PyPI *yet* but names a version the workspace holds
        (working tree or ``origin/dev``) is this cascade's own in-flight state:
        push.ps1 writes each pin from the sibling's local version and publishes
        upstream-first, so the gap closes on upload. Failing on it would red the
        suite for the length of every release -- including the run that records
        the ``tests`` receipt. A pin naming a version nobody has is still a
        failure, because that one can never resolve.

        Skips if pip cannot query indexes (offline environments).
        """

        pinned = []
        for pkg in ["uitk", "mayatk", "blendertk", "tentacle"]:
            pins = self._read_pins(pkg)
            for dep in ["pythontk", "uitk", "mayatk", "blendertk"]:
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
            if ver in out:
                continue

            pending = self._workspace_versions(dep)
            self.assertIn(
                ver,
                pending,
                f"{dep} pinned version {ver} is not on PyPI and is not a version "
                f"this workspace holds ({sorted(pending) or 'none found'}) -- "
                f"nothing can satisfy that pin",
            )
            print(
                f"  [pending publish] {dep}>={ver} not yet on PyPI; the workspace "
                f"holds it, so the cascade is expected to upload it"
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
