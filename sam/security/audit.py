"""
SAM - Audit Logger
Maintains an append-only JSONL audit log of all computer actions, tool executions, and security decisions.
"""

from pathlib import Path
from typing import Any
import json
import time
from sam.config.settings import settings


class AuditLogger:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or settings.security.audit_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(
        self,
        event_type: str,
        action: str,
        risk_level: str,
        status: str,
        details: dict[str, Any] | None = None,
        task_id: str | None = None,
    ):
        record = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "event_type": event_type,
            "action": action,
            "risk_level": risk_level,
            "status": status,
            "task_id": task_id,
            "details": details or {},
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[AUDIT LOG ERROR] Failed to write audit entry: {e}")

    def read_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                parsed = [json.loads(line.strip()) for line in lines if line.strip()]
                return parsed[-limit:]
        except Exception as e:
            return [{"error": str(e)}]


audit_logger = AuditLogger()

