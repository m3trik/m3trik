---
name: backlog
description: Work `.claude/BACKLOG.md` end to end - pick the next entry by the file's own triage order, PROVE it still reproduces before touching anything, critique the entry's prescribed fix against the real code, then halt for approval before implementing. Use whenever the ask is "what's next on the backlog", "fix the next backlog item", "is this entry still relevant", or after any session that logged new entries.
---

# Backlog resolution

Runs the backlog as a gated pipeline. Two phases are **gates, not suggestions**: an
entry that cannot be reproduced is never implemented, and a prescribed fix is never
written before it has been checked against the code.

## Modes (argument)

- *(none)* / `next` - full pipeline on the next entry per SELECT. Halts after
  CRITIQUE for approval; batches only per the batching rule below.
- `verify [N]` - **triage-only sweep**: run Phase 2 on the top N pickable entries
  (default 5), stamp each with `- Verified:`, implement NOTHING. This is the cheap
  answer to "is the backlog still true" - run it periodically; the SessionStart hook
  reports S1+S2 verification coverage so drift is visible. A stamp also resets the
  entry's 14-day TTL.
- `decide` - **the maintainer's queue**: batch the `decision` entries to the user
  3-4 at a time as option questions, each option set drawn from the entry's own
  "Next step" plus a verified recommendation. Record the answer as a dated line in
  the entry (then work it or delete it per the answer). An entry that has been
  presented twice without a decision is archived - an undecidable question is not
  a work item. Verify an entry's premise BEFORE presenting it: asking the user to
  decide a refuted question wastes the one resource this mode exists to spend well.
- `status` - report only: the priority slices, verification coverage, TTL and
  decision counts, leverage chains (`Unblocks:` lines), and a recommendation.
  No probes, no edits.
- `<text>` - work the specific entry whose heading matches the text; same gates.
  If the match is ambiguous, list the candidates and stop.

## Why the gates exist

Measured over one 2026-08-20 session, of six entries actually worked:

| Entry | Verdict on the entry itself |
|:---|:---|
| `assembly_reconstructor` MFnMesh writes (S1) | **premise refuted** - no defect existed |
| object-space bounding box (S1) | symptom real, **prescribed fix wrong** |
| scene-exporter sidecar ordering (S2) | real but **narrower** than written |
| texture-token classification (S2) | **root cause misdiagnosed** |
| `list_transforms` instances (S1) | accurate |
| www favicon (S3) | accurate, first fix incomplete |

Four of six carried a materially wrong premise, scope, or prescribed fix. A full
25-entry S1 sweep the same week confirmed the rate at scale: 3 premises refuted
outright, and **0 of the 22 surviving prescribed fixes came through critique
unchanged**. Entries are written at defer time, when the author is mid-way through
other work and has not re-measured; the code then moves under them in days. Treat
every entry as a **lead**, never as a specification - and treat that rot rate as
the reason the fix-now bar and the TTL exist (both in the file header).

## Phase 1 - SELECT

**Maintenance first, every run**: move any entry past the 14-day TTL (its latest
MEASUREMENT - heading date, or a `- Verified:` stamp with a measured verdict - is
over 14 days old; a dated note keeps nothing alive; the SessionStart hook counts
them) and report how many. Where it goes depends on
its blocker, per `FUTURE.md`'s "How an entry moves": a `scope` or `decision`
entry is a structural observation, so it moves to `FUTURE.md` with its
`- Next step:` line stripped and Where/Symptom intact; a `ready` or `blocked`
entry is appended verbatim to `BACKLOG.archive.md`. A stamp resets the clock; it
never exempts permanently. The archive is the file's only history (it is not
under version control), so expiry is a move, never a hard delete.

Then `python m3trik/scripts/ledger_drift.py check`: an entry whose `- Anchors:` name
code that changed (or vanished) since its stamp is re-measured before anything is
built on it -- that is the drift a date cannot show.

Then select. Deterministic - the heading line is the whole index, so slice it
rather than reading the file:

    grep '^## 20' .claude/BACKLOG.md | grep '| S1 | ready |'
    grep '^## 20' .claude/BACKLOG.md | grep '| S1 |'
    grep '^## 20' .claude/BACKLOG.md | grep '| S2 | ready |'

Order: `S1 + ready`, then `S1`, then `S2 + ready`. Tiebreak on **leverage** - an entry
carrying `Unblocks:` outranks one that does not, because clearing it converts another
entry from blocked to actionable. Skip `decision` entries when no maintainer is
present (batch them with `decide` when one is), and `blocked` entries unless their
`- Blocked-on:` dependency is satisfiable now. A live-DCC or GUI pass is NOT a
blocker - launch a fresh instance.

State which entry was picked and why in one line before moving on.

### Batching - scale to difficulty

- **Batch** entries that are `S3 + ready`, conformance-audit items, or otherwise
  mechanical and confined to one file. Verify each one's premise individually even
  when implementing them together.
- **One entry per run** when it is `S1`/`S2`, touches a public API, needs a live DCC
  pass, spans both DCC twins, or carries `Unblocks:`/`Coupled:`. Big diffs hide
  regressions and are miserable to review.

## Phase 2 - VERIFY (gate)

Reproduce before touching anything. Do not trust the entry's `Symptom` line, its line
numbers (they drift), or its claim that a sibling fix "already landed".

