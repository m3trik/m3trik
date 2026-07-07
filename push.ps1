<#
Repository Manager (push.ps1)

Purpose
- Safely push changes on dev and (optionally) promote dev -> main in a controlled release order.
- Designed for the core package chain: pythontk -> uitk -> mayatk -> tentacle (tentacletk on PyPI).

Core safety rules (Strict+Merge)
- Enforces canonical release order when multiple packages are provided.
- Stops on the first failure (build, merge conflict, workflow timeout, unsafe repo state).
- Refuses to operate if a repo has an in-progress merge/rebase/cherry-pick.
- Refuses to proceed if conflict markers exist in requirements.txt (local OR remote origin/main|origin/dev).
- Keeps internal requirements.txt pins in sync with the local versions being released.

Recommended usage

1) Safe release (PR-based, respects “PR-only” policies)
    .\m3trik\push.ps1 -Packages pythontk,uitk,mayatk,tentacle -Strict -Merge -UsePR

2) Safe release (direct merge, for repos without PR-only enforcement)
    .\m3trik\push.ps1 -Packages pythontk,uitk,mayatk,tentacle -Strict -Merge

3) Push dev only (no merge)
    .\m3trik\push.ps1 -Packages mayatk,tentacle

4) Dry run (no repo changes)
    .\m3trik\push.ps1 -All -DryRun -Strict

Key flags
-All                  Process all git repos under -Root.
-Packages             Target specific repos (comma-separated allowed).
-Strict               Adds build validation + strict safety checks for core packages.
-Merge                Promotes dev -> main after pushing dev.
-UsePR                Uses GitHub PRs (via gh) to merge dev -> main (recommended).
-SkipBuild            Skip python build/twine validation.
-SkipWorkflowWait     Skip waiting for the publish workflow on main.
-CommitMessage        Message for the auto-commit Sync-DevWithOrigin makes when
                              absorbing local changes (defaults to "Update").
-WorkflowTimeoutSeconds / -WorkflowPollSeconds
                              Control workflow wait behavior.

Notes
- PyPI install requirements come from pyproject.toml; requirements.txt pins are for pip -r workflows.
- PR mode requires GitHub CLI (gh) with authenticated access.
#>

param(
    [switch]$All,
    [string[]]$Packages,
    [switch]$Merge,
    [switch]$Strict,
    [switch]$DryRun,
    [switch]$SkipBuild,
    [switch]$SkipWorkflowWait,
    [switch]$SkipPypiCheck,
    [switch]$UsePR,
    [int]$PRMergeTimeoutSeconds = 1800,
    [int]$WorkflowTimeoutSeconds = 900,
    [int]$WorkflowPollSeconds = 15,
    [string]$WorkflowFile = "publish.yml",
    [string]$Root = "O:\Cloud\Code\_scripts",
    [string]$CommitMessage = "Update"
)

$ErrorActionPreference = "Continue"
$ROOT = $Root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
. (Join-Path $SCRIPT_DIR "common.ps1")

# Packages that support strict validation
# NOTE: blendertk is dep-synced (see $requiredPinsByPackage) but stays OUT of the strict/release
# sets until it is publishable — repo is private, not on PyPI, and has no publish workflow yet
# (same treatment as unitytk). Add it here + to the auto-cascade graph when that decision lands.
$STRICT_PACKAGES = @("pythontk", "uitk", "mayatk", "tentacle")
$RELEASE_ORDER = @("pythontk", "uitk", "mayatk", "tentacle")

function Get-RepoSlugFromOriginUrl {
    param([string]$OriginUrl)

    if (-not $OriginUrl) {
        return $null
    }
    if ($OriginUrl -match "github\.com[:/](?<slug>[^/]+/[^/]+?)(?:\.git)?$") {
        return $Matches["slug"]
    }
    return $null
}

function Get-PypiProjectName {
    param([string]$PackageName)

    # The tentacle repo publishes as tentacletk
    if ($PackageName -eq "tentacle") { return "tentacletk" }
    return $PackageName
}

function Test-PypiHasVersion {
    param(
        [string]$ProjectName,
        [string]$Version
    )

    try {
        $url = "https://pypi.org/pypi/$ProjectName/json"
        $data = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
        if (-not $data -or -not $data.releases) {
            return $false
        }
        return $data.releases.PSObject.Properties.Name -contains $Version
    }
    catch {
        # If offline or rate-limited, fail safe in strict merge mode unless explicitly skipped.
        return $false
    }
}

function Get-PypiLatestVersion {
    param([string]$ProjectName)

    try {
        $url = "https://pypi.org/pypi/$ProjectName/json"
        $data = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
        if ($data -and $data.info -and $data.info.version) {
            return [string]$data.info.version
        }
    }
    catch {}
    return $null
}

