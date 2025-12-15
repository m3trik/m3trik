param(
    [switch]$All,
    [string[]]$Packages,
    [switch]$Merge,
    [switch]$Strict,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$ROOT = "O:\Cloud\Code\_scripts"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
. (Join-Path $SCRIPT_DIR "common.ps1")

# Packages that support strict validation
$STRICT_PACKAGES = @("pythontk", "uitk", "mayatk", "tentacle")

Write-Header "Repository Manager"
if ($DryRun) { Write-Host "  [DRY RUN MODE]" -ForegroundColor Magenta }
if ($Merge) { Write-Host "  [MERGE MODE ENABLED]" -ForegroundColor Magenta }
if ($Strict) { Write-Host "  [STRICT MODE ENABLED]" -ForegroundColor Magenta }

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
else {
    # Default: Process current directory if it's a repo
    $current = Get-Item .
    if (Test-Path (Join-Path $current.FullName ".git")) {
        $reposToProcess += $current
    } else {
        Write-Host "Current directory is not a git repository." -ForegroundColor Yellow
        Write-Host "Use -All to process all repositories or -Packages <name> to specify one." -ForegroundColor Yellow
        exit
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
    
    # 1. Strict Validation (Build & Test)
    if ($Strict -and $isStrictPackage) {
        if (-not $DryRun) {
            $buildOk = Test-Build $pkgName $repoPath
            if (-not $buildOk) {
                $results[$pkgName] = "build-failed"
                $anyErrors = $true
                Write-Err "Build failed - skipping push/merge"
                continue
            }
        } else {
            Write-Step "[DryRun] Would validate build"
        }
    } elseif ($Strict) {
        Write-Skip "Strict mode not supported for $pkgName (skipping build check)"
    }

    # 2. Check for Changes
    $hasChanges = Test-HasChanges $repoPath
    
    if (-not $hasChanges) {
        Write-Skip "No changes to push"
        if (-not $Merge) {
            $results[$pkgName] = "skipped"
            continue
        }
    } else {
        Write-Host "  Has changes to push" -ForegroundColor White
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
                continue
            }
        }
    }

    # 4. Merge to Main
    if ($Merge) {
        # Check for conflicts first
        if ($Strict -and $isStrictPackage) {
             $mergeTestOk = Test-MergeConflicts $repoPath
             if (-not $mergeTestOk) {
                 $results[$pkgName] = "merge-conflict"
                 $anyErrors = $true
                 Write-Err "Merge conflicts detected - skipping merge"
                 continue
             }
        }

        if ($DryRun) {
            Write-Step "[DryRun] Would merge to main"
        } else {
            $mergeOk = Merge-ToMain $repoPath
            if (-not $mergeOk) {
                $results[$pkgName] = "merge-failed"
                $anyErrors = $true
                Write-Err "Merge failed"
                continue
            }
            
            # 5. Wait for Workflow (Strict only)
            if ($Strict -and $isStrictPackage) {
                Wait-ForWorkflow $repoPath $pkgName
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
        "build-failed" { Write-Err "$pkg - Build failed" }
        "push-failed" { Write-Err "$pkg - Push failed" }
        "merge-failed" { Write-Err "$pkg - Merge failed" }
        "merge-conflict" { Write-Err "$pkg - Merge conflicts" }
        default { 
            if ($DryRun) { Write-Host "  o $pkg - Dry Run OK" -ForegroundColor Cyan }
            else { Write-Host "  ? $pkg - Unknown status" -ForegroundColor DarkGray }
        }
    }
}

if ($anyErrors) {
    exit 1
}