- Write a probe under the package's `tests/temp_tests/` and run it in a **fresh** DCC.
- Verify the entry's **premise**, not just its symptom. An entry can describe a real
  symptom with a wrong cause - which then makes its prescribed fix wrong too.
- When an entry says a defect is discarded/dropped/ignored, force the condition
  explicitly (a DG re-evaluation, a reload, a recompute). A transient cache can make
  broken behaviour read as correct, and correct behaviour read as broken.

Emit exactly one verdict, with the measurement that supports it:

- `REPRODUCES` - proceed to Phase 3.
- `PARTIAL` - some of it landed already; narrow the scope, record what remains.
- `STALE` - line numbers or names moved but the defect stands; correct the entry.
- `REFUTED` - **halt.** Do not implement. Append a dated refutation to the entry with
  the measurement, name the cases you did NOT probe, and recommend closing it. Deleting
  an S1 on a single probe is the maintainer's call, not yours.

Stamp the outcome on the entry: `- Verified: YYYY-MM-DD | reproduces|partial|stale|refuted`.
Only a measurement earns a stamp (it resets the TTL): when all you could do was read
the code, write a dated note instead -- `- YYYY-MM-DD: code read, not measured: ...`.
Beside a fresh stamp record what it measured: `python m3trik/scripts/ledger_drift.py
stamp "<heading text>"` prints the `- Anchors:` line (a hash per named definition).

## Phase 3 - CRITIQUE (gate), then HALT

Read the actual code the entry names, and interrogate its prescribed `Next step`:

- Is the **root cause** right? (A missing enum value is often a duplicated table that
  drifted - fixing the symptom leaves the duplication to drift again.)
- Is the **scope** right? Which callers really reach the broken path? Grep them; a
  branch reached only through a variable will not show up in a literal search.
- Would the prescribed fix **break a neighbouring path that is already correct?**
  Verify the neighbour is correct rather than assuming it.
- Does the prescribed remedy actually produce the stated goal? Check the semantics
  against the real consumer, not against the entry's wording.
- Is there an existing primitive for this? Search the API (`api.search`, MCP
  `api_search`, `python -m pythontk ops run api.search "query=<words>"`) before adding a
  helper. If the right primitive is private, adding a small public one is part of the
  work, not a reason to duplicate it. Look outside too: the host's built-ins, an open
  standard, a maintained library (CODE_STANDARD section 15, "Adopt before building").

Then **stop and report**: the verified verdict, the confirmed/amended/replaced plan,
any decision that is the maintainer's, and the estimated blast radius. Wait for
approval before writing code.

## Phase 4 - IMPLEMENT (only after approval)

1. **Failing test first**, per the repo TDD rule. It goes in the package's real suite,
   not `temp_tests/`.
2. Fix at the source. Never mask a symptom.
3. **Prove the test is not vacuous**: revert the fix, confirm the new test fails,
   restore. A test written after a fix proves nothing until this is done. Preserve
   line endings when patching (`mixed CRLF/LF` repo) and restore from a byte copy.
4. **Mirror to the twin** when the code has one (`mayatk` <-> `blendertk`). Check the
   twin's guards match rather than assuming; then mirror the tests too.
5. **Verify on the production scene as well** - maintainer rule: no fix ships on its
   standalone test alone. Read-only, path only via `PROD_VERIFY_SCENE`, never saved,
   fingerprinted before and after; Blender-side fixes use that scene pulled through the
   bridge. Write the expectation as a pass/fail check, and fix at the source rather
   than patching the symptom the check shows.
6. Run the tests the fix reaches -- `python m3trik/scripts/affected_tests.py <files> --run`
   (headless; the twin's files too) -- and report the real numbers. The full suite is the
   release preflight's job (CODE_STANDARD section 9); no scoped run stamps a badge.

## Phase 5 - RECORD

- `CHANGELOG.md` entry in the package's voice: what was wrong, the measurement, why
  this fix and not the obvious alternative, and what the tests pin.
- **Delete** the entry from `BACKLOG.md`. Fixed entries are not archived - git history
  and the CHANGELOG are the record.
- **Annotate coupled entries.** If the work cleared another entry's blocker or moved
  the ground under it, say so in that entry with a dated line. This is how leverage
  survives across sessions.
- Log new findings only past the file header's bar: mechanical or S3 findings are
  FIXED in the turn that found them (or dropped), never logged; a logged entry needs
  a real blocker (`decision`/`scope`/`blocked`) or to be genuinely another turn's
  work (`ready`). A new `ready` S1/S2 entry carries `- Repro:` (an expectedFailure
  test preferred -- the file header). Update an existing entry rather than duplicating.
- Re-validate the index - every heading must parse:

      grep '^## 20' .claude/BACKLOG.md | grep -vcE '^## 20[0-9]{2}-[0-9]{2}-[0-9]{2} \| [^|]+ \| S[123] \| (ready|decision|scope|blocked) \| .+'

## Hard rules

- **Session safety.** Never attach to a Maya/Blender/Painter a person opened. Launch a
  fresh instance first; reuse only one this tooling launched and still owns while no other run uses it, with changed
  code reloaded. Waiting minutes beats losing hours of unsaved work.
- **Never guess a `decision` entry.** Public-API contracts, product behaviour and
  business judgement are the maintainer's. Present the options with a recommendation.
- **Report failures honestly.** If a suite fails, say so with the output. A test that
  passed before your change and fails after is yours until proven otherwise - diff
  against the earlier run rather than assuming a flake.
