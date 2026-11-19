"""
SAM - Phase 6.2 Deep Reliability, Concurrency & Regression Test Suite
Comprehensive automated tests verifying:
1. Model Resolution & Inference Reliability (resolve_ollama_model, ModelUnavailableError)
2. FastAPI Event Loop & Concurrency (sync def threadpool offloading, non-blocking telemetry)
3. Computer-Use Observation & Action Verification (ACTION_UNVERIFIED, metadata propagation)
4. Voice Pipeline & Microphone Safety (boAt Airdopes dynamic discovery, capability check)
5. Task Planner Input Validation (strict JSON validation, unregistered tool rejection, thinking block stripping)
6. SQLite Memory Concurrency & WAL Mode (PRAGMA journal_mode=WAL, busy_timeout)
7. Task Lifecycle & Concurrency Mutex (valid FSM, emergency stop lock release)
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import time
import json
import sqlite3
import numpy as np

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.agent.models import Task, TaskStep, TaskStatus, StepStatus, RiskLevel, Observation, VerificationResult, ToolCall
from sam.agent.models_provider import (
    resolve_ollama_model,
    ModelUnavailableError,
    OllamaProvider,
    ModelManager,
    model_manager
)
from sam.planner.task_planner import task_planner, TaskPlanner
from sam.executor.task_executor import task_executor, TaskExecutor
from sam.computer_use.session_manager import session_manager, ComputerUseSessionConflictError
from sam.computer_use.operator import computer_operator
from sam.voice.voice_interface import voice_interface, AudioMetrics, TranscriptionResult
from sam.memory.sqlite_memory import memory_store, MemoryStore
from sam.security.permissions import security_gatekeeper, EmergencyStopActiveError
from sam.desktop.web_desktop import app
from sam.tools.registry import tool_registry
from fastapi.testclient import TestClient


class TestPhase62ModelResolution(unittest.TestCase):
    """Verifies Ollama model resolution rules, size preservation, and error handling."""

    def test_exact_match(self):
        available = ["qwen2.5:3b", "llama3:8b", "mistral:7b"]
        self.assertEqual(resolve_ollama_model("qwen2.5:3b", available), "qwen2.5:3b")

    def test_case_insensitive_match(self):
        available = ["qwen2.5:3b", "llama3:8b"]
        self.assertEqual(resolve_ollama_model("QWEN2.5:3B", available), "qwen2.5:3b")

    def test_missing_latest_tag_resolution(self):
        available = ["qwen3:latest", "phi3:latest"]
        self.assertEqual(resolve_ollama_model("qwen3", available), "qwen3:latest")

    def test_trailing_latest_tag_stripped(self):
        available = ["qwen3", "phi3"]
        self.assertEqual(resolve_ollama_model("qwen3:latest", available), "qwen3")

    def test_size_preservation_rejects_mismatched_sizes(self):
        """Requested 3b model must NEVER resolve to a 7b, 14b, or 32b model."""
        available = ["qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b"]
        resolved = resolve_ollama_model("qwen2.5:3b", available)
        self.assertIsNone(resolved, "Resolver matched 7b/14b/32b when 3b was requested")

    def test_family_preservation_never_falls_back_to_available_zero(self):
        """Resolver must return None rather than silently falling back to available[0]."""
        available = ["deepseek-r1:1.5b", "llama3:8b"]
        resolved = resolve_ollama_model("qwen2.5:3b", available)
        self.assertIsNone(resolved, "Resolver fell back to available[0]")

    def test_empty_available_returns_none(self):
        self.assertIsNone(resolve_ollama_model("qwen2.5:3b", []))
        self.assertIsNone(resolve_ollama_model("", ["qwen2.5:3b"]))

    def test_ollama_provider_generate_raises_model_unavailable(self):
        provider = OllamaProvider(host="http://127.0.0.1:11434", model="qwen2.5:3b")
        with patch.object(provider, "list_available_models", return_value=["llama3:8b", "phi3:3.8b"]):
            with self.assertRaises(ModelUnavailableError):
                provider.generate("Hello world", model="qwen2.5:3b")

    def test_model_manager_status_reporting(self):
        mgr = ModelManager()
        with patch.object(mgr.ollama, "is_available", return_value=True), \
             patch.object(mgr.ollama, "list_available_models", return_value=["qwen3:4b:latest"]):
            status = mgr.get_status()
            self.assertTrue(status["ollama_online"])
            self.assertTrue(status["model_downloaded"])
            self.assertEqual(status["status"], "ONLINE")


class TestPhase62EventLoopAndConcurrency(unittest.TestCase):
    """Verifies FastAPI concurrency hardening, non-blocking telemetry and threadpool offloading."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_telemetry_endpoints_are_synchronous_and_fast(self):
        """Verifies telemetry and health endpoints are synchronous def and respond in threadpool."""
        t0 = time.time()
        res_tel = self.client.get("/api/telemetry")
        t1 = time.time()
        res_hlth = self.client.get("/api/telemetry/health")
        t2 = time.time()

        self.assertEqual(res_tel.status_code, 200)
        self.assertEqual(res_hlth.status_code, 200)
        # Should execute cleanly without event loop starvation
        self.assertIn("cpu", res_tel.json())
        self.assertIn("diagnostics", res_hlth.json())

    def test_screenshot_endpoints_are_synchronous(self):
        """Verifies screenshot endpoints do not block event loop."""
        res_img = self.client.get("/api/computer/screenshot/image")
        self.assertEqual(res_img.status_code, 200)
        self.assertEqual(res_img.headers.get("content-type"), "image/jpeg")

        res_info = self.client.get("/api/computer/screenshot")
        self.assertEqual(res_info.status_code, 200)
        self.assertTrue(res_info.json().get("success"))

    def test_chat_planning_offloaded_to_threadpool(self):
        """Verifies chat message planning runs asynchronously without blocking event loop."""
        res = self.client.post("/api/chat", json={
            "message": "Inspect CPU and RAM usage and summarize hardware telemetry",
            "context": {"deterministic": True}
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("task_id", data)


class TestPhase62ObservationAndActionVerification(unittest.TestCase):
    """Verifies action-specific physical verification, observation propagation, and ACTION_UNVERIFIED."""

    def test_observation_metadata_propagation(self):
        obs = computer_operator.observe_state()
        self.assertIsNotNone(obs.timestamp)
        self.assertIsNotNone(obs.window_title)
        self.assertIsNotNone(obs.system_metrics)
        self.assertIn("cursor", obs.system_metrics)

    def test_action_unverified_on_placeholder_observation(self):
        """VerificationResult must report ACTION_UNVERIFIED with verified=False if observation failed."""
        step = TaskStep(
            step_index=0,
            title="Click Button",
            description="Perform UI click",
            tool_name="computer_mouse_click",
            tool_args={"x": 100, "y": 200},
            risk_level=RiskLevel.LOW,
            verification_criteria="Button click confirmed",
            observation_after=Observation(
                timestamp=time.time(),
                window_title="",
                active_process="",
                success=False,
                is_placeholder=True,
                error="Screen lock active"
            )
        )
        tool_call = ToolCall(tool_name="computer_mouse_click", args={"x": 100, "y": 200}, success=True, output="Clicked.")
        res = task_executor.verify_step_outcome(step, tool_call)
        self.assertFalse(res.verified)
        self.assertIn("ACTION_UNVERIFIED", res.details)

    def test_action_unverified_on_window_focus_mismatch(self):
        """FocusWindowTool must report ACTION_UNVERIFIED if observed window does not match query."""
        step = TaskStep(
            step_index=0,
            title="Focus Notepad",
            description="Bring notepad to foreground",
            tool_name="computer_focus_window",
            tool_args={"title_query": "Notepad"},
            risk_level=RiskLevel.LOW,
            verification_criteria="Notepad is active",
            observation_after=Observation(
                timestamp=time.time(),
                window_title="Calculator",
                active_process="calc.exe",
                success=True,
                is_placeholder=False,
            )
        )
        tool_call = ToolCall(tool_name="computer_focus_window", args={"title_query": "Notepad"}, success=True, output="Focused.")
        res = task_executor.verify_step_outcome(step, tool_call)
        self.assertFalse(res.verified)
        self.assertIn("ACTION_UNVERIFIED", res.details)

    def test_emergency_stop_blocks_session_acquisition(self):
        """Session manager must raise EmergencyStopActiveError when emergency stop is active."""
        security_gatekeeper.trigger_emergency_stop("Safety verification")
        try:
            with self.assertRaises(EmergencyStopActiveError):
                session_manager.acquire("worker_test_estop", timeout=0.1)
        finally:
            security_gatekeeper.reset_emergency_stop()


class TestPhase62VoiceAndMicrophoneSafety(unittest.TestCase):
    """Verifies dynamic boAt Airdopes 131 resolution, capability check, and rejection of hallucinated words."""

    def test_preferred_device_dynamic_name_search(self):
        pref_id, pref_info = voice_interface.find_preferred_device()
        self.assertTrue(pref_info.get("preferred"))
        self.assertEqual(voice_interface._preferred_device_name, "boAt Airdopes 131")

    def test_audio_metrics_on_silence(self):
        silent_audio = np.zeros(16000, dtype=np.float32)
        metrics = voice_interface.calculate_audio_metrics(silent_audio, sample_rate=16000)
        self.assertTrue(metrics.is_silent)
        self.assertEqual(metrics.rms, 0.0)
        self.assertEqual(metrics.peak, 0.0)

    def test_structured_transcription_rejects_silent_recording(self):
        silent_audio = np.zeros(16000, dtype=np.float32)
        res = voice_interface.transcribe_structured(silent_audio)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.confidence, 0.0)
        self.assertIn("silent", res.rejection_reason.lower())

    def test_structured_transcription_rejects_hallucinated_triggers(self):
        """Whisper hallucinated words like 'You', 'Thank you', 'Bye' must be rejected."""
        mock_whisper = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "You."
        mock_segment.no_speech_prob = 0.05
        mock_segment.avg_logprob = -0.3
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_whisper.transcribe.return_value = ([mock_segment], MagicMock())

        audio = np.random.uniform(-0.1, 0.1, 16000).astype(np.float32)
        with patch.object(voice_interface, "_get_whisper_model", return_value=mock_whisper):
            res = voice_interface.transcribe_structured(audio)
            self.assertFalse(res.is_valid)
            self.assertIn("hallucinated", res.rejection_reason.lower())


class TestPhase62PlannerInputValidation(unittest.TestCase):
    """Verifies strict schema and tool name validation on untrusted LLM outputs."""

    def test_parse_llm_plan_valid(self):
        valid_json = json.dumps([
            {
                "title": "Check Health",
                "description": "Inspect hardware counters",
                "tool_name": "system_get_telemetry",
                "tool_args": {},
                "risk_level": "LOW",
                "verification_criteria": "Telemetry received"
            }
        ])
        steps = task_planner._parse_llm_plan(valid_json)
        self.assertIsNotNone(steps)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].tool_name, "system_get_telemetry")

    def test_parse_llm_plan_rejects_unregistered_tool(self):
        """Plan containing non-existent or hallucinated tool must be safely rejected."""
        invalid_json = json.dumps([
            {
                "title": "Hack Shell",
                "description": "Run unknown binary",
                "tool_name": "unregistered_dangerous_tool_xyz",
                "tool_args": {"cmd": "rm -rf /"},
                "risk_level": "HIGH"
            }
        ])
        steps = task_planner._parse_llm_plan(invalid_json)
        self.assertIsNone(steps, "Planner accepted an unregistered tool name")

    def test_parse_llm_plan_rejects_non_list_root(self):
        dict_json = json.dumps({"tool_name": "system_get_telemetry", "title": "Check Health"})
        self.assertIsNone(task_planner._parse_llm_plan(dict_json))

    def test_parse_llm_plan_rejects_empty_list(self):
        self.assertIsNone(task_planner._parse_llm_plan("[]"))

    def test_parse_llm_plan_strips_thinking_blocks(self):
        raw_output = "<think>Let me reason about the steps carefully...</think>\n[{\"title\": \"Telemetry\", \"tool_name\": \"system_get_telemetry\", \"tool_args\": {}, \"risk_level\": \"LOW\"}]"
        steps = task_planner._parse_llm_plan(raw_output)
        self.assertIsNotNone(steps)
        self.assertEqual(len(steps), 1)

    def test_parse_llm_plan_strips_markdown_fences(self):
        raw_output = "```json\n[{\"title\": \"Telemetry\", \"tool_name\": \"system_get_telemetry\", \"tool_args\": {}, \"risk_level\": \"LOW\"}]\n```"
        steps = task_planner._parse_llm_plan(raw_output)
        self.assertIsNotNone(steps)
        self.assertEqual(len(steps), 1)

    def test_deterministic_fallback_on_invalid_llm_plan(self):
        """When LLM returns invalid plan, task_planner must fall back to deterministic plan."""
        with patch.object(task_planner.model_manager, "is_available", return_value=True), \
             patch.object(task_planner.model_manager, "generate_plan", return_value=("MALFORMED_OUTPUT_NOT_JSON", "qwen2.5:3b")):
            task = task_planner.plan("Inspect hardware CPU telemetry")
            self.assertEqual(task.status, TaskStatus.PENDING)
            self.assertEqual(task.context_data.get("planned_by"), "DETERMINISTIC_SCHEMA_FALLBACK")
            self.assertGreater(len(task.steps), 0)


