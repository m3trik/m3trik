#!/usr/bin/python
# coding=utf-8
"""Tests for claude-challenge/skills/challenge/challenge.py -- the challenge process and its runner.

The process runs whole on canned answers (``stub``) and through a fake runner (``run``), so
every stage, the voting, the de-duplication, the limits and the verdict are held here without
spending; the headless runner is held by its command line and by how it reads the CLI's answer.
"""

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "claude-challenge", "skills", "challenge")
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)

import challenge  # noqa: E402

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

FRAME = {
    "title": "T",
    "brief": "What must be true.",
    "criteria": [{"name": "Simple", "weight": 2, "question": "Is it simple?"}, {"name": "Safe", "question": "Is it safe?"}],
    "seats": [{"name": "Seat one", "lens": "Look one way."}, {"name": "Seat two", "lens": "Look another way."}],
    "rivals": [{"name": "Rival one", "stance": "Do it another way."}, {"name": "Rival two", "stance": "Do nothing."}],
    "scenarios": ["Something happens.", "Something else happens."],
    "audit": True,
}


def _write(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _args(frame=None, subject="The subject.", mode="stub"):
    with tempfile.TemporaryDirectory() as folder:
        return challenge.load_args(_write(folder, "design.txt", subject), dict(frame or FRAME), mode=mode)


def _seat_of(prompt):
    """The seat a seat's prompt is for."""
    return prompt.split("YOUR SEAT: ")[1].split(".")[0]


class TestPlainText(unittest.TestCase):
    def test_markup_is_reduced_to_what_a_reader_takes(self):
        with tempfile.TemporaryDirectory() as folder:
            text = challenge.plain_text(_write(folder, "page.html", PAGE))
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
            text = challenge.plain_text(_write(folder, "plan.md", "# Plan\n\n<b>kept</b>\n"))
        self.assertEqual(text, "# Plan\n\n<b>kept</b>")

    def test_preformatted_text_keeps_its_indentation_and_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            page = _write(folder, "page.html", "<p>The tree:</p><pre>\nroot\n    child_a\n        leaf\n</pre><p>after   it</p>")
            text = challenge.plain_text(page)
        self.assertIn("root\n    child_a\n        leaf", text)
        self.assertIn("after it", text)


class TestArguments(unittest.TestCase):
    """What would spend by accident, or fail at launch, is refused before anything runs."""

    def test_the_subject_joins_the_frame_and_the_title_leaves_it(self):
        args = _args({"title": "A design", "brief": "b"})
        self.assertEqual(args["subject"], {"title": "A design", "text": "The subject."})
        self.assertNotIn("title", args)

    def test_a_subject_with_no_title_takes_its_file_name(self):
        self.assertEqual(_args({"brief": "b"})["subject"]["title"], "design")

    def test_the_mode_given_overrides_the_frames(self):
        self.assertEqual(_args({"brief": "b", "mode": "run"}, mode="stub")["mode"], "stub")
        self.assertEqual(_args({"brief": "b", "mode": "run"}, mode=None)["mode"], "run")

    def test_the_previous_revision_rides_along(self):
        with tempfile.TemporaryDirectory() as folder:
            before = _write(folder, "before.txt", "The old text.")
            args = challenge.load_args(_write(folder, "design.txt", "New."), {"brief": "b"}, previous=before)
        self.assertEqual(args["previous"], "The old text.")

    def test_a_mode_that_is_not_plan_stub_or_run_is_refused(self):
        # "Plan" is not "plan": anything the process does not know as free would start real agents.
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "x")
            for mode in ("Plan", "dry", ""):
                with self.subTest(mode=mode), self.assertRaises(SystemExit) as refused:
                    challenge.load_args(subject, {"brief": "b", "mode": mode})
                self.assertIn("plan, frame, stub, run", str(refused.exception))
            self.assertEqual(challenge.load_args(subject, {"brief": "b"}).get("mode", "plan"), "plan")

    def test_a_frame_that_is_not_an_object_and_a_missing_subject_are_said_plainly(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "x")
            with self.assertRaises(SystemExit) as refused:
                challenge.load_args(subject, ["brief"])
            self.assertIn("JSON object", str(refused.exception))
            with self.assertRaises(SystemExit) as refused:
                challenge.load_args(os.path.join(folder, "gone.html"), {"brief": "b"})
            self.assertIn("gone.html", str(refused.exception))

    def test_a_run_with_no_brief_says_so_and_starts_nothing(self):
        result = challenge.Challenge(_args({"title": "T"}), runner=self.fail).run()
        self.assertIn("brief", result["error"])


class TestPlan(unittest.TestCase):
    def test_a_plan_lists_the_agents_and_starts_none(self):
        result = challenge.Challenge(_args(mode="plan"), runner=self.fail).run()
        stages = [p["stage"] for p in result["plan"]]
        self.assertEqual(stages, ["frame", "attack", "attack", "rivals", "rivals", "rivals", "walk", "verify", "judge",
                                  "recheck", "audit"])
        est = result["estimate"]
        self.assertEqual(est["agents_planned"], 13)  # 1 + 2 + 3 + 2 + 1 + 1 + 2 + 1
        self.assertGreater(est["total_tokens_rough"], 0)
        self.assertNotIn("verdict", result)

    def test_later_votes_are_planned_on_the_critic_model(self):
        frame = dict(FRAME, limits={"verify_votes": 3})
        plan = challenge.Challenge(_args(frame, mode="plan")).run()["plan"]
        verify = [p for p in plan if p["stage"] == "verify"]
        self.assertEqual([(p["kind"], p["agents"]) for p in verify], [("senior", 1), ("critic", 2)])

    def test_the_estimate_reads_a_prompt_once_a_turn_and_an_evidence_file_on_each_turn_after_it(self):
        # Measured 2026-11-25: 437k estimated against 771k used. A prompt is read once per turn (two: the
        # answer goes back through a tool), and a 26 KB evidence file every agent read was counted by none.
        self.assertEqual(challenge.agent_tokens(1000, "critic"),
                         2 * 1000 + challenge.OVERHEAD["critic"] + challenge.WRITES["critic"])
        self.assertEqual(challenge.agent_tokens(1000, "senior", evidence=500),
                         3 * 1000 + 2 * 500 + challenge.OVERHEAD["senior"] + challenge.WRITES["senior"])
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "x" * 4000)  # 1,000 tokens
            plain = challenge.Challenge(_args(mode="plan")).run()["estimate"]
            listed = challenge.Challenge(_args(dict(FRAME, evidence=[evidence]), mode="plan")).run()["estimate"]
        self.assertEqual(plain["agents_planned"], 13)
        self.assertGreaterEqual(listed["total_tokens_rough"] - plain["total_tokens_rough"], 13 * 2 * 1000)

    def test_a_frame_check_alone_is_estimated_by_the_same_rule(self):
        # It kept the one-turn sum the rule replaced: 8.7k planned where the measured check read 25k.
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "x" * 4000)
            run = challenge.Challenge(_args(dict(FRAME, evidence=[evidence]), mode="frame"))
            plan, estimate = run.plan()
        self.assertEqual([p["stage"] for p in plan], ["frame"])
        self.assertEqual(estimate["total_tokens_rough"],
                         challenge.agent_tokens(challenge.tokens(run.HEAD) + challenge.tokens(run.frame_tail()), "critic", 1000))

    def test_roots_plan_one_agent_that_settles_findings_in_the_files(self):
        plan = challenge.Challenge(_args(dict(FRAME, roots=["."]), mode="plan")).run()["plan"]
        self.assertEqual([p["stage"] for p in plan][-2:], ["audit", "settle"])  # in the order they run
        settle = next(p for p in plan if p["stage"] == "settle")
        self.assertEqual((settle["kind"], settle["agents"]), ("senior", 8))  # one agent a finding, up to the limit
        self.assertNotIn("settle", [p["stage"] for p in challenge.Challenge(_args(mode="plan")).run()["plan"]])
        for off in (dict(FRAME, roots=["."], limits={"settle": 0}), {"title": "T", "brief": "b", "roots": ["."]}):
            self.assertNotIn("settle", [p["stage"] for p in challenge.Challenge(_args(off, mode="plan")).run()["plan"]])
        # What a search reads is in the estimate: each of the 8 agents its prompt on every turn, and its searches.
        with_roots = challenge.Challenge(_args(dict(FRAME, roots=["."]), mode="plan")).run()["estimate"]["total_tokens_rough"]
        without = challenge.Challenge(_args(mode="plan")).run()["estimate"]["total_tokens_rough"]
        self.assertGreaterEqual(with_roots - without, 8 * challenge.SEARCH)


