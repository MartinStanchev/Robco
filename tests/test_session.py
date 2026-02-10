"""Tests for the Gemini Live API session manager (Task 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.gemini.session import GeminiSession, GeminiSessionConfig, ServerMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_message(**kwargs):
    """Create a mock LiveServerMessage with explicit field values.

    All fields default to None/False so that truthiness checks
    in _parse_message behave correctly.
    """
    msg = MagicMock()
    msg.setup_complete = kwargs.get("setup_complete", None)
    msg.server_content = kwargs.get("server_content", None)
    msg.tool_call = kwargs.get("tool_call", None)
    msg.tool_call_cancellation = kwargs.get("tool_call_cancellation", None)
    msg.go_away = kwargs.get("go_away", None)
    return msg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_config() -> GeminiSessionConfig:
    return GeminiSessionConfig(
        model="gemini-2.5-flash-preview-native-audio-dialog",
        voice="Achird",
        system_prompt="You are a test robot.",
        tools=[],
        vad_sensitivity="MEDIUM",
    )


@pytest.fixture
def mock_sdk_session():
    """Mock of the google-genai AsyncSession returned by connect()."""
    session = AsyncMock()
    session.send_realtime_input = AsyncMock()
    session.send_tool_response = AsyncMock()
    return session


@pytest.fixture
def mock_client(mock_sdk_session):
    """Mock genai.Client whose aio.live.connect() yields mock_sdk_session."""
    client = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_sdk_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    client.aio.live.connect = MagicMock(return_value=cm)
    return client


# ---------------------------------------------------------------------------
# GeminiSessionConfig
# ---------------------------------------------------------------------------

class TestGeminiSessionConfig:
    def test_creates_config(self) -> None:
        config = GeminiSessionConfig(
            model="test-model", voice="Puck", system_prompt="test"
        )
        assert config.model == "test-model"
        assert config.voice == "Puck"
        assert config.vad_sensitivity == "MEDIUM"

    def test_config_with_all_fields(self) -> None:
        config = GeminiSessionConfig(
            model="m", voice="Kore", system_prompt="p",
            tools=["tool1"], vad_sensitivity="HIGH",
        )
        assert config.tools == ["tool1"]
        assert config.vad_sensitivity == "HIGH"


# ---------------------------------------------------------------------------
# ServerMessage
# ---------------------------------------------------------------------------

class TestServerMessage:
    def test_audio_message(self) -> None:
        msg = ServerMessage(type="audio", audio_data=b"\x00" * 100)
        assert msg.type == "audio"
        assert len(msg.audio_data) == 100

    def test_tool_call_message(self) -> None:
        msg = ServerMessage(
            type="tool_call",
            tool_call_id="call_123",
            tool_name="display_text",
            tool_args={"text": "hello"},
        )
        assert msg.tool_call_id == "call_123"
        assert msg.tool_args == {"text": "hello"}

    def test_defaults(self) -> None:
        msg = ServerMessage(type="turn_complete")
        assert msg.audio_data == b""
        assert msg.text == ""
        assert msg.tool_call_id == ""
        assert msg.tool_args == {}


# ---------------------------------------------------------------------------
# GeminiSession — connection lifecycle
# ---------------------------------------------------------------------------

class TestGeminiSessionLifecycle:
    async def test_connect(self, session_config, mock_client) -> None:
        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            assert not session.is_connected
            await session.connect()
            assert session.is_connected

    async def test_close(self, session_config, mock_client) -> None:
        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            assert session.is_connected
            await session.close()
            assert not session.is_connected

    async def test_close_when_not_connected(self, session_config) -> None:
        session = GeminiSession(api_key="test-key", config=session_config)
        await session.close()  # Should not raise
        assert not session.is_connected

    async def test_connect_passes_config(self, session_config, mock_client) -> None:
        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            mock_client.aio.live.connect.assert_called_once()
            call_kwargs = mock_client.aio.live.connect.call_args[1]
            assert call_kwargs["model"] == session_config.model


# ---------------------------------------------------------------------------
# GeminiSession — send_audio
# ---------------------------------------------------------------------------

class TestGeminiSessionSendAudio:
    async def test_send_audio(self, session_config, mock_client, mock_sdk_session) -> None:
        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            await session.send_audio(b"\x00" * 1024)
            mock_sdk_session.send_realtime_input.assert_called_once()

    async def test_send_audio_not_connected_raises(self, session_config) -> None:
        session = GeminiSession(api_key="test-key", config=session_config)
        with pytest.raises(RuntimeError, match="not connected"):
            await session.send_audio(b"\x00" * 1024)


# ---------------------------------------------------------------------------
# GeminiSession — send_tool_response
# ---------------------------------------------------------------------------

class TestGeminiSessionToolResponse:
    async def test_send_tool_response(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()

            # Simulate receiving a tool call first (stores name mapping)
            fc = MagicMock()
            fc.id = "call_1"
            fc.name = "test_tool"
            fc.args = {}
            tc_msg = _make_mock_message(
                tool_call=MagicMock(function_calls=[fc])
            )
            session._parse_message(tc_msg)

            await session.send_tool_response("call_1", {"result": "ok"})
            mock_sdk_session.send_tool_response.assert_called_once()

    async def test_send_tool_response_not_connected_raises(self, session_config) -> None:
        session = GeminiSession(api_key="test-key", config=session_config)
        with pytest.raises(RuntimeError, match="not connected"):
            await session.send_tool_response("id", {})


# ---------------------------------------------------------------------------
# GeminiSession — receive
# ---------------------------------------------------------------------------

class TestGeminiSessionReceive:
    async def test_receive_not_connected_raises(self, session_config) -> None:
        session = GeminiSession(api_key="test-key", config=session_config)
        with pytest.raises(RuntimeError, match="not connected"):
            async for _ in session.receive():
                pass

    async def test_receive_setup_complete(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        msg = _make_mock_message(setup_complete=MagicMock())

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "setup_complete"

    async def test_receive_audio(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        part = MagicMock()
        part.inline_data = MagicMock()
        part.inline_data.data = b"\x00" * 2400
        part.text = None

        sc = MagicMock()
        sc.model_turn = MagicMock(parts=[part])
        sc.output_transcription = None
        sc.input_transcription = None
        sc.interrupted = False
        sc.turn_complete = False

        msg = _make_mock_message(server_content=sc)

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "audio"
        assert len(messages[0].audio_data) == 2400

    async def test_receive_transcription(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        sc = MagicMock()
        sc.model_turn = None
        sc.output_transcription = MagicMock(text="Hello world")
        sc.input_transcription = None
        sc.interrupted = False
        sc.turn_complete = False

        msg = _make_mock_message(server_content=sc)

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "transcription"
        assert messages[0].text == "Hello world"

    async def test_receive_input_transcription(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        sc = MagicMock()
        sc.model_turn = None
        sc.output_transcription = None
        sc.input_transcription = MagicMock(text="User said this")
        sc.interrupted = False
        sc.turn_complete = False

        msg = _make_mock_message(server_content=sc)

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "input_transcription"
        assert messages[0].text == "User said this"

    async def test_receive_turn_complete(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        sc = MagicMock()
        sc.model_turn = None
        sc.output_transcription = None
        sc.input_transcription = None
        sc.interrupted = False
        sc.turn_complete = True

        msg = _make_mock_message(server_content=sc)

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert any(m.type == "turn_complete" for m in messages)

    async def test_receive_interrupted(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        sc = MagicMock()
        sc.model_turn = None
        sc.output_transcription = None
        sc.input_transcription = None
        sc.interrupted = True
        sc.turn_complete = False

        msg = _make_mock_message(server_content=sc)

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert any(m.type == "interrupted" for m in messages)

    async def test_receive_tool_call(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        fc = MagicMock()
        fc.id = "call_42"
        fc.name = "display_text"
        fc.args = {"text": "hello world"}

        msg = _make_mock_message(
            tool_call=MagicMock(function_calls=[fc])
        )

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "tool_call"
        assert messages[0].tool_name == "display_text"
        assert messages[0].tool_call_id == "call_42"
        assert messages[0].tool_args == {"text": "hello world"}

    async def test_receive_go_away(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        msg = _make_mock_message(go_away=MagicMock())

        async def mock_receive():
            yield msg

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert any(m.type == "go_away" for m in messages)

    async def test_receive_error_yields_error_message(
        self, session_config, mock_client, mock_sdk_session
    ) -> None:
        async def mock_receive():
            raise ConnectionError("WebSocket closed")
            yield  # pragma: no cover — makes this an async generator

        mock_sdk_session.receive = mock_receive

        with patch("src.gemini.session.genai.Client", return_value=mock_client):
            session = GeminiSession(api_key="test-key", config=session_config)
            await session.connect()
            messages = [m async for m in session.receive()]

        assert len(messages) == 1
        assert messages[0].type == "error"
        assert "WebSocket closed" in messages[0].text
        assert not session.is_connected


# ---------------------------------------------------------------------------
# GeminiSession — _parse_message
# ---------------------------------------------------------------------------

class TestParseMessage:
    def test_empty_message_returns_empty(self, session_config) -> None:
        session = GeminiSession(api_key="k", config=session_config)
        msg = _make_mock_message()
        assert session._parse_message(msg) == []

    def test_multiple_audio_parts(self, session_config) -> None:
        part1 = MagicMock()
        part1.inline_data = MagicMock(data=b"\x01" * 100)
        part1.text = None

        part2 = MagicMock()
        part2.inline_data = MagicMock(data=b"\x02" * 200)
        part2.text = None

        sc = MagicMock()
        sc.model_turn = MagicMock(parts=[part1, part2])
        sc.output_transcription = None
        sc.input_transcription = None
        sc.interrupted = False
        sc.turn_complete = False

        session = GeminiSession(api_key="k", config=session_config)
        results = session._parse_message(_make_mock_message(server_content=sc))

        audio_msgs = [r for r in results if r.type == "audio"]
        assert len(audio_msgs) == 2
        assert len(audio_msgs[0].audio_data) == 100
        assert len(audio_msgs[1].audio_data) == 200

    def test_tool_call_stores_name_mapping(self, session_config) -> None:
        fc = MagicMock()
        fc.id = "c1"
        fc.name = "my_tool"
        fc.args = {"x": 1}

        msg = _make_mock_message(tool_call=MagicMock(function_calls=[fc]))

        session = GeminiSession(api_key="k", config=session_config)
        session._parse_message(msg)

        assert session._tool_call_names["c1"] == "my_tool"

    def test_tool_call_cancellation(self, session_config) -> None:
        cancel = MagicMock()
        cancel.ids = ["c1", "c2"]

        msg = _make_mock_message(tool_call_cancellation=cancel)

        session = GeminiSession(api_key="k", config=session_config)
        results = session._parse_message(msg)

        assert len(results) == 1
        assert results[0].type == "tool_call_cancellation"
        assert "c1" in results[0].text
        assert "c2" in results[0].text
