#!/usr/bin/python
# coding=utf-8
"""Tests for the workspace plugin's hooks (claude/hooks/hooks.py), run as Claude Code
runs them: the event's JSON on stdin, the project and the plugin's data folder in
the environment, a fresh interpreter in isolated mode.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "claude" / "hooks"


class _HookCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "project"
        self.data = Path(self._tmp.name) / "data"
        (self.project / ".claude").mkdir(parents=True)
        self.data.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def hook(self, event: str, payload: dict, *args: str) -> dict:
        """Run *event* with *payload*; the JSON it printed, or ``{}``."""
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), CLAUDE_PLUGIN_DATA=str(self.data))
        done = subprocess.run(
            [sys.executable, "-I", str(HOOKS / "hooks.py"), event, *args],
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=env,
            timeout=60,
        )
        self.assertEqual((done.returncode, done.stderr.decode()), (0, ""))
        return json.loads(done.stdout) if done.stdout.strip() else {}

    def context(self, event: str, payload: dict, *args: str) -> str:
        out = self.hook(event, payload, *args)
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def edit(self, path: str = None, command: str = None, session: str = "s1"):
        if command is not None:
            payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        else:
            payload = {"tool_name": "Edit", "tool_input": {"file_path": path}}
        self.hook("edit", dict(payload, session_id=session))

    def marker(self, session: str = "s1") -> Path:
        return self.data / "critique" / f"{session}.txt"


class TestHooksJson(unittest.TestCase):
    def test_every_event_runs_the_script_with_no_shell(self):
        config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(set(config), {"SessionStart", "PostToolUse", "Stop"})
        for event, groups in config.items():
            for hook in (h for g in groups for h in g["hooks"]):
                with self.subTest(event=event):
                    self.assertEqual(hook["command"], "uv")  # a real executable: no shell, every OS
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/hooks.py", hook["args"])
        (edit,) = config["PostToolUse"][0]["hooks"]
        self.assertTrue(edit["async"], "no tool call may wait on the marker")
        (stop,) = config["Stop"][0]["hooks"]
        budget = int(stop["args"][stop["args"].index("--budget") + 1])
        self.assertLess(budget, stop["timeout"], "a hook that times out has its output discarded: the gates end first")


class TestSessionStart(_HookCase):
    def _backlog(self, text: str):
        (self.project / ".claude" / "BACKLOG.md").write_text(textwrap.dedent(text), encoding="utf-8")

    def _git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(self.project / ".claude"), *args], capture_output=True, text=True, check=True
        )
        return done.stdout

    def test_a_ledger_folder_that_is_a_repo_gets_one_local_commit_per_change(self):
        """``git init`` inside ``.claude/`` makes the ledgers' history: each
        session start commits what changed since the last, honouring the
        folder's ``.gitignore``, and commits nothing when nothing changed."""
        self._git("init", "-q")
        self._git("config", "user.name", "t")
        self._git("config", "user.email", "t@t")
        (self.project / ".claude" / ".gitignore").write_text("receipts.json\n", encoding="utf-8")
        (self.project / ".claude" / "receipts.json").write_text("{}", encoding="utf-8")
        self._backlog("# Backlog\n\nNothing open.\n")
        self.hook("session-start", {})
        self.assertEqual(self._git("log", "--format=%s").split(), ["Checkpoint"])
        self.assertEqual(sorted(self._git("ls-files").split()), [".gitignore", "BACKLOG.md"])
        self.hook("session-start", {})  # nothing changed: no second commit
        self.assertEqual(len(self._git("log", "--format=%s").split()), 1)
        self._backlog("# Backlog\n\nAn entry was deleted.\n")
        self.hook("session-start", {})
        self.assertEqual(len(self._git("log", "--format=%s").split()), 2)
        self.assertEqual(self._git("status", "--porcelain"), "")

    def test_a_ledger_folder_that_is_no_repo_is_never_made_one(self):
        self._backlog("# Backlog\n\nNothing open.\n")
        self.hook("session-start", {})
        self.assertFalse((self.project / ".claude" / ".git").exists())

    def test_no_backlog_or_no_entry_costs_no_context(self):
        self.assertEqual(self.hook("session-start", {}), {})
        self._backlog("# Backlog\n\nNothing open.\n")
        self.assertEqual(self.hook("session-start", {}), {})

    def test_the_backlog_is_graded_in_one_line(self):
        old = (date.today() - timedelta(days=30)).isoformat()
        fresh = date.today().isoformat()
        self._backlog(
            f"""\
            # Backlog

            ## {fresh} | mayatk | S1 | ready | one
            - Verified: {fresh} | reproduces | measured
            ## {old} | pythontk | S1 | decision | two
            ## {old} | uitk | S2 | ready | three
            - Verified: {fresh} | reproduces | re-measured, so alive
            ## {old} | uitk | S9 | someday | four
            """
        )
        line = self.context("session-start", {})
        self.assertIn("4 deferred issue(s) are open", line)
        self.assertIn("2 are S1, 1 of those actionable now", line)
        self.assertIn("1 wait on a maintainer decision", line)
        self.assertIn("2 entries are past the 14-day TTL", line)  # two (no stamp) and four
        self.assertIn("2/3 S1+S2 entries carry a measured Verified stamp", line)
        self.assertIn("WARNING 1 heading(s)", line)
        self.assertIn("(line(s) 8)", line)