class TestStub(unittest.TestCase):
    """Every stage on canned answers: the counts below are worked out by hand from ``STUB``."""

    @classmethod
    def setUpClass(cls):
        cls.result = challenge.Challenge(_args(), runner=lambda *a: (_ for _ in ()).throw(AssertionError("spent"))).run()

    def test_every_stage_runs_and_nothing_is_spent(self):
        cost = self.result["cost"]
        self.assertEqual(cost["agents"], 12)  # frame, 2 seats, 3 cases, 2 walks, 1 verify, 1 judge, 1 recheck, 1 audit
        self.assertEqual((cost["output_tokens"], cost["usd"]), (0, 0.0))
        self.assertEqual(self.result["dropped"], [])

    def test_a_finding_without_a_scenario_is_dropped_and_a_repeat_joins_the_first(self):
        stats = {s["seat"]: s for s in self.result["seat_stats"]}
        self.assertEqual((stats["Seat one"]["raised"], stats["Seat one"]["no_scenario"]), (3, 1))
        self.assertEqual(stats["Seat two"]["duplicate"], 1)
        first = next(d for d in self.result["defects"] if d["id"] == "F1")
        self.assertEqual(first["also_from"], ["Seat two"])
        self.assertEqual(self.result["refuted"], 1)

    def test_a_suspected_finding_is_rechecked_and_the_audit_can_overturn_it(self):
        by_id = {d["id"]: d for d in self.result["defects"]}
        self.assertEqual(by_id["F1"]["verified"], "VERIFIED")
        self.assertEqual(by_id["F2"]["verified"], "SUSPECTED")
        self.assertIn("Overturned at audit", by_id["F2"]["reason"])
        self.assertEqual(len(self.result["open_questions"]), 1)

    def test_a_refuted_finding_is_kept_with_its_reason_so_the_refutation_can_be_checked(self):
        refuted = self.result["refuted_findings"]
        self.assertEqual([f["id"] for f in refuted], ["F3"])
        self.assertEqual((refuted[0]["seat"], refuted[0]["claim"], refuted[0]["reason"]), ("Seat one", "stub defect one", "stub"))

    def test_the_designs_are_judged_under_letters_and_the_best_rival_can_win(self):
        # k = (len("T") + 2 seats + 2 scenarios + 2 criteria) % 3 cases = 1: Rival one is A and scores 4.
        self.assertEqual(self.result["verdict"], "rival-wins:Rival one")
        totals = {t["design"]: t["score"] for t in self.result["totals"]}
        self.assertEqual(totals, {"Rival one": 4.0, "Rival two": 3.0, "T": 3.0})
        self.assertEqual(self.result["grafts"][0]["from"], "Rival one")
        self.assertEqual(len(self.result["walk"]), 2)


