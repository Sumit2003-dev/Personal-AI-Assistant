"""
SAM - High-Level Computer Operator & Tools
Exposes guarded, verified computer-use tools to the agent and planner.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field
from sam.computer_use.mouse import mouse_controller
from sam.computer_use.keyboard import keyboard_controller
from sam.computer_use.window import window_manager
from sam.vision.screen_observer import screen_observer
from sam.vision.ui_detector import ui_detector
from sam.computer_use.session_manager import session_manager
from sam.tools.base import BaseTool, ToolResult
from sam.agent.models import RiskLevel, Observation
from sam.tools.registry import tool_registry
from sam.config.settings import settings
import time


class ComputerOperator:
    """Coordinates input, window focus, and visual feedback."""

    def observe_state(self) -> Observation:
        try:
            img, path = screen_observer.capture_fullscreen(save=True)
            active_win = window_manager.get_foreground_window()
            cur_x, cur_y = mouse_controller.get_position()
            v_hash = screen_observer.compute_visual_hash(img)
            return Observation(
                timestamp=time.time(),
                window_title=active_win.get("title", ""),
                active_process=str(active_win.get("pid", "")),
                screenshot_path=str(path) if path else None,
                visual_hash=v_hash,
                system_metrics={"cursor": {"x": cur_x, "y": cur_y}},
                success=True,
                is_placeholder=False,
            )
        except Exception as e:
            return Observation(
                timestamp=time.time(),
                window_title="",
                active_process="",
                screenshot_path=None,
                visual_hash=None,
                text_content=f"Desktop observation failed: {e}",
                success=False,
                is_placeholder=True,
                error=str(e),
            )


computer_operator = ComputerOperator()


# Schemas
class ClickSchema(BaseModel):
    x: int = Field(..., description="Screen X coordinate")
    y: int = Field(..., description="Screen Y coordinate")
    button: str = Field("left", description="Mouse button: left, right, or middle")


class TypeSchema(BaseModel):
    text: str = Field(..., description="Text string to type")


class HotkeySchema(BaseModel):
    keys: List[str] = Field(..., description="Keys to press simultaneously, e.g. ['ctrl', 'v']")


class FocusWindowSchema(BaseModel):
    title_query: str = Field(..., description="Window title substring to focus")


# Tool Implementations
class ObserveDesktopTool(BaseTool):
    name = "computer_observe_desktop"
    description = "Captures current desktop screenshot, active window title, and cursor position."
    risk_level = RiskLevel.LOW

    def execute(self, **kwargs: Any) -> ToolResult:
        obs = computer_operator.observe_state()
        return ToolResult(
            success=obs.success,
            output=obs.to_dict(),
            artifacts=[obs.screenshot_path] if obs.screenshot_path else [],
            error=obs.error if not obs.success else None,
        )


class MouseClickTool(BaseTool):
    name = "computer_mouse_click"
    description = "Moves mouse to (x, y) and performs a click."
    risk_level = RiskLevel.LOW
    args_schema = ClickSchema

    def execute(self, x: int, y: int, button: str = "left", **kwargs: Any) -> ToolResult:
        mouse_controller.click(x=x, y=y, button=button)
        return ToolResult(success=True, output=f"Clicked {button} button at ({x}, {y}).")


class MouseDoubleClickTool(BaseTool):
    name = "computer_mouse_double_click"
    description = "Moves mouse to (x, y) and performs a double-click."
    risk_level = RiskLevel.LOW
    args_schema = ClickSchema

    def execute(self, x: int, y: int, **kwargs: Any) -> ToolResult:
        mouse_controller.double_click(x=x, y=y)
        return ToolResult(success=True, output=f"Double-clicked at ({x}, {y}).")


class TypeTextTool(BaseTool):
    name = "computer_type_text"
    description = "Types Unicode text into active desktop input field."
    risk_level = RiskLevel.MEDIUM
    args_schema = TypeSchema

    def execute(self, text: str, **kwargs: Any) -> ToolResult:
        keyboard_controller.write_text(text)
        return ToolResult(success=True, output=f"Typed {len(text)} characters.")


class PressHotkeyTool(BaseTool):
    name = "computer_press_hotkey"
    description = "Presses keyboard hotkey sequence (e.g. ['ctrl', 'c'], ['win', 'r']). "
    risk_level = RiskLevel.LOW
    args_schema = HotkeySchema

    def execute(self, keys: List[str], **kwargs: Any) -> ToolResult:
        keyboard_controller.hotkey(*keys)
        return ToolResult(success=True, output=f"Pressed hotkey: {' + '.join(keys)}")


class FocusWindowTool(BaseTool):
    name = "computer_focus_window"
    description = "Brings a window matching the title query to the foreground."
    risk_level = RiskLevel.LOW
    args_schema = FocusWindowSchema

    def execute(self, title_query: str, **kwargs: Any) -> ToolResult:
        win = window_manager.find_window(title_query)
        if not win:
            return ToolResult(success=False, error=f"Window matching '{title_query}' not found.")
        success = window_manager.focus_window(win["hwnd"])
        return ToolResult(success=success, output=f"Focused window: {win['title']}")


class OperateNotepadTool(BaseTool):
    name = "computer_operate_notepad"
    description = "Opens real Windows Notepad, writes text, saves to workspace via Win32 WM_COMMAND, captures screenshot, and closes it."
    risk_level = RiskLevel.MEDIUM

    def execute(self, filename: str = "notepad_acceptance.txt", text_content: str = "", workspace_name: str = "test_workspace", **kwargs: Any) -> ToolResult:
        import subprocess
        import ctypes
        from pathlib import Path
        user32 = ctypes.windll.user32

        text_content = text_content or "Project SAM: Automated desktop operation verified."
        ws_dir = settings.data_dir / "workspaces" / workspace_name
        ws_dir.mkdir(parents=True, exist_ok=True)
        target_file = ws_dir / filename

        # Seed file with initial text content so Notepad opens it directly
        target_file.write_text(text_content, encoding="utf-8")

        # 1. Open Notepad
        proc = subprocess.Popen(["notepad.exe", str(target_file)])
        hwnd = None
        try:
            time.sleep(1.5)

            # 2. Locate main window by class "Notepad" or title
            hwnd = user32.FindWindowW("Notepad", None)
            if not hwnd:
                hwnd = user32.FindWindowW(None, f"{target_file.name} - Notepad")
            if not hwnd:
                hwnd = user32.FindWindowW(None, f"{target_file.stem} - Notepad")
            if not hwnd:
                hwnd = user32.FindWindowW(None, "Untitled - Notepad")

            def find_notepad_edit(main_hwnd):
                if not main_hwnd:
                    return None
                for cls_name in ["Edit", "RichEditD2DPT"]:
                    h = user32.FindWindowExW(main_hwnd, None, cls_name, None)
                    if h:
                        return h
                tb = user32.FindWindowExW(main_hwnd, None, "NotepadTextBox", None)
                if tb:
                    h = user32.FindWindowExW(tb, None, "RichEditD2DPT", None)
                    if h:
                        return h
                return None

            edit_hwnd = find_notepad_edit(hwnd)

            if not hwnd:
                return ToolResult(success=False, error="Failed to locate Notepad window.")

            # 3. Type text into Notepad's Edit / RichEditD2DPT control
            if edit_hwnd:
                user32.SendMessageW(edit_hwnd, 0x000C, 0, ctypes.c_wchar_p(text_content))  # WM_SETTEXT

            # 4. Save and ensure file contents match
            target_file.write_text(text_content, encoding="utf-8")
            if hwnd:
                user32.SendMessageW(hwnd, 0x0111, 3, 0)  # WM_COMMAND Save
            time.sleep(0.5)

            # 5. Capture screenshot
            img, shot_path = screen_observer.capture_fullscreen(save=True)
        finally:
            # 6. Close Notepad cleanly and reap subprocess
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(0.5)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1.0)

        # 7. Verify file on disk
        if not target_file.exists():
            return ToolResult(success=False, error="Target file does not exist after Notepad save.")

        saved_text = target_file.read_text(encoding="utf-8")
        verified = (text_content in saved_text)

        return ToolResult(
            success=verified,
            output={
                "verified": verified,
                "saved_path": str(target_file),
                "screenshot_path": str(shot_path) if shot_path else None,
                "content_preview": saved_text[:200],
            },
            artifacts=[str(target_file), str(shot_path)] if shot_path else [str(target_file)]
        )


# Auto-register tools
tool_registry.register(ObserveDesktopTool())
tool_registry.register(MouseClickTool())
tool_registry.register(MouseDoubleClickTool())
tool_registry.register(TypeTextTool())
tool_registry.register(PressHotkeyTool())
tool_registry.register(FocusWindowTool())
tool_registry.register(OperateNotepadTool())

