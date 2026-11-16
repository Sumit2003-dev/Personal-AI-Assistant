"""
SAM - Phase 6 Complete Agent Integrations Test Suite
Comprehensive automated tests verifying end-to-end integration across:
1. AI Orchestration & Memory Context Injection
2. Computer-Use Real Observer & Session Mutex
3. Coding Agent Checkpointing, Rollback & Diagnostics
4. Browser Agent Web Research & Submission Security Gate
5. Document Agent Multi-Format Parsing & Source Preservation
6. Video Pipeline Non-Destructive 1080p Rendering
7. Shared Orchestration, Emergency Stop & Lifecycle (Pause/Resume/Cancel)
8. Desktop Web REST Endpoints
"""

import unittest
from pathlib import Path
import sys
import time
import shutil

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.agent.models import Task, TaskStep, TaskStatus, StepStatus, RiskLevel, Observation
from sam.planner.task_planner import task_planner
from sam.agent.models_provider import model_manager
from sam.executor.task_executor import task_executor
from sam.computer_use.session_manager import session_manager, ComputerUseSessionConflictError
from sam.computer_use.operator import computer_operator
from sam.coding.coding_agent import coding_agent
from sam.browser.browser_agent import browser_agent
from sam.documents.doc_engine import document_engine
from sam.video.video_pipeline import video_pipeline
from sam.memory.sqlite_memory import memory_store
from sam.security.permissions import security_gatekeeper, EmergencyStopActiveError
from sam.desktop.web_desktop import app
from fastapi.testclient import TestClient


