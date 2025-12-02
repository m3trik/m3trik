# Package Publisher - Publishes packages in dependency order
# Dependency order: pythontk -> uitk -> mayatk -> tentacle

param(
    [switch]$List,
    [switch]$DryRun,
    [switch]$Help
)

$Root = "O:\Cloud\Code\_scripts"
$Packages = @("pythontk", "uitk", "mayatk", "tentacle", "map_compositor")

if ($Help) {
    Write-Host ""
    Write-Host "Usage: .\update_all_wheels.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -List     Show packages in dependency order"
    Write-Host "  -DryRun   Show what would be done without publishing"
    Write-Host "  -Help     Show this help"
    Write-Host "  (none)    Publish all packages interactively"
    Write-Host ""
    exit 0
}

if ($List) {
    Write-Host ""
    Write-Host "Package publish order:"
    $i = 1
    foreach ($pkg in $Packages) {
        Write-Host "  $i. $pkg"
        $i++
    }
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "========================================"
Write-Host "  Package Publisher (Dependency Order)"
Write-Host "========================================"
Write-Host ""
Write-Host "Packages will be published in this order:"
$i = 1
foreach ($pkg in $Packages) {
    Write-Host "  $i. $pkg"
    $i++
}
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN MODE - No actual publishing]"
    Write-Host ""
}

$response = Read-Host "Continue? (y/n)"
if ($response -ne "y") {
    Write-Host "Cancelled."
    exit 0
}

foreach ($pkg in $Packages) {
    Write-Host ""
    Write-Host "----------------------------------------"
    Write-Host "Publishing: $pkg"
    Write-Host "----------------------------------------"
    
    $pkgPath = Join-Path $Root $pkg
    if (-not (Test-Path $pkgPath)) {
        Write-Host "ERROR: Directory not found: $pkgPath" -ForegroundColor Red
        exit 1
    }
    
    Set-Location $pkgPath
    
    # Clean old builds
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    
    if ($DryRun) {
        Write-Host "[DRY RUN] Would build and upload $pkg"
    } else {
        # Build
        Write-Host "Building $pkg..."
        python -m build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Build failed for $pkg" -ForegroundColor Red
            Set-Location $Root
            exit 1
        }
        
        # Upload
        Write-Host "Uploading $pkg to PyPI..."
        python -m twine upload dist/* --skip-existing
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Upload failed for $pkg" -ForegroundColor Red
            Set-Location $Root
            exit 1
        }
    }
    
    Write-Host "$pkg published successfully!" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================"
Write-Host "  All packages published successfully!"
Write-Host "========================================"

Set-Location $Root
