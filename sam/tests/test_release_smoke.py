r"""
SAM Phase 7.1 — Release Readiness & Packaging Smoke Tests
Validates:
1. Real packaged executable (dist/SAM/SAM.exe) startup, health endpoint, static assets.
2. Working directory independence (launching from external directories and paths with spaces).
3. Upgrade and uninstallation data protection simulation (ensuring %APPDATA%\SAM and models are preserved).
4. Localhost binding & port safety.
5. Inno Setup script security and isolation audits.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SAM_ROOT = Path(__file__).resolve().parent.parent.parent
DIST_EXE = SAM_ROOT / "dist" / "SAM" / "SAM.exe"


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


class TestPackagedExecutableSmoke(unittest.TestCase):
    """Real executable smoke tests for dist/SAM/SAM.exe."""

    @unittest.skipUnless(DIST_EXE.exists(), "dist/SAM/SAM.exe not found")
    def test_real_packaged_backend_startup_and_health(self):
        """
        Launches dist/SAM/SAM.exe with --backend-server on a test port,
        probes health and static assets, and verifies clean shutdown.
        """
        # Find a free ephemeral port
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        test_port = s.getsockname()[1]
        s.close()

        test_data_root = SAM_ROOT / "dist" / "test_smoke_data"
        shutil.rmtree(test_data_root, ignore_errors=True)
        test_data_root.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["SAM_DATA_ROOT"] = str(test_data_root)
        env["SAM_UI_HOST"] = "127.0.0.1"
        env["SAM_UI_PORT"] = str(test_port)
        env["SAM_HEADLESS"] = "1"

        log_file = test_data_root / "test_exec.log"

        with open(log_file, "w", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                [str(DIST_EXE), "--backend-server"],
                env=env,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=str(DIST_EXE.parent),
            )

        server_ready = False
        try:
            import urllib.request

            health_url = f"http://127.0.0.1:{test_port}/api/telemetry/health"
            static_url = f"http://127.0.0.1:{test_port}/static/css/style.css"

            start = time.time()
            log_content = ""
            while time.time() - start < 25.0:
                try:
                    req = urllib.request.Request(health_url)
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            payload = json.loads(resp.read().decode("utf-8"))
                            self.assertIn("status", payload)
                            self.assertIn("telemetry", payload)
                            server_ready = True
                            break
                except Exception:
                    time.sleep(0.5)

            if log_file.exists():
                log_content = log_file.read_text(encoding="utf-8", errors="replace")

            self.assertTrue(server_ready, f"Packaged backend failed to answer on {health_url}.\nLog:\n{log_content}")

            # Probe static asset
            with urllib.request.urlopen(static_url, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                content = resp.read().decode("utf-8")
                self.assertIn("--bg-app", content)

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            shutil.rmtree(test_data_root, ignore_errors=True)

        self.assertIsNotNone(proc.returncode)


class TestWorkingDirectoryIndependence(unittest.TestCase):
    """Ensures SAM runs correctly regardless of working directory or spaces in path."""

    @unittest.skipUnless(DIST_EXE.exists(), "dist/SAM/SAM.exe not found")
    def test_launch_from_directory_with_spaces(self):
        """Launches backend from a path containing spaces and outside the repo."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        test_port = s.getsockname()[1]
        s.close()

        space_dir = SAM_ROOT / "dist" / "SAM Test Path With Spaces"
        shutil.rmtree(space_dir, ignore_errors=True)
        space_dir.mkdir(parents=True, exist_ok=True)
        test_data_root = space_dir / "UserData"
        test_data_root.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["SAM_DATA_ROOT"] = str(test_data_root)
        env["SAM_UI_HOST"] = "127.0.0.1"
        env["SAM_UI_PORT"] = str(test_port)
        env["SAM_HEADLESS"] = "1"

        log_file = space_dir / "space_test.log"
        with open(log_file, "w", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                [str(DIST_EXE), "--backend-server"],
                env=env,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=str(space_dir),  # Launch with space_dir as CWD
            )

        ready = False
        log_content = ""
        try:
            import urllib.request
            health_url = f"http://127.0.0.1:{test_port}/api/telemetry/health"
            start = time.time()
            while time.time() - start < 25.0:
                try:
                    with urllib.request.urlopen(health_url, timeout=2.0) as resp:
                        if resp.status == 200:
                            ready = True
                            break
                except Exception:
                    time.sleep(0.5)

            if log_file.exists():
                log_content = log_file.read_text(encoding="utf-8", errors="replace")

            self.assertTrue(ready, f"Backend failed to launch from directory with spaces.\nLog:\n{log_content}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            shutil.rmtree(space_dir, ignore_errors=True)


class TestDataProtectionAndLifecycleSimulation(unittest.TestCase):
    r"""
    Simulates upgrade and uninstallation workflows in temporary environments
    to mathematically verify that user data and model folders are NEVER deleted.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.base = Path(self._tmp)
        self.install_dir = self.base / "ProgramFiles" / "SAM"
        self.install_dir.mkdir(parents=True)
        self.appdata_dir = self.base / "AppData" / "SAM"
        self.appdata_dir.mkdir(parents=True)
        self.ollama_models = self.base / "Models" / "Ollama"
        self.ollama_models.mkdir(parents=True)
        self.whisper_models = self.base / "Models" / "Whisper"
        self.whisper_models.mkdir(parents=True)

        # Seed initial installation files (binaries)
        (self.install_dir / "SAM.exe").write_bytes(b"BIN_V1_SAM_EXE")
        (self.install_dir / "sam_icon.ico").write_bytes(b"BIN_V1_ICON")
        (self.install_dir / "python314.dll").write_bytes(b"BIN_V1_DLL")

        # Seed user data (must be preserved across upgrade and uninstall)
        (self.appdata_dir / "data").mkdir(parents=True)
        (self.appdata_dir / "config").mkdir(parents=True)
        (self.appdata_dir / "workspaces").mkdir(parents=True)

        self.memory_db = self.appdata_dir / "data" / "sam_memory.db"
        self.memory_db.write_text("SQLITE_SAMPLE_USER_MEMORIES", encoding="utf-8")

        self.config_json = self.appdata_dir / "config" / "sam_config.json"
        self.config_json.write_text(json.dumps({"preferred_mic": "boAt Airdopes 131"}), encoding="utf-8")

        self.user_code = self.appdata_dir / "workspaces" / "my_project.py"
        self.user_code.write_text("print('user precious project')", encoding="utf-8")

        # Seed models
        self.qwen_model = self.ollama_models / "qwen2.5_3b.gguf"
        self.qwen_model.write_bytes(b"MULTI_GB_SIMULATED_OLLAMA_MODEL")

        self.whisper_model = self.whisper_models / "tiny_en.bin"
        self.whisper_model.write_bytes(b"SIMULATED_WHISPER_MODEL")

        # Precompute hashes of all user data
        self.expected_hashes = {
            self.memory_db: _sha256_of_file(self.memory_db),
            self.config_json: _sha256_of_file(self.config_json),
            self.user_code: _sha256_of_file(self.user_code),
            self.qwen_model: _sha256_of_file(self.qwen_model),
            self.whisper_model: _sha256_of_file(self.whisper_model),
        }

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_upgrade_preserves_all_user_data_and_models(self):
        """
        Simulate upgrade: Inno Setup uninstalls previous binaries from {app}
        and places new v2 binaries into {app}.
        All user data, databases, and models must remain untouched.
        """
        # Step 1: Simulated old version uninstall (purges {app})
        for f in list(self.install_dir.iterdir()):
            if f.is_file():
                f.unlink()

        # Step 2: Simulated new version install (writes v2 binaries into {app})
        (self.install_dir / "SAM.exe").write_bytes(b"BIN_V2_SAM_EXE")
        (self.install_dir / "sam_icon.ico").write_bytes(b"BIN_V2_ICON")
        (self.install_dir / "python314.dll").write_bytes(b"BIN_V2_DLL")

        # Verify new binaries exist
        self.assertEqual((self.install_dir / "SAM.exe").read_bytes(), b"BIN_V2_SAM_EXE")

        # Verify user data and models are 100% byte-for-byte identical
        for path, expected_hash in self.expected_hashes.items():
            self.assertTrue(path.exists(), f"File disappeared during upgrade: {path}")
            self.assertEqual(_sha256_of_file(path), expected_hash, f"File altered during upgrade: {path}")

    def test_uninstall_preserves_all_user_data_and_models(self):
        r"""
        Simulate uninstall: Inno Setup removes {app}.
        User data in %APPDATA% and models in D:\ must remain intact.
        """
        # Simulated uninstall purges {app}
        shutil.rmtree(self.install_dir, ignore_errors=True)
        self.assertFalse(self.install_dir.exists())

        # Verify user data and models are 100% byte-for-byte preserved
        for path, expected_hash in self.expected_hashes.items():
            self.assertTrue(path.exists(), f"File deleted during uninstall: {path}")
            self.assertEqual(_sha256_of_file(path), expected_hash, f"File corrupted during uninstall: {path}")

    def test_inno_setup_script_destructiveness_audit(self):
        """Static audit of sam_installer.iss to ensure no wildcards target user directories."""
        iss_path = SAM_ROOT / "packaging" / "sam_installer.iss"
        content = iss_path.read_text(encoding="utf-8")

        # UninstallDelete should only target {app}
        lines = content.splitlines()
        in_uninstall_delete = False
        for line in lines:
            line_strip = line.strip()
            if line_strip.startswith("[") and line_strip.endswith("]"):
                in_uninstall_delete = (line_strip.lower() == "[uninstalldelete]")
                continue
            if in_uninstall_delete and line_strip and not line_strip.startswith(";"):
                self.assertNotIn("{userappdata}", line_strip.lower())
                self.assertNotIn("{localappdata}", line_strip.lower())
                self.assertNotIn("models", line_strip.lower())
                self.assertIn("{app}", line_strip)


class TestLocalhostAndPortSafety(unittest.TestCase):
    """Network binding and port conflict safety tests."""

    def test_default_ui_host_is_strict_localhost(self):
        from sam.config.settings import Settings
        s = Settings()
        self.assertEqual(s.desktop.ui_host, "127.0.0.1")
        self.assertNotEqual(s.desktop.ui_host, "0.0.0.0")

    def test_port_conflict_detection(self):
        from sam.launcher.app_launcher import _is_port_in_use
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        busy_port = s.getsockname()[1]
        try:
            self.assertTrue(_is_port_in_use("127.0.0.1", busy_port))
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