class FakeRunner:
    """Answers by the stage's schema, as the CLI would; *fail* names schemas to fail."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, prompt, spec):
        self.calls.append((prompt, spec))
        props = set(spec["schema"]["properties"])
        if props & self.fail:
            return None, {"output_tokens": 7}, "error_max_turns: stopped"
        if "findings" in props:
            answer = {"findings": [{"claim": "c", "failure_scenario": "A person does this and it goes wrong.",
                                    "quote": "q", "severity": "S2", "fix": "f"}], "held": ["h"]}
        elif "case" in props:
            answer = {"case": "Core idea: x.", "take": []}
        elif "verdicts" in props:
            answer = {"verdicts": [{"id": "F1", "verdict": "VERIFIED", "severity": "S2", "reason": "r", "same_as": ""}]}
        elif "words" in props:
            answer = {"verdict": "UNSETTLED", "file": "", "line": 0, "words": "", "note": ""}
        else:
            answer = challenge.STUB["frame"](None) if "halt" in props else {"results": []} if "results" in props else \
                {"scores": [], "grafts": [], "missing_from_all": []} if "scores" in props else \
                {"overturned": [], "conflicts": [], "overreach": [], "gaps": []}
        return answer, {"output_tokens": 100, "input_tokens": 10, "cache_read_input_tokens": 5, "usd": 0.01}, None


class TestRun(unittest.TestCase):
    def test_a_run_counts_what_its_agents_report(self):
        runner = FakeRunner()
        result = challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"]}, mode="run"),
                                     runner=runner, log=lambda line: None).run()
        self.assertEqual(len(runner.calls), result["cost"]["agents"])
        self.assertEqual(result["cost"]["output_tokens"], 100 * len(runner.calls))
        self.assertEqual(result["cost"]["input_tokens"], 15 * len(runner.calls))
        self.assertEqual(result["verdict"], "holds-with-changes")

    def test_a_failed_agent_is_reported_and_the_run_goes_on(self):
        runner = FakeRunner(fail={"findings"})
        result = challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"]}, mode="run"),
                                     runner=runner, log=lambda line: None).run()
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("attack: Seat one: error_max_turns", result["errors"][0])
        self.assertIn("attack: Seat two (agent failed)", result["dropped"])
        self.assertEqual(result["defects"], [])
        self.assertEqual(result["cost"]["output_tokens"], 7 * 2 + 100)  # the frame answered

    def test_the_agent_limit_drops_what_does_not_fit(self):
        frame = dict(FRAME, limits={"agents": 3})
        result = challenge.Challenge(_args(frame), runner=None).run()
        self.assertEqual(result["cost"]["agents"], 3)
        self.assertIn("rivals: the proposal (limit reached)", result["dropped"])

    def test_each_agent_is_reported_as_it_finishes_with_its_own_time(self):
        # Collected in the order they were sent, a quick agent queued behind a slow one was
        # logged when the slow one finished, with the slow one's time.
        import time as clock

        slow_started = threading.Event()

        def runner(prompt, spec):
            if "Seat one" in prompt:
                slow_started.set()
                clock.sleep(0.4)
            else:
                slow_started.wait(1)
            return FakeRunner()(prompt, spec)

        lines = []
        frame = {"title": "T", "brief": "b", "seats": FRAME["seats"], "limits": {"waves": 1}}  # both seats at once
        challenge.Challenge(_args(frame, mode="run"), runner=runner, log=lines.append).run()
        attack = [line for line in lines if line.startswith("[Attack]")]
        self.assertTrue(attack[0].startswith("[Attack] Seat two"), attack)
        self.assertIn("done in 0s", attack[0])

    def test_judges_and_walkers_answer_in_the_frames_own_names_and_letters(self):
        # A judge wrote "Fits code rules" for the criterion "Fits the code rules"; the names'
        # containment test missed it and that judge's scores were dropped without a word.
        runner = FakeRunner()
        challenge.Challenge(_args(dict(FRAME, audit=False), mode="run"), runner=runner, log=lambda line: None).run()
        schemas = {}
        for _, spec in runner.calls:
            schemas.setdefault(tuple(sorted(spec["schema"]["properties"])), spec["schema"])
        judge = schemas[("grafts", "missing_from_all", "scores")]["properties"]
        score = judge["scores"]["items"]["properties"]
        self.assertEqual(score["criterion"]["enum"], ["Simple", "Safe"])
        self.assertEqual(sorted(score["design"]["enum"]), ["A", "B", "C"])
        self.assertEqual(sorted(judge["grafts"]["items"]["properties"]["from"]["enum"]), ["A", "B", "C"])
        walk = schemas[("results",)]["properties"]["results"]["items"]["properties"]
        self.assertEqual(sorted(walk["design"]["enum"]), ["A", "B", "C"])
        verdicts = schemas[("verdicts",)]["properties"]["verdicts"]["items"]["properties"]
        self.assertEqual(verdicts["id"]["enum"], ["F1", "F2"])
        self.assertEqual(verdicts["same_as"]["enum"], ["", "F1", "F2"])
        self.assertNotIn("enum", challenge.S_JUDGE["properties"]["scores"]["items"]["properties"]["criterion"],
                         "the shared schema is copied, never changed")

    def test_reviewers_get_no_tools_and_the_critics_rules(self):
        runner = FakeRunner()
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"][:1]}, mode="run"),
                            runner=runner, log=lambda line: None).run()
        for prompt, spec in runner.calls:
            self.assertEqual(spec["tools"], "")
            self.assertIn("independent reviewer", spec["system"])
            self.assertNotIn("name: critic", spec["system"], "the agent file's header is not part of the prompt")
        models = [spec["model"] for _, spec in runner.calls]
        self.assertEqual(models[0], "sonnet")  # the frame check, on the critic model
        self.assertIsNone(models[-1])  # the verifier, on the CLI's default model

    def test_each_agent_reports_what_it_read_as_well_as_what_it_wrote(self):
        # Measured 2026-11-25: reads were four fifths of a run's tokens and no line said which agent read them.
        lines = []
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"][:1]}, mode="run"),
                            runner=FakeRunner(), log=lines.append).run()
        self.assertIn("100 tokens written, 15 read", lines[0])

    def test_later_seats_are_shown_what_the_first_ones_raised(self):
        # Measured 2026-11-25: six seats working blind raised 30 findings, 21 of them repeats, and all six
        # raised the same one, while the audit found a whole part of the subject untested.
        seats = [{"name": "Seat %s" % n, "lens": "Look."} for n in ("one", "two", "three", "four")]
        def named(prompt):
            return {"findings": [{"claim": "the claim of %s" % _seat_of(prompt), "quote": "q", "severity": "S2",
                                  "failure_scenario": "A person does this and it goes wrong.", "fix": "f"}], "held": []}

        runner = Scripted({"findings": named})
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": seats}, mode="run"),
                            runner=runner, log=lambda line: None).run()
        prompts = {_seat_of(p): p for p, s in runner.calls if "findings" in s["schema"]["properties"]}
        self.assertNotIn("ALREADY RAISED", prompts["Seat one"] + prompts["Seat two"])
        for later in ("Seat three", "Seat four"):
            self.assertIn("ALREADY RAISED", prompts[later])
            self.assertIn("the claim of Seat one", prompts[later])
            self.assertIn("the claim of Seat two", prompts[later])
        self.assertNotIn("the claim of Seat three", prompts["Seat four"], "the seats of one wave work in parallel")
        blind = Scripted({"findings": named})
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": seats, "limits": {"waves": 1}}, mode="run"),
                            runner=blind, log=lambda line: None).run()
        self.assertFalse(any("ALREADY RAISED" in p for p, _ in blind.calls))
        # As many groups as the frame asks for, the earlier ones the larger: four seats in three waves are 2, 1, 1.
        three = Scripted({"findings": named})
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": seats, "limits": {"waves": 3}}, mode="run"),
                            runner=three, log=lambda line: None).run()
        prompts = {_seat_of(p): p for p, s in three.calls if "findings" in s["schema"]["properties"]}
        shown = {seat: sorted(n for n in ("one", "two", "three", "four") if "the claim of Seat %s" % n in p)
                 for seat, p in prompts.items()}
        self.assertEqual(shown, {"Seat one": [], "Seat two": [], "Seat three": ["one", "two"],
                                 "Seat four": ["one", "three", "two"]})

    def test_a_claim_that_was_dropped_is_not_called_taken(self):
        # The review's probe: a finding with no scenario is dropped from the result, yet later seats were told
        # it was taken, so nobody could raise it properly.
        def named(prompt):
            seat = _seat_of(prompt)
            return {"findings": [{"claim": "kept, from %s" % seat, "failure_scenario": "A person does this and it goes wrong.",
                                  "quote": "q", "severity": "S2", "fix": "f"},
                                 {"claim": "dropped, from %s" % seat, "failure_scenario": "too short", "quote": "q",
                                  "severity": "S2", "fix": "f"}], "held": []}

        runner = Scripted({"findings": named})
        challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"]}, mode="run"),
                            runner=runner, log=lambda line: None).run()
        second = next(p for p, s in runner.calls if "findings" in s["schema"]["properties"] and "YOUR SEAT: Seat two" in p)
        self.assertIn("kept, from Seat one", second)
        self.assertNotIn("dropped, from Seat one", second)

    def test_walkers_and_judges_are_told_what_is_settled_and_what_they_may_read(self):
        # Measured 2026-11-25: a rival that overturned three settled decisions was walked and judged by
        # readers never told of them, and a walker credited the unchanged design with a check the
        # as-built document says cannot run there.
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "What exists.")
            runner = FakeRunner()
            frame = dict(FRAME, audit=False, settled=["The carrier is one node."], evidence=[evidence])
            challenge.Challenge(_args(frame, mode="run"), runner=runner, log=lambda line: None).run()
        compared = [p for p, s in runner.calls if set(s["schema"]["properties"]) & {"results", "scores"}]
        self.assertEqual(len(compared), 3)  # two walks and a judge
        for prompt in compared:
            self.assertIn("SETTLED", prompt)
            self.assertIn("The carrier is one node.", prompt)
            self.assertIn("as_built.md", prompt)
            self.assertNotIn("PROPOSAL:", prompt, "the designs stay under letters")
        judge = next(p for p, s in runner.calls if "scores" in s["schema"]["properties"])
        self.assertIn("using only what is in this message and the files under EVIDENCE", judge)
        plain = FakeRunner()
        challenge.Challenge(_args(dict(FRAME, audit=False), mode="run"), runner=plain, log=lambda line: None).run()
        self.assertNotIn("under EVIDENCE", next(p for p, s in plain.calls if "scores" in s["schema"]["properties"]))
        check = runner.calls[0][0]
        self.assertIn("A criterion that a design changing nothing scores full marks on", check)

    def test_evidence_named_from_here_is_listed_where_its_readers_find_it(self):
        """Each agent runs in an empty folder of its own, so an evidence path written relative to where the
        run started named no file it could read. Fixed: 2026-11-26"""
        here = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            _write(folder, "as_built.md", "What exists.")
            os.chdir(folder)
            try:
                runner = FakeRunner()
                challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"][:1],
                                           "evidence": ["as_built.md"]}, mode="run"), runner=runner, log=lambda line: None).run()
                where = os.path.realpath(folder)
            finally:
                os.chdir(here)
        for prompt, spec in runner.calls:
            self.assertIn("EVIDENCE (files you may read)\n- %s" % os.path.join(where, "as_built.md"), prompt)
            self.assertEqual(spec["add_dirs"], [where])


class RecordingGate:
    """A usage gate that lets every stage start and keeps what each was said to need."""

    def __init__(self):
        self.needs = []
        self.models = []

    def begin(self):
        pass

    def end(self, usd, tokens):
        pass

    def check(self, need, models=()):
        self.needs.append(need)
        self.models.append(list(models))
        return None


class TestGateNeeds(unittest.TestCase):
    """The gate holds a stage to the plan's own rule (``agent_tokens``), all of its waves counted."""

    def test_a_stage_is_held_to_what_its_agents_read_on_every_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "x" * 4000)  # 1,000 tokens
            gate, runner = RecordingGate(), FakeRunner()
            frame = {"title": "T", "brief": "b", "seats": [dict(FRAME["seats"][0], model="session")], "evidence": [evidence]}
            challenge.Challenge(_args(frame, mode="run"), runner=runner, log=lambda line: None, gate=gate).run()
        frame_prompt, seat_prompt = runner.calls[0][0], runner.calls[1][0]
        self.assertEqual(gate.needs[0], challenge.agent_tokens(challenge.tokens(frame_prompt), "critic", evidence=1000))
        self.assertEqual(gate.needs[1], challenge.agent_tokens(challenge.tokens(seat_prompt), "senior", evidence=1000))

    def test_the_first_wave_is_checked_with_the_later_seats_and_the_cases(self):
        gate, runner = RecordingGate(), FakeRunner()
        challenge.Challenge(_args(dict(FRAME, audit=False, scenarios=[]), mode="run"), runner=runner,
                            log=lambda line: None, gate=gate).run()
        prompts = [p for p, s in runner.calls if set(s["schema"]["properties"]) & {"findings", "case"}]
        self.assertEqual(len(prompts), 5)  # two seats in two waves, three cases
        alone = [challenge.agent_tokens(challenge.tokens(p), "critic") for p in prompts]
        # Seat two's prompt in the count ahead is its blind one: what Seat one raises is not known yet.
        blind_two = challenge.agent_tokens(challenge.tokens(prompts[1].split("ALREADY RAISED")[0].rstrip()), "critic")
        self.assertEqual(gate.needs[1], alone[0] + blind_two + sum(alone[2:]))
        self.assertEqual(gate.needs[2], alone[1] + sum(alone[2:]))  # the second wave, and the cases beside it

    def test_a_stage_is_held_to_the_windows_of_the_models_it_runs_on(self):
        # A full weekly window of another model is no reason to stop a stage; the CLI's default model (no
        # name) is unknown, so it adds no window of its own.
        gate = RecordingGate()
        frame = {"title": "T", "brief": "b", "seats": [dict(FRAME["seats"][0], model="session")],
                 "models": {"senior": "opus"}}
        challenge.Challenge(_args(frame, mode="run"), runner=FakeRunner(), log=lambda line: None, gate=gate).run()
        self.assertEqual(gate.models[:2], [["sonnet"], ["opus"]])  # the frame check, then the senior seat
        gate = RecordingGate()
        challenge.Challenge(_args(dict(frame, models={}), mode="run"), runner=FakeRunner(), log=lambda line: None,
                            gate=gate).run()
        self.assertEqual(gate.models[1], [])


