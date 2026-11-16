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
from sam.computer_use.session_manager import session_manager, ComputerUseSessionConflictError
from sam.config.settings import settings

logger = logging.getLogger("sam.executor")


class InvalidStateTransitionError(Exception):
    pass


class TaskExecutor:
    """Orchestrates step execution, state observation, and post-action verification."""

    VALID_TRANSITIONS = {
        TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.STOPPED, TaskStatus.FAILED},
        TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.STOPPED, TaskStatus.FAILED, TaskStatus.PENDING},
        TaskStatus.RUNNING: {TaskStatus.PAUSED, TaskStatus.WAITING_APPROVAL, TaskStatus.VERIFYING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED},
        TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.STOPPED, TaskStatus.FAILED},
        TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.STOPPED, TaskStatus.FAILED},
        TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED},
        TaskStatus.COMPLETED: set(),  # Terminal
        TaskStatus.FAILED: set(),     # Terminal
        TaskStatus.STOPPED: set(),    # Terminal
    }

    def __init__(self):
        self._active_tasks: dict[str, Task] = {}
        self._observer_func: Optional[Callable[[], Observation]] = None
        self._progress_callbacks: list[Callable[[Task], None]] = []

        # Wire real Windows desktop screen observer by default
        try:
            from sam.computer_use.operator import computer_operator
            self.register_observer(computer_operator.observe_state)
            logger.info("Successfully registered computer_operator.observe_state as desktop observer.")
        except Exception as e:
            logger.debug(f"Default observer deferred: {e}")

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

    def set_task_status(self, task: Task, new_status: TaskStatus) -> bool:
        """Transitions task status ensuring valid FSM lifecycle rules."""
        if task.status == new_status:
            return True
        allowed = self.VALID_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            logger.warning(
                f"Blocked invalid state transition for task {task.task_id}: {task.status.value} -> {new_status.value}"
            )
            return False
        task.status = new_status
        task.updated_at = time.time()
        return True

    def capture_observation(self) -> Observation:
        """Captures desktop state. Returns explicit failure/placeholder metadata if capture fails."""
        if self._observer_func:
            try:
                obs = self._observer_func()
                if obs is not None:
                    return obs
            except Exception as e:
                logger.warning(f"Observer failed: {e}")
                return Observation(
                    timestamp=time.time(),
                    window_title="",
                    active_process="",
                    text_content=f"Observation capture error: {e}",
                    success=False,
                    is_placeholder=True,
                    error=str(e),
                )
        return Observation(
            timestamp=time.time(),
            window_title="Unknown",
            active_process="",
            text_content="No active observer registered.",
            success=False,
            is_placeholder=True,
            error="No observer registered",
        )

    def verify_step_outcome(self, step: TaskStep, tool_call: ToolCall) -> VerificationResult:
        """
        Enforces action-specific physical and observable verification criteria.
        Does NOT rely solely on tool_call.success.
        """
        if not tool_call.success:
            return VerificationResult(
                verified=False,
                criteria=step.verification_criteria,
                details=f"Tool execution failed: {tool_call.error}",
            )

        # 1. Desktop Observation Verification
        if step.tool_name == "computer_observe_desktop":
            obs = step.observation_after
            if not obs or obs.is_placeholder or not obs.success:
                return VerificationResult(
                    verified=False,
                    criteria=step.verification_criteria,
                    details="Desktop observation failed: Observation returned placeholder or error.",
                )

        # 2. Computer-Use GUI Actions
        if step.tool_name.startswith("computer_"):
            obs = step.observation_after
            if not obs or obs.is_placeholder or not obs.success:
                return VerificationResult(
                    verified=False,
                    criteria=step.verification_criteria,
                    details="GUI action post-observation failed or produced placeholder.",
                )
            if step.tool_name == "computer_focus_window":
                query = step.tool_args.get("title_query", "").lower()
                if query and query not in (obs.window_title or "").lower():
                    return VerificationResult(
                        verified=False,
                        criteria=step.verification_criteria,
                        details=f"Target window title '{obs.window_title}' did not match query '{query}'.",
                    )

        # 3. File Creation & Modification Artifacts
        if step.tool_name in ["coding_write_file", "document_create_report", "document_export_analysis", "video_export_render", "video_trim_clip"]:
            from pathlib import Path
            if not tool_call.output:
                return VerificationResult(
                    verified=False,
                    criteria=step.verification_criteria,
                    details="Action returned no output artifact reference.",
                )
            # Check artifact paths on disk
            artifacts_to_check = []
            if hasattr(tool_call, "artifacts") and tool_call.artifacts:
                for a in tool_call.artifacts:
                    artifacts_to_check.append(Path(a))
            elif step.tool_name == "coding_write_file" and "filename" in step.tool_args:
                ws_name = step.tool_args.get("workspace_name", "default_project")
                ws_dir = settings.data_dir / "workspaces" / ws_name
                artifacts_to_check.append(ws_dir / step.tool_args["filename"])
            elif isinstance(tool_call.output, dict):
                p = tool_call.output.get("output_path") or tool_call.output.get("path")
                if p:
                    artifacts_to_check.append(Path(p))
            elif isinstance(tool_call.output, str):
                cleaned = tool_call.output.strip()
                if " at: " in cleaned:
                    cleaned = cleaned.split(" at: ")[-1].strip()
                if "\n" not in cleaned and ("/" in cleaned or "\\" in cleaned or Path(cleaned).suffix):
                    artifacts_to_check.append(Path(cleaned))
            elif isinstance(tool_call.output, Path):
                artifacts_to_check.append(tool_call.output)

            for art in artifacts_to_check:
                if not art.exists() or art.stat().st_size == 0:
                    return VerificationResult(
                        verified=False,
                        criteria=step.verification_criteria,
                        details=f"Expected artifact '{art}' does not exist on disk or is 0 bytes.",
                    )

        # 4. Code & Test Execution
        if step.tool_name == "coding_run_script":
            if isinstance(tool_call.output, dict):
                code = tool_call.output.get("exit_code")
                if code != 0:
                    return VerificationResult(
                        verified=False,
                        criteria=step.verification_criteria,
                        details=f"Script execution exited with non-zero code {code}: {tool_call.output.get('stderr')}",
                    )

        if step.tool_name == "coding_run_tests":
            if isinstance(tool_call.output, dict):
                passed = tool_call.output.get("tests_passed", False)
                if not passed:
                    return VerificationResult(
                        verified=False,
                        criteria=step.verification_criteria,
                        details=f"Unit tests failed: {tool_call.output.get('stderr')}",
                    )

        # Step-level visual verification note
        visual_changed = False
        if step.observation_before and step.observation_after:
            v1 = step.observation_before.visual_hash
            v2 = step.observation_after.visual_hash
            if v1 and v2 and v1 != v2:
                visual_changed = True

        detail_str = "Action executed and verified."
        if visual_changed:
            detail_str += " (Visual state change confirmed)"

        return VerificationResult(
            verified=True,
            criteria=step.verification_criteria,
            details=detail_str,
            artifacts=step.tool_call.args.get("artifacts", []),
        )

    def execute_task(self, task: Task) -> Task:
        """Synchronously executes a planned task through the observe-plan-act-verify loop."""
        self._active_tasks[task.task_id] = task

        # Do not restart or overwrite terminal or cancelled states
        if task.status in [TaskStatus.STOPPED, TaskStatus.COMPLETED, TaskStatus.FAILED]:
            logger.warning(f"Task {task.task_id} is already in terminal/stopped state ({task.status.value}). Aborting execution.")
            return task

        if not self.set_task_status(task, TaskStatus.RUNNING):
            return task
        self._notify_progress(task)

        audit_logger.log_event(
            event_type="TASK_START",
            action="EXECUTE_TASK",
            risk_level="LOW",
            status="RUNNING",
            task_id=task.task_id,
            details={"objective": task.objective, "total_steps": len(task.steps)}
        )

        has_computer_steps = any(
            step.tool_name.startswith("computer_") or "mouse" in step.tool_name or "keyboard" in step.tool_name
            for step in task.steps
        )
        acquired_session = False
        if has_computer_steps:
            try:
                session_manager.acquire(task.task_id, timeout=2.0)
                acquired_session = True
            except ComputerUseSessionConflictError as e:
                task.status = TaskStatus.FAILED
                task.error_details = f"Cannot execute desktop task: concurrent session in progress ({e})"
                self._notify_progress(task)
                return task

        try:
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
                    tool_call.artifacts = list(result.artifacts or [])
                    if result.artifacts:
                        task.artifacts.extend(result.artifacts)
                except Exception as e:
                    tool_call.success = False
                    tool_call.error = str(e)
                    result = None

                # 3. OBSERVE (After)
                step.observation_after = self.capture_observation()

                # 4. VERIFY (Action-specific outcome verification)
                verification = self.verify_step_outcome(step, tool_call)
                step.verification_result = verification
                step_success = verification.verified

                if step_success:
                    step.status = StepStatus.COMPLETED
                    task.current_step_index += 1
                    task.updated_at = time.time()
                    self._notify_progress(task)
                else:
                    # Check if emergency stop or cancellation was triggered before retrying
                    if security_gatekeeper.is_emergency_stop_active or task.status in [TaskStatus.STOPPED, TaskStatus.PAUSED, TaskStatus.FAILED]:
                        return task

                    # Error recovery and retry handling
                    if step.retries < step.max_retries:
                        step.retries += 1
                        logger.warning(
                            f"Step {step.step_id} failed: {verification.details}. Attempting retry {step.retries}/{step.max_retries}..."
                        )
                        time.sleep(0.3)
                        if security_gatekeeper.is_emergency_stop_active or task.status in [TaskStatus.STOPPED, TaskStatus.PAUSED, TaskStatus.FAILED]:
                            return task
                        continue  # Retry same step
                    else:
                        step.status = StepStatus.FAILED
                        step.error = verification.details
                        self.set_task_status(task, TaskStatus.FAILED)
                        task.error_details = f"Failed at step '{step.title}': {step.error}"
                        self._notify_progress(task)
                        return task

            # Final Task Verification
            self.set_task_status(task, TaskStatus.COMPLETED)
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
        finally:
            if acquired_session:
                session_manager.release(task.task_id)

    async def execute_task_async(self, task: Task) -> Task:
        """Asynchronous execution bridge for background event loops."""
        return await asyncio.to_thread(self.execute_task, task)

    def approve_pending_step(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if not task or task.status != TaskStatus.WAITING_APPROVAL:
            return False
        task.requires_approval = False
        task.pending_approval_step = None
        self.set_task_status(task, TaskStatus.RUNNING)
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
        self.set_task_status(task, TaskStatus.STOPPED)
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
            if self.set_task_status(task, TaskStatus.PAUSED):
                session_manager.pause()
                self._notify_progress(task)
                return True
        return False

    def resume_task(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            if self.set_task_status(task, TaskStatus.RUNNING):
                session_manager.resume()
                self._notify_progress(task)
                return True
        return False

    def stop_task(self, task_id: str) -> bool:
        task = self._active_tasks.get(task_id)
        if task and task.status not in [TaskStatus.COMPLETED, TaskStatus.STOPPED]:
            self.set_task_status(task, TaskStatus.STOPPED)
            task.error_details = "Task stopped by user request."
            session_manager.release(task_id)
            self._notify_progress(task)
            return True
        return False


task_executor = TaskExecutor()
