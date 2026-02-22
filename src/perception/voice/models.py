"""Pydantic models for voice perception."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VoiceLanguage(str, Enum):
    """Supported voice languages (30+ languages)."""

    # European
    EN = "en"  # English
    ES = "es"  # Spanish
    FR = "fr"  # French
    DE = "de"  # German
    IT = "it"  # Italian
    PT = "pt"  # Portuguese
    RU = "ru"  # Russian
    NL = "nl"  # Dutch
    PL = "pl"  # Polish
    UK = "uk"  # Ukrainian
    TR = "tr"  # Turkish
    SV = "sv"  # Swedish
    DA = "da"  # Danish
    NO = "no"  # Norwegian
    FI = "fi"  # Finnish

    # Asian
    ZH = "zh"  # Chinese
    JA = "ja"  # Japanese
    KO = "ko"  # Korean
    HI = "hi"  # Hindi
    BN = "bn"  # Bengali
    PA = "pa"  # Punjabi
    TE = "te"  # Telugu
    MR = "mr"  # Marathi
    TA = "ta"  # Tamil
    UR = "ur"  # Urdu
    GU = "gu"  # Gujarati
    KN = "kn"  # Kannada
    VI = "vi"  # Vietnamese
    TH = "th"  # Thai
    ID = "id"  # Indonesian
    MS = "ms"  # Malay
    FIL = "fil"  # Filipino

    # Middle Eastern/African
    AR = "ar"  # Arabic
    HE = "he"  # Hebrew
    SW = "sw"  # Swahili


class EmotionType(str, Enum):
    """Emotion types detected from voice."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    EXCITED = "excited"
    CALM = "calm"
    STRESSED = "stressed"


class TranscriptionResult(BaseModel):
    """Result of speech-to-text transcription."""

    text: str = Field(..., description="Transcribed text")
    language: VoiceLanguage = Field(..., description="Detected language")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    duration_ms: float = Field(..., description="Audio duration in milliseconds")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    segments: Optional[list[dict]] = Field(
        default=None, description="Word-level timestamps (if available)"
    )


class SynthesisRequest(BaseModel):
    """Request for text-to-speech synthesis."""

    text: str = Field(..., description="Text to synthesize", min_length=1, max_length=5000)
    language: VoiceLanguage = Field(default=VoiceLanguage.EN, description="Target language")
    voice: Optional[str] = Field(
        default=None, description="Specific voice name (e.g., 'en-US-AriaNeural')"
    )
    rate: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech rate multiplier")
    pitch: float = Field(default=1.0, ge=0.5, le=2.0, description="Pitch multiplier")
    volume: float = Field(default=1.0, ge=0.0, le=2.0, description="Volume multiplier")


class SynthesisResult(BaseModel):
    """Result of text-to-speech synthesis."""

    audio_data: bytes = Field(..., description="Synthesized audio data (MP3/WAV)")
    duration_ms: float = Field(..., description="Audio duration in milliseconds")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    voice_used: str = Field(..., description="Voice name used for synthesis")
    format: str = Field(default="mp3", description="Audio format")
    sample_rate: int = Field(default=24000, description="Audio sample rate")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WakeWordResult(BaseModel):
    """Result of wake word detection."""

    detected: bool = Field(..., description="Whether wake word was detected")
    keyword: Optional[str] = Field(default=None, description="Detected keyword")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VADResult(BaseModel):
    """Result of voice activity detection."""

    is_speech: bool = Field(..., description="Whether speech is detected")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    duration_ms: float = Field(..., description="Duration of audio analyzed (ms)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EmotionResult(BaseModel):
    """Result of emotion detection from voice."""

    emotion: EmotionType = Field(..., description="Detected emotion")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    all_scores: dict[EmotionType, float] = Field(
        ..., description="Confidence scores for all emotions"
    )
    features: dict[str, float] = Field(
        ...,
        description="Extracted prosody features (pitch, tempo, energy, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VoiceConfig(BaseModel):
    """Configuration for voice perception system."""

    # STT Config
    stt_model_size: str = Field(
        default="base", description="Whisper model size (tiny, base, small, medium, large)"
    )
    stt_language: Optional[VoiceLanguage] = Field(
        default=None, description="Force specific language (None = auto-detect)"
    )
    stt_device: str = Field(default="cpu", description="Device for STT (cpu, cuda, npu)")

    # TTS Config
    tts_default_language: VoiceLanguage = Field(default=VoiceLanguage.EN)
    tts_default_voice: Optional[str] = Field(default=None)

    # Wake Word Config
    wake_word_keyword: str = Field(default="hey ironclaw", description="Wake word phrase")
    wake_word_sensitivity: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Sensitivity (0=less sensitive, 1=more)"
    )

    # VAD Config
    vad_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Voice activity threshold"
    )

    # Emotion Config
    emotion_enabled: bool = Field(default=True, description="Enable emotion detection")

    # Performance
    max_audio_duration_sec: int = Field(
        default=30, description="Max audio duration for processing"
    )
    timeout_sec: int = Field(default=10, description="Processing timeout")
