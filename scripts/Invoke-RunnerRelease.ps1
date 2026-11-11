<#
Invoke-RunnerRelease.ps1 -- release the cascade from the release runner, gates intact.

What the private release repo's Release workflow runs (docs/RELEASE_RUNNER.md) on the
self-hosted runner Install-ReleaseRunner.ps1 sets up on the machine that has Maya and
Blender. It never touches a person's working trees: it runs in a DEDICATED workspace
(-Root, marked by the installer's .release-runner file) that it resets to origin/dev
on every run, so a release publishes exactly what dev holds and nothing a person is
still editing.

    Sync      clone or fetch every workspace repo; each checks out dev at origin/dev,
              reset and cleaned (untracked files go, ignored ones stay).
    Tooling   m3trik's dev reaches main first, through a PR it waits on, when they
              differ (push.ps1 refuses a release while m3trik/scripts lags origin/main).
    Suites    each requested package whose origin/main..origin/dev touches anything
              that ships runs its FULL suite (fresh Maya / Blender instances, launched
              by each runner); green records its tests receipt, and its review receipt
              when the dispatcher attests the review (-Reviewed). Red stops the run:
              nothing is merged or published.
    Release   push.ps1 -Packages <set> -Strict -Merge -UsePR, every gate its own.

-DryRun skips the tooling merge and the suites and runs push.ps1 -DryRun -SkipReview:
a check of the plan and the runner, never a release. Exit 0 only when every phase passed.

Dot-sourcing this file defines its functions and runs nothing (the tests use that).
#>

param(
    [string]$Root,
    [string]$Packages = "pythontk,uitk,mayatk,blendertk,tentacle",
    [switch]$Reviewed,
    [switch]$DryRun,
    # Where the workspace repos are cloned from: https://github.com/<owner>/<repo>. A test
    # points it at local bare repos.
    [string]$RemoteBase = "https://github.com/m3trik",
    [int]$ToolingMergeTimeoutMinutes = 60
)

$ErrorActionPreference = "Stop"

#: The file Install-ReleaseRunner.ps1 writes at the dedicated workspace's root. Sync resets
#: and cleans every repo under -Root, so a root without it is refused: it could be a
#: person's live workspace.
$RUNNER_MARKER = ".release-runner"

#: The paths whose change merges WITHOUT a release (push.ps1's must-reach-main and
#: rides-along deltas): a package whose delta is only these needs no suite.
$NON_ARTIFACT = @(
    '^test/', '^docs/', '^\.github/', '^\.agents/', '^\.claude/',
    '^CHANGELOG\.md$', '^AGENTS\.md$', '^CLAUDE\.md$'
)

#: Each cascade package's FULL suite, relative to the workspace root: what a tests
#: receipt asserts ran green against the tree being published (m3trik/AGENTS.md).
$SUITES = @{
    "pythontk"  = @("pythontk/test/run_tests.py")
    "uitk"      = @("uitk/test/run_tests.py")
    "mayatk"    = @("mayatk/test/run_tests.py", "--all")
    "blendertk" = @("blendertk/test/run_tests.py")
    "tentacle"  = @("tentacle/test/run_tests.py", "--in-maya")
}

function Write-Phase {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text" -ForegroundColor Cyan
}

function Read-Manifest {
    param([string]$Root)
    return Get-Content -Raw -Encoding UTF8 (Join-Path $Root "m3trik/workspace.json") | ConvertFrom-Json
}

function Get-WorkspaceRepos {
    # The repos a release reads: the cascade, the standalone units (unitytk's samples are
    # checked against Maya's export; tentacle's extapps floor), and m3trik.
    param($Manifest)
    $standalone = @($Manifest.units | Where-Object { $_.release -eq "standalone" } | ForEach-Object { $_.path })
    return @(@($Manifest.cascade) + $standalone + @("m3trik") | Select-Object -Unique)
}

function Resolve-ReleasePackages {
    # *Requested* (comma-separated) as cascade packages in release order. Throws on a name
    # the cascade lacks: a typo must never release a partial set.
    param([string]$Requested, [string[]]$Cascade)
    $names = @($Requested -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if (-not $names) { throw "No packages named." }
    $unknown = @($names | Where-Object { $Cascade -notcontains $_ })
    if ($unknown) { throw "Not cascade packages: $($unknown -join ', ') (the cascade: $($Cascade -join ', '))." }
    return @($Cascade | Where-Object { $names -contains $_ })
}

function Test-ArtifactPath {
    # Whether a changed *Path* (repo-relative, forward slashes) ships.
    param([string]$Path)
    foreach ($pattern in $NON_ARTIFACT) {
        if ($Path -match $pattern) { return $false }
    }
    return $true
}

function Get-ArtifactDelta {
    # The files origin/main..origin/dev changes in *RepoPath* that ship.
    param([string]$RepoPath)
    $changed = @(git -C $RepoPath diff --name-only origin/main origin/dev)
    if ($LASTEXITCODE) { throw "git diff failed in $RepoPath" }
    return @($changed | Where-Object { $_ -and (Test-ArtifactPath $_) })
}

function Sync-ReleaseRepo {
    # Clone *Name* under *Root*, or fetch it; check out dev at origin/dev (main where the
    # repo has no dev), reset and clean. Returns the branch checked out.
    param([string]$Root, [string]$Name, [string]$RemoteBase)
    $path = Join-Path $Root $Name
    if (-not (Test-Path -LiteralPath (Join-Path $path ".git"))) {
        git clone --quiet "$RemoteBase/$Name" $path
        if ($LASTEXITCODE) { throw "clone of $Name failed" }
    }
    git -C $path fetch --quiet --prune --tags origin
    if ($LASTEXITCODE) { throw "fetch of $Name failed" }
    git -C $path rev-parse --quiet --verify "refs/remotes/origin/dev" *> $null
    $branch = if ($LASTEXITCODE -eq 0) { "dev" } else { "main" }
    git -C $path checkout --quiet --force -B $branch "origin/$branch"
    if ($LASTEXITCODE) { throw "checkout of $Name $branch failed" }
    git -C $path reset --quiet --hard "origin/$branch"
    git -C $path clean --quiet -fd
    if ($LASTEXITCODE) { throw "reset of $Name failed" }
    return $branch
}

function Merge-ToolingRepo {
    # m3trik's dev into main by PR, waited on, when their trees differ.
    param([string]$Root, [string]$Slug, [int]$TimeoutMinutes)
    $path = Join-Path $Root "m3trik"
    git -C $path diff --quiet origin/main origin/dev
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  m3trik: dev and main hold one tree"
        return
    }
    $pr = gh pr list --repo $Slug --head dev --base main --state open --json number --jq ".[0].number"
    if (-not $pr) {
        gh pr create --repo $Slug --head dev --base main --title "Release tooling: dev into main" `
            --body "Merged by the release runner before the cascade releases (push.ps1 refuses a release while m3trik/scripts lags main)." | Out-Null
        if ($LASTEXITCODE) { throw "could not open m3trik's dev -> main PR" }
        $pr = gh pr list --repo $Slug --head dev --base main --state open --json number --jq ".[0].number"
    }
    Write-Host "  m3trik: PR #$pr, merging when its checks pass"
    gh pr merge $pr --repo $Slug --merge --auto
    if ($LASTEXITCODE) { throw "could not arm m3trik PR #$pr" }
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    while ((Get-Date) -lt $deadline) {
        $state = gh pr view $pr --repo $Slug --json state --jq ".state"
        if ($state -eq "MERGED") {
            git -C $path fetch --quiet origin
            Write-Host "  m3trik: PR #$pr merged"
            return
        }
        if ($state -eq "CLOSED") { throw "m3trik PR #$pr was closed unmerged" }
        $failed = gh pr checks $pr --repo $Slug --json name,bucket --jq '[.[] | select(.bucket == "fail") | .name] | join(", ")'
        if ($failed) { throw "m3trik PR #${pr}: red check(s) $failed; fix on dev and dispatch again" }
        Start-Sleep -Seconds 20
    }
    throw "m3trik PR #$pr did not merge within $TimeoutMinutes minutes"
}

function Copy-HygieneDenylist {
    # *Source* to <Root>/.claude/public_hygiene.txt, where push.ps1's hygiene gate reads it.
    param([string]$Root, [string]$Source)
    if (-not $Source -or -not (Test-Path -LiteralPath $Source)) {
        Write-Host "  [WARN] no hygiene denylist (M3TRIK_HYGIENE_DENYLIST): push.ps1 cannot judge client names" -ForegroundColor Yellow
        return
    }
    $target = Join-Path $Root ".claude/public_hygiene.txt"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $target -Force
}

function Invoke-PackageSuite {
    # Run *Name*'s full suite from *Root* under *Python*; throws when it is red.
    param([string]$Root, [string]$Name, [string]$Python)
    $suite = $SUITES[$Name]
    if (-not $suite) { throw "No suite declared for $Name." }
    Push-Location $Root
    try {
        & $Python @suite
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($code) { throw "$Name's suite is red (exit $code): nothing was merged or published" }
}

function Invoke-RunnerRelease {
    param(
        [string]$Root,
        [string]$Packages,
        [bool]$Reviewed,
        [bool]$DryRun,
        [string]$RemoteBase,
        [int]$ToolingMergeTimeoutMinutes
    )
    if (-not $Root -or -not (Test-Path -LiteralPath (Join-Path $Root $RUNNER_MARKER))) {
        throw "$Root is not a release-runner workspace (no $RUNNER_MARKER): this run resets and cleans every repo under its root, so it never runs in a person's workspace. Run Install-ReleaseRunner.ps1."
    }
    $Root = (Resolve-Path -LiteralPath $Root).Path
    $manifest = Read-Manifest $Root
    $release = Resolve-ReleasePackages $Packages @($manifest.cascade)
    if (-not $Reviewed -and -not $DryRun) {
        throw "Not reviewed: the review receipt is the dispatcher's assertion. Review origin/main...origin/dev of $($release -join ', ') (correctness, DRY, simplification, efficiency), then dispatch with reviewed=true."
    }

    # The interpreter every suite and gate runs under: the runner's own (M3TRIK_PYTHON),
    # first on PATH so push.ps1's `python` is the same one.
    $python = if ($env:M3TRIK_PYTHON) { $env:M3TRIK_PYTHON } else { (Get-Command python -CommandType Application).Source }
    $env:PATH = (Split-Path -Parent $python) + [IO.Path]::PathSeparator + $env:PATH
    $repos = Get-WorkspaceRepos $manifest
    # The clones, ahead of any editable install of a person's workspace.
    $env:PYTHONPATH = (@($repos | Where-Object { $_ -ne "m3trik" } | ForEach-Object { Join-Path $Root $_ }) -join [IO.Path]::PathSeparator)

    # The public-hygiene denylist is private and lives in a person's workspace
    # (M3TRIK_HYGIENE_DENYLIST, set by the installer): copied in fresh each run, so
    # push.ps1's hygiene gate judges client names here as it does there.
    Copy-HygieneDenylist $Root $env:M3TRIK_HYGIENE_DENYLIST

    Write-Phase "Sync $($repos -join ', ')"
    foreach ($name in $repos) {
        if ($name -eq "m3trik") { continue }  # the workflow synced it before running this
        $branch = Sync-ReleaseRepo $Root $name $RemoteBase
        Write-Host ("  {0}: {1} at {2}" -f $name, $branch, (git -C (Join-Path $Root $name) rev-parse --short HEAD))
    }

    $push = Join-Path $Root "m3trik/push.ps1"
    if ($DryRun) {
        Write-Phase "Dry run: push.ps1 -DryRun -SkipReview"
        & $push -Packages $release -Strict -Merge -UsePR -DryRun -SkipReview -Root $Root
        return $LASTEXITCODE
    }

    Write-Phase "Tooling: m3trik dev -> main"
    $slug = ($RemoteBase -replace '^https://github\.com/', '') + "/m3trik"
    Merge-ToolingRepo $Root $slug $ToolingMergeTimeoutMinutes

    foreach ($name in $release) {
        $delta = Get-ArtifactDelta (Join-Path $Root $name)
        if (-not $delta) {
            Write-Phase "$name`: nothing that ships changed, no suite (push.ps1 exempts it)"
            continue
        }
        Write-Phase "$name`: full suite ($($delta.Count) shipping file(s) changed)"
        Invoke-PackageSuite $Root $name $python
        $checks = if ($Reviewed) { "review,tests" } else { "tests" }
        & $push -RecordReceipt $checks -Packages $name -Root $Root
        if ($LASTEXITCODE) { throw "could not record $name's receipts" }
    }

    Write-Phase "Release: push.ps1 -Packages $($release -join ',') -Strict -Merge -UsePR"
    & $push -Packages $release -Strict -Merge -UsePR -Root $Root
    return $LASTEXITCODE
}

if ($MyInvocation.InvocationName -eq ".") { return }

try {
    $code = Invoke-RunnerRelease -Root $Root -Packages $Packages -Reviewed $Reviewed.IsPresent `
        -DryRun $DryRun.IsPresent -RemoteBase $RemoteBase -ToolingMergeTimeoutMinutes $ToolingMergeTimeoutMinutes
    exit $(if ($code) { $code } else { 0 })
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
