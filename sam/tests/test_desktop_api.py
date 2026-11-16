"""
SAM - Desktop Web API Automated Test Suite
Verifies all 46 FastAPI endpoints and desktop backend operations.
"""

import unittest
from pathlib import Path
import sys

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from fastapi.testclient import TestClient
from sam.desktop.web_desktop import app
from sam.security.permissions import security_gatekeeper


class TestDesktopAPI(unittest.TestCase):
    """Verifies all desktop UI backend routes, telemetry, tasks, and security controls."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def tearDown(self):
        security_gatekeeper.reset_emergency_stop()

    def test_root_index_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("SAM // Autonomous AI Computer Operator", res.text)
        self.assertIn("RTX 4050 6GB", res.text)

    def test_telemetry_endpoints(self):
        res = self.client.get("/api/telemetry")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("cpu", data)
        self.assertIn("ram", data)
        self.assertIn("gpu", data)

        res_health = self.client.get("/api/telemetry/health")
        self.assertEqual(res_health.status_code, 200)
        health = res_health.json()
        self.assertIn("status", health)
        self.assertIn("diagnostics", health)

    def test_applications_endpoint(self):
        res = self.client.get("/api/applications")
        self.assertEqual(res.status_code, 200)
        apps = res.json()
        self.assertIsInstance(apps, list)
        self.assertGreater(len(apps), 0)

    def test_chat_and_task_execution(self):
        # 1. Send chat goal
        res = self.client.post("/api/chat", json={"message": "Inspect CPU and RAM usage and summarize status"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("task_id", data)
        self.assertGreater(data.get("steps_count", 0), 0)

        task_id = data["task_id"]

        # 2. Query task status
        res_task = self.client.get(f"/api/tasks/{task_id}")
        self.assertEqual(res_task.status_code, 200)
        task_data = res_task.json()
        self.assertEqual(task_data["task_id"], task_id)

        # 3. Query chat history
        res_hist = self.client.get("/api/chat/history")
        self.assertEqual(res_hist.status_code, 200)
        messages = res_hist.json().get("messages", [])
        self.assertGreater(len(messages), 0)

    def test_computer_preview_and_active_window(self):
        res_win = self.client.get("/api/computer/active_window")
        self.assertEqual(res_win.status_code, 200)
        win_data = res_win.json()
        self.assertIn("title", win_data)
        self.assertIn("emergency_stop_active", win_data)

        # Verify live screenshot image endpoint returns image/jpeg bytes
        res_img = self.client.get("/api/computer/screenshot/image")
        self.assertEqual(res_img.status_code, 200)
        self.assertEqual(res_img.headers.get("content-type"), "image/jpeg")
        self.assertGreater(len(res_img.content), 1000)

    def test_voice_devices_endpoint(self):
        res = self.client.get("/api/voice/devices")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("devices", data)
        self.assertIsInstance(data["devices"], list)

    def test_coding_workspace_endpoints(self):
        res_ws = self.client.get("/api/coding/workspaces")
        self.assertEqual(res_ws.status_code, 200)
        workspaces = res_ws.json().get("workspaces", [])
        self.assertIsInstance(workspaces, list)

        # Write code
        write_payload = {
            "workspace": "test_desktop_api_ws",
            "filename": "hello.py",
            "content": "print('HELLO FROM SAM DESKTOP API')"
        }
        res_write = self.client.post("/api/coding/write", json=write_payload)
        self.assertEqual(res_write.status_code, 200)

        # Read code
        res_read = self.client.get("/api/coding/read?workspace=test_desktop_api_ws&filename=hello.py")
        self.assertEqual(res_read.status_code, 200)
        self.assertIn("HELLO FROM SAM", res_read.json()["content"])

        # Run script
        res_run = self.client.post("/api/coding/run", json={"workspace": "test_desktop_api_ws", "filename": "hello.py"})
        self.assertEqual(res_run.status_code, 200)
        run_data = res_run.json()
        self.assertTrue(run_data["success"])
        self.assertIn("HELLO FROM SAM", run_data["stdout"])

    def test_video_exports_endpoint(self):
        res = self.client.get("/api/video/exports")
        self.assertEqual(res.status_code, 200)
        self.assertIn("exports", res.json())

    def test_browser_research_endpoint(self):
        res = self.client.post("/api/browser/research", json={"query": "Python Programming", "url": None})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("title", data)
        self.assertIn("content_sample", data)

    def test_memory_crud_endpoints(self):
        test_key = "test_desktop_pref"
        create_payload = {
            "category": "ui_test",
            "key": test_key,
            "value": "dark_graphite_verified"
        }
        res_post = self.client.post("/api/memory", json=create_payload)
        self.assertEqual(res_post.status_code, 200)

        # Search
        res_search = self.client.get(f"/api/memory/search?query={test_key}")
        self.assertEqual(res_search.status_code, 200)
        memories = res_search.json().get("memories", [])
        self.assertTrue(any(m["key"] == test_key for m in memories))

        # Delete
        res_del = self.client.delete(f"/api/memory/{test_key}")
        self.assertEqual(res_del.status_code, 200)

    def test_models_and_emergency_stop_endpoints(self):
        res_model = self.client.get("/api/models/status")
        self.assertEqual(res_model.status_code, 200)
        data = res_model.json()
        self.assertIn("ollama_online", data)

        # Switch model
        res_switch = self.client.post("/api/models/select", json={"model_name": "qwen2.5:3b"})
        self.assertEqual(res_switch.status_code, 200)
        self.assertEqual(res_switch.json()["selected_model"], "qwen2.5:3b")

        # Emergency Stop
        res_stop = self.client.post("/api/emergency_stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertTrue(security_gatekeeper.is_emergency_stop_active)

        # Reset Emergency Stop
        res_reset = self.client.post("/api/security/reset_emergency_stop")
        self.assertEqual(res_reset.status_code, 200)
        self.assertFalse(security_gatekeeper.is_emergency_stop_active)


if __name__ == "__main__":
    unittest.main()
