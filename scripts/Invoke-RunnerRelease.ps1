<#
Invoke-RunnerRelease.ps1 -- release the cascade from the release runner, gates intact.

What the private release repo's Release workflow runs (docs/RELEASE_RUNNER.md) on the
self-hosted runner Install-ReleaseRunner.ps1 sets up on the machine that has Maya and
Blender. It never touches a person's working trees: it runs in a DEDICATED workspace
(-Root, marked by the installer's .release-runner file) that it resets to origin/dev
on every run, so a release publishes exactly what dev holds and nothing a person is
still editing. It decides nothing push.ps1 decides: which packages release, in what
order, and which owe a receipt are push.ps1's answers (-GateReport).

    Sync       clone or fetch every workspace repo; each checks out dev at origin/dev,
               reset and cleaned (untracked files go, ignored ones stay).
    Tooling    m3trik's main is fast-forwarded to dev when they differ, as m3trik lands
               (push.ps1 refuses a release while m3trik/scripts lags origin/main); a
               main dev does not contain stops the run.
    Preflight  push.ps1 -DryRun: the plan and every cheap gate, before a suite runs.
    Receipts   push.ps1 -GateReport names the packages that owe receipts. A review
               receipt is the dispatcher's assertion, pinned to the commit reviewed
               (-Reviewed "pkg@sha,..."): a dev that moved since is refused. A tests
               receipt is that package's FULL suite, green, in fresh Maya / Blender
               instances its runner launches; red stops the run.
    Release    push.ps1 -Strict -Merge -UsePR, every gate its own.

-DryRun stops after the preflight and the gate report (no tooling push, no suite,
nothing recorded): the plan, the runner's health, and the -Reviewed value a release
of what dev holds now would need. Exit 0 only when every phase passed.

Dot-sourcing this file defines its functions and runs nothing (the tests use that).
#>

param(
    [string]$Root,
    # Cascade packages, comma-separated; blank is the whole cascade (workspace.json).
    [string]$Packages = "",
    # The review attestation: "package@sha,..." naming the dev commit reviewed, per package.
    [string]$Reviewed = "",
    [switch]$DryRun,
    # Where the workspace repos are cloned from (<base>/<repo>); blank: beside m3trik's own
    # origin, so a fork's runner releases the fork.
    [string]$RemoteBase = ""
)

$ErrorActionPreference = "Stop"

#: The file Install-ReleaseRunner.ps1 writes at the dedicated workspace's root. Sync resets
#: and cleans every repo under -Root, so a root without it is refused: it could be a
#: person's live workspace.
$RUNNER_MARKER = ".release-runner"

#: Each cascade package's FULL suite, relative to the workspace root: what a tests
#: receipt asserts ran green against the tree being published (m3trik/AGENTS.md).
$SUITES = @{
    "pythontk"  = @("pythontk/test/run_tests.py")
    "uitk"      = @("uitk/test/run_tests.py")
    "mayatk"    = @("mayatk/test/run_tests.py", "--all")
    "blendertk" = @("blendertk/test/run_tests.py")
    "tentacle"  = @("tentacle/test/run_tests.py", "--in-maya")
}

#: The PowerShell running this, for push.ps1's child runs.
$POWERSHELL = (Get-Process -Id $PID).Path

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
    # *Requested* (comma-separated; blank: all of it) as cascade packages. Throws on a
    # name the cascade lacks: push.ps1 skips an unknown name and releases the rest, and a
    # typo must never release a partial set.
    param([string]$Requested, [string[]]$Cascade)
    $names = @($Requested -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if (-not $names) { return $Cascade }
    $unknown = @($names | Where-Object { $Cascade -notcontains $_ })
    if ($unknown) { throw "Not cascade packages: $($unknown -join ', ') (the cascade: $($Cascade -join ', '))." }
    return @($Cascade | Where-Object { $names -contains $_ })
}

function Sync-ReleaseRepo {
    # Clone *Name* under *Root*, or fetch it; check out dev at origin/dev (main where the
    # repo has no dev), reset and clean. Returns the branch checked out.
    param([string]$Root, [string]$Name, [string]$RemoteBase)
    $path = Join-Path $Root $Name
    if (-not (Test-Path -LiteralPath (Join-Path $path ".git"))) {
        git clone --quiet "$RemoteBase/$Name" $path | Out-Host
        if ($LASTEXITCODE) { throw "clone of $Name failed" }
    }
    git -C $path fetch --quiet --prune --tags origin | Out-Host
    if ($LASTEXITCODE) { throw "fetch of $Name failed" }
    git -C $path rev-parse --quiet --verify "refs/remotes/origin/dev" *> $null
    $branch = if ($LASTEXITCODE -eq 0) { "dev" } else { "main" }
    git -C $path checkout --quiet --force -B $branch "origin/$branch" | Out-Host
    if ($LASTEXITCODE) { throw "checkout of $Name $branch failed" }
    git -C $path reset --quiet --hard "origin/$branch" | Out-Host
    git -C $path clean --quiet -fd | Out-Host
    if ($LASTEXITCODE) { throw "reset of $Name failed" }
    return $branch
}

function Merge-ToolingRepo {
    # m3trik's dev onto main, as m3trik lands (a direct push; its CI runs on main), when
    # their trees differ. A fast-forward only: a main that dev does not contain is a
    # person's call, never the runner's. Returns what it did.
    param([string]$Root)
    $path = Join-Path $Root "m3trik"
    git -C $path diff --quiet origin/main origin/dev
    if ($LASTEXITCODE -eq 0) { return "level" }
    git -C $path merge-base --is-ancestor origin/main origin/dev
    if ($LASTEXITCODE) {
        throw "m3trik's main holds commits dev lacks: merge main into dev, then dispatch again"
    }
    git -C $path push --quiet origin "refs/remotes/origin/dev:refs/heads/main" | Out-Host
    if ($LASTEXITCODE) { throw "could not push m3trik's dev to main" }
    git -C $path fetch --quiet origin | Out-Host
    return "fast-forwarded"
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

function Invoke-Push {
    # <Root>/m3trik/push.ps1 in a child PowerShell with *Arguments*, its output to the
    # log. Throws *Why* when it fails.
    param([string]$Root, [string]$Why, [string[]]$Arguments)
    & $POWERSHELL -NoProfile -File (Join-Path $Root "m3trik/push.ps1") -Root $Root @Arguments | Out-Host
    if ($LASTEXITCODE) { throw "$Why (push.ps1 exit $LASTEXITCODE)" }
}

function Get-GateVerdicts {
    # push.ps1 -GateReport for *Names*: one row per package the run would process,
    # @{ package; sha; hash; class; exempt; missing }. *Extra*: more push.ps1 arguments.
    param([string]$Root, [string[]]$Names, [string[]]$Extra = @())
    $out = & $POWERSHELL -NoProfile -File (Join-Path $Root "m3trik/push.ps1") -Root $Root `
        -Packages ($Names -join ",") -Strict -Merge -GateReport @Extra
    $code = $LASTEXITCODE
    $lines = @($out | ForEach-Object { "$_" } | Where-Object { $_.Trim() })
    if ($code -or -not $lines) {
        $lines | Out-Host
        throw "push.ps1 could not report the release gate (exit $code)"
    }
    $lines | Select-Object -SkipLast 1 | Out-Host
    return @($lines[-1] | ConvertFrom-Json)
}

function Test-Attested {
    # Whether *Reviewed* ("package@sha,...") names *Package* at *Sha* (a prefix of 7+).
    param([string]$Reviewed, [string]$Package, [string]$Sha)
    foreach ($entry in @($Reviewed -split "[,\s]+" | Where-Object { $_ })) {
        $name, $at = $entry -split "@", 2
        if ($name -eq $Package -and $at -and $at.Length -ge 7 -and $Sha.StartsWith($at, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Invoke-PackageSuite {
    # Run *Name*'s full suite from *Root* under *Python*, its output to the log; throws
    # when it is red.
    param([string]$Root, [string]$Name, [string]$Python)
    $suite = $SUITES[$Name]
    if (-not $suite) { throw "No suite declared for $Name." }
    Push-Location $Root
    try {
        & $Python @suite | Out-Host
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
        [string]$Reviewed,
        [bool]$DryRun,
        [string]$RemoteBase
    )
    if (-not $Root -or -not (Test-Path -LiteralPath (Join-Path $Root $RUNNER_MARKER))) {
        throw "$Root is not a release-runner workspace (no $RUNNER_MARKER): this run resets and cleans every repo under its root, so it never runs in a person's workspace. Run Install-ReleaseRunner.ps1."
    }
    $Root = (Resolve-Path -LiteralPath $Root).Path
    if (-not $RemoteBase) {
        $RemoteBase = "$(git -C (Join-Path $Root 'm3trik') remote get-url origin)" -replace '[\\/]m3trik(\.git)?[\\/]?$', ''
    }
    $manifest = Read-Manifest $Root
    $release = Resolve-ReleasePackages $Packages @($manifest.cascade)
    $set = $release -join ","

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

    if (-not $DryRun) {
        Write-Phase "Tooling: m3trik main <= dev"
        Write-Host "  m3trik: $(Merge-ToolingRepo $Root)"
    }

    Write-Phase "Preflight: push.ps1 -DryRun (the plan and the cheap gates)"
    Invoke-Push $Root "The preflight failed: nothing was tested, merged or published" @(
        "-Packages", $set, "-Strict", "-Merge", "-UsePR", "-DryRun", "-SkipReview")

    Write-Phase "Release gate: who owes a receipt"
    # A dry run reads the gate past the m3trik-first guard (-SkipReview): it pushed no tooling.
    $verdicts = Get-GateVerdicts $Root $release $(if ($DryRun) { @("-SkipReview") } else { @() })
    $owing = @($verdicts | Where-Object { $_.missing })
    foreach ($v in $verdicts) {
        $state = if ($v.missing) { "owes $($v.missing -join ' + ')" } elseif ($v.exempt) { $v.exempt } else { "receipts valid" }
        Write-Host ("  {0}@{1}: {2}" -f $v.package, "$($v.sha)".Substring(0, [Math]::Min(7, "$($v.sha)".Length)), $state)
    }
    $toReview = @($owing | Where-Object { $_.missing -contains "review" })
    $attestation = (@($toReview | ForEach-Object { "$($_.package)@$("$($_.sha)".Substring(0, 7))" }) -join ",")
    if ($toReview) { Write-Host "  A release of this dev needs: reviewed=$attestation" }
    if ($DryRun) { return }

    # Before any suite: an unreviewed tree must not cost hours of them.
    $unreviewed = @($toReview | Where-Object { -not (Test-Attested $Reviewed $_.package $_.sha) })
    if ($unreviewed) {
        throw "Not reviewed at the commit dev holds: $(@($unreviewed | ForEach-Object { $_.package }) -join ', '). Review origin/main...origin/dev of each (correctness, DRY, simplification, efficiency), then dispatch with reviewed=$attestation"
    }

    foreach ($v in $owing) {
        if ($v.missing -contains "tests") {
            Write-Phase "$($v.package): full suite"
            Invoke-PackageSuite $Root $v.package $python
        }
        # After the suite: a full run stamps the README badge, and a receipt keys on the tree.
        Invoke-Push $Root "could not record $($v.package)'s receipts" @(
            "-RecordReceipt", ($v.missing -join ","), "-Packages", $v.package)
    }

    Write-Phase "Release: push.ps1 -Packages $set -Strict -Merge -UsePR"
    Invoke-Push $Root "The release did not complete; dispatching again resumes it" @(
        "-Packages", $set, "-Strict", "-Merge", "-UsePR")
}

if ($MyInvocation.InvocationName -eq ".") { return }

try {
    Invoke-RunnerRelease -Root $Root -Packages $Packages -Reviewed $Reviewed `
        -DryRun $DryRun.IsPresent -RemoteBase $RemoteBase
    exit 0
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
