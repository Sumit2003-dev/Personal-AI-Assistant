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


class CodingAgent:
    """Manages coding workspaces, file edits, script execution, and test verification."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or DEFAULT_WORKSPACE_ROOT
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def get_workspace_dir(self, name: str) -> Path:
        ws = (self.workspace_root / name).resolve()
        ws.mkdir(parents=True, exist_ok=True)
        return ws

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
        ws = self.get_workspace_dir(workspace_name)
        target = (ws / rel_path).resolve()
        # Security boundary check
        if ws not in target.parents and target != ws:
            raise PermissionError("Path traversal outside workspace is blocked.")
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
        ws = self.get_workspace_dir(workspace_name)
        target = (ws / rel_path).resolve()
        backup_path = target.with_name(f"{target.name}.bak")
        if not backup_path.exists():
            return False
        shutil.copy2(backup_path, target)
        return True

    def read_file(self, workspace_name: str, rel_path: str) -> str:
        ws = self.get_workspace_dir(workspace_name)
        target = (ws / rel_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"File '{rel_path}' does not exist in workspace '{workspace_name}'.")
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
        script_path = (ws / script_rel_path).resolve()
        if not script_path.exists():
            return {
                "success": False,
                "exit_code": -1,
                "error": f"Script '{script_rel_path}' not found.",
                "stdout": "",
                "stderr": "",
                "diagnostics": {"error_type": "FileNotFound", "details": f"Script '{script_rel_path}' not found."},
            }

        cmd = [sys.executable, str(script_path)] + (args or [])
        start_t = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=timeout,
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
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", test_pattern]
        start_t = time.time()
        try:
            res = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, timeout=30.0)
            duration = round(time.time() - start_t, 3)
            return {
                "success": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "tests_passed": res.returncode == 0,
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

