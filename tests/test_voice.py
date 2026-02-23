"""
test_voice.py — Tests para voice tools de Mikalia.

Verifica:
- TextToSpeechTool: generacion de audio con edge-tts
- SpeechToTextTool: transcripcion con faster-whisper
- Manejo de errores (texto vacio, archivo no encontrado)
- Definiciones Claude correctas

Usa mocks para evitar dependencias reales en CI.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from mikalia.tools.voice import (
    TextToSpeechTool,
    SpeechToTextTool,
    VOICES,
    VOICE_DIR,
)


# ================================================================
# TextToSpeechTool
# ================================================================

class TestTextToSpeechTool:
    def test_name(self):
        tool = TextToSpeechTool()
        assert tool.name == "text_to_speech"

    def test_description(self):
        tool = TextToSpeechTool()
        assert "speech" in tool.description.lower()

    def test_parameters(self):
        tool = TextToSpeechTool()
        params = tool.get_parameters()
        assert "text" in params["properties"]
        assert "voice" in params["properties"]
        assert "text" in params["required"]

    def test_claude_definition(self):
        tool = TextToSpeechTool()
        d = tool.to_claude_definition()
        assert d["name"] == "text_to_speech"
        assert "input_schema" in d

    def test_empty_text_fails(self):
        tool = TextToSpeechTool()
        result = tool.execute(text="   ")
        assert not result.success
        assert "vacio" in result.error.lower()

    def test_edge_tts_not_installed(self):
        """Si edge-tts no esta instalado, retorna error claro."""
        tool = TextToSpeechTool()
        with patch.dict("sys.modules", {"edge_tts": None}):
            # Forzar ImportError
            with patch("mikalia.tools.voice.TextToSpeechTool.execute") as mock_exec:
                from mikalia.tools.base import ToolResult
                mock_exec.return_value = ToolResult(
                    success=False,
                    error="edge-tts no instalado",
                )
                result = mock_exec(text="hola")
                assert not result.success
                assert "edge-tts" in result.error

    @patch("mikalia.tools.voice.asyncio")
    @patch("mikalia.tools.voice.Path.mkdir")
    def test_tts_success_mocked(self, mock_mkdir, mock_asyncio, tmp_path):
        """TTS genera audio exitosamente (mocked)."""
        mock_asyncio.get_running_loop.side_effect = RuntimeError
        mock_asyncio.run = MagicMock()

        tool = TextToSpeechTool()
        with patch("mikalia.tools.voice.VOICE_DIR", tmp_path):
            result = tool.execute(text="Hola Mikata-kun!")

        assert result.success
        assert "Audio generado" in result.output
        assert "DaliaNeural" in result.output

    @patch("mikalia.tools.voice.asyncio")
    @patch("mikalia.tools.voice.Path.mkdir")
    def test_tts_custom_voice(self, mock_mkdir, mock_asyncio, tmp_path):
        """TTS usa voz personalizada."""
        mock_asyncio.get_running_loop.side_effect = RuntimeError
        mock_asyncio.run = MagicMock()

        tool = TextToSpeechTool()
        with patch("mikalia.tools.voice.VOICE_DIR", tmp_path):
            result = tool.execute(text="Hello!", voice="en_female")

        assert result.success
        assert "JennyNeural" in result.output

    @patch("mikalia.tools.voice.asyncio")
    @patch("mikalia.tools.voice.Path.mkdir")
    def test_tts_unknown_voice_uses_default(self, mock_mkdir, mock_asyncio, tmp_path):
        """Voz desconocida cae al default (mikalia)."""
        mock_asyncio.get_running_loop.side_effect = RuntimeError
        mock_asyncio.run = MagicMock()

        tool = TextToSpeechTool()
        with patch("mikalia.tools.voice.VOICE_DIR", tmp_path):
            result = tool.execute(text="Test", voice="nonexistent")

        assert result.success
        assert "DaliaNeural" in result.output


# ================================================================
# SpeechToTextTool
# ================================================================

class TestSpeechToTextTool:
    def test_name(self):
        tool = SpeechToTextTool()
        assert tool.name == "speech_to_text"

    def test_description(self):
        tool = SpeechToTextTool()
        assert "transcrib" in tool.description.lower()

    def test_parameters(self):
        tool = SpeechToTextTool()
        params = tool.get_parameters()
        assert "audio_path" in params["properties"]
        assert "language" in params["properties"]
        assert "audio_path" in params["required"]

    def test_claude_definition(self):
        tool = SpeechToTextTool()
        d = tool.to_claude_definition()
        assert d["name"] == "speech_to_text"

    def test_file_not_found(self):
        tool = SpeechToTextTool()
        result = tool.execute(audio_path="/nonexistent/audio.mp3")
        assert not result.success
        assert "no encontrado" in result.error.lower()

    def test_stt_success_mocked(self, tmp_path):
        """STT transcribe exitosamente (mocked)."""
        # Crear archivo dummy
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        tool = SpeechToTextTool()

        # Mock del modelo Whisper
        mock_segment = MagicMock()
        mock_segment.text = "Hola Mikalia, como estas?"
        mock_info = MagicMock()
        mock_info.language = "es"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        tool._model = mock_model

        result = tool.execute(audio_path=str(audio_file))

        assert result.success
        assert "Hola Mikalia" in result.output
        assert "es" in result.output

    def test_stt_with_language_hint(self, tmp_path):
        """STT respeta language hint."""
        audio_file = tmp_path / "test.ogg"
        audio_file.write_bytes(b"fake")

        tool = SpeechToTextTool()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        tool._model = mock_model

        result = tool.execute(audio_path=str(audio_file), language="en")

        assert result.success
        mock_model.transcribe.assert_called_once_with(
            str(audio_file), language="en", beam_size=5,
        )

    def test_stt_auto_language(self, tmp_path):
        """STT con language=auto pasa None al modelo."""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake")

        tool = SpeechToTextTool()
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Texto"
        mock_info = MagicMock()
        mock_info.language = "es"
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        tool._model = mock_model

        result = tool.execute(audio_path=str(audio_file), language="auto")

        mock_model.transcribe.assert_called_once_with(
            str(audio_file), language=None, beam_size=5,
        )

    def test_stt_multiple_segments(self, tmp_path):
        """STT concatena multiples segmentos."""
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake")

        tool = SpeechToTextTool()
        seg1 = MagicMock()
        seg1.text = "Primera parte."
        seg2 = MagicMock()
        seg2.text = "Segunda parte."
        mock_info = MagicMock()
        mock_info.language = "es"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], mock_info)
        tool._model = mock_model

        result = tool.execute(audio_path=str(audio_file))

        assert result.success
        assert "Primera parte." in result.output
        assert "Segunda parte." in result.output


# ================================================================
# Voices config
# ================================================================

class TestVoicesConfig:
    def test_voices_has_mikalia_default(self):
        assert "mikalia" in VOICES
        assert "Dalia" in VOICES["mikalia"]

    def test_voices_has_english(self):
        assert "en_female" in VOICES
        assert "en_male" in VOICES

    def test_voices_all_mexican_spanish(self):
        """Voces mexicanas usan es-MX."""
        for key in ["mikalia", "mikalia_alt", "male"]:
            assert "es-MX" in VOICES[key]
