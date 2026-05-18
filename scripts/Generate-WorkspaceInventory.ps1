param(
    [string]$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$OutputDir = (Resolve-Path (Join-Path $PSScriptRoot "..\docs")).Path
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\..\common.ps1"

$pythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$generatorScript = Join-Path $PSScriptRoot "generate_workspace_inventory.py"

Write-Header "Generate Workspace Inventory"

if (-not (Test-Path $pythonExe -PathType Leaf)) {
    Write-Err "Python executable not found: $pythonExe"
    exit 1
}

if (-not (Test-Path $generatorScript -PathType Leaf)) {
    Write-Err "Generator script not found: $generatorScript"
    exit 1
}

Write-Step "Workspace root: $WorkspaceRoot"
Write-Step "Output directory: $OutputDir"
Write-Step "Running inventory generator"

& $pythonExe $generatorScript --workspace-root $WorkspaceRoot --output-dir $OutputDir

if ($LASTEXITCODE -ne 0) {
    Write-Err "Inventory generation failed"
    exit $LASTEXITCODE
}

Write-Success "Workspace inventory generated"