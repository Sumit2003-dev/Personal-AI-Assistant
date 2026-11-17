@echo off
REM SAM Desktop Application — Windows Build Script
REM Builds the PyInstaller bundle and (optionally) the Inno Setup installer.
REM
REM Usage:
REM   build_windows.bat              — bundle only
REM   build_windows.bat --installer  — bundle + installer (requires Inno Setup)
REM
REM Prerequisites:
REM   pip install pyinstaller pystray pillow

setlocal enabledelayedexpansion

set SAM_VERSION=7.0.0
set PYINSTALLER=pyinstaller
set ISCC=

REM Locate pyinstaller on PATH or in AppData Scripts
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    set PYINSTALLER=%APPDATA%\Python\Python314\Scripts\pyinstaller.exe
)

REM Locate Inno Setup compiler
for %%D in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%D set ISCC=%%D
)

echo ============================================================
echo  SAM v%SAM_VERSION% — Windows Build
echo ============================================================

REM --- Step 1: Generate icons if missing ---
if not exist packaging\assets\sam_icon.ico (
    echo [1/4] Generating application icons...
    python packaging\generate_icon.py
    if %errorlevel% neq 0 goto :error
) else (
    echo [1/4] Icons already exist, skipping generation.
)

REM --- Step 2: Run automated packaging tests ---
echo [2/4] Running packaging validation tests...
python -m pytest sam\tests\test_packaging.py -v --tb=short 2>nul
if %errorlevel% neq 0 (
    python -m unittest sam.tests.test_packaging -v
    if %errorlevel% neq 0 (
        echo WARNING: Some packaging tests failed. Review before distributing.
    )
)

REM --- Step 3: PyInstaller bundle ---
echo [3/4] Building PyInstaller bundle...
%PYINSTALLER% SAM.spec --noconfirm --clean
if %errorlevel% neq 0 goto :error
echo Bundle created: dist\SAM\SAM.exe

REM --- Step 4: Inno Setup installer (optional) ---
if "%1"=="--installer" (
    if "%ISCC%"=="" (
        echo [4/4] Inno Setup not found. Install from https://jrsoftware.org/isinfo.php
        echo        Then re-run with --installer
        goto :done
    )
    echo [4/4] Building installer...
    %ISCC% packaging\sam_installer.iss
    if %errorlevel% neq 0 goto :error
    echo Installer: packaging\output\SAM_Setup_%SAM_VERSION%.exe
) else (
    echo [4/4] Skipping installer (pass --installer to build it).
)

:done
echo.
echo ============================================================
echo  Build complete!
echo  Bundle:    dist\SAM\SAM.exe
if "%1"=="--installer" echo  Installer: packaging\output\SAM_Setup_%SAM_VERSION%.exe
echo ============================================================
exit /b 0

:error
echo.
echo [ERROR] Build failed. See output above.
exit /b 1
