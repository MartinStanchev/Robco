"""Audio capture pipeline — streams microphone audio to Gemini.

Reads PCM chunks from an AudioInput interface and sends them
to a Gemini Live API session in an async loop.
"""

from __future__ import annotations

import asyncio
import logging

from src.gemini.session import GeminiSession
from src.hardware.interfaces import AudioInput

logger = logging.getLogger(__name__)


class AudioCaptureStream:
    """Streams PCM audio from AudioInput to a Gemini session.

    Args:
        audio_input: Hardware audio input interface.
        session: Connected Gemini session.
        sample_rate: Audio sample rate in Hz.
        chunk_size: Bytes per audio chunk.
    """

    def __init__(
        self,
        audio_input: AudioInput,
        session: GeminiSession,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
    ) -> None:
        self._audio_input = audio_input
        self._session = session
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._streaming = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Begin capturing and sending audio chunks to Gemini."""
        if self._streaming:
            return

        if not self._audio_input.is_open():
            self._audio_input.open_stream(
                sample_rate=self._sample_rate,
                chunk_size=self._chunk_size,
            )
        self._streaming = True
        self._task = asyncio.create_task(self._capture_loop())
        logger.info(
            "Audio capture started (rate=%d, chunk=%d)",
            self._sample_rate,
            self._chunk_size,
        )

    async def stop(self) -> None:
        """Stop capturing audio."""
        self._streaming = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._audio_input.is_open():
            self._audio_input.close_stream()
        logger.info("Audio capture stopped.")

    @property
    def is_streaming(self) -> bool:
        """Check if audio capture is active."""
        return self._streaming

    async def _capture_loop(self) -> None:
        """Main capture loop — reads chunks and sends to Gemini."""
        loop = asyncio.get_event_loop()
        try:
            while self._streaming:
                chunk = await loop.run_in_executor(
                    None, self._audio_input.read_chunk
                )
                if self._streaming and self._session.is_connected:
                    await self._session.send_audio(chunk)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Audio capture error: %s", e)
            self._streaming = False
