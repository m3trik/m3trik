<#
Repository Manager (push.ps1)

Purpose
- Safely push changes on dev and (optionally) promote dev -> main in a controlled release order.
- Designed for the core package chain: pythontk -> uitk -> {mayatk, blendertk} -> tentacle
  (tentacle publishes as tentacletk on PyPI).

Core safety rules (Strict+Merge)
- Enforces canonical release order when multiple packages are provided.
- Stops on the first failure (build, merge conflict, workflow timeout, unsafe repo state).
- Refuses to operate if a repo has an in-progress merge/rebase/cherry-pick.
- Refuses to proceed if conflict markers exist in pyproject.toml (local OR remote origin/main|origin/dev).
- Refuses to release a real code delta without recorded "review" AND "tests" receipts
  for the current tree (release gate; receipts in .claude/receipts.json — see
  m3trik/CLAUDE.md "Release preflight"). The tests receipt is enforced, not advisory:
  mayatk and blendertk ship no pull_request-triggered tests workflow, so it is the only
  evidence their suite ever ran against the tree being published.
- Keeps internal pyproject.toml pins in sync with the local versions being released, and
  waits for a just-published upstream version to become visible on PyPI before merging
  a downstream package that pins it.

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
                      Verifies the PR is ACTUALLY gated before waiting on it: a PR with
                      zero check runs, or a mergeStateStatus of BLOCKED, fails loudly
                      instead of silently waiting out -PRMergeTimeoutSeconds.
-PRGateTimeoutSeconds / -PRGatePollSeconds
                      How long to let GitHub attach check runs to a fresh release PR
                      before the -UsePR gate concludes nothing is watching it, and
                      how often to re-probe while waiting.
-SkipBuild            Skip python build/twine validation.
-SkipWorkflowWait     Skip waiting for the publish workflow on main.
-SkipPypiCheck        Skip all PyPI availability gates (downstream pin pre-check +
                      post-publish visibility wait). Meant for offline use only —
                      indexing lag is already handled by bounded retries.
-SkipReview           Bypass the whole Strict+Merge release gate -- review AND tests
                      receipts, plus the m3trik-first guard (emergencies only).
-SkipTestsReceipt     Bypass ONLY the "tests" half of the release gate, after printing
                      a loud banner naming what is being given up. The review receipt
                      is still required.
-RecordReceipt        Record named verification receipt(s) (e.g. review,tests) for
                      the current tree of -Packages, then exit. See "Release
                      preflight" in m3trik/CLAUDE.md.
-ShowReceipts         Show receipt validity for -Packages (default: strict set),
                      then exit.
-CommitMessage        Message for the auto-commit Sync-DevWithOrigin makes when
                              absorbing local changes (defaults to "Update").
-WorkflowTimeoutSeconds / -WorkflowPollSeconds
                              Control workflow wait behavior.
-PypiVisibilityTimeoutSeconds How long to wait for a just-published version to become
                              visible on PyPI's simple index (the surface pip
                              resolves against) before continuing (default 300).

Notes
- Install requirements come from pyproject.toml (requirements.txt is deprecated repo-wide).
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
    [switch]$SkipReview,
    [switch]$SkipTestsReceipt,
    [string[]]$RecordReceipt,
    [switch]$ShowReceipts,
    [int]$ReceiptMaxAgeDays = 7,
    [switch]$UsePR,
    [int]$PRMergeTimeoutSeconds = 1800,
    # How long to let GitHub attach check runs to a freshly opened release PR before
    # the -UsePR gate calls it ungated. Checks normally appear within seconds; 120s
    # absorbs a slow Actions queue without hiding a real "nothing is watching this PR"
    # condition (which is the whole point of the gate).
    [int]$PRGateTimeoutSeconds = 120,
    # A poll interval is the wait loop's ONLY clock (`$elapsed += $PRGatePollSeconds`),
    # so 0 spins forever on `gh pr view` instead of ever reaching the "ZERO check runs"
    # refusal. Reject it at bind time rather than clamping silently.
    [ValidateRange(1, 600)]
    [int]$PRGatePollSeconds = 10,
    # 2400s (40 min), not 900s: the publish workflow reliably runs ~17 min for
    # uitk (build + verify-install + twine upload), which OVERRAN the old 900s
    # default and made the script abort a still-in-progress-but-successful
    # publish as "workflow failed", stopping the whole cascade one package in.
    # The manual-dispatch fallback + `twine upload --skip-existing` make an
    # over-generous wait safe; a genuinely hung run just costs a longer wait.
    [int]$WorkflowTimeoutSeconds = 2400,
    # Same clock-of-record rule as -PRGatePollSeconds above: Wait-ForWorkflow advances
    # its elapsed budget by this value alone.
    [ValidateRange(1, 600)]
    [int]$WorkflowPollSeconds = 15,
    [int]$PypiVisibilityTimeoutSeconds = 300,
    [string]$WorkflowFile = "publish.yml",
    [string]$Root = "O:\Cloud\Code\_scripts",
    [string]$CommitMessage = "Update"
)

$ErrorActionPreference = "Continue"
$ROOT = $Root
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
. (Join-Path $SCRIPT_DIR "common.ps1")

# Packages that support strict validation.
# blendertk is a full ecosystem package: public repo, published to PyPI, its own publish.yml,
# and a hard tentacle dependency. It releases in parallel with mayatk (both consume uitk; the
# chain is pythontk -> uitk -> {mayatk, blendertk} -> tentacle), so it sits after mayatk and
# before tentacle in the release order. (unitytk remains off-chain — floor-pinned, not cascaded.)
$STRICT_PACKAGES = @("pythontk", "uitk", "mayatk", "blendertk", "tentacle")
$RELEASE_ORDER = @("pythontk", "uitk", "mayatk", "blendertk", "tentacle")

# Internal (in-chain) pins each package carries — the SAME set is kept in sync in
# its pyproject.toml AND checked for availability on PyPI, so it lives in one place.
# unitytk is intentionally excluded everywhere (off-chain: floor-pinned, not cascaded).
$REQUIRED_PINS = @{
    "uitk"      = @("pythontk")
    "mayatk"    = @("pythontk", "uitk")
    "blendertk" = @("pythontk", "uitk")
    "tentacle"  = @("pythontk", "uitk", "mayatk", "blendertk")
}

