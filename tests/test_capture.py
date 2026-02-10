"""Tests for the audio capture pipeline (Task 5)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.audio.capture import AudioCaptureStream
from src.hardware.stubs import StubAudioInput

FIXTURES = Path(__file__).parent / "fixtures"
TEST_WAV = FIXTURES / "test_tone.wav"


class TestAudioCaptureStream:
    async def test_start_opens_stream(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = True

        stream = AudioCaptureStream(audio_in, session)
        assert not stream.is_streaming

        await stream.start()
        assert stream.is_streaming
        assert audio_in.is_open()

        await stream.stop()

    async def test_stop_closes_stream(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = True

        stream = AudioCaptureStream(audio_in, session)
        await stream.start()
        await stream.stop()

        assert not stream.is_streaming
        assert not audio_in.is_open()

    async def test_sends_audio_to_session(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = True
        session.send_audio = AsyncMock()

        stream = AudioCaptureStream(audio_in, session, chunk_size=1024)
        await stream.start()
        await asyncio.sleep(0.1)
        await stream.stop()

        assert session.send_audio.call_count > 0
        for call in session.send_audio.call_args_list:
            assert len(call.args[0]) == 1024

    async def test_skips_send_when_disconnected(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = False
        session.send_audio = AsyncMock()

        stream = AudioCaptureStream(audio_in, session)
        await stream.start()
        await asyncio.sleep(0.05)
        await stream.stop()

        session.send_audio.assert_not_called()

    async def test_silence_input(self) -> None:
        audio_in = StubAudioInput()  # No WAV = silence
        session = AsyncMock()
        session.is_connected = True
        session.send_audio = AsyncMock()

        stream = AudioCaptureStream(audio_in, session, chunk_size=512)
        await stream.start()
        await asyncio.sleep(0.05)
        await stream.stop()

        assert session.send_audio.call_count > 0

    async def test_does_not_reopen_already_open_stream(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        audio_in.open_stream(sample_rate=16000, chunk_size=1024)
        assert audio_in.is_open()

        session = AsyncMock()
        session.is_connected = True

        stream = AudioCaptureStream(audio_in, session)
        await stream.start()
        # Should not have closed/reopened the stream
        assert audio_in.is_open()

        await stream.stop()

    async def test_start_is_idempotent(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = True

        stream = AudioCaptureStream(audio_in, session)
        await stream.start()
        await stream.start()  # Should not create second task
        assert stream.is_streaming

        await stream.stop()

    async def test_stop_when_not_started(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        session = AsyncMock()
        session.is_connected = True

        stream = AudioCaptureStream(audio_in, session)
        await stream.stop()  # Should not raise
        assert not stream.is_streaming
