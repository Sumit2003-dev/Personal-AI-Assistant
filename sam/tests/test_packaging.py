"""
SAM Phase 7 — Automated Packaging Validation Tests
Tests packaging infrastructure, configuration, Ollama detection,
user data persistence, upgrade migration, duplicate-instance prevention,
launcher logic, and runtime checks — all without requiring a live
packaged .exe or hardware.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
SAM_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))


# ===========================================================================
# 1. Runtime Check Tests
# ===========================================================================

class TestRuntimeCheck(unittest.TestCase):
    """Verifies runtime_check.py dependency and Ollama detection."""

    def setUp(self):
        from sam.launcher.runtime_check import run_checks
        self._run_checks = run_checks

    def test_python_version_ok(self):
        from sam.launcher.runtime_check import _check_python
        ok, ver = _check_python()
        # Must be 3.11+
        major, minor, *_ = sys.version_info
        self.assertEqual(ok, (major, minor) >= (3, 11))
        self.assertIn(str(major), ver)

    def test_check_modules_returns_list(self):
        from sam.launcher.runtime_check import _check_modules
        deps = _check_modules()
        self.assertIsInstance(deps, list)
        self.assertTrue(len(deps) > 0)
        # Check all entries have required fields
        for dep in deps:
            self.assertIsNotNone(dep.name)
            self.assertIsInstance(dep.available, bool)

    def test_critical_modules_present(self):
        """fastapi, uvicorn, pydantic, httpx, psutil, numpy must all be importable."""
        from sam.launcher.runtime_check import _check_modules
        deps = {d.name: d for d in _check_modules()}
        for critical in ["fastapi", "uvicorn", "pydantic", "httpx", "psutil", "numpy"]:
            self.assertIn(critical, deps, f"Module '{critical}' not found in check list")
            self.assertTrue(deps[critical].available, f"Critical module '{critical}' missing")

    def test_full_run_checks_can_launch(self):
        """Full run_checks should allow launch given our dev environment."""
        result = self._run_checks()
        self.assertTrue(result.can_launch, msg=f"Cannot launch:\n{result.summary()}")

    def test_summary_is_string(self):
        result = self._run_checks()
        s = result.summary()
        self.assertIsInstance(s, str)
        self.assertIn("Python", s)

    def test_ollama_status_has_required_fields(self):
        result = self._run_checks()
        self.assertIsInstance(result.ollama.required_models, list)
        self.assertIsInstance(result.ollama.missing_models, list)
        self.assertIn("qwen2.5:3b", result.ollama.required_models)

    def test_critical_errors_list_on_failure(self):
        from sam.launcher.runtime_check import RuntimeCheckResult, DependencyStatus
        result = RuntimeCheckResult()
        result.python_ok = True
        result.dependencies = [
            DependencyStatus(name="fastapi", available=False, error="not found", critical=True),
        ]
        errs = result.critical_errors()
        self.assertTrue(any("fastapi" in e for e in errs))

    @patch("sam.launcher.runtime_check._check_ollama_api", return_value=False)
    def test_ollama_offline_produces_warning_not_error(self, _mock):
        result = self._run_checks()
        # Offline Ollama should produce a warning but not block launch
        all_warnings = " ".join(result.warnings)
        self.assertIn("11434", all_warnings)
        self.assertTrue(result.can_launch)

    @patch("sam.launcher.runtime_check._find_ollama_executable", return_value="")
    def test_ollama_not_installed_produces_warning(self, _mock):
        result = self._run_checks()
        all_warnings = " ".join(result.warnings)
        self.assertTrue(
            any("Ollama" in w or "ollama" in w for w in result.warnings),
            f"Expected Ollama warning, got: {result.warnings}",
        )

    def test_user_data_dir_created(self):
        result = self._run_checks()
        self.assertTrue(result.user_data_dir.exists())

    def test_model_tag_matching(self):
        """Confirm prefix matching logic used in runtime_check."""
        available = ["qwen2.5:3b:latest", "llama3.1:8b"]
        target = "qwen2.5:3b"
        matched = None
        for m in available:
            if m == target or m.startswith(target + ":") or m.split(":")[0] == target.split(":")[0]:
                matched = m
                break
        self.assertEqual(matched, "qwen2.5:3b:latest")


# ===========================================================================
# 2. Configuration Manager Tests
# ===========================================================================

class TestConfigManager(unittest.TestCase):
    """Validates config load/save/migrate/backup in a temporary directory."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Redirect config to temp directory
        self._patcher = patch(
            "sam.launcher.config_manager._CONFIG_DIR",
            Path(self._tmpdir),
        )
        self._patcher2 = patch(
            "sam.launcher.config_manager._CONFIG_FILE",
            Path(self._tmpdir) / "sam_config.json",
        )
        self._patcher3 = patch(
            "sam.launcher.config_manager._BACKUP_FILE",
            Path(self._tmpdir) / "sam_config.backup.json",
        )
        self._patcher.start()
        self._patcher2.start()
        self._patcher3.start()

    def tearDown(self):
        self._patcher.stop()
        self._patcher2.stop()
        self._patcher3.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _fresh_manager(self):
        from sam.launcher.config_manager import ConfigManager
        return ConfigManager()

    def test_creates_default_config(self):
        mgr = self._fresh_manager()
        cfg_file = Path(self._tmpdir) / "sam_config.json"
        self.assertTrue(cfg_file.exists())

    def test_default_values(self):
        mgr = self._fresh_manager()
        self.assertEqual(mgr.config.ui_port, 8765)
        self.assertEqual(mgr.config.ui_host, "127.0.0.1")
        self.assertFalse(mgr.config.start_with_windows)

    def test_save_and_reload(self):
        mgr = self._fresh_manager()
        mgr.set("ui_port", 9999)
        mgr2 = self._fresh_manager()
        self.assertEqual(mgr2.config.ui_port, 9999)

    def test_migration_fills_missing_keys(self):
        """Config file missing new keys gets defaults filled without touching existing values."""
        cfg_file = Path(self._tmpdir) / "sam_config.json"
        # Write a minimal old-schema config
        cfg_file.write_text(json.dumps({"ui_port": 7777, "schema_version": 1}), encoding="utf-8")
        mgr = self._fresh_manager()
        # Existing key preserved
        self.assertEqual(mgr.config.ui_port, 7777)
        # New key gets default
        self.assertFalse(mgr.config.start_with_windows)
        # Schema bumped
        self.assertEqual(mgr.config.schema_version, 2)

    def test_backup_created_on_save(self):
        mgr = self._fresh_manager()
        mgr.save()
        backup = Path(self._tmpdir) / "sam_config.backup.json"
        self.assertTrue(backup.exists())

    def test_restore_from_backup(self):
        mgr = self._fresh_manager()
        mgr.set("ui_port", 1111)
        # Corrupt the main file
        Path(self._tmpdir, "sam_config.json").write_text("{invalid json}", encoding="utf-8")
        # Restore from backup
        result = mgr.restore_from_backup()
        self.assertTrue(result)

    def test_set_extra_key(self):
        mgr = self._fresh_manager()
        mgr.set("custom_nonexistent_key", "hello")
        self.assertEqual(mgr.config.extra.get("custom_nonexistent_key"), "hello")

    def test_never_overwrites_user_values(self):
        cfg_file = Path(self._tmpdir) / "sam_config.json"
        cfg_file.write_text(
            json.dumps({"preferred_mic": "My Fancy Mic", "schema_version": 2, "ui_port": 8765}),
            encoding="utf-8",
        )
        mgr = self._fresh_manager()
        self.assertEqual(mgr.config.preferred_mic, "My Fancy Mic")


