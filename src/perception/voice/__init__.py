"""Voice perception module for Ironclaw AI.

This module provides:
- Speech-to-Text (STT) with Faster-Whisper
- Text-to-Speech (TTS) with edge-TTS
- Wake word detection with Porcupine
- Voice Activity Detection (VAD) with Silero
- Emotion detection from voice prosody
"""

from src.perception.voice.stt import FasterWhisperSTT
from src.perception.voice.tts import EdgeTTS
from src.perception.voice.wake_word import WakeWordDetector
from src.perception.voice.vad import VoiceActivityDetector
from src.perception.voice.emotion import EmotionDetector
from src.perception.voice.models import (
    TranscriptionResult,
    SynthesisRequest,
    SynthesisResult,
    WakeWordResult,
    VADResult,
    EmotionResult,
    VoiceLanguage,
)

__all__ = [
    "FasterWhisperSTT",
    "EdgeTTS",
    "WakeWordDetector",
    "VoiceActivityDetector",
    "EmotionDetector",
    "TranscriptionResult",
    "SynthesisRequest",
    "SynthesisResult",
    "WakeWordResult",
    "VADResult",
    "EmotionResult",
    "VoiceLanguage",
]
