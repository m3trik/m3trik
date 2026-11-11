# Release runner

A release needs Maya: the `tests` receipt asserts mayatk's and tentacle's full suites ran in a fresh Maya, and push.ps1 checks unitytk's samples against a headless mayapy before it merges pythontk or mayatk. A cloud session has no Maya, so it cannot release on its own, and bypassing those gates would publish untested code to PyPI, where nothing is recalled. The release runner moves the release to the machine that has Maya and keeps every gate: any session, or the GitHub app, dispatches one workflow, and the machine does the rest.

## How it works

| Part | Where | What |
|:--|:--|:--|
| Release workflow | the private repo `m3trik/release-runner`, published from [`release_runner/release.yml`](../release_runner/release.yml) | Dispatched by hand only (`workflow_dispatch`), one at a time; runs on the runner labelled `m3trik-release`. |
| Driver | [`scripts/Invoke-RunnerRelease.ps1`](../scripts/Invoke-RunnerRelease.ps1) | Sync, tooling merge, suites and receipts, push.ps1. Its header is the contract. |
| Installer | [`scripts/Install-ReleaseRunner.ps1`](../scripts/Install-ReleaseRunner.ps1) | The repo, the dedicated workspace, the runner and its logon task. Idempotent; `-Uninstall` removes it. |

A run:

1. **Sync.** The workflow resets m3trik's clone to `origin/dev`; the driver clones or fetches every other workspace repo (the cascade, unitytk, extapps) and resets each to `origin/dev`. The private public-hygiene denylist is copied in from your workspace's `.claude/` each run. It runs only in the **dedicated workspace** the installer marked (`.release-runner`), never in a person's working trees: a release publishes what `dev` holds, never an edit in progress.
2. **Tooling.** When m3trik's `dev` and `main` differ, `main` is fast-forwarded to `dev` and pushed, the way m3trik lands (push.ps1 refuses a release while `m3trik/scripts` lags `origin/main`); a `main` holding commits `dev` lacks stops the run.
3. **Preflight.** `push.ps1 -DryRun`: the plan and every cheap gate (hygiene, layers, saved names, the line budget), so a release that cannot pass them stops before a suite runs.
4. **Receipts.** `push.ps1 -GateReport` names the packages that owe receipts; the driver restates none of push.ps1's rules. A `review` receipt is recorded only for a package `reviewed` names **at the commit `dev` holds** (`package@sha`): a `dev` that moved since the review is refused. A `tests` receipt is that package's full suite, green: `pythontk`, `uitk`, `blendertk` (fresh background Blenders), `mayatk --all` and `tentacle --in-maya` (fresh Maya instances, never one a person opened). A package whose receipts are still valid runs nothing again. Red stops the run before anything merges.
5. **Release.** `push.ps1 -Packages <set> -Strict -Merge -UsePR`, with every gate push.ps1 has (receipts, behind-dev, Unity samples, semver, PR checks, PyPI visibility).

The runner runs as you, in your desktop session (a logon task, not a service: the GUI Maya suites need a desktop), so git and gh use your own login and no token is stored. A Maya or Blender window a run opens is its own; close nothing it did not open.

**Why a private repo.** A self-hosted runner on a public repo runs whatever a fork's pull request puts in a workflow. The release repo is private, holds only the Release workflow, and dispatch needs write access to it.

## Set up (once, on the Maya machine)

```powershell
pwsh -File <workspace>\m3trik\scripts\Install-ReleaseRunner.ps1 -Python <workspace>\.venv\Scripts\python.exe
```

`-Python` is the interpreter with the workspace's test dependencies (Qt, numpy, ...); it defaults to the `python` on PATH. Other defaults: `-Repo m3trik/release-runner`, `-Root ~\m3trik-release` (the dedicated workspace), `-RunnerDir ~\actions-runner-m3trik`. Prerequisites: PowerShell 7, git, a logged-in `gh`, Maya and Blender where the test runners find them. Re-run it after editing `release_runner/` to republish the workflow.

## Release

1. **Dry run**, to see the plan and what a release of this `dev` needs:

   ```powershell
   gh workflow run release.yml --repo m3trik/release-runner -f dry_run=true
   ```

   Its log ends with each package's state and, when any owes a review, the line `A release of this dev needs: reviewed=pythontk@aade873,mayatk@170be25`.
2. **Review** `origin/main...origin/dev` of each package named (correctness, DRY, simplification, efficiency) and land the fixes on `dev` (a fix moves the commit: take the new sha). The `review` receipt is that assertion, which is why it names commits.
3. **Dispatch** with the commits reviewed:

   ```powershell
   gh workflow run release.yml --repo m3trik/release-runner -f reviewed=pythontk@aade873,mayatk@170be25
   gh workflow run release.yml --repo m3trik/release-runner -f packages=mayatk,tentacle -f reviewed=mayatk@170be25
   ```

   An agent dispatches the same way (the GitHub MCP `actions_run_trigger`, workflow `release.yml`, ref `main`), with the shas of the `origin/dev` it reviewed, and reads the run's job log for the outcome.
4. **On a red run**, the log names the phase: the preflight (a push.ps1 gate), a `dev` that moved since the review, a red suite (fix on `dev`, dispatch again), or the release itself. Receipts already recorded stay valid for an unchanged tree and push.ps1's phases are idempotent, so dispatching again resumes: it re-runs no green suite and completes anything left merged but unpublished.

## Remove

```powershell
pwsh -File <workspace>\m3trik\scripts\Install-ReleaseRunner.ps1 -Uninstall
```

The logon task and the runner registration go; the release repo and the dedicated workspace stay.