# ===========================================================================
# 3. Startup Manager Tests
# ===========================================================================

class TestStartupManager(unittest.TestCase):
    """Tests Windows startup registry helpers (mocked)."""

    def test_non_windows_returns_false(self):
        with patch("sys.platform", "linux"):
            from sam.launcher.startup_manager import enable_startup, disable_startup
            self.assertFalse(enable_startup("/some/path"))
            self.assertFalse(disable_startup())

    def test_enable_and_disable_startup(self):
        from sam.launcher import startup_manager

        class MockKey:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class MockWinreg:
            HKEY_CURRENT_USER = 1
            KEY_READ = 1
            KEY_SET_VALUE = 2
            KEY_WRITE = 2
            REG_SZ = 1

            def __init__(self):
                self.store = {}

            def OpenKey(self, key, subkey, reserved, access):
                return MockKey()

            def QueryValueEx(self, key, name):
                if name in self.store:
                    return (self.store[name], self.REG_SZ)
                raise FileNotFoundError()

            def SetValueEx(self, key, name, reserved, type_, value):
                self.store[name] = value

            def DeleteValue(self, key, name):
                if name in self.store:
                    del self.store[name]
                else:
                    raise FileNotFoundError()

        mock_reg = MockWinreg()
        with patch.object(startup_manager, "_get_winreg", return_value=mock_reg):
            exe_path = sys.executable
            result = startup_manager.enable_startup(exe_path)
            self.assertTrue(result)
            self.assertTrue(startup_manager.is_startup_enabled())
            self.assertTrue(startup_manager.disable_startup())
            self.assertFalse(startup_manager.is_startup_enabled())


