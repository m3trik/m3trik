# m3trik

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../CLAUDE.md) · [README](README.md) · [docs](docs/) · **Related**: [server](../server/CLAUDE.md) · **Publishes**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Primary tool — `push.ps1`

**The** release path for ecosystem packages. Handles dependency sync, PyPI publication, version bumps. Never `git push` these packages manually. On publish it also tags `vX.Y.Z` + cuts a GitHub Release (notes = `CHANGELOG.md` lines added since the last release, via `Get-ChangelogDelta`/`git diff origin/main..dev`); additive + non-fatal.

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge -UsePR
```

`-UsePR` is the default release form — without it the dev→main merge is an admin bypass of branch protection and skips the pre-merge required checks, so a red commit can land on main. Drop it only in emergencies. push.ps1 proves the PR is *actually* gated before waiting on it: **zero check runs** (a `[skip ci]` head commit, or a repo whose required check has no `pull_request` trigger) or `mergeStateStatus=BLOCKED` (missing required review) fails immediately instead of silently waiting out `-PRMergeTimeoutSeconds`.

**Push THIS repo first when `scripts/` changed.** Each package's `publish.yml` dispatches m3trik's [`refresh-api-registry.yml`](.github/workflows/refresh-api-registry.yml) on a successful upload; that workflow checks out **m3trik@main** and force-pushes regenerated registries back to every package's `dev`. So an unpushed generator change means the bot rewrites the packages' registries with the OLD generator, silently reverting the refresh you just released — and tentacle's parity-audit gate, which reads the sibling engines at `dev`, then fails on the reverted registries. Enforced: the Strict+Merge pre-pass fails when `m3trik/scripts` differs from `origin/main` (bypass: `-SkipReview`).

## Release preflight — release gate

`-Strict -Merge` refuses to release a package whose real code delta (dirty tree, unpushed dev, or non-housekeeping `origin/main..dev`) lacks **both** a `review` and a `tests` receipt for the **current** tree. Receipts live in `.claude/receipts.json`, keyed `pkg@treehash` — any edit self-invalidates; max age 7 days; push.ps1 is the sole writer. Mechanical cascade commits (pin-sync/bump) and untouched packages are exempt.

`tests` is a **hard** gate, not advisory: `mayatk` and `blendertk` ship no `pull_request`-triggered tests workflow (only `bump-dev`/`publish`/`static-analysis`), so the local receipt is the only evidence their suite ever ran against the tree being published.

**On gate failure, do the preflight unprompted:**
1. Review the release diff (`git diff origin/main...dev` + working tree): correctness → DRY → simplification → efficiency. Implement fixes; out-of-scope findings → `.claude/BACKLOG.md`.
2. Run the package suite — unless `-ShowReceipts` shows a valid `tests` receipt for the unchanged tree (record once, never re-run green).
3. `.\m3trik\push.ps1 -RecordReceipt review,tests -Packages <pkgs>`, then re-run the original push command.

Two pre-passes run **before any mutation**, so a failure costs nothing:

- **Behind `origin/dev`** (any `-Merge`; deliberately *not* waivable by `-SkipReview`, which waives only the review receipt). The bump-version/API-registry bots move `dev` after every release, so being behind is the normal resting state — and releasing behind rewrites every tree and *then* fails at push. Pull first, **then** record receipts: a pull changes the tree and voids anything recorded before it.
- **Concurrent writer.** A receipt-gate failure also lists changed files whose mtime is under 15 min (generated `API_*` sidecars excluded — regenerating them right before a release is normal). Fresh mtimes mean another session is editing that tree: **wait for it to settle**. Re-recording pins a receipt to a moving tree, and `-Merge` does `git add -A` — it would publish their in-progress work to PyPI, unrecallably.

**Checkpoint to `dev` as work lands.** Don't let `push.ps1`'s `git add .` be the first commit a change ever sees: between releases the only copy is a cloud-synced drive, and a multi-day pile-up is what turns a release into one undifferentiated sweep.

Bypasses: `-SkipTestsReceipt` waives the `tests` half alone, printing a loud banner naming what is given up; `-SkipReview` waives the whole pre-pass (emergency, and required to DryRun past it).

## Style

- PascalCase verbs (Verb-Noun).
- Config reads: `server/scripts/Config.psm1` is the SSoT for server hostname/user — import rather than hardcode.

## Sub-scripts

- [scripts/](scripts/CLAUDE.md) — Repo-maintenance helpers (inventory, API registry, credential rotation).

## Cross-repo standards (this repo owns them)

- [docs/TEST_BADGE_STANDARD.md](docs/TEST_BADGE_STANDARD.md) — README **Tests** badges count *individual test cases* (never suites/modules/categories), skips excluded. One writer: `ptk.StatusBadge`. Read before touching any `test/run_tests.py` or a CI badge step.
- [docs/CODE_STANDARD.md](docs/CODE_STANDARD.md) — the long form of the root one-line code rules (formatter, docstrings, encapsulation scope, deprecation, vendoring, performance, hygiene).
- [docs/DOCS_STANDARD.md](docs/DOCS_STANDARD.md) · [docs/CONTEXT_BUDGET.md](docs/CONTEXT_BUDGET.md) — markdown wiring + instruction-surface size caps.

See [CHANGELOG.md](CHANGELOG.md) for history.
