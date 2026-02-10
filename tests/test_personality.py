"""Tests for the personality configuration system (Task 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.personality.manager import PersonalityConfig, PersonalityManager, _validate_personality
from src.personality.voices import VOICE_CATALOG, VoiceInfo, get_voice, list_voices


class TestVoiceCatalog:
    """Tests for the voice catalog."""

    def test_has_30_voices(self) -> None:
        assert len(VOICE_CATALOG) == 30

    def test_all_voices_are_voice_info(self) -> None:
        for voice in VOICE_CATALOG.values():
            assert isinstance(voice, VoiceInfo)
            assert voice.name
            assert voice.description
            assert voice.personality_fit

    def test_get_voice_exact(self) -> None:
        voice = get_voice("Achird")
        assert voice.name == "Achird"
        assert voice.description == "Friendly"

    def test_get_voice_case_insensitive(self) -> None:
        voice = get_voice("achird")
        assert voice.name == "Achird"

    def test_get_voice_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            get_voice("NonexistentVoice")

    def test_list_voices_returns_all(self) -> None:
        voices = list_voices()
        assert len(voices) == 30
        names = {v.name for v in voices}
        assert "Achird" in names
        assert "Kore" in names
        assert "Puck" in names
        assert "Vindemiatrix" in names

    def test_key_voices_present(self) -> None:
        """Verify the 4 voices used by pre-defined personalities exist."""
        for name in ["Achird", "Kore", "Puck", "Vindemiatrix"]:
            assert name in VOICE_CATALOG


class TestPersonalityValidation:
    """Tests for personality validation."""

    def test_valid_personality(self) -> None:
        data = {
            "name": "Test",
            "voice": "Achird",
            "system_prompt": "You are a test robot.",
            "description": "Test personality",
            "conversation_timeout_seconds": 30,
            "vad_sensitivity": "MEDIUM",
        }
        config = _validate_personality(data, "test.json")
        assert config.name == "Test"
        assert config.voice == "Achird"
        assert config.vad_sensitivity == "MEDIUM"

    def test_missing_name_raises(self) -> None:
        data = {"voice": "Achird", "system_prompt": "test"}
        with pytest.raises(ValueError, match="missing required field: name"):
            _validate_personality(data, "test.json")

    def test_missing_voice_raises(self) -> None:
        data = {"name": "Test", "system_prompt": "test"}
        with pytest.raises(ValueError, match="missing required field: voice"):
            _validate_personality(data, "test.json")

    def test_missing_system_prompt_raises(self) -> None:
        data = {"name": "Test", "voice": "Achird"}
        with pytest.raises(ValueError, match="missing required field: system_prompt"):
            _validate_personality(data, "test.json")

    def test_unknown_voice_raises(self) -> None:
        data = {"name": "Test", "voice": "FakeVoice", "system_prompt": "test"}
        with pytest.raises(ValueError, match="unknown voice"):
            _validate_personality(data, "test.json")

    def test_invalid_vad_raises(self) -> None:
        data = {
            "name": "Test",
            "voice": "Achird",
            "system_prompt": "test",
            "vad_sensitivity": "INVALID",
        }
        with pytest.raises(ValueError, match="invalid vad_sensitivity"):
            _validate_personality(data, "test.json")

    def test_defaults_applied(self) -> None:
        data = {"name": "Test", "voice": "Achird", "system_prompt": "test"}
        config = _validate_personality(data, "test.json")
        assert config.description == ""
        assert config.conversation_timeout_seconds == 30
        assert config.vad_sensitivity == "MEDIUM"

    def test_vad_case_insensitive(self) -> None:
        data = {
            "name": "Test",
            "voice": "Achird",
            "system_prompt": "test",
            "vad_sensitivity": "low",
        }
        config = _validate_personality(data, "test.json")
        assert config.vad_sensitivity == "LOW"


class TestPersonalityManager:
    """Tests for PersonalityManager."""

    def _write_personality(self, dir_path: Path, filename: str, data: dict) -> None:
        (dir_path / filename).write_text(json.dumps(data))

    def test_loads_from_directory(self, tmp_path: Path) -> None:
        self._write_personality(tmp_path, "test.json", {
            "name": "Test",
            "voice": "Achird",
            "system_prompt": "test prompt",
        })
        mgr = PersonalityManager(tmp_path)
        assert "test" in mgr.list_personalities()

    def test_get_personality(self, tmp_path: Path) -> None:
        self._write_personality(tmp_path, "mybot.json", {
            "name": "My Bot",
            "voice": "Puck",
            "system_prompt": "You are fun!",
            "description": "Fun bot",
        })
        mgr = PersonalityManager(tmp_path)
        p = mgr.get_personality("mybot")
        assert p.name == "My Bot"
        assert p.voice == "Puck"

    def test_get_personality_case_insensitive(self, tmp_path: Path) -> None:
        self._write_personality(tmp_path, "MyBot.json", {
            "name": "My Bot",
            "voice": "Kore",
            "system_prompt": "Professional.",
        })
        mgr = PersonalityManager(tmp_path)
        # Stored as lowercase of stem
        p = mgr.get_personality("mybot")
        assert p.name == "My Bot"

    def test_get_unknown_personality_raises(self, tmp_path: Path) -> None:
        mgr = PersonalityManager(tmp_path)
        with pytest.raises(KeyError, match="not found"):
            mgr.get_personality("nonexistent")

    def test_skips_invalid_files(self, tmp_path: Path) -> None:
        # Valid file
        self._write_personality(tmp_path, "good.json", {
            "name": "Good",
            "voice": "Achird",
            "system_prompt": "test",
        })
        # Invalid file (bad JSON)
        (tmp_path / "bad.json").write_text("not json{{{")

        mgr = PersonalityManager(tmp_path)
        assert "good" in mgr.list_personalities()
        assert "bad" not in mgr.list_personalities()

    def test_empty_directory(self, tmp_path: Path) -> None:
        mgr = PersonalityManager(tmp_path)
        assert mgr.list_personalities() == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        mgr = PersonalityManager(tmp_path / "nonexistent")
        assert mgr.list_personalities() == []

    def test_loads_real_personalities(self) -> None:
        """Test loading the actual shipped personality files."""
        personalities_dir = Path(__file__).parent.parent / "config" / "personalities"
        if not personalities_dir.exists():
            pytest.skip("Personality files not found")

        mgr = PersonalityManager(personalities_dir)
        names = mgr.list_personalities()
        assert "friendly" in names
        assert "professional" in names
        assert "energetic" in names
        assert "calm" in names

        friendly = mgr.get_personality("friendly")
        assert friendly.voice == "Achird"
        assert friendly.vad_sensitivity == "MEDIUM"

    def test_get_default(self) -> None:
        """Test get_default() with the real personality files."""
        personalities_dir = Path(__file__).parent.parent / "config" / "personalities"
        if not personalities_dir.exists():
            pytest.skip("Personality files not found")

        mgr = PersonalityManager(personalities_dir)
        default = mgr.get_default()
        assert default.name == "Friendly"

    def test_personality_config_is_frozen(self, tmp_path: Path) -> None:
        self._write_personality(tmp_path, "test.json", {
            "name": "Test",
            "voice": "Achird",
            "system_prompt": "test",
        })
        mgr = PersonalityManager(tmp_path)
        p = mgr.get_personality("test")
        with pytest.raises(AttributeError):
            p.name = "Changed"  # type: ignore[misc]
