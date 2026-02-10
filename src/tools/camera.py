"""Camera MCP tool — capture frames for Gemini's multimodal understanding.

Provides a tool that captures a single camera frame as base64-encoded JPEG
for Gemini to analyze during conversation.
"""

from __future__ import annotations

import base64

from src.hardware.interfaces import CameraInput
from src.tools.server import ToolDefinition


def create_camera_tools(camera: CameraInput) -> list[ToolDefinition]:
    """Create camera tool definitions bound to a CameraInput instance.

    Args:
        camera: The camera hardware interface.

    Returns:
        List of ToolDefinition objects for camera capture.
    """

    def capture_camera_frame() -> dict[str, object]:
        frame_bytes = camera.capture_frame()
        return {
            "image": base64.b64encode(frame_bytes).decode("ascii"),
            "mime_type": "image/jpeg",
            "size_bytes": len(frame_bytes),
        }

    return [
        ToolDefinition(
            name="capture_camera_frame",
            description=(
                "Capture a photo from the robot's camera. "
                "Returns a base64-encoded JPEG image."
            ),
            parameters={},
            handler=capture_camera_frame,
        ),
    ]