function Bump-LocalVersion {
    param(
        [string]$PackagePath
    )
    $initFile = Join-Path (Join-Path $PackagePath "src") "__init__.py"
    # Try src/pkg/__init__.py first, then pkg/__init__.py
    if (-not (Test-Path $initFile)) {
        $name = Split-Path $PackagePath -Leaf
        $initFile = Join-Path (Join-Path $PackagePath $name) "__init__.py"
    }

    if (-not (Test-Path $initFile)) { 
        return $null 
    }

    $content = Get-Content $initFile -Raw
    if ($content -match '__version__\s*=\s*["''](?<ver>\d+\.\d+\.\d+)["'']') {
        $oldVer = $Matches['ver']
        $parts = $oldVer -split "\."
        $parts[2] = [int]$parts[2] + 1
        $newVer = "$($parts[0]).$($parts[1]).$($parts[2])"
        
        $newContent = $content -replace "__version__\s*=\s*.*", "__version__ = `"$newVer`""
        Set-Content -Path $initFile -Value $newContent -NoNewline
        Write-Host "    Bumped version: $oldVer -> $newVer" -ForegroundColor Cyan
        return $newVer
    }
    return $null
}

function Get-LocalStrictVersions {
    # Read each strict package's local __init__.py version, then clamp against
    # PyPI: if the local version isn't actually published (e.g. bump-dev left a
    # next-version placeholder), use PyPI's latest instead. This way every
    # consumer of the version map (cascade pins, PyPI check, etc.) sees the
    # version that's actually installable.
    $versions = @{}
    foreach ($pkg in $STRICT_PACKAGES) {
        $pkgPath = Join-Path (Join-Path $ROOT $pkg) $pkg
        $ver = Get-PackageVersion $pkgPath
        if (-not $ver -or $ver -eq "unknown") { continue }

        $pypiName = Get-PypiProjectName $pkg
        if (-not (Test-PypiHasVersion $pypiName $ver)) {
            $latest = Get-PypiLatestVersion $pypiName
            if ($latest) {
                Write-Host "  > $pkg local $ver is unpublished; using PyPI latest $latest" -ForegroundColor DarkGray
                $ver = $latest
            }
        }
        $versions[$pkg] = $ver
    }
    return $versions
}

function Sync-PyProjectDepsToLocalVersions {
    param(
        [string]$PackageName,
        [string]$RepoPath,
        [hashtable]$LocalVersions
    )

    $tomlFile = Join-Path $RepoPath "pyproject.toml"
    if (-not (Test-Path $tomlFile)) {
        return $true
    }

    # Only these packages have internal pins today.
    $requiredPinsByPackage = @{
        "uitk"      = @("pythontk")
        "mayatk"    = @("pythontk", "uitk")
        "blendertk" = @("pythontk")
        "tentacle"  = @("pythontk", "uitk", "mayatk")
    }

    if (-not $requiredPinsByPackage.ContainsKey($PackageName)) {
        return $true
    }

    $requiredPins = $requiredPinsByPackage[$PackageName]
    # Ensure edits land on dev
    Push-Location $RepoPath
    try {
        git checkout dev --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Checkout dev failed (toml sync)"
            return $false
        }
    }
    finally {
        Pop-Location
    }

    $content = Get-Content $tomlFile -Raw
    $newContent = $content
    $changed = $false

    foreach ($dep in $requiredPins) {
        if (-not $LocalVersions.ContainsKey($dep)) {
            Write-Err "Cannot sync toml: missing local version for '$dep'"
            return $false
        }
        # $LocalVersions is pre-clamped against PyPI in Get-LocalStrictVersions,
        # so this is the actually-published version to pin against.
        $ver = $LocalVersions[$dep]

        $pattern = '"' + $dep + '>=[0-9.]+"'
        $replacement = '"' + $dep + '>=' + $ver + '"'
        
        if ($newContent -match $pattern) {
             # Check if it's already correct to avoid unnecessary writes
             $currentMatch = $matches[0]
             if ($currentMatch -ne $replacement) {
                 $newContent = $newContent -replace $pattern, $replacement
                 $changed = $true
             }
        }
    }

    if ($DryRun) {
        if ($changed) {
            Write-Step "[DryRun] Would bump local version of $PackageName (dependency sync)"
            Write-Step "[DryRun] Would sync pyproject.toml dependencies"
            # Mirror the auto-bump DryRun mock so downstream pin simulations see the
            # cascaded version, not the pre-cascade one.
            if ($LocalVersions.ContainsKey($PackageName)) {
                $curr = $LocalVersions[$PackageName]
                try {
                    $parts = $curr -split "\."
                    $nextPatch = [int]$parts[-1] + 1
                    $LocalVersions[$PackageName] = "$($parts[0]).$($parts[1]).$nextPatch"
                } catch {}
            }
        } else {
            Write-Step "[DryRun] Dependencies already in sync"
        }
        return $true
    }

    if (-not $changed) {
        return $true
    }

    # CRITICAL: If dependencies change, the package artifact has changed.
    # We MUST bump the package version, otherwise PyPI will reject the re-upload 
    # of the existing version with new metadata.
    $newVer = Bump-LocalVersion $RepoPath
    if ($newVer) {
        Write-Host "    [Dependency Cascading] Bumped $PackageName to $newVer" -ForegroundColor Cyan
        # Write back so downstream packages pin the cascaded version, not the pre-cascade one.
        $LocalVersions[$PackageName] = $newVer
    } else {
        Write-Err "    Failed to bump version for $PackageName after dependency update"
        # Abort: writing the new toml + committing without a version bump produces
        # a "version to  [skip ci]" commit that PyPI will reject (changed metadata,
        # unchanged version). Let the caller mark this package failed.
        return $false
    }

    Set-Content -Path $tomlFile -Value $newContent -NoNewline

    Push-Location $RepoPath
    try {
        git add .
        git commit -m "Update dependencies & bump version to $newVer [skip ci]" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to commit pyproject.toml updates"
            return $false
        }
        Write-Success "Synced dependencies & bumped version"
        return $true
    }
    finally {
        Pop-Location
    }
}

function Test-OnlyDevBumpChanges {
    param(
        [string]$RepoPath,
        [string]$PackageName
    )

    # ONLY a pure version-string bump counts as "nothing to release". The strict
    # packages all declare `version = {attr = "<pkg>.__version__"}` (dynamic), so
    # a bump touches exactly <pkg>/__init__.py and nothing else. Deliberately
    # NOT allowing pyproject.toml here: a dependency-cascade release changes only
    # the pin in pyproject.toml (+ the version), and that MUST still merge/publish
    # so downstream pins propagate — treating it as "bump noise" would silently
    # drop the whole point of the cascade. README/docs changes likewise ship in
    # the wheel and should release. (A statically-versioned package would touch
    # pyproject.toml on bump and fall through to a merge — harmless, just no skip.)
    $allowed = @(
        "$PackageName/__init__.py"
    )

    Push-Location $RepoPath
    try {
        git fetch origin main dev --quiet 2>&1 | Out-Null
        $files = @(git diff --name-only origin/main..origin/dev 2>$null)
        if (-not $files -or $files.Count -eq 0) {
            return $false
        }
        foreach ($f in $files) {
            if ($allowed -notcontains $f) {
                return $false
            }
        }
        return $true
    }
    finally {
        Pop-Location
    }
}

function Test-Build {
    param([string]$PackageName, [string]$RepoPath)

    Write-Step "Validating build..."
    Push-Location $RepoPath
    try {
        $oldErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"

        # Cloud-sync clients (OneDrive/Dropbox) on O:\Cloud\ intermittently lock the
        # final wheel write, surfacing as "Permission denied" / Errno 13. Retry on
        # that signature; bail immediately on real build errors.
        $maxAttempts = 3
        $filteredOutput = $null
        $buildOk = $false
        for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
            if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue }
            if (Test-Path "build") { Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue }
            $eggInfo = "$PackageName.egg-info"
            if (Test-Path $eggInfo) { Remove-Item -Recurse -Force $eggInfo -ErrorAction SilentlyContinue }

            $buildJob = Start-Job -ScriptBlock {
                param($path)
                Set-Location $path
                python -m build --wheel 2>&1
            } -ArgumentList $RepoPath

            Wait-Job $buildJob -Timeout 60 | Out-Null
            if ($buildJob.State -eq 'Running') {
                Stop-Job $buildJob
                Remove-Job $buildJob
                $ErrorActionPreference = $oldErrorAction
                Write-Err "Build timed out (60s)!"
                return $false
            }

            $buildOutput = Receive-Job $buildJob
            Remove-Job $buildJob

            $filteredOutput = $buildOutput | Where-Object {
                $_ -notmatch "^\s*(copying|creating|reading|writing|hard linking|adding|removing)"
            }

            $buildCode = $filteredOutput | Select-String -Pattern "error|ERROR|failed|FAILED" -Quiet
            if (-not $buildCode) {
                $buildOk = $true
                break
            }

            $transient = $filteredOutput | Select-String -Pattern "Permission denied|Errno 13" -Quiet
            if ($transient -and $attempt -lt $maxAttempts) {
                Write-Host "    Build attempt $attempt hit cloud-sync lock; retrying..." -ForegroundColor DarkGray
                Start-Sleep -Seconds 5
                continue
            }
            break
        }

        if (-not $buildOk) {
            $ErrorActionPreference = $oldErrorAction
            Write-Err "Build failed!"
            Write-Host "    $($filteredOutput | Select-String -Pattern 'error|ERROR|failed|FAILED' | Select-Object -First 1)" -ForegroundColor DarkGray
            return $false
        }
        
        # Run twine check with timeout (30 seconds)
        $twineJob = Start-Job -ScriptBlock {
            param($path)
            Set-Location $path
            python -m twine check dist/* 2>&1
        } -ArgumentList $RepoPath
        
        Wait-Job $twineJob -Timeout 30 | Out-Null
        if ($twineJob.State -eq 'Running') {
            Stop-Job $twineJob
            Remove-Job $twineJob
            $ErrorActionPreference = $oldErrorAction
            Write-Err "Twine check timed out (30s)!"
            return $false
        }
        
        $twineOutput = Receive-Job $twineJob
        Remove-Job $twineJob

        # Negative signals: import errors, tracebacks, twine's own error/warning lines.
        $twineErrPattern = "ModuleNotFoundError|ImportError|Traceback|error|ERROR|failed|FAILED|warning|WARNING"
        # Positive signal: every wheel must show "PASSED". If twine never ran (e.g. the
        # module is missing from this venv), we won't see PASSED and treat it as failure.
        $twineCode = $twineOutput | Select-String -Pattern $twineErrPattern -Quiet
        $passedCount = ($twineOutput | Select-String -Pattern ":\s*PASSED").Count

        $ErrorActionPreference = $oldErrorAction

        if ($twineCode -or $passedCount -lt 1) {
            Write-Err "Twine validation failed!"
            $firstHit = $twineOutput | Select-String -Pattern $twineErrPattern | Select-Object -First 1
            if (-not $firstHit) { $firstHit = "no PASSED line in twine output" }
            Write-Host "    $firstHit" -ForegroundColor DarkGray
            return $false
        }

        Write-Success "Build validated"
        return $true
    }
    finally {
        Pop-Location
    }
}

function Wait-ForWorkflow {
    param(
        [string]$RepoPath,
        [string]$PackageName
    )
    
    Write-Step "Waiting for GitHub Actions to complete..."

    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Err "GitHub CLI (gh) not found; cannot reliably wait for workflows"
        return $false
    }

    $repoSlug = $null
    $headSha = $null
    try {
        Push-Location $RepoPath
        $originUrl = (git config --get remote.origin.url 2>$null).Trim()
        $repoSlug = Get-RepoSlugFromOriginUrl $originUrl
        git fetch origin main --quiet 2>&1 | Out-Null
        $headSha = (git rev-parse origin/main 2>$null).Trim()
    }
    finally {
        Pop-Location
    }

    if (-not $repoSlug) {
        Write-Err "Cannot determine GitHub repo (remote.origin.url='$originUrl')"
        return $false
    }
    if (-not $headSha) {
        Write-Err "Cannot determine head SHA for origin/main"
        return $false
    }

    $maxWait = $WorkflowTimeoutSeconds
    $elapsed = 0

    while ($elapsed -lt $maxWait) {
        if ($elapsed -eq 0) {
            Start-Sleep -Seconds 10
            $elapsed += 10
        } else {
            Start-Sleep -Seconds $WorkflowPollSeconds
            $elapsed += $WorkflowPollSeconds
        }

        $runs = $null
        try {
            # Use the publish workflow as the canonical signal.
            $runsJson = gh run list --repo $repoSlug --branch main --workflow $WorkflowFile --limit 20 --json status,conclusion,headSha,createdAt,displayTitle 2>$null
            if (-not $runsJson) {
                continue
            }
            $runs = $runsJson | ConvertFrom-Json
        }
        catch {
            continue
        }

        $matching = @($runs | Where-Object { $_.headSha -eq $headSha })
        if (-not $matching -or $matching.Count -eq 0) {
            if ($elapsed % 60 -eq 0) {
                Write-Host "    Waiting for workflow to start... ($elapsed/$maxWait seconds)" -ForegroundColor Gray
            }
            continue
        }

        $inProgress = @($matching | Where-Object { $_.status -ne "completed" })
        if ($inProgress.Count -gt 0) {
            if ($elapsed % 60 -eq 0) {
                Write-Host "    Waiting... ($elapsed/$maxWait seconds)" -ForegroundColor Gray
            }
            continue
        }

        $failed = @($matching | Where-Object { $_.conclusion -and $_.conclusion -ne "success" })
        if ($failed.Count -gt 0) {
            $c = $failed[0].conclusion
            Write-Err "Workflow concluded with '$c'"
            return $false
        }

        Write-Success "Workflow completed (publish.yml)"
        return $true
    }

    Write-Host "    Warning: Timeout waiting for workflow (${maxWait}s)" -ForegroundColor Yellow
    Write-Host "    Stopping process - check GitHub Actions manually" -ForegroundColor Red
    return $false
}

function Get-GitHubRepoSlug {
    param([string]$RepoPath)

    Push-Location $RepoPath
    try {
        $originUrl = (git config --get remote.origin.url 2>$null).Trim()
        return Get-RepoSlugFromOriginUrl $originUrl
    }
    finally {
        Pop-Location
    }
}

function Ensure-GhAuth {
    $out = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "gh is not authenticated"
        if ($out) { Write-Host "    $out" -ForegroundColor DarkGray }
        return $false
    }
    return $true
}

function Ensure-ReleasePR {
    param(
        [string]$RepoSlug,
        [string]$PackageName
    )

    # Try to find an existing open PR from dev -> main
    $listJson = gh pr list --repo $RepoSlug --state open --base main --head dev --json number --limit 1 2>$null
    if ($LASTEXITCODE -eq 0 -and $listJson) {
        try {
            $prs = $listJson | ConvertFrom-Json
            if ($prs -and $prs.Count -gt 0) {
                return [int]$prs[0].number
            }
        }
        catch {
        }
    }

    # Create a new PR
    $title = "Release: $PackageName"
    $body = "Automated release PR (dev -> main)."
    $createOut = gh pr create --repo $RepoSlug --base main --head dev --title $title --body $body 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create PR"
        if ($createOut) { Write-Host "    $createOut" -ForegroundColor DarkGray }
        return $null
    }

    # Parse PR number from URL
    if ($createOut -match "/pull/(?<num>\d+)") {
        return [int]$Matches["num"]
    }

    # Fallback: list again
    $listJson2 = gh pr list --repo $RepoSlug --state open --base main --head dev --json number --limit 1 2>$null
    try {
        $prs2 = $listJson2 | ConvertFrom-Json
        if ($prs2 -and $prs2.Count -gt 0) {
            return [int]$prs2[0].number
        }
    }
    catch {
    }
    return $null
}

function Enable-AutoMergePR {
    param(
        [string]$RepoSlug,
        [int]$PrNumber
    )

    $out = gh pr merge $PrNumber --repo $RepoSlug --merge --auto 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to enable auto-merge for PR #$PrNumber"
        if ($out) { Write-Host "    $out" -ForegroundColor DarkGray }
        Write-Err "Ensure auto-merge is enabled in repo settings, or run without -UsePR."
        return $false
    }
    return $true
}

function Wait-ForPRMerged {
    param(
        [string]$RepoSlug,
        [int]$PrNumber,
        [int]$TimeoutSeconds
    )

    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        Start-Sleep -Seconds 10
        $elapsed += 10

        $viewJson = gh pr view $PrNumber --repo $RepoSlug --json state,mergedAt 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $viewJson) {
            continue
        }
        try {
            $v = $viewJson | ConvertFrom-Json
            if ($v.mergedAt) {
                Write-Success "PR #$PrNumber merged"
                return $true
            }
            if ($v.state -eq "CLOSED") {
                Write-Err "PR #$PrNumber closed without merge"
                return $false
            }
        }
        catch {
        }

        if ($elapsed % 60 -eq 0) {
            Write-Host "    Waiting for PR merge... ($elapsed/$TimeoutSeconds seconds)" -ForegroundColor Gray
        }
    }

    Write-Host "    Warning: Timeout waiting for PR merge (${TimeoutSeconds}s)" -ForegroundColor Yellow
    Write-Host "    Stopping process - check PR status manually" -ForegroundColor Red
    return $false
}

function Merge-ToMainViaPR {
    param(
        [string]$RepoPath,
        [string]$PackageName
    )

    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Err "GitHub CLI (gh) not found; cannot use PR mode"
        return $false
    }
    if (-not (Ensure-GhAuth)) {
        return $false
    }

    $repoSlug = Get-GitHubRepoSlug $RepoPath
    if (-not $repoSlug) {
        Write-Err "Origin remote is not a GitHub URL; cannot use PR mode"
        return $false
    }

    Write-Step "Creating/updating PR (dev -> main)..."
    $pr = Ensure-ReleasePR $repoSlug $PackageName
    if (-not $pr) {
        return $false
    }
    Write-Success "PR ready (#$pr)"

    Write-Step "Enabling auto-merge (merge commit) for PR #$pr..."
    $autoOk = Enable-AutoMergePR $repoSlug $pr
    if (-not $autoOk) {
        return $false
    }

    Write-Step "Waiting for PR to merge..."
    return (Wait-ForPRMerged $repoSlug $pr $PRMergeTimeoutSeconds)
}

function Get-ChangelogDelta {
    # This release's CHANGELOG additions = lines added to CHANGELOG.md on dev
    # relative to the last-released state (origin/main). A deterministic boundary
    # (no date heuristics) that fits the existing dated-prose CHANGELOG as-is —
    # nothing about how the changelog is written changes. Returns the added text
    # (for the git tag / GitHub Release), or "" when this release added no
    # CHANGELOG entries (e.g. a docstring-only or dependency-bump release → the
    # version is still tagged, just without a Release body).
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        if (-not (Test-Path "CHANGELOG.md")) { return "" }
        git fetch origin main --quiet 2>&1 | Out-Null
        # `dev` (local HEAD) vs origin/main; keep added lines, drop the '+++' header.
        $diff = git diff origin/main..dev -- CHANGELOG.md 2>$null
        if (-not $diff) { return "" }
        $added = $diff |
            Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' } |
            ForEach-Object { $_.Substring(1) }
        return (($added -join "`n").Trim())
    }
    finally {
        Pop-Location
    }
}

