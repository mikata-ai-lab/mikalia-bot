"""
voice.py — Voice tools para Mikalia.

Le da cuerdas vocales (TTS) y oidos (STT) a Mikalia:
- Text-to-Speech: edge-tts (Microsoft, gratis, voz mexicana)
- Speech-to-Text: faster-whisper (local, ONNX, sin API)

Uso:
    from mikalia.tools.voice import TextToSpeechTool, SpeechToTextTool
    tts = TextToSpeechTool()
    result = tts.execute(text="Hola Mikata-kun~")
    # → data/voice/tts_1234567.mp3

    stt = SpeechToTextTool()
    result = stt.execute(audio_path="voice_message.ogg")
    # → "Hola Mikalia, como estas?"
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.voice")

# Voces disponibles (es-MX para Mikalia)
VOICES = {
    "mikalia": "es-MX-DaliaNeural",      # Femenina mexicana (default)
    "mikalia_alt": "es-MX-BeatrizNeural", # Femenina mexicana alternativa
    "male": "es-MX-JorgeNeural",          # Masculina mexicana
    "en_female": "en-US-JennyNeural",     # Inglés femenino
    "en_male": "en-US-GuyNeural",         # Inglés masculino
}

VOICE_DIR = Path("data/voice")


class TextToSpeechTool(BaseTool):
    """
    Convierte texto a audio usando edge-tts.

    Genera archivos MP3 con voces de alta calidad.
    Default: voz femenina mexicana (DaliaNeural).
    """

    @property
    def name(self) -> str:
        return "text_to_speech"

    @property
    def description(self) -> str:
        return (
            "Convert text to speech audio (MP3). "
            "Uses high-quality neural voices. Default is Mexican Spanish female. "
            "Available voices: mikalia (default), mikalia_alt, male, en_female, en_male. "
            "Returns the path to the generated audio file."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to convert to speech",
                },
                "voice": {
                    "type": "string",
                    "description": "Voice to use (default: mikalia)",
                    "enum": list(VOICES.keys()),
                },
            },
            "required": ["text"],
        }

    def execute(
        self,
        text: str,
        voice: str = "mikalia",
        **_: Any,
    ) -> ToolResult:
        try:
            import edge_tts
        except ImportError:
            return ToolResult(
                success=False,
                error="edge-tts no instalado. Ejecuta: pip install edge-tts",
            )

        if not text.strip():
            return ToolResult(success=False, error="Texto vacio")

        voice_id = VOICES.get(voice, VOICES["mikalia"])
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = VOICE_DIR / f"tts_{timestamp}.mp3"

        try:
            # edge-tts es async, lo corremos en un event loop
            async def _generate():
                comm = edge_tts.Communicate(text, voice_id)
                await comm.save(str(output_path))

            # Usar el loop existente o crear uno nuevo
            try:
                loop = asyncio.get_running_loop()
                # Si ya hay loop, crear task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    loop.run_in_executor(pool, lambda: asyncio.run(_generate()))
            except RuntimeError:
                asyncio.run(_generate())

            logger.success(f"Audio generado: {output_path}")
            return ToolResult(
                success=True,
                output=(
                    f"Audio generado: {output_path}\n"
                    f"Voz: {voice_id}\n"
                    f"Texto: {text[:100]}{'...' if len(text) > 100 else ''}"
                ),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error generando audio: {e}")


class SpeechToTextTool(BaseTool):
    """
    Transcribe audio a texto usando faster-whisper.

    Modelo 'base' (~150MB) se descarga en primer uso.
    Soporta español e inglés con detección automática.
    """

    def __init__(self) -> None:
        self._model = None

    @property
    def name(self) -> str:
        return "speech_to_text"

    @property
    def description(self) -> str:
        return (
            "Transcribe audio file to text. "
            "Supports Spanish and English with auto-detection. "
            "Accepts MP3, OGG, WAV, M4A formats. "
            "Uses Whisper model (downloaded on first use, ~150MB)."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Path to the audio file to transcribe",
                },
                "language": {
                    "type": "string",
                    "description": "Language hint (es, en, auto). Default: auto",
                },
            },
            "required": ["audio_path"],
        }

    def execute(
        self,
        audio_path: str,
        language: str = "auto",
        **_: Any,
    ) -> ToolResult:
        audio_file = Path(audio_path)
        if not audio_file.exists():
            return ToolResult(
                success=False,
                error=f"Archivo no encontrado: {audio_path}",
            )

        try:
            self._ensure_model()

            lang = language if language != "auto" else None
            segments, info = self._model.transcribe(
                str(audio_file),
                language=lang,
                beam_size=5,
            )

            # Concatenar segmentos
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            text = " ".join(text_parts)
            detected_lang = info.language

            logger.success(f"Transcripcion completada: {len(text)} chars ({detected_lang})")
            return ToolResult(
                success=True,
                output=(
                    f"Idioma detectado: {detected_lang}\n"
                    f"Transcripcion:\n{text}"
                ),
            )
        except ImportError:
            return ToolResult(
                success=False,
                error="faster-whisper no instalado. Ejecuta: pip install faster-whisper",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error transcribiendo: {e}")

    def _ensure_model(self) -> None:
        """Carga modelo Whisper (lazy, descarga en primer uso)."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        logger.info("Cargando modelo Whisper (base)...")
        self._model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )
        logger.success("Modelo Whisper cargado.")
