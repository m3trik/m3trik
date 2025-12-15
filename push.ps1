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
    [string]$Root = "O:\Cloud\Code\_scripts"
)

$ErrorActionPreference = "Continue"
$ROOT = $Root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
. (Join-Path $SCRIPT_DIR "common.ps1")

# Packages that support strict validation
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

function Get-LocalStrictVersions {
    $versions = @{}
    foreach ($pkg in $STRICT_PACKAGES) {
        $pkgPath = Join-Path (Join-Path $ROOT $pkg) $pkg
        $ver = Get-PackageVersion $pkgPath
        if ($ver -and $ver -ne "unknown") {
            $versions[$pkg] = $ver
        }
    }
    return $versions
}

function Sync-InternalRequirementsToLocalVersions {
    param(
        [string]$PackageName,
        [string]$RepoPath,
        [hashtable]$LocalVersions
    )

    $reqFile = Join-Path $RepoPath "requirements.txt"
    if (-not (Test-Path $reqFile)) {
        return $true
    }

    # Only these packages have internal pins today.
    $requiredPinsByPackage = @{
        "uitk"      = @("pythontk")
        "mayatk"    = @("pythontk", "uitk")
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
            Write-Err "Checkout dev failed (requirements sync)"
            return $false
        }
    }
    finally {
        Pop-Location
    }

    $lines = Get-Content $reqFile
    $changed = $false

    foreach ($dep in $requiredPins) {
        if (-not $LocalVersions.ContainsKey($dep)) {
            Write-Err "Cannot sync requirements: missing local version for '$dep'"
            return $false
        }
        $expected = "$dep==$($LocalVersions[$dep])"

        $found = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^$dep==") {
                $found = $true
                if ($lines[$i] -ne $expected) {
                    $lines[$i] = $expected
                    $changed = $true
                }
            }
        }

        if (-not $found) {
            Write-Err "requirements.txt is missing expected pinned dep: '$dep==...'."
            return $false
        }
    }

    if (-not $changed) {
        return $true
    }

    Set-Content -Path $reqFile -Value $lines

    Push-Location $RepoPath
    try {
        git add requirements.txt
        git commit -m "Update requirements.txt [skip ci]" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to commit requirements.txt updates"
            return $false
        }
        Write-Success "Synced requirements.txt pins"
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

    $allowed = @(
        "pyproject.toml",
        "README.md",
        "docs/README.md",
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
        if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
        if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
        $eggInfo = "$PackageName.egg-info"
        if (Test-Path $eggInfo) { Remove-Item -Recurse -Force $eggInfo }
        
        $oldErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        
        # Run build with timeout (60 seconds)
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
        $buildCode = $buildOutput | Select-String -Pattern "error|ERROR|failed|FAILED" -Quiet
        
        if ($buildCode) {
            $ErrorActionPreference = $oldErrorAction
            Write-Err "Build failed!"
            Write-Host "    $($buildOutput | Select-String -Pattern 'error|ERROR|failed|FAILED' | Select-Object -First 1)" -ForegroundColor DarkGray
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
        $twineCode = $twineOutput | Select-String -Pattern "error|ERROR|failed|FAILED|warning|WARNING" -Quiet
        
        $ErrorActionPreference = $oldErrorAction
        
        if ($twineCode) {
            Write-Err "Twine validation failed!"
            Write-Host "    $($twineOutput | Select-String -Pattern 'error|ERROR|failed|FAILED|warning|WARNING' | Select-Object -First 1)" -ForegroundColor DarkGray
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

# Enforce canonical release order for strict packages when merging.
if ($Merge -and $Strict -and $reposToProcess.Count -gt 1) {
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
else {
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

$results = @{}
$anyErrors = $false

foreach ($repo in $reposToProcess) {
    $pkgName = $repo.Name
    Write-Host ""
    Write-Host "Processing $pkgName..." -ForegroundColor Cyan
    
    $repoPath = $repo.FullName
    $isStrictPackage = $STRICT_PACKAGES -contains $pkgName

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
        $remoteMainOk = Test-RemoteConflictMarkers $repoPath "origin/main" @("requirements.txt")
        if (-not $remoteMainOk) {
            $results[$pkgName] = "unsafe-repo"
            $anyErrors = $true
            Write-Err "Remote main contains conflict markers"
            if ($stopOnFailure) { break }
            continue
        }
        $remoteDevOk = Test-RemoteConflictMarkers $repoPath "origin/dev" @("requirements.txt")
        if (-not $remoteDevOk) {
            $results[$pkgName] = "unsafe-repo"
            $anyErrors = $true
            Write-Err "Remote dev contains conflict markers"
            if ($stopOnFailure) { break }
            continue
        }
    }
    
    # 1. Strict Validation (Build & Test)
    if ($Strict -and $isStrictPackage) {
        if ($Merge -and -not $DryRun) {
            # Keep internal pins consistent with what we're releasing, so pip installs are reliable.
            $syncOk = Sync-InternalRequirementsToLocalVersions $pkgName $repoPath $localStrictVersions
            if (-not $syncOk) {
                $results[$pkgName] = "requirements-invalid"
                $anyErrors = $true
                Write-Err "Requirements sync failed"
                if ($stopOnFailure) { break }
                continue
            }

            # Optional: ensure pinned upstream versions are already available on PyPI.
            # This prevents merging downstream pins that would temporarily be un-installable.
            if (-not $SkipPypiCheck -and $pkgName -ne "pythontk") {
                $requiredPinsByPackage = @{
                    "uitk"      = @("pythontk")
                    "mayatk"    = @("pythontk", "uitk")
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
        }
        if (-not $DryRun -and -not $SkipBuild) {
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
    if ($Merge) {
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
        default { 
            if ($DryRun) { Write-Host "  o $pkg - Dry Run OK" -ForegroundColor Cyan }
            else { Write-Host "  ? $pkg - Not processed" -ForegroundColor DarkGray }
        }
    }
}

if ($anyErrors) {
    exit 1
}
