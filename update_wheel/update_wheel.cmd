@ECHO OFF
SETLOCAL EnableDelayedExpansion

:: ============================================================================
:: PyPI Package Publisher
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

:: Get current version before bump
for /f "tokens=*" %%v in ('python -c "from %name% import __version__; print(__version__)"') do set "OLD_VERSION=%%v"
echo Current version: %OLD_VERSION%

:: Bump version
echo Incrementing version...
python -c "import pythontk as ptk; ptk.PackageManager.update_version(r'%dir%/%name%/__init__.py')"
python -c "import pythontk as ptk; ptk.PackageManager.update_version(r'%dir%/docs/README.md', version_regex=r'!\[Version\]\(https://img.shields.io/badge/Version-(\d+)\.(\d+)\.(\d+)-.*\.svg\)')"

:: Get new version
for /f "tokens=*" %%v in ('python -c "from %name% import __version__; print(__version__)"') do set "NEW_VERSION=%%v"
echo New version: %NEW_VERSION%
echo.

:: Build package (using modern python -m build)
echo Building package...
python -m build
if %errorlevel% neq 0 (
    echo Build failed!
    goto :revert
)

:: Validate build
echo Validating package...
python -m twine check dist/*
if %errorlevel% neq 0 (
    echo Validation failed!
    goto :revert
)

:: Check for dry run
if defined DRY_RUN (
    echo.
    echo [DRY RUN] Would upload:
    dir /b dist\*
    echo.
    echo Reverting version for dry run...
    goto :revert_silent
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
python -m twine upload dist/* --skip-existing 2> upload_errors.txt
if %errorlevel% neq 0 (
    echo.
    echo Upload failed!
    type upload_errors.txt
    del upload_errors.txt 2>nul
    goto :revert
)

del upload_errors.txt 2>nul
echo.
echo ========================================
echo   Successfully published %name% v%NEW_VERSION%
echo ========================================
goto :end

:revert
echo.
echo Reverting version %NEW_VERSION% to %OLD_VERSION%...
:revert_silent
python -c "import pythontk as ptk; ptk.PackageManager.update_version(r'%dir%/%name%/__init__.py', 'decrement')"
python -c "import pythontk as ptk; ptk.PackageManager.update_version(r'%dir%/docs/README.md', change='decrement', version_regex=r'!\[Version\]\(https://img.shields.io/badge/Version-(\d+)\.(\d+)\.(\d+)-.*\.svg\)')"
if defined DRY_RUN (
    echo Dry run complete.
) else (
    echo Version reverted.
)

:end
echo.
PAUSE
