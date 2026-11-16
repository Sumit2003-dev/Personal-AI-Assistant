"""
SAM - Autonomous Coding Agent
Inspects workspaces, writes/edits code, executes tests, captures stdout/stderr, and verifies execution.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess
import os
import sys
import time
import shutil
import re
from sam.tools.base import BaseTool, ToolResult
from sam.agent.models import RiskLevel
from sam.tools.registry import tool_registry
from sam.config.settings import settings
from sam.security.permissions import security_gatekeeper

DEFAULT_WORKSPACE_ROOT = settings.data_dir / "workspaces"
DEFAULT_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

RESERVED_DEVICE_NAMES = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "lpt1", "lpt2", "lpt3"}
ILLEGAL_PATH_CHARS = set('<>:"|?*\0')


class CodingAgent:
    """Manages coding workspaces, file edits, script execution, and test verification."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def sanitize_workspace_name(self, name: str) -> str:
        """Sanitizes workspace folder name to strictly prevent directory traversal."""
        trimmed = name.strip()
        if ".." in trimmed or "/" in trimmed or "\\" in trimmed or ":" in trimmed:
            raise PermissionError(f"Directory traversal characters prohibited in workspace name: '{name}'")
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "", trimmed)
        if not clean or clean in [".", ".."]:
            raise PermissionError(f"Invalid or unsafe workspace name: '{name}'")
        return clean

    def get_workspace_dir(self, name: str) -> Path:
        clean_name = self.sanitize_workspace_name(name)
        ws = (self.workspace_root / clean_name).resolve()
        if self.workspace_root not in ws.parents and ws != self.workspace_root:
            raise PermissionError(f"Workspace traversal blocked: '{name}'")
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def resolve_safe_path(self, workspace_name: str, rel_path: str, must_exist: bool = False) -> Path:
        """
        Validates and resolves a file path strictly within the approved workspace.
        Blocks path traversal, absolute drive paths, Windows reserved device names, and symlink escapes.
        """
        ws = self.get_workspace_dir(workspace_name)
        clean_p = rel_path.strip().replace("\\", "/")

        if not clean_p or clean_p.startswith("/") or re.match(r"^[a-zA-Z]:", clean_p):
            raise PermissionError(f"Path traversal or absolute path prohibited: '{rel_path}'")

        parts = Path(clean_p).parts
        for part in parts:
            if part in [".", ".."]:
                raise PermissionError(f"Directory traversal operator '{part}' prohibited.")
            stem = part.split(".")[0].lower()
            if stem in RESERVED_DEVICE_NAMES:
                raise PermissionError(f"Reserved device filename '{part}' is prohibited on Windows.")
            if any(c in ILLEGAL_PATH_CHARS for c in part):
                raise PermissionError(f"Filename contains illegal characters: '{part}'")

        target = (ws / clean_p).resolve()

        if ws not in target.parents and target != ws:
            raise PermissionError(f"Path traversal outside workspace '{workspace_name}' blocked: '{rel_path}'")

        if target.is_symlink():
            real_target = target.resolve()
            if ws not in real_target.parents and real_target != ws:
                raise PermissionError(f"Symlink traversal outside workspace blocked: '{rel_path}'")

        if must_exist and not target.exists():
            raise FileNotFoundError(f"File '{rel_path}' does not exist in workspace '{workspace_name}'.")

        return target

    def inspect_workspace(self, name: str) -> Dict[str, Any]:
        ws = self.get_workspace_dir(name)
        files = []
        for p in ws.rglob("*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                files.append(str(p.relative_to(ws)))
        return {
            "workspace_name": name,
            "workspace_path": str(ws),
            "total_files": len(files),
            "files": files[:100],
        }

    def write_file(self, workspace_name: str, rel_path: str, content: str) -> Path:
        target = self.resolve_safe_path(workspace_name, rel_path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Checkpoint original if file already exists
        if target.exists():
            backup_path = target.with_name(f"{target.name}.bak")
            shutil.copy2(target, backup_path)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return target

    def rollback_file(self, workspace_name: str, rel_path: str) -> bool:
        """Restores a file to its checkpoint backup (.bak) if available."""
        target = self.resolve_safe_path(workspace_name, rel_path, must_exist=True)
        backup_path = target.with_name(f"{target.name}.bak")
        if not backup_path.exists():
            return False
        ws = self.get_workspace_dir(workspace_name)
        if ws not in backup_path.resolve().parents and backup_path.resolve() != ws:
            raise PermissionError("Rollback checkpoint resides outside workspace.")
        shutil.copy2(backup_path, target)
        return True

    def read_file(self, workspace_name: str, rel_path: str) -> str:
        target = self.resolve_safe_path(workspace_name, rel_path, must_exist=True)
        with open(target, "r", encoding="utf-8") as f:
            return f.read()

    def run_script(
        self,
        workspace_name: str,
        script_rel_path: str,
        args: List[str] | None = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        ws = self.get_workspace_dir(workspace_name)
        script_path = self.resolve_safe_path(workspace_name, script_rel_path, must_exist=True)

        cmd = [sys.executable, str(script_path)] + (args or [])
        start_t = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            duration = round(time.time() - start_t, 3)
            diagnostics = {}
            if res.returncode != 0 and res.stderr:
                lines = res.stderr.strip().splitlines()
                error_line = lines[-1] if lines else "Unknown runtime error"
                failing_line = next((l.strip() for l in reversed(lines) if "File " in l and "line " in l), None)
                diagnostics = {
                    "error_type": error_line.split(":")[0] if ":" in error_line else "RuntimeError",
                    "error_message": error_line,
                    "failing_location": failing_line,
                    "stack_depth": sum(1 for l in lines if "File " in l),
                }

            return {
                "success": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "duration_s": duration,
                "diagnostics": diagnostics,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -99,
                "error": f"Script timed out after {timeout} seconds.",
                "stdout": "",
                "stderr": "",
                "diagnostics": {"error_type": "TimeoutExpired"},
            }

    def run_tests(self, workspace_name: str, test_pattern: str = "test*.py") -> Dict[str, Any]:
        """Runs unit tests inside the workspace and captures results."""
        ws = self.get_workspace_dir(workspace_name)
        if "/" in test_pattern or "\\" in test_pattern or ".." in test_pattern:
            raise PermissionError(f"Invalid test discovery pattern: '{test_pattern}'")

        cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(ws), "-t", str(ws), "-p", test_pattern]
        start_t = time.time()
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ws)
            res = subprocess.run(
                cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=15.0,
                env=env,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            duration = round(time.time() - start_t, 3)
            passed = res.returncode in [0, 5]
            return {
                "success": passed,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "tests_passed": res.returncode == 0 or (res.returncode == 5 and "Ran 0 tests" in res.stderr),
                "duration_s": duration,
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "tests_passed": False,
                "duration_s": 0.0,
            }


coding_agent = CodingAgent()


# Tools
class InspectWorkspaceTool(BaseTool):
    name = "coding_inspect_workspace"
    description = "Inspects coding workspace structure and file listings."
    risk_level = RiskLevel.LOW

    def execute(self, workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        data = coding_agent.inspect_workspace(workspace_name)
        return ToolResult(success=True, output=data)


class WriteCodeFileTool(BaseTool):
    name = "coding_write_file"
    description = "Creates or overwrites a source code file inside the approved project workspace."
    risk_level = RiskLevel.MEDIUM

    def execute(self, filename: str, content: str = "", workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        if not content:
            # Default working script if none passed
            content = (
                "\"\"\"Auto-generated by SAM Autonomous Coding Agent.\"\"\"\n"
                "import sys\n"
                "def main():\n"
                "    print('Hello from SAM Autonomous Coding Agent!')\n"
                "    print(f'Python version: {sys.version}')\n"
                "    return 0\n\n"
                "if __name__ == '__main__':\n"
                "    sys.exit(main())\n"
            )
        path = coding_agent.write_file(workspace_name, filename, content)
        return ToolResult(
            success=True,
            output=f"Successfully wrote code file: {filename}",
            artifacts=[str(path)]
        )


class ReadCodeFileTool(BaseTool):
    name = "coding_read_file"
    description = "Safely reads the contents of a source code file inside the project workspace."
    risk_level = RiskLevel.LOW

    def execute(self, filename: str, workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        try:
            content = coding_agent.read_file(workspace_name, filename)
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class RunScriptTool(BaseTool):
    name = "coding_run_script"
    description = "Executes a Python script in the isolated workspace and captures stdout and stderr."
    risk_level = RiskLevel.MEDIUM

    def execute(self, filename: str, workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        result = coding_agent.run_script(workspace_name, filename)
        return ToolResult(
            success=result["success"],
            output=result,
            error=result.get("stderr") if not result["success"] else None
        )


class VerifyCodingResultsTool(BaseTool):
    name = "coding_verify_results"
    description = "Verifies script execution output, asserts exit code 0, and inspects for runtime tracebacks."
    risk_level = RiskLevel.LOW

    def execute(self, filename: str, workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        res = coding_agent.run_script(workspace_name, filename)
        passed = res["success"] and not res.get("stderr")
        return ToolResult(
            success=passed,
            output={
                "verified": passed,
                "stdout_sample": res.get("stdout", "")[:200],
                "exit_code": res.get("exit_code"),
            },
            error=None if passed else f"Script exited with error code {res.get('exit_code')}: {res.get('stderr')}"
        )


class RollbackCodeFileTool(BaseTool):
    name = "coding_rollback_file"
    description = "Restores a source code file to its previous checkpoint backup (.bak)."
    risk_level = RiskLevel.MEDIUM

    def execute(self, filename: str, workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        success = coding_agent.rollback_file(workspace_name, filename)
        if success:
            return ToolResult(success=True, output=f"Successfully rolled back '{filename}' from checkpoint.")
        return ToolResult(success=False, error=f"No backup checkpoint found for '{filename}'.")


class RunTestsTool(BaseTool):
    name = "coding_run_tests"
    description = "Discovers and executes automated unit tests inside the workspace."
    risk_level = RiskLevel.LOW

    def execute(self, pattern: str = "test*.py", workspace_name: str = "default_project", **kwargs: Any) -> ToolResult:
        res = coding_agent.run_tests(workspace_name, pattern)
        return ToolResult(
            success=res["tests_passed"],
            output=res,
            error=res.get("stderr") if not res["tests_passed"] else None,
        )


# Register tools
tool_registry.register(InspectWorkspaceTool())
tool_registry.register(WriteCodeFileTool())
tool_registry.register(ReadCodeFileTool())
tool_registry.register(RunScriptTool())
tool_registry.register(VerifyCodingResultsTool())
tool_registry.register(RollbackCodeFileTool())
tool_registry.register(RunTestsTool())

