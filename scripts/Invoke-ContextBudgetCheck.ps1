<#
.SYNOPSIS
  Weekly context-budget check for the Claude agent context surface.

.DESCRIPTION
  Runs check_context_budget.py against the repo + the local Claude auto-memory
  dir, appends the result to a log, and raises a Windows toast on a hard FAIL or
  when MEMORY.md is within 2 KB of its 24,400-byte load cap. Driven by the
  'ClaudeContextBudget' Scheduled Task. The log is the durable record; the toast
  is best-effort (skipped silently in a non-interactive session).

  Registry freshness is checked with --no-registry here: this repo lives on a
  Nextcloud cloud-synced drive (O:) where reading a just-written .json sidecar can
  transiently return an incoherent byte view and false-flag staleness. Registry
  freshness is gated authoritatively in CI (clean checkout), so the unattended
  local run focuses on the memory budget + CLAUDE.md sizes + dispatch. Run the
  full guard manually (no flag) when the drive is settled.

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
$output = & $py $guard --no-registry 2>&1 | Out-String
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

if ($code -ne 0) {
    Show-BudgetToast 'Context budget FAILED' 'A hard budget was breached — see claude-context-budget.log and run check_context_budget.py.'
} elseif ($nearCap) {
    Show-BudgetToast 'MEMORY.md near cap' 'Memory index is within 2 KB of the 24.4 KB load cap — compress index entries soon.'
}

exit $code
