<#
.SYNOPSIS
  Runtime-vs-static API drift check across the ecosystem (the DCC half of the
  drift gate).

.DESCRIPTION
  The static registry walker (generate_api_registry.py) cannot import Maya / Qt /
  Blender, so metaclass / mixin / dynamically-composed members are invisible to
  it. This dumps each package's LIVE HelpMixin surface - from a fresh,
  session-safe DCC instance where one is needed - and diffs it against the
  committed registry via verify_runtime_surface.py.

  Runs where the runtimes actually exist (a local workstation), NOT cloud CI
  (ubuntu, no DCC). Graceful degradation: a package whose runtime is unavailable
  on this machine (mayapy / blender / Qt missing) is SKIPPED, never a failure. A
  DCC dump is preceded by deleting its artifact, so a failed dump leaves none and
  the verify SKIPs rather than comparing against stale data.

.NOTES
  verify_runtime_surface exit codes: 0 = clean, 1 = missing-member drift (FAIL -
  the registry promises a member the live class lacks), 2 = runtime unavailable /
  empty (SKIP). advisory 'added' / 'kind_changed' notes never fail.

  Exit code: 0 = no drift, 1 = at least one package FAILed.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = 'o:\Cloud\Code\_scripts',
    [string]$LogPath  = "$env:LOCALAPPDATA\claude-runtime-surface.log"
)

$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$tool = Join-Path $RepoRoot 'm3trik\scripts\verify_runtime_surface.py'

$results = New-Object System.Collections.Generic.List[string]
$script:failed = $false

function Record([string]$status, [string]$pkg, [string]$note = '') {
    $suffix = if ($note) { " ($note)" } else { '' }
    $line = ('{0,-4} {1}{2}' -f $status, $pkg, $suffix)
    $results.Add($line); Write-Host $line
    if ($status -eq 'FAIL') { $script:failed = $true }
}

function Invoke-Verify([string]$pkg, [string[]]$extra = @()) {
    $out = & $py $tool verify $pkg @extra   # stdout captured; stderr -> host
    $rc = $LASTEXITCODE
    switch ($rc) {
        0 { Record 'OK'   $pkg }
        2 { Record 'SKIP' $pkg 'runtime unavailable' }
        default { Record 'FAIL' $pkg 'registry promises a live-missing member' }
    }
    foreach ($l in $out) {
        if ($l -match '^\s+(FAIL|note)') { $results.Add("      $l") }
    }
}

Push-Location $RepoRoot
try {
    # pythontk - DCC-free, importable in-process.
    Invoke-Verify 'pythontk'

    # uitk - needs a Qt binding; offscreen so no display is required.
    $env:QT_QPA_PLATFORM = 'offscreen'; $env:QT_API = 'pyside6'
    Invoke-Verify 'uitk'
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue

    # mayatk - fresh headless standalone (mayapy).
    $mayapy = Get-ChildItem 'C:\Program Files\Autodesk\Maya*\bin\mayapy.exe' -ErrorAction SilentlyContinue |
              Select-Object -First 1
    if ($mayapy) {
        $art = Join-Path $RepoRoot 'mayatk\API_RUNTIME.json'
        Remove-Item $art -ErrorAction SilentlyContinue
        & $mayapy.FullName (Join-Path $RepoRoot 'mayatk\test\dump_runtime_surface.py') | Out-Null
        Invoke-Verify 'mayatk' @('--runtime', $art)
    } else { Record 'SKIP' 'mayatk' 'mayapy not found' }

    # blendertk - fresh headless Blender.
    $blender = Get-ChildItem 'C:\Program Files\Blender Foundation\*\blender.exe' -ErrorAction SilentlyContinue |
               Select-Object -First 1
    if ($blender) {
        $art = Join-Path $RepoRoot 'blendertk\API_RUNTIME.json'
        Remove-Item $art -ErrorAction SilentlyContinue
        & $blender.FullName --background --factory-startup --python (Join-Path $RepoRoot 'blendertk\test\dump_runtime_surface.py') | Out-Null
        Invoke-Verify 'blendertk' @('--runtime', $art)
    } else { Record 'SKIP' 'blendertk' 'blender not found' }
}
finally { Pop-Location }

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$body  = "===== $stamp (drift=$([int]$script:failed)) =====`n" + ($results -join "`n")
Add-Content -Path $LogPath -Value $body -Encoding UTF8

if ($script:failed) { exit 1 } else { exit 0 }
