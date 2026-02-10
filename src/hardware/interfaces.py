"""Abstract hardware interfaces for the Robco voice robot.

All robot code that touches microphones, speakers, displays, or cameras
must go through these interfaces. Hardware-specific implementations live
in src/hardware/impl/ — never import hardware libraries outside of that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AudioInput(ABC):
    """Abstract microphone input."""

    @abstractmethod
    def open_stream(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
    ) -> None:
        """Open the audio input stream.

        Args:
            sample_rate: Sample rate in Hz.
            channels: Number of audio channels (1 = mono).
            chunk_size: Number of bytes per chunk.
        """
        ...

    @abstractmethod
    def read_chunk(self) -> bytes:
        """Read one chunk of PCM audio data.

        Returns:
            Raw PCM audio bytes (16-bit little-endian).

        Raises:
            RuntimeError: If the stream is not open.
        """
        ...

    @abstractmethod
    def close_stream(self) -> None:
        """Close the audio input stream."""
        ...

    @abstractmethod
    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        ...


class AudioOutput(ABC):
    """Abstract speaker output."""

    @abstractmethod
    def open_stream(self, sample_rate: int = 24000, channels: int = 1) -> None:
        """Open the audio output stream.

        Args:
            sample_rate: Sample rate in Hz.
            channels: Number of audio channels (1 = mono).
        """
        ...

    @abstractmethod
    def write_chunk(self, data: bytes) -> None:
        """Write one chunk of PCM audio data to the speaker.

        Args:
            data: Raw PCM audio bytes (16-bit little-endian).

        Raises:
            RuntimeError: If the stream is not open.
        """
        ...

    @abstractmethod
    def close_stream(self) -> None:
        """Close the audio output stream."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Immediately stop playback and close the stream."""
        ...

    @abstractmethod
    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        ...


class DisplayOutput(ABC):
    """Abstract display/screen output."""

    @abstractmethod
    def show_text(self, text: str) -> None:
        """Display text on the screen.

        Args:
            text: Text content to display.
        """
        ...

    @abstractmethod
    def show_status(self, status: str) -> None:
        """Display a status indicator.

        Args:
            status: Status string (e.g., "listening", "thinking").
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        ...


class CameraInput(ABC):
    """Abstract camera input."""

    @abstractmethod
    def capture_frame(self) -> bytes:
        """Capture a single frame as JPEG bytes.

        Returns:
            JPEG-encoded image bytes.

        Raises:
            RuntimeError: If the camera is not available.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if camera hardware is available."""
        ...
