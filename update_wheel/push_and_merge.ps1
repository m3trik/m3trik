param(
    [switch]$DryRun,
    [switch]$SkipBuild,
    [ValidateSet("pythontk", "uitk", "mayatk", "tentacle", "")]
    [string]$Package = ""
)

$ErrorActionPreference = "Stop"
$ROOT = "O:\Cloud\Code\_scripts"
$PACKAGES = @("pythontk", "uitk", "mayatk", "tentacle")

if ($Package) {
    $PACKAGES = @($Package)
}

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Text)
    Write-Host "  -> $Text" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Text)
    Write-Host "  OK $Text" -ForegroundColor Green
}

function Write-Skip {
    param([string]$Text)
    Write-Host "  -- $Text" -ForegroundColor DarkGray
}

function Write-Err {
    param([string]$Text)
    Write-Host "  !! $Text" -ForegroundColor Red
}

function Get-PackageVersion {
    param([string]$PackagePath)
    $initFile = Join-Path $PackagePath "__init__.py"
    if (Test-Path $initFile) {
        $content = Get-Content $initFile -Raw
        if ($content -match '__version__\s*=\s*"(\d+\.\d+\.\d+)"') {
            return $Matches[1]
        }
    }
    return "unknown"
}

function Test-HasChanges {
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        $status = git status --porcelain 2>$null
        $hasUncommitted = $status.Length -gt 0
        
        $ahead = git rev-list --count "origin/dev..dev" 2>$null
        if ($LASTEXITCODE -ne 0) { $ahead = 0 }
        
        $aheadOfMain = git rev-list --count "main..dev" 2>$null
        if ($LASTEXITCODE -ne 0) { $aheadOfMain = 0 }
        
        return ($hasUncommitted -or ($ahead -gt 0) -or ($aheadOfMain -gt 0))
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

function Push-DevBranch {
    param([string]$RepoPath)
    
    Push-Location $RepoPath
    try {
        # Check if local is behind remote
        git fetch origin dev --quiet 2>&1
        $behind = git rev-list HEAD..origin/dev --count 2>&1
        if ($behind -gt 0) {
            Write-Step "Pulling latest dev (behind by $behind commits)..."
            git pull origin dev --quiet 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Pull failed"
                return $false
            }
        }
        
        $status = git status --porcelain
        if ($status) {
            Write-Step "Staging uncommitted changes..."
            git add -A
            git commit -m "Prepare for publish"
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Commit failed"
                return $false
            }
        }
        
        Write-Step "Pushing dev branch..."
        git push origin dev
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Push failed"
            return $false
        }
        Write-Success "Pushed dev branch"
        return $true
    }
    finally {
        Pop-Location
    }
}

function Test-MergeConflicts {
    param([string]$RepoPath)
    
    Push-Location $RepoPath
    try {
        Write-Step "Testing merge compatibility..."
        
        $oldErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        
        # Fetch latest to ensure we're testing against current remote state
        git fetch origin main *>&1 | Out-Null
        git fetch origin dev *>&1 | Out-Null
        
        # Use git merge-tree for virtual merge (no working directory changes)
        git merge-tree origin/main origin/dev *>&1 | Out-Null
        $mergeStatus = $LASTEXITCODE
        
        $ErrorActionPreference = $oldErrorAction
        
        if ($mergeStatus -ne 0) {
            Write-Err "Merge conflicts detected!"
            return $false
        }
        
        Write-Success "No merge conflicts"
        return $true
    }
    finally {
        Pop-Location
    }
}

