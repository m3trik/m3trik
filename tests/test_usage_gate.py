#!/usr/bin/python
# coding=utf-8
"""Tests for claude-challenge/skills/challenge/usage_gate.py -- the usage gate and its PreToolUse hook.

The hook stops a tool call that would launch paid agents (a subagent, a workflow, a headless
``claude -p``) when the account's usage windows cannot take it, and lets every other call through
without reading anything.
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "claude-challenge", "skills", "challenge")
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)

import usage_gate  # noqa: E402

FULL = {"session": {"pct": 97.0, "resets": "8:30pm"}}
ROOM = {"session": {"pct": 20.0, "resets": "8:30pm"}, "week": {"pct": 50.0, "resets": "Nov 21"}}
NOON = datetime(2026, 11, 20, 12, 0)  # hours from FULL's reset: its reserve in full


def _event(tool, **tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


class TestWhatItGates(unittest.TestCase):
    def test_agents_workflows_and_headless_sessions_are_gated(self):
        for event in (_event("Agent", prompt="p"), _event("Task", prompt="p"), _event("Workflow", script="s"),
                      _event("Bash", command='claude -p --model sonnet "review this"'),
                      _event("PowerShell", command="& claude.exe --print 'x'"),
                      _event("Bash", command="python challenge.py --subject s --frame f --out o --mode run")):
            with self.subTest(event=event):
                self.assertIsNotNone(usage_gate.need_of(event))

    def test_every_other_call_passes_without_a_reading(self):
        for event in (_event("Bash", command="git status"), _event("Read", file_path="x"),
                      _event("Bash", command='claude -p "/usage" --output-format json'),
                      _event("Bash", command="python challenge.py --mode plan --subject s"),
                      _event("Bash", command="claude plugin validate .")):
            with self.subTest(event=event):
                self.assertIsNone(usage_gate.need_of(event))

    def test_a_launch_by_path_or_wrapper_is_gated(self):
        for command in ('~/.local/bin/claude -p "x"', "/usr/bin/claude --print x",
                        r'C:\Users\u\.local\bin\claude.exe -p "x"',
                        r'& "C:\Program Files\Claude\claude.exe" -p x',
                        'CLAUDE_X=1 timeout 300 claude -p "x"', 'cd repo && claude -p "x"',
                        'claude -p /usage && claude -p "review this"'):
            with self.subTest(command=command):
                self.assertIsNotNone(usage_gate.need_of(_event("Bash", command=command)))

    def test_a_command_that_only_names_a_launch_passes(self):
        for command in ('git commit -m "claude -p note"', 'grep -rn "claude -p" .', "echo claude -p",
                        "python -m pytest tests/test_challenge.py", "/usr/bin/claude -p /usage",
                        "echo then claude -p", "git commit -m \"bash -c 'claude -p x'\""):
            with self.subTest(command=command):
                self.assertIsNone(usage_gate.need_of(_event("Bash", command=command)))

    def test_a_prompt_that_only_mentions_usage_is_a_launch(self):
        # Only a session whose prompt IS ``/usage`` reads the windows; one that names it in a prompt is work.
        self.assertEqual(usage_gate.need_of(_event("Bash", command='claude -p "docs for /usage" --resume')),
                         usage_gate.AGENT_TOKENS)

    def test_a_launch_inside_a_shell_construct_or_a_nested_shell_is_gated(self):
        """A loop's body, a branch, a group and a command handed to another shell all start a session.
        Fixed: 2026-11-26"""
        for command in ('for f in a b; do claude -p "review $f"; done', "if true; then claude -p x; fi",
                        "if false; then :; else claude -p x; fi", "{ claude -p x; }",
                        'bash -c "claude -p x"', "sh -c 'cd repo && claude -p x'",
                        'powershell -NoProfile -Command "claude -p x"', "cmd /c claude -p x",
                        'cmd /c "claude -p x"', "claude.cmd -p x",
                        'python challenge.py --subject s --mode "run"', "python challenge.py --mode 'frame'"):
            with self.subTest(command=command):
                self.assertEqual(usage_gate.need_of(_event("Bash", command=command)), usage_gate.AGENT_TOKENS)


class TestParse(unittest.TestCase):
    def test_each_models_weekly_line_is_a_window_of_its_own(self):
        """The fullest line stood for the week whatever its model, so one model's full allocation blocked
        every launch, agents on other models included. Fixed: 2026-11-26"""
        text = ("Current session: 12% used · resets 8:30pm\n"
                "Current week (all models): 59% used · resets Nov 28, 2am\n"
                "Current week (Sonnet only): 100% used · resets Nov 28, 2am\n")
        found = usage_gate.UsageGate.parse(text)
        self.assertEqual({k: v["pct"] for k, v in found.items()}, {"session": 12.0, "week": 59.0, "week:sonnet": 100.0})


#: The weekly allocation of one model used up, the account's own windows with room.
OPUS_FULL = {"session": {"pct": 20.0, "resets": "8:30pm"}, "week": {"pct": 50.0, "resets": "Nov 25, 1pm"},
             "week:opus": {"pct": 100.0, "resets": "Nov 25, 1pm"}}


class TestModelWindows(unittest.TestCase):
    """A full weekly window that belongs to another model is no constraint on work that does not run on it."""

    def setUp(self):
        self.gate = usage_gate.UsageGate(lambda: OPUS_FULL, os.devnull, clock=lambda: NOON)

    def test_work_is_held_to_the_all_models_windows_and_its_own_models(self):
        self.assertIsNone(self.gate.check(1000), "no model named: the all-models windows alone")
        self.assertIsNone(self.gate.check(1000, ["sonnet"]))
        why = self.gate.check(1000, ["claude-opus-5-5"])
        self.assertIn("the weekly opus window is 100% used", why)

    def test_the_hook_reads_the_model_a_launch_names(self):
        for event, code in ((_event("Agent", prompt="p", model="opus"), 2), (_event("Agent", prompt="p", model="sonnet"), 0),
                            (_event("Agent", prompt="p"), 0), (_event("Bash", command='claude -p --model opus "x"'), 2),
                            (_event("Bash", command="claude --model=sonnet -p x"), 0)):
            with self.subTest(event=event):
                self.assertEqual(usage_gate.hook(io.StringIO(json.dumps(event)), self.gate)[0], code)

    def test_each_window_printed_says_which_model_it_belongs_to(self):
        self.assertEqual({k: v["model"] for k, v in self.gate.budget().items()},
                         {"session": "all", "week": "all", "week:opus": "opus"})
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(usage_gate, "home", lambda: usage_gate.Path(folder)), \
                mock.patch.object(usage_gate, "read_usage", lambda: OPUS_FULL), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(usage_gate.main([]), 0)
        self.assertEqual(json.loads(out.getvalue())["week:opus"]["model"], "opus")


class TestHook(unittest.TestCase):
    def _hook(self, event, reading, env=None):
        with tempfile.TemporaryDirectory() as folder:
            gate = usage_gate.UsageGate(lambda: reading, os.path.join(folder, "calibration.json"), clock=lambda: NOON)
            reads = []
            gate.read = lambda: reads.append(1) or reading
            with mock.patch.dict(os.environ, env or {}, clear=False):
                code, message = usage_gate.hook(io.StringIO(json.dumps(event)), gate)
        return code, message, len(reads)

    def test_a_launch_the_window_cannot_take_is_blocked_with_the_reset(self):
        code, message, _ = self._hook(_event("Agent", prompt="p"), FULL)
        self.assertEqual(code, 2)
        self.assertIn("8:30pm", message)
        self.assertIn("CLAUDE_USAGE_GATE=off", message)

    def test_a_window_inside_its_reserve_is_said_as_such(self):
        """Inside the reserve the work's size is no reason: the block read "needs about 0% of it" and
        "would fail part way". Fixed: 2026-11-23"""
        _, message, _ = self._hook(_event("Agent", prompt="p"), FULL)
        self.assertIn("the 5-hour window is 97% used, inside the 5% kept back for the person's own work", message)
        self.assertNotIn("needs about", message)
        self.assertNotIn("fail part way", message)

    def test_work_bigger_than_what_is_left_says_its_size(self):
        gate = usage_gate.UsageGate(lambda: {"week": {"pct": 50.0, "resets": "Nov 25, 1pm"}}, os.devnull,
                                    clock=lambda: NOON)
        gate.cal = {"pct_per_usd": {"week": 10.0}, "usd_per_token": 1e-4}
        why = gate.check(60000)  # $6 at 10% a dollar: 60% of a window with 45% spendable
        self.assertIn("the weekly window is 50% used and this needs about 60% of it", why)
        self.assertIn("fail part way", why)
        self.assertIn("resets Nov 25, 1pm", why)

    def test_a_launch_with_room_passes(self):
        self.assertEqual(self._hook(_event("Agent", prompt="p"), ROOM)[:2], (0, ""))

    def test_an_unrelated_call_reads_nothing(self):
        code, _, reads = self._hook(_event("Bash", command="ls"), FULL)
        self.assertEqual((code, reads), (0, 0))

    def test_the_gate_can_be_switched_off(self):
        self.assertEqual(self._hook(_event("Agent", prompt="p"), FULL, {"CLAUDE_USAGE_GATE": "off"})[0], 0)

    def test_no_reading_means_the_call_passes(self):
        # An API key account reports no windows; the gate never blocks what it cannot measure.
        self.assertEqual(self._hook(_event("Agent", prompt="p"), None)[0], 0)

    def test_a_malformed_event_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            gate = usage_gate.UsageGate(lambda: FULL, os.path.join(folder, "c.json"))
            self.assertEqual(usage_gate.hook(io.StringIO("not json"), gate), (0, ""))


#: A launch whose prompt holds a letter the Windows code page cannot decode from UTF-8 (its second byte, 0x81).
WIDE = json.dumps(_event("Agent", prompt="Review Á design"), ensure_ascii=False).encode("utf-8")
#: A window with nothing left at any hour (no reserve near a reset can open it).
SPENT = {"session": {"pct": 100.0, "resets": "8:30pm"}}


class TestHookCommand(unittest.TestCase):
    """``python usage_gate.py --hook`` as Claude Code runs it: the event as UTF-8 bytes on stdin, exit 2 and
    the reason on stderr to block."""

    def _main(self, stdin):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(usage_gate, "home", lambda: usage_gate.Path(folder)), \
                mock.patch.object(usage_gate, "read_usage", lambda: SPENT), \
                mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            return usage_gate.main(["--hook"]), err.getvalue()

    def test_a_blocked_launch_exits_2_with_its_reason_on_stderr(self):
        code, err = self._main(io.TextIOWrapper(io.BytesIO(WIDE), encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertIn("Blocked by the usage gate", err)

    def test_the_event_is_read_as_utf8_whatever_the_locale(self):
        """Under ``-I`` the stream decodes with the code page, which fails on such a prompt, and the hook let
        the launch through unread. Fixed: 2026-11-26"""
        code, _ = self._main(io.TextIOWrapper(io.BytesIO(WIDE), encoding="cp1252"))
        self.assertEqual(code, 2)

    def test_the_usage_reading_reads_no_stdin(self):
        done = usage_gate.subprocess.CompletedProcess([], 0, stdout='{"result": ""}', stderr="")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(usage_gate.subprocess, "run", return_value=done) as ran:
            usage_gate.read_usage(exe="claude", cwd=folder)
        self.assertIs(ran.call_args.kwargs["stdin"], usage_gate.subprocess.DEVNULL)

    def test_the_plugin_hook_runs_this_script_on_every_tool_that_launches(self):
        plugin = os.path.join(os.path.dirname(HERE), "claude-challenge")
        with open(os.path.join(plugin, "hooks", "hooks.json"), encoding="utf-8") as handle:
            (entry,) = json.load(handle)["hooks"]["PreToolUse"]
        self.assertEqual(set(entry["matcher"].split("|")), set(usage_gate.AGENT_TOOLS) | {"Bash", "PowerShell"})
        (command,) = entry["hooks"]
        script = next(a for a in command["args"] if a.endswith(".py"))
        self.assertTrue(script.startswith("${CLAUDE_PLUGIN_ROOT}/"))
        self.assertEqual(os.path.realpath(script.replace("${CLAUDE_PLUGIN_ROOT}", plugin)),
                         os.path.realpath(usage_gate.__file__))
        self.assertEqual(command["args"][-1], "--hook")

    def test_python_starts_as_the_marketplaces_other_plugin_starts_it(self):
        """A bare ``python`` is no command on most Linux and macOS machines, and the Store's stub on a bare
        Windows one; the other plugin's hooks start it through uv on every OS. Fixed: 2026-11-26"""
        def launcher(name):
            with open(os.path.join(os.path.dirname(HERE), name, "hooks", "hooks.json"), encoding="utf-8") as handle:
                hooks = json.load(handle)["hooks"]
            command = next(iter(hooks.values()))[0]["hooks"][0]
            args = command["args"]
            return [command["command"]] + args[:next(i for i, a in enumerate(args) if a.endswith(".py"))]

        self.assertEqual(launcher("claude-challenge"), launcher("claude"))


