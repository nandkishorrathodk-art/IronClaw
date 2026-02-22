"""Unit tests for voice models (Pydantic)."""

import pytest
from datetime import datetime

from src.perception.voice.models import (
    EmotionResult,
    EmotionType,
    SynthesisRequest,
    SynthesisResult,
    TranscriptionResult,
    VADResult,
    VoiceLanguage,
    WakeWordResult,
)


class TestVoiceLanguage:
    """Test VoiceLanguage enum."""

    def test_language_values(self):
        """Test language enum values."""
        assert VoiceLanguage.EN.value == "en"
        assert VoiceLanguage.ES.value == "es"
        assert VoiceLanguage.ZH.value == "zh"

    def test_all_languages_present(self):
        """Test that all major language groups are present."""
        languages = [lang.value for lang in VoiceLanguage]

        # European
        assert "en" in languages
        assert "fr" in languages
        assert "de" in languages

        # Asian
        assert "zh" in languages
        assert "ja" in languages
        assert "hi" in languages

        # Middle Eastern
        assert "ar" in languages


class TestTranscriptionResult:
    """Test TranscriptionResult model."""

    def test_create_valid_result(self):
        """Test creating valid transcription result."""
        result = TranscriptionResult(
            text="Hello world",
            language=VoiceLanguage.EN,
            confidence=0.95,
            duration_ms=2500.0,
            processing_time_ms=450.0,
        )

        assert result.text == "Hello world"
        assert result.language == VoiceLanguage.EN
        assert result.confidence == 0.95
        assert isinstance(result.timestamp, datetime)

    def test_confidence_validation(self):
        """Test confidence score validation (0.0-1.0)."""
        # Valid
        result = TranscriptionResult(
            text="test",
            language=VoiceLanguage.EN,
            confidence=0.5,
            duration_ms=1000.0,
            processing_time_ms=100.0,
        )
        assert result.confidence == 0.5

        # Invalid: too high
        with pytest.raises(Exception):  # Pydantic ValidationError
            TranscriptionResult(
                text="test",
                language=VoiceLanguage.EN,
                confidence=1.5,
                duration_ms=1000.0,
                processing_time_ms=100.0,
            )

        # Invalid: negative
        with pytest.raises(Exception):
            TranscriptionResult(
                text="test",
                language=VoiceLanguage.EN,
                confidence=-0.1,
                duration_ms=1000.0,
                processing_time_ms=100.0,
            )


class TestSynthesisRequest:
    """Test SynthesisRequest model."""

    def test_create_valid_request(self):
        """Test creating valid synthesis request."""
        request = SynthesisRequest(
            text="Hello world",
            language=VoiceLanguage.EN,
            rate=1.2,
            pitch=1.0,
            volume=0.8,
        )

        assert request.text == "Hello world"
        assert request.language == VoiceLanguage.EN
        assert request.rate == 1.2

    def test_default_values(self):
        """Test default values for optional fields."""
        request = SynthesisRequest(text="Test")

        assert request.language == VoiceLanguage.EN
        assert request.rate == 1.0
        assert request.pitch == 1.0
        assert request.volume == 1.0
        assert request.voice is None

    def test_text_length_validation(self):
        """Test text length validation."""
        # Valid: within limits
        request = SynthesisRequest(text="A" * 5000)
        assert len(request.text) == 5000

        # Invalid: too long
        with pytest.raises(Exception):
            SynthesisRequest(text="A" * 10000)

        # Invalid: empty
        with pytest.raises(Exception):
            SynthesisRequest(text="")

    def test_rate_validation(self):
        """Test rate validation (0.5-2.0)."""
        # Valid
        request = SynthesisRequest(text="test", rate=1.5)
        assert request.rate == 1.5

        # Invalid: too fast
        with pytest.raises(Exception):
            SynthesisRequest(text="test", rate=3.0)

        # Invalid: too slow
        with pytest.raises(Exception):
            SynthesisRequest(text="test", rate=0.1)


class TestSynthesisResult:
    """Test SynthesisResult model."""

    def test_create_valid_result(self):
        """Test creating valid synthesis result."""
        result = SynthesisResult(
            audio_data=b"\x00\x01\x02",
            duration_ms=2500.0,
            processing_time_ms=800.0,
            voice_used="en-US-AriaNeural",
            format="mp3",
            sample_rate=24000,
        )

        assert len(result.audio_data) == 3
        assert result.duration_ms == 2500.0
        assert result.voice_used == "en-US-AriaNeural"
        assert result.format == "mp3"


class TestVADResult:
    """Test VADResult model."""

    def test_create_valid_result(self):
        """Test creating valid VAD result."""
        result = VADResult(is_speech=True, confidence=0.85, duration_ms=50.0)

        assert result.is_speech is True
        assert result.confidence == 0.85
        assert result.duration_ms == 50.0


class TestWakeWordResult:
    """Test WakeWordResult model."""

    def test_detected_wake_word(self):
        """Test detected wake word result."""
        result = WakeWordResult(detected=True, keyword="hey ironclaw", confidence=0.9)

        assert result.detected is True
        assert result.keyword == "hey ironclaw"
        assert result.confidence == 0.9

    def test_not_detected(self):
        """Test not detected result."""
        result = WakeWordResult(detected=False)

        assert result.detected is False
        assert result.keyword is None
        assert result.confidence == 0.0


class TestEmotionResult:
    """Test EmotionResult model."""

    def test_create_valid_result(self):
        """Test creating valid emotion result."""
        all_scores = {
            EmotionType.HAPPY: 0.7,
            EmotionType.NEUTRAL: 0.2,
            EmotionType.SAD: 0.1,
            EmotionType.ANGRY: 0.0,
            EmotionType.FEARFUL: 0.0,
            EmotionType.SURPRISED: 0.0,
            EmotionType.DISGUSTED: 0.0,
            EmotionType.EXCITED: 0.0,
            EmotionType.CALM: 0.0,
            EmotionType.STRESSED: 0.0,
        }

        features = {
            "pitch_mean": 180.0,
            "pitch_std": 35.0,
            "tempo": 120.0,
            "energy_mean": 0.6,
        }

        result = EmotionResult(
            emotion=EmotionType.HAPPY,
            confidence=0.7,
            all_scores=all_scores,
            features=features,
        )

        assert result.emotion == EmotionType.HAPPY
        assert result.confidence == 0.7
        assert len(result.all_scores) == 10
        assert "pitch_mean" in result.features


class TestEmotionType:
    """Test EmotionType enum."""

    def test_emotion_types(self):
        """Test all emotion types are defined."""
        emotions = [e.value for e in EmotionType]

        assert "neutral" in emotions
        assert "happy" in emotions
        assert "sad" in emotions
        assert "angry" in emotions
        assert "excited" in emotions

    def test_emotion_count(self):
        """Test that we have exactly 10 emotion types."""
        assert len(list(EmotionType)) == 10
