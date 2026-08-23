# m3trik

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../CLAUDE.md) · [README](README.md) · [docs](docs/) · **Related**: [server](../server/CLAUDE.md) · **Publishes**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Primary tool — `push.ps1`

**The** release path for ecosystem packages. Never `git push` these packages manually.

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge -UsePR
```

**Phases `Finalize → Prepare → Push → Merge → Finalize`, all idempotent** (full contract: push.ps1's header). An **artifact** delta (anything that ships, or a floor that must ratchet) becomes ONE commit `Release X.Y.Z` — version stepped from what is **published** (PyPI ∪ `v*` tags; a hand-edited `__version__` above it is honored as a deliberate minor/major), floors, fresh registry. `dev == main` after a release. `.github/**`, `test/**`, `docs/**` (not the wheel's readme) merge **without** a version; sidecars/CHANGELOG skip the merge. **Re-running push.ps1 completes anything merged-but-unpublished or published-but-untagged** — "no changes" never hides an unfinished release. Release notes = CHANGELOG lines since the previous tag.

`-UsePR` is the default release form — without it the dev→main merge bypasses branch protection. The PR must be *actually* gated before auto-merge is armed, and while waiting the check rollup is re-read every poll: **a settled red check fails in one poll, by name**, never waited out. Recovery: fix → push dev (auto-merge stays armed) → re-run push.ps1.

**Push THIS repo first when `scripts/` changed.** Each package's PR runs `generate_api_registry.py <pkg> --check` against **m3trik@main**, and `publish.yml` dispatches [`refresh-api-registry.yml`](.github/workflows/refresh-api-registry.yml), which regenerates the cross-package shadow report with the generator at m3trik@main. Since 2026-08-23 that bot writes **only** `docs/API_SHADOWS.md` in this repo — it never pushes into a package repo (Prepare owns the per-package registries). Enforced: the Strict+Merge pre-pass fails when `m3trik/scripts` differs from `origin/main` (bypass: `-SkipReview`).

## Release preflight — release gate

`-Strict -Merge` refuses to release a package whose **artifact** delta (dirty tree, unpushed dev, or `origin/main..dev` touching anything that ships) lacks **both** a `review` and a `tests` receipt for the **current** tree. Receipts live in `.claude/receipts.json`, keyed `pkg@treehash` where the hash is a git tree object of the **source** tree — generated sidecars (`API_*`, `docs/PARITY_*`) are excluded, so a registry refresh never voids one, while any source edit self-invalidates; max age 7 days; push.ps1 is the sole writer and re-keys receipts across its own `Release` commit. Must-reach-main / rides-along deltas and untouched packages are exempt.

`tests` is a **hard** gate: the `pull_request` suite `mayatk`/`blendertk` now run is the no-DCC subset (mocks / Qt-only) and gates no publish, so the local receipt is still the only evidence the FULL suite ran against the published tree.

**On gate failure, do the preflight unprompted:**
1. Review the release diff (`git diff origin/main...dev` + working tree): correctness → DRY → simplification → efficiency. Implement fixes; out-of-scope findings → `.claude/BACKLOG.md`.
2. Run the package suite — unless `-ShowReceipts` shows a valid `tests` receipt for the unchanged tree (record once, never re-run green).
3. `.\m3trik\push.ps1 -RecordReceipt review,tests -Packages <pkgs>`, then re-run the original push command.

Two pre-passes run **before any mutation**, so a failure costs nothing:

- **Behind `origin/dev`** (any `-Merge`; deliberately *not* waivable by `-SkipReview`, which waives only the review receipt). Releasing behind rewrites every tree and *then* fails at push. Pull first, **then** record receipts: a pull that brings in *source* changes the tree and voids anything recorded before it (a sidecar-only pull does not).
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
