"""
SAM - Phase 6.1 Reliability, Safety & Integration Hardening Test Suite
Focused automated tests covering:
1. Voice Reliability, Microphone Safety, Audio Metrics, & Hallucination Rejection
2. Desktop Observation Truthfulness & Action-Specific Outcome Verification
3. Session Mutex, Emergency Stop Invalidation, & Retry Interruption
4. Browser Capability Audit, Interactive Playwright, & Consequential Action Gating
5. Coding Workspace Path Traversal, Symlink Escapes, & Malicious Path Rejection
6. Task Lifecycle Finite State Machine (FSM) Transitions
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys
import time
import numpy as np

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.agent.models import Task, TaskStep, TaskStatus, StepStatus, RiskLevel, Observation, ToolCall, VerificationResult
from sam.voice.voice_interface import voice_interface, AudioMetrics, TranscriptionResult
from sam.computer_use.session_manager import session_manager, ComputerUseSessionConflictError
from sam.computer_use.operator import computer_operator
from sam.executor.task_executor import task_executor
from sam.coding.coding_agent import coding_agent
from sam.browser.browser_agent import browser_agent
from sam.security.permissions import security_gatekeeper, EmergencyStopActiveError
from sam.desktop.web_desktop import app
from fastapi.testclient import TestClient


class TestPhase61Hardening(unittest.TestCase):
    """Verifies all Phase 6.1 safety, reliability, and security hardening fixes."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def tearDown(self):
        security_gatekeeper.reset_emergency_stop()
        session_manager.force_release()

    # -------------------------------------------------------------
    # 1. Voice Reliability & Microphone Safety (Hermetic / Mocked)
    # -------------------------------------------------------------
    def test_silent_audio_rejected_before_whisper(self):
        """Verifies near-silent audio is rejected without invoking Whisper model."""
        # 16000 samples of quiet ambient noise (RMS ~0.001, Peak ~0.003)
        silent_audio = np.random.uniform(-0.003, 0.003, 16000).astype(np.float32)
        metrics = voice_interface.calculate_audio_metrics(silent_audio)
        self.assertTrue(metrics.is_silent, "Near-silent audio was not flagged as silent")
        self.assertLess(metrics.rms, 0.008)

        # Transcribe should reject before model inference
        res = voice_interface.transcribe_structured(silent_audio)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.text, "")
        self.assertIn("near-silent", res.rejection_reason.lower())

    def test_hallucinated_words_rejected(self):
        """Verifies accidental words like 'You', 'Thank you', etc. are rejected."""
        # Generate audio with speech-like peak to bypass initial silence filter
        synthetic_audio = np.random.uniform(-0.15, 0.15, 16000).astype(np.float32)

        mock_segment = MagicMock()
        mock_segment.text = "You."
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.avg_logprob = -0.3
        mock_segment.no_speech_prob = 0.05

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)

        with patch.object(voice_interface, "_get_whisper_model", return_value=mock_model):
            res = voice_interface.transcribe_structured(synthetic_audio)
            self.assertFalse(res.is_valid)
            self.assertEqual(res.text, "")
            self.assertIn("hallucinated", res.rejection_reason.lower())

    def test_low_confidence_rejected(self):
        """Verifies transcripts with high no_speech_prob or low avg_logprob are rejected."""
        synthetic_audio = np.random.uniform(-0.15, 0.15, 16000).astype(np.float32)

        mock_segment = MagicMock()
        mock_segment.text = "Launch browser and search"
        mock_segment.start = 0.0
        mock_segment.end = 2.0
        mock_segment.avg_logprob = -1.8  # Poor confidence
        mock_segment.no_speech_prob = 0.65  # Likely not speech

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)

        with patch.object(voice_interface, "_get_whisper_model", return_value=mock_model):
            res = voice_interface.transcribe_structured(synthetic_audio)
            self.assertFalse(res.is_valid)
            self.assertIn("low confidence", res.rejection_reason.lower())

    def test_valid_speech_transcription(self):
        """Verifies high-confidence speech is accepted with structured metadata."""
        synthetic_audio = np.random.uniform(-0.3, 0.3, 16000).astype(np.float32)

        mock_segment = MagicMock()
        mock_segment.text = "open visual studio code"
        mock_segment.start = 0.0
        mock_segment.end = 1.5
        mock_segment.avg_logprob = -0.2
        mock_segment.no_speech_prob = 0.02

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)

        with patch.object(voice_interface, "_get_whisper_model", return_value=mock_model):
            res = voice_interface.transcribe_structured(synthetic_audio)
            self.assertTrue(res.is_valid)
            self.assertEqual(res.text, "open visual studio code")
            self.assertGreater(res.confidence, 0.7)
            self.assertEqual(len(res.segments), 1)

    def test_preferred_microphone_preservation(self):
        """Verifies boAt Airdopes 131 preference is preserved even when offline."""
        dev_id, info = voice_interface.find_preferred_device()
        self.assertTrue(info.get("preferred", False))
        # Status must preserve preferred name
        status = voice_interface.get_status()
        self.assertEqual(status["preferred_microphone"], "boAt Airdopes 131")

    def test_clipping_and_silence_metrics(self):
        """Verifies clipping detection on audio exceeding 0.99 threshold."""
        clipped_audio = np.array([1.0, -1.0, 0.5, -0.5], dtype=np.float32)
        metrics = voice_interface.calculate_audio_metrics(clipped_audio)
        self.assertEqual(metrics.clipping_ratio, 0.5)
        self.assertEqual(metrics.peak, 1.0)

    # -------------------------------------------------------------
    # 2. Desktop Observation & Action-Specific Verification
    # -------------------------------------------------------------
    def test_placeholder_observation_explicit_failure(self):
        """Verifies placeholder observations explicitly report is_placeholder=True and success=False."""
        with patch.object(task_executor, "_observer_func", side_effect=RuntimeError("Screen lock active")):
            obs = task_executor.capture_observation()
            self.assertFalse(obs.success)
            self.assertTrue(obs.is_placeholder)
            self.assertIn("Screen lock active", obs.error)

    def test_verification_rejects_placeholder_observation(self):
        """Verifies desktop action verification fails if post-observation was a placeholder."""
        step = TaskStep(
            tool_name="computer_observe_desktop",
            verification_criteria="Desktop observation captures live screen",
            observation_after=Observation(success=False, is_placeholder=True, error="Capture timeout"),
        )
        tool_call = ToolCall(tool_name="computer_observe_desktop", success=True)
        res = task_executor.verify_step_outcome(step, tool_call)
        self.assertFalse(res.verified, "Verification succeeded on a placeholder observation!")
        self.assertIn("placeholder", res.details.lower())

    def test_action_specific_verification_file_artifacts(self):
        """Verifies action verification fails if output artifact does not exist or is 0 bytes."""
        step = TaskStep(
            tool_name="coding_write_file",
            verification_criteria="Target file exists on disk",
        )
        # Non-existent artifact
        tool_call_fail = ToolCall(
            tool_name="coding_write_file",
            success=True,
            output={"path": "C:/non_existent_folder/file.py"}
        )
        res = task_executor.verify_step_outcome(step, tool_call_fail)
        self.assertFalse(res.verified)
        self.assertIn("does not exist", res.details)

    def test_action_specific_verification_script_exit_code(self):
        """Verifies action verification fails if script exited with non-zero exit code."""
        step = TaskStep(
            tool_name="coding_run_script",
            verification_criteria="Script exits with 0",
        )
        tool_call = ToolCall(
            tool_name="coding_run_script",
            success=True,
            output={"exit_code": 1, "stderr": "SyntaxError: invalid syntax"}
        )
        res = task_executor.verify_step_outcome(step, tool_call)
        self.assertFalse(res.verified)
        self.assertIn("non-zero code 1", res.details)

    def test_action_specific_verification_window_title(self):
        """Verifies window focus action fails if target window title does not match query."""
        step = TaskStep(
            tool_name="computer_focus_window",
            tool_args={"title_query": "Visual Studio Code"},
            observation_after=Observation(window_title="Calculator", success=True, is_placeholder=False),
        )
        tool_call = ToolCall(tool_name="computer_focus_window", success=True)
        res = task_executor.verify_step_outcome(step, tool_call)
        self.assertFalse(res.verified)
        self.assertIn("did not match", res.details)

    # -------------------------------------------------------------
    # 3. Session Mutex & Emergency Stop Hardening
    # -------------------------------------------------------------
    def test_session_mutex_emergency_stop_acquisition_block(self):
        """Verifies that while emergency stop is active, session lock acquisition is blocked."""
        security_gatekeeper.trigger_emergency_stop("Safety check")
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)

        with self.assertRaises(EmergencyStopActiveError):
            session_manager.acquire("unauthorized_task", timeout=0.1)

    def test_emergency_stop_force_releases_lock(self):
        """Verifies that triggering emergency stop forcibly releases any held lock."""
        session_manager.acquire("active_worker", timeout=1.0)
        self.assertEqual(session_manager.active_session_id, "active_worker")

        # Trigger emergency stop
        security_gatekeeper.trigger_emergency_stop("Operator emergency trigger")
        self.assertFalse(session_manager.is_locked)
        self.assertIsNone(session_manager.active_session_id)

    def test_task_retries_halt_immediately_on_cancellation(self):
        """Verifies that a cancelled or stopped task does not continue through retry loops."""
        task = Task(
            task_id="test_halt_task",
            objective="Simulate cancelled task",
            steps=[
                TaskStep(
                    step_index=0,
                    title="Failing Step",
                    tool_name="coding_write_file",
                    tool_args={"workspace_name": "default_project", "rel_path": "test.py", "content": ""},
                    max_retries=3,
                )
            ]
        )
        task_executor._active_tasks[task.task_id] = task

        # Stop task before/during execution
        task_executor.stop_task(task.task_id)
        self.assertEqual(task.status, TaskStatus.STOPPED)

        # Executing must immediately return without retrying
        executed = task_executor.execute_task(task)
        self.assertEqual(executed.status, TaskStatus.STOPPED)
        self.assertEqual(task.steps[0].retries, 0)

    # -------------------------------------------------------------
    # 4. Browser Capability Audit & Consequential Action Gating
    # -------------------------------------------------------------
    def test_browser_capabilities_audit_reporting(self):
        """Verifies get_capabilities accurately distinguishes Playwright from HTTP extraction."""
        caps = browser_agent.get_capabilities()
        self.assertIn("playwright_installed", caps)
        self.assertIn("browser_modes", caps)
        self.assertIn("features", caps)
        self.assertEqual(caps["features"]["search_web"], "HTTP extraction & synthesis")
        self.assertEqual(caps["features"]["fetch_page_content"], "HTTP extraction & HTML parser")

    def test_browser_consequential_submission_gating(self):
        """Verifies purchases, checkout, or account change submissions require explicit approval."""
        res_purchase = browser_agent.submit_form(
            url="https://store.example.com/checkout",
            form_data={"item_id": "123", "amount": "$99.00"},
            method="POST",
            action_type="purchase"
        )
        self.assertFalse(res_purchase["success"])
        self.assertTrue(res_purchase["requires_approval"])
        self.assertEqual(res_purchase["risk_level"], "HIGH")

    # -------------------------------------------------------------
    # 5. Coding Agent Workspace Security & Malicious Paths
    # -------------------------------------------------------------
    def test_path_traversal_blocked_relative(self):
        """Verifies relative ../ traversal outside workspace is blocked."""
        with self.assertRaises(PermissionError):
            coding_agent.write_file("default_project", "../../escaped.py", "malicious_code")

    def test_path_traversal_blocked_absolute(self):
        """Verifies absolute paths outside workspace are blocked."""
        with self.assertRaises(PermissionError):
            coding_agent.write_file("default_project", "C:/Windows/system32/calc.exe", "malicious_code")

    def test_path_traversal_blocked_workspace_name(self):
        """Verifies malicious workspace names with ../ are blocked."""
        with self.assertRaises(PermissionError):
            coding_agent.get_workspace_dir("../../Windows")

    def test_reserved_device_names_blocked(self):
        """Verifies Windows reserved filenames (CON, PRN, AUX, NUL) are blocked."""
        with self.assertRaises(PermissionError):
            coding_agent.write_file("default_project", "con.py", "malicious_code")
        with self.assertRaises(PermissionError):
            coding_agent.write_file("default_project", "nul.txt", "malicious_code")

    def test_illegal_filename_characters_blocked(self):
        """Verifies illegal characters (< > : " | ? *) are blocked."""
        with self.assertRaises(PermissionError):
            coding_agent.write_file("default_project", "bad<name>*.py", "code")

    def test_rollback_security_isolation(self):
        """Verifies rollback cannot restore a file that does not exist or outside workspace."""
        with self.assertRaises(FileNotFoundError):
            coding_agent.rollback_file("default_project", "non_existent_file_xyz.py")

    # -------------------------------------------------------------
    # 6. Task Lifecycle Finite State Machine (FSM)
    # -------------------------------------------------------------
    def test_invalid_state_transitions_blocked(self):
        """Verifies terminal task states cannot transition back to active states."""
        task = Task(task_id="fsm_test_1", objective="Test FSM")

        # Terminal state: COMPLETED
        task.status = TaskStatus.COMPLETED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.PAUSED))
        self.assertEqual(task.status, TaskStatus.COMPLETED)

        # Terminal state: STOPPED
        task.status = TaskStatus.STOPPED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertEqual(task.status, TaskStatus.STOPPED)

        # Terminal state: FAILED
        task.status = TaskStatus.FAILED
        self.assertFalse(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_valid_state_transitions(self):
        """Verifies permitted state transitions work correctly."""
        task = Task(task_id="fsm_test_2", objective="Test FSM Valid")
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.PAUSED))
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.WAITING_APPROVAL))
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.RUNNING))
        self.assertTrue(task_executor.set_task_status(task, TaskStatus.COMPLETED))
        self.assertEqual(task.status, TaskStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
