<#
Repository Manager (push.ps1)

Purpose
- Safely push changes on dev and (optionally) promote dev -> main in a controlled release order.
- Designed for the core package chain: pythontk -> uitk -> {mayatk, blendertk} -> tentacle
  (tentacle publishes as tentacletk on PyPI).

Release phases (Strict+Merge) — every phase is idempotent with an entry predicate, so a
re-run after ANY abort resumes at the right place instead of re-doing or skipping work.

    Finalize(entry) -> Prepare -> Push -> Merge -> Finalize(exit)

- Finalize   reconciles origin/main with PyPI and the v* tags: a version that is merged
             but unpublished gets its publish.yml dispatched; one that is published but
             untagged gets its tag + GitHub Release. Runs FIRST so a previous aborted run
             is completed before anything new is prepared, and LAST for this run's own
             release. "No changes" can never hide an unfinished release.
- Prepare    classifies the dev delta (Test-ReleaseDelta). An ARTIFACT delta (anything
             that ships, or an upstream floor that must ratchet) becomes ONE commit,
             `Release X.Y.Z`: the version (Resolve-ReleaseVersion — stepped from what is
             PUBLISHED, never from the file), the internal floors, and a fresh API
             registry. One release = one version = one commit; every version number
             reaches PyPI. A hand-edited __version__ above the published one is honored
             as a deliberate minor/major bump.
