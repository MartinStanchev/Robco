"""Tests for wake word detection (Task 7)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.hardware.stubs import StubAudioInput
from src.wake_word.detector import WakeWordDetector

FIXTURES = Path(__file__).parent / "fixtures"
TEST_WAV = FIXTURES / "test_tone.wav"


class TestWakeWordDetector:
    async def test_start_and_stop(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            assert detector.is_listening

            await asyncio.sleep(0.1)

            detector.stop()
            assert not detector.is_listening

    async def test_fires_callback_on_detection(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.8}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            await asyncio.sleep(0.2)
            detector.stop()

            assert callback.call_count >= 1

    async def test_no_callback_below_sensitivity(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.3}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            await asyncio.sleep(0.2)
            detector.stop()

            callback.assert_not_called()

    async def test_pause_prevents_detection(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.9}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)

            # Pause immediately
            detector.pause()
            assert not detector.is_listening

            callback.reset_mock()
            await asyncio.sleep(0.15)
            callback.assert_not_called()

            detector.stop()

    async def test_resume_after_pause(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.9}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            detector.pause()
            callback.reset_mock()

            # Resume — should detect again
            detector.resume()
            assert detector.is_listening
            await asyncio.sleep(0.15)
            detector.stop()

            assert callback.call_count >= 1

    async def test_pause_resets_model(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            detector.pause()
            mock_model.reset.assert_called()
            detector.stop()

    async def test_resume_resets_model(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            detector.pause()
            mock_model.reset.reset_mock()

            detector.resume()
            mock_model.reset.assert_called()
            detector.stop()

    async def test_silence_input(self) -> None:
        audio_in = StubAudioInput()  # No WAV = silence

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(
                audio_in, wake_word="hey_jarvis", sensitivity=0.5
            )
            callback = AsyncMock()

            await detector.start(callback)
            await asyncio.sleep(0.1)
            detector.stop()

            callback.assert_not_called()

    async def test_stop_closes_audio_input(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(audio_in)
            callback = AsyncMock()

            await detector.start(callback)
            assert audio_in.is_open()

            detector.stop()
            assert not audio_in.is_open()

    async def test_start_is_idempotent(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(audio_in)
            callback = AsyncMock()

            await detector.start(callback)
            await detector.start(callback)  # Should not create second task
            assert detector.is_listening

            detector.stop()

    def test_default_sensitivity(self) -> None:
        audio_in = StubAudioInput()

        with patch("src.wake_word.detector.OWWModel"):
            detector = WakeWordDetector(audio_in)
            assert detector._sensitivity == 0.5

    async def test_does_not_reopen_already_open_stream(self) -> None:
        audio_in = StubAudioInput(TEST_WAV)
        audio_in.open_stream(sample_rate=16000, chunk_size=1024)

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"test_model": 0.0}
            MockModel.return_value = mock_model

            detector = WakeWordDetector(audio_in)
            callback = AsyncMock()

            await detector.start(callback)
            assert audio_in.is_open()

            detector.stop()

    async def test_model_receives_correct_audio_format(self) -> None:
        """Verify that OWW receives int16 numpy arrays of correct size."""
        audio_in = StubAudioInput(TEST_WAV)
        received_arrays = []

        with patch("src.wake_word.detector.OWWModel") as MockModel:
            mock_model = MagicMock()

            def capture_predict(audio_array):
                received_arrays.append(audio_array.copy())
                return {"test_model": 0.0}

            mock_model.predict.side_effect = capture_predict
            MockModel.return_value = mock_model

            detector = WakeWordDetector(audio_in, sensitivity=0.5)
            callback = AsyncMock()

            await detector.start(callback)
            await asyncio.sleep(0.15)
            detector.stop()

        assert len(received_arrays) > 0
        for arr in received_arrays:
            assert arr.dtype.name == "int16"
            assert len(arr) == 1280  # OWW frame size
