$ErrorActionPreference = "Stop"

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

function Test-RepoOperationSafe {
    param(
        [string]$RepoPath,
        [string[]]$FilesToScanForConflictMarkers = @("requirements.txt")
    )

    Push-Location $RepoPath
    try {
        # Abort if a merge/rebase/cherry-pick is in progress.
        $gitDir = (git rev-parse --git-dir 2>$null)
        if (-not $gitDir) {
            Write-Err "Not a git repository"
            return $false
        }

        if (Test-Path (Join-Path $gitDir "MERGE_HEAD")) {
            Write-Err "Merge in progress (MERGE_HEAD present)"
            return $false
        }
        if (Test-Path (Join-Path $gitDir "REBASE_HEAD")) {
            Write-Err "Rebase in progress (REBASE_HEAD present)"
            return $false
        }
        if (Test-Path (Join-Path $gitDir "rebase-apply")) {
            Write-Err "Rebase in progress (rebase-apply present)"
            return $false
        }
        if (Test-Path (Join-Path $gitDir "rebase-merge")) {
            Write-Err "Rebase in progress (rebase-merge present)"
            return $false
        }
        if (Test-Path (Join-Path $gitDir "CHERRY_PICK_HEAD")) {
            Write-Err "Cherry-pick in progress (CHERRY_PICK_HEAD present)"
            return $false
        }

        foreach ($rel in $FilesToScanForConflictMarkers) {
            $p = Join-Path $RepoPath $rel
            if (Test-Path $p) {
                $raw = Get-Content $p -Raw -ErrorAction SilentlyContinue
                if ($raw -match "(?m)^<<<<<<< ") {
                    Write-Err "Conflict markers found in $rel"
                    return $false
                }
            }
        }

        return $true
    }
    finally {
        Pop-Location
    }
}

function Test-RemoteConflictMarkers {
    param(
        [string]$RepoPath,
        [string]$Ref,
        [string[]]$FilesToScan = @("requirements.txt")
    )

    Push-Location $RepoPath
    try {
        git fetch origin --quiet 2>&1 | Out-Null
        foreach ($rel in $FilesToScan) {
            $spec = "$($Ref):$rel"
            
            # Check if file exists in the tree first to avoid errors
            $treeEntry = (git ls-tree $Ref $rel 2>$null)
            if (-not $treeEntry) { continue }

            $content = (git show $spec 2>&1)
            if ($content -and ($content -match "(?m)^<<<<<<< ")) {
                Write-Err "Conflict markers found in $spec"
                return $false
            }
        }
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
        
        # Use git merge-tree for a virtual merge (no working directory changes)
        # Note: merge-tree often returns exit code 0 even when conflicts exist,
        # so we must inspect its output.
        $base = git merge-base origin/main origin/dev
        if ($LASTEXITCODE -ne 0) {
            $ErrorActionPreference = $oldErrorAction
            Write-Err "Cannot compute merge-base for origin/main and origin/dev"
            return $false
        }

        $mergeText = git merge-tree $base origin/main origin/dev 2>&1
        $hasConflicts = $false
        if ($mergeText -match "<<<<<<< ") {
            $hasConflicts = $true
        }
        
        $ErrorActionPreference = $oldErrorAction

        if ($hasConflicts) {
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

function Test-HasChanges {
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        # 1. Check for uncommitted changes
        $status = git status --porcelain 2>&1
        $hasUncommitted = $status.Length -gt 0
        
        # 2. Check if current branch is ahead of upstream
        $ahead = 0
        $currentBranch = (git rev-parse --abbrev-ref HEAD 2>$null)
        if ($currentBranch -and $currentBranch -ne "HEAD") {
            $upstream = (git rev-parse --abbrev-ref "@{u}" 2>$null)
            if ($upstream) {
                $ahead = (git rev-list --count "$upstream..HEAD" 2>$null)
            }
        }
        
        # 3. Check if dev is ahead of main (specific to our workflow)
        $aheadOfMain = 0
        
        $devExists = git branch --list dev
        $mainExists = git branch --list main
        
        if ($devExists -and $mainExists) {
            $aheadOfMain = (git rev-list --count "main..dev" 2>$null)
        }
        
        return ($hasUncommitted -or ($ahead -gt 0) -or ($aheadOfMain -gt 0))
    }
    finally {
        Pop-Location
    }
}

function Push-DevBranch {
    param([string]$RepoPath)
    
    Push-Location $RepoPath
    try {
        # Ensure we're on dev
        git checkout dev --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Checkout dev failed"
            return $false
        }
        
        $status = git status --porcelain
        if ($status) {
            Write-Step "Staging uncommitted changes..."
            git add -A
            git commit -m "Update"
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Commit failed"
                return $false
            }
        }

        # Bring local dev up to date (after committing local changes)
        git fetch origin dev --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $behind = git rev-list --count "HEAD..origin/dev" 2>$null
            if ($behind -gt 0) {
                Write-Step "Rebasing onto origin/dev (behind by $behind commits)..."
                $oldEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                $pullOut = git pull --rebase origin dev --quiet 2>&1
                $pullCode = $LASTEXITCODE
                $ErrorActionPreference = $oldEap
                if ($pullCode -ne 0) {
                    Write-Err "Rebase/pull failed"
                    if ($pullOut) { Write-Host "    $pullOut" -ForegroundColor DarkGray }
                    return $false
                }
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
        
        Write-Step "Pushing main..."
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
