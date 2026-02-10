"""Tests for the robot main controller (Task 8)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Settings
from src.core.controller import RobotController
from src.core.state_machine import RobotState
from src.gemini.session import ServerMessage
from src.hardware.stubs import (
    StubAudioInput,
    StubAudioOutput,
    StubCameraInput,
    StubDisplayOutput,
)

FIXTURES = Path(__file__).parent / "fixtures"
TEST_WAV = FIXTURES / "test_tone.wav"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERSONALITIES_DIR = PROJECT_ROOT / "config" / "personalities"


def _make_settings(**overrides: object) -> Settings:
    """Create a Settings object with test defaults."""
    defaults = dict(
        gemini_api_key="test-key",
        gemini_model="test-model",
        input_sample_rate=16000,
        output_sample_rate=24000,
        input_channels=1,
        audio_chunk_size=1024,
        wake_word="hey_jarvis",
        wake_word_sensitivity=0.5,
        default_personality="friendly",
        personalities_dir=str(PERSONALITIES_DIR),
        conversation_timeout=30,
        max_session_duration=600,
        n8n_server_url="",
        n8n_api_key="",
        log_level="INFO",
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class TestRobotState:
    def test_states_exist(self) -> None:
        assert RobotState.IDLE is not None
        assert RobotState.CONNECTING is not None
        assert RobotState.CONVERSATION is not None
        assert RobotState.SHUTTING_DOWN is not None

    def test_states_are_distinct(self) -> None:
        states = [RobotState.IDLE, RobotState.CONNECTING,
                  RobotState.CONVERSATION, RobotState.SHUTTING_DOWN]
        assert len(set(states)) == 4


# ---------------------------------------------------------------------------
# Controller init
# ---------------------------------------------------------------------------


class TestRobotControllerInit:
    @patch("src.core.controller.WakeWordDetector")
    def test_initial_state_is_idle(self, MockDetector: MagicMock) -> None:
        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.WakeWordDetector")
    def test_accepts_optional_display_camera(self, MockDetector: MagicMock) -> None:
        settings = _make_settings()
        display = StubDisplayOutput()
        camera = StubCameraInput()
        controller = RobotController(
            settings, StubAudioInput(), StubAudioOutput(),
            display=display, camera=camera,
        )
        assert controller.state == RobotState.IDLE


# ---------------------------------------------------------------------------
# IDLE state
# ---------------------------------------------------------------------------


class TestRobotControllerIdle:
    @patch("src.core.controller.WakeWordDetector")
    async def test_wake_word_transitions_to_connecting(
        self, MockDetector: MagicMock
    ) -> None:
        mock_det = MagicMock()

        async def fake_start(callback):
            await callback()

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        mock_det.is_listening = False
        MockDetector.return_value = mock_det

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._stop_event = asyncio.Event()

        await controller._run_idle()
        assert controller.state == RobotState.CONNECTING

    @patch("src.core.controller.WakeWordDetector")
    async def test_stop_during_idle(self, MockDetector: MagicMock) -> None:
        mock_det = MagicMock()

        async def fake_start(callback):
            pass  # Don't fire callback

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._stop_event = asyncio.Event()

        async def delayed_stop():
            await asyncio.sleep(0.05)
            controller._running = False
            controller._stop_event.set()

        asyncio.create_task(delayed_stop())
        await controller._run_idle()

        # Should NOT transition to CONNECTING
        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.WakeWordDetector")
    async def test_display_shows_listening(self, MockDetector: MagicMock) -> None:
        mock_det = MagicMock()

        async def fake_start(callback):
            await callback()

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        display = StubDisplayOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(), StubAudioOutput(), display=display
        )
        controller._running = True
        controller._stop_event = asyncio.Event()

        await controller._run_idle()
        assert display.last_status == "listening"


# ---------------------------------------------------------------------------
# CONNECTING state
# ---------------------------------------------------------------------------


class TestRobotControllerConnecting:
    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_successful_connection(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock()
        mock_session.is_connected = True
        MockSession.return_value = mock_session

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._state = RobotState.CONNECTING

        await controller._run_connecting()
        assert controller.state == RobotState.CONVERSATION
        mock_session.connect.assert_called_once()

    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_connection_failure_returns_to_idle(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock(side_effect=ConnectionError("refused"))
        MockSession.return_value = mock_session

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._state = RobotState.CONNECTING

        await controller._run_connecting()
        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_session_config_from_personality(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock()
        MockSession.return_value = mock_session

        settings = _make_settings(default_personality="professional")
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._state = RobotState.CONNECTING

        await controller._run_connecting()

        call_kwargs = MockSession.call_args[1]
        assert call_kwargs["config"].voice == "Kore"
        assert call_kwargs["api_key"] == "test-key"

    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_missing_personality_uses_default(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock()
        MockSession.return_value = mock_session

        settings = _make_settings(default_personality="nonexistent")
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._state = RobotState.CONNECTING

        await controller._run_connecting()
        # Should fall back to "friendly" and still connect
        assert controller.state == RobotState.CONVERSATION

    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_display_shows_connecting(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock()
        MockSession.return_value = mock_session

        display = StubDisplayOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(), StubAudioOutput(), display=display
        )
        controller._running = True
        controller._state = RobotState.CONNECTING

        await controller._run_connecting()
        assert display.last_status == "connecting"


# ---------------------------------------------------------------------------
# CONVERSATION state
# ---------------------------------------------------------------------------


def _mock_session_with_messages(messages: list[ServerMessage]) -> AsyncMock:
    """Create a mock GeminiSession that yields the given messages."""
    mock = AsyncMock()
    mock.is_connected = True
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    mock.send_audio = AsyncMock()
    mock.send_tool_response = AsyncMock()

    async def mock_receive():
        for msg in messages:
            yield msg

    mock.receive = mock_receive
    return mock


class TestRobotControllerConversation:
    @patch("src.core.controller.WakeWordDetector")
    async def test_audio_plays_through_speaker(
        self, MockDetector: MagicMock
    ) -> None:
        audio_out = StubAudioOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), audio_out
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="audio", audio_data=b"\xab" * 200),
            ServerMessage(type="turn_complete"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert controller.state == RobotState.IDLE
        assert len(audio_out.get_recorded_data()) == 200

    @patch("src.core.controller.WakeWordDetector")
    async def test_transcription_shown_on_display(
        self, MockDetector: MagicMock
    ) -> None:
        display = StubDisplayOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput(), display=display
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="transcription", text="Hello!"),
            ServerMessage(type="turn_complete"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert display.last_text == "Hello!"

    @patch("src.core.controller.WakeWordDetector")
    async def test_input_transcription_shown_on_display(
        self, MockDetector: MagicMock
    ) -> None:
        display = StubDisplayOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput(), display=display
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="input_transcription", text="User said hi"),
            ServerMessage(type="turn_complete"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert display.last_text == "> User said hi"

    @patch("src.core.controller.WakeWordDetector")
    async def test_error_ends_conversation(
        self, MockDetector: MagicMock
    ) -> None:
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput()
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="error", text="WebSocket closed"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.WakeWordDetector")
    async def test_go_away_ends_conversation(
        self, MockDetector: MagicMock
    ) -> None:
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput()
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="go_away"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.WakeWordDetector")
    async def test_tool_call_unknown_tool_sends_error(
        self, MockDetector: MagicMock
    ) -> None:
        settings = _make_settings()
        mock_session = _mock_session_with_messages([
            ServerMessage(
                type="tool_call",
                tool_call_id="c1",
                tool_name="nonexistent_tool",
                tool_args={"text": "hi"},
            ),
            ServerMessage(type="turn_complete"),
        ])

        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput()
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = mock_session
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        mock_session.send_tool_response.assert_called_once_with(
            "c1", {"error": "Unknown tool: nonexistent_tool"}
        )

    @patch("src.core.controller.WakeWordDetector")
    async def test_tool_call_executes_registered_tool(
        self, MockDetector: MagicMock
    ) -> None:
        display = StubDisplayOutput()
        settings = _make_settings()
        mock_session = _mock_session_with_messages([
            ServerMessage(
                type="tool_call",
                tool_call_id="c2",
                tool_name="display_text",
                tool_args={"text": "Hello from Gemini"},
            ),
            ServerMessage(type="turn_complete"),
        ])

        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput(),
            display=display,
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = mock_session
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        # Display tool executed
        assert display.last_text == "Hello from Gemini"
        # Response sent back to Gemini
        mock_session.send_tool_response.assert_called_once_with(
            "c2", {"status": "ok", "text": "Hello from Gemini"}
        )

    @patch("src.core.controller.WakeWordDetector")
    async def test_silence_timeout_ends_conversation(
        self, MockDetector: MagicMock
    ) -> None:
        """A very short timeout should end the conversation quickly."""
        mock_session = AsyncMock()
        mock_session.is_connected = True
        mock_session.close = AsyncMock()
        mock_session.send_audio = AsyncMock()

        async def slow_receive():
            yield ServerMessage(type="setup_complete")
            # Hang for longer than the timeout
            await asyncio.sleep(10)
            yield ServerMessage(type="audio", audio_data=b"\x00")

        mock_session.receive = slow_receive

        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput()
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = mock_session
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 0.1  # 100ms

        await controller._run_conversation()

        assert controller.state == RobotState.IDLE

    @patch("src.core.controller.WakeWordDetector")
    async def test_session_closed_after_conversation(
        self, MockDetector: MagicMock
    ) -> None:
        mock_session = _mock_session_with_messages([
            ServerMessage(type="turn_complete"),
        ])

        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput()
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = mock_session
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        mock_session.close.assert_called_once()
        assert controller._session is None

    @patch("src.core.controller.WakeWordDetector")
    async def test_display_shows_conversation(
        self, MockDetector: MagicMock
    ) -> None:
        display = StubDisplayOutput()
        settings = _make_settings()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), StubAudioOutput(), display=display
        )
        controller._running = True
        controller._stop_event = asyncio.Event()
        controller._session = _mock_session_with_messages([
            ServerMessage(type="turn_complete"),
        ])
        controller._state = RobotState.CONVERSATION
        controller._conversation_timeout = 30

        await controller._run_conversation()

        assert display.last_status == "conversation"


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


class TestRobotControllerLifecycle:
    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_full_cycle_idle_to_conversation_to_idle(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        """Full cycle: wake word → connect → conversation → idle → stop."""
        # Configure wake word detector to fire immediately
        mock_det = MagicMock()
        call_count = 0

        async def fake_start(callback):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await callback()  # First call: fire wake word
            # Second call: don't fire (will be stopped externally)

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        # Configure Gemini session
        mock_session = AsyncMock()
        mock_session.is_connected = True
        mock_session.connect = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.send_audio = AsyncMock()

        async def mock_receive():
            yield ServerMessage(type="setup_complete")
            yield ServerMessage(type="audio", audio_data=b"\x00" * 48)
            yield ServerMessage(type="turn_complete")

        mock_session.receive = mock_receive
        MockSession.return_value = mock_session

        settings = _make_settings()
        audio_out = StubAudioOutput()
        controller = RobotController(
            settings, StubAudioInput(TEST_WAV), audio_out
        )

        # Run controller with a delayed stop
        async def delayed_stop():
            # Wait for conversation to end and IDLE to be re-entered
            while controller.state != RobotState.IDLE or call_count < 2:
                await asyncio.sleep(0.02)
            await controller.stop()

        stop_task = asyncio.create_task(delayed_stop())
        await controller.start()
        await stop_task

        assert controller.state == RobotState.SHUTTING_DOWN
        assert len(audio_out.get_recorded_data()) == 48

    @patch("src.core.controller.WakeWordDetector")
    async def test_stop_immediately(self, MockDetector: MagicMock) -> None:
        """Calling stop() immediately should exit cleanly."""
        mock_det = MagicMock()

        async def fake_start(callback):
            pass

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())

        async def immediate_stop():
            await asyncio.sleep(0.02)
            await controller.stop()

        asyncio.create_task(immediate_stop())
        await controller.start()

        assert controller.state == RobotState.SHUTTING_DOWN

    @patch("src.core.controller.GeminiSession")
    @patch("src.core.controller.WakeWordDetector")
    async def test_connection_failure_retries_idle(
        self, MockDetector: MagicMock, MockSession: MagicMock
    ) -> None:
        """If connection fails, robot should go back to IDLE."""
        call_count = 0
        mock_det = MagicMock()

        async def fake_start(callback):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                await callback()  # Keep triggering wake word

        mock_det.start = fake_start
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        # Session always fails
        mock_session = AsyncMock()
        mock_session.connect = AsyncMock(side_effect=ConnectionError("fail"))
        MockSession.return_value = mock_session

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())

        async def delayed_stop():
            while call_count < 2:
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.05)
            await controller.stop()

        asyncio.create_task(delayed_stop())
        await controller.start()

        assert controller.state == RobotState.SHUTTING_DOWN
        assert call_count >= 2  # Retried at least once


# ---------------------------------------------------------------------------
# Shutdown and cleanup
# ---------------------------------------------------------------------------


class TestRobotControllerShutdown:
    @patch("src.core.controller.WakeWordDetector")
    async def test_cleanup_closes_resources(self, MockDetector: MagicMock) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        audio_in.open_stream(sample_rate=16000, chunk_size=1024)
        audio_out = StubAudioOutput()
        audio_out.open_stream(sample_rate=24000)
        display = StubDisplayOutput()
        display.show_text("something")

        settings = _make_settings()
        controller = RobotController(
            settings, audio_in, audio_out, display=display
        )

        await controller._cleanup()

        assert not audio_in.is_open()
        assert not audio_out.is_open()
        assert display.last_text == ""

    @patch("src.core.controller.WakeWordDetector")
    async def test_stop_sets_flags(self, MockDetector: MagicMock) -> None:
        mock_det = MagicMock()
        mock_det.stop = MagicMock()
        MockDetector.return_value = mock_det

        settings = _make_settings()
        controller = RobotController(settings, StubAudioInput(), StubAudioOutput())
        controller._running = True
        controller._stop_event = asyncio.Event()

        await controller.stop()

        assert not controller._running
        assert controller._stop_event.is_set()
        mock_det.stop.assert_called()
