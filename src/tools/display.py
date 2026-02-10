"""Display MCP tools — control the robot's screen via Gemini function calling.

Provides tools for showing text, status indicators, and clearing the display.
Tools are created bound to a specific DisplayOutput instance.
"""

from __future__ import annotations

from src.hardware.interfaces import DisplayOutput
from src.tools.server import ToolDefinition, ToolParam


def create_display_tools(display: DisplayOutput) -> list[ToolDefinition]:
    """Create display tool definitions bound to a DisplayOutput instance.

    Args:
        display: The display hardware interface.

    Returns:
        List of ToolDefinition objects for display control.
    """

    def display_text(text: str) -> dict[str, str]:
        display.show_text(text)
        return {"status": "ok", "text": text}

    def display_status(status: str) -> dict[str, str]:
        display.show_status(status)
        return {"status": "ok", "status_shown": status}

    def clear_display() -> dict[str, str]:
        display.clear()
        return {"status": "ok"}

    return [
        ToolDefinition(
            name="display_text",
            description="Show text on the robot's screen.",
            parameters={
                "text": ToolParam(
                    type="string", description="Text content to display"
                ),
            },
            handler=display_text,
        ),
        ToolDefinition(
            name="display_status",
            description="Show a status indicator on the robot's screen.",
            parameters={
                "status": ToolParam(
                    type="string",
                    description="Status string (e.g., 'listening', 'thinking')",
                ),
            },
            handler=display_status,
        ),
        ToolDefinition(
            name="clear_display",
            description="Clear the robot's screen.",
            parameters={},
            handler=clear_display,
        ),
    ]
