"""Text-to-Speech using edge-TTS.

Target: High-quality synthesis with <1s latency for 100 words
Supports 30+ languages and 50+ voices
"""

import asyncio
import time
from io import BytesIO
from typing import Optional

import edge_tts
from loguru import logger

from src.perception.voice.models import (
    SynthesisRequest,
    SynthesisResult,
    VoiceLanguage,
)


# Voice mapping: language -> [list of voice names]
# Format: "en-US-AriaNeural" where:
#   - en-US: language-region
#   - Aria: voice name
#   - Neural: neural TTS indicator
VOICE_MAP = {
    # English
    VoiceLanguage.EN: [
        "en-US-AriaNeural",  # Female, friendly
        "en-US-GuyNeural",  # Male, friendly
        "en-US-JennyNeural",  # Female, conversational
        "en-GB-SoniaNeural",  # British female
        "en-GB-RyanNeural",  # British male
    ],
    # Spanish
    VoiceLanguage.ES: [
        "es-ES-ElviraNeural",  # Female
        "es-ES-AlvaroNeural",  # Male
        "es-MX-DaliaNeural",  # Mexican female
    ],
    # French
    VoiceLanguage.FR: [
        "fr-FR-DeniseNeural",  # Female
        "fr-FR-HenriNeural",  # Male
    ],
    # German
    VoiceLanguage.DE: [
        "de-DE-KatjaNeural",  # Female
        "de-DE-ConradNeural",  # Male
    ],
    # Italian
    VoiceLanguage.IT: [
        "it-IT-ElsaNeural",  # Female
        "it-IT-DiegoNeural",  # Male
    ],
    # Portuguese
    VoiceLanguage.PT: [
        "pt-BR-FranciscaNeural",  # Brazilian female
        "pt-BR-AntonioNeural",  # Brazilian male
    ],
    # Russian
    VoiceLanguage.RU: [
        "ru-RU-SvetlanaNeural",  # Female
        "ru-RU-DmitryNeural",  # Male
    ],
    # Chinese
    VoiceLanguage.ZH: [
        "zh-CN-XiaoxiaoNeural",  # Female
        "zh-CN-YunxiNeural",  # Male
    ],
    # Japanese
    VoiceLanguage.JA: [
        "ja-JP-NanamiNeural",  # Female
        "ja-JP-KeitaNeural",  # Male
    ],
    # Korean
    VoiceLanguage.KO: [
        "ko-KR-SunHiNeural",  # Female
        "ko-KR-InJoonNeural",  # Male
    ],
    # Hindi
    VoiceLanguage.HI: [
        "hi-IN-SwaraNeural",  # Female
        "hi-IN-MadhurNeural",  # Male
    ],
    # Arabic
    VoiceLanguage.AR: [
        "ar-SA-ZariyahNeural",  # Female
        "ar-SA-HamedNeural",  # Male
    ],
    # Dutch
    VoiceLanguage.NL: [
        "nl-NL-ColetteNeural",  # Female
        "nl-NL-MaartenNeural",  # Male
    ],
    # Polish
    VoiceLanguage.PL: [
        "pl-PL-ZofiaNeural",  # Female
        "pl-PL-MarekNeural",  # Male
    ],
    # Turkish
    VoiceLanguage.TR: [
        "tr-TR-EmelNeural",  # Female
        "tr-TR-AhmetNeural",  # Male
    ],
    # Vietnamese
    VoiceLanguage.VI: [
        "vi-VN-HoaiMyNeural",  # Female
        "vi-VN-NamMinhNeural",  # Male
    ],
    # Thai
    VoiceLanguage.TH: [
        "th-TH-PremwadeeNeural",  # Female
        "th-TH-NiwatNeural",  # Male
    ],
    # Indonesian
    VoiceLanguage.ID: [
        "id-ID-GadisNeural",  # Female
        "id-ID-ArdiNeural",  # Male
    ],
}


