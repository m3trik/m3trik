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
2. **Tooling.** When m3trik's `dev` and `main` differ, `dev` reaches `main` through a PR the driver opens and waits on (push.ps1 refuses a release while `m3trik/scripts` lags `origin/main`).
3. **Suites and receipts.** Each requested package whose `origin/main..origin/dev` touches anything that ships runs its full suite: `pythontk`, `uitk` and `blendertk` (fresh background Blenders) their runners, `mayatk --all` and `tentacle --in-maya` (fresh Maya instances, never one a person opened). Green records the `tests` receipt; `reviewed=true` records the `review` receipt beside it. Red stops the run before anything merges.
4. **Release.** `push.ps1 -Packages <set> -Strict -Merge -UsePR`, with every gate push.ps1 has (receipts, behind-dev, Unity samples, semver, line budget, PR checks, PyPI visibility).

The runner runs as you, in your desktop session (a logon task, not a service: the GUI Maya suites need a desktop), so git and gh use your own login and no token is stored. A Maya or Blender window a run opens is its own; close nothing it did not open.

**Why a private repo.** A self-hosted runner on a public repo runs whatever a fork's pull request puts in a workflow. The release repo is private, holds only the Release workflow, and dispatch needs write access to it.

## Set up (once, on the Maya machine)

```powershell
pwsh -File <workspace>\m3trik\scripts\Install-ReleaseRunner.ps1 -Python <workspace>\.venv\Scripts\python.exe
```

`-Python` is the interpreter with the workspace's test dependencies (Qt, numpy, ...); it defaults to the `python` on PATH. Other defaults: `-Repo m3trik/release-runner`, `-Root ~\m3trik-release` (the dedicated workspace), `-RunnerDir ~\actions-runner-m3trik`. Prerequisites: PowerShell 7, git, a logged-in `gh`, Maya and Blender where the test runners find them. Re-run it after editing `release_runner/` to republish the workflow.

## Release

1. **Review** `origin/main...origin/dev` of each package (correctness, DRY, simplification, efficiency) and land the fixes on `dev`. The `review` receipt is that assertion: dispatch with `reviewed=true` only after it.
2. **Dispatch:**

   ```powershell
   gh workflow run release.yml --repo m3trik/release-runner -f reviewed=true
   gh workflow run release.yml --repo m3trik/release-runner -f packages=mayatk,tentacle -f reviewed=true
   gh workflow run release.yml --repo m3trik/release-runner -f dry_run=true   # the plan and the runner, nothing released
   ```

   An agent dispatches it the same way (the GitHub MCP `actions_run_trigger`, workflow `release.yml`, ref `main`) and reads the run's job log for the outcome.
3. **On a red run**, the log names the phase: a red suite (fix on `dev`, dispatch again), a red tooling PR check, or a push.ps1 gate. push.ps1's phases are idempotent, so dispatching again completes anything a run left merged but unpublished.

## Remove

```powershell
pwsh -File <workspace>\m3trik\scripts\Install-ReleaseRunner.ps1 -Uninstall
```

The logon task and the runner registration go; the release repo and the dedicated workspace stay.