# ------------------------------------------------------------------------------------------------
# Verification receipts
# One writer for .claude/receipts.json: a receipt records that a named check ("review",
# "tests", ...) passed for a package at an EXACT tree state. The tree hash covers HEAD plus
# the working-tree delta (tracked diff + untracked names/size/mtime), so any edit
# self-invalidates. The Strict+Merge release gate consumes BOTH "review" and "tests"
# (-SkipTestsReceipt waives only the latter, loudly); sessions consult -ShowReceipts to
# skip re-running a suite already green for an identical tree.
# Protocol: m3trik/CLAUDE.md "Release preflight".
# ------------------------------------------------------------------------------------------------
$RECEIPTS_PATH = Join-Path $ROOT ".claude\receipts.json"

function Get-TreeHash {
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        $head = (git rev-parse HEAD 2>$null)
        $status = @(git status --porcelain 2>$null) -join "`n"
        $diff = @(git diff HEAD 2>$null) -join "`n"
        # Untracked content edits don't show in `git diff`; fold in size+mtime per file.
        $untracked = @(git ls-files --others --exclude-standard 2>$null | ForEach-Object {
                $fi = Get-Item -LiteralPath (Join-Path $RepoPath $_) -ErrorAction SilentlyContinue
                if ($fi) { "$_|$($fi.Length)|$($fi.LastWriteTimeUtc.Ticks)" } else { $_ }
            }) -join "`n"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("$head`n$status`n$diff`n$untracked")
        $md5 = [System.Security.Cryptography.MD5]::Create()
        try { $hex = -join ($md5.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
        finally { $md5.Dispose() }
        return $hex.Substring(0, 12)
    }
    finally { Pop-Location }
}

function Get-RecentlyModifiedFiles {
    <#
      Changed files whose mtime is within $WithinMinutes. Used ONLY to explain a
      failed receipt gate: a receipt is keyed on the tree hash, so a concurrent
      writer already invalidates it -- but "no tests receipt" reads identically
      to "you never ran the suite", and the fix for those two is opposite (wait
      vs. run). Generated sidecars are excluded: regenerating the API registry
      immediately before a release is the NORMAL flow and would otherwise make
      every clean release look like a collision.
    #>
    param(
        [string]$RepoPath,
        [int]$WithinMinutes = 15
    )
    $cutoff = (Get-Date).ToUniversalTime().AddMinutes(-$WithinMinutes)
    Push-Location $RepoPath
    try {
        $paths = @(git status --porcelain 2>$null | ForEach-Object {
                # Porcelain v1: 2 status chars + space, then the path. A rename
                # reads "R  old -> new"; the post-rename path is what exists.
                $p = $_.Substring(3).Trim('"')
                if ($p -match ' -> ') { $p = ($p -split ' -> ')[-1] }
                $p
            })
        $recent = foreach ($p in $paths) {
            if ($p -match '^API_(INDEX|REGISTRY|CHANGES)\.(md|json)$') { continue }
            $fi = Get-Item -LiteralPath (Join-Path $RepoPath $p) -ErrorAction SilentlyContinue
            if ($fi -and -not $fi.PSIsContainer -and $fi.LastWriteTimeUtc -gt $cutoff) {
                [pscustomobject]@{
                    Path    = $p
                    Minutes = [math]::Round(((Get-Date).ToUniversalTime() - $fi.LastWriteTimeUtc).TotalMinutes, 1)
                }
            }
        }
        return @($recent | Sort-Object Minutes)
    }
    finally { Pop-Location }
}

function Read-Receipts {
    $map = @{}
    if (-not (Test-Path $RECEIPTS_PATH)) { return $map }
    try {
        $obj = Get-Content $RECEIPTS_PATH -Raw | ConvertFrom-Json
        foreach ($p in $obj.PSObject.Properties) { $map[$p.Name] = $p.Value }
    } catch {}
    return $map
}

function Save-Receipts {
    param([hashtable]$Map)
    $dir = Split-Path $RECEIPTS_PATH -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if ($Map.Count -eq 0) {
        $json = "{}"
    } else {
        $out = New-Object PSObject
        foreach ($k in ($Map.Keys | Sort-Object)) {
            $out | Add-Member -NotePropertyName $k -NotePropertyValue $Map[$k]
        }
        $json = $out | ConvertTo-Json -Depth 4
    }
    [System.IO.File]::WriteAllText($RECEIPTS_PATH, $json, (New-Object System.Text.UTF8Encoding $false))
}

function Write-ReceiptEntry {
    param([string]$PackageName, [string]$RepoPath, [string[]]$Checks)
    $key = "$PackageName@$(Get-TreeHash $RepoPath)"
    $map = Read-Receipts
    $entry = if ($map.ContainsKey($key)) { $map[$key] } else { New-Object PSObject }
    $now = [DateTime]::UtcNow.ToString('o')
    foreach ($c in $Checks) {
        $entry | Add-Member -NotePropertyName $c -NotePropertyValue $now -Force
    }
    $map[$key] = $entry
    # Prune entries whose every check is stale beyond any plausible validity window.
    $cutoff = [DateTime]::UtcNow.AddDays(-30)
    foreach ($k in @($map.Keys)) {
        $live = $false
        foreach ($p in $map[$k].PSObject.Properties) {
            try { if ([DateTime]::Parse($p.Value).ToUniversalTime() -gt $cutoff) { $live = $true; break } } catch {}
        }
        if (-not $live) { $map.Remove($k) }
    }
    Save-Receipts $map
    return $key
}

function Test-Receipt {
    param(
        [string]$PackageName,
        [string]$RepoPath,
        [string]$Check,
        [string]$TreeHash  # optional precomputed hash (avoids recomputation)
    )
    if (-not $TreeHash) { $TreeHash = Get-TreeHash $RepoPath }
    $map = Read-Receipts
    $key = "$PackageName@$TreeHash"
    if (-not $map.ContainsKey($key)) { return $false }
    $prop = $map[$key].PSObject.Properties[$Check]
    if (-not $prop) { return $false }
    try {
        $ts = [DateTime]::Parse($prop.Value).ToUniversalTime()
        return (([DateTime]::UtcNow - $ts).TotalDays -le $ReceiptMaxAgeDays)
    } catch { return $false }
}

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

    # Probe the SIMPLE index (PEP 691 JSON form) — the surface pip actually
    # resolves against. The JSON API (`/pypi/<name>/json`) updates ahead of it
    # after an upload, so gating there let the cascade proceed while a
    # downstream workflow's `pip install <pkg>>=<ver>` still failed with
    # "No matching distribution found" (measured 2026-08-13: this gate
    # confirmed uitk==1.3.76 while /simple/uitk/ still listed 1.3.73).
    try {
        # PEP 503 name normalization: lowercase; runs of ., -, _ collapse to -.
        $normalized = $ProjectName.ToLowerInvariant() -replace '[-_.]+', '-'
        $url = "https://pypi.org/simple/$normalized/"
        $data = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop -Headers @{
            Accept = "application/vnd.pypi.simple.v1+json"
        }
        # PS 5.1 only auto-parses recognized JSON content types; the vendored
        # +json type may come back as a raw string.
        if ($data -is [string]) { $data = $data | ConvertFrom-Json }
        if (-not $data) {
            return $false
        }
        if ($data.versions) {
            return @($data.versions) -contains $Version
        }
        # Strict PEP 691 v1.0 indexes may omit the PEP 700 `versions` key and
        # only list `files`; fall back to matching the version against filenames.
        # Anchored on the real delimiters so the bound cuts both ways: a version
        # is preceded by `-` (PEP 427 wheel / PEP 625 sdist both use
        # `{name}-{version}`) and followed by `-` (wheel) or the archive suffix
        # (sdist). That rejects "1.3.7" against "...-1.3.76-..." AND still
        # matches an sdist-only listing — a trailing [^0-9A-Za-z.] class excludes
        # the dot, so it never matched "pkg-1.3.76.tar.gz" at all.
        if ($data.files) {
            $escaped = [regex]::Escape($Version)
            $pattern = "(?:^|-)$escaped(?:-|\.tar\.gz$|\.zip$)"
            foreach ($f in @($data.files)) {
                if ($f.filename -and ($f.filename -match $pattern)) {
                    return $true
                }
            }
        }
        return $false
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

function Wait-PypiHasVersion {
    # PyPI's API can lag a fresh twine upload (CDN propagation), so a single
    # Test-PypiHasVersion probe right after a publish can false-negative.
    # Poll with a bounded window instead of failing immediately — the old
    # workaround was re-running the cascade with -SkipPypiCheck, which drops
    # the installability guard entirely.
    param(
        [string]$ProjectName,
        [string]$Version,
        [int]$TimeoutSeconds = 180,
        [int]$PollSeconds = 10
    )

    if (Test-PypiHasVersion $ProjectName $Version) { return $true }
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        Write-Host "    Waiting for PyPI to show $ProjectName==$Version... ($elapsed/$TimeoutSeconds seconds)" -ForegroundColor Gray
        Start-Sleep -Seconds $PollSeconds
        $elapsed += $PollSeconds
        if (Test-PypiHasVersion $ProjectName $Version) {
            Write-Success "PyPI shows $ProjectName==$Version"
            return $true
        }
    }
    return $false
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
    # (?m)^ anchors detection to the real assignment line, matching the
    # replacement below — a docstring that merely mentions __version__ = "…"
    # earlier in the file must not seed $oldVer.
    if ($content -match '(?m)^__version__\s*=\s*["''](?<ver>\d+\.\d+\.\d+)["'']') {
        $oldVer = $Matches['ver']
        $parts = $oldVer -split "\."
        $parts[2] = [int]$parts[2] + 1
        $newVer = "$($parts[0]).$($parts[1]).$($parts[2])"
        
        # (?m)^ anchors to the assignment line so a docstring/comment that
        # happens to mention __version__ is never clobbered.
        $newContent = $content -replace '(?m)^__version__\s*=\s*.*', "__version__ = `"$newVer`""
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

        # -SkipPypiCheck (offline runs): trust local versions as-is — every
        # other PyPI probe honors the flag, and firing network calls here
        # contradicted the parameter's documented offline purpose.
        if (-not $SkipPypiCheck) {
            $pypiName = Get-PypiProjectName $pkg
            if (-not (Test-PypiHasVersion $pypiName $ver)) {
                $latest = Get-PypiLatestVersion $pypiName
                if ($latest) {
                    Write-Host "  > $pkg local $ver is unpublished; using PyPI latest $latest" -ForegroundColor DarkGray
                    $ver = $latest
                }
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

    # Only these packages have internal pins today (see $REQUIRED_PINS, top of file).
    if (-not $REQUIRED_PINS.ContainsKey($PackageName)) {
        return $true
    }

    $requiredPins = $REQUIRED_PINS[$PackageName]
    # Ensure edits land on dev. A DryRun makes no edits, so it must not
    # switch branches either.
    if (-not $DryRun) {
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

        $pattern = '"' + $dep + '>=([0-9.]+)"'
        $replacement = '"' + $dep + '>=' + $ver + '"'
        
        if ($newContent -match $pattern) {
             # Check if it's already correct to avoid unnecessary writes
             $currentMatch = $matches[0]
             $currentFloor = $matches[1]
             if ($currentMatch -ne $replacement) {
                 # NEVER lower a declared floor. $LocalVersions is clamped to
                 # what is PUBLISHED, so on a run that does not include the
                 # upstream this would rewrite a deliberately-raised floor back
                 # down to the old release and silently reintroduce the break
                 # the raise existed to prevent (measured 2026-08-19:
                 # `-Packages mayatk` alone walked `pythontk>=0.9.25` back to
                 # `>=0.9.24`, and mayatk reads a 0.9.25 attribute in a CLASS
                 # BODY, i.e. AttributeError at import). A floor states what the
                 # CODE needs; the sync may only ratchet it UP to what it is
                 # publishing. An unparseable version keeps the historical
                 # behaviour -- every real version here is 3-part semver, which
                 # Bump-LocalVersion's own regex enforces.
                 $isLower = $false
                 try {
                     $isLower = ([version]$ver -lt [version]$currentFloor)
                 } catch {
                     $isLower = $false
                 }
                 if ($isLower) {
                     Write-Host "    Keeping $dep>=$currentFloor (declared floor is above the $ver being pinned)" -ForegroundColor DarkGray
                 } else {
                     $newContent = $newContent -replace $pattern, $replacement
                     $changed = $true
                 }
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
        # Deliberately NOT tagged [skip ci]. For a package whose deps cascaded,
        # THIS commit is the version bump, so it heads the release PR - and
        # GitHub skips every workflow for a [skip ci] head, which strips the
        # required check ("test" / "static-analysis") off the very PR the gate
        # exists to hold. With required status checks live (2026-08-17) that is
        # not merely ungated, it is a PR that can never merge. Nothing on dev
        # triggers on push anyway - every push-triggered workflow in all five
        # repos is branches:[main] - so the tag suppressed nothing here; its
        # only other effect was on the MERGED head, where publish.yml now
        # auto-queues instead of needing Wait-ForWorkflow's manual dispatch.
        git commit -m "Update dependencies & bump version to $newVer" | Out-Null
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

    # ONLY deltas that cannot change the shipped artifact count as "nothing to
    # release":
    #   - <pkg>/__init__.py — the version-string bump itself. The strict
    #     packages all declare `version = {attr = "<pkg>.__version__"}`
    #     (dynamic), so a pure bump touches exactly this file.
    #   - API_INDEX/API_REGISTRY/API_CHANGES — repo-root artifacts the
    #     refresh-api-registry bot commits to dev after every publish. They
    #     never ship in the wheel; without this, the bot's post-release commit
    #     defeated the guard and every cascade re-run phantom-published.
    #   - CHANGELOG.md — repo-root release-notes source, not wheel content; a
    #     notes-only delta rides along with the next real release
    #     (Get-ChangelogDelta diffs origin/main..dev, so nothing is lost).
    # Deliberately NOT allowed: pyproject.toml (a dependency-cascade release
    # changes only the pin + version and MUST still merge/publish so downstream
    # pins propagate) and docs/README.md (dynamic readme -> wheel metadata).
    $allowed = @(
        "$PackageName/__init__.py",
        "API_INDEX.md",
        "API_REGISTRY.md",
        "API_REGISTRY.json",
        "API_CHANGES.md",
        "CHANGELOG.md"
    )

    Push-Location $RepoPath
    try {
        git fetch origin main dev --quiet 2>&1 | Out-Null
        # Diff LOCAL dev (what Merge-ToMain will actually merge), not
        # origin/dev: this run's absorbed local work and bump/pin-sync commits
        # exist only locally at this point — the push happens later, in step 3.
        # Diffing origin/dev made the guard skip the merge whenever real local
        # changes rode on top of a bot-bumped origin/dev, silently dropping the
        # release while reporting success. Local dev is rebased onto origin/dev
        # by Sync-DevWithOrigin before this runs, so it is always a superset of
        # origin/dev in Strict+Merge mode.
        $files = @(git diff --name-only origin/main..dev 2>$null)
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

    # Polls `gh run list`, filters to $headSha, and reports a verdict:
    # 'pending' (no matching run yet, or still running), 'success', or a
    # failure conclusion string. Shared by the main wait loop and the
    # post-timeout fallback below so both apply identical match/status logic.
    function Get-MatchingRunVerdict {
        param([string]$RepoSlug, [string]$Sha)
        try {
            $runsJson = gh run list --repo $RepoSlug --branch main --workflow $WorkflowFile --limit 20 --json status,conclusion,headSha,createdAt,displayTitle 2>$null
            if (-not $runsJson) { return "pending" }
            $runs = $runsJson | ConvertFrom-Json
        }
        catch {
            return "pending"
        }

        $matching = @($runs | Where-Object { $_.headSha -eq $Sha })
        # "norun" (no run for this SHA yet) is distinct from "pending" (a run
        # exists and is still going): the manual-dispatch fallback below fires
        # only on "norun", so an already auto-triggered run isn't shadowed by a
        # redundant second dispatch.
        if (-not $matching -or $matching.Count -eq 0) { return "norun" }

        $inProgress = @($matching | Where-Object { $_.status -ne "completed" })
        if ($inProgress.Count -gt 0) { return "pending" }

        $failed = @($matching | Where-Object { $_.conclusion -and $_.conclusion -ne "success" })
        if ($failed.Count -gt 0) { return $failed[0].conclusion }

        return "success"
    }

    # publish.yml's push trigger is path-filtered (paths: [<pkg>/**,
    # pyproject.toml]), so a merged head that touches neither queues no run.
    # As of 2026-08-17 NO commit push.ps1 makes carries [skip ci] (both the dev
    # auto-bump and the cascade pin-sync bump dropped it, because either can head
    # the release PR and a [skip ci] head strips the required check off it), and
    # both merge paths interpose a merge commit whose own message is clean
    # (Merge-ToMain forces --no-ff; `gh pr merge --merge` always creates one).
    # So a run should now auto-queue on every release. This fallback stays for the
    # cases it cannot: a hand-made [skip ci] head, a paths-filter miss, or GitHub
    # simply not queueing. It costs nothing when a run already did.
    # Rather than burn the whole $maxWait budget polling for a run that will never
    # appear (the old code did, then left only a 180s window for a late dispatch --
    # far too short for a real publish run, so the cascade aborted after one
    # package), proactively dispatch publish.yml once a short grace passes with no
    # matching run, then keep polling the FULL budget for that run to finish.
    # Safe to retry: the publish job's own version-vs-PyPI check plus
    # `twine upload --skip-existing` make a redundant dispatch a no-op, and the
    # per-ref concurrency group serializes any auto+manual pair.
    $maxWait = $WorkflowTimeoutSeconds
    $elapsed = 0
    $dispatched = $false
    $dispatchAfter = 90

    while ($elapsed -lt $maxWait) {
        if ($elapsed -eq 0) {
            Start-Sleep -Seconds 10
            $elapsed += 10
        } else {
            Start-Sleep -Seconds $WorkflowPollSeconds
            $elapsed += $WorkflowPollSeconds
        }

        $verdict = Get-MatchingRunVerdict -RepoSlug $repoSlug -Sha $headSha
        if ($verdict -eq "norun" -or $verdict -eq "pending") {
            # Only dispatch when NO run exists for this SHA (norun). If one is
            # already in-progress (pending -- the push auto-triggered it), wait
            # it out rather than queue a redundant second run.
            if ($verdict -eq "norun" -and -not $dispatched -and $elapsed -ge $dispatchAfter) {
                Write-Host "    No auto-triggered run after ${elapsed}s (paths filter missed, or a hand-made [skip ci] head); dispatching publish.yml manually..." -ForegroundColor Yellow
                gh workflow run $WorkflowFile --repo $repoSlug --ref main 2>&1 | Out-Null
                $dispatched = $true
            }
            if ($elapsed % 60 -eq 0) {
                $mode = if ($dispatched) { "dispatched" } elseif ($verdict -eq "pending") { "auto" } else { "waiting" }
                Write-Host "    Waiting for workflow ($mode)... ($elapsed/$maxWait seconds)" -ForegroundColor Gray
            }
            continue
        }
        if ($verdict -eq "success") {
            Write-Success "Workflow completed (publish.yml)"
            return $true
        }
        Write-Err "Workflow concluded with '$verdict'"
        return $false
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

function Get-PRGateState {
    # One `gh pr view` probe reduced to the two facts the -UsePR gate needs: how many
    # check runs GitHub has attached to the PR head, and the computed mergeStateStatus.
    # Returns $null when the probe itself fails (so callers can retry rather than treat
    # a transient gh error as "ungated").
    param(
        [string]$RepoSlug,
        [int]$PrNumber
    )

    $json = gh pr view $PrNumber --repo $RepoSlug --json statusCheckRollup,mergeStateStatus 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
    try { $v = $json | ConvertFrom-Json } catch { return $null }
    if (-not $v) { return $null }

    # A missing/null rollup is zero checks, not one: @($null).Count is 1.
    $rollup = @()
    if ($null -ne $v.statusCheckRollup) { $rollup = @($v.statusCheckRollup) }

    # statusCheckRollup mixes two node shapes: CheckRun (status/conclusion) and
    # StatusContext (state). A node is SETTLED once it has a conclusion, or a state
    # that is no longer PENDING/EXPECTED. Anything else is still running - which is
    # the one reading of BLOCKED that auto-merge is designed to sit through.
    $pending = 0
    foreach ($c in $rollup) {
        $conclusion = ""
        $stateVal = ""
        if ($c.PSObject.Properties['conclusion']) { $conclusion = [string]$c.conclusion }
        if ($c.PSObject.Properties['state']) { $stateVal = [string]$c.state }
        $settled = $conclusion -or ($stateVal -and $stateVal -ne "PENDING" -and $stateVal -ne "EXPECTED")
        if (-not $settled) { $pending++ }
    }

    return [PSCustomObject]@{
        CheckCount       = $rollup.Count
        PendingCount     = $pending
        MergeStateStatus = [string]$v.mergeStateStatus
    }
}

function Test-PRReleaseGate {
    # -UsePR only buys anything if the PR is ACTUALLY gated. Two states made it a
    # no-op that used to pass silently:
    #   * ZERO check runs - nothing is testing the merge, so GitHub lands the PR the
    #     instant auto-merge is armed. -UsePR then differs from a direct merge only in
    #     the reassuring log line. Real cause: the PR head commit carries [skip ci]
    #     (GitHub skips every workflow for such a head). As of 2026-08-17 every
    #     ecosystem repo HAS a pull_request-triggered required check - "test" on
    #     pythontk/uitk/tentacle, "static-analysis" on mayatk/blendertk - so zero
    #     check runs now means the head was skipped, not that the repo lacks a
    #     workflow. (static-analysis is a parse/pyflakes gate, NOT a test suite:
    #     the tests receipt remains mayatk's and blendertk's only suite evidence.)
    #   * mergeStateStatus BLOCKED - branch protection is holding the PR (missing
    #     required approving review, failing required check). Auto-merge never fires,
    #     and the old code just waited out -PRMergeTimeoutSeconds (30 min) before
    #     reporting a generic timeout with no cause and no remedy.
    # Both now fail immediately, naming the cause.
    param(
        [string]$RepoSlug,
        [int]$PrNumber
    )

    $elapsed = 0
    $state = Get-PRGateState $RepoSlug $PrNumber
    while (($null -eq $state -or $state.CheckCount -eq 0) -and $elapsed -lt $PRGateTimeoutSeconds) {
        Start-Sleep -Seconds $PRGatePollSeconds
        $elapsed += $PRGatePollSeconds
        Write-Host "    Waiting for check runs on PR #$PrNumber... ($elapsed/$PRGateTimeoutSeconds seconds)" -ForegroundColor Gray
        $state = Get-PRGateState $RepoSlug $PrNumber
    }

    if ($null -eq $state) {
        Write-Err "Cannot read the gate state of PR #$PrNumber (gh pr view failed)"
        Write-Err "Refusing to wait on a PR whose checks cannot be verified."
        return $false
    }

    if ($state.CheckCount -eq 0) {
        Write-Err "PR #$PrNumber reports ZERO check runs after ${elapsed}s - -UsePR is not gating this release."
        Write-Host @"
  Auto-merge with no checks lands the PR immediately, so -UsePR would be exactly a
  direct merge while reporting that it honored a test gate. Known causes:
    * The PR head commit is tagged "[skip ci]" - GitHub skips every workflow,
      tests.yml included, for such a head.
    * The repo's required check was renamed, or its workflow no longer triggers on
      pull_request (expected: "test" on pythontk/uitk/tentacle, "static-analysis"
      on mayatk/blendertk).
  Give the repo a real gate, or re-run WITHOUT -UsePR to merge deliberately ungated.
"@ -ForegroundColor Yellow
        return $false
    }

    if ($state.MergeStateStatus -eq "BLOCKED" -and $state.PendingCount -eq 0) {
        # Every check has settled, so nothing left to run can clear the block:
        # a required approving review is missing, or a required check failed.
        # Auto-merge would stay armed forever.
        Write-Err "PR #$PrNumber mergeStateStatus=BLOCKED - auto-merge can never fire."
        Write-Host @"
  Branch protection is holding this PR and every check has already settled:
  typically a missing required approving review, or a required status check that
  failed. Auto-merge would stay armed and the release would sit here until
  -PRMergeTimeoutSeconds expires.
  Approve/unblock the PR (or fix the failing check), then re-run this same command.
"@ -ForegroundColor Yellow
        return $false
    }

    if ($state.MergeStateStatus -eq "BLOCKED") {
        # BLOCKED with checks still running is the normal, transient state that
        # auto-merge exists for - failing here would break every release the moment
        # a required status check is configured. Wait-ForPRMerged owns this case.
        Write-Skip "PR #$PrNumber is BLOCKED with $($state.PendingCount) check(s) still running (auto-merge will land it)"
        return $true
    }

    Write-Success "PR #$PrNumber is gated by $($state.CheckCount) check run(s) (mergeStateStatus=$($state.MergeStateStatus))"
    return $true
}

function Enable-AutoMergePR {
    param(
        [string]$RepoSlug,
        [int]$PrNumber
    )

    # Gate FIRST, arm second. On a PR with no required checks GitHub merges the
    # instant --auto is set, so a post-hoc verification would be refusing a merge
    # that had already happened.
    if (-not (Test-PRReleaseGate $RepoSlug $PrNumber)) { return $false }

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

    Write-Step "Verifying PR #$pr is gated, then enabling auto-merge (merge commit)..."
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

# Receipt utility modes: record/show verification receipts and exit (no repo mutations).
if ($RecordReceipt -or $ShowReceipts) {
    if ($RecordReceipt -and -not $Packages) {
        Write-Err "-RecordReceipt requires -Packages (recording is an explicit per-package assertion)"
        exit 1
    }
    $receiptPkgs = if ($Packages) { $Packages } else { $STRICT_PACKAGES }
    $receiptFail = $false
    foreach ($pkg in $receiptPkgs) {
        $repoPath = Join-Path $ROOT $pkg
        if (-not (Test-Path (Join-Path $repoPath ".git"))) {
            Write-Err "Not a git repo: $repoPath"
            $receiptFail = $true
            continue
        }
        if ($RecordReceipt) {
            $checks = @($RecordReceipt | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            $key = Write-ReceiptEntry -PackageName $pkg -RepoPath $repoPath -Checks $checks
            Write-Success "Recorded [$($checks -join ', ')] for $key"
        } else {
            $hash = Get-TreeHash $repoPath
            $map = Read-Receipts
            $key = "$pkg@$hash"
            if ($map.ContainsKey($key)) {
                $states = foreach ($p in $map[$key].PSObject.Properties) {
                    $valid = Test-Receipt -PackageName $pkg -RepoPath $repoPath -Check $p.Name -TreeHash $hash
                    "$($p.Name)=$(if ($valid) { 'VALID' } else { 'EXPIRED' })"
                }
                Write-Host "  $key : $($states -join ', ')" -ForegroundColor Cyan
            } else {
                Write-Host "  $key : no receipts for current tree" -ForegroundColor DarkGray
            }
        }
    }
    if ($receiptFail) { exit 1 } else { exit 0 }
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
        "pythontk"  = @("uitk", "mayatk", "blendertk", "tentacle")
        "uitk"      = @("mayatk", "blendertk", "tentacle")
        "mayatk"    = @("tentacle")
        "blendertk" = @("tentacle")
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

# ------------------------------------------------------------------------------------------------
# m3trik-first guard (Strict+Merge releases only). Each package's publish.yml dispatches
# m3trik's refresh-api-registry.yml, which checks out m3trik@MAIN and force-pushes regenerated
# registries back to every package's dev. Releasing while local m3trik/scripts differs from
# origin/main means the bot regenerates with the OLD tooling and silently reverts the
# registries this release just produced (measured 2026-08-01: mayatk -495 / blendertk -234
# lines, two failed parity-audit gates, a full re-release cycle). Push m3trik first.
# Runs BEFORE the review gate: it is cheaper, and its remedy (push m3trik) precedes preflight.
# ------------------------------------------------------------------------------------------------
if ($Merge -and $Strict -and -not $SkipReview) {
    $m3trikPath = Join-Path $ROOT "m3trik"
    if ((Test-Path (Join-Path $m3trikPath "scripts")) -and (Test-Path (Join-Path $m3trikPath ".git"))) {
        $m3trikDrift = $false
        $originMain = $null
        Push-Location $m3trikPath
        try {
            git fetch origin main --quiet 2>&1 | Out-Null
            $originMain = git rev-parse --verify -q origin/main 2>$null
            if ($originMain) {
                git diff --quiet origin/main -- scripts 2>$null
                if ($LASTEXITCODE -ne 0) { $m3trikDrift = $true }
                if (-not $m3trikDrift) {
                    $untrackedScripts = git ls-files --others --exclude-standard -- scripts 2>$null
                    if ($untrackedScripts) { $m3trikDrift = $true }
                }
            }
        }
        finally { Pop-Location }
        if (-not $originMain) {
            Write-Header "m3trik-first guard"
            Write-Err "m3trik-first guard: cannot resolve origin/main (fetch failed?) - refusing to release"
            exit 1
        }
        if ($m3trikDrift) {
            Write-Header "m3trik-first guard"
            Write-Err "m3trik/scripts differs from origin/main (uncommitted, unpushed, or untracked changes)."
            Write-Host @"
  The publish-triggered refresh-api-registry.yml runs the generator and gates from
  m3trik@main. Releasing now would have the bot regenerate every package's registries
  with the OLD tooling, force-pushing over what this release just produced.
  Fix: sync m3trik main first (pull, or commit and push), then re-run this same command.
  Emergency bypass: -SkipReview.
"@ -ForegroundColor Yellow
            exit 1
        }
        Write-Success "m3trik-first guard: m3trik/scripts matches origin/main"
    }
    else {
        Write-Skip "m3trik-first guard: skipped (m3trik/scripts or m3trik/.git not found at $m3trikPath)"
    }
}

# ------------------------------------------------------------------------------------------------
# Release gate (Strict+Merge releases only). A package with a real code delta may not release
# unless its CURRENT tree has BOTH a "review" and a "tests" receipt. Runs as a pre-pass BEFORE
# any repo mutation so (a) a failure has zero side effects and (b) the cascade's own mechanical
# commits (pin-sync, version bump) can't void a receipt mid-run. No-delta and housekeeping-only
# packages are exempt — "push everything" never demands review of untouched repos.
#
# The "tests" half is a HARD gate, not advisory: mayatk and blendertk ship no
# pull_request-triggered tests workflow (only bump-dev / publish / static-analysis), so the
# local receipt is the ONLY evidence that this exact tree's suite ever ran. -SkipTestsReceipt
# waives that half alone and says so loudly; -SkipReview waives the whole pre-pass.
# The failure text carries the full protocol so any session (or human) can complete preflight
# without being re-instructed.
# ------------------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------
# Behind-remote preflight (-Merge). Every other rev-list in this script measures origin/dev..dev
# -- AHEAD. Nothing measured the reverse, so a repo the bump-version / API-registry bots had
# moved on looked pristine right up until the push failed, with every tree already mutated
# (2026-08-19: all five cascade repos sat 2 commits back at once, and only a manual check found
# it). Deliberately NOT under -SkipReview: that flag waives the review RECEIPT, and being behind
# is a fact about the remote no review can settle. Runs before any mutation, so failing is free.
# ------------------------------------------------------------------------------------------------
if ($Merge) {
    $behindRepos = @()
    foreach ($repo in $reposToProcess) {
        if ($STRICT_PACKAGES -notcontains $repo.Name) { continue }
        Push-Location $repo.FullName
        try {
            git fetch origin dev --quiet 2>&1 | Out-Null
            $bh = git rev-list --count dev..origin/dev 2>$null
            if ($bh -and [int]$bh -gt 0) { $behindRepos += "$($repo.Name) ($bh)" }
        }
        finally { Pop-Location }
    }
    if ($behindRepos.Count -gt 0) {
        Write-Header "Behind origin/dev"
        Write-Err "Local dev is behind: $($behindRepos -join ', ')"
        $behindNames = @($behindRepos | ForEach-Object { ($_ -split ' ')[0] })
        Write-Host @"
  Those commits are normally the bump-version / API-registry bots from the LAST
  release. Releasing now mutates every tree and then fails at push.

  Pull first, then re-run this command:
    '$($behindNames -join "','")' | ForEach-Object { git -C (Join-Path '$Root' `$_) pull --rebase }

  A pull changes the tree, so it also voids any receipt recorded before it --
  record review/tests AFTER pulling, never before.
"@ -ForegroundColor Yellow
        exit 1
    }
}