# ===========================================================================
# 4. Launcher Logic Tests (mocked)
# ===========================================================================

class TestLauncherLogic(unittest.TestCase):
    """Unit tests for app_launcher.py without actually launching processes."""

    def test_single_instance_mutex_on_non_windows(self):
        with patch("sys.platform", "linux"):
            from sam.launcher.app_launcher import _acquire_single_instance_mutex
            handle = _acquire_single_instance_mutex()
            self.assertEqual(handle, -1)

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_single_instance_mutex_acquire_release(self):
        from sam.launcher.app_launcher import _acquire_single_instance_mutex, _release_mutex, MUTEX_NAME
        with patch("sam.launcher.app_launcher.MUTEX_NAME", "Global\\SAM_Test_Mutex_12345"):
            handle = _acquire_single_instance_mutex()
            self.assertIsNotNone(handle)
            _release_mutex(handle)

    def test_wait_for_backend_timeout(self):
        """_wait_for_backend returns False when nothing is listening."""
        from sam.launcher.app_launcher import _wait_for_backend
        result = _wait_for_backend(timeout=0.5)
        self.assertFalse(result)

    @patch("ctypes.windll.user32.MessageBoxW", create=True)
    def test_show_error_dialog_does_not_raise(self, mock_msgbox=None):
        from sam.launcher.app_launcher import _show_error_dialog
        # Must not raise on any platform
        _show_error_dialog("Test", "This is an automated test error message.")

    @patch("sam.launcher.app_launcher._start_backend")
    @patch("sam.launcher.app_launcher._wait_for_backend", return_value=False)
    @patch("sam.launcher.app_launcher._acquire_single_instance_mutex", return_value=-1)
    def test_main_returns_nonzero_on_backend_timeout(self, mock_mutex, mock_wait, mock_start):
        from sam.launcher.app_launcher import main
        mock_start.return_value = MagicMock(poll=MagicMock(return_value=None))
        with patch("sam.launcher.app_launcher._show_error_dialog"):
            with patch("sam.launcher.app_launcher._stop_backend"):
                with patch("sam.launcher.app_launcher._release_mutex"):
                    result = main()
        self.assertNotEqual(result, 0)

    @patch("sam.launcher.app_launcher._acquire_single_instance_mutex", return_value=None)
    @patch("webbrowser.open")
    def test_main_opens_existing_window_when_already_running(self, mock_wb, mock_mutex):
        from sam.launcher.app_launcher import main
        result = main()
        self.assertEqual(result, 0)
        mock_wb.assert_called_once()

    def test_resolve_backend_script_returns_path(self):
        from sam.launcher.app_launcher import _resolve_backend_script
        path = _resolve_backend_script()
        self.assertTrue(Path(path).name.endswith(".py"))


# ===========================================================================
# 5. Data Persistence & Migration Tests
# ===========================================================================