STORE = "def get(cache, k):\n    return cache[k]  # reads by key\n" + "\n" * 40 + "def put(cache, k, v):\n    cache[k] = v\n"
READS = "return cache[k]  # reads by key"  # line 2 of STORE


class TestSettle(unittest.TestCase):
    """Measured 2026-11-25: both open questions of a run were settled by one search each in the code,
    and the two weaknesses no reviewer raised were the two only the code shows. No stage could look."""

    def _run(self, verdicts, settled, audited=None, **frame):
        """*settled*: per finding id a verdict (cited at the line that is there) or a whole answer;
        *audited*: the audit's answer. Each agent answers for the one finding it was handed."""
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="challenge_root_"))
        self.addCleanup(challenge.shutil.rmtree, self.root, True)
        _write(self.root, "store.py", STORE)
        frame = dict({"title": "T", "brief": "b", "seats": FRAME["seats"], "roots": [self.root], "limits": {"contest": 0}},
                     **frame)

        def found(prompt):
            mine = next(i for i in settled if "[%s]" % i in prompt.split("FINDING")[-1])
            v = settled[mine]
            return v if isinstance(v, dict) else {"verdict": v, "file": "store.py", "line": 2, "words": READS, "note": "n"}

        answers = {"verdicts": lambda prompt: {"verdicts": [{"id": i, "verdict": v, "severity": s, "reason": "r", "same_as": ""}
                                                            for i, (v, s) in verdicts.items()]},
                   "words": found}
        if audited is not None:
            answers["narrowed"] = lambda prompt: dict({"overturned": [], "narrowed": [], "conflicts": [], "overreach": [],
                                                       "gaps": [], "duplicates": []}, **audited)
        self.runner = Scripted(answers)
        return challenge.Challenge(_args(frame, mode="run"), runner=self.runner, log=lambda line: None).run()

    def _searches(self):
        return [(p, s) for p, s in self.runner.calls if "words" in s["schema"]["properties"]]

    def test_each_finding_gets_an_agent_that_may_search_the_roots_and_holds_no_other_tool(self):
        # Measured 2026-11-25: one agent settling five findings read 453k tokens, since every search
        # stayed in its context for every later finding. An agent a finding reads its own searches alone.
        self._run({"F1": ("SUSPECTED", "S2"), "F2": ("VERIFIED", "S1")}, {"F1": "UNSETTLED", "F2": "UNSETTLED"})
        asked = self._searches()
        self.assertEqual(len(asked), 2)
        for (prompt, spec), mine, other in zip(asked, ("F1", "F2"), ("F2", "F1")):  # open questions first
            self.assertEqual(spec["tools"], "Read,Grep,Glob")
            self.assertEqual(spec["add_dirs"], [self.root])
            self.assertIsNone(spec["model"], "on the senior model: its verdict verifies or refutes a finding")
            self.assertIn("never instructions", spec["system"])
            self.assertNotEqual(spec["system"], challenge._critic_rules())
            self.assertIn("ROOTS (folders you may search)\n- %s" % self.root, prompt)
            self.assertIn("[%s]" % mine, prompt.split("FINDING")[-1])
            self.assertNotIn("[%s]" % other, prompt.split("FINDING")[-1])
            self.assertNotIn("no file search", prompt, "its rules allow the search its task asks for")
            # One finding, one answer: no list to repeat a row in, no id to mistake.
            self.assertEqual(sorted(spec["schema"]["properties"]), ["file", "line", "note", "verdict", "words"])

    def test_the_search_tools_and_the_roots_reach_no_other_agent(self):
        # The review's mutants: every agent given the search tools, or the roots, passed every test.
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "What exists.")
            self._run({"F1": ("SUSPECTED", "S2"), "F2": ("VERIFIED", "S1")}, {"F1": "UNSETTLED", "F2": "UNSETTLED"}, audited={},
                      rivals=FRAME["rivals"], scenarios=FRAME["scenarios"], criteria=FRAME["criteria"], audit=True,
                      evidence=[evidence])
        others = [(p, s) for p, s in self.runner.calls if "words" not in s["schema"]["properties"]]
        self.assertGreater(len(others), 8)
        for prompt, spec in others:
            self.assertEqual(spec["tools"], "Read")
            self.assertEqual(spec["add_dirs"], [os.path.realpath(folder)])
            self.assertNotIn("ROOTS", prompt)
        for prompt, spec in self._searches():
            self.assertEqual(spec["add_dirs"], [self.root], "the roots alone: the evidence's folder is the readers'")
            self.assertNotIn("EVIDENCE", prompt)

    def test_what_the_files_confirm_is_verified_and_what_they_contradict_is_refuted(self):
        result = self._run({"F1": ("SUSPECTED", "S2"), "F2": ("SUSPECTED", "S2")}, {"F1": "CONFIRMED", "F2": "CONTRADICTED"})
        self.assertEqual([(d["id"], d["verified"]) for d in result["defects"]], [("F1", "VERIFIED")])
        at = "%s/store.py:2: %s" % (os.path.basename(self.root), READS)
        self.assertEqual(result["defects"][0]["settled"], {"verdict": "CONFIRMED", "evidence": at, "note": "n"})
        self.assertEqual(result["open_questions"], [])
        self.assertEqual([f["id"] for f in result["refuted_findings"]], ["F2"])
        self.assertIn("store.py:2", result["refuted_findings"][0]["reason"])
        self.assertEqual({s["seat"]: s["refuted"] for s in result["seat_stats"]}["Seat two"], 1)
        self.assertEqual(result["refuted"], 1)

    def test_a_verified_finding_the_files_contradict_becomes_a_question(self):
        result = self._run({"F1": ("VERIFIED", "S1"), "F2": ("VERIFIED", "S1")}, {"F1": "CONTRADICTED", "F2": "UNSETTLED"})
        by_id = {d["id"]: d for d in result["defects"]}
        self.assertEqual((by_id["F1"]["verified"], by_id["F2"]["verified"]), ("SUSPECTED", "VERIFIED"))
        self.assertIn("store.py:2", by_id["F1"]["reason"])
        self.assertEqual(by_id["F2"]["settled"]["verdict"], "UNSETTLED")
        self.assertEqual(len(result["open_questions"]), 1)

    def test_a_verdict_rests_on_a_line_the_run_itself_opened(self):
        # The review's probe: evidence "n/a" with CONTRADICTED refuted an open S1. A pattern for "names a
        # line" would pass any line number; the run opens the file and looks for the words.
        def cite(**parts):
            return dict({"verdict": "CONTRADICTED", "file": "store.py", "line": 2, "words": READS, "note": "n"}, **parts)

        other = os.path.realpath(tempfile.mkdtemp(prefix="challenge_elsewhere_"))
        self.addCleanup(challenge.shutil.rmtree, other, True)
        outside = _write(other, "store.py", STORE)
        for name, answer in {"words that are not there": cite(words="return cache.get(k)  # reads by key"),
                             "the words, far from the line": cite(line=30),
                             "a file outside the roots": cite(file=outside),
                             "no file": cite(file="n/a", line=0, words=""),
                             "too few words to tell a line by": cite(words="k]")}.items():
            result = self._run({"F1": ("SUSPECTED", "S1")}, {"F1": answer})
            self.assertEqual((result["defects"][0]["verified"], result["defects"][0]["settled"]["verdict"]),
                             ("SUSPECTED", "UNSETTLED"), name)
            self.assertEqual(result["refuted_findings"], [], name)
        self.assertIn("were not found", result["defects"][0]["settled"]["note"])
        # However an agent writes the path, and whatever its spacing, quotes or case: the same line.
        here = os.path.basename(self.root)
        for file in ("store.py", "%s/store.py" % here, "%s\\store.py" % here, os.path.join(self.root, "store.py")):
            self.assertEqual(challenge.cited([self.root], file, 2, READS), "%s/store.py:2" % here, file)
        self.assertEqual(challenge.cited([self.root], "store.py", 4, "`return  cache[k]` # Reads by key"), "%s/store.py:4" % here)
        self.assertEqual(challenge.cited([self.root], "elsewhere/store.py", 2, READS), "")

    def test_a_cited_name_is_a_name_never_a_pattern(self):
        """An agent wrote the file name; ``a**b.py`` raised out of the run as a bad glob. Fixed: 2026-11-26"""
        root = os.path.realpath(tempfile.mkdtemp(prefix="challenge_root_"))
        self.addCleanup(challenge.shutil.rmtree, root, True)
        _write(root, "store.py", STORE)
        os.makedirs(os.path.join(root, "deep", "er"))
        _write(os.path.join(root, "deep", "er"), "other.py", STORE)
        for name in ("a**b.py", "st*.py", "store[.py", "../%s/store.py" % os.path.basename(root)):
            with self.subTest(name=name):
                self.assertEqual(challenge.cited([root], name, 2, READS), "")
        here = os.path.basename(root)
        self.assertEqual(challenge.cited([root], "other.py", 2, READS), "%s/deep/er/other.py:2" % here, "found anywhere under")

    def test_minor_findings_are_not_searched_for_and_the_limit_says_what_it_left(self):
        # The review's probe: nine minor open questions filled the pool and the one verified S1 was never settled.
        self._run({"F1": ("SUSPECTED", "S3"), "F2": ("VERIFIED", "S1")}, {"F2": "UNSETTLED"})
        self.assertEqual(len(self._searches()), 1)
        self.assertIn("[F2]", self._searches()[0][0].split("FINDING")[-1])
        result = self._run({"F1": ("SUSPECTED", "S2"), "F2": ("VERIFIED", "S1")}, {"F1": "UNSETTLED"},
                           limits={"contest": 0, "settle": 1})
        self.assertEqual(len(self._searches()), 1)
        self.assertIn("settle: 1 findings beyond the first 1 were not checked against the files", result["dropped"])

    def test_without_roots_no_agent_searches(self):
        result = self._run({"F1": ("SUSPECTED", "S2")}, {}, roots=[])
        self.assertEqual(self._searches(), [])
        self.assertTrue(all(s["tools"] == "" for _, s in self.runner.calls))
        self.assertNotIn("settled", result["defects"][0])
        self._run({"F1": ("SUSPECTED", "S2")}, {}, limits={"contest": 0, "settle": 0})
        self.assertEqual(self._searches(), [])

    def test_the_files_are_searched_last_for_what_the_audit_left_in_its_corrected_words(self):
        # Measured 2026-11-25, searching before the audit: two of six searches went to findings the audit
        # then joined to others, and a finding it narrowed was searched for in the words it had corrected.
        verdicts = {i: ("VERIFIED", "S1") for i in ("F1", "F2")}
        both = {"F1": "CONFIRMED", "F2": "CONFIRMED"}

        def searched(audited):
            result = self._run(verdicts, both, audited=audited, audit=True)
            kinds = ["search" if "words" in s["schema"]["properties"] else "audit" if "narrowed" in s["schema"]["properties"]
                     else "" for _, s in self.runner.calls]
            self.assertLess(kinds.index("audit"), kinds.index("search"))
            return result, [p.split("FINDING")[-1] for p, _ in self._searches()]

        _, asked = searched({"narrowed": [{"id": "F1", "claim": "The narrower claim that stands."}]})
        self.assertEqual(len(asked), 2)
        self.assertIn("The narrower claim that stands.", asked[0])
        result, asked = searched({"overturned": [{"id": "F2", "reason": "The text answers it whole."}]})
        self.assertEqual(len(asked), 1)  # F2 is answered by the text: no question for the files
        self.assertIn("[F1]", asked[0])
        by_id = {d["id"]: d for d in result["defects"]}
        self.assertEqual((by_id["F2"]["verified"], "settled" in by_id["F2"]), ("SUSPECTED", False))
        _, asked = searched({"duplicates": [{"ids": "F1, F2", "why": "one defect"}]})
        self.assertEqual(len(asked), 1)  # F2 joined F1: one search, not two

    def test_a_search_is_never_kept_and_every_other_answer_is(self):
        # The review's probe: a line was edited, the same command was run again, and the kept answer still
        # cited the old line as what is really there. No key can say what a search will read.
        root = os.path.realpath(tempfile.mkdtemp(prefix="challenge_root_"))
        self.addCleanup(challenge.shutil.rmtree, root, True)
        frame = {"title": "T", "brief": "b", "seats": FRAME["seats"][:1], "roots": [root], "limits": {"contest": 0}}
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "result.json.answers.json")

            def run():
                runner = FakeRunner()
                result = challenge.Challenge(_args(frame, mode="run"), runner=runner, log=lambda line: None, cache=cache).run()
                return [sorted(s["schema"]["properties"])[-1] for _, s in runner.calls], result["cost"]["reused"]

            first, _ = run()
            self.assertEqual(len(first), 4)  # the frame check, the seat, the verifier and the one that searches
            self.assertEqual(run(), (["words"], 3))

    def test_a_rerun_asks_again_once_an_evidence_file_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = _write(folder, "as_built.md", "What exists.")
            cache = os.path.join(folder, "result.json.answers.json")
            frame = {"title": "T", "brief": "b", "seats": FRAME["seats"][:1], "evidence": [evidence]}

            def run():
                runner = FakeRunner()
                challenge.Challenge(_args(frame, mode="run"), runner=runner, log=lambda line: None, cache=cache).run()
                return len(runner.calls)

            self.assertEqual((run(), run()), (3, 0))
            _write(folder, "as_built.md", "What exists now.")
            self.assertEqual(run(), 3)

    def test_the_self_test_runs_the_stage_on_canned_answers(self):
        result = challenge.Challenge(_args(dict(FRAME, roots=["."]))).run()
        # The 12 of the frame without roots, and one search: of the two verified findings the audit found
        # one answered by the text, which is then no question for the files.
        self.assertEqual(result["cost"]["agents"], 13)
        by_id = {d["id"]: d for d in result["defects"]}
        self.assertEqual(by_id["F1"]["settled"]["verdict"], "CONFIRMED")
        self.assertNotIn("settled", by_id["F2"])


