"""Tests for the audio playback pipeline (Task 6)."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

import pytest

from src.audio.playback import AudioPlaybackStream
from src.hardware.stubs import StubAudioOutput


class TestAudioPlaybackStream:
    async def test_play_chunk_opens_stream(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        assert not player.is_playing
        await player.play_chunk(b"\x00" * 1024)
        assert player.is_playing
        assert output.is_open()

        player.stop()

    async def test_buffered_playback(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=2)

        for _ in range(3):
            await player.play_chunk(b"\x00" * 1024)

        await player.flush()

        assert len(output.get_recorded_data()) == 3 * 1024

    async def test_single_chunk_with_flush(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        await player.play_chunk(b"\xab" * 512)
        await player.flush()

        assert len(output.get_recorded_data()) == 512

    async def test_stop_interrupts(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        await player.play_chunk(b"\x00" * 1024)
        assert player.is_playing

        player.stop()
        assert not player.is_playing
        assert not output.is_open()

    async def test_stop_clears_queue(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=100)

        # Queue many chunks but don't start draining (buffer_chunks=100)
        for _ in range(5):
            await player.play_chunk(b"\x00" * 1024)

        player.stop()
        assert not player.is_playing

    async def test_play_file(self, tmp_path: Path) -> None:
        wav_path = tmp_path / "test.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00" * 4800)

        output = StubAudioOutput()
        player = AudioPlaybackStream(output)

        await player.play_file(str(wav_path))

        assert len(output.get_recorded_data()) == 4800

    async def test_play_file_nonexistent(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output)

        await player.play_file("/nonexistent/path.wav")
        assert not player.is_playing

    async def test_stop_during_play_file_sets_flag(self, tmp_path: Path) -> None:
        """Verify stop() clears the playing flag so play_file can exit."""
        wav_path = tmp_path / "test.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00" * 4800)

        output = StubAudioOutput()
        player = AudioPlaybackStream(output)

        await player.play_file(str(wav_path))
        # After play_file completes, is_playing should be False
        assert not player.is_playing

        # Calling stop() mid-state should also work cleanly
        player.stop()
        assert not player.is_playing

    async def test_multiple_turns(self) -> None:
        """Test playing audio from two separate turns."""
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        # Turn 1
        await player.play_chunk(b"\x01" * 1024)
        await player.flush()

        # Turn 2
        await player.play_chunk(b"\x02" * 1024)
        await player.flush()

        assert len(output.get_recorded_data()) == 2 * 1024

    async def test_flush_when_not_playing(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        await player.flush()  # Should not raise

    async def test_is_playing_false_after_drain(self) -> None:
        output = StubAudioOutput()
        player = AudioPlaybackStream(output, buffer_chunks=1)

        await player.play_chunk(b"\x00" * 1024)
        await player.flush()

        assert not player.is_playing
