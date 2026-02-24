"""
test_image_gen.py — Tests para image generation de Mikalia.

Verifica:
- Pollinations.ai (gratis)
- DALL-E 3 (con mock)
- Manejo de errores
- Definiciones Claude correctas
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mikalia.tools.image_gen import (
    ImageGenerationTool,
    PROVIDERS,
    IMAGE_DIR,
)


class TestImageGenerationTool:
    def test_name(self):
        tool = ImageGenerationTool()
        assert tool.name == "image_generation"

    def test_description(self):
        tool = ImageGenerationTool()
        assert "image" in tool.description.lower()

    def test_parameters(self):
        tool = ImageGenerationTool()
        params = tool.get_parameters()
        assert "prompt" in params["properties"]
        assert "provider" in params["properties"]
        assert "size" in params["properties"]
        assert "prompt" in params["required"]

    def test_claude_definition(self):
        tool = ImageGenerationTool()
        d = tool.to_claude_definition()
        assert d["name"] == "image_generation"
        assert "input_schema" in d

    def test_empty_prompt_fails(self):
        tool = ImageGenerationTool()
        result = tool.execute(prompt="   ")
        assert not result.success
        assert "vacio" in result.error.lower()


class TestPollinations:
    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_success(self, mock_get, tmp_path):
        """Pollinations genera imagen exitosamente."""
        # Simular respuesta con imagen PNG valida
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 5000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [fake_png]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
            result = tool.execute(
                prompt="A sakura tree with circuit board roots",
                provider="pollinations",
            )

        assert result.success
        assert "Pollinations" in result.output
        assert "gratis" in result.output

    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_timeout(self, mock_get):
        """Timeout retorna error claro."""
        import requests as req
        mock_get.side_effect = req.Timeout("timeout")

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", Path("/tmp/test_img")):
            with patch("pathlib.Path.mkdir"):
                result = tool._generate_pollinations(
                    "test image", "1024x1024", Path("/tmp/test_img/out.png"),
                )

        assert not result.success
        assert "Timeout" in result.error or "no disponible" in result.error

    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_small_file(self, mock_get, tmp_path):
        """Archivo muy pequeno indica error."""
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"tiny"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
            result = tool._generate_pollinations(
                "test", "1024x1024", tmp_path / "out.png",
            )

        assert not result.success

    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_custom_size(self, mock_get, tmp_path):
        """Pollinations respeta el tamano personalizado en primera URL."""
        fake_png = b"\x89PNG" + b"\x00" * 5000
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [fake_png]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
            tool.execute(prompt="test", size="1792x1024")

        # First call should have custom size params
        first_call_url = mock_get.call_args_list[0][0][0]
        assert "width=1792" in first_call_url
        assert "height=1024" in first_call_url

    @patch("mikalia.tools.image_gen.time.sleep")
    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_retry_on_error(self, mock_get, mock_sleep, tmp_path):
        """Pollinations reintenta tras error HTTP."""
        import requests as req
        fake_png = b"\x89PNG" + b"\x00" * 5000
        ok_resp = MagicMock()
        ok_resp.iter_content.return_value = [fake_png]
        ok_resp.raise_for_status = MagicMock()

        # Fail twice, succeed on third
        mock_get.side_effect = [
            req.ConnectionError("530"),
            req.ConnectionError("530"),
            ok_resp,
        ]

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
            result = tool._generate_pollinations(
                "test", "1024x1024", tmp_path / "out.png",
            )

        assert result.success
        assert mock_get.call_count == 3

    @patch("mikalia.tools.image_gen.time.sleep")
    @patch("mikalia.tools.image_gen.requests.get")
    def test_pollinations_fallback_url_without_params(self, mock_get, mock_sleep, tmp_path):
        """Si URL con params falla, prueba sin params."""
        import requests as req
        fake_png = b"\x89PNG" + b"\x00" * 5000
        ok_resp = MagicMock()
        ok_resp.iter_content.return_value = [fake_png]
        ok_resp.raise_for_status = MagicMock()

        # All 3 retries with params fail, first without params succeeds
        mock_get.side_effect = [
            req.ConnectionError("530"),
            req.ConnectionError("530"),
            req.ConnectionError("530"),
            ok_resp,
        ]

        tool = ImageGenerationTool()
        with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
            result = tool._generate_pollinations(
                "test", "1024x1024", tmp_path / "out.png",
            )

        assert result.success
        # Last successful call should be the URL without params
        last_url = mock_get.call_args_list[-1][0][0]
        assert "width=" not in last_url


class TestDALLE:
    def test_dalle_no_api_key(self, tmp_path):
        """DALL-E sin API key retorna error claro."""
        tool = ImageGenerationTool()
        with patch.dict("os.environ", {}, clear=True):
            with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
                result = tool.execute(prompt="test", provider="dalle")

        assert not result.success
        assert "OPENAI_API_KEY" in result.error

    @patch("mikalia.tools.image_gen.requests.get")
    @patch("mikalia.tools.image_gen.requests.post")
    def test_dalle_success(self, mock_post, mock_get, tmp_path):
        """DALL-E genera imagen exitosamente (mocked)."""
        # Mock API response
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": [{
                    "url": "https://example.com/image.png",
                    "revised_prompt": "A beautiful sakura tree",
                }],
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        # Mock image download
        fake_png = b"\x89PNG" + b"\x00" * 5000
        mock_get.return_value = MagicMock(
            content=fake_png,
            status_code=200,
        )
        mock_get.return_value.raise_for_status = MagicMock()

        tool = ImageGenerationTool()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
                result = tool.execute(prompt="sakura tree", provider="dalle")

        assert result.success
        assert "DALL-E" in result.output
        assert "revisado" in result.output

    @patch("mikalia.tools.image_gen.requests.post")
    def test_dalle_invalid_size_defaults(self, mock_post, tmp_path):
        """DALL-E con tamano invalido usa default."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": [{"url": "https://x.com/img.png", "revised_prompt": "test"}],
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        with patch("mikalia.tools.image_gen.requests.get") as mock_get:
            mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 5000)
            mock_get.return_value.raise_for_status = MagicMock()

            tool = ImageGenerationTool()
            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
                with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
                    tool.execute(prompt="test", provider="dalle", size="512x512")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["size"] == "1024x1024"


