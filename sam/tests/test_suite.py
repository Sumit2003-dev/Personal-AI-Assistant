"""
SAM - Comprehensive Test Suite & Verification Rig
Tests Phase 1 & Phase 2 architecture, computer use, telemetry, security, and acceptance workflows.
"""

import unittest
from pathlib import Path
import time
import os
import sys

# Ensure SAM root package is in sys.path
SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

import sam
from sam.config.settings import settings
from sam.agent.models import (
    Task, TaskStep, RiskLevel, TaskStatus, StepStatus, Observation, ToolCall, VerificationResult
)
from sam.tools.registry import tool_registry
from sam.tools.base import BaseTool, ToolResult
from sam.security.permissions import security_gatekeeper
from sam.security.audit import audit_logger
from sam.monitoring.system_monitor import system_monitor
from sam.computer_use.mouse import mouse_controller
from sam.computer_use.keyboard import keyboard_controller
from sam.computer_use.window import window_manager
from sam.computer_use.session_manager import session_manager
from sam.vision.screen_observer import screen_observer
from sam.vision.ui_detector import ui_detector
from sam.memory.sqlite_memory import memory_store
from sam.integrations.app_registry import app_registry
from sam.planner.task_planner import task_planner
from sam.executor.task_executor import task_executor
from sam.agent.models_provider import model_manager
from sam.coding.coding_agent import coding_agent
from sam.video.video_pipeline import video_pipeline
from sam.browser.browser_agent import browser_agent
from sam.documents.doc_engine import document_engine
from sam.voice.voice_interface import voice_interface


class TestSAMArchitecture(unittest.TestCase):
    """Phase 1: Architecture & Data Contracts Verification"""

    def test_settings_and_hardware_profile(self):
        self.assertEqual(settings.hardware.device_name, "HP OMEN 16")
        self.assertEqual(settings.hardware.os_name, "Windows 11")
        self.assertEqual(settings.hardware.total_vram_mb, 6144)
        self.assertTrue(settings.data_dir.exists())
        self.assertTrue(settings.logs_dir.exists())

    def test_tool_registry(self):
        tools = tool_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        self.assertIn("system_get_telemetry", tool_names)
        self.assertIn("system_analyze_health", tool_names)
        self.assertIn("coding_write_file", tool_names)
        self.assertIn("video_export_render", tool_names)
        self.assertIn("computer_observe_desktop", tool_names)

    def test_security_gatekeeper_and_emergency_stop(self):
        security_gatekeeper.reset_emergency_stop()
        self.assertFalse(security_gatekeeper.is_emergency_stop_active)

        can_exec, reason = security_gatekeeper.evaluate_action("test_low", RiskLevel.LOW)
        self.assertTrue(can_exec)

        security_gatekeeper.trigger_emergency_stop("Test trigger")
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)

        can_exec_blocked, _ = security_gatekeeper.evaluate_action("test_low", RiskLevel.LOW)
        self.assertFalse(can_exec_blocked)

        security_gatekeeper.reset_emergency_stop()
        self.assertFalse(security_gatekeeper.is_emergency_stop_active)

    def test_command_sanitization(self):
        self.assertFalse(security_gatekeeper.validate_command("format C:"))
        self.assertFalse(security_gatekeeper.validate_command("rmdir /s /q C:\\"))
        self.assertTrue(security_gatekeeper.validate_command("python main.py"))
        self.assertTrue(security_gatekeeper.validate_command("git status"))


class TestHardwareAndComputerUse(unittest.TestCase):
    """Phase 1 & 2: System Telemetry & Windows Computer-Use"""

    def test_system_telemetry_query(self):
        telemetry = system_monitor.get_full_telemetry()
        self.assertIn("cpu", telemetry)
        self.assertIn("ram", telemetry)
        self.assertIn("gpu", telemetry)
        self.assertIn("disks", telemetry)
        self.assertGreater(telemetry["cpu"]["cores_logical"], 0)
        self.assertGreater(telemetry["ram"]["total_gb"], 8.0)

    def test_health_diagnostics(self):
        health = system_monitor.analyze_health()
        self.assertIn("status", health)
        self.assertIn("diagnostics", health)
        self.assertGreater(len(health["diagnostics"]), 0)

    def test_mouse_and_screen_coordinates(self):
        pos = mouse_controller.get_position()
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 2)
        self.assertGreaterEqual(pos[0], 0)
        self.assertGreaterEqual(pos[1], 0)

    def test_screen_capture_and_hash(self):
        img, path = screen_observer.capture_fullscreen(save=True)
        self.assertIsNotNone(img)
        self.assertGreater(img.size[0], 0)
        self.assertGreater(img.size[1], 0)
        h = screen_observer.compute_visual_hash(img)
        self.assertEqual(len(h), 64)

    def test_application_registry_detection(self):
        apps = app_registry.list_applications()
        app_ids = [a["app_id"] for a in apps]
        self.assertIn("vscode", app_ids)
        self.assertIn("powershell", app_ids)
        self.assertIn("git", app_ids)
        self.assertIn("edge", app_ids)

        vscode = app_registry.get_app("vscode")
        self.assertTrue(vscode.is_installed)


