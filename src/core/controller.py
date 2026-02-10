"""Robot main controller — orchestrates the voice interaction loop.

Manages the state machine: IDLE (wake word listening) → CONNECTING
(Gemini session setup) → CONVERSATION (bidirectional audio) → IDLE.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Set

from src.audio.capture import AudioCaptureStream
from src.audio.playback import AudioPlaybackStream
from src.core.config import Settings
from src.core.state_machine import RobotState
from src.gemini.session import GeminiSession, GeminiSessionConfig, ServerMessage
from src.hardware.interfaces import AudioInput, AudioOutput, CameraInput, DisplayOutput
from src.personality.manager import PersonalityManager
from src.tools.server import ToolServer
from src.wake_word.detector import WakeWordDetector

logger = logging.getLogger(__name__)


class RobotController:
    """Orchestrates the full robot interaction as a state machine.

    Ties together wake word detection, Gemini Live API session management,
    audio capture/playback, and optional display/camera modules.

    Args:
        settings: Application settings.
        audio_input: Hardware audio input interface.
        audio_output: Hardware audio output interface.
        display: Optional display output interface.
        camera: Optional camera input interface.
    """

    def __init__(
        self,
        settings: Settings,
        audio_input: AudioInput,
        audio_output: AudioOutput,
        display: DisplayOutput | None = None,
        camera: CameraInput | None = None,
    ) -> None:
        self._settings = settings
        self._audio_input = audio_input
        self._audio_output = audio_output
        self._display = display
        self._camera = camera

        self._state = RobotState.IDLE
        self._running = False
        self._stop_event: asyncio.Event | None = None

        self._personality_manager = PersonalityManager(settings.personalities_dir)
        self._wake_detector = WakeWordDetector(
            audio_input,
            wake_word=settings.wake_word,
            sensitivity=settings.wake_word_sensitivity,
        )
        self._tool_server = ToolServer()
        self._tool_server.register_builtin_tools(display=display, camera=camera)
        self._tool_server.discover_user_tools()

        self._session: GeminiSession | None = None
        self._last_activity = 0.0
        self._conversation_timeout = settings.conversation_timeout

    async def start(self) -> None:
        """Begin the main loop (wake word → conversation → idle).

        Runs until stop() is called. Each cycle:
        1. IDLE — listen for wake word
        2. CONNECTING — open Gemini session
        3. CONVERSATION — stream audio bidirectionally
        4. Back to IDLE
        """
        self._running = True
        self._stop_event = asyncio.Event()
        self._state = RobotState.IDLE
        logger.info("Robot controller started.")

        try:
            while self._running:
                if self._state == RobotState.IDLE:
                    await self._run_idle()
                elif self._state == RobotState.CONNECTING:
                    await self._run_connecting()
                elif self._state == RobotState.CONVERSATION:
                    await self._run_conversation()
                else:
                    break
        except asyncio.CancelledError:
            logger.info("Robot controller cancelled.")
        finally:
            self._state = RobotState.SHUTTING_DOWN
            await self._cleanup()
            logger.info("Robot controller stopped.")

    async def stop(self) -> None:
        """Graceful shutdown — exits the main loop."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        self._wake_detector.stop()
        if self._session and self._session.is_connected:
            await self._session.close()

    @property
    def state(self) -> RobotState:
        """Current robot state."""
        return self._state

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _run_idle(self) -> None:
        """IDLE state — listen for wake word, wait for detection or stop."""
        if self._display:
            self._display.show_status("listening")

        wake_event = asyncio.Event()

        async def on_wake_word() -> None:
            wake_event.set()

        await self._wake_detector.start(on_wake_word)
        logger.info("Entering IDLE — listening for wake word.")

        woke = await self._wait_for_event_or_stop(wake_event)
        self._wake_detector.stop()

        if woke and self._running:
            logger.info("Wake word detected! Transitioning to CONNECTING.")
            self._state = RobotState.CONNECTING

    async def _run_connecting(self) -> None:
        """CONNECTING state — load personality and open Gemini session."""
        if self._display:
            self._display.show_status("connecting")

        logger.info("Entering CONNECTING state.")

        try:
            personality = self._personality_manager.get_personality(
                self._settings.default_personality
            )
        except KeyError:
            logger.warning(
                "Personality '%s' not found, falling back to default.",
                self._settings.default_personality,
            )
            try:
                personality = self._personality_manager.get_default()
            except KeyError:
                logger.error("No personalities available. Returning to IDLE.")
                self._state = RobotState.IDLE
                return

        config = GeminiSessionConfig(
            model=self._settings.gemini_model,
            voice=personality.voice,
            system_prompt=personality.system_prompt,
            tools=self._tool_server.get_tool_declarations() or [],
            vad_sensitivity=personality.vad_sensitivity,
        )

        self._session = GeminiSession(
            api_key=self._settings.gemini_api_key,
            config=config,
        )
        self._conversation_timeout = personality.conversation_timeout_seconds

        try:
            await self._session.connect()
            logger.info("Gemini session connected. Transitioning to CONVERSATION.")
            self._state = RobotState.CONVERSATION
        except Exception as e:
            logger.error("Failed to connect to Gemini: %s", e)
            self._session = None
            self._state = RobotState.IDLE

    async def _run_conversation(self) -> None:
        """CONVERSATION state — bidirectional audio streaming with Gemini."""
        if self._display:
            self._display.show_status("conversation")

        logger.info("Entering CONVERSATION state.")

        capture = AudioCaptureStream(
            self._audio_input,
            self._session,
            sample_rate=self._settings.input_sample_rate,
            chunk_size=self._settings.audio_chunk_size,
        )
        playback = AudioPlaybackStream(
            self._audio_output,
            sample_rate=self._settings.output_sample_rate,
        )

        await capture.start()
        self._last_activity = time.monotonic()

        receive_task = asyncio.create_task(self._receive_loop(playback))
        timeout_task = asyncio.create_task(self._timeout_monitor())

        try:
            done, pending = await asyncio.wait(
                {receive_task, timeout_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            await capture.stop()
            playback.stop()
            if self._session and self._session.is_connected:
                await self._session.close()
            self._session = None
            self._state = RobotState.IDLE
            logger.info("Conversation ended. Returning to IDLE.")

    # ------------------------------------------------------------------
    # Conversation helpers
    # ------------------------------------------------------------------

    async def _receive_loop(self, playback: AudioPlaybackStream) -> None:
        """Process incoming Gemini messages until error/disconnect."""
        try:
            async for msg in self._session.receive():
                if not self._running:
                    break
                await self._handle_message(msg, playback)
                if msg.type in ("error", "go_away"):
                    break
        except asyncio.CancelledError:
            raise

    async def _handle_message(
        self, msg: ServerMessage, playback: AudioPlaybackStream
    ) -> None:
        """Route a single Gemini message to the appropriate handler."""
        if msg.type == "audio":
            await playback.play_chunk(msg.audio_data)

        elif msg.type == "transcription":
            if self._display:
                self._display.show_text(msg.text)

        elif msg.type == "input_transcription":
            self._last_activity = time.monotonic()
            if self._display:
                self._display.show_text(f"> {msg.text}")

        elif msg.type == "turn_complete":
            self._last_activity = time.monotonic()
            await playback.flush()

        elif msg.type == "interrupted":
            playback.stop()
            self._last_activity = time.monotonic()

        elif msg.type == "tool_call":
            logger.info("Tool call: %s(%s)", msg.tool_name, msg.tool_args)
            result = await self._tool_server.execute_tool(
                msg.tool_name, msg.tool_args
            )
            self._last_activity = time.monotonic()
            if self._session and self._session.is_connected:
                await self._session.send_tool_response(msg.tool_call_id, result)

        elif msg.type == "setup_complete":
            logger.info("Gemini setup complete.")

        elif msg.type == "go_away":
            logger.warning("Gemini session ending (go_away).")

        elif msg.type == "error":
            logger.error("Gemini error: %s", msg.text)

    async def _timeout_monitor(self) -> None:
        """Watch for conversation silence timeout."""
        while self._running and self._state == RobotState.CONVERSATION:
            await asyncio.sleep(1.0)
            elapsed = time.monotonic() - self._last_activity
            if elapsed >= self._conversation_timeout:
                logger.info(
                    "Conversation timed out after %.1fs of silence.", elapsed
                )
                return

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def _wait_for_event_or_stop(self, event: asyncio.Event) -> bool:
        """Wait for an event to fire or for stop to be requested.

        Args:
            event: The event to wait for.

        Returns:
            True if the event was set, False if stop was requested.
        """
        event_task = asyncio.create_task(event.wait())
        stop_task = asyncio.create_task(self._stop_event.wait())

        done: Set[asyncio.Task] = set()
        pending: Set[asyncio.Task] = set()
        try:
            done, pending = await asyncio.wait(
                {event_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        return event_task in done

    async def _cleanup(self) -> None:
        """Release all resources during shutdown."""
        self._wake_detector.stop()
        if self._session and self._session.is_connected:
            await self._session.close()
        if self._audio_input.is_open():
            self._audio_input.close_stream()
        if self._audio_output.is_open():
            self._audio_output.stop()
        if self._display:
            self._display.clear()
        logger.info("Cleanup complete.")