function Merge-ToMain {
    param([string]$RepoPath)
    
    Push-Location $RepoPath
    try {
        Write-Step "Checking out main..."
        git checkout main
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Checkout main failed"
            return $false
        }
        
        Write-Step "Pulling latest main..."
        git pull origin main
        
        Write-Step "Merging dev into main..."
        git merge dev --no-edit
        
        # Handle merge conflicts automatically
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    Resolving conflicts..." -ForegroundColor Yellow
            
            # Accept dev version for workflows and __init__.py (suppress stderr)
            $ErrorActionPreference = "SilentlyContinue"
            git checkout --theirs ".github/workflows/*.yml" *>&1 | Out-Null
            git checkout --theirs "*/__init__.py" *>&1 | Out-Null
            $ErrorActionPreference = "Continue"
            
            git add -A
            git commit --no-edit
            
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Merge failed - could not auto-resolve conflicts"
                return $false
            }
        }
        
        Write-Step "Pushing main (triggers GitHub Actions)..."
        git push origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Push main failed"
            return $false
        }
        
        Write-Step "Switching back to dev..."
        git checkout dev
        
        Write-Success "Merged and pushed to main"
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
    
    # Wait for workflow to start and complete (max 5 minutes)
    $maxWait = 300
    $elapsed = 0
    $checkInterval = 10
    
    Start-Sleep -Seconds 15  # Initial delay for workflow to start
    
    # Get initial main commit before workflow runs
    $initialCommit = $null
    try {
        Push-Location $RepoPath
        git fetch origin main --quiet 2>&1 | Out-Null
        $initialCommit = (git rev-parse origin/main 2>&1).Trim()
        Pop-Location
    }
    catch {
        Pop-Location
        Write-Host "    Warning: Cannot get initial commit - $($_.Exception.Message)" -ForegroundColor Yellow
        return $true  # Don't fail the whole process, continue
    }
    
    if (-not $initialCommit) {
        Write-Host "    Warning: No initial commit found, skipping workflow wait" -ForegroundColor Yellow
        return $true  # Don't fail the whole process
    }
    
    while ($elapsed -lt $maxWait) {
        Start-Sleep -Seconds $checkInterval
        $elapsed += $checkInterval
        
        $currentCommit = $null
        try {
            Push-Location $RepoPath
            git fetch origin main --quiet 2>&1 | Out-Null
            $currentCommit = (git rev-parse origin/main 2>&1).Trim()
            Pop-Location
            
            if ($currentCommit -and $currentCommit -ne $initialCommit) {
                Write-Host "    Workflow completed (new commit detected)" -ForegroundColor Green
                # Switch to main and pull the updates
                try {
                    Push-Location $RepoPath
                    git checkout main --quiet 2>&1 | Out-Null
                    git pull origin main --quiet 2>&1 | Out-Null
                    git checkout dev --quiet 2>&1 | Out-Null
                    Pop-Location
                }
                catch {
                    Pop-Location
                }
                return $true
            }
            
            if ($elapsed % 30 -eq 0) {
                Write-Host "    Waiting... ($elapsed/$maxWait seconds)" -ForegroundColor Gray
            }
        }
        catch {
            if ((Get-Location).Path -eq $RepoPath) {
                Pop-Location
            }
            Write-Host "    Warning: Check failed - $($_.Exception.Message)" -ForegroundColor DarkGray
            continue
        }
    }
    
    # Timeout reached - check one more time
    Write-Host "    Timeout reached, final check..." -ForegroundColor DarkGray
    try {
        Push-Location $RepoPath
        git fetch origin main --quiet 2>&1 | Out-Null
        $finalCommit = (git rev-parse origin/main 2>&1).Trim()
        Pop-Location
        
        if ($finalCommit -and $finalCommit -ne $initialCommit) {
            Write-Host "    Workflow completed (detected after timeout)" -ForegroundColor Green
            try {
                Push-Location $RepoPath
                git checkout main --quiet 2>&1 | Out-Null
                git pull origin main --quiet 2>&1 | Out-Null
                git checkout dev --quiet 2>&1 | Out-Null
                Pop-Location
            }
            catch {
                if ((Get-Location).Path -eq $RepoPath) {
                    Pop-Location
                }
            }
            return $true
        }
    }
    catch {
        if ((Get-Location).Path -eq $RepoPath) {
            Pop-Location
        }
    }
    
    Write-Host "    Warning: Timeout waiting for workflow (${maxWait}s)" -ForegroundColor Yellow
    Write-Host "    Continuing anyway - check GitHub Actions manually" -ForegroundColor DarkGray
    return $true  # Don't fail - let the process continue
}

# Main Script
Write-Header "Package Push and Merge Script"
if ($DryRun) {
    Write-Host "  [DRY RUN MODE - No changes will be made]" -ForegroundColor Magenta
}

$results = @{}
$anyErrors = $false

