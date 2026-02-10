"""Tests for the hardware abstraction layer (Task 2)."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from src.hardware.interfaces import AudioInput, AudioOutput, CameraInput, DisplayOutput
from src.hardware.stubs import (
    StubAudioInput,
    StubAudioOutput,
    StubCameraInput,
    StubDisplayOutput,
)


FIXTURES = Path(__file__).parent / "fixtures"
TEST_WAV = FIXTURES / "test_tone.wav"
TEST_IMAGE = FIXTURES / "test_image.jpg"


class TestStubAudioInput:
    """Tests for StubAudioInput."""

    def test_implements_interface(self) -> None:
        assert issubclass(StubAudioInput, AudioInput)

    def test_open_and_close(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        assert not audio_in.is_open()
        audio_in.open_stream()
        assert audio_in.is_open()
        audio_in.close_stream()
        assert not audio_in.is_open()

    def test_read_chunk_returns_correct_size(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        audio_in.open_stream(chunk_size=1024)
        chunk = audio_in.read_chunk()
        assert len(chunk) == 1024
        audio_in.close_stream()

    def test_read_chunk_without_open_raises(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        with pytest.raises(RuntimeError, match="not open"):
            audio_in.read_chunk()

    def test_loops_at_end_of_data(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        audio_in.open_stream(chunk_size=1024)
        # test_tone.wav is 32000 bytes (16000 frames * 2 bytes)
        # Reading 32 chunks of 1024 should exhaust the file, then loop
        chunks = []
        for _ in range(33):
            chunks.append(audio_in.read_chunk())
        assert all(len(c) == 1024 for c in chunks)
        audio_in.close_stream()

    def test_generates_silence_without_file(self) -> None:
        audio_in = StubAudioInput()  # No WAV file
        audio_in.open_stream(sample_rate=16000, chunk_size=512)
        chunk = audio_in.read_chunk()
        assert len(chunk) == 512
        # Silence = all zeros
        assert chunk == b"\x00" * 512
        audio_in.close_stream()


class TestStubAudioOutput:
    """Tests for StubAudioOutput."""

    def test_implements_interface(self) -> None:
        assert issubclass(StubAudioOutput, AudioOutput)

    def test_open_and_close(self) -> None:
        audio_out = StubAudioOutput()
        assert not audio_out.is_open()
        audio_out.open_stream()
        assert audio_out.is_open()
        audio_out.close_stream()
        assert not audio_out.is_open()

    def test_write_chunk(self) -> None:
        audio_out = StubAudioOutput()
        audio_out.open_stream()
        audio_out.write_chunk(b"\x00" * 1024)
        audio_out.write_chunk(b"\xff" * 512)
        assert len(audio_out.get_recorded_data()) == 1024 + 512
        audio_out.close_stream()

    def test_write_without_open_raises(self) -> None:
        audio_out = StubAudioOutput()
        with pytest.raises(RuntimeError, match="not open"):
            audio_out.write_chunk(b"\x00" * 100)

    def test_stop_closes_stream(self) -> None:
        audio_out = StubAudioOutput()
        audio_out.open_stream()
        assert audio_out.is_open()
        audio_out.stop()
        assert not audio_out.is_open()

    def test_writes_wav_file(self, tmp_path: Path) -> None:
        output_path = tmp_path / "output.wav"
        audio_out = StubAudioOutput(output_path)
        audio_out.open_stream(sample_rate=24000)
        audio_out.write_chunk(b"\x00" * 4800)  # 0.1s of silence at 24kHz/16-bit
        audio_out.close_stream()

        assert output_path.exists()
        with wave.open(str(output_path), "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2


class TestStubDisplayOutput:
    """Tests for StubDisplayOutput."""

    def test_implements_interface(self) -> None:
        assert issubclass(StubDisplayOutput, DisplayOutput)

    def test_show_text(self) -> None:
        display = StubDisplayOutput()
        display.show_text("Hello, world!")
        assert display.last_text == "Hello, world!"

    def test_show_status(self) -> None:
        display = StubDisplayOutput()
        display.show_status("listening")
        assert display.last_status == "listening"

    def test_clear(self) -> None:
        display = StubDisplayOutput()
        display.show_text("something")
        display.show_status("active")
        display.clear()
        assert display.last_text == ""
        assert display.last_status == ""


class TestStubCameraInput:
    """Tests for StubCameraInput."""

    def test_implements_interface(self) -> None:
        assert issubclass(StubCameraInput, CameraInput)

    def test_is_available(self) -> None:
        camera = StubCameraInput()
        assert camera.is_available()

    def test_capture_returns_jpeg_bytes(self) -> None:
        camera = StubCameraInput()
        frame = camera.capture_frame()
        # JPEG starts with SOI marker
        assert frame[:2] == b"\xff\xd8"

    def test_capture_from_file(self) -> None:
        if not TEST_IMAGE.exists():
            pytest.skip("Test image fixture not available")
        camera = StubCameraInput(TEST_IMAGE)
        frame = camera.capture_frame()
        assert frame[:2] == b"\xff\xd8"
        assert len(frame) > 100  # Real JPEG is larger than placeholder