class TestClaudeCli(unittest.TestCase):
    def setUp(self):
        self.cli = challenge.ClaudeCli(exe="claude", workdir=tempfile.gettempdir())

    def _spec(self, **more):
        return dict({"schema": challenge.S_CASE, "model": "sonnet", "tools": "", "system": "rules"}, **more)

    def test_an_agent_runs_isolated_with_no_tools_and_answers_to_its_schema(self):
        cmd = self.cli.command(self._spec())
        for flag in ("-p", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(json.loads(cmd[cmd.index("--json-schema") + 1]), challenge.S_CASE)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "rules")
        self.assertNotIn("--allowedTools", cmd)

    #: A folder as this machine writes it, and the permission rule Claude Code's settings give it (an absolute
    #: path behind ``//``, a Windows drive as ``/c``; a parenthesis escaped).
    FOLDER, RULE = ((r"C:\Work\Team (A)\evidence", r"Read(//c/Work/Team \(A\)/evidence/**)") if os.name == "nt"
                    else ("/work/Team (A)/evidence", r"Read(//work/Team \(A\)/evidence/**)"))

    def test_evidence_gives_the_read_tool_in_its_folders_and_a_claim_the_web(self):
        """``--allowedTools Read`` permitted a read anywhere, past the folders the docs confined it to: a
        tool that reads files is permitted by a rule per folder opened to it, never by its name. Fixed: 2026-11-26"""
        cmd = self.cli.command(self._spec(tools="Read", add_dirs=[self.FOLDER]))
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read")
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], self.FOLDER)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], self.RULE)
        cmd = self.cli.command(self._spec(tools="Read,Grep,Glob", add_dirs=[self.FOLDER, self.FOLDER + "2"]))
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1].split(","),
                         [self.RULE, self.RULE.replace("evidence/", "evidence2/")])
        cmd = self.cli.command(self._spec(tools="WebSearch,WebFetch", model=None, effort="high"))
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch,WebFetch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch,WebFetch")
        self.assertNotIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")

    def _answered(self, stdout, code=0):
        done = subprocess.CompletedProcess([], code, stdout=stdout, stderr="boom")
        with mock.patch.object(challenge.subprocess, "run", return_value=done) as ran:
            answer = self.cli("the prompt", self._spec())
        self.assertEqual(ran.call_args.kwargs["input"], "the prompt", "the prompt goes on stdin")
        return answer

    def test_the_structured_answer_and_its_usage_are_read(self):
        out = json.dumps({"is_error": False, "subtype": "success", "structured_output": {"case": "x", "take": []},
                          "usage": {"output_tokens": 12}, "total_cost_usd": 0.02})
        answer, usage, error = self._answered(out)
        self.assertEqual(answer, {"case": "x", "take": []})
        self.assertEqual((usage["output_tokens"], usage["usd"], error), (12, 0.02, None))

    def test_an_error_or_no_answer_is_a_failure_with_its_reason(self):
        answer, _, error = self._answered(json.dumps({"is_error": True, "subtype": "error_max_turns", "result": "stopped"}))
        self.assertIsNone(answer)
        self.assertIn("error_max_turns", error)
        answer, _, error = self._answered("not json", code=1)
        self.assertIsNone(answer)
        self.assertIn("exit 1", error)

    def test_a_missing_claude_command_is_said_plainly(self):
        with mock.patch.object(challenge.shutil, "which", return_value=None), self.assertRaises(SystemExit) as refused:
            challenge.ClaudeCli()
        self.assertIn("--claude", str(refused.exception))


