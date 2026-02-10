"""Robot state machine definitions.

Defines the states for the robot's main control loop.
"""

from __future__ import annotations

from enum import Enum, auto


class RobotState(Enum):
    """States of the robot controller.

    Transitions:
        IDLE → CONNECTING (wake word detected)
        CONNECTING → CONVERSATION (Gemini session opened)
        CONNECTING → IDLE (connection failed)
        CONVERSATION → IDLE (silence timeout, go_away, or error)
        Any → SHUTTING_DOWN (stop requested)
    """

    IDLE = auto()
    CONNECTING = auto()
    CONVERSATION = auto()
    SHUTTING_DOWN = auto()