class EdgeTTS:
    """Text-to-Speech using Microsoft Edge TTS.

    Features:
    - 30+ language support
    - 50+ neural voices (male/female)
    - High-quality synthesis (MOS >4.0)
    - Fast synthesis (<1s for 100 words)
    - Rate, pitch, volume control
    - Free (no API key required)

    Performance:
    - Target: <1s latency for 100 words
    - Quality: MOS >4.0 (Mean Opinion Score)
    """

    def __init__(
        self,
        default_language: VoiceLanguage = VoiceLanguage.EN,
        default_voice: Optional[str] = None,
    ) -> None:
        """Initialize Edge TTS.

        Args:
            default_language: Default language for synthesis
            default_voice: Default voice name (overrides language)
        """
        self.default_language = default_language
        self.default_voice = default_voice

        logger.info(
            f"Initialized Edge TTS: language={default_language.value}, voice={default_voice}"
        )

    def get_voice_for_language(
        self, language: VoiceLanguage, voice_name: Optional[str] = None
    ) -> str:
        """Get voice name for a language.

        Args:
            language: Target language
            voice_name: Specific voice name (optional)

        Returns:
            Voice name string (e.g., "en-US-AriaNeural")

        Raises:
            ValueError: If language not supported
        """
        if voice_name is not None:
            return voice_name

        if language not in VOICE_MAP:
            raise ValueError(f"Language {language.value} not supported")

        # Return first voice (typically female)
        return VOICE_MAP[language][0]

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize text to speech.

        Args:
            request: Synthesis request with text and options

        Returns:
            SynthesisResult with audio data

        Raises:
            ValueError: If synthesis fails
        """
        logger.debug(f"Synthesizing {len(request.text)} chars in {request.language.value}")
        start = time.time()

        # Determine voice to use
        voice = self.get_voice_for_language(request.language, request.voice)

        # Build SSML for rate/pitch/volume control
        ssml_text = self._build_ssml(request.text, request.rate, request.pitch, request.volume)

        # Synthesize using edge-tts
        try:
            communicate = edge_tts.Communicate(ssml_text, voice)

            # Collect audio chunks
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            # Combine audio
            audio_data = b"".join(audio_chunks)

            if not audio_data:
                raise ValueError("Synthesis produced no audio")

            # Calculate duration (approximate from text length)
            # Typical speaking rate: ~150 words/minute = 2.5 words/second
            # Average word length: ~5 chars
            words = len(request.text.split())
            duration_ms = (words / 2.5) * 1000 * (1.0 / request.rate)

            processing_time_ms = (time.time() - start) * 1000

            logger.success(
                f"Synthesis complete: {len(audio_data)} bytes in {processing_time_ms:.0f}ms "
                f"(voice: {voice})"
            )

            return SynthesisResult(
                audio_data=audio_data,
                duration_ms=duration_ms,
                processing_time_ms=processing_time_ms,
                voice_used=voice,
                format="mp3",
                sample_rate=24000,  # Edge TTS default
            )

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise ValueError(f"TTS synthesis failed: {e}") from e

    def _build_ssml(self, text: str, rate: float, pitch: float, volume: float) -> str:
        """Build SSML markup for advanced control.

        Args:
            text: Text to speak
            rate: Speech rate (0.5-2.0, 1.0=normal)
            pitch: Pitch (0.5-2.0, 1.0=normal)
            volume: Volume (0.0-2.0, 1.0=normal)

        Returns:
            SSML markup string
        """
        # Convert to percentage
        rate_pct = int((rate - 1.0) * 100)
        pitch_pct = int((pitch - 1.0) * 50)  # Pitch is more sensitive
        volume_pct = int(volume * 100)

        # Build SSML
        ssml = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        ssml += f'<prosody rate="{rate_pct:+d}%" pitch="{pitch_pct:+d}%" volume="{volume_pct}%">'
        ssml += text
        ssml += "</prosody></speak>"

        return ssml

    async def list_voices(
        self, language: Optional[VoiceLanguage] = None
    ) -> list[dict[str, str]]:
        """List available voices.

        Args:
            language: Filter by language (None = all languages)

        Returns:
            List of voice info dicts with 'name' and 'language' keys
        """
        logger.debug(f"Listing voices for language: {language}")

        # Get all voices from edge-tts
        try:
            all_voices = await edge_tts.list_voices()

            # Filter by language if specified
            if language is not None:
                lang_code = language.value
                filtered = [
                    {"name": v["ShortName"], "language": v["Locale"]}
                    for v in all_voices
                    if v["Locale"].startswith(lang_code)
                ]
                return filtered

            # Return all
            return [{"name": v["ShortName"], "language": v["Locale"]} for v in all_voices]

        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            # Return hardcoded list as fallback
            if language is not None and language in VOICE_MAP:
                return [
                    {"name": v, "language": language.value} for v in VOICE_MAP[language]
                ]
            return []

    async def synthesize_to_file(
        self, request: SynthesisRequest, output_path: str
    ) -> SynthesisResult:
        """Synthesize text and save to file.

        Args:
            request: Synthesis request
            output_path: Output file path

        Returns:
            SynthesisResult
        """
        result = await self.synthesize(request)

        # Write to file
        with open(output_path, "wb") as f:
            f.write(result.audio_data)

        logger.info(f"Saved TTS audio to: {output_path}")
        return result

    def __repr__(self) -> str:
        return f"EdgeTTS(language={self.default_language.value}, voice={self.default_voice})"
