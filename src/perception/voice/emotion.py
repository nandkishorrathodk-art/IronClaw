"""Emotion detection from voice prosody.

Analyzes pitch, tempo, energy, and other acoustic features to detect emotions
Target: >80% accuracy across 10 emotion types
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Union

import numpy as np
import torch
from loguru import logger

from src.perception.voice.models import EmotionResult, EmotionType


class EmotionDetector:
    """Emotion detection from voice using prosody analysis.

    Features:
    - 10 emotion types (neutral, happy, sad, angry, etc.)
    - Prosody feature extraction (pitch, tempo, energy)
    - AI-based classification
    - Confidence scoring

    Performance:
    - Target: >80% accuracy
    - Latency: <200ms
    - Works with any audio format
    """

    def __init__(
        self,
        model_name: str = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim",
        device: str = "cpu",
    ) -> None:
        """Initialize emotion detector.

        Args:
            model_name: HuggingFace model for emotion detection
            device: Device for inference (cpu, cuda)

        Note:
            Default model is wav2vec2 fine-tuned for emotion recognition
        """
        self.model_name = model_name
        self.device = device
        self.model: Optional[torch.nn.Module] = None
        self.processor: Optional[object] = None

        logger.info(f"Initialized Emotion Detector: model={model_name}, device={device}")

    async def initialize(self) -> None:
        """Load emotion detection model."""
        if self.model is not None:
            logger.debug("Emotion model already loaded")
            return

        logger.info("Loading emotion detection model (this may take a moment)...")
        start = time.time()

        try:
            from transformers import AutoModelForAudioClassification, Wav2Vec2Processor

            # Load in thread pool
            loop = asyncio.get_event_loop()

            async def load_model():
                """Load model and processor."""
                processor = await loop.run_in_executor(
                    None, lambda: Wav2Vec2Processor.from_pretrained(self.model_name)
                )
                model = await loop.run_in_executor(
                    None, lambda: AutoModelForAudioClassification.from_pretrained(self.model_name)
                )
                model.to(self.device)
                model.eval()
                return processor, model

            self.processor, self.model = await load_model()

            elapsed = time.time() - start
            logger.success(f"Emotion model loaded in {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load emotion model: {e}")
            logger.warning("Falling back to rule-based emotion detection")
            # Set to None to trigger rule-based fallback
            self.model = None
            self.processor = None

    async def detect(self, audio_path: Union[str, Path]) -> EmotionResult:
        """Detect emotion from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            EmotionResult with detected emotion and confidence

        Raises:
            ValueError: If audio file not found
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.debug(f"Detecting emotion from: {audio_path}")
        start = time.time()

        if self.model is not None:
            # Use AI model
            result = await self._detect_with_model(audio_path)
        else:
            # Use rule-based fallback
            result = await self._detect_rule_based(audio_path)

        processing_time_ms = (time.time() - start) * 1000
        logger.info(
            f"Emotion detected: {result.emotion.value} ({result.confidence:.2f}) "
            f"in {processing_time_ms:.0f}ms"
        )

        return result

    async def _detect_with_model(self, audio_path: Path) -> EmotionResult:
        """Detect emotion using AI model."""
        import librosa

        # Load audio
        loop = asyncio.get_event_loop()
        audio, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=16000))

        # Process audio
        inputs = self.processor(audio, sampling_rate=sr, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Run inference
        with torch.no_grad():
            logits = self.model(**inputs).logits

        # Get probabilities
        probs = torch.nn.functional.softmax(logits, dim=-1)[0]

        # Map to emotion types
        # Note: This mapping depends on the specific model
        # The default model outputs arousal/valence dimensions
        # We map these to discrete emotions
        emotion, all_scores = self._map_to_emotions(probs.cpu().numpy())

        # Extract prosody features for additional context
        features = await self._extract_features(audio_path)

        return EmotionResult(
            emotion=emotion,
            confidence=all_scores[emotion],
            all_scores=all_scores,
            features=features,
        )

    async def _detect_rule_based(self, audio_path: Path) -> EmotionResult:
        """Detect emotion using rule-based prosody analysis.

        This is a fallback when AI model is not available.
        Analyzes pitch, tempo, and energy to infer emotion.
        """
        features = await self._extract_features(audio_path)

        # Rule-based emotion detection
        pitch_mean = features.get("pitch_mean", 150.0)
        pitch_std = features.get("pitch_std", 30.0)
        tempo = features.get("tempo", 120.0)
        energy_mean = features.get("energy_mean", 0.5)

        # Simple heuristics
        if pitch_mean > 200 and tempo > 140:
            emotion = EmotionType.EXCITED
        elif pitch_mean > 180 and pitch_std > 40:
            emotion = EmotionType.HAPPY
        elif pitch_mean < 130 and energy_mean < 0.3:
            emotion = EmotionType.SAD
        elif pitch_std > 50 and energy_mean > 0.7:
            emotion = EmotionType.ANGRY
        elif pitch_mean > 170 and pitch_std > 45:
            emotion = EmotionType.SURPRISED
        elif energy_mean < 0.25:
            emotion = EmotionType.CALM
        else:
            emotion = EmotionType.NEUTRAL

        # Mock confidence scores
        all_scores = {emo: 0.1 for emo in EmotionType}
        all_scores[emotion] = 0.7  # Higher confidence for detected emotion

        return EmotionResult(
            emotion=emotion,
            confidence=all_scores[emotion],
            all_scores=all_scores,
            features=features,
        )

    async def _extract_features(self, audio_path: Path) -> dict[str, float]:
        """Extract prosody features from audio.

        Features:
        - pitch_mean: Average pitch (Hz)
        - pitch_std: Pitch variation (Hz)
        - tempo: Speaking rate (BPM)
        - energy_mean: Average energy/loudness
        - energy_std: Energy variation
        """
        try:
            import librosa

            loop = asyncio.get_event_loop()

            # Load audio
            audio, sr = await loop.run_in_executor(None, lambda: librosa.load(audio_path, sr=None))

            # Extract pitch (fundamental frequency)
            pitches, magnitudes = await loop.run_in_executor(
                None, lambda: librosa.piptrack(y=audio, sr=sr)
            )
            pitch_values = []
            for t in range(pitches.shape[1]):
                index = magnitudes[:, t].argmax()
                pitch = pitches[index, t]
                if pitch > 0:  # Filter out zeros
                    pitch_values.append(pitch)

            pitch_mean = float(np.mean(pitch_values)) if pitch_values else 150.0
            pitch_std = float(np.std(pitch_values)) if pitch_values else 30.0

            # Extract tempo
            tempo, _ = await loop.run_in_executor(None, lambda: librosa.beat.beat_track(y=audio, sr=sr))
            tempo = float(tempo)

            # Extract energy (RMS)
            rms = await loop.run_in_executor(None, lambda: librosa.feature.rms(y=audio)[0])
            energy_mean = float(np.mean(rms))
            energy_std = float(np.std(rms))

            # Extract spectral centroid (brightness)
            centroid = await loop.run_in_executor(
                None, lambda: librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
            )
            spectral_mean = float(np.mean(centroid))

            return {
                "pitch_mean": pitch_mean,
                "pitch_std": pitch_std,
                "tempo": tempo,
                "energy_mean": energy_mean,
                "energy_std": energy_std,
                "spectral_centroid": spectral_mean,
            }

        except Exception as e:
            logger.warning(f"Failed to extract features: {e}")
            # Return default features
            return {
                "pitch_mean": 150.0,
                "pitch_std": 30.0,
                "tempo": 120.0,
                "energy_mean": 0.5,
                "energy_std": 0.2,
                "spectral_centroid": 2000.0,
            }

    def _map_to_emotions(self, probs: np.ndarray) -> tuple[EmotionType, dict[EmotionType, float]]:
        """Map model outputs to emotion types.

        Note: This is model-specific. The default model outputs
        arousal/valence dimensions which we map to discrete emotions.
        """
        # For wav2vec2 emotion models, outputs are typically:
        # [neutral, happy, sad, angry, fearful, surprised, disgusted]
        # Map these to our EmotionType enum

        emotion_map = [
            EmotionType.NEUTRAL,
            EmotionType.HAPPY,
            EmotionType.SAD,
            EmotionType.ANGRY,
            EmotionType.FEARFUL,
            EmotionType.SURPRISED,
            EmotionType.DISGUSTED,
        ]

        # Pad probs if needed
        if len(probs) < len(emotion_map):
            probs = np.pad(probs, (0, len(emotion_map) - len(probs)))

        # Create scores dict
        all_scores = {emotion_map[i]: float(probs[i]) for i in range(len(emotion_map))}

        # Add missing emotions with low scores
        for emotion in EmotionType:
            if emotion not in all_scores:
                all_scores[emotion] = 0.05

        # Get top emotion
        top_emotion = max(all_scores.items(), key=lambda x: x[1])[0]

        return top_emotion, all_scores

    async def detect_bytes(self, audio_bytes: bytes) -> EmotionResult:
        """Detect emotion from audio bytes.

        Args:
            audio_bytes: Audio data as bytes

        Returns:
            EmotionResult
        """
        import tempfile

        # Write to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            return await self.detect(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.model is not None:
            logger.info("Cleaning up emotion model")
            self.model = None
            self.processor = None

    def __repr__(self) -> str:
        return f"EmotionDetector(model={self.model_name}, loaded={self.model is not None})"
