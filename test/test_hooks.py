#!/usr/bin/python
# coding=utf-8
"""Tests for the workspace plugin's hooks (claude/hooks/hooks.py), run as Claude Code
runs them: the event's JSON on stdin, the project and the plugin's data folder in
the environment, a fresh interpreter in isolated mode.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
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

    def hook(self, event: str, payload: dict) -> dict:
        """Run *event* with *payload*; the JSON it printed, or ``{}``."""
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), CLAUDE_PLUGIN_DATA=str(self.data))
        done = subprocess.run(
            [sys.executable, "-I", str(HOOKS / "hooks.py"), event],
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=env,
            timeout=60,
        )
        self.assertEqual((done.returncode, done.stderr.decode()), (0, ""))
        return json.loads(done.stdout) if done.stdout.strip() else {}

    def context(self, event: str, payload: dict) -> str:
        out = self.hook(event, payload)
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

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


class TestSessionStart(_HookCase):
    def _backlog(self, text: str):
        (self.project / ".claude" / "BACKLOG.md").write_text(textwrap.dedent(text), encoding="utf-8")

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
    def edit(self, path: str = None, command: str = None, session: str = "s1"):
        if command is not None:
            payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        else:
            payload = {"tool_name": "Edit", "tool_input": {"file_path": path}}
        self.hook("edit", dict(payload, session_id=session))

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


if __name__ == "__main__":
    unittest.main()
