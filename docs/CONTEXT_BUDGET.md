# Context Budget — keeping Claude agent queries fast

The instructions, API registry, and auto-memory exist to make agent queries
*better*. They only do that while they stay small and in sync. Past a few silent
size cliffs they make queries **worse** — context the agent pays for on every
query, or recall that is dropped without warning. This is the contract that keeps
that from happening, and [`check_context_budget.py`](../scripts/check_context_budget.py)
is what enforces it.

> **Root cause this prevents (2026-06-21 audit):** `MEMORY.md` silently grew past
> its 24,400-byte load cap, so the agent's memory index was **truncated tail-first
> every session** — the most recently learned facts vanished first. That is the
> "queries falling off lately" failure. Nothing was watching the budget. Now
> something is.

## Tier the context — never load a lower tier whole

| Tier | What | Rule |
|:---|:---|:---|
| **Always-on** | root + the relevant sub `CLAUDE.md`, `MEMORY.md` (index) | Bounded & lean. Paid on *every* query. |
| **On-demand** | memory topic files, `API_INDEX.md` | Pulled only when relevant; keep each one fact / one tool. |
| **Raw** | `API_REGISTRY.md` / `.json` | **`grep`/slice only — never Read whole.** |

**Any instruction that says "Read `<file>`" where the file is >~40 KB is a bug.**
`mayatk/API_REGISTRY.md` is ~350 KB (~90 K tokens, ~half a context window).

## Hard budgets (enforced — FAIL the build)

- `MEMORY.md` ≤ **24,400 bytes** (the harness load cap). Over → the index is silently truncated.
- Each `MEMORY.md` index entry ≤ **280 chars** (slug + link + one ≤200-char relevance hook).
- Every `memory/*.md` topic file has **exactly one** index link — no orphans (un-recallable), no broken links.
- Each `CLAUDE.md` ≤ **10,240 bytes**.
- Registries fresh vs source (`generate_api_registry.py --check`).
- Root dispatch table covers **every** `ECOSYSTEM_PACKAGES` member.
- Every relative markdown link in a `CLAUDE.md` resolves (no broken nav).

## Soft budgets (WARN — advisory, flag for cleanup)

- `CLAUDE.md` > 6,144 bytes — trim; move runbook/recipe content into `<subdir>/docs/`.
- Topic file > 20,480 bytes — compress to durable lessons or split (one fact per file).

## The rules behind the numbers

1. **The memory index is a relevance router, not a knowledge store.** Each bullet
   is `[slug](file) — one hook answering "when would I need this?"`. All
   PRIMARY/SECONDARY/Phase-N/`→`/`=` narrative chains live in the *topic file*,
   never the index line. Truncation is tail-first → keep broadly-applicable
   `feedback`/`user` entries short and near the **top**.
2. **A `reference` memory reads as a timeless rule, not a dated event.** When work
   ships, extract the one gotcha that survives the fix and let `CHANGELOG`/`git`
   own the history. Retire DONE `project_*` files to `reference_*`. Name-prefix ==
   frontmatter `type`. One fact per file.
3. **Don't ship a control the agent can't afford to use.** "Check the registry
   before writing a helper" is only real because a compact, grep-able
   `API_INDEX.md` backs it. Grep `API_REGISTRY.md` for a symbol; never Read it whole.
4. **One SSoT for the package set.** `generate_api_registry.py`'s
   `ECOSYSTEM_PACKAGES` tuple is canonical. The root dispatch table, the ecosystem
   chain, `m3trik/scripts/CLAUDE.md`, and the CI clone/commit loops are all derived
   from it (and CI-asserted equal) — never hand-maintained lists that drift.
5. **Protect the prompt cache.** It keys on a stable prefix. Keep `MEMORY.md`
   edits small (the index sits in that prefix) and confine churny registry
   refreshes to a fixed off-peak window.

## How to run it

```powershell
# Full check (repo + local auto-memory) — run before a release / when memory feels off
python m3trik/scripts/check_context_budget.py

# Repo-side only (what CI runs; no local memory dir)
python m3trik/scripts/check_context_budget.py --no-memory

# Refresh registries + indexes, then re-check
python m3trik/scripts/generate_api_registry.py
python m3trik/scripts/check_context_budget.py
```

## Maintenance cadence

- **Repo-side (automated):** the guard runs in
  [`refresh-api-registry.yml`](../.github/workflows/refresh-api-registry.yml) on
  every registry refresh — monthly cron + after each PyPI publish. A hard budget
  breach fails that job.
- **Memory-side (local):** the auto-memory dir is local, so it can't be checked in
  the cloud. The **`ClaudeContextBudget`** Windows Scheduled Task runs the guard
  weekly (Mon ~09:07) via
  [`Invoke-ContextBudgetCheck.ps1`](../scripts/Invoke-ContextBudgetCheck.ps1) —
  logging to `%LOCALAPPDATA%\claude-context-budget.log` and raising a toast on a
  hard FAIL or when `MEMORY.md` is within 2 KB of cap. It runs with
  `--no-registry` (see the Nextcloud caveat below). The agent also self-enforces
  the `MEMORY.md` cap whenever it writes a memory (the cap is in the header).
- **Runtime API drift (local):** the same weekly task then runs
  [`Check-RuntimeSurface.ps1`](../scripts/Check-RuntimeSurface.ps1) — the DCC half
  of the drift gate cloud CI can't run (no Maya/Qt/Blender). It dumps each
  package's live `HelpMixin` surface from a fresh session-safe DCC instance and
  diffs it against the committed registry (`verify_runtime_surface.py`), logging to
  `%LOCALAPPDATA%\claude-runtime-surface.log` and toasting on a `missing`-member
  FAIL. This covers ALL packages incl. pythontk; cloud CI stays import-free
  (`--no-runtime`), since runtime drift needs importable/DCC runtimes it lacks.
- **When a WARN shows up,** don't wait for it to become a FAIL — that is the
  early-warning the audit found was missing.

> **Nextcloud caveat:** this repo lives on a cloud-synced drive (O:). Reading a
> just-written `.json` sidecar can transiently return an incoherent byte view, so
> `generate_api_registry.py --check` may **false-flag one registry as stale**
> locally (different file each run; generation itself is deterministic). Registry
> freshness is therefore gated in CI (clean checkout), and the local weekly task
> skips it. To confirm a *real* local drift, re-run `--check` after the drive settles.
