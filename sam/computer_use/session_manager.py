"""
SAM - Computer-Use Session Manager
Prevents concurrent or conflicting automations from manipulating inputs simultaneously.
"""

import threading
import time
from typing import Optional
import logging

logger = logging.getLogger("sam.computer_use.session")


class ComputerUseSessionConflictError(Exception):
    pass


class ComputerUseSessionManager:
    """Provides a thread-safe mutex and status tracking for computer-use operations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_session_id: Optional[str] = None
        self._acquired_at: Optional[float] = None
        self._is_paused: bool = False

    def acquire(self, session_id: str, timeout: float = 5.0) -> bool:
        start_t = time.time()
        while time.time() - start_t < timeout:
            if self._lock.acquire(blocking=False):
                self._active_session_id = session_id
                self._acquired_at = time.time()
                self._is_paused = False
                logger.info(f"Computer-use lock acquired by session: {session_id}")
                return True
            time.sleep(0.05)
        raise ComputerUseSessionConflictError(
            f"Failed to acquire computer-use lock. Active session: {self._active_session_id}"
        )

    def release(self, session_id: str) -> bool:
        if self._active_session_id == session_id:
            self._active_session_id = None
            self._acquired_at = None
            self._is_paused = False
            try:
                self._lock.release()
                logger.info(f"Computer-use lock released by session: {session_id}")
                return True
            except RuntimeError:
                return False
        return False

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    @property
    def is_locked(self) -> bool:
        return self._active_session_id is not None

    @property
    def active_session(self) -> Optional[str]:
        return self._active_session_id


session_manager = ComputerUseSessionManager()

