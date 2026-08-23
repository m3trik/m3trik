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
import time
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
        # The initial version is a PUBLISHED release, as every real package's
        # main is: tagged v<version>. Under -SkipPypiCheck the highest v* tag on
        # origin is the only source of "what is published", so the release
        # version steps from it (0.1.0 -> 0.1.1) exactly as a live run steps
        # from the PyPI index.
        self._git(repo, "tag", "-a", f"v{version}", "-m", f"{name} v{version}")
        self._git(repo, "checkout", "-b", "dev")

        # Create bare origin remote
        remotes = root / "_remotes"
        remotes.mkdir(exist_ok=True)
        origin = remotes / f"{name}.git"
        self._git(remotes, "init", "--bare", str(origin))

        self._git(repo, "remote", "add", "origin", str(origin))
        self._git(repo, "push", "-u", "origin", "main")
        self._git(repo, "push", "-u", "origin", "dev")
        self._git(repo, "push", "origin", f"v{version}")

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
    def test_hand_bumped_version_on_dev_is_honored(self):
        """A __version__ ABOVE the published one is a deliberate minor/major bump.

        With the bump-dev bot retired, nothing but a human edits the version on
        dev — so a version-only delta is an artifact change, and the release
        carries that version instead of stepping the patch from the tag.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            self._git(repo, "checkout", "dev")
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.2.0"\n',
                encoding="utf-8",
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "minor bump: new public API")
            self._git(repo, "push", "origin", "dev")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Delta: artifact", out)
            # The operator's own commit already IS the release state (version
            # set, no floors to ratchet), so no extra Release commit is made.
            self.assertIn("dev already carries Release 0.2.0", out)
            main_init = self._git(
                origin, "show", "main:pythontk/__init__.py"
            ).stdout
            self.assertIn('__version__ = "0.2.0"', main_init, out)
            tags = self._git(origin, "tag", "--list").stdout
            self.assertIn("v0.2.0", tags, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_merges_local_changes_when_origin_dev_is_sidecars_only(self):
        """Real local work must release even when origin/dev is ahead by sidecars.

        A run absorbs uncommitted local work as a LOCAL commit first (the push
        happens later), so the delta classifier must read local dev, not
        origin/dev — or it files the run under "rides along" and silently drops
        the release while still reporting success.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            # A registry refresh on origin/dev (rides-along class).
            (repo / "API_INDEX.md").write_text("# generated\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "chore: refresh API registry")
            self._git(repo, "push", "origin", "dev")

            # Real, not-yet-committed local work.
            (repo / "pythontk" / "feature.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Delta: artifact", out)
            self.assertIn("Merged and pushed to main", out)
            tree = self._git(origin, "ls-tree", "-r", "--name-only", "main").stdout
            self.assertIn("pythontk/feature.py", tree, out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_rides_along_delta_skips_merge(self):
        """Sidecars + CHANGELOG ahead of main: nothing to release, nothing to merge.

        None of those files ship in the wheel, and a registry/CHANGELOG-only
        PR would cost a full CI cycle to land content the next release carries
        anyway. No version is consumed and main is untouched.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            for name in (
                "API_INDEX.md",
                "API_REGISTRY.md",
                "API_REGISTRY.json",
                "API_CHANGES.md",
                "CHANGELOG.md",
            ):
                (repo / name).write_text("# generated\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "chore: refresh API registry")
            self._git(repo, "push", "origin", "dev")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Delta: rides-along", out)
            self.assertIn("rides along with the next release", out)
            tree = self._git(origin, "ls-tree", "-r", "--name-only", "main").stdout
            self.assertNotIn("API_INDEX.md", tree, out)
            self.assertNotIn("v0.1.1", self._git(origin, "tag", "--list").stdout)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_release_is_one_commit_one_version(self):
        """One release = one `Release X.Y.Z` commit = one version, stepped from the tag.

        Three bumpers used to act on every release and PyPI showed it
        (pythontk 0.9.26 -> 0.9.28 -> 0.9.30). Here: local 0.1.0 == tag 0.1.0,
        so the release is 0.1.1, exactly one Release commit carries it, and a
        re-run afterwards consumes nothing.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            (repo / "pythontk" / "feature.py").write_text("x = 1\n", encoding="utf-8")
            # A stub API-registry generator at the path Prepare invokes, so the
            # regen-inside-the-Release-commit path is exercised, not just the
            # version/pin half. It records its argv into the sidecar.
            gen = root / "m3trik" / "scripts" / "generate_api_registry.py"
            gen.parent.mkdir(parents=True)
            gen.write_text(
                "import sys, pathlib\n"
                "root = pathlib.Path(__file__).resolve().parents[2]  # as the real one\n"
                "(root / sys.argv[1] / 'API_INDEX.md').write_text('argv: ' + ' '.join(sys.argv[1:]) + '\\n')\n",
                encoding="utf-8",
            )

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.1'", out)

            subjects = self._git(origin, "log", "--pretty=%s", "main").stdout.splitlines()
            releases = [s for s in subjects if s.startswith("Release ")]
            self.assertEqual(releases, ["Release 0.1.1"], out)
            # The registry was regenerated for THIS package only, without the
            # cross-package shadow report, and rode in the Release commit.
            index = self._git(origin, "show", "main:API_INDEX.md").stdout
            self.assertIn("argv: pythontk --no-shadows", index, out)
            self.assertFalse(
                [s for s in subjects if "Bump version" in s or "bump version" in s],
                f"a legacy bump commit slipped in:\n{subjects}",
            )
            main_init = self._git(origin, "show", "main:pythontk/__init__.py").stdout
            self.assertIn('__version__ = "0.1.1"', main_init, out)
            self.assertIn("v0.1.1", self._git(origin, "tag", "--list").stdout, out)

            # Re-run: dev == main, nothing to do, no version consumed.
            again = self._run(self._release_cmd(root, "pythontk"), cwd=root, timeout=180)
            out2 = again.stdout + again.stderr
            self.assertEqual(again.returncode, 0, out2)
            self.assertIn("No changes to push and fully merged", out2)
            self.assertNotIn("Release 0.1.2", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_release_version_steps_from_published_not_from_the_file(self):
        """The release version comes from what is PUBLISHED (the tag here).

        local == published -> step the patch; local BELOW published (a stale
        checkout) -> step from published, never re-release the stale number.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            # Published moved on without this checkout: tag v0.1.3 on origin.
            self._git(repo, "tag", "-a", "v0.1.3", "-m", "pythontk v0.1.3")
            self._git(repo, "push", "origin", "v0.1.3")
            self._git(repo, "checkout", "dev")
            (repo / "pythontk" / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.4'", out)
            self.assertNotIn("Release 0.1.1", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_syncs_internal_pyproject_pins(self):
        """Internal floors ratchet to the PUBLISHED upstream and cascade downstream.

        pythontk is published at 0.7.51 (tag). Releasing uitk pins it there,
        releases uitk as 1.0.52, and the cascade extras (mayatk, blendertk,
        tentacle) pin uitk>=1.0.52 — all from tags, no network.
        """
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

            result = self._run(
                self._release_cmd(root, "uitk"), cwd=root, timeout=300
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Pinned pythontk>=0.7.51", out)
            self.assertIn("Committed 'Release 1.0.52'", out)

            toml = (root / "uitk" / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('"pythontk>=0.7.51"', toml)
            # The cascade synced the parallel blendertk branch to uitk's NEW version.
            btk_toml = (root / "blendertk" / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('"pythontk>=0.7.51"', btk_toml)
            self.assertIn('"uitk>=1.0.52"', btk_toml)
            # A pin-only delta is an artifact delta: blendertk got its own release.
            self.assertIn("Committed 'Release 0.5.1'", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_release_commit_is_not_marked_skip_ci(self):
        """The Release commit heads the branch the release PR is opened from.

        GitHub skips every workflow for a "[skip ci]" head commit, so tagging it
        would mean tests.yml never runs on any release PR and -UsePR merges code
        no check has ever seen.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            _, uitk_origin = self._init_dummy_repo(
                root, "uitk", "1.0.51", ["qtpy", "pythontk==0.0.1"]
            )

            result = self._run(
                self._release_cmd(root, "uitk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)

            subjects = self._git(uitk_origin, "log", "--pretty=%s", "dev").stdout
            self.assertIn("Release 1.0.52", subjects, out)
            self.assertNotIn(
                "[skip ci]",
                subjects,
                "a [skip ci] head strips the required check off the release PR",
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_refuses_to_release_while_behind_origin_dev(self):
        """Behind origin/dev must fail BEFORE any tree is mutated.

        Every other rev-list in push.ps1 measures origin/dev..dev (ahead);
        nothing measured the reverse, so a repo the bump-version / API-registry
        bots had moved on looked pristine until the push failed -- with the
        trees already rewritten. Measured 2026-08-19: all five cascade repos sat
        2 commits back simultaneously and only a manual check caught it.

        -SkipReview is passed deliberately: that flag waives the review RECEIPT,
        and being behind is a fact about the remote no review can settle, so the
        check has to survive it.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _origin = self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])

            # Advance origin/dev, then rewind the local branch off it: the exact
            # shape a bot's "Bump version ... [skip ci]" commit leaves behind.
            (repo / "BOTFILE.md").write_text("bot commit", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "Bump version to 0.7.52 [skip ci]")
            self._git(repo, "push", "origin", "dev")
            self._git(repo, "reset", "--hard", "HEAD~1")

            before = (repo / "pyproject.toml").read_text(encoding="utf-8")

            result = self._run(
                [
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
                    "-SkipReview",
                    "-DryRun",
                    "-SkipBuild",
                    "-SkipWorkflowWait",
                ],
                cwd=root,
                timeout=120,
            )
            out = result.stdout + result.stderr

            self.assertEqual(result.returncode, 1, out)
            self.assertIn("behind", out.lower(), out)
            # Failing free is the whole point of a pre-pass: nothing rewritten.
            self.assertEqual(
                before,
                (repo / "pyproject.toml").read_text(encoding="utf-8"),
                "pyproject was mutated even though the preflight failed: " + out,
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pin_sync_never_lowers_a_declared_floor(self):
        """A floor ABOVE the version being pinned must survive the sync.

        The version map is what is PUBLISHED (here: the v* tags), so a run
        that does NOT include the upstream would
        otherwise rewrite a deliberately raised floor back to the old release --
        reintroducing exactly the break the raise existed to prevent. Measured
        2026-08-19 on mayatk's ``pythontk>=0.9.25``, which is needed because
        ``task_manager`` reads a 0.9.25 attribute in a CLASS BODY (an
        AttributeError at import, not at first use).
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            # uitk declares a floor ABOVE pythontk's published version, the way a
            # package does when its code needs an unreleased upstream.
            self._init_dummy_repo(root, "uitk", "1.0.51", ["qtpy", "pythontk>=0.7.96"])

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
            self.assertEqual(result.returncode, 0, out)

            toml = (root / "uitk" / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn(
                '"pythontk>=0.7.96"',
                toml,
                f"the sync lowered a declared floor\n{out}",
            )
            self.assertNotIn('"pythontk>=0.7.51"', toml, out)

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

    def test_tree_hash_is_stable_across_host_console_encodings(self):
        """Get-TreeHash must not depend on the host's console encoding.

        PowerShell DECODES a native command's stdout with
        ``[Console]::OutputEncoding``, so before the 2026-08-20 pin the same tree
        hashed differently per host: a receipt recorded from an interactive
        console failed the gate under ``Start-Process -WindowStyle Hidden``.
        Measured on the real pythontk tree at the time: the pre-fix code produced
        three DIFFERENT hashes under UTF-8 / Windows-1252 / CP437.

        The non-ASCII has to reach ``git diff HEAD`` to exercise the decode, so
        the file is committed as ASCII and then rewritten with em-dashes. stdout
        is captured (redirected) here, which is the other half of the reported
        repro.
        """
        if not self._have_git():
            self.skipTest("git not available")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])

            notes = repo / "CHANGELOG.md"
            notes.write_text("# Changelog\n\n- plain ascii line\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "changelog")
            # Uncommitted non-ASCII: em-dashes and an arrow, exactly what the real
            # CHANGELOG.md carries and what decoded differently per host.
            notes.write_text(
                "# Changelog — notes\n\n- a — b → c\n- café\n",
                encoding="utf-8",
            )

            script = M3TRIK_DIR / "push.ps1"
            hashes = {}
            enc = "[Console]::OutputEncoding="
            for label, setup in (
                ("utf8", enc + "[Text.UTF8Encoding]::new($false)"),
                ("ansi", enc + "[Text.Encoding]::GetEncoding(1252)"),
                ("cp437", enc + "[Text.Encoding]::GetEncoding(437)"),
            ):
                result = self._run(
                    [
                        "powershell",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-NoProfile",
                        "-Command",
                        f"{setup}; & '{script}' -ShowReceipts "
                        f"-Packages pythontk -Root '{root}'",
                    ],
                    cwd=root,
                    timeout=120,
                )
                out = result.stdout + result.stderr
                found = re.search(r"pythontk@([0-9a-f]{12})", out)
                self.assertIsNotNone(found, f"no tree hash under {label}: {out}")
                hashes[label] = found.group(1)

            self.assertEqual(
                len(set(hashes.values())),
                1,
                f"tree hash varies with console encoding: {hashes}",
            )

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
    def _stub_parity_scripts(self, root, sweep_rc=0):
        """Stub the two parity generators where Prepare looks for them.

        Each records that it ran (so a package WITHOUT docs/PARITY_AUDIT.md can
        be shown not to invoke them) and writes its artifact into the tentacle
        fixture, as the real tentacle-specific generators do.
        """
        scripts = root / "m3trik" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "compare_panel_surface.py").write_text(
            "import sys, pathlib\n"
            "root = pathlib.Path(__file__).resolve().parents[2]\n"
            "(root / '_sweep_ran').write_text(' '.join(sys.argv[1:]))\n"
            "docs = root / 'tentacle' / 'docs'\n"
            "docs.mkdir(parents=True, exist_ok=True)\n"
            "(docs / 'PARITY_SURFACE.md').write_text('swept\\n')\n"
            f"sys.exit({sweep_rc})\n",
            encoding="utf-8",
        )
        (scripts / "generate_parity_audit.py").write_text(
            "import pathlib\n"
            "root = pathlib.Path(__file__).resolve().parents[2]\n"
            "(root / '_audit_ran').write_text('yes')\n"
            "docs = root / 'tentacle' / 'docs'\n"
            "docs.mkdir(parents=True, exist_ok=True)\n"
            "(docs / 'PARITY_AUDIT.md').write_text('audited\\n')\n",
            encoding="utf-8",
        )
        return scripts

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_parity_artifacts_ride_in_the_release_commit(self):
        """A release regenerates the parity pair, as it does the API registry.

        tentacle's `parity` job is not a REQUIRED check, so a stale artifact
        merges -- and then skips the publish, because publish.yml gates on the
        whole reusable tests.yml (`needs: test`). Measured 2026-08-23 on
        tentacletk 0.13.76: merged-but-unpublished, cascade aborted behind it.
        Regenerating inside the Release commit makes the check green by
        construction, which is the only way the two gates can agree.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "tentacle", "0.1.0", [])
            self._stub_parity_scripts(root)
            self._git(repo, "checkout", "dev")
            docs = repo / "docs"
            docs.mkdir(exist_ok=True)
            (docs / "PARITY_AUDIT.md").write_text("stale\n", encoding="utf-8")
            (docs / "PARITY_SURFACE.md").write_text("stale\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "parity artifacts")
            (repo / "tentacle" / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._release_cmd(root, "tentacle"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.1'", out)
            # Both generators ran, and BOTH refreshed artifacts are on main --
            # not left dirty for the next run to sweep up.
            self.assertTrue((root / "_sweep_ran").is_file(), out)
            self.assertIn("--all --write", (root / "_sweep_ran").read_text())
            self.assertTrue((root / "_audit_ran").is_file(), out)
            self.assertEqual(
                self._git(origin, "show", "main:docs/PARITY_AUDIT.md").stdout.strip(),
                "audited",
                out,
            )
            self.assertEqual(
                self._git(origin, "show", "main:docs/PARITY_SURFACE.md").stdout.strip(),
                "swept",
                out,
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_untriaged_parity_sweep_fails_before_anything_is_pushed(self):
        """The sweep is a hard gate, and it fails while a failure is still free.

        compare_panel_surface.py exits 1 on untriaged deltas. Catching that in
        Prepare costs seconds; the same failure reaching CI costs a merged PR
        whose publish never runs.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "tentacle", "0.1.0", [])
            self._stub_parity_scripts(root, sweep_rc=1)
            self._git(repo, "checkout", "dev")
            docs = repo / "docs"
            docs.mkdir(exist_ok=True)
            (docs / "PARITY_AUDIT.md").write_text("stale\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "parity audit")
            (repo / "tentacle" / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._release_cmd(root, "tentacle"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("Parity sweep FAILS", out)
            self.assertIn("parity_map.py", out)
            # Nothing reached the remote: no Release commit, no tag.
            subjects = self._git(origin, "log", "--pretty=%s", "main").stdout
            self.assertNotIn("Release 0.1.1", subjects)
            self.assertNotIn("v0.1.1", self._git(origin, "tag", "--list").stdout)
            # ...and the audit generator never ran behind the failed sweep.
            self.assertFalse((root / "_audit_ran").exists(), out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_dirty_engine_tree_refuses_the_parity_regen(self):
        """The parity pair derives from mayatk + blendertk SOURCE.

        Regenerating over another session's uncommitted engine work would bake
        it into what this release publishes -- the same trap that makes a
        registry refresh during a concurrent edit unsafe. Refuse, and name the
        tree, rather than produce a plausible-looking artifact.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "tentacle", "0.1.0", [])
            self._stub_parity_scripts(root)
            engine = root / "mayatk"
            engine.mkdir(parents=True, exist_ok=True)
            self._git(engine, "init")
            self._git(engine, "config", "user.email", "ci@example.com")
            self._git(engine, "config", "user.name", "CI")
            (engine / "keep.py").write_text("x = 1\n", encoding="utf-8")
            self._git(engine, "add", "-A")
            self._git(engine, "commit", "-m", "init")
            (engine / "wip.py").write_text("half a feature\n", encoding="utf-8")

            self._git(repo, "checkout", "dev")
            docs = repo / "docs"
            docs.mkdir(exist_ok=True)
            (docs / "PARITY_AUDIT.md").write_text("stale\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "parity audit")
            (repo / "tentacle" / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._release_cmd(root, "tentacle"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("mayatk", out)
            self.assertIn("dirty", out)
            self.assertFalse((root / "_sweep_ran").exists(), out)
            self.assertNotIn("v0.1.1", self._git(origin, "tag", "--list").stdout)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_a_package_without_the_parity_artifact_never_runs_the_generators(self):
        """Keyed off the artifact, not a hardcoded package name.

        Only tentacle carries docs/PARITY_AUDIT.md; every other package must
        release without paying for -- or being blocked by -- a sweep that says
        nothing about it.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", [])
            self._stub_parity_scripts(root, sweep_rc=1)  # would fail if invoked
            self._git(repo, "checkout", "dev")
            (repo / "pythontk" / "feature.py").write_text("x = 1\n", encoding="utf-8")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.1'", out)
            self.assertFalse((root / "_sweep_ran").exists(), out)
            self.assertFalse((root / "_audit_ran").exists(), out)

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

    def _release_cmd(self, root: Path, package: str, *extra):
        """A Strict+Merge direct-merge release with every network gate off.

        Versions resolve from the fixture's v* tags (-SkipPypiCheck), so the
        run is deterministic and offline.
        """
        return self._push_cmd(
            root,
            "-Packages",
            package,
            "-Strict",
            "-Merge",
            "-SkipReview",
            "-SkipBuild",
            "-SkipWorkflowWait",
            "-SkipPypiCheck",
            *extra,
        )

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

    # A `gh` stand-in. Dispatches on the subcommand and, for `pr view`, on which
    # --json fields are asked for: mergedAt (the merge-wait probe),
    # autoMergeRequest (the arm-once probe) or the gate fields. Responses come
    # from sibling files so each test can pick a scenario without rewriting the
    # shim; a NUMBERED file (`pr_gates.2.json`) answers the Nth call of that
    # probe, so a test can script "pending for two polls, then red". Every call
    # is appended to gh_calls.log. `release create` copies the --notes-file at
    # call time, because push.ps1 deletes the temp file in `finally`.
    # .cmd + CRLF: cmd.exe rejects LF-only batch files, and PATHEXT resolution
    # makes `gh` find it from PowerShell.
    _GH_SHIM_LINES = [
        "@echo off",
        "setlocal",
        # Captured ONCE, in the main body: inside a `call :label` subroutine %0 is the
        # LABEL, so %HERE% there resolves against the CWD -- and push.ps1 changes CWD
        # between gh calls (Push-Location into each repo).
        'set "HERE=%~dp0"',
        'set "ARGS=%*"',
        '>>"%HERE%gh_calls.log" echo %ARGS%',
        'if "%1"=="auth" exit /b 0',
        'if "%1"=="release" goto :release',
        'if "%1"=="run" goto :runlist',
        'if "%1"=="workflow" exit /b 0',
        'if "%2"=="list" goto :prlist',
        'if "%2"=="create" goto :prcreate',
        'if "%2"=="merge" exit /b 0',
        'if "%2"=="view" goto :prview',
        "exit /b 0",
        "",
        ":prlist",
        'type "%HERE%pr_list.json"',
        "exit /b 0",
        "",
        ":prcreate",
        'if exist "%HERE%pr_create_fails" exit /b 1',
        'type "%HERE%pr_create.txt"',
        "exit /b 0",
        "",
        ":prview",
        'echo %ARGS% | findstr /C:"mergedAt" >nul',
        "if not errorlevel 1 goto :prmerged",
        'echo %ARGS% | findstr /C:"autoMergeRequest" >nul',
        "if not errorlevel 1 goto :prarmed",
        "goto :prgates",
        "",
        ":prmerged",
        "call :nth merged_calls",
        'if exist "%HERE%pr_merged.%N%.json" (type "%HERE%pr_merged.%N%.json") else (type "%HERE%pr_merged.json")',
        "exit /b 0",
        "",
        ":prgates",
        "call :nth gates_calls",
        'if exist "%HERE%pr_gates.%N%.json" (type "%HERE%pr_gates.%N%.json") else (type "%HERE%pr_gates.json")',
        "exit /b 0",
        "",
        ":prarmed",
        'if exist "%HERE%pr_armed.json" (type "%HERE%pr_armed.json") else (echo {"autoMergeRequest":null})',
        "exit /b 0",
        "",
        ":release",
        'if "%2"=="view" (',
        '  if exist "%HERE%release_exists" exit /b 0',
        "  exit /b 1",
        ")",
        'if "%2"=="create" (',
        "  call :copynotes %*",
        '  >"%HERE%release_exists" echo 1',
        "  exit /b 0",
        ")",
        "exit /b 0",
        "",
        ":runlist",
        'if exist "%HERE%runs.json" (type "%HERE%runs.json") else (echo [])',
        "exit /b 0",
        "",
        ":copynotes",
        'if "%~1"=="" exit /b 0',
        'if "%~1"=="--notes-file" (',
        '  copy /y "%~2" "%HERE%release_notes.txt" >nul',
        "  exit /b 0",
        ")",
        "shift",
        "goto :copynotes",
        "",
        ":nth",
        "set N=0",
        'if exist "%HERE%%1" set /p N=<"%HERE%%1"',
        "set /a N+=1",
        '>"%HERE%%1" echo %N%',
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

    def _gh_calls(self, root: Path) -> str:
        log = root / "_bin" / "gh_calls.log"
        return log.read_text(encoding="ascii", errors="replace") if log.exists() else ""

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

    def _pr_release_cmd(self, root: Path, *extra):
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
            *extra,
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
            # Counterweight to test_pr_mode_surfaces_a_failing_non_required_check:
            # an all-green rollup must not trip the failing-check report.
            self.assertNotIn("reporting FAILURE", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_surfaces_a_failing_non_required_check(self):
        """A red NON-required check must be named, not silently shipped past.

        The gate counts check runs and reads mergeStateStatus; it never looked
        at a check's conclusion. A workflow that reports FAILURE but is not a
        required check leaves mergeStateStatus CLEAN, so auto-merge fires and
        the release prints green over a red PR. Measured 2026-08-20: "Validate
        Publish Chain" jobs validate-tentacle and summary were FAILURE on
        pythontk PRs #48 and #49; both released.

        The release must still PROCEED - blocking on a non-required check is
        branch protection's call, not push.ps1's - but the operator has to be
        told which checks are red.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"CLEAN",'
                '"statusCheckRollup":['
                '{"name":"test","conclusion":"SUCCESS"},'
                '{"name":"validate-tentacle","conclusion":"FAILURE"},'
                '{"name":"summary","conclusion":"FAILURE"}]}',
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            # Still releases: a non-required red check is not push.ps1's to block.
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("PR #7 merged", out)
            # ...but it is push.ps1's to REPORT, by name.
            self.assertIn("validate-tentacle", out)
            self.assertIn("summary", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_pr_mode_names_a_failing_check_while_others_still_run(self):
        """The BLOCKED-but-still-running path returns $true too, so it must report.

        The first cut of this report sat on the plain-success path only. A PR that
        is BLOCKED with a required check still running takes a different branch,
        proceeds all the same, and would have carried a red non-required check past
        unmentioned - which is the exact gap this reporting exists to close.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":['
                '{"name":"test","status":"IN_PROGRESS","conclusion":null},'
                '{"name":"validate-tentacle","conclusion":"FAILURE"}]}',
            )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("still running", out)
            self.assertIn("reporting FAILURE", out)
            self.assertIn("validate-tentacle", out)

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

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_dead_pr_fails_in_one_poll_and_names_the_check(self):
        """A settled red check is reported in ONE poll, not waited out.

        Measured 2026-08-23: uitk's required `test` failed at minute 17 and the
        old merge-wait loop (which read only state/mergedAt) sat on the dead PR
        for 13 more minutes to the 1800 s ceiling, then aborted three packages.
        Arm-time gate sees checks still running (passes); the first merge-wait
        poll sees them settled with `test` red -> merge-dead, by name, fast.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","status":"IN_PROGRESS","conclusion":null},'
                '{"name":"api-registry","conclusion":"SUCCESS"}]}',
            )
            b = root / "_bin"
            (b / "pr_merged.json").write_text('{"state":"OPEN","mergedAt":null}', encoding="ascii")
            # Gate probe #1 is the arm-time check (still running); from #2 on the
            # rollup is settled and red.
            (b / "pr_gates.2.json").write_text(
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","conclusion":"FAILURE"},'
                '{"name":"api-registry","conclusion":"SUCCESS"}]}',
                encoding="ascii",
            )
            (b / "pr_gates.3.json").write_bytes((b / "pr_gates.2.json").read_bytes())

            started = time.monotonic()
            result = self._run(
                self._pr_release_cmd(root, "-PRMergeTimeoutSeconds", "1800"),
                cwd=root,
                timeout=300,
                env=env,
            )
            elapsed = time.monotonic() - started
            out = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, out)
            self.assertIn("cannot merge: branch protection is holding it", out)
            self.assertIn("x test", out)
            self.assertIn("PR cannot merge", out)  # summary line
            self.assertLess(elapsed, 120, f"took {elapsed:.0f}s -- the dead PR was waited out\n{out}")

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_red_non_required_check_is_named_but_does_not_abort(self):
        """A red check that branch protection does not require must NOT abort
        the release - GitHub merges over it and so must the wait loop.

        Measured on the live repos: pythontk #48 and #49 both MERGED carrying
        settled FAILUREs on `summary` and `validate-tentacle`, because neither
        is a required context. Treating any red check as fatal would have
        aborted both cascades, and would contradict the arm-time gate, which
        deliberately reports these without blocking. mayatk/blendertk make it
        concrete: their required check is `static-analysis`, and both now carry
        extra non-required Qt/mock suites on every PR.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            # CLEAN (nothing is holding the merge) with one red non-required check.
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"CLEAN",'
                '"statusCheckRollup":[{"name":"static-analysis","conclusion":"SUCCESS"},'
                '{"name":"Qt-only suites (no Blender)","conclusion":"FAILURE"}]}',
            )
            b = root / "_bin"
            # OPEN for the first two merge probes, then merged - the auto-merge
            # GitHub performs over a non-required failure.
            for n in (1, 2):
                (b / f"pr_merged.{n}.json").write_text(
                    '{"state":"OPEN","mergedAt":null}', encoding="ascii"
                )

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=300, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("PR #7 merged", out)
            # Named, so it is never silent...
            self.assertIn("Qt-only suites (no Blender)", out)
            # ...but not fatal: no path may report it as unmergeable.
            self.assertNotIn("cannot merge", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_all_green_blocked_window_is_not_dead(self):
        """BLOCKED with every check green is a transient GitHub state, not death.

        The window between the last check going green and mergeStateStatus
        being recomputed is crossed on every successful release. Three polls of
        it, then MERGED, must succeed.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._pr_release_repo(root)
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","conclusion":"SUCCESS"}]}',
            )
            b = root / "_bin"
            # Arm-time gate: BLOCKED + 0 pending would be refused, so probe #1
            # shows the check still running; later probes are all-green BLOCKED.
            (b / "pr_gates.1.json").write_text(
                '{"mergeStateStatus":"BLOCKED",'
                '"statusCheckRollup":[{"name":"test","status":"IN_PROGRESS","conclusion":null}]}',
                encoding="ascii",
            )
            for n in (1, 2, 3):
                (b / f"pr_merged.{n}.json").write_text('{"state":"OPEN","mergedAt":null}', encoding="ascii")

            result = self._run(
                self._pr_release_cmd(root), cwd=root, timeout=300, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("PR #7 merged", out)
            self.assertNotIn("cannot merge", out)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_finalize_resumes_a_merged_but_untagged_release(self):
        """A release that merged in an aborted run is completed on the next run.

        origin/main already carries `Release 0.1.1` with no v0.1.1 tag (the
        2026-08-23 uitk state). The old script saw "local version unpublished ->
        no changes" and left it; now Finalize tags + cuts the Release at entry.
        Second half: tag present, Release absent -> the Release is created.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
            # Simulate the aborted run: Release 0.1.1 merged to main, untagged.
            self._git(repo, "checkout", "dev")
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n', encoding="utf-8"
            )
            (repo / "CHANGELOG.md").write_text("# log\n\n- 0.1.1: the fix\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "Release 0.1.1")
            self._git(repo, "checkout", "main")
            self._git(repo, "merge", "--no-ff", "dev", "-m", "Merge dev")
            self._git(repo, "push", "origin", "main")
            self._git(repo, "checkout", "dev")
            self._git(repo, "push", "origin", "dev")
            env = self._install_fake_gh(root, "{}")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Tagged v0.1.1", out)
            self.assertIn("GitHub Release v0.1.1 created", out)
            self.assertIn("Finalized a previously merged release", out)
            self.assertIn("v0.1.1", self._git(origin, "tag", "--list").stdout)
            notes = (root / "_bin" / "release_notes.txt").read_text(encoding="utf-8")
            self.assertIn("- 0.1.1: the fix", notes)

            # Idempotent: nothing left to do.
            again = self._run(self._release_cmd(root, "pythontk"), cwd=root, timeout=240, env=env)
            out2 = again.stdout + again.stderr
            self.assertEqual(again.returncode, 0, out2)
            self.assertNotIn("Tagged", out2)
            self.assertIn("No changes to push and fully merged", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_finalize_creates_a_missing_release_when_the_tag_exists(self):
        """`tag exists` must not hide `Release missing` (the tag is pushed first)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
            # main at 0.1.1, tagged (the tag push succeeded) but no Release (the
            # `gh release create` that follows it failed).
            (repo / "pythontk" / "__init__.py").write_text(
                '__package__ = "pythontk"\n__version__ = "0.1.1"\n', encoding="utf-8"
            )
            (repo / "CHANGELOG.md").write_text("# log\n\n- 0.1.1: the fix\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "Release 0.1.1")
            self._git(repo, "checkout", "main")
            self._git(repo, "merge", "--ff-only", "dev")
            self._git(repo, "tag", "-a", "v0.1.1", "-m", "v0.1.1")
            self._git(repo, "push", "origin", "main", "v0.1.1")
            self._git(repo, "checkout", "dev")
            self._git(repo, "push", "origin", "dev")
            env = self._install_fake_gh(root, "{}")  # release view -> absent

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertNotIn("Tagged", out)  # v0.1.1 already existed
            self.assertIn("GitHub Release v0.1.1 created", out)
            notes = (root / "_bin" / "release_notes.txt").read_text(encoding="utf-8")
            self.assertIn("- 0.1.1: the fix", notes)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_release_notes_are_changelog_lines_since_previous_tag(self):
        """The Release body is exactly the CHANGELOG lines added after the
        previous v* tag -- computed from tags, so it works after the merge too
        (the old origin/main..dev delta was empty the moment the PR landed)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
            self._git(repo, "checkout", "dev")
            (repo / "CHANGELOG.md").write_text("# log\n\n- old entry\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "old notes")
            self._git(repo, "checkout", "main")
            self._git(repo, "merge", "--ff-only", "dev")
            self._git(repo, "push", "origin", "main")
            # Re-point the published tag at the state that HAS the old entry, so
            # "since the previous tag" excludes it.
            self._git(repo, "tag", "-f", "-a", "v0.1.0", "-m", "v0.1.0")
            self._git(repo, "push", "-f", "origin", "v0.1.0")
            self._git(repo, "checkout", "dev")
            (repo / "CHANGELOG.md").write_text(
                "# log\n\n- NEW: the fix\n- NEW: the other fix\n- old entry\n", encoding="utf-8"
            )
            (repo / "pythontk" / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature + notes")
            self._git(repo, "push", "origin", "dev")
            env = self._install_fake_gh(root, "{}")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=240, env=env
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("GitHub Release v0.1.1 created", out)
            notes = (root / "_bin" / "release_notes.txt").read_text(encoding="utf-8")
            self.assertEqual(
                [ln for ln in notes.splitlines() if ln.strip()],
                ["- NEW: the fix", "- NEW: the other fix"],
                out,
            )

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_receipt_survives_a_sidecar_only_commit(self):
        """The receipt hash covers the SOURCE tree: generated sidecars are
        excluded, so a registry refresh (the bot's, or Prepare's) cannot void a
        receipt for code that has not moved -- while a source edit still does."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, _ = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            base = self._push_cmd(root, "-Packages", "pythontk")

            recorded = self._run(base + ["-RecordReceipt", "review,tests"], cwd=root, timeout=120)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            def shown():
                r = self._run(base + ["-ShowReceipts"], cwd=root, timeout=120)
                return r.stdout + r.stderr

            self.assertIn("review=VALID", shown())

            (repo / "API_INDEX.md").write_text("# regenerated\n", encoding="utf-8")
            (repo / "API_CHANGES.md").write_text("# regenerated\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "chore: refresh API registry")
            self.assertIn("review=VALID", shown(), "a sidecar-only commit voided the receipt")

            (repo / "pythontk" / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self.assertIn("no receipts for current tree", shown(), "a source edit did NOT void the receipt")

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_workflow_change_merges_but_does_not_release(self):
        """A `.github/**`-only delta MUST reach main (workflows only take effect
        there) but ships nothing: no version, no tag, summary `merged`."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._git(repo, "checkout", "dev")
            wf = repo / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "tests.yml").write_text("name: Tests\non: [pull_request]\n", encoding="utf-8")
            # test/ and docs/ (other than the wheel's readme) never ship either.
            (repo / "test").mkdir()
            (repo / "test" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
            (repo / "docs").mkdir()
            (repo / "docs" / "GUIDE.md").write_text("# guide\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "ci: add tests workflow, a test, a doc")
            self._git(repo, "push", "origin", "dev")

            result = self._run(
                self._release_cmd(root, "pythontk"), cwd=root, timeout=180
            )
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            self.assertIn("Delta: must-reach-main", out)
            self.assertIn("Merged to main (no version", out)
            tree = self._git(origin, "ls-tree", "-r", "--name-only", "main").stdout
            self.assertIn(".github/workflows/tests.yml", tree, out)
            main_init = self._git(origin, "show", "main:pythontk/__init__.py").stdout
            self.assertIn('__version__ = "0.1.0"', main_init, out)
            self.assertNotIn("v0.1.1", self._git(origin, "tag", "--list").stdout)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_prepare_rekeys_receipts_after_its_own_commit(self):
        """The Release commit changes the source hash (version line, pins) --
        push.ps1 carries the receipts across its own mechanical edit, so a
        re-run after an abort passes the gate without re-recording."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")
            base = self._push_cmd(root, "-Packages", "pythontk")
            recorded = self._run(base + ["-RecordReceipt", "review,tests"], cwd=root, timeout=120)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            # Abort AFTER the Release commit: PR creation fails.
            env = self._install_fake_gh(root, "{}")
            (root / "_bin" / "pr_create_fails").write_text("1", encoding="ascii")
            gated = self._push_cmd(
                root, "-Packages", "pythontk", "-Strict", "-Merge", "-SkipBuild",
                "-SkipWorkflowWait", "-SkipPypiCheck", "-UsePR", "-PRGateTimeoutSeconds", "0",
            )
            first = self._run(gated, cwd=root, timeout=240, env=env)
            out = first.stdout + first.stderr
            self.assertNotEqual(first.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.1'", out)
            self.assertIn("Failed to create PR", out)

            # Re-run: the tree now carries push.ps1's own Release commit. The gate
            # must accept it without a fresh -RecordReceipt.
            (root / "_bin" / "pr_create_fails").unlink()
            second = self._run(gated, cwd=root, timeout=240, env=env)
            out2 = second.stdout + second.stderr
            self.assertNotIn("No review receipt for the current tree", out2)
            self.assertIn("Review receipt valid", out2)
            self.assertIn("dev already carries Release 0.1.1", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_skip_review_never_manufactures_a_receipt(self):
        """Re-keying carries EXISTING receipts only. A -SkipReview run that
        commits a Release and aborts must leave no receipt behind - otherwise a
        later strict run would trust a review nobody did."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, origin = self._init_dummy_repo(root, "pythontk", "0.1.0", ["qtpy"])
            self._retarget_origin_to_github(repo, origin, "m3trik/pythontk")
            self._git(repo, "checkout", "dev")
            (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "feature")
            self._git(repo, "push", "origin", "dev")

            env = self._install_fake_gh(root, "{}")
            (root / "_bin" / "pr_create_fails").write_text("1", encoding="ascii")
            first = self._run(self._pr_release_cmd(root), cwd=root, timeout=240, env=env)
            out = first.stdout + first.stderr
            self.assertNotEqual(first.returncode, 0, out)
            self.assertIn("Committed 'Release 0.1.1'", out)

            shown = self._run(
                self._push_cmd(root, "-Packages", "pythontk", "-ShowReceipts"), cwd=root, timeout=120
            )
            self.assertIn("no receipts for current tree", shown.stdout + shown.stderr)

            # And the strict re-run is gated: a human commit ("feature") is in the
            # range, so this is NOT a mechanical delta.
            (root / "_bin" / "pr_create_fails").unlink()
            strict = self._pr_release_cmd(root)
            strict.remove("-SkipReview")
            second = self._run(strict, cwd=root, timeout=240, env=env)
            out2 = second.stdout + second.stderr
            self.assertNotEqual(second.returncode, 0, out2)
            self.assertIn("No review receipt for the current tree", out2)

    @unittest.skipUnless(_have_git.__func__(), "git is required")
    def test_mechanical_release_commit_is_exempt_from_the_gate(self):
        """A cascade-extra package (no code of its own, only a floor ratchet) is
        exempt from the gate before Prepare; after an abort it is ahead of main
        by ONLY push.ps1's `Release X.Y.Z` commit, and must stay exempt - without
        any receipt being invented for it."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_dummy_repo(root, "pythontk", "0.7.51", ["qtpy"])
            uitk, uitk_origin = self._init_dummy_repo(
                root, "uitk", "1.0.51", ["qtpy", "pythontk==0.0.1"]
            )
            self._retarget_origin_to_github(uitk, uitk_origin, "m3trik/uitk")

            # Strict, NO -SkipReview: uitk's delta is a pin ratchet only -> exempt.
            env = self._install_fake_gh(
                root,
                '{"mergeStateStatus":"CLEAN",'
                '"statusCheckRollup":[{"name":"test","conclusion":"SUCCESS"}]}',
                slug="m3trik/uitk",
            )
            (root / "_bin" / "pr_create_fails").write_text("1", encoding="ascii")
            cmd = self._push_cmd(
                root, "-Packages", "uitk", "-Strict", "-Merge", "-SkipBuild",
                "-SkipWorkflowWait", "-SkipPypiCheck", "-UsePR", "-PRGateTimeoutSeconds", "0",
            )
            first = self._run(cmd, cwd=root, timeout=240, env=env)
            out = first.stdout + first.stderr
            # Clean and not ahead of origin: the gate has nothing to judge yet.
            self.assertNotIn("No review receipt", out)
            self.assertIn("Committed 'Release 1.0.52'", out)
            self.assertIn("Failed to create PR", out)

            # Re-run: dev is ahead of main by exactly that one Release commit.
            (root / "_bin" / "pr_create_fails").unlink()
            second = self._run(cmd, cwd=root, timeout=240, env=env)
            out2 = second.stdout + second.stderr
            self.assertIn("ahead only by push.ps1's own Release commit (exempt)", out2)
            self.assertNotIn("No review receipt", out2)
            self.assertIn("PR #7 merged", out2)

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

    def test_workflows_do_not_bump_dev_after_publish(self):
        """No publish.yml dispatches `bump_dev`, and no bump-dev.yml exists.

        The post-publish placeholder bump was retired 2026-08-23: push.ps1 now
        steps the release version from what is PUBLISHED, so a placeholder on
        dev was dead weight -- and the reason every release burned 2-3 version
        numbers. Invariant after a release: dev == main.
        """
        for pkg in PACKAGES:
            workflows = ROOT / pkg / ".github" / "workflows"
            content = (workflows / "publish.yml").read_text(encoding="utf-8")
            self.assertNotIn("bump_dev", content, f"{pkg} publish.yml still dispatches bump_dev")
            self.assertNotIn("Trigger dev bump", content, pkg)
            self.assertFalse((workflows / "bump-dev.yml").exists(), f"{pkg} still ships bump-dev.yml")