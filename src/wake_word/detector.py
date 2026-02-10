"""Wake word detection using OpenWakeWord.

Wraps the OpenWakeWord library to provide always-on wake word detection
from an AudioInput stream. Fires an async callback when the wake word
is detected.

Note: The default wake word "hey robot" requires a custom-trained model.
For development, use a built-in model like "hey_jarvis" or provide a
path to a custom .tflite/.onnx model file.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import numpy as np
from openwakeword.model import Model as OWWModel

from src.hardware.interfaces import AudioInput

logger = logging.getLogger(__name__)

# OpenWakeWord processes audio in 1280-sample frames (80ms at 16kHz).
# Each sample is 2 bytes (int16), so 1280 samples = 2560 bytes.
_OWW_FRAME_BYTES = 1280 * 2


class WakeWordDetector:
    """Detects a wake word from audio input using OpenWakeWord.

    Args:
        audio_input: Hardware audio input interface.
        wake_word: Wake word model name or path to a custom model file.
        sensitivity: Detection sensitivity threshold (0.0-1.0).
    """

    def __init__(
        self,
        audio_input: AudioInput,
        wake_word: str = "hey_jarvis",
        sensitivity: float = 0.5,
    ) -> None:
        self._audio_input = audio_input
        self._wake_word = wake_word
        self._sensitivity = sensitivity
        self._listening = False
        self._paused = False
        self._task: asyncio.Task | None = None
        self._model: OWWModel | None = None

    async def start(self, on_detected: Callable[[], Awaitable[None]]) -> None:
        """Begin listening for the wake word.

        Opens the audio input stream and starts an async detection loop.
        Calls on_detected() when the wake word is detected.

        Args:
            on_detected: Async callback fired when wake word is detected.
        """
        if self._listening:
            return

        self._model = OWWModel(wakeword_models=[self._wake_word])

        if not self._audio_input.is_open():
            self._audio_input.open_stream(
                sample_rate=16000, channels=1, chunk_size=1024
            )
        self._listening = True
        self._paused = False
        self._task = asyncio.create_task(self._detection_loop(on_detected))
        logger.info(
            "Wake word detector started (word=%s, sensitivity=%.2f)",
            self._wake_word,
            self._sensitivity,
        )

    def stop(self) -> None:
        """Stop listening for the wake word."""
        self._listening = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._audio_input.is_open():
            self._audio_input.close_stream()
        self._model = None
        logger.info("Wake word detector stopped.")

    def pause(self) -> None:
        """Temporarily pause detection (during active Gemini session)."""
        self._paused = True
        if self._model is not None:
            self._model.reset()
        logger.debug("Wake word detection paused.")

    def resume(self) -> None:
        """Resume detection after pause."""
        self._paused = False
        if self._model is not None:
            self._model.reset()
        logger.debug("Wake word detection resumed.")

    @property
    def is_listening(self) -> bool:
        """Check if the detector is actively listening (not paused)."""
        return self._listening and not self._paused

    async def _detection_loop(
        self, on_detected: Callable[[], Awaitable[None]]
    ) -> None:
        """Main detection loop — reads audio, feeds to OWW, fires callback."""
        loop = asyncio.get_event_loop()
        audio_buffer = b""

        try:
            while self._listening:
                chunk = await loop.run_in_executor(
                    None, self._audio_input.read_chunk
                )

                if self._paused:
                    await asyncio.sleep(0.01)
                    continue

                # Accumulate audio until we have enough for an OWW frame
                audio_buffer += chunk
                if len(audio_buffer) < _OWW_FRAME_BYTES:
                    continue

                # Extract one frame and keep remainder
                frame_data = audio_buffer[:_OWW_FRAME_BYTES]
                audio_buffer = audio_buffer[_OWW_FRAME_BYTES:]

                audio_array = np.frombuffer(frame_data, dtype=np.int16)

                predictions = await loop.run_in_executor(
                    None, self._model.predict, audio_array
                )

                for model_name, score in predictions.items():
                    if score >= self._sensitivity:
                        logger.info(
                            "Wake word detected! model=%s score=%.4f",
                            model_name,
                            score,
                        )
                        await on_detected()
                        # Reset after detection to prevent rapid re-triggers
                        self._model.reset()
                        audio_buffer = b""
                        break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Wake word detection error: %s", e)
        finally:
            self._listening = False
