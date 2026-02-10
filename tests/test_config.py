"""Tests for the configuration system (Task 1)."""

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

from src.core.config import Settings, load_settings


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Robco env vars so tests start clean."""
    for key in [
        "GEMINI_API_KEY", "GEMINI_MODEL", "INPUT_SAMPLE_RATE",
        "OUTPUT_SAMPLE_RATE", "INPUT_CHANNELS", "AUDIO_CHUNK_SIZE",
        "WAKE_WORD", "WAKE_WORD_SENSITIVITY", "DEFAULT_PERSONALITY",
        "PERSONALITIES_DIR", "CONVERSATION_TIMEOUT", "MAX_SESSION_DURATION",
        "N8N_SERVER_URL", "N8N_API_KEY", "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)


class TestLoadSettings:
    """Tests for load_settings()."""

    def test_loads_from_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=test-key-123\n")

        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text("")

        settings = load_settings(env_path=env_file, yaml_path=yaml_file)
        assert settings.gemini_api_key == "test-key-123"

    def test_defaults_from_yaml(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=key\n")

        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text(dedent("""\
            audio:
              input_sample_rate: 44100
              chunk_size: 2048
            conversation:
              timeout: 60
        """))

        settings = load_settings(env_path=env_file, yaml_path=yaml_file)
        assert settings.input_sample_rate == 44100
        assert settings.audio_chunk_size == 2048
        assert settings.conversation_timeout == 60

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=key\nINPUT_SAMPLE_RATE=8000\n")

        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text(dedent("""\
            audio:
              input_sample_rate: 44100
        """))

        settings = load_settings(env_path=env_file, yaml_path=yaml_file)
        assert settings.input_sample_rate == 8000

    def test_hardcoded_defaults_when_no_yaml(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=key\n")

        yaml_file = tmp_path / "nonexistent.yaml"

        settings = load_settings(env_path=env_file, yaml_path=yaml_file)
        assert settings.gemini_model == "gemini-2.5-flash-preview-native-audio-dialog"
        assert settings.input_sample_rate == 16000
        assert settings.output_sample_rate == 24000
        assert settings.input_channels == 1
        assert settings.audio_chunk_size == 1024
        assert settings.wake_word == "hey robot"
        assert settings.wake_word_sensitivity == 0.5
        assert settings.default_personality == "friendly"
        assert settings.conversation_timeout == 30
        assert settings.max_session_duration == 600
        assert settings.n8n_server_url == ""
        assert settings.n8n_api_key == ""
        assert settings.log_level == "INFO"

    def test_missing_api_key_raises(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("")
        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text("")

        with pytest.raises(ValueError, match="GEMINI_API_KEY is required"):
            load_settings(env_path=env_file, yaml_path=yaml_file)

    def test_settings_is_frozen(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("GEMINI_API_KEY=key\n")
        yaml_file = tmp_path / "default.yaml"
        yaml_file.write_text("")

        settings = load_settings(env_path=env_file, yaml_path=yaml_file)
        with pytest.raises(AttributeError):
            settings.gemini_api_key = "other"  # type: ignore[misc]