class TestAutoFallback:
    @patch("mikalia.tools.image_gen.time.sleep")
    @patch("mikalia.tools.image_gen.requests.get")
    @patch("mikalia.tools.image_gen.requests.post")
    def test_fallback_to_dalle_when_pollinations_fails(
        self, mock_post, mock_get, mock_sleep, tmp_path,
    ):
        """Si Pollinations falla y hay OPENAI_API_KEY, cae a DALL-E."""
        import requests as req

        fake_png = b"\x89PNG" + b"\x00" * 5000

        # Pollinations always fails
        mock_get.side_effect = req.ConnectionError("530 all the time")

        # DALL-E succeeds
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": [{"url": "https://x.com/img.png", "revised_prompt": "test"}],
            },
        )
        mock_post.return_value.raise_for_status = MagicMock()

        tool = ImageGenerationTool()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
                # Mock get for image download from DALL-E URL
                def smart_get(url, **kwargs):
                    if "openai" not in url and "x.com" not in url:
                        raise req.ConnectionError("530")
                    resp = MagicMock(content=fake_png, status_code=200)
                    resp.raise_for_status = MagicMock()
                    return resp

                mock_get.side_effect = smart_get
                result = tool.execute(prompt="test image")

        assert result.success
        assert "DALL-E" in result.output

    @patch("mikalia.tools.image_gen.time.sleep")
    @patch("mikalia.tools.image_gen.requests.get")
    def test_no_fallback_without_api_key(self, mock_get, mock_sleep, tmp_path):
        """Sin OPENAI_API_KEY, no hay fallback a DALL-E."""
        import requests as req
        mock_get.side_effect = req.ConnectionError("530")

        tool = ImageGenerationTool()
        with patch.dict("os.environ", {}, clear=True):
            with patch("mikalia.tools.image_gen.IMAGE_DIR", tmp_path):
                result = tool.execute(prompt="test")

        assert not result.success
        assert "no disponible" in result.error.lower()


class TestProviders:
    def test_providers_dict(self):
        assert "pollinations" in PROVIDERS
        assert "dalle" in PROVIDERS

    def test_pollinations_no_key_needed(self):
        assert PROVIDERS["pollinations"]["needs_key"] is False

    def test_dalle_needs_key(self):
        assert PROVIDERS["dalle"]["needs_key"] is True