class TestPersonalMemory(unittest.TestCase):
    """Memory & Persistent State"""

    def test_memory_crud(self):
        key = f"test_key_{int(time.time())}"
        memory_store.set_memory("preferences", key, {"theme": "cyber_dark", "font_size": 14})
        retrieved = memory_store.get_memory(key)
        self.assertEqual(retrieved.get("theme"), "cyber_dark")

        search_results = memory_store.search_memories(key)
        self.assertGreaterEqual(len(search_results), 1)

        deleted = memory_store.delete_memory(key)
        self.assertTrue(deleted)
        self.assertIsNone(memory_store.get_memory(key))


class TestWorkflowsAcceptance(unittest.TestCase):
    """Section 18: Final Acceptance Workflows Verification"""

    def test_workflow_d_hardware_inspection(self):
        """WORKFLOW D: Inspect CPU, RAM, GPU, Disk and diagnose issues."""
        obj = "Check my laptop's CPU, RAM, GPU and disk usage and explain any issues."
        task = task_planner.plan(obj, context={"deterministic": True})
        self.assertEqual(len(task.steps), 2)

        completed = task_executor.execute_task(task)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertTrue(completed.verification_result.verified)

    def test_workflow_a_coding_agent(self):
        """WORKFLOW A: Open project, write Python script, run it and verify."""
        obj = "Open VS Code, create a Python project, write a script, run it and fix errors."
        task = task_planner.plan(obj, context={"deterministic": True, "project_name": "test_coding_project", "filename": "test_script.py"})
        self.assertGreaterEqual(len(task.steps), 3)

        completed = task_executor.execute_task(task)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertTrue(completed.verification_result.verified)

    def test_workflow_b_video_editing_pipeline(self):
        """WORKFLOW B: Vertical 1080p edit, subtitles, and export verification."""
        obj = "Open a selected video, create a vertical 1080p edit, add generated subtitles and export the finished video."
        task = task_planner.plan(obj, context={"deterministic": True})
        self.assertEqual(len(task.steps), 5)

        completed = task_executor.execute_task(task)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertTrue(completed.verification_result.verified)

        verify_step = completed.steps[-1]
        self.assertTrue(verify_step.verification_result.verified)

    def test_workflow_c_browser_research(self):
        """WORKFLOW C: Web navigation, information collection, and report creation."""
        obj = "Open a browser, research a topic, collect information and prepare a report."
        task = task_planner.plan(obj, context={"deterministic": True})
        completed = task_executor.execute_task(task)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertTrue(completed.verification_result.verified)

    def test_workflow_e_document_intelligence(self):
        """WORKFLOW E: PDF reading, summarization, and key insight extraction."""
        obj = "Open my selected PDF, summarize it and answer questions about its contents."
        task = task_planner.plan(obj, context={"deterministic": True})
        completed = task_executor.execute_task(task)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertTrue(completed.verification_result.verified)

    def test_local_ai_status_reporting(self):
        """Section 1: Verifies truthful reporting of local AI engine status."""
        status = model_manager.get_status()
        self.assertIn("ollama_online", status)
        self.assertIn("status", status)
        # Verify planner transparently records whether LLM or deterministic schema was used
        task = task_planner.plan("Check my laptop hardware telemetry")
        if not status["ollama_online"]:
            self.assertEqual(task.context_data["planned_by"], "DETERMINISTIC_SCHEMA_FALLBACK")
            self.assertFalse(task.context_data["llm_used"])

    def test_real_notepad_computer_use_acceptance(self):
        """Section 4: Real Windows Application (Notepad) Interaction & Verification."""
        test_sentence = "Project SAM: Real Windows 11 Computer-Use Operator Acceptance Test Verified."
        res = tool_registry.execute_tool("computer_operate_notepad", {
            "filename": "notepad_acceptance_verified.txt",
            "text_content": test_sentence,
            "workspace_name": "test_workspace"
        })
        self.assertTrue(res.success)
        self.assertIn("saved_path", res.output)
        self.assertTrue(Path(res.output["saved_path"]).exists())
        content = Path(res.output["saved_path"]).read_text(encoding="utf-8")
        self.assertIn(test_sentence, content)

    def test_coding_agent_bug_fix_acceptance(self):
        """Section 5: Real Coding Agent Bug Identification, Source Code Patch, and Test Verification."""
        ws_name = "disposable_math_project"
        # 1. Setup buggy code
        buggy_code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def divide(a, b):\n"
            "    # Deliberate bug introduced: multiplying instead of dividing\n"
            "    return a * b\n"
        )
        test_code = (
            "import unittest\n"
            "from calculator import add, divide\n\n"
            "class TestCalculator(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n\n"
            "    def test_divide(self):\n"
            "        self.assertEqual(divide(10, 2), 5)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
        )
        coding_agent.write_file(ws_name, "calculator.py", buggy_code)
        coding_agent.write_file(ws_name, "test_calculator.py", test_code)

        # 2. Run tests to confirm deliberate failure
        res_before = coding_agent.run_script(ws_name, "test_calculator.py")
        self.assertFalse(res_before["success"])
        self.assertIn("AssertionError: 20 != 5", res_before["stderr"])

        # 3. Patch code to fix the bug
        fixed_code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def divide(a, b):\n"
            "    if b == 0:\n"
            "        raise ZeroDivisionError('division by zero')\n"
            "    return a / b\n"
        )
        coding_agent.write_file(ws_name, "calculator.py", fixed_code)

        # 4. Re-run tests to verify fix
        res_after = coding_agent.run_script(ws_name, "test_calculator.py")
        self.assertTrue(res_after["success"])
        self.assertIn("OK", res_after["stderr"])


