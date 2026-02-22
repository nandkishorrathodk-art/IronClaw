"""Speech-to-Text using Faster-Whisper.

Target: <500ms latency for 10-second audio on Acer Swift Neo
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Union

from faster_whisper import WhisperModel
from loguru import logger

from src.perception.voice.models import TranscriptionResult, VoiceLanguage


class FasterWhisperSTT:
    """Fast speech-to-text using Faster-Whisper (5x faster than OpenAI Whisper).

    Features:
    - GPU/NPU acceleration support
    - Streaming transcription
    - Word-level timestamps
    - 30+ language support
    - Auto language detection

    Performance:
    - Target: <500ms for 10s audio
    - Model: base (good accuracy, fast)
    - Device: CPU (can use NPU via OpenVINO)
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ) -> None:
        """Initialize Faster-Whisper STT.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
            device: Device (cpu, cuda, auto)
            compute_type: Compute type (int8, float16, float32)
            language: Force specific language (None = auto-detect)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.forced_language = language
        self.model: Optional[WhisperModel] = None

        logger.info(
            f"Initializing Faster-Whisper STT: model={model_size}, device={device}, "
            f"compute_type={compute_type}"
        )

    async def initialize(self) -> None:
        """Load the Whisper model (async wrapper)."""
        if self.model is not None:
            logger.debug("Faster-Whisper model already loaded")
            return

        logger.info("Loading Faster-Whisper model (this may take a moment)...")
        start = time.time()

        # Load model in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        self.model = await loop.run_in_executor(
            None,
            lambda: WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            ),
        )

        elapsed = time.time() - start
        logger.success(f"Faster-Whisper model loaded in {elapsed:.2f}s")

    async def transcribe(
        self,
        audio_path: Union[str, Path],
        language: Optional[VoiceLanguage] = None,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            language: Force specific language (overrides init)
            word_timestamps: Include word-level timestamps

        Returns:
            TranscriptionResult with text and metadata

        Raises:
            ValueError: If model not initialized or audio file not found
        """
        if self.model is None:
            raise ValueError("Model not initialized. Call initialize() first.")

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.debug(f"Transcribing audio: {audio_path}")
        start = time.time()

        # Determine language to use
        target_language = None
        if language is not None:
            target_language = language.value
        elif self.forced_language is not None:
            target_language = self.forced_language

        # Transcribe in thread pool
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(
                str(audio_path),
                language=target_language,
                word_timestamps=word_timestamps,
                beam_size=5,
                vad_filter=True,  # Filter silence
                vad_parameters={"threshold": 0.5},
            ),
        )

        # Collect segments
        text_parts = []
        all_segments = []

        for segment in segments:
            text_parts.append(segment.text)
            if word_timestamps:
                all_segments.append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                        "words": [
                            {"word": w.word, "start": w.start, "end": w.end}
                            for w in getattr(segment, "words", [])
                        ],
                    }
                )

        # Combine text
        full_text = " ".join(text_parts).strip()

        # Calculate metrics
        processing_time_ms = (time.time() - start) * 1000
        duration_ms = info.duration * 1000

        # Detect language
        detected_lang = VoiceLanguage(info.language)

        # Calculate confidence (average of segment probabilities)
        # Note: faster-whisper doesn't provide confidence directly,
        # we use detection probability as proxy
        confidence = min(info.language_probability, 0.99)

        logger.success(
            f"Transcription complete: {len(full_text)} chars in {processing_time_ms:.0f}ms "
            f"(audio: {duration_ms:.0f}ms, language: {detected_lang.value})"
        )

        return TranscriptionResult(
            text=full_text,
            language=detected_lang,
            confidence=confidence,
            duration_ms=duration_ms,
            processing_time_ms=processing_time_ms,
            segments=all_segments if word_timestamps else None,
        )

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        language: Optional[VoiceLanguage] = None,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio from bytes.

        Args:
            audio_bytes: Audio data as bytes
            language: Force specific language
            word_timestamps: Include word-level timestamps

        Returns:
            TranscriptionResult
        """
        # Write to temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            return await self.transcribe(tmp_path, language, word_timestamps)
        finally:
            # Clean up temp file
            try:
                tmp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file {tmp_path}: {e}")

    async def detect_language(self, audio_path: Union[str, Path]) -> VoiceLanguage:
        """Detect language from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Detected language
        """
        if self.model is None:
            raise ValueError("Model not initialized. Call initialize() first.")

        logger.debug(f"Detecting language: {audio_path}")

        # Transcribe with auto language detection
        loop = asyncio.get_event_loop()
        _, info = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(str(audio_path), language=None, beam_size=1),
        )

        detected = VoiceLanguage(info.language)
        logger.info(
            f"Detected language: {detected.value} (confidence: {info.language_probability:.2f})"
        )

        return detected

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.model is not None:
            logger.info("Cleaning up Faster-Whisper model")
            # Note: faster-whisper doesn't require explicit cleanup
            # but we set to None to free reference
            self.model = None

    def __repr__(self) -> str:
        return (
            f"FasterWhisperSTT(model={self.model_size}, device={self.device}, "
            f"loaded={self.model is not None})"
        )
