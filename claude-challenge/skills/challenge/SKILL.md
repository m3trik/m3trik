---
name: challenge
description: Stress-test a design, plan or proposal with independent agents - critics attack it from named seats, advocates argue rival designs, scenarios are walked through every design, findings are verified and a judge scores. Use for "challenge this design", "red team this", "pre-mortem", "compare against the alternatives", "is this the right architecture". Not for code diffs (use code review) or open research (use deep research).
---

# Challenge

Tests one document, the **subject**, and returns verified defects, ideas worth taking from
rivals, and a verdict. [`challenge.py`](challenge.py), beside this file, runs the whole
process from the command line: every agent is its own headless Claude Code session
(`claude -p`), so a run needs Python and the `claude` command, nothing else, whatever tools
this session has. The reviewers' system prompt is the [`critic`](../../agents/critic.md)
agent's text.

## 1. Frame it (no agents)

Write the frame as a JSON file in the session's scratch folder. The frame decides what the
test can find, so show it to the user and get a yes before a paid run, unless they already
asked for this run.

| Key | What |
|:---|:---|
| `title`, `brief` | The subject's name; what must be true, priorities in order, constraints. The brief's facts are what every reviewer trusts: check each against the code or the record first. |
| `criteria` | `[{name, weight, question, gate?}]`: what the judge scores. `"gate": true` makes a criterion a must-have: a design whose judges average under `gate_min` (default 3) on it fails it and cannot win, however it scores elsewhere. |
| `seats` | `[{name, lens, model?}]`: viewpoints that attack the subject. `"model": "session"` puts one seat on the senior model. |
| `rivals` | `[{name, stance}]`: alternatives, each argued by an advocate. |
| `scenarios` | Concrete situations, one sentence each, walked through every design. Needs `rivals`. |
| `settled` | Decisions reviewers may not reopen without a new, concrete failure. |
| `headings`, `severity` | The headings every case is written under, and the S1 to S3 scale. The defaults suit a system design; give your own for a project plan, a business case or a process. |
| `claims`, `web` | Outside-world facts to check. They are checked only when `web` is true. |
| `evidence` | Files every reviewer may read, walkers and judges included: what exists today, stated once. Each agent reads them on two turns, so keep them small, or put their facts in the brief. Empty means the subject alone. |
| `roots` | Folders the last stage may search (Read, Grep, Glob, nothing else; those folders opened to it and a read permitted there alone, see section 2) to settle what the text cannot show. After the audit, each open question, then each finding the text verified, minor ones left out and the graver first, up to `limits.settle` of them, is held against the files it is about by an agent of its own, on the senior model: these are a run's dearest agents. A finding the audit found answered by the proposal's own text is not searched for. Give roots for a subject about code or documents that exist. Empty: no agent searches. |
| `audit` | `true` adds a last reader who raised nothing: it overturns verified findings the text does not support, and reports fixes that conflict or overreach and what went untested. |
| `limits` | `agents` (the firm limit), `output_tokens` (what the agents write), `findings_per_seat`, `verify_batch`, `verify_agents`, `verify_votes` (readers per finding: the first on the senior model, the rest on the critic model, each from a different stand; a verdict needs a majority), `judges` (a panel, each shown the designs in a different order), `contest`, `adopt_scenarios`, `words`, `workers` (agents at once, default 6), `agent_timeout_s` (default 900), `gate_min`, `waves` (default 2: the seats attack in that many groups, in the frame's order, each later group shown the claims already made; 1 = every seat blind; more waves repeat less and take longer), `settle` (default 8: how many findings are searched for in the roots, one agent each; what is left over is listed under `dropped`). |
| `models` | `critic` (default `sonnet`), `senior` (default: the `claude` command's own default model), `effort` (passed as `--effort`; default: the user's setting). |

A stage runs only when its input is there: seats alone is a red team; rivals and scenarios
add the comparison; claims with `web` add a fact check; `roots` add the search that settles
findings in the files.

The run reasons from what it is shown and reaches nothing else, and a search settles only what
a seat raised. So do the checks only you can do first (count what the proposal touches, read
what it would change, fit it to a real case) and put what they show in the brief; give `roots`
when the subject is about files that exist.

Order the seats: the first half work blind, the rest are shown what those raised and report only what is new, so put the broad lenses first and the senior seat last. Where the subject has parts (moves, phases, sections), name a part in each later seat's lens, so no part goes untested.

Give one seat the brief's FACTS to hold every claim of the subject against (a seat that checks what the subject says exists or does): an author's own fixes overclaim. Seats that suit an architecture: security and confidentiality; the people who must adopt
it; the owner of the upstream system of record; an auditor rebuilding events a year later;
simplicity and delivery; and one seat on the senior model for contradictions between
sections and a pre-mortem.

## 2. Plan, self-test, run

```
python <this skill's folder>/challenge.py --subject <file> --frame <frame.json> --out <scratch>/result.json --mode plan
```

- `plan` lists the agents, their models and a rough token estimate. It spends nothing.
- `frame` runs the frame check alone (one agent, about a minute): take its missing scenarios, rivals and criteria, and its tilts, into the frame before a paid run.
- `stub` runs every stage on canned answers. It spends nothing.
- `run` does the work, inside `limits`, and needs the user's opt-in. It takes minutes:
  start it in the background and wait for it to finish. Progress goes to standard error,
  one line per agent; the result is the `--out` file.

`--previous <file>` hands reviewers the last revision so they concentrate on what changed, and puts it in the comparison as one more design, blind like the rest: the result's `revision` says whether the new one scored higher, and a regression reads as `rival-wins:Previous revision`.
`--claude <path>` names the `claude` command when it is not on PATH. Paths in the frame's `evidence` and `roots` are read from the folder the command runs in, and each agent is handed them whole.

The command exits 0 when the run (or the plan) finished, 1 when it failed (the reason on standard error and under `error` in the result; a frame check alone fails when its one agent did), and 3 when a usage limit stopped it (`incomplete`: run it again once the window resets).

Before each stage the run reads the account's usage windows ([`usage_gate.py`](usage_gate.py), the plugin's hook for every session as well) and starts the stage only when its estimate fits what is left less a reserve: 5%, shrinking over the last day of the weekly window (the last hour of the 5-hour one) to nothing at its reset, since what is left expires there (a reset the gate cannot read keeps the whole reserve; one in a named zone is read in that zone where the machine has a zone database, else as local time); `python usage_gate.py` prints each window, the model it belongs to, its hours to its reset and the percent spendable now; otherwise it stops with `incomplete` and says when the window resets, instead of starting agents the limit would fail. A weekly window `/usage` lists for one model alone holds only work on that model: a stage is held to the all-models windows and to those of the models it runs on (the hook: a subagent's `model`, a command's `--model`), and work on an unnamed model (the CLI's default) to the all-models windows alone. The hook runs through [uv](https://docs.astral.sh/uv/) (`uv run --no-project python`), as the marketplace's other plugin does, so it finds a Python on every OS; without uv on PATH the gate does nothing. It learns what a dollar costs each window from each run (calibration in the user's cache folder); `--ignore-usage` starts every stage regardless, once the run is going. Inside a Claude Code session the plugin's hook gates the command that starts the run too, so while the windows cannot take it that command is blocked before `--ignore-usage` is read, unless `CLAUDE_USAGE_GATE=off` is set in the environment Claude Code started with (the hook reads its own; setting it on the command line does not reach it).

Every answer is kept beside the result (`<out>.answers.json`), keyed by what was asked. A usage limit stops new agents and the result reads `incomplete`; run the same command again once the limit resets and every answer already given is reused (`cost.reused`), so only the missing agents spend. A changed frame or subject asks again only what changed, and so does an edited evidence file (its bytes are part of what its readers were asked). A search of the roots is never kept: no key can say what it will read, so a re-run searches again. `--fresh` asks every agent anew.

Each agent runs in an empty folder outside any project (no project settings, hooks or
instructions load), with no MCP servers, no saved session, and its answer checked against
the stage's JSON schema. Reviewers get no tools at all: the Read tool when the frame lists
`evidence`, with the evidence's folders opened to it; the web tools for a claim; Read, Grep
and Glob, with the frame's `roots` opened to them, for the agents that settle findings, which
can change nothing. A tool that reads files is permitted by one rule per folder opened to it
(`--allowedTools "Read(//<folder>/**)"`), never by its bare name, which would permit it
anywhere; that a headless session refuses a read outside those folders is Claude Code's to
enforce, and no run here has probed it. An agent that fails or times out is listed under
`errors` and the run goes on without it. A run that is stopped starts no agent still queued,
and every answer already given is kept.

## 3. Read the result

| Field | Meaning |
|:---|:---|
| `verdict` | `holds`, `holds-with-changes`, `rival-wins:<name>`, `fails-gate:<criteria>` (the subject fails a must-have and no rival passes them), `incomplete` (a usage limit stopped it: run it again) or `frame-rejected`. |
| `revision` | With `--previous`: both revisions' scores and whether the new one is better. |
| `totals` | Each design's weighted score, the gate criteria it `fails`, and its `walk` tally (holds, strains, breaks, unstated). |
| `checks` | What to see before trusting the result: the top-ranked design breaks more scenarios than the subject and holds no more; the top two are a tie; no design holds a third of the scenarios (the tally then says little of any of them); the walk could not say what happens in most scenarios for a design (its case is too short to state it: raise `limits.words` or say it in the design); the audit names things no finding tested; the frame check named rivals this run did not test, or tilts in the frame. Read these first. |
| `defects` | Each with `severity` (S1 to S3), `verified` (VERIFIED, SUSPECTED, UNVERIFIED), its `failure_scenario`, a `fix`, the seat; repeats the audit found are joined to the first (`also_from`); `settled` where the files were searched for it (CONFIRMED, CONTRADICTED or UNSETTLED, with the line that decides it: the run opens the file the agent cites and looks for the cited words within three lines of the cited number, and a verdict whose words are not there counts as UNSETTLED; an open question the files confirm is VERIFIED, one they contradict is refuted, a verified finding they contradict becomes a question); `narrowed_from` where the audit corrected part of its claim and its verdict stood. |
| `walk` | Per scenario and design: the outcome, how the design gets through it and its weakest point. The outcome is derived from what the walker found (stated, handled, silently wrong, manual work): `unstated` where the design's text does not say what happens, which is not a break. |
| `refuted_findings` | Each refuted finding with the verifier's reason: check a refutation before trusting it. |
| `held` | What was attacked and survived. Feed it into the next run's `settled`. |
| `grafts`, `advocate_takes` | Ideas from rivals worth taking. |
| `missing_from_all` | What the brief requires and no design addresses. |
| `frame` | What the frame left out. Fix the frame before the next run. |
| `seat_stats` | Per seat: raised, verified, refuted. Retire a seat that keeps being refuted. |
| `dropped`, `errors`, `cost` | What the limits cut and which agents failed; agents, tokens and dollars used, as the agents reported them. |

## 4. Weigh it against the goals, and tighten the method

A run answers the frame, not the goal: weigh the outcome against the brief's priorities, in their order, before calling it done.

- Did the revision serve the top priorities, or did it drift toward what the seats could attack (completeness, robustness) at the cost of a higher one? For a design people use, count what they must learn (concepts, states, modes, choices) before and after: a revision that adds them must pay for them in a top priority, or the fix belongs in a simpler design.
- Say plainly where the result fell short of the goal, and what the next run must test that this one did not.
- Revise by amendment: keep what held, word for word, and change only what a verified finding touches. A rewrite drops settled detail, and the next run spends its findings on the omissions.
- Stop when two revisions tie (`revision.tie`): take what held from both, and build. Put facts checked against the code in the brief: the facts seat verifies only what it is given.
- Keep a method log beside the usage calibration (`method.md` in the user's cache folder, `usage_gate.home()`): per run, the subject's kind, the seats that verified versus only duplicated or were refuted, the frame-check tilts that proved right, and the goal drift found. Read it before framing the next run and start from its lessons: retire a seat that only duplicates, add the seat or scenario a drift showed missing.

## Rules

- Brief the agents with the subject, never with the author's reasoning.
- Reviewers hold no tools but those their stage needs; the runner enforces it.
- A reviewer that can reach the web never sees the subject: it gets one claim.
- Act on VERIFIED findings. Re-verify an S1 yourself before changing the subject, unless it is `settled` CONFIRMED: the run has opened that line. A SUSPECTED finding is a question for the user.
- Apply fixes to the subject only with the user's yes, and follow the project's own rules for findings it defers.
- After applying fixes, have one fresh reader check the revision against the brief's facts: a challenge's own fixes can overclaim.
- Judges score from cases of one form and length under letters, so the subject is not known to them.
- Check the result against its own reasoning before acting on it: does the ranking follow the walk, are the defects distinct, do the refutations (`refuted_findings`) hold? A ranking within one point on one criterion is a tie.
- Compare the `estimate` with the `cost` the run reports, and correct `OVERHEAD`, `WRITES`, `TURNS` and `SEARCH` in `challenge.py` when they disagree: each line of the progress log says what its agent wrote and read.