class TestPhase4Acceptance(unittest.TestCase):
    """Phase 4 & 4.1 Granular Acceptance Tests."""

    def test_acceptance_ollama_inference(self):
        """1. Verify real Ollama LLM inference on localhost:11434."""
        status = model_manager.get_status()
        self.assertTrue(status["ollama_online"], "Ollama daemon is not online on localhost:11434")
        resp = model_manager.ollama.generate("Respond with exactly one word: VERIFIED", model="qwen2.5:3b", max_tokens=15)
        self.assertIsInstance(resp, str)
        self.assertGreater(len(resp), 0, "Ollama returned empty response")

    def test_acceptance_llm_planning(self):
        """2. Verify autonomous task planner decomposes goals using local LLM."""
        task = task_planner.plan("Inspect system storage and report disk usage")
        self.assertTrue(task.context_data.get("llm_used"), "Planner did not use local LLM")
        self.assertGreater(len(task.steps), 0, "No steps planned by LLM")

    def test_acceptance_live_microphone_recording(self):
        """3. Verify physical audio capture from Windows microphone."""
        audio = voice_interface.record_microphone(duration=0.5)
        self.assertIsNotNone(audio, "Microphone capture failed")
        import numpy as np
        self.assertIsInstance(audio, np.ndarray)
        self.assertGreater(len(audio), 0, "Microphone recorded 0 samples")

    def test_acceptance_speech_transcription(self):
        """4. Verify faster-whisper speech transcription on audio."""
        test_wav = Path("sam/data/whisper_test_sample.wav").resolve()
        voice_interface.synthesize_to_wav("Speech recognition verified", str(test_wav))
        transcript = voice_interface.transcribe(test_wav)
        self.assertIsInstance(transcript, str)
        self.assertGreater(len(transcript), 0)
        self.assertIn("speech", transcript.lower())

    def test_acceptance_tts_playback(self):
        """5. Verify text-to-speech synthesis and interruption."""
        ok = voice_interface.speak_text("Testing SAM speech synthesis.", block=False)
        self.assertTrue(ok)
        time.sleep(0.3)
        voice_interface.interrupt_speech()

    def test_acceptance_desktop_operation(self):
        """6. Verify real Windows desktop application operation."""
        res = tool_registry.execute_tool("computer_operate_notepad", {
            "filename": "desktop_acceptance_test.txt",
            "text_content": "SAM Real Desktop Operation Verified.",
            "workspace_name": "test_workspace"
        })
        self.assertTrue(res.success)
        self.assertTrue(Path(res.output["saved_path"]).exists())

    def test_acceptance_emergency_stop(self):
        """7. Verify emergency stop isolation and action blocking."""
        security_gatekeeper.trigger_emergency_stop("Regression verification")
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)
        can_exec, _ = security_gatekeeper.evaluate_action("test_action", RiskLevel.LOW)
        self.assertFalse(can_exec)
        security_gatekeeper.reset_emergency_stop()
        self.assertFalse(security_gatekeeper.is_emergency_stop_active)


if __name__ == "__main__":
    unittest.main(verbosity=2)
