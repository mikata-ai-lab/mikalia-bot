"""
test_weather.py — Tests para WeatherTool.

Verifica:
- Consulta exitosa (mock wttr.in)
- Ciudad default Monterrey
- Timeout
- Respuesta invalida
- Definicion Claude correcta
- Idioma custom

Mock de la API wttr.in con estructura JSON realista.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from mikalia.tools.weather import WeatherTool


def _make_wttr_response(
    city: str = "Monterrey",
    country: str = "Mexico",
    temp_c: str = "32",
    feels_like: str = "35",
    humidity: str = "60",
    wind_kmph: str = "15",
    wind_dir: str = "SE",
    description: str = "Parcialmente nublado",
    max_temp: str = "36",
    min_temp: str = "24",
    lang: str = "es",
) -> dict:
    """Genera una respuesta realista de wttr.in."""
    return {
        "current_condition": [
            {
                "temp_C": temp_c,
                "FeelsLikeC": feels_like,
                "humidity": humidity,
                "windspeedKmph": wind_kmph,
                "winddir16Point": wind_dir,
                "weatherDesc": [{"value": "Partly cloudy"}],
                f"lang_{lang}": [{"value": description}],
            }
        ],
        "nearest_area": [
            {
                "areaName": [{"value": city}],
                "country": [{"value": country}],
            }
        ],
        "weather": [
            {
                "maxtempC": max_temp,
                "mintempC": min_temp,
            }
        ],
    }


# ================================================================
# WeatherTool
# ================================================================

class TestWeatherTool:

    @patch("mikalia.tools.weather.requests.get")
    def test_weather_success(self, mock_get):
        """Consulta de clima exitosa con respuesta JSON completa."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_wttr_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WeatherTool()
        result = tool.execute(city="Monterrey")

        assert result.success
        assert "Monterrey" in result.output
        assert "32" in result.output  # temperatura
        assert "Mexico" in result.output
        assert "60" in result.output  # humedad
        assert "Parcialmente nublado" in result.output

    @patch("mikalia.tools.weather.requests.get")
    def test_default_city_monterrey(self, mock_get):
        """Sin parametro city, usa Monterrey como default."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_wttr_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WeatherTool()
        result = tool.execute()

        assert result.success
        # Verifica que la URL usada contiene Monterrey
        call_args = mock_get.call_args
        url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "Monterrey" in url_called

    @patch("mikalia.tools.weather.requests.get")
    def test_timeout_error(self, mock_get):
        """Timeout retorna error claro."""
        import requests as req
        mock_get.side_effect = req.Timeout("Connection timed out")

        tool = WeatherTool()
        result = tool.execute(city="Tokyo")

        assert not result.success
        assert "timeout" in result.error.lower()

    @patch("mikalia.tools.weather.requests.get")
    def test_invalid_response_format(self, mock_get):
        """Respuesta JSON que causa IndexError al parsear retorna error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # current_condition es lista vacia — [0] provocara IndexError
        mock_resp.json.return_value = {
            "current_condition": [],
            "nearest_area": [],
            "weather": [],
        }
        mock_get.return_value = mock_resp

        tool = WeatherTool()
        result = tool.execute(city="InvalidCity")

        assert not result.success
        assert "error" in result.error.lower() or "parse" in result.error.lower()

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = WeatherTool()

        assert tool.name == "weather"
        assert "weather" in tool.description.lower() or "clima" in tool.description.lower()

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "city" in params["properties"]
        assert "lang" in params["properties"]
        assert params["required"] == []

        defn = tool.to_claude_definition()
        assert defn["name"] == "weather"
        assert "input_schema" in defn
        assert "description" in defn

    @patch("mikalia.tools.weather.requests.get")
    def test_custom_language(self, mock_get):
        """Lang personalizado se pasa en la URL y se usa para la descripcion."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_wttr_response(
            city="Paris",
            country="France",
            description="Ensoleille",
            lang="fr",
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WeatherTool()
        result = tool.execute(city="Paris", lang="fr")

        assert result.success
        assert "Paris" in result.output
        # Verifica que la URL incluye lang=fr
        call_args = mock_get.call_args
        url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "lang=fr" in url_called