- Push       dev -> origin/dev when ahead.
- Merge      dev -> main via PR (-UsePR) or direct. A MUST-REACH-MAIN delta (.github/**,
             test/**, docs/** except the wheel's readme) merges WITHOUT a version:
             publish.yml is paths-filtered so nothing publishes. A RIDES-ALONG delta
             (registry sidecars, CHANGELOG) skips the merge and lands with the next
             release. A dead PR — a settled red check — fails in one poll, naming the
             check, instead of waiting out the timeout.

Core safety rules (Strict+Merge)
- Enforces canonical release order when multiple packages are provided.
- Stops on the first failure (build, merge conflict, workflow timeout, unsafe repo state).
- Refuses to operate if a repo has an in-progress merge/rebase/cherry-pick.
- Refuses to proceed if conflict markers exist in pyproject.toml (local OR remote origin/main|origin/dev).
- Refuses to release a real code delta without recorded "review" AND "tests" receipts
  for the current tree (release gate; receipts in .claude/receipts.json — see
  m3trik/CLAUDE.md "Release preflight"). The tests receipt is enforced, not advisory:
  mayatk and blendertk ship no pull_request-triggered tests workflow, so it is the only
  evidence their suite ever ran against the tree being published. Receipts key on a
  content hash of the SOURCE tree (generated sidecars excluded), so a registry refresh
  never voids one; Prepare re-keys them across its own Release commit.
- Keeps internal pyproject.toml pins in sync with the versions being released, and
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
    # Derived, never hardcoded: this repo is PUBLIC and owns the hygiene rule, and a
    # clone at any other path would otherwise default -Root at a drive that does not
    # exist there. push.ps1 sits at <root>/m3trik/, so the root is ONE level up (the
    # scripts/ helpers that got this same fix are two).
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
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

# Paths that are DERIVED from source by a generator and gated by CI (`generate_api_registry.py
# --check`, tentacle's parity job). They are excluded from the receipt hash: if the source is
# unchanged their content is determined, so regenerating them certifies nothing new -- and
# including them made every registry refresh void a receipt for a tree whose code had not
# moved. Git pathspec magic: `:!X` is anchored at the repo root (it does not match `sub/X`).
$API_SIDECARS = @('API_INDEX.md', 'API_REGISTRY.md', 'API_REGISTRY.json', 'API_CHANGES.md')
$GENERATED_PATHS = $API_SIDECARS + @('docs/PARITY_AUDIT.md', 'docs/PARITY_SURFACE.md')
$GENERATED_PATHSPEC = @($GENERATED_PATHS | ForEach-Object { ":!$_" })

function Get-TreeHash {
    # Content-addressed hash of the SOURCE tree: a real git tree object, built in a
    # throwaway index from the working tree with the generated sidecars excluded.
    # One sha, no text hashing -- so unlike the previous md5-of-`git diff` this is
    # immune to the host's console encoding (git emits the sha as ASCII), hashes
    # untracked files by CONTENT rather than name+size+mtime, and is unchanged by a
    # commit that touches only generated files.
    param([string]$RepoPath)
    Push-Location $RepoPath
    $prevIndex = $env:GIT_INDEX_FILE
    $indexFile = $null
    try {
        $gitDir = (git rev-parse --git-dir 2>$null)
        if (-not $gitDir) { return $null }
        if (-not [System.IO.Path]::IsPathRooted($gitDir)) {
            $gitDir = Join-Path (Get-Location).Path $gitDir
        }
        $indexFile = Join-Path $gitDir "receipt-index"
        # The env var is process-wide: every later git call in this session would
        # silently operate on the throwaway index if it leaked, so it is restored in
        # `finally` no matter how this function exits.
        $env:GIT_INDEX_FILE = $indexFile
        git read-tree --empty 2>$null | Out-Null
        git add -A -- . $GENERATED_PATHSPEC 2>$null | Out-Null
        $sha = (git write-tree 2>$null)
        if (-not $sha) { return $null }
        return $sha.Trim().Substring(0, 12)
    }
    finally {
        if ($prevIndex) { $env:GIT_INDEX_FILE = $prevIndex } else { Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue }
        if ($indexFile) { Remove-Item -LiteralPath $indexFile -Force -ErrorAction SilentlyContinue }
        Pop-Location
    }
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
            if ($GENERATED_PATHS -contains $p) { continue }
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

function Copy-ReceiptsToTree {
    # Re-key a package's EXISTING receipts from one tree hash to another. Used by
    # Prepare right after its own `Release X.Y.Z` commit: the version line and
    # the floor pins change the source hash, but the delta is push.ps1's own
    # mechanical edit on a tree whose review + tests it just verified. Without
    # this, a re-run after an abort would fail its own gate with "no receipt for
    # the current tree" - for a tree push.ps1 built. Only receipts that exist are
    # carried (timestamps included): NOTHING is manufactured, so a -SkipReview run
    # cannot leave behind a receipt a later strict run would trust. A package the
    # gate exempted (no delta of its own) gets no receipt here either - its
    # re-run is covered by Test-MechanicalDelta instead.
    param([string]$PackageName, [string]$FromHash, [string]$ToHash)
    if ($FromHash -eq $ToHash) { return }
    $map = Read-Receipts
    $fromKey = "$PackageName@$FromHash"
    if (-not $map.ContainsKey($fromKey)) { return }
    $map["$PackageName@$ToHash"] = $map[$fromKey]
    Save-Receipts $map
}

function Test-MechanicalDelta {
    # True when everything that puts dev ahead of origin/main is push.ps1's own
    # work: every commit is a `Release X.Y.Z` and the working tree is clean. That
    # is the state a cascade-extra package (no code change, only a floor ratchet)
    # is left in when a run aborts between Prepare and Merge. Such a delta was
    # exempt from the receipt gate BEFORE Prepare touched it, and nothing a human
    # wrote has been added since, so it stays exempt - honestly, without a
    # receipt being invented for it. An absorbed "Update" commit or any other
    # human commit in the range makes this false, and the gate applies.
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        if (git status --porcelain 2>$null) { return $false }
        $subjects = @(git log --pretty=%s origin/main..dev 2>$null)
        if ($subjects.Count -eq 0) { return $false }
        foreach ($s in $subjects) {
            if ($s -notmatch '^Release \d+\.\d+\.\d+$') { return $false }
        }
        return $true
    }
    finally { Pop-Location }
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

function Get-PypiVersions {
    # Every version the SIMPLE index lists for a project, yanked ones included.
    # This is the surface pip actually resolves against: the JSON API
    # (`/pypi/<name>/json`) updates ahead of it after an upload, so gating there
    # let the cascade proceed while a downstream workflow's `pip install
    # <pkg>>=<ver>` still failed with "No matching distribution found" (measured
    # 2026-08-13: the old gate confirmed uitk==1.3.76 while /simple/uitk/ still
    # listed 1.3.73). Yanked releases are deliberately kept: a yanked version's
    # filename is still TAKEN on PyPI, so stepping the next release from a list
    # that hid it would land on a number the upload then rejects.
    # Returns $null (not an empty list) when the index cannot be read, so a
    # caller can tell "offline" from "no releases".
    param([string]$ProjectName)
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
        if (-not $data) { return $null }
        if ($data.versions) { return @($data.versions | ForEach-Object { [string]$_ }) }
        # Strict PEP 691 v1.0 indexes may omit the PEP 700 `versions` key and
        # only list `files`; recover the versions from the filenames. PEP 427
        # wheels and PEP 625 sdists both use `{name}-{version}` followed by `-`
        # (wheel) or the archive suffix (sdist).
        $found = @{}
        foreach ($f in @($data.files)) {
            if ($f.filename -and ($f.filename -match '^[^-]+-(?<ver>[0-9][^-]*?)(?:-|\.tar\.gz$|\.zip$)')) {
                $found[$Matches['ver']] = $true
            }
        }
        return @($found.Keys)
    }
    catch {
        return $null
    }
}

function Test-PypiHasVersion {
    param(
        [string]$ProjectName,
        [string]$Version
    )
    $versions = Get-PypiVersions $ProjectName
    # Offline or rate-limited: fail safe in strict merge mode unless explicitly skipped.
    if ($null -eq $versions) { return $false }
    return @($versions) -contains $Version
}

function ConvertTo-VersionOrNull {
    # [version] parsing that swallows the non-semver strings PyPI can list
    # (pre-releases, post-releases, 2-part versions) instead of throwing.
    param([string]$Text)
    if ($Text -match '^\d+\.\d+\.\d+$') {
        try { return [version]$Text } catch { return $null }
    }
    return $null
}

function Get-PypiMaxVersion {
    # Highest 3-part version on the simple index, yanked included (see
    # Get-PypiVersions). $null when the index cannot be read or lists nothing.
    param([string]$ProjectName)
    $versions = Get-PypiVersions $ProjectName
    if ($null -eq $versions) { return $null }
    $max = $null
    foreach ($v in $versions) {
        $parsed = ConvertTo-VersionOrNull $v
        if ($parsed -and (-not $max -or $parsed -gt $max)) { $max = $parsed }
    }
    if ($max) { return $max.ToString() }
    return $null
}

function Get-ReleaseTags {
    # Every `vX.Y.Z` tag on ORIGIN, as [version] objects, ascending. Read with
    # `ls-remote` - a remote query, so no fetch is needed and a stale local tag
    # never misleads. Annotated tags list twice (`v1.2.3` and `v1.2.3^{}`);
    # both collapse to one entry.
    param([string]$RepoPath)
    Push-Location $RepoPath
    try {
        $found = @{}
        foreach ($line in @(git ls-remote --tags origin 'v*' 2>$null)) {
            if ($line -match 'refs/tags/v(?<ver>\d+\.\d+\.\d+)(\^\{\})?$') {
                $parsed = ConvertTo-VersionOrNull $Matches['ver']
                if ($parsed) { $found[$parsed.ToString()] = $parsed }
            }
        }
        return @($found.Values | Sort-Object)
    }
    finally { Pop-Location }
}

function Get-HighestReleaseTag {
    # Highest `vX.Y.Z` tag on origin. The second source of truth for "what is
    # published": a tag is pushed only after PyPI shows the version (Finalize),
    # so it is never ahead of PyPI, and it closes the window where the index
    # lags a just-finished publish. Under -SkipPypiCheck it is the ONLY source.
    param([string]$RepoPath)
    $tags = Get-ReleaseTags $RepoPath
    if ($tags.Count -eq 0) { return $null }
    return $tags[-1].ToString()
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

# ------------------------------------------------------------------------------------------------
# Versioning — one release = one version = one commit.
#
# The release version is decided ONCE, up front, from what is PUBLISHED — never from the
# file. Three independent bumpers used to act on each release (the post-publish bump-dev
# bot, an "auto-bump" that incremented whatever the file said, and a second bump inside
# the pin sync), so every release burned 2-3 version numbers: PyPI showed pythontk
# 0.9.26 -> 0.9.28 -> 0.9.30 and uitk 1.3.87 -> 1.3.90 -> 1.3.93 with total regularity,
# and `pythontk>=0.9.29` was a legal floor that resolved to nothing.
# ------------------------------------------------------------------------------------------------

function Get-PublishedVersion {
    # "What is installable" for one package: the max of the simple index and the
    # highest v* tag on origin. $null only when BOTH are unavailable.
    param([string]$PackageName, [string]$RepoPath)
    $candidates = @()
    if (-not $SkipPypiCheck) {
        $fromIndex = Get-PypiMaxVersion (Get-PypiProjectName $PackageName)
        if ($fromIndex) { $candidates += $fromIndex }
    }
    $fromTag = Get-HighestReleaseTag $RepoPath
    if ($fromTag) { $candidates += $fromTag }
    $max = $null
    foreach ($c in $candidates) {
        $parsed = ConvertTo-VersionOrNull $c
        if ($parsed -and (-not $max -or $parsed -gt $max)) { $max = $parsed }
    }
    if ($max) { return $max.ToString() }
    return $null
}

function Get-PublishedVersions {
    # Version map for the strict set: what each package's consumers can install
    # RIGHT NOW. A package's own entry is refreshed to its released version as
    # it finalizes in this run, so a downstream pin targets the version that was
    # actually just published.
    $versions = @{}
    foreach ($pkg in $STRICT_PACKAGES) {
        $repoPath = Join-Path $ROOT $pkg
        if (-not (Test-Path (Join-Path $repoPath ".git"))) { continue }
        $published = Get-PublishedVersion $pkg $repoPath
        if ($published) { $versions[$pkg] = $published }
    }
    return $versions
}

function Step-PatchVersion {
    param([string]$Version)
    $parts = $Version -split '\.'
    $parts[2] = [int]$parts[2] + 1
    return "$($parts[0]).$($parts[1]).$($parts[2])"
}

function Resolve-ReleaseVersion {
    # The version this release will carry.
    #   published = the run's version map entry (Get-PublishedVersions at start,
    #               refreshed by Finalize as packages release in this run), or
    #               max(simple index incl. yanked, highest v* tag) when absent
    #   local     = __version__ on dev
    #   release   = (local > published AND local not on the index) ? local
    #             : Step(published)
    # A hand-edited __version__ ABOVE the published one is a deliberate minor or
    # major bump and is honored as-is; anything else steps the patch from what is
    # published. `local > published` alone is not enough: a stale index can make
    # a just-published version look unpublished, and re-releasing it would merge
    # code to main that PyPI's copy does not have (publish.yml's exact-membership
    # probe then silently skips the upload). Returns $null when nothing
    # authoritative is reachable - the caller refuses rather than guesses.
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)
    $published = $null
    if ($Versions -and $Versions.ContainsKey($PackageName)) { $published = $Versions[$PackageName] }
    if (-not $published) { $published = Get-PublishedVersion $PackageName $RepoPath }
    if (-not $published) { return $null }
    $localText = Get-PackageVersion (Join-Path $RepoPath $PackageName)
    $local = ConvertTo-VersionOrNull $localText
    $pub = [version]$published
    if ($local -and $local -gt $pub) {
        $onIndex = $false
        if (-not $SkipPypiCheck) {
            $onIndex = Test-PypiHasVersion (Get-PypiProjectName $PackageName) $localText
        }
        if (-not $onIndex) { return $localText }
    }
    return (Step-PatchVersion $published)
}

function Set-PackageVersion {
    # Write __version__ in <pkg>/<pkg>/__init__.py (or src/__init__.py). Returns
    # $true when the file changed. Detection and replacement are both anchored
    # to the real assignment line ($VERSION_LINE, common.ps1).
    param([string]$PackagePath, [string]$Version)
    $initFile = Join-Path (Join-Path $PackagePath "src") "__init__.py"
    if (-not (Test-Path $initFile)) {
        $name = Split-Path $PackagePath -Leaf
        $initFile = Join-Path (Join-Path $PackagePath $name) "__init__.py"
    }
    if (-not (Test-Path $initFile)) { return $false }
    $content = Get-Content $initFile -Raw
    if ($content -notmatch $VERSION_LINE) { return $false }
    if ($Matches['ver'] -eq $Version) { return $false }
    $newContent = $content -replace '(?m)^__version__\s*=\s*.*', "__version__ = `"$Version`""
    Set-Content -Path $initFile -Value $newContent -NoNewline
    return $true
}

function Get-InternalPinUpdates {
    # The floor edits Update-InternalPins would make: @{ dep = @{ From; To } }.
    # Pure computation — used both to classify the delta (a floor that must
    # ratchet is an artifact change even when no code moved) and to apply it.
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)
    $updates = @{}
    if (-not $REQUIRED_PINS.ContainsKey($PackageName)) { return $updates }
    $tomlFile = Join-Path $RepoPath "pyproject.toml"
    if (-not (Test-Path $tomlFile)) { return $updates }
    $content = Get-Content $tomlFile -Raw
    foreach ($dep in $REQUIRED_PINS[$PackageName]) {
        if (-not $Versions.ContainsKey($dep)) { continue }
        $ver = $Versions[$dep]
        $pattern = '"' + $dep + '>=([0-9.]+)"'
        if ($content -notmatch $pattern) { continue }
        $currentFloor = $Matches[1]
        if ($currentFloor -eq $ver) { continue }
        # NEVER lower a declared floor. The map is what is PUBLISHED, so on a run
        # that does not include the upstream this would rewrite a deliberately-
        # raised floor back down to the old release and silently reintroduce the
        # break the raise existed to prevent (measured 2026-08-19: `-Packages
        # mayatk` alone walked `pythontk>=0.9.25` back to `>=0.9.24`, and mayatk
        # reads a 0.9.25 attribute in a CLASS BODY, i.e. AttributeError at
        # import). A floor states what the CODE needs; the sync may only ratchet
        # it UP to what it is publishing.
        $isLower = $false
        try { $isLower = ([version]$ver -lt [version]$currentFloor) } catch { $isLower = $false }
        if ($isLower) {
            Write-Host "    Keeping $dep>=$currentFloor (declared floor is above the $ver being pinned)" -ForegroundColor DarkGray
            continue
        }
        $updates[$dep] = @{ From = $currentFloor; To = $ver }
    }
    return $updates
}

function Update-InternalPins {
    # Apply Get-InternalPinUpdates to pyproject.toml. Pure edit: no version
    # bump, no commit — Prepare folds it into the single Release commit.
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)
    $updates = Get-InternalPinUpdates $PackageName $RepoPath $Versions
    if ($updates.Count -eq 0) { return $false }
    $tomlFile = Join-Path $RepoPath "pyproject.toml"
    $content = Get-Content $tomlFile -Raw
    foreach ($dep in $updates.Keys) {
        $pattern = '"' + $dep + '>=([0-9.]+)"'
        $replacement = '"' + $dep + '>=' + $updates[$dep].To + '"'
        $content = $content -replace $pattern, $replacement
        Write-Host "    Pinned $dep>=$($updates[$dep].To) (was >=$($updates[$dep].From))" -ForegroundColor Cyan
    }
    Set-Content -Path $tomlFile -Value $content -NoNewline
    return $true
}

# ------------------------------------------------------------------------------------------------
# Delta classification — what does `origin/main..dev` (plus the working tree) contain?
#   artifact        anything that ships, or an internal floor that must ratchet -> release
#   must-reach-main CI/doc files that only take effect on main               -> merge, no version
#   rides-along     generated sidecars + CHANGELOG                             -> skip; next release
#   none            nothing                                                    -> skip
# Paths that NEVER ship in the wheel. `<pkg>/__init__.py` is deliberately NOT here any more:
# with the bump-dev bot retired, a version edit on dev is a deliberate artifact change.
# pyproject.toml is an artifact (a pin change MUST publish so downstream floors propagate).
# `docs/README.md` is an artifact even though it sits under docs/: every cascade pyproject
# names it as the wheel's `readme`, so editing it changes the published metadata.
# ------------------------------------------------------------------------------------------------
$MUST_REACH_MAIN_PATHS = @('.github/', 'test/', 'docs/')
$ARTIFACT_EXCEPTIONS = @('docs/README.md')
$RIDES_ALONG_PATHS = $API_SIDECARS + @('CHANGELOG.md')

function Get-DeltaClass {
    # Classify one repo-relative path.
    param([string]$Path)
    if ($ARTIFACT_EXCEPTIONS -contains $Path) { return 'artifact' }
    foreach ($p in $MUST_REACH_MAIN_PATHS) {
        if ($p.EndsWith('/')) { if ($Path.StartsWith($p)) { return 'must-reach-main' } }
        elseif ($Path -eq $p) { return 'must-reach-main' }
    }
    if ($RIDES_ALONG_PATHS -contains $Path) { return 'rides-along' }
    return 'artifact'
}

function Test-ReleaseDelta {
    # The strongest class present in origin/main..dev + the working tree, plus a
    # pending floor ratchet. Diffs ORIGIN/main: local `main` never advances under
    # PR merges, so diffing it would re-merge an already-released dev forever.
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)
    Push-Location $RepoPath
    try {
        git fetch origin main --quiet 2>&1 | Out-Null
        $files = @(git diff --name-only origin/main..dev 2>$null)
        $files += @(git status --porcelain 2>$null | ForEach-Object {
            $p = $_.Substring(3).Trim('"')
            if ($p -match ' -> ') { $p = ($p -split ' -> ')[-1] }
            $p
        })
    }
    finally { Pop-Location }
    $rank = @{ 'none' = 0; 'rides-along' = 1; 'must-reach-main' = 2; 'artifact' = 3 }
    $best = 'none'
    foreach ($f in ($files | Where-Object { $_ } | Select-Object -Unique)) {
        $c = Get-DeltaClass $f
        if ($rank[$c] -gt $rank[$best]) { $best = $c }
    }
    if ($best -ne 'artifact' -and $Versions) {
        if ((Get-InternalPinUpdates $PackageName $RepoPath $Versions).Count -gt 0) { $best = 'artifact' }
    }
    return $best
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

        # The NEWEST completed run for this sha is the verdict. A re-dispatch
        # after a failed run leaves the failure in the list; judging "any run
        # failed" would report the retry as red no matter how it went.
        $newest = @($matching | Sort-Object { [DateTime]$_.createdAt } -Descending)[0]
        if ($newest.conclusion -and $newest.conclusion -ne "success") { return $newest.conclusion }

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
    $dispatchedAt = $null
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
        # A failed run gets ONE re-dispatch. A flaky test job or an index-lag
        # Verify-Install timeout is the common cause, and the publish job is
        # idempotent (exact-membership PyPI probe + `--skip-existing`), so a
        # retry can at worst fail the same way. A second failure stands.
        if (-not $dispatched) {
            Write-Host "    Workflow concluded with '$verdict'; re-dispatching publish.yml once..." -ForegroundColor Yellow
            gh workflow run $WorkflowFile --repo $repoSlug --ref main 2>&1 | Out-Null
            $dispatched = $true
            $dispatchedAt = $elapsed
            continue
        }
        # Until the re-dispatched run is queued, the old failure is still the
        # newest completed run; give GitHub a grace window before believing it.
        if ($null -ne $dispatchedAt -and ($elapsed - $dispatchedAt) -lt 90) { continue }
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
    $failed = @()
    foreach ($c in $rollup) {
        $conclusion = ""
        $stateVal = ""
        if ($c.PSObject.Properties['conclusion']) { $conclusion = [string]$c.conclusion }
        if ($c.PSObject.Properties['state']) { $stateVal = [string]$c.state }
        $settled = $conclusion -or ($stateVal -and $stateVal -ne "PENDING" -and $stateVal -ne "EXPECTED")
        if (-not $settled) { $pending++ }
        # A settled check that did not succeed. NEUTRAL and SKIPPED count as
        # success for merge purposes; anything else is red. GitHub blocks the
        # merge itself when such a check is REQUIRED (mergeStateStatus BLOCKED),
        # so what lands here is specifically the red checks that do NOT block -
        # the ones that used to ship unmentioned.
        elseif ($conclusion -and $conclusion -notin @('SUCCESS', 'NEUTRAL', 'SKIPPED')) {
            $failed += [string]$c.name
        }
        elseif (-not $conclusion -and ($stateVal -eq 'FAILURE' -or $stateVal -eq 'ERROR')) {
            $failed += [string]$c.context
        }
    }

    return [PSCustomObject]@{
        CheckCount       = $rollup.Count
        PendingCount     = $pending
        FailedChecks     = @($failed)
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
      pull_request. Compare branch protection's required contexts against the job
      names in the repo's tests.yml / static-analysis.yml.
  Give the repo a real gate, or re-run WITHOUT -UsePR to merge deliberately ungated.
"@ -ForegroundColor Yellow
        return $false
    }

    if ($state.FailedChecks.Count -gt 0) {
        # Emitted BEFORE the BLOCKED branches so every outcome names them: the
        # transient 'BLOCKED, checks still running' path also returns $true, and a
        # red non-required check riding along there would otherwise ship unmentioned
        # - which is exactly how 'Validate Publish Chain' stayed FAILURE across
        # pythontk #48 and #49 without anyone noticing. Reporting, not blocking:
        # whether a red check may hold a merge is branch protection's call, and
        # GitHub already enforces that for REQUIRED checks by way of BLOCKED.
        Write-Host "  !! PR #$PrNumber has $($state.FailedChecks.Count) check(s) reporting FAILURE:" -ForegroundColor Yellow
        foreach ($checkName in $state.FailedChecks) {
            Write-Host "       x $checkName" -ForegroundColor Red
        }
        Write-Host "     GitHub holds the merge only for REQUIRED checks; any others here ship as-is." -ForegroundColor Yellow
        Write-Host "     Inspect: gh pr view $PrNumber --repo $RepoSlug --json statusCheckRollup" -ForegroundColor Yellow
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

    # A re-run after an abort finds the PR already armed (Ensure-ReleasePR reuses
    # the open PR). Re-issuing `--auto` on an armed PR is not documented to be
    # idempotent, so probe and skip rather than find out.
    $armedJson = gh pr view $PrNumber --repo $RepoSlug --json autoMergeRequest 2>$null
    if ($LASTEXITCODE -eq 0 -and $armedJson) {
        try {
            $armed = ($armedJson | ConvertFrom-Json).autoMergeRequest
            if ($armed) {
                Write-Skip "Auto-merge already armed on PR #$PrNumber"
                return $true
            }
        } catch {}
    }

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
    # Poll until the PR merges - or until branch protection is provably holding
    # it, which is reported in one poll instead of waited out. The old loop read
    # only `state,mergedAt` and sat on a permanently-blocked PR for the full
    # 1800 s on 2026-08-23 after uitk's required `test` failed at minute 17,
    # then aborted three unprocessed packages.
    #
    # DEAD requires mergeStateStatus BLOCKED. A red check alone is NOT death: a
    # check that is not REQUIRED leaves the PR mergeable and auto-merge lands it
    # anyway (measured - pythontk #48 and #49 both merged carrying settled
    # FAILUREs on `summary` and `validate-tentacle`). Blocking on those would
    # abort releases GitHub was about to complete, and it would contradict the
    # arm-time gate, which reports red non-required checks without blocking
    # because whether a check may hold a merge is branch protection's call.
    # mayatk/blendertk make this concrete: their required check is
    # `static-analysis`, and both now carry additional non-required Qt/mock
    # suites on every PR.
    #
    # Two states LOOK dead and are not, so they keep polling:
    #   * BLOCKED with 0 pending and 0 failed — the window between the last
    #     check going green and GitHub recomputing mergeStateStatus. Crossed on
    #     every successful release; only after 6 consecutive polls (60 s) is it
    #     called (a required check that is not attached, or a missing review).
    #   * ZERO check runs — a fresh head (the operator pushed a fix mid-wait)
    #     whose checks GitHub has not attached yet.
    # Returns "merged", "dead", "closed", or "timeout".
    param(
        [string]$RepoSlug,
        [int]$PrNumber,
        [int]$TimeoutSeconds
    )

    $elapsed = 0
    $quietBlocked = 0
    $reportedFailures = $false
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
                return "merged"
            }
            if ($v.state -eq "CLOSED") {
                Write-Err "PR #$PrNumber closed without merge"
                return "closed"
            }
        }
        catch {
            continue
        }

        $state = Get-PRGateState $RepoSlug $PrNumber
        if ($state) {
            if ($state.MergeStateStatus -eq "DIRTY") {
                Write-Err "PR #$PrNumber has merge conflicts (mergeStateStatus=DIRTY)"
                return "dead"
            }
            # Red checks are REPORTED once, whether or not they block: on a
            # non-required check this is the only mention the operator gets
            # before the PR merges over it.
            if ($state.FailedChecks.Count -gt 0 -and -not $reportedFailures) {
                $reportedFailures = $true
                Write-Host "  !! PR #$PrNumber has $($state.FailedChecks.Count) check(s) reporting FAILURE:" -ForegroundColor Yellow
                foreach ($checkName in $state.FailedChecks) {
                    Write-Host "       x $checkName" -ForegroundColor Red
                }
            }
            if ($state.MergeStateStatus -eq "BLOCKED" -and $state.CheckCount -gt 0 -and $state.PendingCount -eq 0) {
                if ($state.FailedChecks.Count -gt 0) {
                    # BLOCKED with everything settled and something red: branch
                    # protection is holding this PR on a REQUIRED check, and
                    # nothing left to run can clear it.
                    Write-Err "PR #$PrNumber cannot merge: branch protection is holding it and every check has settled."
                    Write-Host "     Red: $($state.FailedChecks -join ', ')" -ForegroundColor Red
                    Write-Host "     Fix on dev and push; auto-merge stays armed and a green re-run lands the PR." -ForegroundColor Yellow
                    Write-Host "     Then re-run push.ps1 - Finalize picks the merged release up from origin/main." -ForegroundColor Yellow
                    Write-Host "     Inspect: gh pr view $PrNumber --repo $RepoSlug --json statusCheckRollup" -ForegroundColor Yellow
                    return "dead"
                }
                $quietBlocked++
                if ($quietBlocked -ge 6) {
                    Write-Err "PR #$PrNumber has been BLOCKED with every check green for $($quietBlocked * 10)s."
                    Write-Host "     No failing check - a REQUIRED check is not attached to this PR, or a review is required." -ForegroundColor Yellow
                    Write-Host "     Inspect: gh pr view $PrNumber --repo $RepoSlug --json mergeStateStatus,statusCheckRollup" -ForegroundColor Yellow
                    return "dead"
                }
            } else {
                $quietBlocked = 0
            }
        }

        if ($elapsed % 60 -eq 0) {
            Write-Host "    Waiting for PR merge... ($elapsed/$TimeoutSeconds seconds)" -ForegroundColor Gray
        }
    }

    Write-Host "    Warning: Timeout waiting for PR merge (${TimeoutSeconds}s)" -ForegroundColor Yellow
    Write-Host "    Stopping process - check PR status manually" -ForegroundColor Red
    return "timeout"
}

function Merge-ToMainViaPR {
    # Returns "merged", "dead", "closed", "timeout", or $false (setup failure).
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

function Get-ReleaseNotes {
    # CHANGELOG.md lines added between the previous release tag and origin/main:
    # the curated notes for the tag + GitHub Release. Keyed on TAGS, not on
    # `origin/main..dev` - the old delta was empty the moment the PR merged, so a
    # run that aborted after the merge could never reconstruct the notes and
    # the Release body had to be rebuilt by hand (26 KB of it, 2026-08-23).
    # With no previous tag there is no boundary; the Release is tag-only.
    # Caller has fetched origin/main and the tags (Invoke-FinalizePhase does).
    param([string]$RepoPath, [string]$Version)
    $target = [version]$Version
    $prev = $null
    foreach ($t in (Get-ReleaseTags $RepoPath)) {
        if ($t -lt $target) { $prev = $t }
    }
    if (-not $prev) { return "" }
    Push-Location $RepoPath
    try {
        if (-not (Test-Path "CHANGELOG.md")) { return "" }
        $diff = git diff "v$prev..origin/main" -- CHANGELOG.md 2>$null
        if (-not $diff) { return "" }
        $added = $diff |
            Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' } |
            ForEach-Object { $_.Substring(1) }
        return (($added -join "`n").Trim())
    }
    finally { Pop-Location }
}

function Test-GitHubReleaseExists {
    param([string]$RepoSlug, [string]$Tag)
    if (-not $RepoSlug -or -not (Get-Command gh -ErrorAction SilentlyContinue)) { return $false }
    gh release view $Tag --repo $RepoSlug --json tagName 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Complete-Release {
    # Tag v<Version> at origin/main and cut the GitHub Release, each only if
    # absent. Both probes run every time: a previous run may have pushed the
    # tag and then failed on the Release, and "tag exists" must not hide
    # "Release missing". Non-fatal: the publish + merge already succeeded, so
    # the worst case is a re-run. Returns $true when anything was done.
    # Caller has fetched origin/main and the tags.
    param(
        [string]$RepoPath,
        [string]$RepoSlug,
        [string]$PackageName,
        [string]$Version
    )
    if (-not $Version) { return $false }
    $tag = "v$Version"
    $did = $false
    Push-Location $RepoPath
    try {
        $existing = git ls-remote --tags origin $tag 2>$null
        if (-not $existing) {
            $sha = (git rev-parse origin/main 2>$null)
            if ($LASTEXITCODE -ne 0 -or -not $sha) {
                Write-Err "Cannot resolve origin/main for tag $tag"
                return $false
            }
            $sha = $sha.Trim()
            # -f so a stale local tag from a prior failed run is re-pointed at the
            # released SHA (the ls-remote guard above already prevents re-tagging an
            # existing *remote* release, so this only ever fixes a local-only tag).
            git tag -f -a $tag $sha -m "$PackageName $tag" 2>&1 | Out-Null
            git push origin $tag 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Failed to push tag $tag (create manually)"
                return $false
            }
            Write-Success "Tagged $tag"
            $did = $true
        }

        if (-not $RepoSlug -or -not (Get-Command gh -ErrorAction SilentlyContinue)) { return $did }
        if (Test-GitHubReleaseExists $RepoSlug $tag) { return $did }

        $notes = Get-ReleaseNotes $RepoPath $Version
        if (-not $notes) {
            Write-Skip "No CHANGELOG additions for $tag (tag-only, no Release)"
            return $did
        }
        $tmp = [System.IO.Path]::GetTempFileName()
        try {
            [System.IO.File]::WriteAllText($tmp, $notes, (New-Object System.Text.UTF8Encoding $false))
            $out = gh release create $tag --repo $RepoSlug --title "$PackageName $tag" --notes-file $tmp --target main 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "GitHub Release $tag created"
                $did = $true
            } else {
                Write-Err "GitHub Release $tag failed (tag pushed; re-run to retry)"
                if ($out) { Write-Host "    $out" -ForegroundColor DarkGray }
            }
        }
        finally {
            Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        }
        return $did
    }
    catch {
        Write-Err "Tag/release step error for $tag : $_"
        return $did
    }
    finally {
        Pop-Location
    }
}

function Get-MainVersion {
    # __version__ as committed on origin/main - never the working tree, which
    # may already hold the NEXT release's version. Caller has fetched origin/main.
    param([string]$PackageName, [string]$RepoPath)
    Push-Location $RepoPath
    try {
        $content = git show "origin/main:$PackageName/__init__.py" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $content) { return $null }
        $joined = ($content -join "`n")
        if ($joined -match $VERSION_LINE) { return $Matches['ver'] }
        return $null
    }
    finally { Pop-Location }
}

function Invoke-FinalizePhase {
    # Reconcile origin/main with PyPI and the v* tags. Idempotent; runs at
    # package ENTRY (so a previous aborted run is completed before anything new
    # is prepared) and at EXIT (for this run's own release). Returns one of:
    #   "noop"       main's version is tagged and released (or nothing to do)
    #   "finalized"  tagged and/or released this call
    #   "failed"     publish failed or PyPI never showed the version
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)

    # The ONE fetch for this phase; every helper below reads origin/main and the
    # tags as fetched here.
    Push-Location $RepoPath
    try { git fetch origin main --tags --quiet 2>&1 | Out-Null } finally { Pop-Location }

    $mainVer = Get-MainVersion $PackageName $RepoPath
    if (-not $mainVer) { return "noop" }
    $tag = "v$mainVer"
    $repoSlug = Get-GitHubRepoSlug $RepoPath
    $pypiName = Get-PypiProjectName $PackageName
    $tagged = @(Get-ReleaseTags $RepoPath | ForEach-Object { $_.ToString() }) -contains $mainVer

    # Fast exit: tagged, and either the Release exists or there is no GitHub to
    # hold one (local origin / no gh) - nothing this phase could add.
    if ($tagged) {
        $canRelease = $repoSlug -and (Get-Command gh -ErrorAction SilentlyContinue)
        if (-not $canRelease -or (Test-GitHubReleaseExists $repoSlug $tag)) { return "noop" }
    }

    $onIndex = $SkipPypiCheck -or (Test-PypiHasVersion $pypiName $mainVer)
    if (-not $onIndex) {
        # main carries a version PyPI does not have. Either publish.yml is still
        # running / failed, or this was a workflow-only merge whose version is the
        # previous (already tagged) release and publish.yml was paths-filtered out.
        if ($tagged) { return "noop" }
        if ($SkipWorkflowWait) {
            Write-Skip "Workflow wait skipped; $pypiName==$mainVer not yet on PyPI - finalize later"
            return "noop"
        }
        Write-Step "origin/main carries $PackageName $mainVer, not yet on PyPI - waiting for publish.yml..."
        if (-not (Wait-ForWorkflow $RepoPath $PackageName)) {
            Write-Err "publish.yml did not succeed for $PackageName $mainVer"
            return "failed"
        }
        if (-not (Wait-PypiHasVersion $pypiName $mainVer -TimeoutSeconds $PypiVisibilityTimeoutSeconds)) {
            # BLOCKING, unlike the old tail: a tag is a promise that the version is
            # installable, and downstream pins in this run target it.
            Write-Err "$pypiName==$mainVer not visible on PyPI after ${PypiVisibilityTimeoutSeconds}s - not tagging"
            return "failed"
        }
    }
    if ($Versions) { $Versions[$PackageName] = $mainVer }

    if (Complete-Release $RepoPath $repoSlug $PackageName $mainVer) { return "finalized" }
    return "noop"
}

function Invoke-PreparePhase {
    # Turn an ARTIFACT delta into exactly one `Release X.Y.Z` commit on dev.
    # Returns a hashtable: @{ Class; Version; Committed } or $null on failure.
    param([string]$PackageName, [string]$RepoPath, [hashtable]$Versions)

    if ($Merge -and -not $DryRun) {
        # Sync local dev with origin BEFORE deciding anything. Absorbs uncommitted
        # work as its own commit (same as before) and rebases onto origin/dev.
        if (-not (Sync-DevWithOrigin $RepoPath -CommitMessage $CommitMessage)) {
            Write-Err "Pre-release sync failed"
            return $null
        }
    }

    $class = Test-ReleaseDelta $PackageName $RepoPath $Versions
    Write-Host "  Delta: $class" -ForegroundColor White
    $result = @{ Class = $class; Version = $null; Committed = $false }
    if ($class -ne 'artifact') { return $result }

    $version = Resolve-ReleaseVersion $PackageName $RepoPath $Versions
    if (-not $version) {
        Write-Err "Cannot resolve a release version for $PackageName : neither PyPI nor a v* tag is reachable."
        Write-Err "Come online, or push a tag for the last published version, or use -SkipPypiCheck with tags present."
        return $null
    }
    $result.Version = $version
    $pkgSource = Join-Path $RepoPath $PackageName
    $currentVer = Get-PackageVersion $pkgSource

    if ($DryRun) {
        if ($currentVer -ne $version) { Write-Step "[DryRun] Would release $PackageName $version (from $currentVer)" }
        else { Write-Step "[DryRun] Would release $PackageName $version (version already set on dev)" }
        $pins = Get-InternalPinUpdates $PackageName $RepoPath $Versions
        foreach ($dep in $pins.Keys) {
            Write-Step "[DryRun] Would pin $dep>=$($pins[$dep].To) (was >=$($pins[$dep].From))"
        }
        Write-Step "[DryRun] Would regenerate the API registry and commit 'Release $version'"
        # Downstream DryRun classification must see this package as published at
        # its would-be version, exactly as a real run refreshes the map in Finalize.
        if ($Versions) { $Versions[$PackageName] = $version }
        return $result
    }

    $preHash = Get-TreeHash $RepoPath
    Push-Location $RepoPath
    try {
        git checkout dev --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Err "Checkout dev failed (prepare)"; return $null }

        $changed = $false
        if (Set-PackageVersion $RepoPath $version) {
            Write-Host "    Version: $currentVer -> $version" -ForegroundColor Cyan
            $changed = $true
        }
        if (Update-InternalPins $PackageName $RepoPath $Versions) { $changed = $true }

        # A current registry in the release commit, so main always carries one and
        # the PR's `API registry up to date` check is green by construction. Runs
        # under the venv python (AST-only; no DCC import). --no-shadows keeps the
        # cross-package shadow report — which lives in m3trik's tree — untouched.
        $gen = Join-Path (Join-Path $ROOT "m3trik") "scripts\generate_api_registry.py"
        if (Test-Path $gen) {
            $genOut = python $gen $PackageName --no-shadows 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Err "API registry regeneration failed for $PackageName"
                if ($genOut) { Write-Host "    $genOut" -ForegroundColor DarkGray }
                return $null
            }
        }
        if (git status --porcelain) { $changed = $true }

        if ($changed) {
            git add -A
            # Deliberately NOT tagged [skip ci]: this commit heads the dev branch the
            # release PR is opened from, and GitHub skips every workflow (tests.yml
            # included) for a [skip ci] head -- which is exactly how -UsePR once came
            # to merge release PRs that had never run a single check.
            git commit -m "Release $version" | Out-Null
            if ($LASTEXITCODE -ne 0) { Write-Err "Release commit failed"; return $null }
            Write-Success "Committed 'Release $version'"
            $result.Committed = $true
        } else {
            Write-Skip "dev already carries Release $version"
        }
    }
    finally { Pop-Location }

    # The version line and floors moved the source hash; the tree is push.ps1's
    # own mechanical edit on a tree whose receipts were just verified (or which
    # was exempt). Carry them across so a re-run after an abort passes its gate.
    $postHash = Get-TreeHash $RepoPath
    Copy-ReceiptsToTree $PackageName $preHash $postHash

    # Upstream floors this release pins must already be installable.
    if (-not $SkipPypiCheck -and $REQUIRED_PINS.ContainsKey($PackageName)) {
        foreach ($dep in $REQUIRED_PINS[$PackageName]) {
            if (-not $Versions.ContainsKey($dep)) { continue }
            $depVer = $Versions[$dep]
            $pypiName = Get-PypiProjectName $dep
            # Retry window sized to simple-index propagation: the dep may have
            # published minutes ago in this cascade (60s was measured too short 2026-08-13).
            if (-not (Wait-PypiHasVersion $pypiName $depVer -TimeoutSeconds 180)) {
                Write-Err "PyPI does not show $pypiName==$depVer yet (or cannot be reached)."
                Write-Err "Use -SkipPypiCheck to override, but this can break installs."
                return $null
            }
        }
    }
    return $result
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
# "What is installable" per strict package (PyPI simple index ∪ v* tags). Each
# package's entry is refreshed to its released version as it finalizes in this
# run, so a downstream pin targets what was actually just published.
$publishedVersions = $null
if ($Strict) {
    $publishedVersions = Get-PublishedVersions
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
        # Only an ARTIFACT delta — something that ships, or a floor that must ratchet —
        # needs review + tests. A CI-only or sidecar-only delta merges without a
        # version (or not at all) and never reaches PyPI.
        $gateClass = Test-ReleaseDelta $gateName $gatePath $publishedVersions
        if ($gateClass -ne 'artifact') {
            Write-Skip "Review gate: $gateName delta is $gateClass (exempt)"
            continue
        }
        if (Test-MechanicalDelta $gatePath) {
            Write-Skip "Review gate: $gateName is ahead only by push.ps1's own Release commit (exempt)"
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

    # 0. Repo Safety Preflight
    if (-not (Test-RepoOperationSafe $repoPath)) {
        $results[$pkgName] = "unsafe-repo"
        $anyErrors = $true
        Write-Err "Repository is not in a safe state for automation"
        if ($stopOnFailure) { break }
        continue
    }
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

    # 1. Finalize (entry): complete a previous run's merged-but-unfinished release
    #    BEFORE preparing anything new, so the version map and tags are truthful.
    $finalizedOnEntry = $false
    if ($Strict -and $isStrictPackage -and $Merge -and -not $DryRun) {
        $entry = Invoke-FinalizePhase $pkgName $repoPath $publishedVersions
        if ($entry -eq "failed") {
            $results[$pkgName] = "workflow-failed"
            $anyErrors = $true
            Write-Err "A previously merged release could not be finalized - aborting remaining packages"
            break
        }
        if ($entry -eq "finalized") { $finalizedOnEntry = $true }
    }

    # 2. Prepare
    $prepared = @{ Class = 'artifact'; Version = $null; Committed = $false }
    if ($Strict -and $isStrictPackage) {
        if ($Merge) {
            $prepared = Invoke-PreparePhase $pkgName $repoPath $publishedVersions
            if (-not $prepared) {
                $results[$pkgName] = "prepare-failed"
                $anyErrors = $true
                if ($stopOnFailure) { break }
                continue
            }
        }
        if ($prepared.Class -eq 'artifact') {
            if (-not $DryRun -and -not $SkipBuild) {
                # Known transient: `[Errno 13] Permission denied` with no path
                # (cloud-sync / AV briefly holding a file in dist/ or build/).
                # Re-running usually succeeds; -SkipBuild is the escape hatch.
                if (-not (Test-Build $pkgName $repoPath)) {
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
        }
    } elseif ($Strict) {
        Write-Skip "Strict mode not supported for $pkgName (skipping build check)"
    }

    # 3. Push dev when ahead of its upstream (or dirty, in non-merge mode).
    Push-Location $repoPath
    try {
        $dirty = [bool](git status --porcelain 2>$null)
        $aheadOfOrigin = 0
        $upstream = (git rev-parse --abbrev-ref "@{u}" 2>$null)
        if ($upstream) { $a = git rev-list --count "$upstream..HEAD" 2>$null; if ($a) { $aheadOfOrigin = [int]$a } }
        git fetch origin main --quiet 2>&1 | Out-Null
        $aheadOfMain = 0
        $m = git rev-list --count "origin/main..dev" 2>$null
        if ($m) { $aheadOfMain = [int]$m }
    }
    finally { Pop-Location }
    $hasChanges = $dirty -or ($aheadOfOrigin -gt 0)

    # Merge when dev is ahead of ORIGIN/main by anything that must reach main.
    $needsMerge = $Merge -and ($aheadOfMain -gt 0) -and ($prepared.Class -in @('artifact', 'must-reach-main'))
    if ($Merge -and $aheadOfMain -gt 0 -and $prepared.Class -eq 'rides-along') {
        Write-Skip "Dev is ahead of main by sidecars/CHANGELOG only (rides along with the next release)"
    }

    if (-not $hasChanges -and -not $needsMerge) {
        if ($finalizedOnEntry) { $results[$pkgName] = "finalized" }
        else { Write-Skip "No changes to push and fully merged"; $results[$pkgName] = "skipped" }
        continue
    }
    if ($hasChanges) { Write-Host "  Has changes to push" -ForegroundColor White }
    if ($needsMerge) { Write-Host "  Dev is ahead of main (needs merge)" -ForegroundColor White }

    if ($hasChanges) {
        if ($DryRun) {
            Write-Step "[DryRun] Would push dev branch"
        } else {
            if (-not (Push-DevBranch $repoPath)) {
                $results[$pkgName] = "push-failed"
                $anyErrors = $true
                Write-Err "Push failed - skipping merge"
                if ($stopOnFailure) { break }
                continue
            }
        }
    }

    # 4. Merge to main
    if ($needsMerge) {
        if (-not (Test-MergeConflicts $repoPath)) {
            $results[$pkgName] = "merge-conflict"
            $anyErrors = $true
            Write-Err "Merge conflicts detected - skipping merge"
            if ($stopOnFailure) { break }
            continue
        }
        if ($DryRun) {
            if ($prepared.Class -eq 'must-reach-main') { Write-Step "[DryRun] Would merge to main WITHOUT a version (CI/docs-only delta)" }
            else { Write-Step "[DryRun] Would merge to main and push" }
        } else {
            $mergeOk = $false
            if ($UsePR) {
                $verdict = Merge-ToMainViaPR $repoPath $pkgName
                if ($verdict -eq "merged") { $mergeOk = $true }
                elseif ($verdict -eq "dead") { $results[$pkgName] = "merge-dead" }
                else { $results[$pkgName] = "merge-failed" }
            } else {
                $mergeOk = [bool](Merge-ToMain $repoPath)
                if (-not $mergeOk) { $results[$pkgName] = "merge-failed" }
            }
            if (-not $mergeOk) {
                $anyErrors = $true
                Write-Err "Merge did not complete"
                if ($stopOnFailure) { break }
                continue
            }
        }
    }

    # 5. Finalize (exit): this run's own release — wait for publish, PyPI, tag, Release.
    if ($Strict -and $isStrictPackage -and $Merge -and -not $DryRun -and $prepared.Class -eq 'artifact' -and $needsMerge) {
        $exit = Invoke-FinalizePhase $pkgName $repoPath $publishedVersions
        if ($exit -eq "failed") {
            $results[$pkgName] = "workflow-failed"
            $anyErrors = $true
            Write-Err "Workflow failed or timed out - aborting remaining packages"
            break
        }
        $results[$pkgName] = "released"
    } elseif ($needsMerge -and $prepared.Class -eq 'must-reach-main') {
        $results[$pkgName] = "merged"
    } elseif ($finalizedOnEntry) {
        $results[$pkgName] = "finalized"
    } elseif ($DryRun) {
        $results[$pkgName] = "dry-run"
    } else {
        $results[$pkgName] = "success"
    }
}

# Summary
Write-Header "Summary"

foreach ($repo in $reposToProcess) {
    $pkg = $repo.Name
    $status = $results[$pkg]
    switch ($status) {
        "released" { Write-Success "$pkg - Released" }
        "merged" { Write-Success "$pkg - Merged to main (no version: CI/docs-only delta)" }
        "finalized" { Write-Success "$pkg - Finalized a previously merged release" }
        "success" { Write-Success "$pkg - Completed" }
        "skipped" { Write-Skip "$pkg - No changes" }
        "prepare-failed" { Write-Err "$pkg - Release preparation failed" }
        "build-failed" { Write-Err "$pkg - Build failed" }
        "push-failed" { Write-Err "$pkg - Push failed" }
        "merge-dead" { Write-Err "$pkg - PR cannot merge (conflict, a red REQUIRED check, or a missing review; see above)" }
        "merge-failed" { Write-Err "$pkg - Merge failed" }
        "merge-conflict" { Write-Err "$pkg - Merge conflicts" }
        "workflow-failed" { Write-Err "$pkg - Workflow failed/timed out" }
        "unsafe-repo" { Write-Err "$pkg - Unsafe repo state" }
        "dry-run" { Write-Host "  o $pkg - Dry Run OK" -ForegroundColor Cyan }
        default { Write-Host "  ? $pkg - Not processed" -ForegroundColor DarkGray }
    }
}

if ($anyErrors) {
    exit 1
}
