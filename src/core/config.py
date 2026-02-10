"""Configuration loader for the Robco voice robot.

Loads settings from environment variables (.env file) and config/default.yaml,
with environment variables taking precedence over YAML defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


# Project root is two levels up from this file (src/core/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    """Immutable configuration for the Robco voice robot."""

    # Gemini
    gemini_api_key: str
    gemini_model: str

    # Audio
    input_sample_rate: int
    output_sample_rate: int
    input_channels: int
    audio_chunk_size: int

    # Wake word
    wake_word: str
    wake_word_sensitivity: float

    # Personality
    default_personality: str
    personalities_dir: str

    # Conversation
    conversation_timeout: int
    max_session_duration: int

    # n8n (optional)
    n8n_server_url: str
    n8n_api_key: str

    # Logging
    log_level: str


def _load_yaml_defaults(yaml_path: Path) -> dict[str, Any]:
    """Load default values from a YAML config file.

    Args:
        yaml_path: Path to the YAML configuration file.

    Returns:
        Dictionary of configuration values. Empty dict if file not found.
    """
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    return data if data else {}


def _get(env_key: str, yaml_defaults: dict[str, Any], yaml_key: str, default: Any = None) -> Any:
    """Get a config value with precedence: env var > yaml default > hardcoded default.

    Args:
        env_key: Environment variable name.
        yaml_defaults: Dictionary from YAML config file.
        yaml_key: Dot-separated key path in YAML (e.g., "audio.input_sample_rate").
        default: Fallback default value.

    Returns:
        The resolved configuration value.
    """
    # Environment variable takes precedence
    env_val = os.environ.get(env_key)
    if env_val is not None and env_val != "":
        return env_val

    # Walk nested YAML keys
    parts = yaml_key.split(".")
    node = yaml_defaults
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node if node is not None else default


def load_settings(
    env_path: Path | None = None,
    yaml_path: Path | None = None,
) -> Settings:
    """Load settings from .env and config/default.yaml.

    Environment variables take precedence over YAML defaults.

    Args:
        env_path: Path to .env file. Defaults to PROJECT_ROOT/.env.
        yaml_path: Path to YAML config. Defaults to PROJECT_ROOT/config/default.yaml.

    Returns:
        Frozen Settings dataclass with all configuration values.

    Raises:
        ValueError: If required configuration (gemini_api_key) is missing.
    """
    if env_path is None:
        env_path = PROJECT_ROOT / ".env"
    if yaml_path is None:
        yaml_path = PROJECT_ROOT / "config" / "default.yaml"

    load_dotenv(env_path, override=False)
    yaml_defaults = _load_yaml_defaults(yaml_path)

    gemini_api_key = _get("GEMINI_API_KEY", yaml_defaults, "gemini.api_key", "")
    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY is required. Set it in .env or as an environment variable."
        )

    return Settings(
        gemini_api_key=gemini_api_key,
        gemini_model=str(
            _get("GEMINI_MODEL", yaml_defaults, "gemini.model",
                 "gemini-2.5-flash-preview-native-audio-dialog")
        ),
        input_sample_rate=int(
            _get("INPUT_SAMPLE_RATE", yaml_defaults, "audio.input_sample_rate", 16000)
        ),
        output_sample_rate=int(
            _get("OUTPUT_SAMPLE_RATE", yaml_defaults, "audio.output_sample_rate", 24000)
        ),
        input_channels=int(
            _get("INPUT_CHANNELS", yaml_defaults, "audio.input_channels", 1)
        ),
        audio_chunk_size=int(
            _get("AUDIO_CHUNK_SIZE", yaml_defaults, "audio.chunk_size", 1024)
        ),
        wake_word=str(
            _get("WAKE_WORD", yaml_defaults, "wake_word.phrase", "hey robot")
        ),
        wake_word_sensitivity=float(
            _get("WAKE_WORD_SENSITIVITY", yaml_defaults, "wake_word.sensitivity", 0.5)
        ),
        default_personality=str(
            _get("DEFAULT_PERSONALITY", yaml_defaults, "personality.default", "friendly")
        ),
        personalities_dir=str(
            _get("PERSONALITIES_DIR", yaml_defaults, "personality.dir",
                 str(PROJECT_ROOT / "config" / "personalities"))
        ),
        conversation_timeout=int(
            _get("CONVERSATION_TIMEOUT", yaml_defaults, "conversation.timeout", 30)
        ),
        max_session_duration=int(
            _get("MAX_SESSION_DURATION", yaml_defaults, "conversation.max_duration", 600)
        ),
        n8n_server_url=str(
            _get("N8N_SERVER_URL", yaml_defaults, "n8n.server_url", "")
        ),
        n8n_api_key=str(
            _get("N8N_API_KEY", yaml_defaults, "n8n.api_key", "")
        ),
        log_level=str(
            _get("LOG_LEVEL", yaml_defaults, "logging.level", "INFO")
        ),
    )
