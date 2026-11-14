#!/usr/bin/python
# coding=utf-8
"""Tests for claude-challenge/skills/challenge/prepare.py -- the run-file builder.

The workflow script itself is proven by its own ``stub`` mode (every stage on canned
answers, in the real harness); these hold the part that runs in Python: the reduction
of a subject to plain text and the injection of the arguments.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "claude-challenge", "skills", "challenge")
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)

import prepare  # noqa: E402

SCRIPT = os.path.join(SKILL, "challenge.js")
MARK = "const INJECTED_ARGS = "

PAGE = """<title>Not the subject</title>
<style>.a { color: red }</style>
<h2>Decisions</h2>
<p>One   master
per product.</p>
<ul><li>First</li><li>Second</li></ul>
<table><tr><th>Stage</th><th>Gate</th></tr><tr><td>Intake</td><td>Units stated</td></tr></table>
<figure><svg aria-label="Sources feed the pipeline."><text>drawn label</text></svg>
<figcaption>The caption.</figcaption></figure>
<script>alert(1)</script>
"""


def _write(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _injected(text):
    line = next(row for row in text.split("\n") if row.startswith(MARK))
    return json.loads(line[len(MARK):])


class TestPlainText(unittest.TestCase):
    def test_markup_is_reduced_to_what_a_reader_takes(self):
        with tempfile.TemporaryDirectory() as folder:
            text = prepare.plain_text(_write(folder, "page.html", PAGE))
        self.assertIn("## Decisions", text)
        self.assertIn("One master per product.", text)
        self.assertIn("- First", text)
        self.assertIn("Intake | Units stated", text)
        self.assertIn("[Figure: Sources feed the pipeline.]", text)
        self.assertIn("The caption.", text)
        for hidden in ("color: red", "alert(1)", "drawn label", "Not the subject"):
            self.assertNotIn(hidden, text)

    def test_text_that_is_not_html_is_kept_as_written(self):
        with tempfile.TemporaryDirectory() as folder:
            text = prepare.plain_text(_write(folder, "plan.md", "# Plan\n\n<b>kept</b>\n"))
        self.assertEqual(text, "# Plan\n\n<b>kept</b>")


class TestBuild(unittest.TestCase):
    def _build(self, frame, subject="The subject.", **more):
        with tempfile.TemporaryDirectory() as folder:
            return prepare.build(SCRIPT, _write(folder, "design.txt", subject), frame, **more)

    def test_the_arguments_land_after_the_marker_and_meta_stays_first(self):
        text, args = self._build({"title": "A design", "brief": "What must be true."})
        lines = text.split("\n")
        self.assertTrue(lines[0].startswith("export const meta"))
        marker = next(i for i, row in enumerate(lines) if row.startswith("// @args"))
        self.assertTrue(lines[marker + 1].startswith(MARK))
        self.assertEqual(_injected(text), args)
        self.assertEqual(args["subject"], {"title": "A design", "text": "The subject."})
        self.assertNotIn("title", args)

    def test_the_mode_given_overrides_the_frames(self):
        _, args = self._build({"brief": "b", "mode": "run"}, mode="stub")
        self.assertEqual(args["mode"], "stub")
        _, args = self._build({"brief": "b", "mode": "run"})
        self.assertEqual(args["mode"], "run")

    def test_a_subject_with_no_title_takes_its_file_name(self):
        _, args = self._build({"brief": "b"})
        self.assertEqual(args["subject"]["title"], "design")

    def test_the_previous_revision_rides_along(self):
        with tempfile.TemporaryDirectory() as folder:
            before = _write(folder, "before.txt", "The old text.")
            _, args = prepare.build(SCRIPT, _write(folder, "design.txt", "New."), {"brief": "b"}, previous=before)
        self.assertEqual(args["previous"], "The old text.")

    def test_a_line_separator_in_the_subject_cannot_break_the_script(self):
        # U+2028 ends a line in JavaScript source; raw, it would cut the literal in two.
        text, args = self._build({"brief": "b"}, subject="one" + chr(0x2028) + "two")
        self.assertNotIn(chr(0x2028), text)
        self.assertEqual(_injected(text)["subject"]["text"], args["subject"]["text"])

    def test_a_script_with_no_marker_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            bare = _write(folder, "bare.js", "export const meta = {}\n")
            with self.assertRaises(SystemExit):
                prepare.build(bare, _write(folder, "design.txt", "x"), {"brief": "b"})


class TestRefusals(unittest.TestCase):
    """What would spend by accident, or fail at launch, is refused when the run file is built."""

    def test_preformatted_text_keeps_its_indentation_and_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            page = _write(folder, "page.html", "<p>The tree:</p><pre>\nroot\n    child_a\n        leaf\n</pre><p>after   it</p>")
            text = prepare.plain_text(page)
        self.assertIn("root\n    child_a\n        leaf", text)
        self.assertIn("after it", text)

    def test_a_mode_that_is_not_plan_stub_or_run_is_refused(self):
        # "Plan" is not "plan": anything the script does not know as free would run real agents.
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "x")
            for mode in ("Plan", "dry", ""):
                with self.subTest(mode=mode), self.assertRaises(SystemExit) as refused:
                    prepare.build(SCRIPT, subject, {"brief": "b", "mode": mode})
                self.assertIn("plan, stub, run", str(refused.exception))
            _, args = prepare.build(SCRIPT, subject, {"brief": "b"})
            self.assertEqual(args.get("mode", "plan"), "plan")

    def test_a_frame_that_is_not_an_object_and_a_missing_subject_are_said_plainly(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "x")
            with self.assertRaises(SystemExit) as refused:
                prepare.build(SCRIPT, subject, ["brief"])
            self.assertIn("JSON object", str(refused.exception))
            with self.assertRaises(SystemExit) as refused:
                prepare.build(SCRIPT, os.path.join(folder, "gone.html"), {"brief": "b"})
            self.assertIn("gone.html", str(refused.exception))

    def test_a_run_file_handed_back_in_keeps_one_set_of_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "first")
            once, _ = prepare.build(SCRIPT, subject, {"brief": "b"})
            again, args = prepare.build(_write(folder, "run.js", once), _write(folder, "next.txt", "second"), {"brief": "b"})
        self.assertEqual(sum(row.startswith(MARK) for row in again.split("\n")), 1)
        self.assertEqual(_injected(again)["subject"]["text"], "second")
        self.assertEqual(args["subject"]["text"], "second")

    def test_the_command_writes_the_run_file_into_a_folder_it_makes(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "The subject.")
            frame = _write(folder, "frame.json", json.dumps({"title": "T", "brief": "b"}))
            out = os.path.join(folder, "new", "deeper", "run.js")
            prepare.main(["--subject", subject, "--frame", frame, "--out", out, "--mode", "stub"])
            with open(out, encoding="utf-8") as handle:
                written = handle.read()
            self.assertEqual(_injected(written)["mode"], "stub")
            with self.assertRaises(SystemExit) as refused:
                prepare.main(["--subject", subject, "--frame", _write(folder, "bad.json", "{not json"), "--out", out])
            self.assertIn("bad.json", str(refused.exception))


class TestTheScriptItFeeds(unittest.TestCase):
    def setUp(self):
        with open(SCRIPT, encoding="utf-8") as handle:
            self.script = handle.read()

    def test_nothing_is_spent_unless_a_run_is_asked_for(self):
        self.assertIn("const mode = A.mode || 'plan'", self.script)
        self.assertIn("if (['plan', 'stub', 'run'].indexOf(mode) < 0) return", self.script)

    def test_it_reads_the_injected_arguments_first(self):
        self.assertIn("typeof INJECTED_ARGS !== 'undefined' ? INJECTED_ARGS : args", self.script)

    def test_it_starts_with_its_meta_block(self):
        self.assertTrue(self.script.startswith("export const meta = {"))


if __name__ == "__main__":
    unittest.main()
