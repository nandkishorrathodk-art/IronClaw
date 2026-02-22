"""Voice API endpoints for Ironclaw.

Provides REST and WebSocket APIs for:
- Speech-to-Text (STT)
- Text-to-Speech (TTS)
- Voice Activity Detection (VAD)
- Emotion Detection
- Wake Word Detection
"""

import asyncio
import base64
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, status
from fastapi.responses import Response

from src.perception.voice import (
    EdgeTTS,
    EmotionDetector,
    FasterWhisperSTT,
    VoiceActivityDetector,
    WakeWordDetector,
)
from src.perception.voice.models import (
    EmotionResult,
    SynthesisRequest,
    SynthesisResult,
    TranscriptionResult,
    VADResult,
    VoiceLanguage,
    WakeWordResult,
)
from src.perception.voice.vad import MockVAD
from src.perception.voice.wake_word import MockWakeWordDetector
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice"])

# Global instances (initialized on startup)
_stt: Optional[FasterWhisperSTT] = None
_tts: Optional[EdgeTTS] = None
_vad: Optional[VoiceActivityDetector] = None
_wake_word: Optional[WakeWordDetector] = None
_emotion: Optional[EmotionDetector] = None


async def get_stt() -> FasterWhisperSTT:
    """Get or initialize STT engine."""
    global _stt
    if _stt is None:
        _stt = FasterWhisperSTT(model_size="base", device="cpu", compute_type="int8")
        await _stt.initialize()
    return _stt


async def get_tts() -> EdgeTTS:
    """Get or initialize TTS engine."""
    global _tts
    if _tts is None:
        _tts = EdgeTTS(default_language=VoiceLanguage.EN)
    return _tts


async def get_vad() -> VoiceActivityDetector:
    """Get or initialize VAD engine."""
    global _vad
    if _vad is None:
        try:
            _vad = VoiceActivityDetector(threshold=0.5)
            await _vad.initialize()
        except Exception as e:
            logger.warning(f"Failed to init VAD, using mock: {e}")
            _vad = MockVAD(threshold=0.5)
            await _vad.initialize()
    return _vad


async def get_wake_word() -> WakeWordDetector:
    """Get or initialize wake word detector."""
    global _wake_word
    if _wake_word is None:
        # Use mock by default (requires Porcupine API key for production)
        logger.info("Using mock wake word detector (set PORCUPINE_API_KEY for production)")
        _wake_word = MockWakeWordDetector(keyword="hey ironclaw")
        await _wake_word.initialize()
    return _wake_word


async def get_emotion() -> EmotionDetector:
    """Get or initialize emotion detector."""
    global _emotion
    if _emotion is None:
        _emotion = EmotionDetector()
        try:
            await _emotion.initialize()
        except Exception as e:
            logger.warning(f"Emotion model init failed, using fallback: {e}")
    return _emotion


# ============================================================================
# STT Endpoints
# ============================================================================


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    language: Optional[VoiceLanguage] = None,
    word_timestamps: bool = False,
) -> TranscriptionResult:
    """Transcribe audio file to text.

    Args:
        audio: Audio file upload
        language: Force specific language (None = auto-detect)
        word_timestamps: Include word-level timestamps

    Returns:
        TranscriptionResult with text and metadata

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/transcribe" \\
             -F "audio=@recording.wav" \\
             -F "language=en"
        ```
    """
    try:
        # Save uploaded file to temp location
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Transcribe
        stt = await get_stt()
        result = await stt.transcribe(tmp_path, language, word_timestamps)

        # Clean up temp file
        try:
            tmp_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete temp file: {e}")

        return result

    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}",
        )


@router.post("/detect-language", response_model=dict)
async def detect_language(
    audio: UploadFile = File(..., description="Audio file"),
) -> dict:
    """Detect language from audio file.

    Returns:
        ```json
        {
            "language": "en",
            "confidence": 0.95
        }
        ```
    """
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        stt = await get_stt()
        detected = await stt.detect_language(tmp_path)

        try:
            tmp_path.unlink()
        except Exception:
            pass

        return {"language": detected.value, "confidence": 0.95}

    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Language detection failed: {str(e)}",
        )


# ============================================================================
# TTS Endpoints
# ============================================================================


@router.post("/synthesize", response_model=dict)
async def synthesize_speech(request: SynthesisRequest) -> dict:
    """Synthesize text to speech.

    Args:
        request: Synthesis request with text and options

    Returns:
        ```json
        {
            "audio_base64": "...",  // Base64-encoded audio
            "duration_ms": 2500,
            "voice_used": "en-US-AriaNeural"
        }
        ```

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/synthesize" \\
             -H "Content-Type: application/json" \\
             -d '{"text": "Hello world", "language": "en"}'
        ```
    """
    try:
        tts = await get_tts()
        result: SynthesisResult = await tts.synthesize(request)

        # Encode audio as base64 for JSON response
        audio_b64 = base64.b64encode(result.audio_data).decode("utf-8")

        return {
            "audio_base64": audio_b64,
            "duration_ms": result.duration_ms,
            "processing_time_ms": result.processing_time_ms,
            "voice_used": result.voice_used,
            "format": result.format,
            "sample_rate": result.sample_rate,
        }

    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS synthesis failed: {str(e)}",
        )


@router.post("/synthesize/audio")
async def synthesize_speech_audio(request: SynthesisRequest) -> Response:
    """Synthesize text to speech and return raw audio.

    Returns audio/mpeg (MP3) directly.

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/synthesize/audio" \\
             -H "Content-Type: application/json" \\
             -d '{"text": "Hello", "language": "en"}' \\
             -o output.mp3
        ```
    """
    try:
        tts = await get_tts()
        result = await tts.synthesize(request)

        return Response(
            content=result.audio_data,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )

    except Exception as e:
        logger.error(f"TTS audio synthesis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS synthesis failed: {str(e)}",
        )


