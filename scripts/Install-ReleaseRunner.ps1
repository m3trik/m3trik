<#
Install-ReleaseRunner.ps1 -- set up (or remove) the release runner on this machine, once.

Run it on the machine that has Maya, Blender and a `gh` login (docs/RELEASE_RUNNER.md).
After it, a release is one workflow dispatch, from any session or the GitHub app:

    1. The PRIVATE release repo (-Repo, made when missing; refused if public). A
       self-hosted runner never serves a public repo: a fork's pull request could edit
       a workflow to run on this machine. It holds only the Release workflow, published
       from m3trik/release_runner/release.yml (edit it there and re-run this).
    2. The dedicated workspace (-Root): the .release-runner marker and m3trik's clone.
       Invoke-RunnerRelease.ps1 resets and cleans every repo in it, so it is never a
       person's working tree.
    3. A GitHub Actions runner (-RunnerDir) registered to the repo with the
       m3trik-release label, M3TRIK_RELEASE_ROOT and M3TRIK_PYTHON in its .env.
    4. A logon task that starts the runner in your desktop session: the GUI Maya suites
       need a desktop, which a Windows service does not have. It runs as you, so git
       and gh use your own credentials; no token is stored anywhere.

Idempotent: a re-run republishes the workflow and keeps a configured runner (-Reconfigure
registers it again). -Uninstall removes the task and the runner registration; the
repo and the workspace stay.
#>

