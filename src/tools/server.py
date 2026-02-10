"""MCP tool server — manages tool registration and execution.

Provides a ToolServer that registers tools (built-in and user-defined),
converts them to Gemini-compatible function declarations, and executes
tool calls received during conversation.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Callable

from src.hardware.interfaces import CameraInput, DisplayOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolParam:
    """Parameter definition for a tool.

    Attributes:
        type: JSON Schema type ("string", "integer", "number", "boolean").
        description: Human-readable description of the parameter.
        required: Whether the parameter is required.
    """

    type: str
    description: str
    required: bool = True


@dataclass
class ToolDefinition:
    """A registered tool with its metadata and handler.

    Attributes:
        name: Tool name (must be unique across the server).
        description: Human-readable description shown to the model.
        parameters: Parameter definitions keyed by name.
        handler: Callable that executes the tool logic.
    """

    name: str
    description: str
    parameters: dict[str, ToolParam] = field(default_factory=dict)
    handler: Callable[..., Any] = field(default=lambda: {})


class ToolServer:
    """Manages tool registrations and execution for Gemini function calling.

    Tools are registered as ToolDefinition objects and converted to
    Gemini-compatible dict-format declarations for the Live API session.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a single tool.

        Args:
            tool: Tool definition to register.
        """
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def register_builtin_tools(
        self,
        display: DisplayOutput | None = None,
        camera: CameraInput | None = None,
    ) -> None:
        """Register built-in tools based on available hardware.

        Args:
            display: Display hardware interface (enables display tools).
            camera: Camera hardware interface (enables camera tools).
        """
        if display:
            from src.tools.display import create_display_tools

            for tool in create_display_tools(display):
                self.register_tool(tool)

        if camera:
            from src.tools.camera import create_camera_tools

            for tool in create_camera_tools(camera):
                self.register_tool(tool)

    def discover_user_tools(self, tools_dir: str = "src/tools/user_tools") -> None:
        """Auto-discover and register user tool modules from a directory.

        Each Python file (not starting with ``_``) can export a ``TOOLS``
        list of :class:`ToolDefinition` objects.

        Args:
            tools_dir: Path to the directory containing user tool modules.
        """
        tools_path = Path(tools_dir)
        if not tools_path.is_dir():
            logger.debug("User tools directory not found: %s", tools_dir)
            return

        for py_file in sorted(tools_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib_util.spec_from_file_location(
                    f"user_tools.{py_file.stem}", py_file
                )
                if spec and spec.loader:
                    module = importlib_util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    tools_list = getattr(module, "TOOLS", [])
                    count = 0
                    for tool in tools_list:
                        if isinstance(tool, ToolDefinition):
                            self.register_tool(tool)
                            count += 1
                    logger.info(
                        "Loaded %d tool(s) from %s", count, py_file.name
                    )
            except Exception as e:
                logger.warning(
                    "Failed to load user tools from %s: %s", py_file.name, e
                )

    def get_tool_declarations(self) -> list[dict] | None:
        """Return Gemini-compatible tool declarations as dicts.

        Returns:
            A list containing one tool dict with all function declarations,
            or None if no tools are registered.
        """
        if not self._tools:
            return None

        declarations = []
        for tool in self._tools.values():
            decl: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
            }

            if tool.parameters:
                properties: dict[str, dict[str, str]] = {}
                required: list[str] = []
                for param_name, param in tool.parameters.items():
                    properties[param_name] = {
                        "type": param.type.upper(),
                        "description": param.description,
                    }
                    if param.required:
                        required.append(param_name)
                decl["parameters"] = {
                    "type": "OBJECT",
                    "properties": properties,
                    "required": required,
                }

            declarations.append(decl)

        return [{"function_declarations": declarations}]

    async def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a registered tool by name.

        Args:
            name: Tool name.
            args: Arguments to pass to the tool handler.

        Returns:
            Result dictionary from the tool, or an error dict on failure.
        """
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}

        try:
            result = tool.handler(**args)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"result": str(result)}
            return result
        except Exception as e:
            logger.error("Tool '%s' failed: %s", name, e)
            return {"error": f"Tool execution failed: {e}"}

    @property
    def registered_tools(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tools.keys())
