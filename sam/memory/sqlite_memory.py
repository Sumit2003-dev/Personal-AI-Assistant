"""
SAM - Personal Memory & Retrieval System
SQLite-backed persistent storage for preferences, project context, workflows, and task history.
"""

from pathlib import Path
from typing import Any, List, Optional, Dict
import sqlite3
import json
import time
from sam.config.settings import settings

MEMORY_DB_PATH = settings.data_dir / "sam_memory.db"


class MemoryStore:
    """Manages long-term personal memory, workflows, and task histories."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or MEMORY_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # Personal Facts & Preferences
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personal_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            # Common Workflows
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    steps_json TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                )
            """)
            # Conversation History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            # Task History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    task_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_count INTEGER,
                    progress_percent REAL,
                    artifacts_json TEXT,
                    error_details TEXT,
                    created_at REAL NOT NULL,
                    completed_at REAL
                )
            """)
            conn.commit()

    def set_memory(self, category: str, key: str, value: Any) -> bool:
        """Saves or updates a memory item."""
        val_str = json.dumps(value) if not isinstance(value, str) else value
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO personal_memory (category, key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = excluded.updated_at
            """, (category, key, val_str, now, now))
            conn.commit()
        return True

    def get_memory(self, key: str) -> Optional[Any]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM personal_memory WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
        return None

    def search_memories(self, query: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            pattern = f"%{query}%"
            cur = conn.execute(
                "SELECT category, key, value, updated_at FROM personal_memory WHERE key LIKE ? OR value LIKE ?",
                (pattern, pattern)
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def delete_memory(self, key: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM personal_memory WHERE key = ?", (key,))
            conn.commit()
            return cur.rowcount > 0

    def list_all_memories(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT category, key, value, updated_at FROM personal_memory ORDER BY category, key")
            return [dict(r) for r in cur.fetchall()]

    def log_message(self, role: str, content: str, metadata: dict[str, Any] | None = None):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (role, content, metadata_json, timestamp) VALUES (?, ?, ?, ?)",
                (role, content, json.dumps(metadata or {}), time.time())
            )
            conn.commit()

    def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content, metadata_json, timestamp FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = [dict(r) for r in cur.fetchall()]
            rows.reverse()
            return rows

    def record_task(self, task_dict: dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO task_history (
                    task_id, objective, status, steps_count, progress_percent,
                    artifacts_json, error_details, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    progress_percent = excluded.progress_percent,
                    artifacts_json = excluded.artifacts_json,
                    error_details = excluded.error_details,
                    completed_at = excluded.completed_at
            """, (
                task_dict["task_id"],
                task_dict["objective"],
                task_dict["status"],
                len(task_dict.get("steps", [])),
                task_dict.get("progress_percent", 0.0),
                json.dumps(task_dict.get("artifacts", [])),
                task_dict.get("error_details"),
                task_dict.get("created_at", time.time()),
                task_dict.get("completed_at")
            ))
            conn.commit()

    def get_recent_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]


memory_store = MemoryStore()

