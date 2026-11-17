# SAM Desktop Application — Packaging & Distribution Guide

Version: **7.0.0**  
Target OS: **Windows 11 (x64)**  
Hardware: **HP OMEN 16, RTX 4050 Laptop GPU (6GB VRAM), 16GB RAM**

---

## 1. Overview & Packaging Architecture

SAM is packaged as a standalone Windows desktop application using a decoupled two-process architecture:

```
[ SAM.exe ] (Launcher Process)
   │
   ├── Windows Named Mutex ("Global\SAM_DesktopApp_SingleInstance_7")
   │   └── Prevents duplicate instances; focuses/opens running instance
   │
   ├── Runtime & Dependency Validator (sam.launcher.runtime_check)
   │   └── Verifies Python 3.11+, critical libraries, and Ollama/Whisper detection
   │
   ├── System Tray Controller (pystray + Pillow)
   │   └── "Open SAM", "Restart Backend", "Exit"
   │
   ├── Subprocess: sam_backend_runner.py (FastAPI + uvicorn)
   │   └── Redirects all persistent data to %APPDATA%\SAM (data, logs, workspaces)
   │
   └── UI Launcher (webbrowser)
       └── Launches default browser to http://127.0.0.1:8765
```

### Key Architectural Safeguards:
1. **Separation of Binaries & User Data:**
   - Application binaries install to `Program Files\SAM` (read-only for standard users).
   - User database (`sam_memory.db`), task logs, workspaces, video exports, and screenshots reside exclusively in `%APPDATA%\SAM`.
   - Upgrading or uninstalling the application **never** touches `%APPDATA%\SAM`.
2. **AI Model Preservation:**
   - Large AI model weights are never bundled into the installer.
   - Ollama models are preserved on `D:\Ollama\models` (or `%USERPROFILE%\.ollama\models`).
   - Whisper models are preserved on `D:\Whisper\models`.
   - SAM operates gracefully in deterministic/fallback mode if local inference or speech recognition is unavailable.
3. **Emergency Stop & Security:**
   - Emergency Stop remains globally accessible at all times via UI button or API.
   - All desktop automations acquire and release an atomic desktop lock with watchdog timeouts.
   - Paths outside approved workspaces are strictly forbidden with path-traversal prevention.

---

## 2. Developer Build Instructions

### Prerequisites
1. **Python 3.11–3.14 (64-bit)**
2. Install build dependencies:
   ```powershell
   pip install pyinstaller pystray pillow
   ```
3. (Optional for installer) **Inno Setup 6.x**:
   - Download and install from [jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php).

### Automated Build Script
Run the automated Windows batch builder:
```cmd
REM Build standalone folder bundle (dist\SAM\SAM.exe):
packaging\build_windows.bat

REM Build standalone bundle + Inno Setup installer:
packaging\build_windows.bat --installer
```

### Manual Build Steps
1. **Generate Icons:**
   ```powershell
   python packaging\generate_icon.py
   ```
2. **Run Packaging Automated Tests:**
   ```powershell
   python -m unittest sam.tests.test_packaging -v
   ```
3. **Compile PyInstaller Specification:**
   ```powershell
   pyinstaller SAM.spec --noconfirm --clean
   ```
4. **Compile Inno Setup Installer:**
   ```powershell
   iscc packaging\sam_installer.iss
   ```

---

## 3. Windows Installation & Upgrade Instructions

### First-Time Installation
1. Run `SAM_Setup_7.0.0.exe` (or launch from `dist\SAM\SAM.exe`).
2. Follow the setup wizard:
   - Select installation directory (defaults to `C:\Program Files\SAM` or per-user local app directory).
   - Choose whether to create a Desktop shortcut.
   - Choose whether to enable "Start with Windows" (disabled by default).
3. Complete the installation and click **Launch SAM**.
4. SAM will verify dependencies and launch the AI workstation UI at `http://127.0.0.1:8765`.

### Local AI Runtime Setup (Ollama & Models)
1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Open Windows Terminal / PowerShell:
   ```powershell
   # Pull primary lightweight model
   ollama pull qwen2.5:3b

   # (Optional) Pull advanced model
   ollama pull qwen3:4b
   ```
3. To store models on `D:\Ollama\models`, set the Windows environment variable:
   ```powershell
   [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "D:\Ollama\models", "User")
   ```

### Upgrading SAM
- Running a newer `SAM_Setup_X.X.X.exe` automatically detects the previous version via registry `AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}`.
- The installer silently uninstalls the previous binary version and installs the new one.
- **Your data, configuration, memories, and model files are 100% preserved.**

### Uninstallation
- Open Windows **Settings > Apps > Installed apps**, locate **SAM**, and click **Uninstall**.
- Or run `C:\Program Files\SAM\unins000.exe`.
- The uninstaller safely deletes the application binaries from `Program Files\SAM` while leaving `%APPDATA%\SAM` completely intact.

---

## 4. Packaging File Manifest

| File / Directory | Purpose |
| :--- | :--- |
| `SAM.spec` | PyInstaller build specification (datas, hiddenimports, icon, version) |
| `sam_main.py` | Top-level entrypoint executed by PyInstaller bootloader |
| `sam_backend_runner.py` | Standalone FastAPI backend subprocess entrypoint |
| `sam/launcher/app_launcher.py` | Desktop application launcher, single-instance mutex & tray |
| `sam/launcher/runtime_check.py` | Pre-flight dependency, Ollama, model & data check engine |
| `sam/launcher/config_manager.py` | Persistent user configuration manager with migration & backup |
| `sam/launcher/startup_manager.py` | Safe HKCU Windows Run registry configuration manager |
| `packaging/sam_installer.iss` | Inno Setup 6 compilation script with upgrade preservation |
| `packaging/version_info.txt` | Windows PE executable file metadata (Version, Copyright, Company) |
| `packaging/assets/sam_icon.ico` | Multi-resolution Windows application icon (16x16 to 256x256) |
| `packaging/assets/sam_icon.png` | Hi-res 256x256 PNG asset for system tray and installer |
| `packaging/generate_icon.py` | Programmatic icon generator |
| `packaging/build_windows.bat` | One-click automated Windows build script |
| `sam/tests/test_packaging.py` | 62 automated unit and regression tests for packaging |

---

## 5. Known Limitations & Recommendations

1. **Hardware-Accelerated In-Window Rendering:**
   - SAM defaults to launching your default web browser (Edge/Chrome) against `http://127.0.0.1:8765`. For embedded webviews, Edge WebView2 runtime is recommended for future native wrapper packaging.
2. **First-Run Whisper Initialization:**
   - On first transcription request, `faster-whisper` loads weights from `D:\Whisper\models`. On an NVIDIA RTX 4050 Laptop GPU, this takes approximately 1.5–3 seconds to load into VRAM.
3. **Playwright Headless Browsing:**
   - If Playwright browsers are not installed (`playwright install`), SAM automatically falls back to high-fidelity HTTP extraction via `httpx` + `BeautifulSoup4`.
