# m3trik

<!-- packs (generated: edit the packs, then sync) -->
Shared rules (packs; Claude Code loads them, other agents read them first): [principles](.agents/packs/principles.md) · [python](.agents/packs/python.md)
<!-- /packs -->

**Role**: PowerShell DevOps — automation, deployment, release management for the ecosystem packages.

**Nav**: [← root](../AGENTS.md) · [README](README.md) · [docs](docs/) · **Related**: [server](../server/AGENTS.md) · **Publishes**: [pythontk](../pythontk/AGENTS.md) · [uitk](../uitk/AGENTS.md) · [mayatk](../mayatk/AGENTS.md) · [blendertk](../blendertk/AGENTS.md) · [tentacle](../tentacle/AGENTS.md)

## Primary tool — `push.ps1`

**The** release path for the cascade packages: never `git push` them manually. extapps and unitytk publish from their own `publish.yml` on `main`; release extapps after uitk and **before** tentacle (Prepare ratchets tentacle's `extapps` range and refuses a floor PyPI lacks). A consumer of a new upstream symbol or behaviour waits for the upstream to publish, its floor proven in the published source, never by `hasattr` on the editable install ([CODE_STANDARD](docs/CODE_STANDARD.md) §12).

```powershell
.\m3trik\push.ps1 -Packages pythontk,uitk -Strict -Merge -UsePR
```

**Phases `Finalize → Prepare → Push → Merge → Finalize`, all idempotent** (full contract: push.ps1's header). An **artifact** delta (anything that ships, or a floor that must ratchet) becomes ONE commit `Release X.Y.Z` — version stepped from what is **published** (PyPI ∪ `v*` tags; a hand-edited `__version__` above it is honored as a deliberate minor/major), floors. `dev == main` after a release. `.github/**`, `test/**`, `docs/**` (not the wheel's readme) merge **without** a version; a CHANGELOG-only delta skips the merge. **Re-running push.ps1 completes anything merged-but-unpublished or published-but-untagged.** Release notes = CHANGELOG bullets dated on or after the previous tag.

`-UsePR` is the default release form — without it the dev→main merge bypasses branch protection. Auto-merge arms only on a gated PR, and **a settled red check fails in one poll, by name**. Recovery: fix → push dev (auto-merge stays armed) → re-run push.ps1.

**No Maya (cloud)? Release via the [runner](docs/RELEASE_RUNNER.md)**: review `origin/dev`, then dispatch `release.yml` on `m3trik/release-runner` with `reviewed=<pkg@sha,...>`; never bypass a gate.

**Push THIS repo first when `scripts/` changed.** Each package's PR runs `check_api_surface.py <pkg> --check` against **m3trik@main**. Enforced: the Strict+Merge pre-pass fails when `m3trik/scripts` differs from `origin/main` (bypass: `-SkipReview`). This repo's CI (siblings' `dev`) reads red until the sibling lands, then clears on a re-run.

## Release preflight — release gate

`-Strict -Merge` refuses to release a package whose **artifact** delta (dirty tree, unpushed dev, or `origin/main..dev` touching anything that ships) lacks **both** a `review` and a `tests` receipt for the **current** tree. Receipts (`.claude/receipts.json`, written only by push.ps1) are keyed to the **source** tree, generated `docs/PARITY_*` excluded: a parity refresh never voids one, any source edit does; they last 7 days. Must-reach-main / rides-along deltas and untouched packages are exempt.

`tests` is a **hard** gate: the `pull_request` suite `mayatk`/`blendertk` run is the no-DCC subset (mocks / Qt-only) and gates no publish, so the local receipt is the only evidence the FULL suite ran against the published tree.

**On gate failure, do the preflight unprompted:**
1. Review the release diff (`git diff origin/main...dev` + working tree): correctness → DRY → simplification → efficiency; fix what it finds.
2. Run the package suite — unless `-ShowReceipts` shows a valid `tests` receipt for the unchanged tree (record once, never re-run green).
3. `.\m3trik\push.ps1 -RecordReceipt review,tests -Packages <pkgs>`, then re-run the original push command.

Two pre-passes run **before any mutation**, so a failure costs nothing:

- **Behind `origin/dev`** (any `-Merge`; deliberately *not* waivable by `-SkipReview`, which waives only the review receipt). Releasing behind rewrites every tree and *then* fails at push. Pull first, **then** record receipts: a pull that brings in *source* changes the tree and voids anything recorded before it.
- **Concurrent writer.** A receipt-gate failure also lists changed files whose mtime is under 15 min. Fresh mtimes mean another session is editing that tree: **wait for it to settle**. Re-recording pins a receipt to a moving tree, and `-Merge` does `git add -A` — it would publish their in-progress work to PyPI, unrecallably.

**Unity samples** (a real `-Merge` of pythontk or mayatk, after the pre-passes): `sync_unity_samples.py --check` in a headless mayapy; no Maya fails it.

**Checkpoint to `dev` as work lands**: never let `push.ps1`'s `git add .` be a change's first commit (between releases the only copy is a cloud-synced drive).

Bypasses: `-SkipTestsReceipt` waives the `tests` half alone (with a banner); `-SkipReview` the whole pre-pass (emergency; also to DryRun past it).

## Style

- PascalCase verbs (Verb-Noun).
- Config reads: `server/scripts/Config.psm1` is the SSoT for server hostname/user — import rather than hardcode.

## Sub-scripts

- [scripts/](scripts/AGENTS.md) — Repo-maintenance helpers (inventory, API checks, credential rotation).

## Cross-repo standards (this repo owns them)

- [docs/TEST_BADGE_STANDARD.md](docs/TEST_BADGE_STANDARD.md) — README **Tests** badges count *individual test cases* (never suites or modules), skips excluded. One writer: `ptk.StatusBadge`. Read it before touching a `test/run_tests.py` or a CI badge step.
- [docs/CODE_STANDARD.md](docs/CODE_STANDARD.md) — the long form of the root one-line rules.
- [docs/CODEBASE_MANIFEST.md](docs/CODEBASE_MANIFEST.md) — architecture of record: roles, placement, decisions.
- [docs/DOCS_STANDARD.md](docs/DOCS_STANDARD.md) · [docs/CONTEXT_BUDGET.md](docs/CONTEXT_BUDGET.md) — markdown wiring + instruction-surface size caps.
- [docs/AGENT_INSTRUCTIONS.md](docs/AGENT_INSTRUCTIONS.md) — agent instructions (stubs, [packs](agents/packs/)) and operations (CLI, MCP).
- [agents/workspace.md](agents/workspace.md) — the workspace's rules: the root `AGENTS.md` is its render (`scripts/sync_workspace.py`), so edit the source, never the root.

## The front door

- **A workspace from this clone**: `python scripts/setup_workspace.py` plans, `--apply` makes it (the other repos, the `.venv`, the root's instruction files); what exists is left as it is.
- **The `m3trik` distribution** ([pyproject.toml](pyproject.toml)): one install of the cascade and the products, dependencies only, held to `workspace.json` by `sync_workspace.py --check`. It adds no requirement of its own (a Qt binding would shadow a host's). Published by hand, on the maintainer's word, never by `push.ps1`.

See [CHANGELOG.md](CHANGELOG.md) for history.
