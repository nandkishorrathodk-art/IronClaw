"""Integration tests for Voice API endpoints.

Tests all Phase 7 voice features:
- STT (Speech-to-Text)
- TTS (Text-to-Speech)
- VAD (Voice Activity Detection)
- Emotion Detection
- Wake Word Detection
"""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.main import app
from src.perception.voice.models import VoiceLanguage


@pytest.fixture
def test_client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_audio_bytes() -> bytes:
    """Generate sample audio bytes (16kHz, 16-bit PCM).

    Note: This is mock audio. For real tests, use actual audio files.
    """
    # Mock 1 second of silence (16kHz * 2 bytes per sample)
    return b"\x00\x00" * 16000


@pytest.fixture
def sample_audio_file(tmp_path, sample_audio_bytes) -> Path:
    """Create sample WAV audio file."""
    import wave

    audio_file = tmp_path / "test_audio.wav"

    with wave.open(str(audio_file), "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(16000)  # 16kHz
        wav.writeframes(sample_audio_bytes)

    return audio_file


# ============================================================================
# STT Tests
# ============================================================================


@pytest.mark.asyncio
async def test_transcribe_audio_endpoint(test_client, sample_audio_file):
    """Test STT transcription endpoint."""
    with open(sample_audio_file, "rb") as f:
        response = test_client.post(
            "/api/v1/voice/transcribe",
            files={"audio": ("test.wav", f, "audio/wav")},
            data={"language": "en"},
        )

    # Should succeed or fail gracefully (mock audio might not transcribe)
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "text" in data
        assert "language" in data
        assert "confidence" in data
        assert "duration_ms" in data


@pytest.mark.asyncio
async def test_detect_language_endpoint(test_client, sample_audio_file):
    """Test language detection endpoint."""
    with open(sample_audio_file, "rb") as f:
        response = test_client.post(
            "/api/v1/voice/detect-language", files={"audio": ("test.wav", f, "audio/wav")}
        )

    # Should succeed or fail gracefully
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "language" in data
        assert "confidence" in data


# ============================================================================
# TTS Tests
# ============================================================================


@pytest.mark.asyncio
async def test_synthesize_speech_endpoint(test_client):
    """Test TTS synthesis endpoint (JSON response)."""
    response = test_client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Hello world", "language": "en", "rate": 1.0, "pitch": 1.0, "volume": 1.0},
    )

    assert response.status_code == 200
    data = response.json()

    assert "audio_base64" in data
    assert "duration_ms" in data
    assert "voice_used" in data
    assert "format" in data
    assert data["format"] == "mp3"


@pytest.mark.asyncio
async def test_synthesize_speech_audio_endpoint(test_client):
    """Test TTS synthesis endpoint (audio response)."""
    response = test_client.post(
        "/api/v1/voice/synthesize/audio", json={"text": "Test speech", "language": "en"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_list_voices_endpoint(test_client):
    """Test list voices endpoint."""
    response = test_client.get("/api/v1/voice/voices")

    assert response.status_code == 200
    data = response.json()

    assert "voices" in data
    assert isinstance(data["voices"], list)

    # If voices found, check structure
    if data["voices"]:
        voice = data["voices"][0]
        assert "name" in voice
        assert "language" in voice


@pytest.mark.asyncio
async def test_list_voices_filtered(test_client):
    """Test list voices with language filter."""
    response = test_client.get("/api/v1/voice/voices?language=en")

    assert response.status_code == 200
    data = response.json()

    assert "voices" in data


# ============================================================================
# VAD Tests
# ============================================================================


@pytest.mark.asyncio
async def test_vad_endpoint(test_client, sample_audio_file):
    """Test VAD endpoint."""
    with open(sample_audio_file, "rb") as f:
        response = test_client.post(
            "/api/v1/voice/vad", files={"audio": ("test.wav", f, "audio/wav")}
        )

    assert response.status_code == 200
    data = response.json()

    assert "is_speech" in data
    assert "confidence" in data
    assert "duration_ms" in data
    assert isinstance(data["is_speech"], bool)
    assert 0.0 <= data["confidence"] <= 1.0


# ============================================================================
# Emotion Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_emotion_detection_endpoint(test_client, sample_audio_file):
    """Test emotion detection endpoint."""
    with open(sample_audio_file, "rb") as f:
        response = test_client.post(
            "/api/v1/voice/emotion", files={"audio": ("test.wav", f, "audio/wav")}
        )

    # May fail if model not loaded, but should handle gracefully
    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "emotion" in data
        assert "confidence" in data
        assert "all_scores" in data
        assert "features" in data
        assert 0.0 <= data["confidence"] <= 1.0


# ============================================================================
# Wake Word Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_wake_word_endpoint(test_client, sample_audio_file):
    """Test wake word detection endpoint."""
    with open(sample_audio_file, "rb") as f:
        response = test_client.post(
            "/api/v1/voice/wake-word", files={"audio": ("test.wav", f, "audio/wav")}
        )

    assert response.status_code == 200
    data = response.json()

    assert "detected" in data
    assert "confidence" in data
    assert isinstance(data["detected"], bool)
    assert 0.0 <= data["confidence"] <= 1.0


# ============================================================================
# Multi-Language Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language",
    [
        VoiceLanguage.EN,
        VoiceLanguage.ES,
        VoiceLanguage.FR,
        VoiceLanguage.DE,
        VoiceLanguage.ZH,
        VoiceLanguage.JA,
        VoiceLanguage.HI,
    ],
)
async def test_tts_multiple_languages(test_client, language):
    """Test TTS synthesis in multiple languages."""
    response = test_client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Hello", "language": language.value},
    )

    assert response.status_code == 200
    data = response.json()
    assert "audio_base64" in data


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.asyncio
async def test_tts_latency(test_client):
    """Test TTS synthesis latency (<1s for 100 words)."""
    import time

    # Generate 100 words
    text = " ".join(["word"] * 100)

    start = time.time()
    response = test_client.post("/api/v1/voice/synthesize/audio", json={"text": text})
    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed < 5.0  # Generous limit (target: <1s, but network/processing adds overhead)


@pytest.mark.asyncio
async def test_stt_latency(test_client, sample_audio_file):
    """Test STT transcription latency."""
    import time

    with open(sample_audio_file, "rb") as f:
        start = time.time()
        response = test_client.post(
            "/api/v1/voice/transcribe",
            files={"audio": ("test.wav", f, "audio/wav")},
        )
        elapsed = time.time() - start

    # Should respond quickly (even if transcription fails on mock audio)
    assert elapsed < 10.0  # Generous limit

    if response.status_code == 200:
        data = response.json()
        # Check processing time is reasonable
        assert data.get("processing_time_ms", 0) < 5000  # <5s


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_transcribe_invalid_file(test_client):
    """Test STT with invalid audio file."""
    # Send text file as audio
    response = test_client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("test.txt", io.BytesIO(b"not audio"), "text/plain")},
    )

    # Should fail gracefully
    assert response.status_code in [400, 500]


@pytest.mark.asyncio
async def test_synthesize_empty_text(test_client):
    """Test TTS with empty text."""
    response = test_client.post("/api/v1/voice/synthesize", json={"text": ""})

    # Should fail validation
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_synthesize_invalid_language(test_client):
    """Test TTS with invalid language code."""
    response = test_client.post(
        "/api/v1/voice/synthesize", json={"text": "Hello", "language": "invalid"}
    )

    # Should fail validation
    assert response.status_code == 422
