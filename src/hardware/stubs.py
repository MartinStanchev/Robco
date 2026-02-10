"""Desktop stub implementations for hardware interfaces.

These stubs enable development and testing without real hardware:
- StubAudioInput: reads PCM data from a WAV file
- StubAudioOutput: writes PCM data to a WAV file
- StubDisplayOutput: prints to terminal
- StubCameraInput: returns a static test JPEG
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from src.hardware.interfaces import AudioInput, AudioOutput, CameraInput, DisplayOutput


class StubAudioInput(AudioInput):
    """Reads PCM audio from a WAV file, looping if necessary.

    Args:
        wav_path: Path to a WAV file to read from. If None, generates silence.
    """

    def __init__(self, wav_path: Path | None = None) -> None:
        self._wav_path = wav_path
        self._stream_open = False
        self._sample_rate = 16000
        self._channels = 1
        self._chunk_size = 1024
        self._wav_file: wave.Wave_read | None = None
        self._pcm_data: bytes = b""
        self._read_pos = 0

    def open_stream(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
    ) -> None:
        """Open the audio input stream."""
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._read_pos = 0

        if self._wav_path and self._wav_path.exists():
            wf = wave.open(str(self._wav_path), "rb")
            self._pcm_data = wf.readframes(wf.getnframes())
            wf.close()
        else:
            # Generate 1 second of silence
            num_samples = sample_rate
            self._pcm_data = struct.pack(f"<{num_samples}h", *([0] * num_samples))

        self._stream_open = True

    def read_chunk(self) -> bytes:
        """Read one chunk of PCM audio, looping at end of data."""
        if not self._stream_open:
            raise RuntimeError("Audio input stream is not open.")

        end = self._read_pos + self._chunk_size
        if end <= len(self._pcm_data):
            chunk = self._pcm_data[self._read_pos:end]
        else:
            # Wrap around
            chunk = self._pcm_data[self._read_pos:]
            remaining = self._chunk_size - len(chunk)
            self._read_pos = 0
            chunk += self._pcm_data[:remaining]
            end = remaining

        self._read_pos = end
        return chunk

    def close_stream(self) -> None:
        """Close the audio input stream."""
        self._stream_open = False
        self._read_pos = 0

    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        return self._stream_open


class StubAudioOutput(AudioOutput):
    """Writes PCM audio to a WAV file or to an in-memory buffer.

    Args:
        output_path: Path to write output WAV file. If None, stores in memory.
    """

    def __init__(self, output_path: Path | None = None) -> None:
        self._output_path = output_path
        self._stream_open = False
        self._sample_rate = 24000
        self._channels = 1
        self._chunks: list[bytes] = []

    def open_stream(self, sample_rate: int = 24000, channels: int = 1) -> None:
        """Open the audio output stream."""
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunks = []
        self._stream_open = True

    def write_chunk(self, data: bytes) -> None:
        """Write one chunk of PCM audio data."""
        if not self._stream_open:
            raise RuntimeError("Audio output stream is not open.")
        self._chunks.append(data)

    def close_stream(self) -> None:
        """Close the stream and write to file if configured."""
        if self._stream_open and self._output_path and self._chunks:
            self._write_wav()
        self._stream_open = False

    def stop(self) -> None:
        """Immediately stop playback and close the stream."""
        self._stream_open = False

    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        return self._stream_open

    def get_recorded_data(self) -> bytes:
        """Return all recorded PCM data (for testing).

        Returns:
            Concatenated PCM bytes from all written chunks.
        """
        return b"".join(self._chunks)

    def _write_wav(self) -> None:
        """Write accumulated chunks to a WAV file."""
        pcm_data = b"".join(self._chunks)
        with wave.open(str(self._output_path), "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm_data)


class StubDisplayOutput(DisplayOutput):
    """Prints display content to the terminal.

    Also stores the last displayed text/status for testing.
    """

    def __init__(self) -> None:
        self.last_text: str = ""
        self.last_status: str = ""

    def show_text(self, text: str) -> None:
        """Display text on the screen (prints to terminal)."""
        self.last_text = text
        print(f"[DISPLAY] {text}")

    def show_status(self, status: str) -> None:
        """Display a status indicator (prints to terminal)."""
        self.last_status = status
        print(f"[STATUS] {status}")

    def clear(self) -> None:
        """Clear the display."""
        self.last_text = ""
        self.last_status = ""
        print("[DISPLAY] <cleared>")


class StubCameraInput(CameraInput):
    """Returns a static test JPEG image.

    Args:
        image_path: Path to a JPEG file. If None, returns a minimal JPEG placeholder.
    """

    def __init__(self, image_path: Path | None = None) -> None:
        self._image_path = image_path

    def capture_frame(self) -> bytes:
        """Capture a single frame as JPEG bytes."""
        if self._image_path and self._image_path.exists():
            return self._image_path.read_bytes()

        # Return minimal JPEG: just SOI + EOI markers as a placeholder
        # Real implementations return actual camera frames
        return b"\xff\xd8\xff\xd9"

    def is_available(self) -> bool:
        """Check if camera hardware is available."""
        return True
