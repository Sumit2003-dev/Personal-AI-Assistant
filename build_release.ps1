# build_release.ps1 — SAM Autonomous Desktop Release Builder
# Fully automated and reproducible packaging for Windows 11
[CmdletBinding()]
param(
    [switch]$SkipTests = $false,
    [switch]$SkipInstaller = $false
)

$ErrorActionPreference = "Stop"
$StartTime = Get-Date

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  SAM Personal AI Assistant — Release Packaging Pipeline  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# 1. Environment & Tools Validation
Write-Host "`n[1/7] Checking environment and toolchain..." -ForegroundColor Yellow

# Python
$pythonVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Host "  Python version: $pythonVer" -ForegroundColor Green
$pyMajor, $pyMinor = ($pythonVer -split '\.')[0..1]
if ([int]$pyMajor -lt 3 -or ([int]$pyMajor -eq 3 -and [int]$pyMinor -lt 11)) {
    Write-Error "Python 3.11+ is required. Found $pythonVer"
}

# PyInstaller
try {
    $pyinstallerVer = & python -m PyInstaller --version
    Write-Host "  PyInstaller version: $pyinstallerVer" -ForegroundColor Green
} catch {
    Write-Error "PyInstaller is not installed. Run: pip install pyinstaller"
}

# Inno Setup (ISCC.exe)
$isccPath = $null
$candidatePaths = @(
    "iscc.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

foreach ($p in $candidatePaths) {
    if (Get-Command $p -ErrorAction SilentlyContinue) {
        $isccPath = (Get-Command $p).Source
        break
    } elseif (Test-Path $p) {
        $isccPath = (Resolve-Path $p).Path
        break
    }
}

if ($isccPath) {
    Write-Host "  Inno Setup Compiler: $isccPath" -ForegroundColor Green
} else {
    if (-not $SkipInstaller) {
        Write-Warning "Inno Setup Compiler (ISCC.exe) was not found."
        Write-Warning "Install Inno Setup via: winget install JRSoftware.InnoSetup"
    }
}

# 2. Source Files Verification
Write-Host "`n[2/7] Verifying required source assets..." -ForegroundColor Yellow
$requiredFiles = @(
    "SAM.spec",
    "sam_main.py",
    "sam_backend_runner.py",
    "LICENSE",
    "packaging\sam_installer.iss",
    "packaging\assets\sam_icon.ico",
    "packaging\assets\sam_icon.png",
    "packaging\scripts\pre_install_info.txt",
    "packaging\scripts\post_install_info.txt",
    "sam\desktop\templates\index.html",
    "sam\desktop\static\css\style.css",
    "sam\desktop\static\js\app.js"
)

foreach ($rf in $requiredFiles) {
    if (-not (Test-Path (Join-Path $RepoRoot $rf))) {
        Write-Error "Required source asset missing: $rf"
    }
}
Write-Host "  All required source files verified." -ForegroundColor Green

# 3. Automated Packaging Validation Tests
if (-not $SkipTests) {
    Write-Host "`n[3/7] Running automated packaging validation test suite..." -ForegroundColor Yellow
    & python -u -m unittest sam.tests.test_packaging
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Packaging test suite failed with exit code $LASTEXITCODE"
    }
    Write-Host "  All packaging tests passed." -ForegroundColor Green
} else {
    Write-Host "`n[3/7] Skipping automated test execution (-SkipTests specified)." -ForegroundColor DarkGray
}

# 4. PyInstaller Build
Write-Host "`n[4/7] Building application bundle via PyInstaller..." -ForegroundColor Yellow
& python -m PyInstaller SAM.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $RepoRoot "dist\SAM\SAM.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Expected build output dist\SAM\SAM.exe was not created."
}
$exeSizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
Write-Host "  PyInstaller bundle built successfully: $exePath [$exeSizeMB MB]" -ForegroundColor Green

# 5. Inno Setup Compilation
$installerPath = $null
if (-not $SkipInstaller -and $isccPath) {
    Write-Host "`n[5/7] Compiling Windows setup installer via Inno Setup..." -ForegroundColor Yellow
    & "$isccPath" (Join-Path $RepoRoot "packaging\sam_installer.iss")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Inno Setup compilation failed with exit code $LASTEXITCODE"
    }
    $installerPath = Join-Path $RepoRoot "packaging\output\SAM_Setup_7.0.0.exe"
    if (-not (Test-Path $installerPath)) {
        Write-Error "Expected installer output packaging\output\SAM_Setup_7.0.0.exe was not created."
    }
    $installerSizeMB = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
    Write-Host "  Installer compiled successfully: $installerPath [$installerSizeMB MB]" -ForegroundColor Green
} else {
    Write-Host "`n[5/7] Skipping Inno Setup compilation." -ForegroundColor DarkGray
}

# 6. Artifact Inspection & Manifest Generation
Write-Host "`n[6/7] Generating release manifest..." -ForegroundColor Yellow
$manifest = @{
    release_version = "7.0.0"
    build_date = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    python_version = $pythonVer
    pyinstaller_version = $pyinstallerVer
    artifacts = @()
}

if (Test-Path $exePath) {
    $exeItem = Get-Item $exePath
    $exeHash = (Get-FileHash $exePath -Algorithm SHA256).Hash
    $manifest.artifacts += @{
        name = "SAM.exe"
        relative_path = "dist\SAM\SAM.exe"
        size_bytes = $exeItem.Length
        sha256 = $exeHash
        type = "portable_application_executable"
    }
}

if ($installerPath -and (Test-Path $installerPath)) {
    $instItem = Get-Item $installerPath
    $instHash = (Get-FileHash $installerPath -Algorithm SHA256).Hash
    $manifest.artifacts += @{
        name = "SAM_Setup_7.0.0.exe"
        relative_path = "packaging\output\SAM_Setup_7.0.0.exe"
        size_bytes = $instItem.Length
        sha256 = $instHash
        type = "windows_inno_setup_installer"
    }
}

$manifestJson = $manifest | ConvertTo-Json -Depth 5
$manifestPath = Join-Path $RepoRoot "release_manifest.json"
Set-Content -Path $manifestPath -Value $manifestJson -Encoding utf8
Write-Host "  Manifest written to: $manifestPath" -ForegroundColor Green

# 7. Build Summary
$Elapsed = (Get-Date) - $StartTime
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  BUILD SUCCESSFUL in $($Elapsed.Minutes)m $($Elapsed.Seconds)s" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Artifacts ready for deployment:"
foreach ($art in $manifest.artifacts) {
    $mb = [math]::Round($art.size_bytes/1MB, 2)
    Write-Host "  • $($art.name) [$mb MB] -> $($art.sha256.Substring(0, 16))..." -ForegroundColor Green
}
Write-Host ""
