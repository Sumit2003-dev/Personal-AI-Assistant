"""
SAM - Core Agent Data Models & State Contracts
Defines Task, Step, ToolCall, Observation, VerificationResult, and RiskLevel.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import time
import uuid


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class Observation:
    timestamp: float = field(default_factory=time.time)
    window_title: str = ""
    active_process: str = ""
    screenshot_path: Optional[str] = None
    ui_elements: list[dict[str, Any]] = field(default_factory=list)
    visual_hash: Optional[str] = None
    text_content: Optional[str] = None
    system_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCall:
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    executed_at: Optional[float] = None
    success: bool = False
    output: Any = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk_level"] = self.risk_level.value
        return data


@dataclass
class VerificationResult:
    verified: bool = False
    criteria: str = ""
    details: str = ""
    checked_at: float = field(default_factory=time.time)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskStep:
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_index: int = 0
    title: str = ""
    description: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    status: StepStatus = StepStatus.PENDING
    observation_before: Optional[Observation] = None
    observation_after: Optional[Observation] = None
    verification_criteria: str = ""
    verification_result: Optional[VerificationResult] = None
    tool_call: Optional[ToolCall] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "title": self.title,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "observation_before": self.observation_before.to_dict() if self.observation_before else None,
            "observation_after": self.observation_after.to_dict() if self.observation_after else None,
            "verification_criteria": self.verification_criteria,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "tool_call": self.tool_call.to_dict() if self.tool_call else None,
            "error": self.error,
            "retries": self.retries,
            "max_retries": self.max_retries,
        }


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: f"task_{int(time.time())}_{str(uuid.uuid4())[:6]}")
    objective: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: TaskStatus = TaskStatus.PENDING
    steps: list[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    verification_result: Optional[VerificationResult] = None
    error_details: Optional[str] = None
    artifacts: list[str] = field(default_factory=list)
    requires_approval: bool = False
    pending_approval_step: Optional[TaskStep] = None
    context_data: dict[str, Any] = field(default_factory=dict)

    def current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def progress_percentage(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return round((completed / len(self.steps)) * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "current_step_index": self.current_step_index,
            "progress_percent": self.progress_percentage(),
            "steps": [s.to_dict() for s in self.steps],
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "error_details": self.error_details,
            "artifacts": self.artifacts,
            "requires_approval": self.requires_approval,
            "context_data": self.context_data,
        }

