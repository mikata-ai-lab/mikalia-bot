"""
weather.py — Clima para Mikalia.

Usa wttr.in (gratis, sin API key) para obtener clima actual.
Util para el daily brief.
"""

from __future__ import annotations

from typing import Any

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.weather")


class WeatherTool(BaseTool):
    """Obtiene el clima actual de una ciudad."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return (
            "Get current weather for a city. Uses wttr.in (free, no API key). "
            "Returns temperature, conditions, humidity, and wind. "
            "Default city: Monterrey (Mikata-kun's city)."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (default: Monterrey)",
                },
                "lang": {
                    "type": "string",
                    "description": "Language for description (default: es)",
                },
            },
            "required": [],
        }

    def execute(
        self, city: str = "Monterrey", lang: str = "es", **_: Any
    ) -> ToolResult:
        try:
            # Formato JSON de wttr.in
            url = f"https://wttr.in/{city}?format=j1&lang={lang}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current_condition", [{}])[0]
            area = data.get("nearest_area", [{}])[0]

            city_name = area.get("areaName", [{"value": city}])[0]["value"]
            country = area.get("country", [{"value": ""}])[0]["value"]

            temp_c = current.get("temp_C", "?")
            feels_like = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            wind_kmph = current.get("windspeedKmph", "?")
            wind_dir = current.get("winddir16Point", "")

            # Descripcion en el idioma pedido
            desc_key = f"lang_{lang}"
            desc_list = current.get(desc_key, current.get("weatherDesc", [{}]))
            description = desc_list[0].get("value", "N/A") if desc_list else "N/A"

            # Pronostico de hoy
            today = data.get("weather", [{}])[0]
            max_temp = today.get("maxtempC", "?")
            min_temp = today.get("mintempC", "?")

            output = (
                f"Clima en {city_name}, {country}:\n"
                f"  Temperatura: {temp_c}°C (sensacion {feels_like}°C)\n"
                f"  Condicion: {description}\n"
                f"  Humedad: {humidity}%\n"
                f"  Viento: {wind_kmph} km/h {wind_dir}\n"
                f"  Min/Max hoy: {min_temp}°C / {max_temp}°C"
            )

            logger.success(f"Clima obtenido: {city_name} {temp_c}°C")
            return ToolResult(success=True, output=output)

        except requests.Timeout:
            return ToolResult(success=False, error="Timeout consultando clima")
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error obteniendo clima: {e}")
        except (KeyError, IndexError) as e:
            return ToolResult(success=False, error=f"Error parseando respuesta: {e}")