param(
    [string]$Repo = "m3trik/release-runner",
    [string]$Root = (Join-Path ([Environment]::GetFolderPath("UserProfile")) "m3trik-release"),
    [string]$RunnerDir = (Join-Path ([Environment]::GetFolderPath("UserProfile")) "actions-runner-m3trik"),
    # The interpreter the suites and push.ps1 run under: one with the workspace's test
    # dependencies (Qt, numpy, ...). Default: the python on PATH.
    [string]$Python,
    [string]$Label = "m3trik-release",
    [string]$TaskName = "m3trik release runner",
    [switch]$Reconfigure,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$M3TRIK = Split-Path -Parent $PSScriptRoot
$OWNER = $Repo.Split("/")[0]

function Write-Step {
    param([string]$Text)
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Native {
    # Run a native command; throw with *Why* when it fails.
    param([string]$Why, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE) { throw "$Why (exit $LASTEXITCODE)" }
}

function Assert-Prerequisites {
    foreach ($tool in "git", "gh") {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not on PATH." }
    }
    gh auth status *> $null
    if ($LASTEXITCODE) { throw "gh is not logged in: run gh auth login (push.ps1 needs it too)." }
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw "Run this under PowerShell 7 (pwsh): the workflow does." }
    if (-not (Test-Path -LiteralPath $script:Python)) { throw "No python at $script:Python (pass -Python)." }
}

function Initialize-ReleaseRepo {
    gh repo view $Repo --json visibility *> $null
    if ($LASTEXITCODE) {
        Write-Step "Creating the private repo $Repo"
        Invoke-Native "could not create $Repo" {
            gh repo create $Repo --private --description "Release runner: the cascade's Release workflow (from m3trik/release_runner)."
        }
    }
    $visibility = gh repo view $Repo --json visibility --jq ".visibility"
    if ($visibility -ne "PRIVATE") {
        throw "$Repo is ${visibility}: a self-hosted runner must never serve a public repo. Make it private or pass another -Repo."
    }
}

function Publish-Workflow {
    Write-Step "Publishing the Release workflow to $Repo"
    $work = Join-Path ([IO.Path]::GetTempPath()) ("release-runner-" + [guid]::NewGuid().ToString("N"))
    try {
        Invoke-Native "could not clone $Repo" { gh repo clone $Repo $work -- --quiet }
        $files = @{
            (Join-Path $M3TRIK "release_runner/release.yml") = ".github/workflows/release.yml"
            (Join-Path $M3TRIK "release_runner/README.md")   = "README.md"
        }
        foreach ($source in $files.Keys) {
            $target = Join-Path $work $files[$source]
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
        git -C $work add -A
        git -C $work diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    already current"
            return
        }
        $source = git -C $M3TRIK rev-parse --short HEAD
        Invoke-Native "could not commit the workflow" { git -C $work commit --quiet -m "Release workflow from m3trik@$source" }
        Invoke-Native "could not push the workflow" { git -C $work push --quiet origin HEAD:main }
    }
    finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Initialize-Workspace {
    Write-Step "Preparing the dedicated workspace $Root"
    $resolved = [IO.Path]::GetFullPath($Root)
    $live = [IO.Path]::GetFullPath((Split-Path -Parent $M3TRIK))
    if ($resolved.TrimEnd('\', '/') -eq $live.TrimEnd('\', '/')) {
        throw "-Root is this workspace ($live): the runner resets and cleans its repos. Pick a dedicated folder."
    }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Set-Content -LiteralPath (Join-Path $Root ".release-runner") -Encoding UTF8 -Value @(
        "The release runner's dedicated workspace (m3trik/scripts/Install-ReleaseRunner.ps1).",
        "Invoke-RunnerRelease.ps1 resets and cleans every repo here on each run: never work in it."
    )
    $m3trik = Join-Path $Root "m3trik"
    if (-not (Test-Path -LiteralPath (Join-Path $m3trik ".git"))) {
        Invoke-Native "could not clone m3trik" { git clone --quiet "https://github.com/$OWNER/m3trik" $m3trik }
    }
}

function Get-RunnerToken {
    param([string]$Kind)  # registration | remove
    $token = gh api -X POST "repos/$Repo/actions/runners/$Kind-token" --jq ".token"
    if ($LASTEXITCODE -or -not $token) { throw "could not get a runner $Kind token for $Repo" }
    return $token
}

function Install-Runner {
    $configured = Test-Path -LiteralPath (Join-Path $RunnerDir ".runner")
    if ($configured -and -not $Reconfigure) {
        Write-Step "Runner already configured in $RunnerDir"
    }
    else {
        if (-not (Test-Path -LiteralPath (Join-Path $RunnerDir "config.cmd"))) {
            Write-Step "Downloading the GitHub Actions runner"
            New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
            $zip = Join-Path ([IO.Path]::GetTempPath()) "actions-runner-win-x64.zip"
            Remove-Item -LiteralPath $zip -ErrorAction SilentlyContinue
            Invoke-Native "could not download the runner" {
                gh release download --repo actions/runner --pattern "actions-runner-win-x64-*.zip" --output $zip --clobber
            }
            Expand-Archive -LiteralPath $zip -DestinationPath $RunnerDir -Force
            Remove-Item -LiteralPath $zip
        }
        Write-Step "Registering the runner with $Repo (label $Label)"
        $token = Get-RunnerToken "registration"
        Push-Location $RunnerDir
        try {
            Invoke-Native "runner configuration failed" {
                .\config.cmd --unattended --replace --url "https://github.com/$Repo" --token $token `
                    --name "$env:COMPUTERNAME-release" --labels $Label --work "_work"
            }
        }
        finally {
            Pop-Location
        }
    }
    $env_lines = @(
        "M3TRIK_RELEASE_ROOT=$([IO.Path]::GetFullPath($Root))",
        "M3TRIK_PYTHON=$script:Python"
    )
    # The private hygiene denylist stays in this workspace; each run copies it in.
    $denylist = Join-Path (Split-Path -Parent $M3TRIK) ".claude/public_hygiene.txt"
    if (Test-Path -LiteralPath $denylist) {
        $env_lines += "M3TRIK_HYGIENE_DENYLIST=$([IO.Path]::GetFullPath($denylist))"
    }
    else {
        Write-Warning "No ${denylist}: releases will skip push.ps1's client-name check."
    }
    Set-Content -LiteralPath (Join-Path $RunnerDir ".env") -Encoding UTF8 -Value $env_lines
}

function Register-LogonTask {
    Write-Step "Starting the runner at logon (task '$TaskName')"
    $action = New-ScheduledTaskAction -Execute (Join-Path $RunnerDir "run.cmd") -WorkingDirectory $RunnerDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Description "GitHub Actions runner for $Repo (m3trik releases)." -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
}

function Uninstall-Runner {
    Write-Step "Removing the logon task and the runner registration"
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    if (Test-Path -LiteralPath (Join-Path $RunnerDir ".runner")) {
        $token = Get-RunnerToken "remove"
        Push-Location $RunnerDir
        try { Invoke-Native "runner removal failed" { .\config.cmd remove --token $token } }
        finally { Pop-Location }
    }
    Write-Host "Removed. $Repo and $Root were kept; delete them by hand if no longer wanted."
}

if ($MyInvocation.InvocationName -eq ".") { return }

if ($Uninstall) {
    Uninstall-Runner
    exit 0
}
if (-not $Python) { $Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source }
$Python = [IO.Path]::GetFullPath($Python)
Assert-Prerequisites
Initialize-ReleaseRepo
Publish-Workflow
Initialize-Workspace
Install-Runner
Register-LogonTask
Write-Host ""
Write-Host "Ready. Release from anywhere:" -ForegroundColor Green
Write-Host "  gh workflow run release.yml --repo $Repo -f packages=pythontk,uitk,mayatk,blendertk,tentacle -f reviewed=true"
Write-Host "  (or: GitHub > $Repo > Actions > Release > Run workflow). A dry run: -f dry_run=true."