class TestAgentIntegrations(unittest.TestCase):
    """Verifies complete Phase 6 agent integrations and shared orchestration."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def tearDown(self):
        security_gatekeeper.reset_emergency_stop()

    # -------------------------------------------------------------
    # 1. AI Orchestration & Memory Injection
    # -------------------------------------------------------------
    def test_planner_retrieves_memory_and_context(self):
        """Verifies that planning an objective retrieves relevant memories and recent messages."""
        # Store a test preference
        memory_store.set_memory("preferences", "preferred_coding_style", "PEP8 compliant with type hints")
        memory_store.log_message("user", "Hello SAM, remember my preferred style.")

        # Plan a task with deterministic mode for fast predictable assertion
        task = task_planner.plan(
            "Write python project coding script with preferred_coding_style",
            context={"deterministic": True}
        )
        self.assertIsNotNone(task)
        self.assertIn("retrieved_memories", task.context_data)
        self.assertIn("recent_history", task.context_data)

        # Confirm preferred_coding_style was retrieved
        memories = task.context_data["retrieved_memories"]
        found = any("preferred_coding_style" in str(m.get("key")) for m in memories)
        self.assertTrue(found, "Planner failed to retrieve stored preference from memory_store")

    # -------------------------------------------------------------
    # 2. Computer-Use Observer & Session Mutex
    # -------------------------------------------------------------
    def test_task_executor_observation_and_visual_verification(self):
        """Verifies that task execution captures before/after observations and records visual hashes."""
        task = Task(
            task_id=f"test_obs_{int(time.time())}",
            objective="Capture desktop state and inspect hardware",
            steps=[
                TaskStep(
                    step_index=0,
                    title="Inspect Hardware",
                    description="Query telemetry counters",
                    tool_name="system_get_telemetry",
                    tool_args={},
                    risk_level=RiskLevel.LOW,
                    verification_criteria="Telemetry contains CPU stats",
                )
            ]
        )
        executed = task_executor.execute_task(task)
        self.assertEqual(executed.status, TaskStatus.COMPLETED)
        step = executed.steps[0]
        self.assertIsNotNone(step.observation_before)
        self.assertIsNotNone(step.observation_after)
        self.assertIsNotNone(step.verification_result)
        self.assertTrue(step.verification_result.verified)

    def test_session_manager_mutex_concurrency_lock(self):
        """Verifies that concurrent tasks attempting computer-use respect the session mutex."""
        session_id_1 = f"session_alpha_{int(time.time())}"
        session_id_2 = f"session_beta_{int(time.time())}"

        # Acquire lock for session 1
        self.assertTrue(session_manager.acquire(session_id_1, timeout=1.0))
        self.assertEqual(session_manager.active_session_id, session_id_1)

        # Attempting to acquire lock for session 2 must raise ComputerUseSessionConflictError
        with self.assertRaises(ComputerUseSessionConflictError):
            session_manager.acquire(session_id_2, timeout=0.2)

        # Release session 1
        self.assertTrue(session_manager.release(session_id_1))
        self.assertIsNone(session_manager.active_session_id)

        # Now session 2 can acquire
        self.assertTrue(session_manager.acquire(session_id_2, timeout=1.0))
        self.assertTrue(session_manager.release(session_id_2))

    # -------------------------------------------------------------
    # 3. Coding Agent Checkpointing, Rollback & Diagnostics
    # -------------------------------------------------------------
    def test_coding_checkpointing_and_rollback(self):
        """Verifies that writing to an existing file creates a .bak checkpoint and rollback restores it."""
        ws = "test_checkpoint_ws"
        fname = "algorithm.py"
        initial_code = "# Version 1.0\ndef solve(): return 42\n"
        updated_code = "# Version 2.0 (Broken)\ndef solve(): raise ValueError('Syntax fault')\n"

        # 1. First write (fresh)
        path1 = coding_agent.write_file(ws, fname, initial_code)
        self.assertTrue(path1.exists())
        self.assertEqual(coding_agent.read_file(ws, fname), initial_code)

        # 2. Overwrite file -> should create algorithm.py.bak
        path2 = coding_agent.write_file(ws, fname, updated_code)
        bak_file = path2.with_name(f"{fname}.bak")
        self.assertTrue(bak_file.exists(), "Checkpoint backup file was not created on overwrite")
        self.assertEqual(bak_file.read_text(encoding="utf-8"), initial_code)
        self.assertEqual(coding_agent.read_file(ws, fname), updated_code)

        # 3. Rollback
        restored = coding_agent.rollback_file(ws, fname)
        self.assertTrue(restored, "Rollback operation reported failure")
        self.assertEqual(coding_agent.read_file(ws, fname), initial_code, "File was not restored to version 1.0")

    def test_coding_diagnostics_on_runtime_error(self):
        """Verifies that script execution captures structured diagnostics on error."""
        ws = "test_diagnostics_ws"
        fname = "failing_script.py"
        code = "import sys\ndef crash():\n    raise ZeroDivisionError('Division by zero in test')\ncrash()\n"
        coding_agent.write_file(ws, fname, code)

        res = coding_agent.run_script(ws, fname)
        self.assertFalse(res["success"])
        self.assertNotEqual(res["exit_code"], 0)
        self.assertIn("diagnostics", res)
        diag = res["diagnostics"]
        self.assertIn("ZeroDivisionError", diag.get("error_message", ""))
        self.assertGreater(diag.get("stack_depth", 0), 0)

    def test_coding_test_runner(self):
        """Verifies workspace unit test execution runner."""
        ws = "test_runner_ws"
        test_file = "test_sample.py"
        test_code = (
            "import unittest\n"
            "class SampleTest(unittest.TestCase):\n"
            "    def test_truth(self): self.assertTrue(True)\n"
            "if __name__ == '__main__': unittest.main()\n"
        )
        coding_agent.write_file(ws, test_file, test_code)
        res = coding_agent.run_tests(ws)
        self.assertTrue(res["tests_passed"])
        self.assertEqual(res["exit_code"], 0)

    # -------------------------------------------------------------
    # 4. Browser Agent Navigation, Extraction & Security
    # -------------------------------------------------------------
    def test_browser_agent_search_and_links(self):
        """Verifies structured web search and link extraction."""
        res_search = browser_agent.search_web("FastAPI Python architecture", max_results=3)
        self.assertIn("query", res_search)
        self.assertGreater(res_search["results_count"], 0)
        first = res_search["results"][0]
        self.assertIn("title", first)
        self.assertIn("url", first)
        self.assertIn("snippet", first)

        res_links = browser_agent.extract_links("https://en.wikipedia.org/wiki/Python_(programming_language)")
        self.assertIn("total_links", res_links)
        self.assertGreater(res_links["total_links"], 0)

    def test_browser_submission_security_gating(self):
        """Verifies that external form submissions require explicit user confirmation."""
        # By default, HIGH risk actions without manual approval must be blocked
        res = browser_agent.submit_form(
            url="https://api.external.service.com/submit",
            form_data={"username": "test_user", "action": "publish_data"},
            method="POST"
        )
        self.assertFalse(res["success"])
        self.assertTrue(res.get("requires_approval", False))
        self.assertIn("explicit user confirmation", res.get("error", ""))

    # -------------------------------------------------------------
    # 5. Document Agent Multi-Format & Source Preservation
    # -------------------------------------------------------------
    def test_document_agent_multi_format_read_and_export(self):
        """Verifies PDF, CSV, TXT reading and non-destructive report export."""
        # 1. Test CSV reading
        ws = "test_doc_ws"
        csv_file = "sample_data.csv"
        csv_data = "id,name,role,status\n1,Alice,Architect,Active\n2,Bob,Developer,Active\n"
        csv_path = coding_agent.write_file(ws, csv_file, csv_data)

        read_res = document_engine.read_document(csv_path)
        self.assertEqual(read_res["format"], ".csv")
        self.assertIn("Alice", read_res["extracted_text"])
        self.assertIn("columns", read_res["metadata"])

        # 2. Test Export Analysis while preserving original CSV
        export_path = document_engine.export_analysis(csv_path, format="md")
        self.assertTrue(export_path.exists())
        # Confirm original CSV is unmodified
        self.assertEqual(csv_path.read_text(encoding="utf-8"), csv_data)

    # -------------------------------------------------------------
    # 6. Video Pipeline Non-Destructive Operations
    # -------------------------------------------------------------
    def test_video_pipeline_preserves_source_and_trims(self):
        """Verifies that video operations preserve source footage and render to dedicated export dirs."""
        demo_src = video_pipeline.generate_demo_source_if_needed()
        self.assertTrue(demo_src.exists())
        original_size = demo_src.stat().st_size

        # Trim clip
        trim_res = video_pipeline.trim_clip(start_sec=0.0, end_sec=1.0, input_path=demo_src)
        self.assertTrue(trim_res["success"])
        self.assertEqual(trim_res["source_preserved"], str(demo_src))

        # Confirm original source is unchanged
        self.assertEqual(demo_src.stat().st_size, original_size)

        # Confirm trimmed clip exists in exports dir
        trimmed_file = Path(trim_res["output_path"])
        self.assertTrue(trimmed_file.exists())
        self.assertGreater(trimmed_file.stat().st_size, 0)

    # -------------------------------------------------------------
    # 7. Shared Orchestration: Emergency Stop & Lifecycle
    # -------------------------------------------------------------
    def test_emergency_stop_halts_active_task(self):
        """Verifies that activating emergency stop halts task execution immediately."""
        security_gatekeeper.trigger_emergency_stop(reason="Automated Integration Test Trigger")
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)

        task = Task(
            task_id=f"test_estop_{int(time.time())}",
            objective="Inspect hardware counters",
            steps=[
                TaskStep(
                    step_index=0,
                    title="Inspect Hardware",
                    description="Query telemetry counters",
                    tool_name="system_get_telemetry",
                    tool_args={},
                    risk_level=RiskLevel.LOW,
                )
            ]
        )
        executed = task_executor.execute_task(task)
        self.assertEqual(executed.status, TaskStatus.STOPPED)
        self.assertIn("Emergency stop", executed.error_details)

    def test_pause_resume_stop_task_lifecycle(self):
        """Verifies task pause, resume, and stop controls."""
        tid = f"task_ctrl_{int(time.time())}"
        task = Task(task_id=tid, objective="Sample long running task", steps=[])
        task_executor._active_tasks[tid] = task
        task.status = TaskStatus.RUNNING

        # Pause
        self.assertTrue(task_executor.pause_task(tid))
        self.assertEqual(task.status, TaskStatus.PAUSED)

        # Resume
        self.assertTrue(task_executor.resume_task(tid))
        self.assertEqual(task.status, TaskStatus.RUNNING)

        # Stop
        self.assertTrue(task_executor.stop_task(tid))
        self.assertEqual(task.status, TaskStatus.STOPPED)

    # -------------------------------------------------------------
    # 8. Web Desktop REST Endpoints
    # -------------------------------------------------------------
    def test_new_desktop_endpoints(self):
        """Verifies the new Phase 6 REST endpoints in web_desktop."""
        # Coding test endpoint
        res_test = self.client.post("/api/coding/test", json={"workspace": "default_project", "pattern": "test*.py"})
        self.assertEqual(res_test.status_code, 200)

        # Coding rollback endpoint
        res_rb = self.client.post("/api/coding/rollback", json={"workspace": "default_project", "filename": "non_existent.py"})
        self.assertEqual(res_rb.status_code, 404)

        # Browser search endpoint
        res_bs = self.client.post("/api/browser/search", json={"query": "Windows 11 API", "max_results": 2})
        self.assertEqual(res_bs.status_code, 200)
        self.assertIn("results", res_bs.json())

        # Browser links endpoint
        res_bl = self.client.post("/api/browser/links", json={"url": "https://www.python.org"})
        self.assertEqual(res_bl.status_code, 200)
        self.assertIn("links", res_bl.json())

        # Browser submit endpoint (security blocked -> 403)
        res_sub = self.client.post("/api/browser/submit", json={"url": "https://httpbin.org/post", "form_data": {"test": "val"}})
        self.assertEqual(res_sub.status_code, 403)

        # Document export endpoint
        res_exp = self.client.post("/api/documents/export", json={"format": "md"})
        self.assertEqual(res_exp.status_code, 200)
        self.assertTrue(res_exp.json().get("success"))


if __name__ == "__main__":
    unittest.main()
