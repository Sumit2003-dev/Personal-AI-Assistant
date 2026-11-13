"""
SAM - Security & Permissions Engine
Enforces multi-tier risk boundaries, allowlisted workspace rules, command sanitization, and Global Emergency Stop.
"""

from pathlib import Path
from typing import Any
import re
from sam.agent.models import RiskLevel
from sam.config.settings import settings
from sam.security.audit import audit_logger


class PermissionDeniedError(Exception):
    pass


class EmergencyStopActiveError(Exception):
    pass


class SecurityGatekeeper:
    def __init__(self):
        self._emergency_stop: bool = False
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    @property
    def is_emergency_stop_active(self) -> bool:
        return self._emergency_stop

    def trigger_emergency_stop(self, reason: str = "User initiated global emergency stop"):
        self._emergency_stop = True
        audit_logger.log_event(
            event_type="EMERGENCY_STOP",
            action="TRIGGER_STOP",
            risk_level="HIGH",
            status="TRIGGERED",
            details={"reason": reason}
        )
        print(f"[SECURITY] EMERGENCY STOP ACTIVATED: {reason}")

    def reset_emergency_stop(self):
        self._emergency_stop = False
        audit_logger.log_event(
            event_type="EMERGENCY_STOP",
            action="RESET_STOP",
            risk_level="HIGH",
            status="RESET",
            details={"message": "Emergency stop cleared"}
        )

    def validate_command(self, cmd: str) -> bool:
        """Sanitizes terminal commands against destructive patterns."""
        cmd_lower = cmd.lower().strip()
        dangerous_patterns = [
            r"format\s+[a-z]:",
            r"rmdir\s+/[sS]\s+/[qQ]\s+[cC]:",
            r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[cC]:\\windows",
            r"reg\s+delete\s+hklm",
            r"diskpart",
            r"bcdedit",
            r"vssadmin\s+delete\s+shadows",
            r":\(\)\{\s*:\|:&\s*\};:",  # Forkbomb
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd_lower):
                audit_logger.log_event(
                    event_type="COMMAND_BLOCKED",
                    action=cmd,
                    risk_level="HIGH",
                    status="REJECTED",
                    details={"pattern": pattern}
                )
                return False
        return True

    def validate_path_access(self, target_path: str | Path, write: bool = False) -> bool:
        """Checks if a path is inside allowed user directories or project folders."""
        try:
            resolved = Path(target_path).resolve()
        except Exception:
            return False

        # Block root system writes
        sys_paths = [
            Path("C:/Windows").resolve(),
            Path("C:/Program Files").resolve(),
            Path("C:/Program Files (x86)").resolve(),
        ]
        if write:
            for sys_p in sys_paths:
                if resolved == sys_p or sys_p in resolved.parents:
                    return False
        return True

    def evaluate_action(
        self,
        action_name: str,
        risk_level: RiskLevel,
        details: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluates whether an action can execute immediately or requires user approval.
        Returns (can_execute, reason).
        """
        if self._emergency_stop:
            audit_logger.log_event(
                event_type="ACTION_BLOCKED",
                action=action_name,
                risk_level=risk_level.value,
                status="BLOCKED_BY_EMERGENCY_STOP",
                details=details,
                task_id=task_id,
            )
            return False, "Emergency stop is active. All automated actions are halted."

        if risk_level == RiskLevel.LOW:
            audit_logger.log_event(
                event_type="ACTION_APPROVED_AUTO",
                action=action_name,
                risk_level=risk_level.value,
                status="EXECUTING",
                details=details,
                task_id=task_id,
            )
            return True, "Low risk action approved automatically."

        if risk_level == RiskLevel.MEDIUM:
            audit_logger.log_event(
                event_type="ACTION_MEDIUM_RISK",
                action=action_name,
                risk_level=risk_level.value,
                status="EXECUTING" if not settings.security.require_confirmation_medium_risk else "WAITING_APPROVAL",
                details=details,
                task_id=task_id,
            )
            if not settings.security.require_confirmation_medium_risk:
                return True, "Medium risk action approved under current policy."
            return False, "User confirmation required for medium-risk operation."

        if risk_level == RiskLevel.HIGH:
            audit_logger.log_event(
                event_type="ACTION_HIGH_RISK_GATED",
                action=action_name,
                risk_level=risk_level.value,
                status="WAITING_APPROVAL",
                details=details,
                task_id=task_id,
            )
            return False, "High-risk action requires explicit user approval."

        return False, "Unknown risk level."


security_gatekeeper = SecurityGatekeeper()

