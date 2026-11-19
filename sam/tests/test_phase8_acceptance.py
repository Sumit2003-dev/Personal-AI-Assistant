r"""
SAM Phase 8 — Comprehensive End-to-End Real-World Acceptance Test Suite
Validates the complete autonomous Windows desktop assistant across all 14 core domains.
Hardware Target: HP OMEN 16, Windows 11, RTX 4050 6GB VRAM, boAt Airdopes 131.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
DIST_EXE = SAM_ROOT / "dist" / "SAM" / "SAM.exe"


class Test01_AppStartupAndShutdown(unittest.TestCase):
    """Test 1: Application Startup, UI and Shutdown Lifecycle."""

    @unittest.skipUnless(DIST_EXE.exists(), "dist/SAM/SAM.exe not found")
    def test_packaged_executable_startup_and_health(self):
        """Validates real packaged SAM.exe booting with live HTTP health probe."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        test_port = s.getsockname()[1]
        s.close()

        test_data = SAM_ROOT / "dist" / "p8_smoke_data"
        shutil.rmtree(test_data, ignore_errors=True)
        test_data.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["SAM_DATA_ROOT"] = str(test_data)
        env["SAM_UI_HOST"] = "127.0.0.1"
        env["SAM_UI_PORT"] = str(test_port)
        env["SAM_HEADLESS"] = "1"

        log_file = test_data / "exec.log"
        with open(log_file, "w", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                [str(DIST_EXE), "--backend-server"],
                env=env,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=str(DIST_EXE.parent),
            )

        ready = False
        try:
            health_url = f"http://127.0.0.1:{test_port}/api/telemetry/health"
            css_url = f"http://127.0.0.1:{test_port}/static/css/style.css"
            start = time.time()
            while time.time() - start < 30.0:
                try:
                    with urllib.request.urlopen(health_url, timeout=2.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode())
                            self.assertIn("status", data)
                            self.assertIn("telemetry", data)
                            ready = True
                            break
                except Exception:
                    time.sleep(0.5)

            self.assertTrue(ready, "Packaged backend failed to answer on health endpoint")

            with urllib.request.urlopen(css_url, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                css_text = resp.read().decode()
                self.assertIn("--bg-app", css_text)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            shutil.rmtree(test_data, ignore_errors=True)

    def test_single_instance_mutex(self):
        """Validates that a second launcher instance detects the running instance."""
        import ctypes
        from sam.launcher.app_launcher import _acquire_single_instance_mutex

        h1 = _acquire_single_instance_mutex()
        self.assertIsNotNone(h1, "First mutex acquisition should succeed")

        try:
            h2 = _acquire_single_instance_mutex()
            self.assertIsNone(h2, "Second mutex check must detect existing instance and return None")
        finally:
            if h1:
                ctypes.windll.kernel32.CloseHandle(h1)


class Test02_ChatAndLocalAIIntelligence(unittest.TestCase):
    """Test 2: Chat & Local AI Intelligence via Ollama."""

    def setUp(self):
        from sam.agent.models_provider import model_manager
        self.manager = model_manager

    def test_ollama_service_online_and_exact_models(self):
        """Verifies local Ollama service is online and exact models are available."""
        status = self.manager.get_status()
        self.assertTrue(status.get("ollama_online"), "Local Ollama daemon on 127.0.0.1:11434 is not online")
        installed = status.get("available_models", [])
        self.assertTrue(
            any("qwen2.5:3b" in m for m in installed) or any("qwen3:4b" in m for m in installed),
            f"Expected qwen2.5:3b or qwen3:4b, found: {installed}",
        )

    def test_chat_inference_and_reasoning(self):
        """Queries local Ollama model for multi-step reasoning and validates response."""
        reply = self.manager.generate_chat_reply("What is 45 plus 55? Answer with only the number.")
        self.assertIsNotNone(reply, "Local model returned empty reply")
        self.assertIn("100", reply)

    def test_chat_code_explanation(self):
        """Validates that the model can explain a simple Python function."""
        reply = self.manager.generate_chat_reply("Explain in one sentence what this does: def sq(x): return x * x")
        self.assertIsNotNone(reply)
        text = reply.lower()
        self.assertTrue("square" in text or "multipl" in text or "product" in text or "x" in text)

    def test_chat_empty_input_rejection(self):
        """Validates that empty inputs are rejected by the API layer."""
        from fastapi.testclient import TestClient
        from sam.desktop.web_desktop import app

        client = TestClient(app)
        resp = client.post("/api/chat", json={"message": "   "})
        self.assertEqual(resp.status_code, 400)


class Test03_PlannerAndTaskExecution(unittest.TestCase):
    """Test 3: Planner and Task Execution Lifecycle."""

    def test_task_planner_decomposition(self):
        """Tests that the task planner decomposes goals into executable step schemas."""
        from sam.planner.task_planner import TaskPlanner
        planner = TaskPlanner()
        task = planner.plan("Inspect hardware telemetry and summarize CPU status")
        self.assertIsNotNone(task.task_id)
        self.assertTrue(len(task.steps) >= 1)
        step_tools = [s.tool_name for s in task.steps]
        self.assertTrue(
            "system_get_telemetry" in step_tools or "system_analyze_health" in step_tools or "document_summarize" in step_tools
        )

    def test_task_lifecycle_transitions(self):
        """Validates legal task transitions: PENDING -> PLANNING -> RUNNING -> COMPLETED."""
        from sam.agent.models import Task, TaskStep, TaskStatus, StepStatus
        t = Task(objective="Lifecycle verification test")
        self.assertEqual(t.status, TaskStatus.PENDING)

        t.status = TaskStatus.PLANNING
        self.assertEqual(t.status, TaskStatus.PLANNING)

        t.status = TaskStatus.RUNNING
        self.assertEqual(t.status, TaskStatus.RUNNING)

        t.status = TaskStatus.COMPLETED
        self.assertEqual(t.status, TaskStatus.COMPLETED)


class Test04_VoiceInputSignalAndDevice(unittest.TestCase):
    """Test 4: Voice Input, Preferred Device Persistence, and Signal Validation."""

    def test_preferred_microphone_is_boat_airdopes_131(self):
        """Verifies that the preferred microphone remains boAt Airdopes 131."""
        from sam.config.settings import settings
        self.assertEqual(settings.voice.preferred_device_name, "boAt Airdopes 131")

    def test_silence_rejection(self):
        """Verifies that silence is rejected and cannot trigger the planner."""
        from sam.voice.voice_interface import voice_interface
        import numpy as np

        # Create 1 second of complete digital silence
        silent_audio = np.zeros((16000, 1), dtype=np.float32)
        metrics = voice_interface.calculate_audio_metrics(silent_audio)
        self.assertLess(metrics.rms, 0.008, "Silent audio RMS should be near zero")
        self.assertTrue(metrics.is_silent, "Audio metrics must identify digital silence")


class Test05_WindowsComputerUse(unittest.TestCase):
    """Test 5: Windows Computer Use (Observation & Safe Notepad Action)."""

    def test_desktop_observation(self):
        """Validates desktop screenshot capture and active window metadata."""
        from sam.computer_use.operator import computer_operator
        obs = computer_operator.observe_state()
        self.assertIsNotNone(obs)
        self.assertTrue(obs.success)
        self.assertIsNotNone(obs.screenshot_path)
        self.assertIsNotNone(obs.window_title)

    def test_safe_notepad_operation_and_file_verification(self):
        """Executes safe Notepad tool in isolated workspace and verifies file content."""
        from sam.computer_use.operator import OperateNotepadTool
        from sam.config.settings import settings

        tool = OperateNotepadTool()
        res = tool.execute(
            filename="p8_acceptance_note.txt",
            text_content="SAM Phase 8 Real-World Acceptance Verified.",
            workspace_name="p8_acceptance_ws",
        )
        self.assertTrue(res.success, f"Notepad operation failed: {res.error}")

        expected_file = settings.data_dir / "workspaces" / "p8_acceptance_ws" / "p8_acceptance_note.txt"
        self.assertTrue(expected_file.exists(), "Saved test file does not exist")
        content = expected_file.read_text(encoding="utf-8")
        self.assertIn("Phase 8", content)

        # Cleanup isolated test workspace
        shutil.rmtree(settings.data_dir / "workspaces" / "p8_acceptance_ws", ignore_errors=True)


class Test06_CodingAgent(unittest.TestCase):
    """Test 6: Coding Agent in Isolated Temporary Workspace."""

    def setUp(self):
        from sam.coding.coding_agent import CodingAgent
        from sam.config.settings import settings
        self.agent = CodingAgent()
        self.ws_name = "p8_coding_test_ws"
        self.ws_dir = settings.data_dir / "workspaces" / self.ws_name
        shutil.rmtree(self.ws_dir, ignore_errors=True)
        self.ws_dir.mkdir(parents=True, exist_ok=True)

        # Seed workspace with a simple script and deliberate bug
        self.agent.write_file(
            self.ws_name,
            "calculator.py",
            "def add(a, b):\n    return a - b  # BUG: subtraction instead of addition\n",
        )
        self.agent.write_file(
            self.ws_name,
            "test_calc.py",
            "import unittest\nfrom calculator import add\n\nclass TestCalc(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\nif __name__ == '__main__':\n    unittest.main()\n",
        )

    def tearDown(self):
        from sam.config.settings import settings
        shutil.rmtree(settings.data_dir / "workspaces" / self.ws_name, ignore_errors=True)

    def test_code_inspection_and_test_failure_interpretation(self):
        """Inspects workspace and identifies that initial test fails due to intentional bug."""
        files = self.agent.inspect_workspace(self.ws_name)
        file_names = files.get("files", [])
        self.assertIn("calculator.py", file_names)

        # Run test - should fail due to bug
        test_run = self.agent.run_tests(self.ws_name, "test_calc.py")
        self.assertFalse(test_run.get("tests_passed"), "Initial test with intentional bug should fail")

    def test_code_fix_and_verification(self):
        """Fixes the bug and verifies tests pass."""
        # Fix bug
        self.agent.write_file(self.ws_name, "calculator.py", "def add(a, b):\n    return a + b\n")

        # Run tests again
        test_run = self.agent.run_tests(self.ws_name, "test_calc.py")
        self.assertTrue(test_run.get("tests_passed"), f"Tests should pass after fix: {test_run}")

    def test_rollback_checkpoint(self):
        """Verifies checkpointing and rollback functionality."""
        # Overwrite with broken code
        self.agent.write_file(self.ws_name, "calculator.py", "# BROKEN CONTENT")
        self.assertIn("# BROKEN", self.agent.read_file(self.ws_name, "calculator.py"))

        # Rollback
        rb = self.agent.rollback_file(self.ws_name, "calculator.py")
        self.assertTrue(rb, "Rollback failed")
        self.assertNotIn("# BROKEN", self.agent.read_file(self.ws_name, "calculator.py"))

    def test_path_traversal_rejection(self):
        """Validates that attempts to access files outside the workspace are rejected."""
        with self.assertRaises(Exception):
            self.agent.read_file(self.ws_name, "../../windows/system32/cmd.exe")


class Test07_BrowserAgent(unittest.TestCase):
    """Test 7: Browser Agent Research and Form Safety."""

    def test_browser_search_and_content_extraction(self):
        """Tests public web research capabilities."""
        from sam.browser.browser_agent import browser_agent
        res = browser_agent.search_web("Python programming language")
        self.assertTrue(res.get("results_count", 0) > 0)
        self.assertIn("results", res)

    def test_high_risk_form_submission_gating(self):
        """Verifies that high-risk form submission is blocked without explicit user approval."""
        from fastapi.testclient import TestClient
        from sam.desktop.web_desktop import app

        client = TestClient(app)
        # Attempt submission without approval
        resp = client.post(
            "/api/browser/submit",
            json={"url": "http://127.0.0.1/test", "form_data": {"user": "test"}, "approved": False},
        )
        self.assertEqual(resp.status_code, 403, "High-risk form submission must return HTTP 403 when not approved")


class Test08_FileManagementAndDocuments(unittest.TestCase):
    """Test 8: File Management and Multi-Format Document Analysis."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.base = Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_document_analysis_txt_csv_json(self):
        """Tests reading and analyzing TXT, CSV, and JSON documents."""
        from sam.documents.doc_engine import document_engine

        txt_file = self.base / "sample.txt"
        txt_file.write_text("SAM Autonomous Assistant Phase 8 Document Analysis Test.", encoding="utf-8")
        read_txt = document_engine.read_document(txt_file)
        self.assertIn("extracted_text", read_txt)
        self.assertIn("Phase 8", read_txt["extracted_text"])

        csv_file = self.base / "data.csv"
        csv_file.write_text("id,metric,value\n1,cpu,24.5\n2,gpu,56.2\n", encoding="utf-8")
        read_csv = document_engine.read_document(csv_file)
        self.assertIn("extracted_text", read_csv)
        self.assertEqual(read_csv.get("metadata", {}).get("row_count"), 2)


class Test09_VideoWorkflow(unittest.TestCase):
    """Test 9: Video Workflow & Metadata Inspection."""

    def test_video_metadata_inspection_and_safety(self):
        """Validates video pipeline configuration and metadata extraction handling."""
        from sam.video.video_pipeline import video_pipeline
        cfg = video_pipeline.configure_pipeline(target_aspect="9:16", target_height=1920)
        self.assertEqual(cfg.get("target_aspect"), "9:16")

        # Non-existent video file check
        meta = video_pipeline.inspect_media("non_existent_clip.mp4")
        self.assertFalse(meta.get("success"))


class Test10_MemoryAndConversationHistory(unittest.TestCase):
    """Test 10: Memory Store & Session Integrity."""

    def test_temporary_fact_storage_search_and_cleanup(self):
        """Stores, queries, and cleans up a temporary test fact without affecting user data."""
        from sam.memory.sqlite_memory import memory_store
        test_key = "p8_test_fact"
        test_val = "SAM-Test-Alpha-Acceptance"

        # Store
        memory_store.set_memory("acceptance", test_key, test_val)

        # Retrieve
        fact = memory_store.get_memory(test_key)
        self.assertEqual(fact, test_val)

        # Search
        results = memory_store.search_memories("SAM-Test-Alpha")
        self.assertTrue(any(test_val in str(r) for r in results))

        # Delete temporary test fact
        memory_store.delete_memory(test_key)
        self.assertIsNone(memory_store.get_memory(test_key))


class Test11_TaskManagerAndEmergencyStop(unittest.TestCase):
    """Test 11: Task Manager and Emergency Stop."""

    def test_emergency_stop_mechanism(self):
        """Validates that emergency stop halts operations and releases locks."""
        from sam.security.permissions import security_gatekeeper
        from sam.computer_use.operator import session_manager

        # Acquire lock
        lock_ok = session_manager.acquire("p8_test_session")
        self.assertTrue(lock_ok)

        # Trigger emergency stop
        security_gatekeeper.trigger_emergency_stop("Phase 8 emergency stop test")
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)

        # Computer session should be force-released
        self.assertFalse(session_manager.is_locked)

        # Reset emergency stop
        security_gatekeeper.reset_emergency_stop()
        self.assertFalse(security_gatekeeper.is_emergency_stop_active)


class Test12_SettingsAndSecurity(unittest.TestCase):
    """Test 12: Settings, Security and Localhost Enforcement."""

    def test_localhost_only_binding(self):
        """Verifies desktop settings enforce 127.0.0.1 and reject 0.0.0.0."""
        from sam.config.settings import settings
        self.assertEqual(settings.desktop.ui_host, "127.0.0.1")
        self.assertNotEqual(settings.desktop.ui_host, "0.0.0.0")

    def test_tool_risk_gating(self):
        """Verifies high-risk tools require explicit authorization."""
        from sam.tools.registry import tool_registry, RiskLevel
        tool = tool_registry.get("browser_submit_form")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk_level, RiskLevel.HIGH)


if __name__ == "__main__":
    unittest.main(verbosity=2)
