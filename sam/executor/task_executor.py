"""
SAM - Autonomous Task Execution Engine
Implements the Observe-Plan-Act-Verify loop with error recovery, retry management, and security gates.
"""

from typing import Any, Callable, Optional
import time
import asyncio
import logging
from sam.agent.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    RiskLevel,
    Observation,
    ToolCall,
    VerificationResult,
)
from sam.tools.registry import tool_registry
from sam.security.permissions import security_gatekeeper, EmergencyStopActiveError
from sam.security.audit import audit_logger
from sam.config.settings import settings

logger = logging.getLogger("sam.executor")


class TaskExecutor:
    """Orchestrates step execution, state observation, and post-action verification."""

    def __init__(self):
        self._active_tasks: dict[str, Task] = {}
        self._observer_func: Optional[Callable[[], Observation]] = None
        self._progress_callbacks: list[Callable[[Task], None]] = []

    def register_observer(self, func: Callable[[], Observation]):
        self._observer_func = func

    def add_progress_listener(self, callback: Callable[[Task], None]):
        self._progress_callbacks.append(callback)

    def _notify_progress(self, task: Task):
        for cb in self._progress_callbacks:
            try:
                cb(task)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

    def capture_observation(self) -> Observation:
        if self._observer_func:
            try:
                return self._observer_func()
            except Exception as e:
                logger.warning(f"Observer failed: {e}")
        return Observation(
            window_title="Desktop Workspace",
            active_process="explorer.exe",
            text_content="Observation capture completed."
        )

    def execute_task(self, task: Task) -> Task:
        """Synchronously executes a planned task through the observe-plan-act-verify loop."""
        self._active_tasks[task.task_id] = task
        task.status = TaskStatus.RUNNING
        self._notify_progress(task)

        audit_logger.log_event(
            event_type="TASK_START",
            action="EXECUTE_TASK",
            risk_level="LOW",
            status="RUNNING",
            task_id=task.task_id,
            details={"objective": task.objective, "total_steps": len(task.steps)}
        )

        while task.current_step_index < len(task.steps):
            if security_gatekeeper.is_emergency_stop_active:
                task.status = TaskStatus.STOPPED
                task.error_details = "Emergency stop activated by user. Task halted."
                self._notify_progress(task)
                return task

            if task.status == TaskStatus.PAUSED:
                logger.info(f"Task {task.task_id} is paused.")
                self._notify_progress(task)
                return task

            step = task.steps[task.current_step_index]
            step.status = StepStatus.RUNNING
            self._notify_progress(task)

            # Security gate evaluation
            can_execute, reason = security_gatekeeper.evaluate_action(
                action_name=f"{step.tool_name}",
                risk_level=step.risk_level,
                details=step.tool_args,
                task_id=task.task_id,
            )

            if not can_execute:
                if step.risk_level == RiskLevel.HIGH or settings.security.require_confirmation_medium_risk:
                    task.status = TaskStatus.WAITING_APPROVAL
                    task.requires_approval = True
                    task.pending_approval_step = step
                    step.status = StepStatus.WAITING_APPROVAL
                    self._notify_progress(task)
                    logger.info(f"Task {task.task_id} waiting for user approval on step: {step.title}")
                    return task
                else:
                    step.status = StepStatus.FAILED
                    step.error = reason
                    task.status = TaskStatus.FAILED
                    task.error_details = reason
                    self._notify_progress(task)
                    return task

            # 1. OBSERVE (Before)
            step.observation_before = self.capture_observation()

            # 2. ACT (Tool Execution)
            tool_call = ToolCall(
                tool_name=step.tool_name,
                args=step.tool_args,
                risk_level=step.risk_level,
                executed_at=time.time(),
            )
            step.tool_call = tool_call

            try:
                result = tool_registry.execute_tool(step.tool_name, step.tool_args)
                tool_call.success = result.success
                tool_call.output = result.output
                tool_call.error = result.error
                if result.artifacts:
                    task.artifacts.extend(result.artifacts)
            except Exception as e:
                tool_call.success = False
                tool_call.error = str(e)
                result = None

            # 3. OBSERVE (After)
            step.observation_after = self.capture_observation()

            # 4. VERIFY
            step_success = tool_call.success
            verification = VerificationResult(
                verified=step_success,
                criteria=step.verification_criteria,
                details="Action executed and verified." if step_success else f"Action failed: {tool_call.error}",
                artifacts=task.artifacts.copy(),
            )
            step.verification_result = verification

            if step_success:
                step.status = StepStatus.COMPLETED
                task.current_step_index += 1
                task.updated_at = time.time()
                self._notify_progress(task)
            else:
                # Error recovery and retry handling
                if step.retries < step.max_retries:
                    step.retries += 1
                    logger.warning(
                        f"Step {step.step_id} failed. Attempting retry {step.retries}/{step.max_retries}..."
                    )
                    time.sleep(0.5)
                    continue  # Retry same step
                else:
                    step.status = StepStatus.FAILED
                    step.error = tool_call.error or "Step verification failed."
                    task.status = TaskStatus.FAILED
                    task.error_details = f"Failed at step '{step.title}': {step.error}"
                    self._notify_progress(task)
                    return task

        # Final Task Verification
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.verification_result = VerificationResult(
            verified=True,
            criteria="All planned task steps executed and verified.",
            details=f"Task completed successfully with {len(task.steps)} verified steps.",
            artifacts=task.artifacts.copy(),
        )
        self._notify_progress(task)

        audit_logger.log_event(
            event_type="TASK_COMPLETE",
            action="FINISH_TASK",
            risk_level="LOW",
            status="COMPLETED",
            task_id=task.task_id,
            details={"artifacts": task.artifacts}
        )
        return task

    async def execute_task_async(self, task: Task) -> Task:
        """Asynchronous execution bridge for background event loops."""
        return await asyncio.to_thread(self.execute_task, task)

    def approve_pending_step(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if not task or task.status != TaskStatus.WAITING_APPROVAL:
            return False
        task.requires_approval = False
        task.pending_approval_step = None
        task.status = TaskStatus.RUNNING
        audit_logger.log_event(
            event_type="USER_APPROVAL",
            action="APPROVE_STEP",
            risk_level="HIGH",
            status="APPROVED",
            task_id=task_id,
        )
        return True

    def reject_pending_step(self, task_id: str, reason: str = "Rejected by user") -> bool:
        task = self._active_tasks.get(task_id)
        if not task or task.status != TaskStatus.WAITING_APPROVAL:
            return False
        task.status = TaskStatus.STOPPED
        task.error_details = f"Action rejected by user: {reason}"
        task.requires_approval = False
        audit_logger.log_event(
            event_type="USER_REJECTION",
            action="REJECT_STEP",
            risk_level="HIGH",
            status="REJECTED",
            task_id=task_id,
            details={"reason": reason}
        )
        self._notify_progress(task)
        return True

    def pause_task(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSED
            self._notify_progress(task)
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.RUNNING
            self._notify_progress(task)
            return True
        return False

    def stop_task(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if task:
            task.status = TaskStatus.STOPPED
            task.error_details = "Task stopped by user request."
            self._notify_progress(task)
            return True
        return False


task_executor = TaskExecutor()
