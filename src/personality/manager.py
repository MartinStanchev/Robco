"""Personality configuration loader and manager.

Loads personality JSON files from the personalities directory,
validates them against the voice catalog, and provides lookup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.personality.voices import get_voice


_VALID_VAD_SENSITIVITIES = {"LOW", "MEDIUM", "HIGH"}


@dataclass(frozen=True)
class PersonalityConfig:
    """Configuration for a robot personality.

    Attributes:
        name: Display name of the personality.
        voice: Gemini voice name (must exist in voice catalog).
        system_prompt: System instruction sent to Gemini.
        description: Short description of this personality.
        conversation_timeout_seconds: Seconds of silence before ending session.
        vad_sensitivity: Voice activity detection sensitivity ("LOW", "MEDIUM", "HIGH").
    """

    name: str
    voice: str
    system_prompt: str
    description: str
    conversation_timeout_seconds: int
    vad_sensitivity: str


def _validate_personality(data: dict[str, Any], source: str) -> PersonalityConfig:
    """Validate and create a PersonalityConfig from raw JSON data.

    Args:
        data: Parsed JSON dictionary.
        source: File path or identifier for error messages.

    Returns:
        Validated PersonalityConfig.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    required_fields = ["name", "voice", "system_prompt"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Personality '{source}' missing required field: {field}")

    voice_name = data["voice"]
    try:
        get_voice(voice_name)
    except KeyError as e:
        raise ValueError(
            f"Personality '{source}' uses unknown voice '{voice_name}': {e}"
        ) from e

    vad = data.get("vad_sensitivity", "MEDIUM").upper()
    if vad not in _VALID_VAD_SENSITIVITIES:
        raise ValueError(
            f"Personality '{source}' has invalid vad_sensitivity '{vad}'. "
            f"Must be one of: {_VALID_VAD_SENSITIVITIES}"
        )

    return PersonalityConfig(
        name=data["name"],
        voice=voice_name,
        system_prompt=data["system_prompt"],
        description=data.get("description", ""),
        conversation_timeout_seconds=int(data.get("conversation_timeout_seconds", 30)),
        vad_sensitivity=vad,
    )


class PersonalityManager:
    """Loads and manages personality configurations from JSON files.

    Args:
        personalities_dir: Path to directory containing personality JSON files.
    """

    def __init__(self, personalities_dir: str | Path) -> None:
        self._dir = Path(personalities_dir)
        self._personalities: dict[str, PersonalityConfig] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all personality JSON files from the directory."""
        if not self._dir.exists():
            return

        for json_file in sorted(self._dir.glob("*.json")):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                personality = _validate_personality(data, str(json_file))
                key = json_file.stem.lower()
                self._personalities[key] = personality
            except (json.JSONDecodeError, ValueError) as e:
                # Log and skip invalid files rather than crashing
                print(f"Warning: Skipping invalid personality file {json_file}: {e}")

    def get_personality(self, name: str) -> PersonalityConfig:
        """Get a personality by name (case-insensitive, matches filename stem).

        Args:
            name: Personality name (e.g., "friendly", "professional").

        Returns:
            PersonalityConfig for the requested personality.

        Raises:
            KeyError: If the personality is not found.
        """
        key = name.lower()
        if key not in self._personalities:
            available = ", ".join(self._personalities.keys())
            raise KeyError(
                f"Personality '{name}' not found. Available: {available}"
            )
        return self._personalities[key]

    def list_personalities(self) -> list[str]:
        """Return names of all loaded personalities.

        Returns:
            Sorted list of personality names (filename stems).
        """
        return sorted(self._personalities.keys())

    def get_default(self) -> PersonalityConfig:
        """Get the default personality ('friendly').

        Returns:
            The 'friendly' personality config.

        Raises:
            KeyError: If the 'friendly' personality is not loaded.
        """
        return self.get_personality("friendly")