if ($Merge -and $Strict -and -not $SkipReview) {
    $reviewMissing = @()
    $testsMissing = @()
    $testsBypassed = @()
    foreach ($repo in $reposToProcess) {
        $gateName = $repo.Name
        if ($STRICT_PACKAGES -notcontains $gateName) { continue }
        $gatePath = $repo.FullName
        Push-Location $gatePath
        try {
            git fetch origin main dev --quiet 2>&1 | Out-Null
            $gateDirty = [bool](git status --porcelain 2>$null)
            $gateAhead = 0
            $a = git rev-list --count origin/dev..dev 2>$null
            if ($a) { $gateAhead = [int]$a }
            $gateMainDelta = 0
            $m = git rev-list --count origin/main..dev 2>$null
            if ($m) { $gateMainDelta = [int]$m }
        }
        finally { Pop-Location }

        if (-not ($gateDirty -or $gateAhead -gt 0 -or $gateMainDelta -gt 0)) { continue }
        if (-not $gateDirty -and $gateAhead -eq 0 -and (Test-OnlyDevBumpChanges $gatePath $gateName)) {
            Write-Skip "Review gate: $gateName delta is housekeeping only (exempt)"
            continue
        }

        $gateHash = Get-TreeHash $gatePath
        if (Test-Receipt -PackageName $gateName -RepoPath $gatePath -Check "review" -TreeHash $gateHash) {
            Write-Success "Review receipt valid: $gateName@$gateHash"
        } else {
            $reviewMissing += "$gateName@$gateHash"
        }
        if ($SkipTestsReceipt) {
            $testsBypassed += "$gateName@$gateHash"
        } elseif (Test-Receipt -PackageName $gateName -RepoPath $gatePath -Check "tests" -TreeHash $gateHash) {
            Write-Success "Tests receipt valid: $gateName@$gateHash"
        } else {
            $testsMissing += "$gateName@$gateHash"
        }
    }
    if ($testsBypassed.Count -gt 0) {
        # A silent bypass switch is worse than no gate at all: it removes the one
        # signal that the tree is untested while leaving the reassuring log intact.
        Write-Header "TESTS RECEIPT GATE BYPASSED (-SkipTestsReceipt)"
        Write-Err "Releasing UNTESTED trees: $($testsBypassed -join ', ')"
        Write-Host @"
  Why this is loud: mayatk and blendertk have NO pull_request-triggered tests
  workflow, and their publish.yml gate is static analysis only -- so the local
  "tests" receipt is the ONLY evidence a suite ever ran against this tree.
  Bypassing it means nothing, anywhere, has tested what is about to reach PyPI.
  Prefer recording a real receipt:
    .\m3trik\push.ps1 -RecordReceipt tests -Packages <pkgs>
"@ -ForegroundColor Yellow
    }
    if ($reviewMissing.Count -gt 0 -or $testsMissing.Count -gt 0) {
        $missingNames = (@($reviewMissing + $testsMissing) |
            ForEach-Object { ($_ -split '@')[0] } |
            Select-Object -Unique) -join ','
        Write-Header "Release gate"
        if ($reviewMissing.Count -gt 0) {
            Write-Err "No review receipt for the current tree of: $($reviewMissing -join ', ')"
        }
        if ($testsMissing.Count -gt 0) {
            Write-Err "No tests receipt for the current tree of: $($testsMissing -join ', ')"
        }

        # A missing receipt has two opposite causes and, until now, one message.
        # "Never ran the suite" -> run it. "Another session is editing this tree"
        # -> running it records a receipt for a tree that is still moving, and the
        # next edit voids it again. Fresh mtimes tell the two apart in one line.
        $liveNames = @(@($reviewMissing + $testsMissing) |
            ForEach-Object { ($_ -split '@')[0] } | Select-Object -Unique)
        $liveFound = $false
        foreach ($ln in $liveNames) {
            $lp = Join-Path $Root $ln
            if (-not (Test-Path $lp)) { continue }
            $recent = Get-RecentlyModifiedFiles -RepoPath $lp -WithinMinutes 15
            if ($recent.Count -gt 0) {
                if (-not $liveFound) {
                    Write-Host ""
                    Write-Host "  Another session may be editing these trees RIGHT NOW:" -ForegroundColor Red
                    $liveFound = $true
                }
                Write-Host "    $ln - $($recent.Count) file(s) changed in the last 15 min:" -ForegroundColor Yellow
                foreach ($r in ($recent | Select-Object -First 8)) {
                    Write-Host "      $($r.Minutes.ToString().PadLeft(5)) min ago  $($r.Path)" -ForegroundColor DarkGray
                }
                if ($recent.Count -gt 8) {
                    Write-Host "      ... and $($recent.Count - 8) more" -ForegroundColor DarkGray
                }
            }
        }
        if ($liveFound) {
            Write-Host @"
  If that is not you: WAIT for it to settle, then review/test/record. Recording
  now pins a receipt to a tree that is still changing, and -Merge does `git add
  -A` -- it would publish the other session's in-progress work to PyPI, which
  cannot be recalled.
"@ -ForegroundColor Yellow
        }

        Write-Host @"
  Release preflight (see m3trik/CLAUDE.md), for each package listed:
    1. Review its release diff (git diff origin/main...dev + working tree):
       correctness -> DRY -> simplification -> efficiency. Implement fixes;
       out-of-scope findings -> .claude/BACKLOG.md.
    2. Run its test suite. The "tests" receipt is a HARD gate: mayatk and
       blendertk have no CI test workflow, so it is the only gate they get.
       -ShowReceipts tells you whether one is already valid for this tree.
    3. Record, then re-run this same push command:
       .\m3trik\push.ps1 -RecordReceipt review,tests -Packages $missingNames
  Bypasses: -SkipTestsReceipt (tests half only, loud), -SkipReview (whole
  pre-pass; also required to DryRun past it).
"@ -ForegroundColor Yellow
        exit 1
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
                        # Check if the last commit was already a bump to avoid loops/double
                        # bumps. Matches BOTH bump message shapes: the auto-bump/bot
                        # "Bump version to X" AND the pin-sync "Update dependencies &
                        # bump version to X" — a run that failed after the pin-sync
                        # commit used to re-bump on every retry, burning a patch
                        # version each time. Anchored to those exact shapes: an
                        # ordinary commit that merely MENTIONS the phrase (e.g.
                        # 'Revert "Bump version to X"') must still bump, or the
                        # release ships an already-published version and the
                        # publish gate silently skips it.
                        $lastMsg = git log -1 --pretty=%s
                        if ($lastMsg -notmatch '(?i)^(update dependencies & )?bump version to ') {
                             $shouldBump = $true
                        }
                        # A delta that is only allow-listed housekeeping
                        # (registry refresh, CHANGELOG curation) skips the
                        # merge later — don't burn a patch version on dev for
                        # a release that won't happen; the notes ride along
                        # with the next real release.
                        if ($shouldBump -and $Strict -and $isStrictPackage -and (Test-OnlyDevBumpChanges $repoPath $pkgName)) {
                            Write-Skip "Dev delta is allow-listed housekeeping only (skipping version bump)"
                            $shouldBump = $false
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
                            # Deliberately NOT tagged [skip ci]: this commit heads the
                            # dev branch the release PR is opened from, and GitHub skips
                            # every workflow (tests.yml included) for a [skip ci] head --
                            # which is exactly how -UsePR came to merge release PRs that
                            # had never run a single check. Nothing auto-triggers on a
                            # dev push anyway (publish.yml is branches:[main], bump-dev
                            # is repository_dispatch only), so the tag bought nothing.
                            git commit -m "Bump version to $newVer" | Out-Null
                         }
                         finally { Pop-Location }
                     }
                 }
            }
        
            # Keep internal pins consistent with what we're releasing, so pip installs are reliable.
            $syncOk = Sync-PyProjectDepsToLocalVersions $pkgName $repoPath $localStrictVersions
            if (-not $syncOk) {
                $results[$pkgName] = "dep-sync-failed"
                $anyErrors = $true
                Write-Err "Dependency sync failed"
                if ($stopOnFailure) { break }
                continue
            }

            # Ensure pinned upstream versions are already available on PyPI.
            # This prevents merging downstream pins that would temporarily be
            # un-installable. Skipped in DryRun: the version map holds simulated
            # (never-published) bumps there, so the check can only false-fail.
            if (-not $SkipPypiCheck -and -not $DryRun) {
                if ($REQUIRED_PINS.ContainsKey($pkgName)) {
                    foreach ($dep in $REQUIRED_PINS[$pkgName]) {
                        if ($localStrictVersions.ContainsKey($dep)) {
                            $depVer = $localStrictVersions[$dep]
                            $pypiName = Get-PypiProjectName $dep
                            # Retry window sized to simple-index propagation:
                            # the dep may have published minutes ago in this
                            # cascade, and 60s was measured too short 2026-08-13.
                            $ok = Wait-PypiHasVersion $pypiName $depVer -TimeoutSeconds 180
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
            } elseif ($DryRun -and -not $SkipPypiCheck -and $REQUIRED_PINS.ContainsKey($pkgName)) {
                Write-Step "[DryRun] Skipping PyPI pin check (versions are simulated)"
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
                        if ($DryRun) {
                            # Sync-DevWithOrigin is skipped in DryRun, so this
                            # classification sees committed state only; a real
                            # run absorbs uncommitted local work first, which
                            # can flip this to a real merge.
                            Write-Host "    Note: [DryRun] classification excludes uncommitted local work" -ForegroundColor DarkGray
                        }
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
    # is ahead of main ONLY by non-artifact deltas (Test-OnlyDevBumpChanges:
    # the version bump, bot registry churn, CHANGELOG) — there is nothing to
    # release. Without this guard the "skipping merge" message was a no-op:
    # step 4 merged that bump to main anyway, tripping publish.yml into a
    # *phantom publish* (e.g. pythontk 0.8.77 shipped to PyPI on a re-run with
    # no real changes, then mis-tagged because $localStrictVersions still held
    # the old version). A dependency-cascade release changes pyproject.toml
    # too, so it is NOT skippable -> $needsMerge stays $true -> it still
    # merges and propagates.
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
                # Re-read the version fresh from disk rather than trusting
                # $localStrictVersions[$pkgName]: Get-LocalStrictVersions clamps
                # an unpublished local version down to PyPI's last-published one
                # (so a phantom-publish re-run doesn't think it needs a fresh
                # bump). That's correct for the bump-decision earlier, but on a
                # run that PUBLISHES a version bumped in an earlier attempt (no
                # re-bump this run -> dict entry never refreshed off the clamp),
                # this dict still holds the stale pre-bump version at tag time,
                # so the tag step tags/skips the wrong release entirely.
                $pkgSourcePath = Join-Path (Join-Path $ROOT $pkgName) $pkgName
                $releasedVersion = Get-PackageVersion $pkgSourcePath
                if (-not $releasedVersion -or $releasedVersion -eq "unknown") {
                    $releasedVersion = $localStrictVersions[$pkgName]
                }

                # Wheel-upload dependency ordering: downstream packages in this
                # same run pin (and PyPI-check) this version, so block until it
                # is actually visible on PyPI's API — the workflow's twine
                # upload completing does not mean the API reflects it yet.
                # Non-fatal on timeout: the publish itself succeeded, and the
                # downstream pin check retries + fails loudly if the version
                # still isn't visible.
                if (-not $SkipWorkflowWait -and -not $SkipPypiCheck -and $releasedVersion) {
                    $pypiName = Get-PypiProjectName $pkgName
                    if (-not (Wait-PypiHasVersion $pypiName $releasedVersion -TimeoutSeconds $PypiVisibilityTimeoutSeconds)) {
                        Write-Host "    Warning: $pypiName==$releasedVersion not visible on PyPI after ${PypiVisibilityTimeoutSeconds}s" -ForegroundColor Yellow
                    }
                    # Refresh the version map whether or not the wait confirmed:
                    # the publish itself succeeded, so downstream pins must
                    # target THIS version. Leaving the clamped pre-bump entry in
                    # place on timeout let the downstream pin check "pass"
                    # instantly against the stale published version and pin a
                    # stale floor, instead of retrying (and failing loudly)
                    # against the new one. (The map only exists in -Strict runs.)
                    if ($localStrictVersions) {
                        $localStrictVersions[$pkgName] = $releasedVersion
                    }
                }

                New-GitReleaseTag $repoPath (Get-GitHubRepoSlug $repoPath) $pkgName $releasedVersion $capturedNotes
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
        "dep-sync-failed" { Write-Err "$pkg - pyproject.toml dependency sync failed" }
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