class TestCritique(_HookCase):
    def test_a_file_tool_marks_its_path_and_a_shell_only_its_writes(self):
        self.edit(str(self.project / "pkg" / "a.py"))
        self.edit(command="ls -la && git status")
        self.edit(command="sed -i 's/a/b/' x.py")
        self.edit(command="python - <<'EOF'\nprint(1)\nEOF")
        lines = self.marker().read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [str(self.project / "pkg" / "a.py"), "(shell)", "(shell)"])

    def test_a_turn_that_changed_repo_files_gets_one_critique(self):
        (self.project / "pkg").mkdir()
        (self.project / "pkg" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        self.edit(str(self.project / "pkg" / "a.py"))
        self.edit(str(self.project / ".claude" / "BACKLOG.md"))
        self.edit(str(Path(self._tmp.name) / "scratch.py"))
        line = self.context("stop", {"session_id": "s1"})
        self.assertIn("This turn changed pkg/a.py (new, 2 lines).", line)  # in no repo: made this turn
        self.assertIn("affected_tests.py pkg/a.py --run", line)
        self.assertNotIn("BACKLOG", line)
        self.assertNotIn("scratch", line)
        self.assertFalse(self.marker().exists(), "the marker is spent")
        self.assertEqual(self.context("stop", {"session_id": "s1"}), "")  # nothing new

    def test_a_path_spelled_another_way_still_counts_and_a_sibling_folder_does_not(self):
        # The path is whatever the model typed: forward slashes and another drive
        # case were dropped silently (no critique), and a sibling sharing the
        # project's prefix was taken for one of its files.
        (self.project / "pkg").mkdir()
        (self.project / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
        spelled = (self.project / "pkg" / "a.py").as_posix()
        self.edit(spelled[0].swapcase() + spelled[1:] if spelled[1] == ":" else spelled)
        self.edit(str(Path(f"{self.project}_old") / "b.py"))
        line = self.context("stop", {"session_id": "s1"})
        self.assertIn("pkg/a.py", line)
        self.assertNotIn("b.py", line)

    def test_a_shell_write_names_no_file_but_still_asks(self):
        self.edit(command="echo x > out.txt")
        line = self.context("stop", {"session_id": "s1"})
        self.assertIn("files through the shell", line)
        self.assertIn("plus any file you changed through the shell", line)

    def test_no_critique_for_a_critique_or_a_turn_that_changed_nothing_of_the_repo(self):
        self.assertEqual(self.context("stop", {"session_id": "s1"}), "")
        self.edit(str(self.project / "pkg" / "a.py"))
        self.assertEqual(self.context("stop", {"session_id": "s1", "stop_hook_active": True}), "")
        self.assertFalse(self.marker().exists())
        self.edit(str(self.project / ".claude" / "notes.md"))
        self.assertEqual(self.context("stop", {"session_id": "s1"}), "")

    def test_a_turn_waiting_on_background_work_keeps_its_marker(self):
        self.edit(str(self.project / "pkg" / "a.py"))
        busy = {"session_id": "s1", "background_tasks": [{"id": "t1", "status": "running"}]}
        self.assertEqual(self.context("stop", busy), "")
        self.assertIn("pkg/a.py", self.context("stop", {"session_id": "s1"}))

    def test_sessions_keep_their_own_markers(self):
        self.edit(str(self.project / "pkg" / "a.py"), session="one")
        self.edit(str(self.project / "pkg" / "b.py"), session="two")
        line = self.context("stop", {"session_id": "two"})
        self.assertIn("pkg/b.py", line)
        self.assertNotIn("pkg/a.py", line)

    def test_a_malformed_input_is_ignored(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), CLAUDE_PLUGIN_DATA=str(self.data))
        for event in ("session-start", "edit", "stop"):
            done = subprocess.run(
                [sys.executable, "-I", str(HOOKS / "hooks.py"), event],
                input=b"not json",
                capture_output=True,
                env=env,
                timeout=60,
            )
            with self.subTest(event=event):
                self.assertEqual((done.returncode, done.stdout), (0, b""))
        self.assertFalse((self.data / "critique" / "nosession.txt").exists(), "no event, no mark")


def _load():
    """The hook script as a module, for the parts that take their collaborators as arguments."""
    spec = importlib.util.spec_from_file_location("plugin_hooks", HOOKS / "hooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGates(_HookCase):
    """Stop runs what a machine can decide and asks the model only for the rest."""

    PLAIN = 'print("m3trik: 1 module(s), ~3 test(s)")'

    def selector(self, run: str = "", plan: str = PLAIN):
        """A stand-in for affected_tests.py: *plan* runs when it is asked for the plan,
        *run* when it is asked to run. It notes every call it gets."""
        folder = self.project / "m3trik" / "scripts"
        folder.mkdir(parents=True, exist_ok=True)
        body = (
            "import sys\n"
            "open('calls.txt', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "if '--run' not in sys.argv:\n"
            + textwrap.indent(textwrap.dedent(plan).strip(), "    ")
            + "\n    sys.exit(0)\n"
            + textwrap.dedent(run)
        )
        (folder / "affected_tests.py").write_text(body, encoding="utf-8")
        (self.project / "calls.txt").unlink(missing_ok=True)

    def calls(self) -> list:
        path = self.project / "calls.txt"
        return path.read_text().splitlines() if path.is_file() else []

    def code(self, name: str = "a.py") -> Path:
        (self.project / "pkg").mkdir(exist_ok=True)
        path = self.project / "pkg" / name
        path.write_text("x = 1\n", encoding="utf-8")
        self.edit(str(path))
        return path

    def log(self) -> list:
        path = self.data / "critique" / "log.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def stop(self, budget: int = 30) -> str:
        return self.context("stop", {"session_id": "s1"}, "--budget", str(budget))

    def test_a_turn_that_changed_only_docs_asks_nothing(self):
        (self.project / "docs").mkdir()
        for name in ("docs/guide.md", "CHANGELOG.md"):
            (self.project / name).write_text("text\n", encoding="utf-8")
            self.edit(str(self.project / name))
        self.assertEqual(self.context("stop", {"session_id": "s1"}), "")
        self.assertFalse(self.marker().exists(), "the marker is spent")
        (entry,) = self.log()
        self.assertEqual((entry["event"], entry["asked"], entry["docs"], entry["code"]), ("stop", False, 2, 0))

    def test_passing_tests_are_planned_then_run_by_the_hook_and_not_again(self):
        self.selector(run='print("=== affected tests: all passed ===")')
        self.code()
        line = self.stop()
        self.assertEqual(self.calls(), ["pkg/a.py --no-gui", "pkg/a.py --run --no-gui"])
        self.assertIn("This turn changed pkg/a.py", line)
        self.assertIn("passed", line)
        self.assertIn("do not rerun", line)
        self.assertNotIn("verify with", line)
        entry = self.log()[-1]
        self.assertEqual((entry["tests"], entry["asked"], entry["code"]), ("passed", True, 1))

    def test_a_selection_that_needs_an_application_is_never_started(self):
        # A headless Maya, Blender, Unity or dotnet run is a host: the hook plans, sees it and starts nothing.
        plans = {
            "a headless Maya": 'print("mayatk: 38 module(s), ~2858 test(s) (~153s last run)")',
            "Blender": 'print("blendertk: 78 module(s), ~22 test(s)")',
            "a whole-suite runner": 'print("unity_edit_mode: the package\'s Edit Mode tests, run whole")',
            "a plain runner beside a host": 'print("m3trik: 1 module(s), ~3 test(s)"); print("mayatk: 1 module(s), ~5 test(s)")',
            "a runner nobody listed": 'print("somepkg: 1 module(s), ~5 test(s)")',
        }
        for what, plan in plans.items():
            with self.subTest(what=what):
                self.selector(run='print("=== affected tests: all passed ===")', plan=plan)
                self.code()
                line = self.stop()
                self.assertEqual(self.calls(), ["pkg/a.py --no-gui"], "planned, never run")
                self.assertIn("verify with python m3trik/scripts/affected_tests.py pkg/a.py --run", line)
                self.assertEqual(self.log()[-1]["tests"], "host")

    def test_a_selection_too_large_for_the_hook_is_handed_back_unstarted(self):
        self.selector(run='print("=== affected tests: all passed ===")', plan='print("uitk: 26 module(s), ~2098 test(s)")')
        self.code()
        line = self.stop()
        self.assertEqual(self.calls(), ["pkg/a.py --no-gui"])
        self.assertIn("verify with", line)
        self.assertEqual(self.log()[-1]["tests"], "large")

    def test_a_pass_beside_a_shell_write_vouches_for_nothing_it_cannot_name(self):
        self.selector(run='print("=== affected tests: all passed ===")')
        self.code()
        self.edit(command="echo x > pkg/b.py")
        line = self.stop()
        self.assertIn("verify with python m3trik/scripts/affected_tests.py pkg/a.py plus any file", line)
        self.assertNotIn("do not rerun", line)
        self.assertEqual(self.log()[-1]["tests"], "partial")

    def test_failing_tests_reach_the_model_with_their_output(self):
        self.selector(run="""
            print("--- pkg: FAIL (exit 1) in 0s")
            print("    AssertionError: boom detail")
            print("=== affected tests: FAILED in pkg ===")
            sys.exit(1)
        """)
        self.code()
        line = self.stop()
        self.assertIn("FAILED", line)
        self.assertIn("boom detail", line)
        self.assertIn("Fix the cause", line)
        self.assertIn("affected_tests.py pkg/a.py --run", line)
        self.assertEqual(self.log()[-1]["tests"], "failed")

    def test_tests_the_hook_could_not_judge_are_handed_back(self):
        # Every selected test skipped, nothing selected, a selector that failed: the model runs them.
        cases = {
            "idle": dict(run='print("=== affected tests: RAN NOTHING in pkg ==="); sys.exit(1)'),
            "none": dict(plan='print("No test module reaches these changes.")'),
            "error": dict(plan="sys.exit(2)"),
        }
        for verdict, parts in cases.items():
            with self.subTest(verdict=verdict):
                self.selector(**parts)
                self.code()
                line = self.stop()
                self.assertIn("verify with python m3trik/scripts/affected_tests.py pkg/a.py --run", line)
                self.assertNotIn("do not rerun", line)
                self.assertEqual(self.log()[-1]["tests"], verdict)

    def test_a_plan_or_a_run_that_outlasts_the_budget_is_stopped_and_handed_back(self):
        for what, parts in {"plan": dict(plan="import time; time.sleep(60)"), "run": dict(run="import time; time.sleep(60)")}.items():
            with self.subTest(what=what):
                self.selector(**parts)
                self.code()
                started = time.monotonic()
                line = self.stop(budget=8)
                self.assertLess(time.monotonic() - started, 25)
                self.assertIn("verify with python m3trik/scripts/affected_tests.py pkg/a.py --run", line)
                self.assertEqual(self.log()[-1]["tests"], "timeout")

    def test_a_passing_run_that_leaves_a_child_behind_still_passes_in_time(self):
        # The run is judged by its own exit, never by a pipe a child of it still holds open.
        self.selector(run="""
            import subprocess, tempfile
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(12)"], cwd=tempfile.gettempdir())
            print("=== affected tests: all passed ===")
        """)
        self.code()
        started = time.monotonic()
        line = self.stop(budget=30)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIn("do not rerun", line)
        self.assertEqual(self.log()[-1]["tests"], "passed")

    def test_a_workspace_with_no_selector_is_asked_as_before(self):
        self.code()
        line = self.stop()
        self.assertIn("verify with python m3trik/scripts/affected_tests.py pkg/a.py --run", line)
        self.assertEqual(self.log()[-1]["tests"], "skipped")

    def test_a_critique_that_changed_files_is_logged_as_one_that_found_something(self):
        self.code()
        self.context("stop", {"session_id": "s1"})
        self.edit(str(self.project / "pkg" / "a.py"))  # the critique pass fixes something
        self.context("stop", {"session_id": "s1", "stop_hook_active": True})
        self.code()
        self.context("stop", {"session_id": "s1"})
        self.context("stop", {"session_id": "s1", "stop_hook_active": True})  # and this one nothing
        found = [entry["changed"] for entry in self.log() if entry["event"] == "critique"]
        self.assertEqual(found, [True, False])


class TestStopping(unittest.TestCase):
    def setUp(self):
        self.hooks = _load()

    def test_a_process_that_is_already_gone_stops_quietly(self):
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait(timeout=30)
        self.hooks._stop(done)  # nothing to kill: no exception, no wait

    def test_a_run_gets_the_hooks_own_limit_however_large_the_budget(self):
        waits = []

        def run(command, cwd, timeout):
            waits.append(timeout)
            if "--run" in command:
                return 0, "=== affected tests: all passed ==="
            return 0, "m3trik: 1 module(s), ~3 test(s)"

        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "m3trik" / "scripts" / "affected_tests.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")
            self.assertEqual(self.hooks._tests(Path(folder), ["pkg/a.py"], 600, run=run), ("passed", ""))
        self.assertEqual(waits, [self.hooks.PLAN_WAIT, self.hooks.RUN_WAIT])

    def test_the_change_of_a_file_costs_nothing_past_its_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.hooks._change(Path(folder), "pkg/a.py", time.monotonic() - 1), ("pkg/a.py", 0))


