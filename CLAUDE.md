# m3trik

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../CLAUDE.md) · [README](README.md) · [docs](docs/) · **Related**: [server](../server/CLAUDE.md) · **Publishes**: [pythontk](../pythontk/CLAUDE.md) · [uitk](../uitk/CLAUDE.md) · [mayatk](../mayatk/CLAUDE.md) · [blendertk](../blendertk/CLAUDE.md) · [tentacle](../tentacle/CLAUDE.md)

## Primary tool — `push.ps1`

**The** release path for ecosystem packages. Handles dependency sync, PyPI publication, version bumps. Never `git push` these packages manually. On publish it also tags `vX.Y.Z` + cuts a GitHub Release (notes = `CHANGELOG.md` lines added since the last release, via `Get-ChangelogDelta`/`git diff origin/main..dev`); additive + non-fatal.

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge
```

## Release preflight — review gate

`-Strict -Merge` refuses to release a package whose real code delta (dirty tree, unpushed dev, or non-housekeeping `origin/main..dev`) lacks a `review` receipt for the **current** tree. Receipts live in `.claude/receipts.json`, keyed `pkg@treehash` — any edit self-invalidates; max age 7 days; push.ps1 is the sole writer. Mechanical cascade commits (pin-sync/bump) and untouched packages are exempt.

**On gate failure, do the preflight unprompted:**
1. Review the release diff (`git diff origin/main...dev` + working tree): correctness → DRY → simplification → efficiency. Implement fixes; out-of-scope findings → `.claude/BACKLOG.md`.
2. Run the package suite — unless `-ShowReceipts` shows a valid `tests` receipt for the unchanged tree (record once, never re-run green).
3. `.\m3trik\push.ps1 -RecordReceipt review,tests -Packages <pkgs>`, then re-run the original push command.

`-SkipReview` = emergency bypass (and required to DryRun past the gate).

## Style

- PascalCase verbs (Verb-Noun).
- Config reads: `server/scripts/Config.psm1` is the SSoT for server hostname/user — import rather than hardcode.

## Sub-scripts

- [scripts/](scripts/CLAUDE.md) — Repo-maintenance helpers (inventory, API registry, credential rotation).

## Cross-repo standards (this repo owns them)

- [docs/TEST_BADGE_STANDARD.md](docs/TEST_BADGE_STANDARD.md) — README **Tests** badges count *individual test cases* (never suites/modules/categories), skips excluded. One writer: `ptk.StatusBadge`. Read before touching any `test/run_tests.py` or a CI badge step.
- [docs/DOCS_STANDARD.md](docs/DOCS_STANDARD.md) · [docs/CONTEXT_BUDGET.md](docs/CONTEXT_BUDGET.md) — markdown wiring + instruction-surface size caps.

See [CHANGELOG.md](CHANGELOG.md) for history.
