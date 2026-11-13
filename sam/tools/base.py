"""
SAM - Base Tool Contract & Input/Output Schema Definition
"""

from abc import ABC, abstractmethod
from typing import Any, Callable
from pydantic import BaseModel, Field
from sam.agent.models import RiskLevel, ToolCall
import time


class ToolResult(BaseModel):
    success: bool
    output: Any = None
    error: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_time_s: float = 0.0


class BaseTool(ABC):
    """Abstract base class for all tools in SAM."""

    name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    args_schema: type[BaseModel] | None = None

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Executes the tool synchronously or within executor thread."""
        pass

    def run_validated(self, **kwargs: Any) -> ToolResult:
        """Validates arguments against args_schema if provided, then executes."""
        start_t = time.time()
        try:
            if self.args_schema:
                validated = self.args_schema(**kwargs)
                kwargs = validated.model_dump()
            result = self.execute(**kwargs)
            result.execution_time_s = round(time.time() - start_t, 4)
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool '{self.name}' error: {str(e)}",
                execution_time_s=round(time.time() - start_t, 4)
            )


class SimpleFunctionTool(BaseTool):
    """Wrapper to turn standard Python functions into validated SAM tools."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        risk_level: RiskLevel = RiskLevel.LOW,
        args_schema: type[BaseModel] | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.risk_level = risk_level
        self.args_schema = args_schema

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            res = self.func(**kwargs)
            if isinstance(res, ToolResult):
                return res
            return ToolResult(success=True, output=res)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