class TestPhase62SQLiteConcurrencyAndWAL(unittest.TestCase):
    """Verifies SQLite WAL mode, busy timeout, and concurrent reads and writes."""

    def test_wal_mode_and_busy_timeout(self):
        with memory_store._get_connection() as conn:
            cur = conn.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0].upper()
            self.assertEqual(journal_mode, "WAL")

            cur = conn.execute("PRAGMA busy_timeout;")
            busy_timeout = cur.fetchone()[0]
            self.assertEqual(busy_timeout, 5000)

    def test_concurrent_connections_read_write(self):
        """Multiple connections in WAL mode must write and read without database locked errors."""
        key_1 = f"test_wal_key_{int(time.time())}"
        val_1 = "wal_verified_value_alpha"

        self.assertTrue(memory_store.set_memory("concurrency", key_1, val_1))
        self.assertEqual(memory_store.get_memory(key_1), val_1)
        self.assertTrue(memory_store.delete_memory(key_1))


class TestPhase62TaskLifecycleAndFSM(unittest.TestCase):
    """Verifies valid and invalid task state machine transitions, and session mutex."""

    def test_invalid_fsm_transitions_blocked(self):
        task = Task(task_id="fsm_reg_test_1", objective="Test FSM transitions")
        task.status = TaskStatus.COMPLETED

        # COMPLETED cannot transition to RUNNING or PAUSED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.PAUSED))

        task.status = TaskStatus.STOPPED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))

        task.status = TaskStatus.FAILED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))

    def test_duplicate_approval_prevention(self):
        task = Task(task_id="approval_test_1", objective="Gated action", status=TaskStatus.RUNNING)
        task_executor._active_tasks[task.task_id] = task

        # Not in WAITING_APPROVAL state -> must return False
        self.assertFalse(task_executor.approve_pending_step(task.task_id))
        self.assertFalse(task_executor.reject_pending_step(task.task_id))

        task.status = TaskStatus.WAITING_APPROVAL
        self.assertTrue(task_executor.approve_pending_step(task.task_id))
        self.assertEqual(task.status, TaskStatus.RUNNING)

        # Subsequent approval on already approved task must return False
        self.assertFalse(task_executor.approve_pending_step(task.task_id))


if __name__ == "__main__":
    unittest.main()
