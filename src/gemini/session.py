"""Gemini Live API session manager.

Wraps the google-genai SDK's Live API client to manage WebSocket sessions
for bidirectional audio streaming with Gemini.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


@dataclass
class GeminiSessionConfig:
    """Configuration for a Gemini Live session.

    Attributes:
        model: Gemini model name.
        voice: Gemini voice name for speech output.
        system_prompt: System instruction sent to Gemini.
        tools: Tool declarations for function calling (empty if none).
        vad_sensitivity: Voice activity detection sensitivity ("LOW", "MEDIUM", "HIGH").
    """

    model: str
    voice: str
    system_prompt: str
    tools: list = field(default_factory=list)
    vad_sensitivity: str = "MEDIUM"


@dataclass
class ServerMessage:
    """Normalized message received from Gemini.

    Attributes:
        type: Message type — "setup_complete", "audio", "transcription",
              "input_transcription", "tool_call", "turn_complete",
              "interrupted", "tool_call_cancellation", "go_away", "error".
        audio_data: PCM audio bytes (for type="audio").
        text: Transcription text or error message.
        tool_call_id: Function call ID (for type="tool_call").
        tool_name: Function name (for type="tool_call").
        tool_args: Function arguments (for type="tool_call").
    """

    type: str
    audio_data: bytes = b""
    text: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)


_VAD_SENSITIVITY_MAP = {
    "LOW": (
        types.StartSensitivity.START_SENSITIVITY_LOW,
        types.EndSensitivity.END_SENSITIVITY_LOW,
    ),
    "MEDIUM": (
        types.StartSensitivity.START_SENSITIVITY_HIGH,
        types.EndSensitivity.END_SENSITIVITY_LOW,
    ),
    "HIGH": (
        types.StartSensitivity.START_SENSITIVITY_HIGH,
        types.EndSensitivity.END_SENSITIVITY_HIGH,
    ),
}


class GeminiSession:
    """Manages a Gemini Live API WebSocket session.

    Args:
        api_key: Google API key for authentication.
        config: Session configuration.
    """

    def __init__(self, api_key: str, config: GeminiSessionConfig) -> None:
        self._api_key = api_key
        self._config = config
        self._client: genai.Client | None = None
        self._session = None
        self._session_cm = None
        self._connected = False
        self._tool_call_names: dict[str, str] = {}

    async def connect(self) -> None:
        """Open WebSocket connection and send setup message."""
        self._client = genai.Client(api_key=self._api_key)

        start_sens, end_sens = _VAD_SENSITIVITY_MAP.get(
            self._config.vad_sensitivity,
            _VAD_SENSITIVITY_MAP["MEDIUM"],
        )

        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._config.system_prompt,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._config.voice,
                    )
                ),
            ),
            tools=self._config.tools if self._config.tools else None,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=start_sens,
                    end_of_speech_sensitivity=end_sens,
                ),
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
        )

        self._session_cm = self._client.aio.live.connect(
            model=self._config.model,
            config=live_config,
        )
        self._session = await self._session_cm.__aenter__()
        self._connected = True
        logger.info(
            "Gemini session connected (model=%s, voice=%s)",
            self._config.model,
            self._config.voice,
        )

    async def send_audio(self, chunk: bytes) -> None:
        """Send a chunk of PCM audio to Gemini.

        Args:
            chunk: Raw PCM audio bytes (16kHz/16-bit/mono).

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._session is None:
            raise RuntimeError("Gemini session is not connected.")

        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"),
        )

    async def receive(self) -> AsyncIterator[ServerMessage]:
        """Yield normalized messages from Gemini.

        Yields:
            ServerMessage for each event (audio, transcription, tool call, etc.).

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._session is None:
            raise RuntimeError("Gemini session is not connected.")

        try:
            async for message in self._session.receive():
                for server_msg in self._parse_message(message):
                    yield server_msg
        except Exception as e:
            logger.error("Error receiving from Gemini: %s", e)
            yield ServerMessage(type="error", text=str(e))
            self._connected = False

    async def send_tool_response(self, call_id: str, result: dict) -> None:
        """Send the result of a function call back to Gemini.

        Args:
            call_id: The function call ID from the tool_call message.
            result: The function result as a dictionary.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._session is None:
            raise RuntimeError("Gemini session is not connected.")

        name = self._tool_call_names.pop(call_id, "")

        await self._session.send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response=result,
                )
            ]
        )

    async def close(self) -> None:
        """Close the WebSocket session gracefully."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing Gemini session: %s", e)
            finally:
                self._session = None
                self._session_cm = None
                self._connected = False
                self._tool_call_names.clear()
                logger.info("Gemini session closed.")

    @property
    def is_connected(self) -> bool:
        """Check if the session is currently connected."""
        return self._connected

    def _parse_message(self, message: types.LiveServerMessage) -> list[ServerMessage]:
        """Parse a raw SDK message into normalized ServerMessage(s).

        Args:
            message: Raw message from the Gemini SDK.

        Returns:
            List of ServerMessage objects (may be empty or multiple).
        """
        results: list[ServerMessage] = []

        if message.setup_complete:
            results.append(ServerMessage(type="setup_complete"))

        if message.server_content:
            sc = message.server_content

            if sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        results.append(ServerMessage(
                            type="audio",
                            audio_data=part.inline_data.data,
                        ))
                    if part.text:
                        results.append(ServerMessage(
                            type="transcription",
                            text=part.text,
                        ))

            if sc.output_transcription and sc.output_transcription.text:
                results.append(ServerMessage(
                    type="transcription",
                    text=sc.output_transcription.text,
                ))

            if sc.input_transcription and sc.input_transcription.text:
                results.append(ServerMessage(
                    type="input_transcription",
                    text=sc.input_transcription.text,
                ))

            if sc.interrupted:
                results.append(ServerMessage(type="interrupted"))

            if sc.turn_complete:
                results.append(ServerMessage(type="turn_complete"))

        if message.tool_call:
            for fc in message.tool_call.function_calls:
                call_id = fc.id or ""
                name = fc.name or ""
                self._tool_call_names[call_id] = name
                results.append(ServerMessage(
                    type="tool_call",
                    tool_call_id=call_id,
                    tool_name=name,
                    tool_args=fc.args or {},
                ))

        if message.tool_call_cancellation:
            ids = message.tool_call_cancellation.ids or []
            results.append(ServerMessage(
                type="tool_call_cancellation",
                text=",".join(ids),
            ))

        if message.go_away:
            results.append(ServerMessage(type="go_away"))

        return results
