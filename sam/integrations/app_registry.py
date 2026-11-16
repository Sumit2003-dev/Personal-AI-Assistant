"""
SAM - Application Registry & Integration Engine
Detects installed Windows applications (VS Code, Chrome, Edge, Office, Terminal, DaVinci, Blender),
tracks running processes, and handles guarded application launching.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import shutil
import subprocess
import os
import psutil
import logging

logger = logging.getLogger("sam.integrations.app_registry")


class ApplicationInfo:
    def __init__(
        self,
        app_id: str,
        name: str,
        category: str,
        exe_candidates: List[str],
        process_names: List[str],
        description: str = "",
    ):
        self.app_id = app_id
        self.name = name
        self.category = category
        self.exe_candidates = exe_candidates
        self.process_names = [p.lower() for p in process_names]
        self.description = description
        self.executable_path: Optional[str] = None
        self.is_installed: bool = False
        self.detect()

    def detect(self) -> bool:
        # Check explicit paths
        for path_str in self.exe_candidates:
            expanded = os.path.expandvars(path_str)
            if os.path.isfile(expanded):
                self.executable_path = expanded
                self.is_installed = True
                return True

        # Check system PATH
        for path_str in self.exe_candidates:
            base = os.path.basename(path_str)
            which_path = shutil.which(base) or shutil.which(path_str)
            if which_path:
                self.executable_path = which_path
                self.is_installed = True
                return True

        self.is_installed = False
        return False

    def is_running(self, running_names: Optional[set] = None) -> bool:
        if running_names is not None:
            return any(p in running_names for p in self.process_names)
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and name.lower() in self.process_names:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def to_dict(self, running_names: Optional[set] = None) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "is_installed": self.is_installed,
            "is_running": self.is_running(running_names),
            "executable_path": self.executable_path,
        }


class ApplicationRegistry:
    """Maintains catalog of verified applications on Windows 11."""

    def __init__(self):
        self._apps: Dict[str, ApplicationInfo] = {}
        self._register_default_applications()

    def _register_default_applications(self):
        defs = [
            # Development
            ApplicationInfo(
                app_id="vscode",
                name="Visual Studio Code",
                category="DEVELOPMENT",
                exe_candidates=[
                    r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                    r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd",
                    "code",
                ],
                process_names=["code.exe"],
                description="Primary code editor and development workspace.",
            ),
            ApplicationInfo(
                app_id="terminal",
                name="Windows Terminal",
                category="DEVELOPMENT",
                exe_candidates=[
                    r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe",
                    "wt",
                ],
                process_names=["windowsterminal.exe", "wt.exe"],
                description="Modern tabbed Windows command line terminal.",
            ),
            ApplicationInfo(
                app_id="powershell",
                name="PowerShell",
                category="DEVELOPMENT",
                exe_candidates=[
                    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                    "powershell",
                ],
                process_names=["powershell.exe"],
                description="Windows PowerShell automation engine.",
            ),
            ApplicationInfo(
                app_id="git",
                name="Git",
                category="DEVELOPMENT",
                exe_candidates=[
                    r"C:\Program Files\Git\cmd\git.exe",
                    "git",
                ],
                process_names=["git.exe"],
                description="Version control system.",
            ),
            # Browsers
            ApplicationInfo(
                app_id="edge",
                name="Microsoft Edge",
                category="BROWSER",
                exe_candidates=[
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    "msedge",
                ],
                process_names=["msedge.exe"],
                description="Default Windows modern web browser.",
            ),
            ApplicationInfo(
                app_id="chrome",
                name="Google Chrome",
                category="BROWSER",
                exe_candidates=[
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    "chrome",
                ],
                process_names=["chrome.exe"],
                description="Chromium-based web browser.",
            ),
            # Productivity
            ApplicationInfo(
                app_id="word",
                name="Microsoft Word",
                category="PRODUCTIVITY",
                exe_candidates=[
                    r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
                    r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
                    "winword",
                ],
                process_names=["winword.exe"],
                description="Word processor for documents.",
            ),
            ApplicationInfo(
                app_id="excel",
                name="Microsoft Excel",
                category="PRODUCTIVITY",
                exe_candidates=[
                    r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
                    r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
                    "excel",
                ],
                process_names=["excel.exe"],
                description="Spreadsheet and data table software.",
            ),
            ApplicationInfo(
                app_id="powerpoint",
                name="Microsoft PowerPoint",
                category="PRODUCTIVITY",
                exe_candidates=[
                    r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
                    r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
                    "powerpnt",
                ],
                process_names=["powerpnt.exe"],
                description="Presentation slides software.",
            ),
            # Creative
            ApplicationInfo(
                app_id="davinci",
                name="DaVinci Resolve",
                category="CREATIVE",
                exe_candidates=[
                    r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe",
                    "resolve",
                ],
                process_names=["resolve.exe"],
                description="Professional video editing and color grading suite.",
            ),
            ApplicationInfo(
                app_id="blender",
                name="Blender",
                category="CREATIVE",
                exe_candidates=[
                    r"C:\Program Files\Blender Foundation\Blender\blender.exe",
                    "blender",
                ],
                process_names=["blender.exe"],
                description="3D creation and rendering suite.",
            ),
            # System
            ApplicationInfo(
                app_id="explorer",
                name="File Explorer",
                category="SYSTEM",
                exe_candidates=[
                    r"C:\Windows\explorer.exe",
                    "explorer",
                ],
                process_names=["explorer.exe"],
                description="Windows desktop shell and file manager.",
            ),
            ApplicationInfo(
                app_id="taskmgr",
                name="Task Manager",
                category="SYSTEM",
                exe_candidates=[
                    r"C:\Windows\System32\Taskmgr.exe",
                    "taskmgr",
                ],
                process_names=["taskmgr.exe"],
                description="Windows system activity and performance manager.",
            ),
        ]
        for app in defs:
            self._apps[app.app_id] = app

    def list_applications(self) -> List[Dict[str, Any]]:
        running_names = set()
        for proc in psutil.process_iter(["name"]):
            try:
                n = proc.info.get("name")
                if n:
                    running_names.add(n.lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return [app.to_dict(running_names) for app in self._apps.values()]

    def get_app(self, app_id: str) -> Optional[ApplicationInfo]:
        return self._apps.get(app_id.lower())

    def launch_app(self, app_id: str, args: List[str] | None = None) -> bool:
        app = self.get_app(app_id)
        if not app:
            logger.error(f"App '{app_id}' not found in registry.")
            return False
        if not app.is_installed or not app.executable_path:
            logger.warning(f"App '{app.name}' is not installed on this system.")
            return False

        try:
            cmd = [app.executable_path] + (args or [])
            subprocess.Popen(cmd, shell=False)
            logger.info(f"Launched application '{app.name}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to launch '{app.name}': {e}")
            return False


app_registry = ApplicationRegistry()