foreach ($pkg in $PACKAGES) {
    $repoPath = Join-Path $ROOT $pkg
    $pkgPath = Join-Path $repoPath $pkg
    
    if (-not (Test-Path $repoPath)) {
        Write-Err "Repository not found: $repoPath"
        continue
    }
    
    Write-Header $pkg
    
    $version = Get-PackageVersion $pkgPath
    Write-Host "  Version: $version" -ForegroundColor White
    
    $hasChanges = Test-HasChanges $repoPath
    if (-not $hasChanges) {
        Write-Skip "No changes to push"
        $results[$pkg] = "skipped"
        continue
    }
    
    Write-Host "  Has changes to push" -ForegroundColor White
    
    if (-not $SkipBuild) {
        $buildOk = Test-Build $pkg $repoPath
        if (-not $buildOk) {
            $results[$pkg] = "build-failed"
            $anyErrors = $true
            Write-Err "Build failed - aborting remaining packages"
            break
        }
    }
    
    # Test for merge conflicts before pushing
    Write-Step "Checking for merge conflicts..."
    $mergeTestOk = Test-MergeConflicts $repoPath
    if (-not $mergeTestOk) {
        # Check if conflicts are only in auto-resolvable files
        Push-Location $repoPath
        try {
            git fetch origin main --quiet
            git fetch origin dev --quiet
            
            # Do a test merge to see what would conflict
            $testMerge = git merge-tree (git merge-base origin/main origin/dev) origin/main origin/dev 2>&1
            
            # Check if conflicts are only in expected files
            $hasUnexpectedConflicts = $false
            if ($testMerge -match "<<<<<<< ") {
                $conflictFiles = $testMerge | Select-String -Pattern "^\+\+\+ b/(.+)$" | ForEach-Object { $_.Matches.Groups[1].Value }
                
                foreach ($file in $conflictFiles) {
                    if ($file -notmatch "\.github/workflows/.*\.yml$" -and $file -notmatch "/__init__\.py$" -and $file -notmatch "/requirements\.txt$") {
                        $hasUnexpectedConflicts = $true
                        Write-Err "Unexpected merge conflict in: $file"
                    }
                }
            }
            
            if ($hasUnexpectedConflicts) {
                $results[$pkg] = "merge-conflict"
                $anyErrors = $true
                Write-Err "Unexpected merge conflicts - aborting remaining packages"
                Pop-Location
                break
            }
            else {
                Write-Success "Conflicts are auto-resolvable"
            }
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Success "No merge conflicts"
    }
    
    if ($DryRun) {
        Write-Success "[DRY RUN] Would push dev, merge to main, trigger publish"
        $results[$pkg] = "dry-run-ok"
        continue
    }
    
    $pushOk = Push-DevBranch $repoPath
    if (-not $pushOk) {
        $results[$pkg] = "push-failed"
        $anyErrors = $true
        Write-Err "Push failed - aborting remaining packages"
        break
    }
    
    $mergeOk = Merge-ToMain $repoPath
    if (-not $mergeOk) {
        $results[$pkg] = "merge-failed"
        $anyErrors = $true
        Write-Err "Merge failed - aborting remaining packages"
        break
    }
    
    # Wait for GitHub Actions workflow to complete before proceeding to next package
    if (-not $DryRun) {
        $workflowOk = Wait-ForWorkflow $repoPath $pkg
        if (-not $workflowOk) {
            Write-Host "  ! Warning: Workflow may not have completed" -ForegroundColor Yellow
        }
    }
    
    $results[$pkg] = "success"
}

# Summary
Write-Header "Summary"

foreach ($pkg in $PACKAGES) {
    $status = $results[$pkg]
    switch ($status) {
        "success" { Write-Success "$pkg - Published" }
        "skipped" { Write-Skip "$pkg - No changes" }
        "dry-run-ok" { Write-Host "  o $pkg - Ready to publish" -ForegroundColor Cyan }
        "build-failed" { Write-Err "$pkg - Build failed" }
        "push-failed" { Write-Err "$pkg - Push failed" }
        "merge-failed" { Write-Err "$pkg - Merge failed" }
        "merge-conflict" { Write-Err "$pkg - Merge conflicts detected" }
        default { Write-Host "  ? $pkg - Not processed" -ForegroundColor DarkGray }
    }
}

Write-Host ""

if ($anyErrors) {
    Write-Host "Some packages failed. Check errors above." -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host "Dry run complete. Run without -DryRun to publish." -ForegroundColor Cyan
}
else {
    Write-Host "All packages pushed and merged successfully!" -ForegroundColor Green
    Write-Host "GitHub Actions workflows have completed." -ForegroundColor Gray
    
    # Pull updated dev branches that were bumped by workflows
    Write-Host ""
    Write-Header "Updating Local Dev Branches"
    
    foreach ($pkg in $PACKAGES) {
        if ($results[$pkg] -eq "success") {
            $repoPath = Join-Path $ROOT $pkg
            Push-Location $repoPath
            try {
                Write-Host "  -> Pulling $pkg dev..." -ForegroundColor Cyan
                git checkout dev --quiet
                git pull origin dev --quiet
                if ($LASTEXITCODE -eq 0) {
                    $pkgPath = Join-Path $repoPath $pkg
                    $newVersion = Get-PackageVersion $pkgPath
                    Write-Success "$pkg updated to $newVersion"
                }
                else {
                    Write-Host "  ! Warning: Failed to pull $pkg dev" -ForegroundColor Yellow
                }
            }
            finally {
                Pop-Location
            }
        }
    }
    
    Write-Host ""
    Write-Host "All dev branches updated!" -ForegroundColor Green
}