class TestReserveNearTheReset(unittest.TestCase):
    def test_the_reset_is_read_as_local_time_today_or_on_its_date(self):
        hours = usage_gate.UsageGate.hours_left
        self.assertEqual(hours("Nov 21, 2am", NOON), 14.0)
        self.assertAlmostEqual(hours("5:20pm", NOON), 5 + 20 / 60)
        self.assertEqual(hours("8am", NOON), 20.0, "a time already past today is tomorrow's")
        self.assertEqual(hours("Jan 2, 9am", datetime(2026, 12, 31, 9, 0)), 48.0, "a date past this year is next year's")
        self.assertIsNone(hours("soon", NOON))

    def test_a_reset_worded_otherwise_is_read_or_keeps_the_whole_reserve(self):
        """"Nov 21 at 2am" read as midnight, an unknown month word as this month, and "Feb 30" raised out of
        the gate and the run. Fixed: 2026-11-26"""
        hours = usage_gate.UsageGate.hours_left
        self.assertEqual(hours("Nov 21 at 2am", NOON), 14.0)
        for words in ("Foo 21, 2am", "Feb 30, 2am", "Nov 21, 2am and then some"):
            with self.subTest(words=words):
                self.assertIsNone(hours(words, NOON))
        gate = usage_gate.UsageGate(lambda: {"week": {"pct": 50.0, "resets": "Feb 30, 2am"}}, os.devnull, clock=lambda: NOON)
        self.assertEqual(gate.reserve("week", "Feb 30, 2am"), gate.RESERVE)
        self.assertIsNone(gate.check(1000))

    #: 17:00 UTC is noon in New York (EST, UTC-5): 2am there is 14 hours away, wherever this runs.
    NOON_NY = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)

    def test_a_reset_in_a_named_zone_is_read_in_that_zone(self):
        with mock.patch.object(usage_gate.UsageGate, "zone", staticmethod(lambda name: timezone(timedelta(hours=-5)))):
            self.assertEqual(usage_gate.UsageGate.hours_left("Nov 21, 2am (America/New_York)", self.NOON_NY), 14.0)

    def test_the_zone_database_reads_the_named_zone(self):
        if usage_gate.UsageGate.zone("America/New_York") is None:
            self.skipTest("no zone database on this machine (Windows without tzdata): the reset is read as local time")
        self.assertEqual(usage_gate.UsageGate.hours_left("Nov 21, 2am (America/New_York)", self.NOON_NY), 14.0)

    def test_the_reserve_shrinks_to_nothing_as_the_reset_nears(self):
        gate = usage_gate.UsageGate(lambda: None, os.devnull, clock=lambda: NOON)
        self.assertEqual(gate.reserve("week", "Nov 23, 2am"), gate.RESERVE, "days away: all of it")
        self.assertAlmostEqual(gate.reserve("week", "Nov 21, 12am"), gate.RESERVE / 2, msg="half a day of its 24 hours")
        self.assertAlmostEqual(gate.reserve("session", "12:30pm"), gate.RESERVE / 2)
        self.assertEqual(gate.reserve("week", "Nov 20, 12pm"), 0.0, "at the reset: nothing to keep back")
        self.assertEqual(gate.reserve("week", "whenever"), gate.RESERVE, "an unread reset keeps it all")

    def test_near_the_reset_a_nearly_full_window_is_still_spendable(self):
        reading = {"week": {"pct": 97.0, "resets": "Nov 20, 1pm"}}
        late = usage_gate.UsageGate(lambda: reading, os.devnull, clock=lambda: NOON)
        self.assertIsNone(late.check(1000), "an hour from the reset, what is left expires: use it")
        self.assertAlmostEqual(late.budget()["week"]["spendable"], 3.0 - late.RESERVE / 24, places=2)
        early = usage_gate.UsageGate(lambda: {"week": {"pct": 97.0, "resets": "Nov 25, 1pm"}}, os.devnull,
                                     clock=lambda: NOON)
        self.assertIsNotNone(early.check(1000), "days from it, the reserve stands")


class TestCachedReading(unittest.TestCase):
    def test_a_reading_is_reused_for_a_while_then_taken_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "usage_cache.json")
            calls = []
            read = usage_gate.cached(lambda: calls.append(1) or ROOM, path, ttl=60)
            self.assertEqual(read(), ROOM)
            self.assertEqual(read(), ROOM)
            self.assertEqual(len(calls), 1)
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            data["at"] = time.time() - 120
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            read()
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
