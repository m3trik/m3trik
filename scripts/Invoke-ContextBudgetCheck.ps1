<#
.SYNOPSIS
  Weekly context-budget check for the Claude agent context surface.

.DESCRIPTION
  Runs check_context_budget.py against the repo + the local Claude auto-memory
  dir, appends the result to a log, and raises a Windows toast on a hard FAIL or
  when MEMORY.md is within 2 KB of its 24,400-byte load cap. Driven by the
  'ClaudeContextBudget' Scheduled Task. The log is the durable record; the toast
  is best-effort (skipped silently in a non-interactive session).

  The guard runs with --no-registry --no-runtime here. --no-registry: this repo
  lives on a Nextcloud cloud-synced drive (O:) where reading a just-written .json
  sidecar can transiently return an incoherent byte view and false-flag staleness
  (gated authoritatively in CI, clean checkout). --no-runtime: the runtime-vs-static
  drift check runs separately below via Check-RuntimeSurface.ps1 across ALL packages
  (not just pythontk), so running it in the guard too would double-verify pythontk.
  The unattended local guard thus focuses on the memory budget + CLAUDE.md sizes +
  dispatch. Run the full guard manually (no flag) when the drive is settled.

.NOTES
  Exit code mirrors the guard: 0 = within budget, 1 = a hard budget was breached.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = 'o:\Cloud\Code\_scripts',
    [string]$LogPath  = "$env:LOCALAPPDATA\claude-context-budget.log"
)

$py = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$guard = Join-Path $RepoRoot 'm3trik\scripts\check_context_budget.py'

$stamp  = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$output = & $py $guard --no-registry --no-runtime 2>&1 | Out-String
$code   = $LASTEXITCODE

Add-Content -Path $LogPath -Value "===== $stamp (exit $code) =====`n$output" -Encoding UTF8

function Show-BudgetToast([string]$title, [string]$message) {
    try {
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $tpl   = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $texts = $tpl.GetElementsByTagName('text')
        $null  = $texts.Item(0).AppendChild($tpl.CreateTextNode($title))
        $null  = $texts.Item(1).AppendChild($tpl.CreateTextNode($message))
        $toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Context Budget').Show($toast)
    } catch {
        # Toast APIs are unavailable in some non-interactive sessions; the log is the record.
    }
}

# Near-cap early warning even when the guard still passes.
$nearCap = $false
$memFile = Join-Path $env:USERPROFILE '.claude\projects\o--Cloud-Code--scripts\memory\MEMORY.md'
if (Test-Path $memFile) {
    if ((Get-Item $memFile).Length -gt 22400) { $nearCap = $true }
}

# Runtime-vs-static API drift for the DCC packages (mayatk/uitk/blendertk) —
# the half the cloud CI can't run (no Maya/Qt/Blender). Best-effort: launches
# fresh session-safe DCC instances where installed, skips the rest. Its own log;
# a FAIL raises a toast and fails the task alongside the budget result. A 'missing'
# drift usually means a real regression OR a stale local registry (regenerate to
# disambiguate).
$driftScript = Join-Path $RepoRoot 'm3trik\scripts\Check-RuntimeSurface.ps1'
$driftCode = 0
if (Test-Path $driftScript) {
    & $driftScript -RepoRoot $RepoRoot
    $driftCode = $LASTEXITCODE
    Add-Content -Path $LogPath -Value "----- runtime-surface drift: exit $driftCode (detail in claude-runtime-surface.log) -----" -Encoding UTF8
}

# Workspace docs sweep — link/orphan integrity for every repo's hand-written
# markdown, plus the uitk DOCMAP ledger suite (policy: m3trik/docs/DOCS_STANDARD.md).
$docsScript = Join-Path $RepoRoot 'm3trik\scripts\check_docs.py'
$docsCode = 0
if (Test-Path $docsScript) {
    $docsOut  = & $py $docsScript --workspace $RepoRoot 2>&1 | Out-String
    $docsCode = $LASTEXITCODE
    Add-Content -Path $LogPath -Value "----- docs sweep: exit $docsCode -----`n$docsOut" -Encoding UTF8
}

if ($code -ne 0) {
    Show-BudgetToast 'Context budget FAILED' 'A hard budget was breached — see claude-context-budget.log and run check_context_budget.py.'
} elseif ($driftCode -ne 0) {
    Show-BudgetToast 'API runtime drift' 'A package registry promises a member its live class lacks — see claude-runtime-surface.log.'
} elseif ($docsCode -ne 0) {
    Show-BudgetToast 'Docs sweep FAILED' 'Broken links or orphaned docs — see claude-context-budget.log and run check_docs.py --workspace.'
} elseif ($nearCap) {
    Show-BudgetToast 'MEMORY.md near cap' 'Memory index is within 2 KB of the 24.4 KB load cap — compress index entries soon.'
}

if ($code -eq 0 -and ($driftCode -ne 0 -or $docsCode -ne 0)) { $code = 1 }
exit $code
