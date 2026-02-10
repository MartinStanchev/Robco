"""Audio playback pipeline — plays Gemini audio through the speaker.

Receives PCM audio chunks, buffers them to prevent stuttering,
and plays through an AudioOutput interface. Supports interruption.
"""

from __future__ import annotations

import asyncio
import logging
import wave
from pathlib import Path

from src.hardware.interfaces import AudioOutput

logger = logging.getLogger(__name__)


class AudioPlaybackStream:
    """Plays PCM audio chunks through AudioOutput with buffering.

    Buffers a configurable number of chunks before starting playback
    to prevent stuttering. Supports immediate interruption when the
    user starts speaking.

    Args:
        audio_output: Hardware audio output interface.
        sample_rate: Audio sample rate in Hz.
        buffer_chunks: Number of chunks to buffer before starting playback.
    """

    def __init__(
        self,
        audio_output: AudioOutput,
        sample_rate: int = 24000,
        buffer_chunks: int = 3,
    ) -> None:
        self._audio_output = audio_output
        self._sample_rate = sample_rate
        self._buffer_chunks = buffer_chunks
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._playing = False
        self._task: asyncio.Task | None = None

    async def play_chunk(self, audio_data: bytes) -> None:
        """Buffer and play a chunk of PCM audio.

        On the first call, opens the audio output stream and starts
        a background drain task. Initial chunks are buffered before
        playback begins.

        Args:
            audio_data: Raw PCM audio bytes (24kHz/16-bit/mono).
        """
        if not self._playing:
            if not self._audio_output.is_open():
                self._audio_output.open_stream(sample_rate=self._sample_rate)
            self._playing = True
            self._task = asyncio.create_task(self._drain_loop())

        await self._queue.put(audio_data)

    async def flush(self) -> None:
        """Signal end of audio stream and wait for playback to finish."""
        if self._task is not None and not self._task.done():
            await self._queue.put(None)
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def play_file(self, file_path: str) -> None:
        """Play a local WAV file (for cached error phrases).

        Args:
            file_path: Path to a WAV file.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("Audio file not found: %s", file_path)
            return

        with wave.open(str(path), "rb") as wf:
            sample_rate = wf.getframerate()
            pcm_data = wf.readframes(wf.getnframes())

        if not self._audio_output.is_open():
            self._audio_output.open_stream(sample_rate=sample_rate)

        self._playing = True
        loop = asyncio.get_event_loop()
        chunk_bytes = max(sample_rate * 2 // 10, 1024)
        for i in range(0, len(pcm_data), chunk_bytes):
            if not self._playing:
                break
            chunk = pcm_data[i : i + chunk_bytes]
            await loop.run_in_executor(
                None, self._audio_output.write_chunk, chunk
            )
        self._playing = False

    def stop(self) -> None:
        """Immediately stop playback (for interruption)."""
        self._playing = False
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._audio_output.is_open():
            self._audio_output.stop()
        logger.info("Audio playback stopped.")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently being played."""
        return self._playing

    async def _drain_loop(self) -> None:
        """Drain buffered audio chunks to the output.

        Waits for buffer_chunks to accumulate before writing any audio,
        then continuously writes chunks as they arrive.
        """
        loop = asyncio.get_event_loop()
        try:
            # Phase 1: initial buffering
            initial: list[bytes] = []
            for _ in range(self._buffer_chunks):
                try:
                    chunk = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    break
                if chunk is None:
                    break
                initial.append(chunk)

            # Phase 2: play buffered chunks
            for chunk in initial:
                if not self._playing:
                    return
                await loop.run_in_executor(
                    None, self._audio_output.write_chunk, chunk
                )

            # Phase 3: continue draining as chunks arrive
            while self._playing:
                try:
                    chunk = await asyncio.wait_for(
                        self._queue.get(), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    break
                if chunk is None:
                    break
                if not self._playing:
                    return
                await loop.run_in_executor(
                    None, self._audio_output.write_chunk, chunk
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Playback drain error: %s", e)
        finally:
            self._playing = False