function New-GitReleaseTag {
    # Annotated tag v<Version> on origin/main HEAD (idempotent) plus a GitHub
    # Release when there are curated notes. Additive and NON-FATAL: a failure
    # here never aborts the release — the PyPI publish + main merge already
    # succeeded by the time this runs, so the worst case is a missing tag/release
    # the operator can add manually.
    param(
        [string]$RepoPath,
        [string]$RepoSlug,
        [string]$PackageName,
        [string]$Version,
        [string]$Notes
    )
    if (-not $Version) { return }
    $tag = "v$Version"
    Push-Location $RepoPath
    try {
        git fetch origin main --quiet 2>&1 | Out-Null
        $existing = git ls-remote --tags origin $tag 2>$null
        if ($existing) {
            Write-Skip "Tag $tag already exists (skipping)"
            return
        }
        $sha = (git rev-parse origin/main 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $sha) {
            Write-Err "Cannot resolve origin/main for tag $tag"
            return
        }
        $sha = $sha.Trim()

        # -f so a stale local tag from a prior failed run is re-pointed at the
        # released SHA (the ls-remote guard above already prevents re-tagging an
        # existing *remote* release, so this only ever fixes a local-only tag).
        git tag -f -a $tag $sha -m "$PackageName $tag" 2>&1 | Out-Null
        git push origin $tag 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to push tag $tag (create manually)"
            return
        }
        Write-Success "Tagged $tag"

        if ($Notes -and $RepoSlug -and (Get-Command gh -ErrorAction SilentlyContinue)) {
            $tmp = [System.IO.Path]::GetTempFileName()
            try {
                [System.IO.File]::WriteAllText($tmp, $Notes, (New-Object System.Text.UTF8Encoding $false))
                $out = gh release create $tag --repo $RepoSlug --title "$PackageName $tag" --notes-file $tmp --target main 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "GitHub Release $tag created"
                } else {
                    Write-Err "GitHub Release $tag failed (tag pushed; create manually)"
                    if ($out) { Write-Host "    $out" -ForegroundColor DarkGray }
                }
            }
            finally {
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Skip "No curated notes for $tag (tag-only, no Release)"
        }
    }
    catch {
        Write-Err "Tag/release step error for $tag : $_"
    }
    finally {
        Pop-Location
    }
}