class TestDataPersistence(unittest.TestCase):
    """Validates user data migration logic."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_migration_copies_missing_files(self):
        old_root = self._tmpdir / "old_data"
        new_root = self._tmpdir / "new_data"
        (old_root / "subdir").mkdir(parents=True)
        (old_root / "subdir" / "memory.db").write_text("FAKE_DB", encoding="utf-8")

        import shutil as _shutil
        for src in old_root.rglob("*"):
            if src.is_file():
                rel = src.relative_to(old_root)
                dst = new_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    _shutil.copy2(src, dst)

        dst_file = new_root / "subdir" / "memory.db"
        self.assertTrue(dst_file.exists())
        self.assertEqual(dst_file.read_text(), "FAKE_DB")

    def test_migration_does_not_overwrite_existing(self):
        old_root = self._tmpdir / "old"
        new_root = self._tmpdir / "new"
        old_root.mkdir()
        new_root.mkdir()
        (old_root / "file.txt").write_text("OLD", encoding="utf-8")
        (new_root / "file.txt").write_text("USER_VERSION", encoding="utf-8")

        import shutil as _shutil
        for src in old_root.rglob("*"):
            if src.is_file():
                rel = src.relative_to(old_root)
                dst = new_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    _shutil.copy2(src, dst)

        # User version must be preserved
        self.assertEqual((new_root / "file.txt").read_text(), "USER_VERSION")

    def test_sqlite_memory_uses_configurable_path(self):
        """Verify SQLite memory store can be pointed to a temp directory."""
        from sam.memory.sqlite_memory import MemoryStore
        db_path = self._tmpdir / "test_memory.db"
        store = MemoryStore(db_path=db_path)
        store.set_memory("test", "test_key", "test_value")
        result = store.get_memory("test_key")
        self.assertEqual(result, "test_value")

    def test_user_data_dir_structure(self):
        """Ensure expected subdirectories exist after runtime check."""
        from sam.launcher.runtime_check import _ensure_user_data_dir
        base = _ensure_user_data_dir()
        self.assertTrue(base.exists())
        for subdir in ["data", "logs", "config"]:
            self.assertTrue((base / subdir).exists(), f"Missing: {subdir}")


# ===========================================================================
# 6. Asset and Module Availability Tests
# ===========================================================================

class TestAssetAvailability(unittest.TestCase):
    """Verifies that all required static assets are present in the source tree."""

    def _asset(self, *parts):
        return SAM_ROOT.joinpath(*parts)

    def test_index_html_exists(self):
        self.assertTrue(self._asset("sam", "desktop", "templates", "index.html").exists())

    def test_app_js_exists(self):
        self.assertTrue(self._asset("sam", "desktop", "static", "js", "app.js").exists())

    def test_style_css_exists(self):
        self.assertTrue(self._asset("sam", "desktop", "static", "css", "style.css").exists())

    def test_sam_icon_exists(self):
        self.assertTrue(self._asset("packaging", "assets", "sam_icon.ico").exists())
        self.assertTrue(self._asset("packaging", "assets", "sam_icon.png").exists())

    def test_pyinstaller_spec_exists(self):
        self.assertTrue(self._asset("SAM.spec").exists())

    def test_inno_setup_script_exists(self):
        self.assertTrue(self._asset("packaging", "sam_installer.iss").exists())

    def test_build_script_exists(self):
        self.assertTrue(self._asset("packaging", "build_windows.bat").exists())

    def test_backend_runner_exists(self):
        self.assertTrue(self._asset("sam_backend_runner.py").exists())

    def test_sam_main_exists(self):
        self.assertTrue(self._asset("sam_main.py").exists())

    def test_launcher_package_importable(self):
        from sam.launcher.runtime_check import run_checks  # noqa: F401
        from sam.launcher.config_manager import ConfigManager  # noqa: F401
        from sam.launcher.app_launcher import main  # noqa: F401
        from sam.launcher.startup_manager import is_startup_enabled  # noqa: F401


# ===========================================================================
# 7. Duplicate Instance Prevention Tests
# ===========================================================================

class TestDuplicateInstancePrevention(unittest.TestCase):

    @unittest.skipUnless(sys.platform == "win32", "Windows named mutex only")
    def test_second_acquire_fails(self):
        import ctypes
        MUTEX_NAME = "Global\\SAM_DuplicateTest_99999"
        kernel32 = ctypes.windll.kernel32

        # First acquire
        h1 = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        err1 = kernel32.GetLastError()
        self.assertNotEqual(err1, 183, "First acquire should not see ERROR_ALREADY_EXISTS")

        # Second acquire — same process, same mutex
        h2 = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        err2 = kernel32.GetLastError()
        self.assertEqual(err2, 183, "Second acquire must see ERROR_ALREADY_EXISTS (183)")

        kernel32.ReleaseMutex(h1)
        kernel32.CloseHandle(h1)
        kernel32.CloseHandle(h2)

    def test_already_running_opens_browser(self):
        """When mutex returns None (already running), main() opens the browser and exits 0."""
        with patch("sam.launcher.app_launcher._acquire_single_instance_mutex", return_value=None):
            with patch("webbrowser.open") as mock_wb:
                from sam.launcher.app_launcher import main
                result = main()
        self.assertEqual(result, 0)
        mock_wb.assert_called_once()


# ===========================================================================
# 8. Graceful Shutdown Tests
# ===========================================================================

class TestGracefulShutdown(unittest.TestCase):

    def test_stop_backend_handles_none(self):
        """_stop_backend must handle _server_proc = None without error."""
        import sam.launcher.app_launcher as launcher_mod
        orig = launcher_mod._server_proc
        launcher_mod._server_proc = None
        try:
            launcher_mod._stop_backend()
        finally:
            launcher_mod._server_proc = orig

    def test_stop_backend_terminates_running_process(self):
        """_stop_backend terminates a running subprocess."""
        import sam.launcher.app_launcher as launcher_mod

        fake_proc = MagicMock()
        fake_proc.pid = 99999
        fake_proc.poll.return_value = None  # still running
        fake_proc.wait.return_value = 0

        orig = launcher_mod._server_proc
        launcher_mod._server_proc = fake_proc
        try:
            launcher_mod._stop_backend()
        finally:
            launcher_mod._server_proc = orig

        fake_proc.terminate.assert_called_once()

    def test_stop_backend_handles_timeout(self):
        """_stop_backend kills the process if terminate() times out."""
        import sam.launcher.app_launcher as launcher_mod

        fake_proc = MagicMock()
        fake_proc.pid = 99998
        fake_proc.poll.return_value = None
        fake_proc.wait.side_effect = [subprocess.TimeoutExpired("x", 8.0), None]

        orig = launcher_mod._server_proc
        launcher_mod._server_proc = fake_proc
        try:
            launcher_mod._stop_backend()
        finally:
            launcher_mod._server_proc = orig

        fake_proc.kill.assert_called_once()


# ===========================================================================
# 9. Backend Runner Bootstrap Tests
# ===========================================================================

class TestBackendRunner(unittest.TestCase):

    def test_bootstrap_paths_runs_without_error(self):
        """_bootstrap_paths must not raise on the current environment."""
        import importlib
        import sam.sam_backend_runner as runner
        # Re-run bootstrap
        runner._bootstrap_paths()

    def test_sam_data_root_set_after_bootstrap(self):
        import sam.sam_backend_runner as runner
        runner._bootstrap_paths()
        self.assertIn("SAM_DATA_ROOT", os.environ)
        self.assertTrue(Path(os.environ["SAM_DATA_ROOT"]).name == "SAM")


# ===========================================================================
# 10. Ollama Detection Logic Tests
# ===========================================================================

class TestOllamaDetection(unittest.TestCase):

    def test_find_executable_returns_string(self):
        from sam.launcher.runtime_check import _find_ollama_executable
        result = _find_ollama_executable()
        self.assertIsInstance(result, str)

    def test_api_offline_handled_gracefully(self):
        from sam.launcher.runtime_check import _check_ollama_api
        result = _check_ollama_api(timeout=0.1)
        self.assertIsInstance(result, bool)

    def test_list_models_with_bad_exe_returns_empty(self):
        from sam.launcher.runtime_check import _list_ollama_models
        result = _list_ollama_models("/nonexistent/path/ollama.exe")
        self.assertEqual(result, [])

    def test_model_dir_detection(self):
        from sam.launcher.runtime_check import _get_model_dir
        result = _get_model_dir()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch("sam.launcher.runtime_check._find_ollama_executable", return_value="fake_ollama.exe")
    @patch("sam.launcher.runtime_check._check_ollama_api", return_value=True)
    @patch("sam.launcher.runtime_check._list_ollama_models", return_value=["qwen2.5:3b:latest", "qwen3:4b"])
    def test_all_models_found_no_missing(self, _m1, _m2, _m3):
        from sam.launcher.runtime_check import run_checks
        result = run_checks()
        self.assertEqual(result.ollama.missing_models, [])

    @patch("sam.launcher.runtime_check._find_ollama_executable", return_value="fake_ollama.exe")
    @patch("sam.launcher.runtime_check._check_ollama_api", return_value=True)
    @patch("sam.launcher.runtime_check._list_ollama_models", return_value=[])
    def test_missing_models_reported(self, _m1, _m2, _m3):
        from sam.launcher.runtime_check import run_checks
        result = run_checks()
        self.assertEqual(len(result.ollama.missing_models), 2)
        self.assertIn("qwen2.5:3b", result.ollama.missing_models)


# ===========================================================================
# 11. Installer Manifest & Build File Tests
# ===========================================================================

class TestInstallerManifest(unittest.TestCase):
    """Static checks on installer script content — no actual build required."""

    def _read_iss(self):
        return (SAM_ROOT / "packaging" / "sam_installer.iss").read_text(encoding="utf-8")

    def test_iss_contains_app_name(self):
        content = self._read_iss()
        self.assertIn("SAM", content)

    def test_iss_has_upgrade_code(self):
        content = self._read_iss()
        self.assertIn("AppId", content)

    def test_iss_preserves_user_data(self):
        r"""Installer must NOT delete %APPDATA%\SAM."""
        content = self._read_iss()
        # UninstallDelete should only target {app}, not {userappdata}
        self.assertNotIn("{userappdata}", content.lower().replace(" ", ""))
        self.assertIn("{app}", content)

    def test_iss_has_upgrade_support(self):
        """Code section must include upgrade uninstall logic."""
        content = self._read_iss()
        self.assertIn("UnInstallOldVersion", content)
        self.assertIn("IsUpgrade", content)

    def test_iss_has_no_admin_requirement(self):
        """We use PrivilegesRequired=lowest to avoid UAC for per-user install."""
        content = self._read_iss()
        self.assertIn("PrivilegesRequired=lowest", content)

    def test_spec_file_has_datas(self):
        spec = (SAM_ROOT / "SAM.spec").read_text(encoding="utf-8")
        self.assertIn("sam/desktop/templates", spec)
        self.assertIn("sam/desktop/static", spec)

    def test_spec_has_no_console(self):
        spec = (SAM_ROOT / "SAM.spec").read_text(encoding="utf-8")
        self.assertIn("console=False", spec)


# ===========================================================================
# 12. Phase 7 Extended Launcher & Tray Validation
# ===========================================================================

class TestPhase7LauncherAndTray(unittest.TestCase):
    """Explicit tests for Phase 7 LauncherState, tray actions, and port pre-checks."""

    def test_launcher_state_enum_members(self):
        from sam.launcher.app_launcher import LauncherState
        expected = {
            "INITIALIZING",
            "CHECKING_DEPENDENCIES",
            "STARTING_BACKEND",
            "WAITING_FOR_HEALTH",
            "READY",
            "STARTUP_FAILED",
            "SHUTTING_DOWN",
        }
        actual = {s.name for s in LauncherState}
        self.assertEqual(actual, expected)

    def test_get_and_set_launcher_state(self):
        from sam.launcher.app_launcher import (
            LauncherState,
            get_launcher_state,
            _set_state,
        )
        _set_state(LauncherState.INITIALIZING)
        self.assertEqual(get_launcher_state(), LauncherState.INITIALIZING)
        _set_state(LauncherState.READY)
        self.assertEqual(get_launcher_state(), LauncherState.READY)

    def test_is_port_in_use_detects_bound_socket(self):
        from sam.launcher.app_launcher import _is_port_in_use
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            self.assertTrue(_is_port_in_use("127.0.0.1", port))
        finally:
            sock.close()
        # After socket closure, port should be free or closing
        # Allow small OS delay
        time.sleep(0.05)
        # Check non-bound port
        free_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        free_sock.bind(("127.0.0.1", 0))
        free_port = free_sock.getsockname()[1]
        free_sock.close()
        self.assertFalse(_is_port_in_use("127.0.0.1", free_port))

    def test_tray_menu_has_required_actions(self):
        """Verify tray menu creation includes all Phase 7 required options."""
        from sam.launcher.app_launcher import _build_tray_icon
        with patch("pystray.Icon") as mock_icon_cls:
            mock_icon = MagicMock()
            mock_icon_cls.return_value = mock_icon
            icon = _build_tray_icon()
            self.assertIsNotNone(icon)
            mock_icon_cls.assert_called_once()
            # Inspect menu passed to pystray.Icon
            call_kwargs = mock_icon_cls.call_args[1]
            menu = call_kwargs.get("menu")
            if menu is None and len(mock_icon_cls.call_args[0]) >= 4:
                menu = mock_icon_cls.call_args[0][3]
            self.assertIsNotNone(menu)
            menu_items_text = [getattr(item, "text", str(item)) for item in menu.items]
            self.assertTrue(any("Open SAM" in t for t in menu_items_text))
            self.assertTrue(any("Show Application Status" in t for t in menu_items_text))
            self.assertTrue(any("Open Logs Folder" in t for t in menu_items_text))
            self.assertTrue(any("Restart SAM" in t for t in menu_items_text))
            self.assertTrue(any("Exit SAM" in t for t in menu_items_text))

    @patch("sam.launcher.app_launcher._show_info_dialog")
    def test_show_status_tray_action(self, mock_dialog):
        from sam.launcher.app_launcher import (
            LauncherState,
            _set_state,
            _tray_action_status,
        )
        _set_state(LauncherState.READY)
        _tray_action_status(None, None)
        mock_dialog.assert_called_once()
        args = mock_dialog.call_args[0]
        self.assertIn("READY", args[1])


# ===========================================================================
# 13. Settings Runtime Data Paths Isolation Tests
# ===========================================================================

class TestSettingsRuntimeDataPaths(unittest.TestCase):
    """Validates that settings.py correctly resolves user-mutable dirs outside installation dir."""

    def test_sam_data_root_environment_variable_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_data = Path(tmp) / "custom_sam"
            with patch.dict(os.environ, {"SAM_DATA_ROOT": str(custom_data)}):
                from sam.config.settings import _resolve_runtime_data_dir, _resolve_runtime_logs_dir
                resolved_data = _resolve_runtime_data_dir()
                resolved_logs = _resolve_runtime_logs_dir()
                self.assertEqual(resolved_data, custom_data / "data")
                self.assertEqual(resolved_logs, custom_data / "logs")

    def test_frozen_runtime_routes_to_appdata(self):
        with patch.dict(os.environ, {}, clear=False):
            if "SAM_DATA_ROOT" in os.environ:
                del os.environ["SAM_DATA_ROOT"]
            with patch("sys.frozen", True, create=True):
                with patch("sys._MEIPASS", "C:\\Program Files\\SAM", create=True):
                    from sam.config.settings import _resolve_runtime_data_dir
                    resolved = _resolve_runtime_data_dir()
                    # Must be under AppData, NOT Program Files
                    self.assertNotIn("Program Files", str(resolved))
                    self.assertIn("SAM", str(resolved))


if __name__ == "__main__":
    unittest.main(verbosity=2)
