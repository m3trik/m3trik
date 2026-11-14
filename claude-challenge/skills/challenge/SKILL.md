---
name: challenge
description: Stress-test a design, plan or proposal with independent agents - critics attack it from named seats, advocates argue rival designs, scenarios are walked through every design, findings are verified and a judge scores. Use for "challenge this design", "red team this", "pre-mortem", "compare against the alternatives", "is this the right architecture". Not for code diffs (use code review) or open research (use deep research).
---

# Challenge

Tests one document, the **subject**, and returns verified defects, ideas worth taking from
rivals, and a verdict. It runs as a workflow ([`challenge.js`](challenge.js), beside this
file); [`prepare.py`](prepare.py) builds the run file. An agent held to the Read tool,
[`critic`](../../agents/critic.md), is there for the reviewers on the critic model.

## 1. Frame it (no agents)

Write the frame as a JSON file in the session's scratch folder. The frame decides what the
test can find, so show it to the user and get a yes before a paid run, unless they already
asked for this run.

| Key | What |
|:---|:---|
| `title`, `brief` | The subject's name; what must be true, priorities in order, constraints. |
| `criteria` | `[{name, weight, question}]`: what the judge scores. |
| `seats` | `[{name, lens, model?}]`: viewpoints that attack the subject. `"model": "session"` puts one seat on this session's model. |
| `rivals` | `[{name, stance}]`: alternatives, each argued by an advocate. |
| `scenarios` | Concrete situations, one sentence each, walked through every design. Needs `rivals`. |
| `settled` | Decisions reviewers may not reopen without a new, concrete failure. |
| `headings`, `severity` | The headings every case is written under, and the S1 to S3 scale. The defaults suit a system design; give your own for a project plan, a business case or a process. |
| `claims`, `web` | Outside-world facts to check. They are checked only when `web` is true. |
| `evidence` | Files the critics may read. Empty means the subject alone. |
| `audit` | `true` adds a last reader who raised nothing: it overturns verified findings the text does not support, and reports fixes that conflict or overreach and what went untested. |
| `limits` | `agents`, `output_tokens`, `findings_per_seat`, `verify_batch`, `verify_agents`, `verify_votes` (readers per finding: the first on the senior model, the rest on the critic model, each from a different stand; a verdict needs a majority), `judges` (a panel, each shown the designs in a different order), `contest`, `adopt_scenarios`, `words`. `agents` is the firm limit: `output_tokens` also counts what this session writes while the run is in flight. |
| `models` | `critic` (default `sonnet`), `senior` (default: this session's model). |
| `critic_agent` | `"challenge:critic"` where this plugin is installed: the reviewers on the critic model then run as that agent, which holds the Read tool alone. Reviewers on the session's model (a `session` seat, the first vote of each verification, the judges, the recheck, the audit) keep the session's tools. |

A stage runs only when its input is there: seats alone is a red team; rivals and scenarios
add the comparison; claims with `web` add a fact check.

Seats that suit an architecture: security and confidentiality; the people who must adopt
it; the owner of the upstream system of record; an auditor rebuilding events a year later;
simplicity and delivery; and one seat on the session's model for contradictions between
sections and a pre-mortem.

## 2. Plan, self-test, run

```
python <this skill's folder>/prepare.py --subject <file> --frame <frame.json> --out <scratch>/run.js --mode plan
```

Launch it with the Workflow tool (`scriptPath`: the run file).

- `plan` lists the agents, their models and a rough token estimate. It spends nothing.
- `stub` runs every stage on canned answers. It spends nothing: run it after any edit to `challenge.js`.
- `run` does the work, inside `limits`. Launching a workflow needs the user's opt-in.

`--previous <file>` hands reviewers the last revision so they concentrate on what changed.

## 3. Read the result

| Field | Meaning |
|:---|:---|
| `verdict` | `holds`, `holds-with-changes`, `rival-wins:<name>` or `frame-rejected`. |
| `defects` | Each with `severity` (S1 to S3), `verified` (VERIFIED, SUSPECTED, UNVERIFIED), its `failure_scenario`, a `fix`, the seat. |
| `held` | What was attacked and survived. Feed it into the next run's `settled`. |
| `grafts`, `advocate_takes` | Ideas from rivals worth taking. |
| `missing_from_all` | What the brief requires and no design addresses. |
| `frame` | What the frame left out. Fix the frame before the next run. |
| `seat_stats` | Per seat: raised, verified, refuted. Retire a seat that keeps being refuted. |
| `dropped`, `cost` | What the limits cut; agents and output tokens used. |

## Rules

- Brief the agents with the subject, never with the author's reasoning.
- Every reviewer is told to use no tools. That is an instruction, not a lock, except for the reviewers `critic_agent` covers.
- A reviewer that can reach the web never sees the subject: it gets one claim.
- Act on VERIFIED findings. Re-verify an S1 yourself before changing the subject. A SUSPECTED finding is a question for the user.
- Apply fixes to the subject only with the user's yes, and follow the project's own rules for findings it defers.
- Judges score from cases of one form and length under letters, so the subject is not known to them.
- Compare the `estimate` with the tokens the run reports, and correct `OVERHEAD` in `challenge.js` when they disagree.