Write-Header "Repository Manager"
if ($DryRun) { Write-Host "  [DRY RUN MODE]" -ForegroundColor Magenta }
if ($Merge) { Write-Host "  [MERGE MODE ENABLED]" -ForegroundColor Magenta }
if ($Strict) { Write-Host "  [STRICT MODE ENABLED]" -ForegroundColor Magenta }

# Normalize -Packages: allow comma-separated values and mixed forms.
if ($Packages) {
    $Packages = @(
        $Packages |
            ForEach-Object { $_ -split "," } |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
}

$stopOnFailure = ($Merge -and $Strict)
$localStrictVersions = $null
if ($Strict) {
    $localStrictVersions = Get-LocalStrictVersions
}

# Determine which repos to process
$reposToProcess = @()

if ($All) {
    $reposToProcess = Get-ChildItem -Directory $ROOT | Where-Object { Test-Path (Join-Path $_.FullName ".git") }
}
elseif ($Packages) {
    foreach ($pkg in $Packages) {
        $path = Join-Path $ROOT $pkg
        if (Test-Path $path) {
            $reposToProcess += Get-Item $path
        } else {
            Write-Err "Package not found: $pkg"
        }
    }
}

# If no packages selected yet, find defaults
if ($reposToProcess.Count -eq 0) {
    # Default: Process current directory if it's a repo
    $current = Get-Item .
    if (Test-Path (Join-Path $current.FullName ".git")) {
        $reposToProcess += $current
    } else {
        # Fallback to all if not in a repo and no args
        Write-Host "Current directory is not a git repository. Processing ALL repositories..." -ForegroundColor Yellow
        $reposToProcess = Get-ChildItem -Directory $ROOT | Where-Object { Test-Path (Join-Path $_.FullName ".git") }
    }
}

# ------------------------------------------------------------------------------------------------
# Auto-Cascade Dependencies (Robustness Fix)
# If a core package is selected in Strict mode, automatically include its downstream dependents.
# This ensures that version bumps propagate correctly through the ecosystem.
# ------------------------------------------------------------------------------------------------
if ($Strict) {
    # Define the dependency graph (Upstream -> [Downstream1, Downstream2...])
    $dependencyGraph = @{
        "pythontk" = @("uitk", "mayatk", "tentacle")
        "uitk"     = @("mayatk", "tentacle")
        "mayatk"   = @("tentacle")
    }

    $initialNames = @($reposToProcess.Name)
    $cascadeExtras = @()

    foreach ($pkgName in $initialNames) {
        if ($dependencyGraph.ContainsKey($pkgName)) {
            foreach ($downstream in $dependencyGraph[$pkgName]) {
                if ($initialNames -notcontains $downstream -and $cascadeExtras -notcontains $downstream) {
                    $cascadeExtras += $downstream
                }
            }
        }
    }

    if ($cascadeExtras.Count -gt 0) {
        Write-Host "  > Auto-including downstream dependencies: $($cascadeExtras -join ', ')" -ForegroundColor Cyan
        foreach ($extra in $cascadeExtras) {
            $path = Join-Path $ROOT $extra
            if (Test-Path $path) {
                $reposToProcess += Get-Item $path
            }
        }
    }
}

# Always enforce canonical release order if multiple packages are involved.
if ($reposToProcess.Count -gt 1) {
    $ordered = @()
    foreach ($name in $RELEASE_ORDER) {
        $match = $reposToProcess | Where-Object { $_.Name -eq $name }
        if ($match) {
            $ordered += $match
        }
    }
    $remaining = $reposToProcess | Where-Object { $RELEASE_ORDER -notcontains $_.Name }
    $reposToProcess = @($ordered + $remaining)
}

$results = @{}
$anyErrors = $false

foreach ($repo in $reposToProcess) {
    $pkgName = $repo.Name
    Write-Host ""
    Write-Host "Processing $pkgName..." -ForegroundColor Cyan
    
    $repoPath = $repo.FullName
    $isStrictPackage = $STRICT_PACKAGES -contains $pkgName
    $capturedNotes = ""   # curated CHANGELOG notes for this release's tag/Release

    # 0. Repo Safety Preflight
    if (-not (Test-RepoOperationSafe $repoPath)) {
        $results[$pkgName] = "unsafe-repo"
        $anyErrors = $true
        Write-Err "Repository is not in a safe state for automation"
        if ($stopOnFailure) { break }
        continue
    }

    # Additional safety: remote refs must not contain conflict markers in critical files.
    if ($Strict -and $isStrictPackage) {
        $remoteSafe = (Test-RemoteConflictMarkers -RepoPath $repoPath -Ref "origin/main") -and
                      (Test-RemoteConflictMarkers -RepoPath $repoPath -Ref "origin/dev")
        if (-not $remoteSafe) {
            $results[$pkgName] = "unsafe-repo"
            $anyErrors = $true
            Write-Err "Repository is not in a safe state for automation"
            if ($stopOnFailure) { break }
            continue
        }
    }
    
    # 1. Strict Validation (Build & Test)
    if ($Strict -and $isStrictPackage) {
        # Sync local dev with origin BEFORE auto-bumping. Without this, a bump
        # computed against a stale local __init__.py can land below origin's
        # current version, producing an unrebasable conflict on push.
        if ($Merge -and -not $DryRun) {
            $syncOk = Sync-DevWithOrigin $repoPath -CommitMessage $CommitMessage
            if (-not $syncOk) {
                $results[$pkgName] = "sync-failed"
                $anyErrors = $true
                Write-Err "Pre-bump sync failed"
                if ($stopOnFailure) { break }
                continue
            }
        }

        # Auto-Bump Logic: If code has changed, increment patch version to force downstream updates.
        if ($Merge) {
            $shouldBump = $false
            Push-Location $repoPath
            try {
                 $st = git status --porcelain
                 if ($st) { $shouldBump = $true }
                 else {
                     # If we have commits ahead of origin/dev, we consider those "new features" requiring a bump.
                     git fetch origin dev --quiet 2>&1 | Out-Null
                     $ahead = git rev-list --count origin/dev..dev 2>$null
                     if ($ahead -and [int]$ahead -gt 0) { 
                        # Check if the last commit was already a bump to avoid loops/double bumps
                        $lastMsg = git log -1 --pretty=%s
                        if ($lastMsg -notmatch "^Bump version to") {
                             $shouldBump = $true 
                        }
                     }
                 }
            } finally { Pop-Location }
    
            if ($shouldBump) {
                 if ($DryRun) {
                     Write-Step "[DryRun] Would bump patch version of $pkgName (code changes detected)"
                     # Mock the new version so downstream sync checks pass
                     if ($localStrictVersions.ContainsKey($pkgName)) {
                        $curr = $localStrictVersions[$pkgName]
                        try {
                            $parts = $curr -split "\."
                            $nextPatch = [int]$parts[-1] + 1
                            $mockVer = "$($parts[0]).$($parts[1]).$nextPatch"
                            $localStrictVersions[$pkgName] = $mockVer
                        } catch {}
                     }
                 } else {
                     $newVer = Bump-LocalVersion $repoPath
                     if ($newVer) {
                         Write-Host "    [Auto-Bump] Updated to $newVer" -ForegroundColor Cyan
                         $localStrictVersions[$pkgName] = $newVer
                         
                         Push-Location $repoPath
                         try {
                            git add .
                            git commit -m "Bump version to $newVer [skip ci]" | Out-Null
                         }
                         finally { Pop-Location }
                     }
                 }
            }
        
            # Keep internal pins consistent with what we're releasing, so pip installs are reliable.
            $syncOk = Sync-PyProjectDepsToLocalVersions $pkgName $repoPath $localStrictVersions
            if (-not $syncOk) {
                $results[$pkgName] = "requirements-invalid"
                $anyErrors = $true
                Write-Err "Dependency sync failed"
                if ($stopOnFailure) { break }
                continue
            }

            # Optional: ensure pinned upstream versions are already available on PyPI.
            # This prevents merging downstream pins that would temporarily be un-installable.
            if (-not $SkipPypiCheck -and $pkgName -ne "pythontk") {
                $requiredPinsByPackage = @{
                    "uitk"      = @("pythontk")
                    "mayatk"    = @("pythontk", "uitk")
                    "blendertk" = @("pythontk")
                    "tentacle"  = @("pythontk", "uitk", "mayatk")
                }

                if ($requiredPinsByPackage.ContainsKey($pkgName)) {
                    foreach ($dep in $requiredPinsByPackage[$pkgName]) {
                        if ($localStrictVersions.ContainsKey($dep)) {
                            $depVer = $localStrictVersions[$dep]
                            $pypiName = Get-PypiProjectName $dep
                            $ok = Test-PypiHasVersion $pypiName $depVer
                            if (-not $ok) {
                                $results[$pkgName] = "pypi-missing"
                                $anyErrors = $true
                                Write-Err "PyPI does not show $pypiName==$depVer yet (or cannot be reached)."
                                Write-Err "Use -SkipPypiCheck to override, but this can break installs."
                                if ($stopOnFailure) { break }
                            }
                        }
                    }
                    if ($results[$pkgName] -eq "pypi-missing") {
                        if ($stopOnFailure) { break }
                        continue
                    }
                }
            }

            # Capture this release's CHANGELOG additions (lines new on dev vs the
            # last-released main) for the git tag + GitHub Release. No file edit —
            # the existing dated-prose CHANGELOG is the source as-is. An empty
            # delta (docstring-only / dependency bump) -> tag-only release.
            if ($isStrictPackage -and -not $DryRun) {
                $capturedNotes = Get-ChangelogDelta $repoPath
                if ($capturedNotes) {
                    Write-Step "Captured CHANGELOG delta for release notes"
                } else {
                    Write-Skip "No CHANGELOG additions this release (tag-only)"
                }
            } elseif ($isStrictPackage -and $DryRun) {
                Write-Step "[DryRun] Would capture CHANGELOG delta for release notes"
            }
        }
        if (-not $DryRun -and -not $SkipBuild) {
            # Known transient: `[Errno 13] Permission denied` with no path.
            # Repo lives under o:\Cloud\... (sync-managed) — likely a sync
            # agent or AV briefly holding a file in dist/ or build/ during
            # cleanup. Re-running usually succeeds; -SkipBuild is the
            # operator escape hatch. Before adding retry/temp-build logic,
            # capture the FULL stderr on next occurrence (the path in the
            # Permission denied message tells you whether it's dist/,
            # build/, .egg-info, or something else) — until we have that,
            # we don't know what to retry or where to relocate.
            $buildOk = Test-Build $pkgName $repoPath
            if (-not $buildOk) {
                $results[$pkgName] = "build-failed"
                $anyErrors = $true
                Write-Err "Build failed - skipping push/merge"
                if ($stopOnFailure) { break }
                continue
            }
        } elseif ($SkipBuild) {
            Write-Skip "Build validation skipped"
        } else {
            Write-Step "[DryRun] Would validate build"
        }
    } elseif ($Strict) {
        Write-Skip "Strict mode not supported for $pkgName (skipping build check)"
    }

    # 2. Check for Changes
    $hasChanges = Test-HasChanges $repoPath
    
    # Check if we need to merge (Dev ahead of Main)
    $needsMerge = $false
    if ($Merge) {
        Push-Location $repoPath
        try {
            $devExists = git branch --list dev
            $mainExists = git branch --list main
            if ($devExists -and $mainExists) {
                $aheadCount = (git rev-list --count "main..dev" 2>$null)
                if ($aheadCount -gt 0) {
                    if ($Strict -and $isStrictPackage -and (Test-OnlyDevBumpChanges $repoPath $pkgName)) {
                        Write-Skip "Dev is ahead only due to dev bump (skipping merge)"
                        $needsMerge = $false
                    } else {
                        $needsMerge = $true
                    }
                }
            }
        }
        finally {
            Pop-Location
        }
    }

    if (-not $hasChanges -and -not $needsMerge) {
        Write-Skip "No changes to push and fully merged"
        $results[$pkgName] = "skipped"
        continue
    } else {
        if ($hasChanges) {
            Write-Host "  Has changes to push" -ForegroundColor White
        }
        if ($needsMerge) {
            Write-Host "  Dev is ahead of Main (Needs Merge)" -ForegroundColor White
        }
    }

    # 3. Push Dev
    if ($hasChanges) {
        if ($DryRun) {
            Write-Step "[DryRun] Would push dev branch"
        } else {
            $pushOk = Push-DevBranch $repoPath
            if (-not $pushOk) {
                $results[$pkgName] = "push-failed"
                $anyErrors = $true
                Write-Err "Push failed - skipping merge"
                if ($stopOnFailure) { break }
                continue
            }
        }
    }

    # 4. Merge to Main
    # Gate on $needsMerge (not just $Merge): step 2 sets it $false only when dev
    # is ahead of main ONLY by a pure version-string bump (Test-OnlyDevBumpChanges,
    # now narrowed to <pkg>/__init__.py alone) — there is nothing to release.
    # Without this guard the "skipping merge" message was a no-op: step 4 merged
    # that bump to main anyway, tripping publish.yml into a *phantom publish*
    # (e.g. pythontk 0.8.77 shipped to PyPI on a re-run with no real changes,
    # then mis-tagged because $localStrictVersions still held the old version).
    # A dependency-cascade release changes pyproject.toml too, so it is NOT
    # version-only -> $needsMerge stays $true -> it still merges and propagates.
    if ($Merge -and $needsMerge) {
        # Check for conflicts first
        $conflictsOk = Test-MergeConflicts $repoPath
        if (-not $conflictsOk) {
             $results[$pkgName] = "merge-conflict"
             $anyErrors = $true
             Write-Err "Merge conflicts detected - skipping merge"
               if ($stopOnFailure) { break }
               continue
        }

        if ($DryRun) {
            Write-Step "[DryRun] Would merge to main and push"
        } else {
            $mergeOk = $null
            if ($UsePR) {
                $mergeOk = Merge-ToMainViaPR $repoPath $pkgName
            } else {
                $mergeOk = Merge-ToMain $repoPath
            }
            if (-not $mergeOk) {
                $results[$pkgName] = "merge-failed"
                $anyErrors = $true
                Write-Err "Merge failed"
                if ($stopOnFailure) { break }
                continue
            }
            
            # 5. Wait for Workflow (only if Strict/Core package)
            if ($isStrictPackage) {
                if (-not $SkipWorkflowWait) {
                    $workflowOk = Wait-ForWorkflow $repoPath $pkgName
                    if (-not $workflowOk) {
                        $results[$pkgName] = "workflow-failed"
                        $anyErrors = $true
                        Write-Err "Workflow failed or timed out - aborting remaining packages"
                        break
                    }
                } else {
                    Write-Skip "Workflow wait skipped"
                }

                # Published OK (or wait skipped). Tag this version and cut a
                # GitHub Release when there are curated notes. Non-fatal.
                New-GitReleaseTag $repoPath (Get-GitHubRepoSlug $repoPath) $pkgName $localStrictVersions[$pkgName] $capturedNotes
            }
        }
    }
    
    $results[$pkgName] = "success"
}

# Summary
Write-Header "Summary"

foreach ($repo in $reposToProcess) {
    $pkg = $repo.Name
    $status = $results[$pkg]
    switch ($status) {
        "success" { Write-Success "$pkg - Completed" }
        "skipped" { Write-Skip "$pkg - No changes" }
        "requirements-invalid" { Write-Err "$pkg - requirements.txt invalid/out of sync" }
        "build-failed" { Write-Err "$pkg - Build failed" }
        "push-failed" { Write-Err "$pkg - Push failed" }
        "merge-failed" { Write-Err "$pkg - Merge failed" }
        "merge-conflict" { Write-Err "$pkg - Merge conflicts" }
        "workflow-failed" { Write-Err "$pkg - Workflow failed/timed out" }
        "unsafe-repo" { Write-Err "$pkg - Unsafe repo state" }
        "pypi-missing" { Write-Err "$pkg - Upstream version not on PyPI" }
        "sync-failed" { Write-Err "$pkg - Pre-bump sync with origin failed" }
        default { 
            if ($DryRun) { Write-Host "  o $pkg - Dry Run OK" -ForegroundColor Cyan }
            else { Write-Host "  ? $pkg - Not processed" -ForegroundColor DarkGray }
        }
    }
}

if ($anyErrors) {
    exit 1
}