class Scripted(FakeRunner):
    """FakeRunner with some stages' answers given: ``{schema property: answer(prompt) -> dict}``."""

    def __init__(self, answers):
        super().__init__()
        self.answers = answers

    def __call__(self, prompt, spec):
        for prop, answer in self.answers.items():
            if prop in spec["schema"]["properties"]:
                self.calls.append((prompt, spec))
                return answer(prompt), {"output_tokens": 1}, None
        return super().__call__(prompt, spec)


def _always(answer):
    """A stage's answer that does not depend on what it is asked, a fresh copy each time (``Scripted``)."""
    return lambda prompt: copy.deepcopy(answer)


def _judged(scores):
    """A judge answer from ``{letter: {criterion: score}}``."""
    return _always({"scores": [{"design": label, "criterion": c, "score": s, "reason": "r"}
                               for label, row in scores.items() for c, s in row.items()],
                    "grafts": [], "missing_from_all": []})


class TestJudgement(unittest.TestCase):
    """What the comparison concludes must follow from what its readers found."""

    def _run(self, frame, answers):
        return challenge.Challenge(_args(frame, mode="run"), runner=Scripted(answers), log=lambda line: None).run()

    def test_a_design_that_fails_a_must_have_cannot_win_however_it_scores_elsewhere(self):
        # Measured: the top-ranked rival broke two scenarios and failed "no guessing", and won on
        # readability's weight. Letters (k = 1): A = Rival one, B = Rival two, C = the subject.
        frame = dict(FRAME, audit=False, criteria=[{"name": "Simple", "weight": 2},
                                                   {"name": "Safe", "weight": 1, "gate": True}])
        judge = _judged({"A": {"Simple": 5, "Safe": 2}, "B": {"Simple": 3, "Safe": 3}, "C": {"Simple": 4, "Safe": 3}})
        result = self._run(frame, {"scores": judge})
        totals = {t["design"]: t for t in result["totals"]}
        self.assertEqual(totals["Rival one"]["fails"], ["Safe"])
        self.assertEqual(totals["T"]["fails"], [])
        self.assertFalse(result["verdict"].startswith("rival-wins"), result["verdict"])
        frame["criteria"][1]["gate"] = False
        self.assertEqual(self._run(frame, {"scores": judge})["verdict"], "rival-wins:Rival one")

    def test_a_subject_that_fails_a_must_have_says_so(self):
        frame = dict(FRAME, audit=False, criteria=[{"name": "Simple"}, {"name": "Safe", "gate": True}])
        judge = _judged({"A": {"Simple": 3, "Safe": 2}, "B": {"Simple": 3, "Safe": 2}, "C": {"Simple": 5, "Safe": 1}})
        self.assertEqual(self._run(frame, {"scores": judge})["verdict"], "fails-gate:Safe")

    def test_a_walk_outcome_follows_from_what_the_walker_found(self):
        # Measured: a walker wrote "holds" beside "a wrong guess still builds silently".
        walked = _always({"results": [
            {"design": "A", "handled": True, "silent_wrong": True, "manual_work": False, "how": "h", "weakest": "w"},
            {"design": "B", "handled": True, "silent_wrong": False, "manual_work": True, "how": "h", "weakest": "w"},
            {"design": "C", "handled": True, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"}]})
        result = self._run(dict(FRAME, audit=False), {"results": walked})
        outcomes = {r["design"]: r["outcome"] for r in result["walk"][0]["results"]}
        self.assertEqual(outcomes, {"Rival one": "breaks", "Rival two": "strains", "T": "holds"})
        self.assertNotIn("outcome", challenge.S_WALK["properties"]["results"]["items"]["properties"],
                         "the walker states facts; the outcome is derived from them")

    def test_a_walk_says_when_a_design_does_not_state_what_happens(self):
        # Measured 2026-11-25: every design "broke" 8 to 11 of 11 scenarios, the unchanged one included. A
        # walker asked whether anything CAN go wrong says yes of a 400-word case that is silent on the point.
        walked = _always({"results": [
            {"design": "A", "stated": False, "handled": False, "silent_wrong": True, "manual_work": True, "how": "h", "weakest": "w"},
            {"design": "B", "stated": True, "handled": True, "silent_wrong": True, "manual_work": False, "how": "h", "weakest": "w"},
            {"design": "C", "stated": True, "handled": True, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"}]})
        runner = Scripted({"results": walked})
        result = challenge.Challenge(_args(dict(FRAME, audit=False), mode="run"), runner=runner, log=lambda line: None).run()
        outcomes = {r["design"]: r["outcome"] for r in result["walk"][0]["results"]}
        self.assertEqual(outcomes, {"Rival one": "unstated", "Rival two": "breaks", "T": "holds"})
        totals = {t["design"]: t["walk"] for t in result["totals"]}
        self.assertEqual(totals["Rival one"], {"holds": 0, "strains": 0, "breaks": 0, "unstated": 2})
        asked = next(p for p, s in runner.calls if "results" in s["schema"]["properties"])
        self.assertIn("stated (true when the design's own text says what happens", asked)
        self.assertIn("as stated", asked.split("silent_wrong")[1].split(";")[0])
        # An answer kept from before the walker was asked reads as stated: its outcome does not change.
        self.assertEqual(challenge.walk_outcome({"handled": True, "silent_wrong": True}), "breaks")

    def test_the_result_says_when_the_walk_does_not_tell_the_designs_apart(self):
        broke = _always({"results": [{"design": label, "stated": True, "handled": True, "silent_wrong": True,
                                       "manual_work": False, "how": "h", "weakest": "w"} for label in "ABC"]})
        frame = dict(FRAME, audit=False, scenarios=["One.", "Two.", "Three."])
        result = challenge.Challenge(_args(frame, mode="run"), runner=Scripted({"results": broke}), log=lambda line: None).run()
        self.assertTrue(any("no design holds a third of the 3 scenarios" in c for c in result["checks"]), result["checks"])
        held = _always({"results": [{"design": label, "stated": True, "handled": True, "silent_wrong": label == "A",
                                      "manual_work": False, "how": "h", "weakest": "w"} for label in "ABC"]})
        result = challenge.Challenge(_args(frame, mode="run"), runner=Scripted({"results": held}), log=lambda line: None).run()
        self.assertFalse(any("no design holds a third" in c for c in result["checks"]), result["checks"])

    def test_an_audit_that_corrects_part_of_a_finding_keeps_its_verdict(self):
        # Measured 2026-11-25: a finding all six seats raised and the verifier confirmed S1 was listed under
        # the audit's overturned findings as "Partial", for one wrong sentence, and left the verified findings.
        verdicts = _always({"verdicts": [{"id": i, "verdict": "VERIFIED", "severity": "S1", "reason": "r", "same_as": ""}
                                          for i in ("F1", "F2")]})
        audited = _always({"overturned": [{"id": "F1", "reason": "Partial: one sentence is answered."},
                                           {"id": "F2", "reason": "The text answers it whole."}],
                            "narrowed": [{"id": "F1", "claim": "The narrower claim that stands."}],
                            "conflicts": [], "overreach": [], "gaps": [], "duplicates": []})
        runner = Scripted({"verdicts": verdicts, "narrowed": audited})
        result = challenge.Challenge(_args({"title": "T", "brief": "b", "seats": FRAME["seats"], "audit": True}, mode="run"),
                                     runner=runner, log=lambda line: None).run()
        by_id = {d["id"]: d for d in result["defects"]}
        self.assertEqual((by_id["F1"]["verified"], by_id["F1"]["claim"], by_id["F1"]["narrowed_from"]),
                         ("VERIFIED", "The narrower claim that stands.", "c"))
        self.assertEqual(by_id["F2"]["verified"], "SUSPECTED")
        self.assertNotIn("narrowed_from", by_id["F2"])
        asked = next(p for p, s in runner.calls if "narrowed" in s["schema"]["properties"])
        self.assertIn("narrowed (", asked)
        self.assertIn("whole", asked.split("overturned (")[1].split(";")[0])

    def test_the_audit_changes_only_the_findings_it_was_shown_and_keeps_the_first_claim(self):
        # The review's probes: a second narrowing lost the original claim, and a narrowing rewrote an open
        # question the audit had never been shown.
        verdicts = _always({"verdicts": [{"id": "F1", "verdict": "VERIFIED", "severity": "S1", "reason": "r", "same_as": ""},
                                          {"id": "F2", "verdict": "SUSPECTED", "severity": "S2", "reason": "r", "same_as": ""}]})
        audited = _always({"overturned": [{"id": "F2", "reason": "not shown"}],
                            "narrowed": [{"id": "F1", "claim": "first"}, {"id": "F1", "claim": "second"},
                                         {"id": "F2", "claim": "not shown either"}],
                            "conflicts": [], "overreach": [], "gaps": ["One thing."], "duplicates": []})
        frame = {"title": "T", "brief": "b", "seats": FRAME["seats"], "audit": True, "limits": {"contest": 0}}
        result = challenge.Challenge(_args(frame, mode="run"), runner=Scripted({"verdicts": verdicts, "narrowed": audited}),
                                     log=lambda line: None).run()
        by_id = {d["id"]: d for d in result["defects"]}
        self.assertEqual((by_id["F1"]["claim"], by_id["F1"]["narrowed_from"]), ("first", "c"))
        self.assertEqual((by_id["F2"]["claim"], by_id["F2"]["reason"]), ("c", "r"))
        self.assertNotIn("narrowed_from", by_id["F2"])
        self.assertTrue(any("the audit names 1 point the brief requires" in c for c in result["checks"]), result["checks"])

    def test_the_result_points_at_what_the_audit_and_the_frame_check_found_untested(self):
        # Measured 2026-11-25: the audit's "a whole move was not tested" and the frame check's best rival
        # sat in fields no summary reads, under a verdict that read as complete.
        framed = _always(dict(challenge.STUB["frame"](None), tilt=["The weights favour the subject."],
                               missing_rivals=["Read both, write old: one release reads both forms.", "Land first"]))
        audited = _always({"overturned": [], "narrowed": [], "conflicts": [], "overreach": [], "duplicates": [],
                            "gaps": ["Move 1 was not tested.", "Priority 3 was never counted."]})
        result = challenge.Challenge(_args(dict(FRAME), mode="run"), runner=Scripted({"halt": framed, "narrowed": audited}),
                                     log=lambda line: None).run()
        checks = result["checks"]
        self.assertTrue(any("the audit names 2 points" in c and "gaps" in c for c in checks), checks)
        self.assertTrue(any("Read both, write old" in c and "Land first" in c and "did not test" in c for c in checks), checks)
        self.assertTrue(any("tilt" in c for c in checks), checks)
        quiet = challenge.Challenge(_args(dict(FRAME, audit=False), mode="run"), runner=FakeRunner(), log=lambda line: None).run()
        self.assertFalse(any("audit" in c or "frame check" in c for c in quiet["checks"]), quiet["checks"])

    def test_the_audit_joins_findings_that_describe_one_defect(self):
        # Measured: verifiers in separate batches cannot see each other's findings, so repeats survived.
        verdicts = _always({"verdicts": [{"id": i, "verdict": "VERIFIED", "severity": "S2", "reason": "r", "same_as": ""}
                                          for i in ("F1", "F2")]})
        audited = _always({"overturned": [], "conflicts": [], "overreach": [], "gaps": [],
                            "duplicates": [{"ids": "F1, F2", "why": "the same defect"}]})
        result = self._run({"title": "T", "brief": "b", "seats": FRAME["seats"], "audit": True},
                           {"verdicts": verdicts, "duplicates": audited})
        self.assertEqual([d["id"] for d in result["defects"]], ["F1"])
        self.assertEqual(result["defects"][0]["also_from"], ["Seat two"])
        self.assertEqual({s["seat"]: s["duplicate"] for s in result["seat_stats"]}["Seat two"], 1)

    def test_the_result_says_when_its_ranking_contradicts_its_walk_or_is_a_tie(self):
        # Measured: the top-ranked rival broke two scenarios the subject held, and nothing said so.
        walked = _always({"results": [
            {"design": "A", "handled": True, "silent_wrong": True, "manual_work": False, "how": "h", "weakest": "w"},
            {"design": "B", "handled": True, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"},
            {"design": "C", "handled": True, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"}]})
        judge = _judged({"A": {"Simple": 5, "Safe": 5}, "B": {"Simple": 3, "Safe": 3}, "C": {"Simple": 4, "Safe": 4}})
        result = self._run(dict(FRAME, audit=False), {"results": walked, "scores": judge})
        totals = {t["design"]: t for t in result["totals"]}
        self.assertEqual(totals["Rival one"]["walk"], {"holds": 0, "strains": 0, "breaks": 2, "unstated": 0})
        self.assertEqual(totals["T"]["walk"], {"holds": 2, "strains": 0, "breaks": 0, "unstated": 0})
        self.assertTrue(any("Rival one" in c and "breaks 2" in c for c in result["checks"]), result["checks"])
        # Measured 2026-11-25: the top design broke 1 and held 4 where the subject broke none and left 9 of 11
        # unstated, and was said to contradict its walk. More breaks with more holds is no contradiction.
        def mostly(prompt):
            return {"results": [
                {"design": "A", "stated": True, "handled": True, "silent_wrong": "happens" in prompt.split("SCENARIO: ")[1][:20]
                 and "else" not in prompt.split("SCENARIO: ")[1][:25], "manual_work": False, "how": "h", "weakest": "w"},
                {"design": "B", "stated": True, "handled": True, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"},
                {"design": "C", "stated": False, "handled": False, "silent_wrong": False, "manual_work": False, "how": "h", "weakest": "w"}]}
        result = self._run(dict(FRAME, audit=False), {"results": mostly, "scores": judge})
        totals = {t["design"]: t for t in result["totals"]}
        self.assertEqual(totals["Rival one"]["walk"], {"holds": 1, "strains": 0, "breaks": 1, "unstated": 0})
        self.assertEqual(totals["T"]["walk"], {"holds": 0, "strains": 0, "breaks": 0, "unstated": 2})
        self.assertFalse(any("read the walk before the ranking" in c for c in result["checks"]), result["checks"])
        self.assertTrue(any("could not say what happens in most scenarios for T (2 of 2 unstated)" in c and "320 words" in c
                            for c in result["checks"]), result["checks"])
        tie = _judged({"A": {"Simple": 4, "Safe": 4}, "B": {"Simple": 3, "Safe": 3}, "C": {"Simple": 4, "Safe": 4}})
        result = self._run(dict(FRAME, audit=False), {"scores": tie})
        self.assertTrue(any("tie" in c for c in result["checks"]), result["checks"])

    def test_a_frame_check_alone_spends_one_agent(self):
        runner = FakeRunner()
        result = challenge.Challenge(_args(mode="frame"), runner=runner, log=lambda line: None).run()
        self.assertEqual((len(runner.calls), result["cost"]["agents"]), (1, 1))
        self.assertIn("missing_scenarios", result["frame"])
        self.assertNotIn("verdict", result)

    def test_the_previous_revision_is_judged_blind_beside_the_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            args = challenge.load_args(_write(folder, "design.txt", "New."), dict(FRAME), mode="stub",
                                       previous=_write(folder, "before.txt", "Old."))
        result = challenge.Challenge(args).run()
        designs = {t["design"] for t in result["totals"]}
        self.assertIn(challenge.PREVIOUS, designs)
        self.assertEqual(set(result["revision"]), {"subject_score", "previous_score", "better", "tie"})
        # Measured: 3.02 against 2.96 was reported better; within the margin it is a tie.
        self.assertEqual(challenge.Challenge.compare_revisions(3.02, 2.96, 0.25), {"subject_score": 3.02, "previous_score": 2.96, "better": False, "tie": True})
        self.assertTrue(challenge.Challenge.compare_revisions(3.4, 2.9, 0.25)["better"])
        plan = challenge.Challenge(dict(args, mode="plan")).run()["plan"]
        self.assertIn("the previous revision as a case", [p["label"] for p in plan])


class TestResume(unittest.TestCase):
    """Measured: a usage limit failed the judges, the recheck and the audit, and a re-run would pay for all 30 again."""

    def test_a_usage_limit_stops_new_agents_and_the_result_says_it_is_incomplete(self):
        class Limited(FakeRunner):
            def __call__(self, prompt, spec):
                if "scores" in spec["schema"]["properties"]:
                    self.calls.append((prompt, spec))
                    return None, {}, "usage limit: You've hit your 5-hour limit"
                return super().__call__(prompt, spec)

        runner = Limited()
        result = challenge.Challenge(_args(dict(FRAME), mode="run"), runner=runner, log=lambda line: None).run()
        self.assertEqual(result["verdict"], "incomplete")
        self.assertIn("audit: audit of the result (usage limit)", result["dropped"])
        self.assertIsNone(result["revision"])
        self.assertFalse(any("duplicates" in s["schema"]["properties"] for _, s in runner.calls), "no agent after the limit")

    def test_a_rerun_reuses_every_answer_it_already_has(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "result.json.answers.json")
            first = FakeRunner()
            challenge.Challenge(_args(dict(FRAME), mode="run"), runner=first, log=lambda line: None, cache=cache).run()
            again = FakeRunner()
            result = challenge.Challenge(_args(dict(FRAME), mode="run"), runner=again, log=lambda line: None, cache=cache).run()
        self.assertGreater(len(first.calls), 5)
        self.assertEqual(again.calls, [])
        self.assertEqual(result["cost"]["reused"], len(first.calls))

    def test_a_stopped_run_starts_no_queued_agent_and_keeps_every_answer_given(self):
        """Interrupted, the pool still started every queued agent before it let go, and the answers were written
        only after the stage, so a stopped run spent the whole stage and kept nothing. Fixed: 2026-11-26"""
        release, started = threading.Event(), []

        def runner(prompt, spec):
            if "findings" in spec["schema"]["properties"]:
                seat = _seat_of(prompt)
                started.append(seat)
                if seat == "Seat two":
                    release.wait(5)  # still running when the run is stopped
            return FakeRunner()(prompt, spec)

        def log(line):
            if line.startswith("[Attack] Seat one: done"):
                raise KeyboardInterrupt

        seats = [{"name": "Seat %s" % n, "lens": "Look."} for n in ("one", "two", "three")]
        frame = {"title": "T", "brief": "b", "seats": seats, "limits": {"workers": 1, "waves": 1}}
        before = set(threading.enumerate())
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "result.json.answers.json")
            with self.assertRaises(KeyboardInterrupt):
                challenge.Challenge(_args(frame, mode="run"), runner=runner, log=log, cache=cache).run()
            release.set()
            for thread in set(threading.enumerate()) - before:
                thread.join(5)
            self.assertNotIn("Seat three", started)
            with open(cache, encoding="utf-8") as handle:
                self.assertEqual(len(json.load(handle)), 2)  # the frame check and Seat one
            self.assertEqual(os.listdir(folder), ["result.json.answers.json"], "written whole, nothing left beside it")

    def test_the_cli_names_a_usage_limit_as_one(self):
        cli = challenge.ClaudeCli(exe="claude", workdir=tempfile.gettempdir())
        out = json.dumps({"is_error": True, "subtype": "success", "result": "You've hit your 5-hour limit · resets 3:30pm"})
        with mock.patch.object(challenge.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout=out, stderr="")):
            _, _, error = cli("p", {"schema": challenge.S_CASE, "system": "s"})
        self.assertTrue(error.startswith("usage limit"), error)


NOON = datetime(2026, 11, 20, 12, 0)  # hours from every reset below: each reserve in full
USAGE_TEXT = ("You are currently using your subscription to power your Claude Code usage\n\n"
              "Current session: 20% used · resets Nov 19, 8:30pm (America/New_York)\n"
              "Current week (all models): 50% used · resets Nov 21, 2am (America/New_York)\n")


class TestUsageGate(unittest.TestCase):
    """No stage starts that the account's usage windows cannot finish (read free from ``claude -p /usage``)."""

    def _gate(self, folder, readings, calibration=None):
        # The clock pinned hours from the readings' resets: a reserve that shrinks near the reset made these
        # red each evening from about 19:54 to 20:30.
        path = os.path.join(folder, "calibration.json")
        if calibration:
            _write(folder, "calibration.json", json.dumps(calibration))
        readings = list(readings)
        return challenge.UsageGate(lambda: readings.pop(0) if len(readings) > 1 else readings[0], path,
                                   clock=lambda: NOON), path

    def test_the_usage_text_is_read_into_windows(self):
        self.assertEqual(challenge.UsageGate.parse(USAGE_TEXT), {
            "session": {"pct": 20.0, "resets": "Nov 19, 8:30pm (America/New_York)"},
            "week": {"pct": 50.0, "resets": "Nov 21, 2am (America/New_York)"}})
        self.assertIsNone(challenge.UsageGate.parse("Usage is not available for API key accounts."))

    def test_a_window_nearly_used_up_stops_the_run_before_any_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            gate, _ = self._gate(folder, [{"session": {"pct": 97.0, "resets": "8:30pm"}}])
            runner = FakeRunner()
            result = challenge.Challenge(_args(dict(FRAME), mode="run"), runner=runner, log=lambda line: None, gate=gate).run()
        self.assertEqual(runner.calls, [])
        self.assertEqual(result["verdict"], "incomplete")
        self.assertIn("8:30pm", result["checks"][0])

    def test_a_stage_that_would_not_fit_what_is_left_is_not_started(self):
        # Learned: 40% of the window per dollar; the frame check (about $0.06) fits 10% left, the attack does not.
        with tempfile.TemporaryDirectory() as folder:
            gate, _ = self._gate(folder, [{"session": {"pct": 85.0, "resets": "8:30pm"}}],
                                 {"usd_per_token": 1e-5, "pct_per_usd": {"session": 40.0}})
            runner = FakeRunner()
            result = challenge.Challenge(_args(dict(FRAME), mode="run"), runner=runner, log=lambda line: None, gate=gate).run()
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(any("(usage limit)" in d and d.startswith("attack") for d in result["dropped"]), result["dropped"])
        self.assertEqual(result["verdict"], "incomplete")

    def test_a_run_teaches_the_gate_what_a_dollar_costs_each_window(self):
        with tempfile.TemporaryDirectory() as folder:
            gate, path = self._gate(folder, [{"session": {"pct": 10.0, "resets": "x"}, "week": {"pct": 40.0, "resets": "y"}},
                                             {"session": {"pct": 30.0, "resets": "x"}, "week": {"pct": 44.0, "resets": "y"}}])
            gate.begin()
            gate.end(usd=4.0, tokens=400000)
            with open(path, encoding="utf-8") as handle:
                learned = json.load(handle)
        self.assertEqual(learned["pct_per_usd"], {"session": 5.0, "week": 1.0})
        self.assertAlmostEqual(learned["usd_per_token"], 1e-5)


class TestCommand(unittest.TestCase):
    def _main(self, folder, frame, result=None):
        subject = _write(folder, "design.txt", "The subject.")
        frame = _write(folder, "frame.json", json.dumps(frame))
        out = os.path.join(folder, "result.json")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            if result is None:
                code = challenge.main(["--subject", subject, "--frame", frame, "--out", out, "--mode", "stub"])
            else:
                with mock.patch.object(challenge.Challenge, "run", return_value=result):
                    code = challenge.main(["--subject", subject, "--frame", frame, "--out", out, "--mode", "stub"])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_the_exit_code_says_whether_the_run_finished(self):
        """A run that failed exited 0 with "verdict: None". Fixed: 2026-11-26"""
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self._main(folder, FRAME)[0], 0)
            code, _, err = self._main(folder, {"title": "T"})
            self.assertEqual(code, 1)
            self.assertIn("challenge needs subject.text and brief", err)
            code, out, _ = self._main(folder, FRAME, {"mode": "run", "verdict": "incomplete", "checks": ["stopped"]})
            self.assertEqual(code, challenge.INCOMPLETE)
            self.assertIn("verdict: incomplete", out)
            self.assertNotIn(challenge.INCOMPLETE, (0, 1, 2), "2 is argparse's")
            # A frame check alone has no verdict to print: it answered, it was stopped, or its one agent failed.
            frame = {"mode": "frame", "frame": {"tilt": []}, "errors": [], "halted": None, "cost": {"agents": 1}}
            code, out, _ = self._main(folder, FRAME, frame)
            self.assertEqual((code, "frame check: done" in out, "verdict" in out), (0, True, False))
            self.assertEqual(self._main(folder, FRAME, dict(frame, frame=None, halted="usage limit: x"))[0], challenge.INCOMPLETE)
            code, _, err = self._main(folder, FRAME, dict(frame, frame=None, errors=["frame: frame: timed out after 900s"]))
            self.assertEqual(code, 1)
            self.assertIn("timed out after 900s", err)
            with open(os.path.join(folder, "result.json"), encoding="utf-8") as handle:
                self.assertIn("timed out", json.load(handle)["error"], "the result file says it too")

    def test_the_command_writes_the_result_into_a_folder_it_makes(self):
        with tempfile.TemporaryDirectory() as folder:
            subject = _write(folder, "design.txt", "The subject.")
            frame = _write(folder, "frame.json", json.dumps(FRAME))
            out = os.path.join(folder, "new", "deeper", "result.json")
            with mock.patch("builtins.print"):
                challenge.main(["--subject", subject, "--frame", frame, "--out", out, "--mode", "stub"])
            with open(out, "rb") as handle:
                written = handle.read()
            self.assertEqual(json.loads(written.decode("utf-8"))["mode"], "stub")
            self.assertNotIn(b"\r\n", written)
            with self.assertRaises(SystemExit) as refused:
                challenge.main(["--subject", subject, "--frame", _write(folder, "bad.json", "{not json"), "--out", out])
            self.assertIn("bad.json", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