@router.get("/voices", response_model=dict)
async def list_available_voices(language: Optional[VoiceLanguage] = None) -> dict:
    """List available TTS voices.

    Args:
        language: Filter by language (optional)

    Returns:
        ```json
        {
            "voices": [
                {"name": "en-US-AriaNeural", "language": "en-US"},
                {"name": "en-US-GuyNeural", "language": "en-US"}
            ]
        }
        ```
    """
    try:
        tts = await get_tts()
        voices = await tts.list_voices(language)
        return {"voices": voices}

    except Exception as e:
        logger.error(f"Failed to list voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list voices: {str(e)}",
        )


# ============================================================================
# VAD Endpoints
# ============================================================================


@router.post("/vad", response_model=VADResult)
async def detect_voice_activity(
    audio: UploadFile = File(..., description="Audio file (16kHz PCM)"),
) -> VADResult:
    """Detect voice activity in audio.

    Args:
        audio: Audio file (preferably 16kHz PCM WAV)

    Returns:
        VADResult with speech detection status

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/vad" \\
             -F "audio=@recording.wav"
        ```
    """
    try:
        content = await audio.read()

        vad = await get_vad()
        result = await vad.detect(content)

        return result

    except Exception as e:
        logger.error(f"VAD detection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"VAD failed: {str(e)}",
        )


# ============================================================================
# Emotion Detection Endpoints
# ============================================================================


@router.post("/emotion", response_model=EmotionResult)
async def detect_emotion(
    audio: UploadFile = File(..., description="Audio file"),
) -> EmotionResult:
    """Detect emotion from voice.

    Args:
        audio: Audio file with speech

    Returns:
        EmotionResult with detected emotion and confidence

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/emotion" \\
             -F "audio=@speech.wav"
        ```
    """
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        emotion_detector = await get_emotion()
        result = await emotion_detector.detect(tmp_path)

        try:
            tmp_path.unlink()
        except Exception:
            pass

        return result

    except Exception as e:
        logger.error(f"Emotion detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Emotion detection failed: {str(e)}",
        )


# ============================================================================
# Wake Word Detection Endpoints
# ============================================================================


@router.post("/wake-word", response_model=WakeWordResult)
async def detect_wake_word(
    audio: UploadFile = File(..., description="Audio file (16kHz PCM)"),
) -> WakeWordResult:
    """Detect wake word in audio.

    Args:
        audio: Audio file (16kHz, 16-bit PCM)

    Returns:
        WakeWordResult with detection status

    Example:
        ```bash
        curl -X POST "http://localhost:8000/api/v1/voice/wake-word" \\
             -F "audio=@recording.wav"
        ```
    """
    try:
        content = await audio.read()

        detector = await get_wake_word()
        result = await detector.detect_from_audio(content)

        return result

    except Exception as e:
        logger.error(f"Wake word detection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wake word detection failed: {str(e)}",
        )


# ============================================================================
# WebSocket Endpoint for Streaming Voice
# ============================================================================


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time voice processing.

    Protocol:
        Client → Server: Binary audio chunks (16kHz, 16-bit PCM)
        Server → Client: JSON responses with transcription, VAD, emotion

    Example response:
        ```json
        {
            "type": "transcription",
            "text": "hello world",
            "confidence": 0.95,
            "is_final": true
        }
        ```
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted for voice streaming")

    try:
        # Initialize all engines
        stt = await get_stt()
        vad = await get_vad()

        audio_buffer = []
        speech_detected = False

        while True:
            # Receive audio chunk
            data = await websocket.receive_bytes()

            # Check for voice activity
            vad_result = await vad.detect(data)

            if vad_result.is_speech:
                speech_detected = True
                audio_buffer.append(data)

                # Send VAD result
                await websocket.send_json(
                    {
                        "type": "vad",
                        "is_speech": True,
                        "confidence": vad_result.confidence,
                    }
                )
            else:
                # If we were detecting speech and now silence, transcribe buffer
                if speech_detected and audio_buffer:
                    logger.info("End of speech detected, transcribing...")

                    # Combine audio chunks
                    full_audio = b"".join(audio_buffer)

                    # Transcribe
                    try:
                        result = await stt.transcribe_bytes(full_audio)

                        # Send transcription
                        await websocket.send_json(
                            {
                                "type": "transcription",
                                "text": result.text,
                                "language": result.language.value,
                                "confidence": result.confidence,
                                "is_final": True,
                            }
                        )

                        # Reset buffer
                        audio_buffer = []
                        speech_detected = False

                    except Exception as e:
                        logger.error(f"Transcription error: {e}")
                        await websocket.send_json(
                            {"type": "error", "message": f"Transcription failed: {str(e)}"}
                        )

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await websocket.close()


# ============================================================================
# Cleanup
# ============================================================================


async def cleanup_voice_engines() -> None:
    """Clean up voice engines on shutdown."""
    logger.info("Cleaning up voice engines...")

    tasks = []
    if _stt:
        tasks.append(_stt.cleanup())
    if _vad:
        tasks.append(_vad.cleanup())
    if _wake_word:
        tasks.append(_wake_word.cleanup())
    if _emotion:
        tasks.append(_emotion.cleanup())

    await asyncio.gather(*tasks, return_exceptions=True)

    logger.success("Voice engines cleaned up")