class TestLint(unittest.TestCase):
    def setUp(self):
        self.hooks = _load()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def linter(self):
        for rel in (".venv/Scripts/ruff.exe", ".venv/bin/ruff"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("", encoding="utf-8")

    def test_only_python_files_that_exist_are_linted_for_what_is_broken(self):
        self.linter()
        calls = []

        def run(command, cwd, timeout):
            calls.append(command)
            return 1, "pkg/a.py:3:5: F821 Undefined name `y`\n" * 14

        found = self.hooks._lint(self.root, ["pkg/a.py", "pkg/gone.py", "docs/x.md"], 5, run=run)
        (command,) = calls
        self.assertEqual(command[-1], "pkg/a.py")
        self.assertNotIn("pkg/gone.py", command)
        self.assertIn(self.hooks.LINT_RULES, command)
        self.assertEqual(len(found), self.hooks.LINT_SHOWN)
        self.assertTrue(all("F821" in line for line in found))

    def test_a_clean_file_and_a_workspace_with_no_linter_report_nothing(self):
        def never(command, cwd, timeout):
            raise AssertionError("no linter, no run")

        self.assertEqual(self.hooks._lint(self.root, ["pkg/a.py"], 5, run=never), [])
        self.linter()
        self.assertEqual(self.hooks._lint(self.root, ["pkg/a.py"], 5, run=lambda *a: (0, "")), [])
        self.assertEqual(self.hooks._lint(self.root, ["docs/x.md"], 5, run=never), [])

    def test_lint_findings_lead_the_ask(self):
        ask = self.hooks._ask("pkg/a.py (+1 -0)", "pkg/a.py", "", "passed", "", ["pkg/a.py:3:5: F821 Undefined name `y`"])
        self.assertIn("F821 Undefined name", ask)
        self.assertLess(ask.index("F821"), ask.index("do not rerun"))


if __name__ == "__main__":
    unittest.main()
