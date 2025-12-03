@ECHO OFF
SETLOCAL EnableDelayedExpansion

:: ============================================================================
:: PyPI Package Publisher
:: 
:: Publishes the current version to PyPI.
:: Version bump happens automatically via GitHub Actions after successful push.
::
:: Usage: update_wheel.cmd [module_name] [--dry-run]
:: ============================================================================

:: Parse arguments
set "name=%~1"
set "DRY_RUN="
if "%~1"=="--dry-run" (set "DRY_RUN=1" & set "name=%~2")
if "%~2"=="--dry-run" set "DRY_RUN=1"

:: Prompt for module name if not provided
if "%name%"=="" set /p "name=Enter the module name: "
if "%name%"=="" (echo No module specified. & exit /b 1)

:: Set paths
set "dir=%CLOUD%\Code\_scripts\%name%"
if not exist "%dir%" (echo Directory not found: %dir% & exit /b 1)

echo.
echo ========================================
echo   Publishing: %name%
if defined DRY_RUN echo   [DRY RUN MODE]
echo ========================================
echo.

:: Navigate to package directory
cd /d "%dir%"

:: Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist" rmdir /s /q "dist" 2>nul
if exist "%name%.egg-info" rmdir /s /q "%name%.egg-info" 2>nul

:: Get current version
for /f "tokens=*" %%v in ('python -c "from %name% import __version__; print(__version__)"') do set "VERSION=%%v"
echo Version: %VERSION%
echo.

:: Build package
echo Building package...
python -m build --wheel
if %errorlevel% neq 0 (
    echo Build failed!
    goto :end
)

:: Validate build
echo Validating package...
python -m twine check dist/*
if %errorlevel% neq 0 (
    echo Validation failed!
    goto :end
)

:: Check for dry run
if defined DRY_RUN (
    echo.
    echo [DRY RUN] Would upload:
    dir /b dist\*
    echo.
    echo Dry run complete.
    goto :end
)

:: Check for PyPI token
set "TWINE_USERNAME=__token__"
if not defined PYPI_TOKEN (
    echo.
    echo PYPI_TOKEN not set in environment.
    echo Get token from: https://pypi.org/manage/account/token/
    set /p "TWINE_PASSWORD=Enter PyPI API token: "
) else (
    set "TWINE_PASSWORD=%PYPI_TOKEN%"
)

:: Upload to PyPI
echo.
echo Uploading to PyPI...
python -m twine upload dist/* --skip-existing
if %errorlevel% neq 0 (
    echo.
    echo Upload failed!
    goto :end
)

echo.
echo ========================================
echo   Published %name% v%VERSION%
echo ========================================
echo.
echo Push to GitHub to trigger automatic version bump.

:end
echo.
PAUSE
