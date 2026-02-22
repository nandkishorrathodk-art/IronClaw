"""Voice Activity Detection using Silero VAD.

Detects speech vs silence/background noise with high accuracy
"""

import asyncio
import time
from typing import Optional

import torch
from loguru import logger

from src.perception.voice.models import VADResult


class VoiceActivityDetector:
    """Voice Activity Detection using Silero VAD.

    Features:
    - Distinguish speech from silence
    - Low latency (<50ms)
    - High accuracy (>95%)
    - Robust to background noise
    - Runs locally (privacy-safe)

    Performance:
    - Latency: <50ms
    - Accuracy: >95%
    - CPU usage: <3%
    """

    def __init__(
        self,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        use_onnx: bool = False,
    ) -> None:
        """Initialize Silero VAD.

        Args:
            threshold: Voice probability threshold (0.0-1.0)
            sampling_rate: Audio sample rate (8000 or 16000)
            use_onnx: Use ONNX runtime for faster inference
        """
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.use_onnx = use_onnx
        self.model: Optional[torch.nn.Module] = None

        logger.info(
            f"Initialized VAD: threshold={threshold}, sr={sampling_rate}, onnx={use_onnx}"
        )

    async def initialize(self) -> None:
        """Load Silero VAD model."""
        if self.model is not None:
            logger.debug("Silero VAD already loaded")
            return

        logger.info("Loading Silero VAD model...")
        start = time.time()

        try:
            # Load model in thread pool
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=self.use_onnx,
                ),
            )

            # Set to eval mode
            if hasattr(self.model, "eval"):
                self.model.eval()

            elapsed = time.time() - start
            logger.success(f"Silero VAD loaded in {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load Silero VAD: {e}")
            raise

    async def detect(self, audio_data: bytes) -> VADResult:
        """Detect voice activity in audio.

        Args:
            audio_data: PCM audio data (16-bit, 16kHz or 8kHz, mono)

        Returns:
            VADResult with speech detection status

        Raises:
            ValueError: If model not initialized
        """
        if self.model is None:
            raise ValueError("VAD model not initialized. Call initialize() first.")

        start = time.time()

        # Convert bytes to tensor
        audio_int16 = torch.frombuffer(audio_data, dtype=torch.int16)
        audio_float32 = audio_int16.float() / 32768.0  # Normalize to [-1, 1]

        # Ensure correct length (Silero VAD expects chunks)
        # Pad or trim to 512 samples (for 16kHz)
        chunk_size = 512 if self.sampling_rate == 16000 else 256
        if len(audio_float32) < chunk_size:
            # Pad with zeros
            audio_float32 = torch.nn.functional.pad(
                audio_float32, (0, chunk_size - len(audio_float32))
            )
        elif len(audio_float32) > chunk_size:
            # Use first chunk
            audio_float32 = audio_float32[:chunk_size]

        # Run VAD inference
        loop = asyncio.get_event_loop()
        try:
            speech_prob = await loop.run_in_executor(
                None, lambda: self.model(audio_float32, self.sampling_rate).item()
            )
        except Exception as e:
            logger.error(f"VAD inference failed: {e}")
            # Return uncertain result on error
            return VADResult(
                is_speech=False, confidence=0.0, duration_ms=(time.time() - start) * 1000
            )

        # Determine if speech
        is_speech = speech_prob >= self.threshold

        duration_ms = (time.time() - start) * 1000

        logger.debug(
            f"VAD: is_speech={is_speech}, prob={speech_prob:.3f}, duration={duration_ms:.0f}ms"
        )

        return VADResult(
            is_speech=is_speech,
            confidence=speech_prob,
            duration_ms=duration_ms,
        )

    async def detect_stream(
        self, audio_chunks: list[bytes], min_speech_duration_ms: float = 250
    ) -> VADResult:
        """Detect voice activity in a stream of audio chunks.

        Args:
            audio_chunks: List of PCM audio chunks
            min_speech_duration_ms: Minimum duration to consider as speech

        Returns:
            VADResult aggregated over all chunks
        """
        if not audio_chunks:
            return VADResult(is_speech=False, confidence=0.0, duration_ms=0.0)

        start = time.time()

        # Process each chunk
        speech_probs = []
        for chunk in audio_chunks:
            result = await self.detect(chunk)
            speech_probs.append(result.confidence)

        # Aggregate: speech if average probability > threshold
        # and sustained for minimum duration
        avg_prob = sum(speech_probs) / len(speech_probs)
        is_speech = avg_prob >= self.threshold

        # Check duration (each chunk is ~32ms at 16kHz/512 samples)
        chunk_duration_ms = 32.0  # Approximate
        total_duration_ms = len(audio_chunks) * chunk_duration_ms

        if is_speech and total_duration_ms < min_speech_duration_ms:
            # Too short to be real speech
            is_speech = False

        processing_time_ms = (time.time() - start) * 1000

        logger.debug(
            f"VAD Stream: is_speech={is_speech}, avg_prob={avg_prob:.3f}, "
            f"duration={total_duration_ms:.0f}ms, processing={processing_time_ms:.0f}ms"
        )

        return VADResult(
            is_speech=is_speech,
            confidence=avg_prob,
            duration_ms=processing_time_ms,
        )

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.model is not None:
            logger.info("Cleaning up Silero VAD model")
            # PyTorch models don't need explicit cleanup
            # but we clear the reference
            self.model = None

    def __repr__(self) -> str:
        return (
            f"VoiceActivityDetector(threshold={self.threshold}, sr={self.sampling_rate}, "
            f"loaded={self.model is not None})"
        )


class MockVAD:
    """Mock VAD for testing without downloading Silero model."""

    def __init__(self, threshold: float = 0.5, sampling_rate: int = 16000) -> None:
        """Initialize mock VAD."""
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        logger.warning("Using MOCK VAD (always returns True for speech)")

    async def initialize(self) -> None:
        """Mock initialization."""
        logger.info("Mock VAD initialized")

    async def detect(self, audio_data: bytes) -> VADResult:
        """Mock detection (always returns speech detected)."""
        return VADResult(
            is_speech=True,
            confidence=0.8,  # Mock confidence
            duration_ms=10.0,  # Mock duration
        )

    async def detect_stream(
        self, audio_chunks: list[bytes], min_speech_duration_ms: float = 250
    ) -> VADResult:
        """Mock stream detection."""
        return VADResult(
            is_speech=True,
            confidence=0.8,
            duration_ms=len(audio_chunks) * 32.0,
        )

    async def cleanup(self) -> None:
        """Mock cleanup."""
        pass

    def __repr__(self) -> str:
        return f"MockVAD(threshold={self.threshold})"
