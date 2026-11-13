"""
SAM - Central Tool Registry
Manages tool discovery, schema introspection, permission checking, and guarded execution.
"""

from typing import Any, Callable
from sam.tools.base import BaseTool, ToolResult, SimpleFunctionTool
from sam.agent.models import RiskLevel, ToolCall
import json
import logging

logger = logging.getLogger("sam.tools.registry")


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        """Register a BaseTool instance."""
        if not tool.name:
            raise ValueError("Tool must have a non-empty name.")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} (Risk: {tool.risk_level.value})")
        return tool

    def register_func(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        args_schema: Any = None,
    ) -> Callable:
        """Decorator to register a simple function as a SAM tool."""
        def decorator(func: Callable) -> Callable:
            tool = SimpleFunctionTool(
                name=name,
                description=description,
                func=func,
                risk_level=risk_level,
                args_schema=args_schema,
            )
            self.register(tool)
            return func
        return decorator

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        result = []
        for name, tool in self._tools.items():
            schema = None
            if tool.args_schema:
                schema = tool.args_schema.model_json_schema()
            result.append({
                "name": name,
                "description": tool.description,
                "risk_level": tool.risk_level.value,
                "schema": schema,
            })
        return result

    def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' is not registered in SAM ToolRegistry."
            )
        return tool.run_validated(**args)


# Global singleton tool registry
tool_registry = ToolRegistry()

