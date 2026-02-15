"""
client.py — Wrapper del SDK de Anthropic para la Claude API.

Este archivo encapsula TODA la comunicación con Claude.

¿Por qué un wrapper en vez de usar el SDK directamente?
    1. No repetir configuración en cada llamada (model, max_tokens, etc.)
    2. Manejar errores de API de forma centralizada
    3. Facilitar testing con mocks (solo mockeas MikaliaClient)
    4. Agregar retry automático con backoff exponencial
    5. Logging de cada llamada para debugging

Conceptos clave de la Anthropic API:
    - anthropic.Anthropic(): Crea el cliente principal
    - client.messages.create(): Envía un mensaje a Claude
    - system: Instrucciones base (personalidad de Mikalia)
    - messages: Lista de mensajes usuario/asistente
    - max_tokens: Límite de la respuesta (4096 ≈ ~3000 palabras)
    - temperature: Creatividad (0.0=determinista, 1.0=muy creativo)

Uso:
    from mikalia.generation.client import MikaliaClient
    client = MikaliaClient(api_key="sk-ant-...", personality=personality)
    respuesta = client.generate("Escribe sobre agentes de IA")
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import anthropic
from rich.console import Console

from mikalia.personality import Personality

# Consola de Rich para output bonito
console = Console()


@dataclass
class APIResponse:
    """
    Respuesta procesada de la Claude API.

    Attributes:
        content: Texto de la respuesta
        model: Modelo que generó la respuesta
        input_tokens: Tokens usados en el prompt
        output_tokens: Tokens generados en la respuesta
        stop_reason: Razón por la que Claude dejó de generar
    """
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


class MikaliaClient:
    """
    Cliente wrapper para la Anthropic API.

    Encapsula la configuración y manejo de errores para que
    el resto del código solo necesite llamar generate() o review().

    Args:
        api_key: Clave de API de Anthropic (sk-ant-...)
        model: Modelo a usar (default: claude-sonnet-4-5-20250929)
        personality: Personalidad cargada (system prompt)
        max_retries: Número máximo de reintentos ante errores (default: 3)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
        personality: Personality | None = None,
        max_retries: int = 3,
    ):
        # Validar que tenemos API key
        if not api_key:
            raise ValueError(
                "No se proporcionó API key de Anthropic.\n"
                "Configura ANTHROPIC_API_KEY en tu archivo .env"
            )

        # Crear el cliente de Anthropic
        # El SDK se encarga de la conexión HTTP, headers, etc.
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._personality = personality
        self._max_retries = max_retries

        # System prompt: si hay personalidad, usarla; si no, string vacío
        self._system_prompt = personality.system_prompt if personality else ""

    def generate(
        self,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_override: str | None = None,
    ) -> APIResponse:
        """
        Genera contenido usando Claude API.

        Este es el método principal para CREAR contenido (posts, traducciones).
        Usa temperatura alta (0.7) para más creatividad.

        Args:
            user_prompt: Lo que le pedimos a Claude (el tema, instrucciones, etc.)
            temperature: Creatividad (0.7 para contenido, 0.3 para revisión)
            max_tokens: Límite de la respuesta
            system_override: System prompt alternativo (ignora MIKALIA.md)

        Returns:
            APIResponse con el contenido generado y metadata.

        Ejemplo:
            respuesta = client.generate(
                "Escribe un post sobre agentes de IA en desarrollo de software"
            )
            print(respuesta.content)
        """
        # El system prompt puede ser el de MIKALIA.md o uno custom
        system = system_override or self._system_prompt

        return self._call_api(
            system=system,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def review(
        self,
        content: str,
        review_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> APIResponse:
        """
        Revisa contenido usando Claude API con temperatura baja.

        Este método es para EVALUAR contenido (self-review).
        Usa temperatura baja (0.3) para ser más analítico y consistente.

        Args:
            content: El contenido a revisar
            review_prompt: Instrucciones de revisión (criterios, formato)
            temperature: Creatividad baja para análisis (0.3 por default)
            max_tokens: Límite de la respuesta de revisión

        Returns:
            APIResponse con el resultado de la revisión.
        """
        # Para review, combinamos el contenido y las instrucciones
        prompt_completo = f"{review_prompt}\n\n---\n\n{content}"

        return self._call_api(
            system="Eres una editora exigente pero justa. Revisa contenido con ojo crítico.",
            user_prompt=prompt_completo,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _call_api(
        self,
        system: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> APIResponse:
        """
        Hace la llamada real a la Anthropic API con retry automático.

        ¿Por qué retry con backoff exponencial?
        Porque las APIs pueden fallar temporalmente por:
        - Rate limiting (muchas llamadas muy rápido)
        - Errores de servidor (500, 503)
        - Timeouts de red

        Backoff exponencial: espera 1s, luego 2s, luego 4s...
        Esto evita saturar la API con reintentos inmediatos.

        Args:
            system: System prompt (personalidad o instrucciones)
            user_prompt: Mensaje del usuario
            temperature: Creatividad
            max_tokens: Límite de respuesta

        Returns:
            APIResponse con el resultado.

        Raises:
            anthropic.APIError: Si todos los reintentos fallan.
        """
        ultimo_error = None

        for intento in range(self._max_retries):
            try:
                # La llamada real a Claude
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ],
                )

                # Extraer el texto de la respuesta
                # Claude puede devolver múltiples bloques de contenido,
                # pero para texto simple siempre es el primero
                texto = response.content[0].text

                return APIResponse(
                    content=texto,
                    model=response.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stop_reason=response.stop_reason,
                )

            except anthropic.RateLimitError as e:
                # Rate limiting: esperar más tiempo
                ultimo_error = e
                tiempo_espera = (2 ** intento) * 2  # 2s, 4s, 8s
                console.print(
                    f"[yellow]⏳ Rate limit alcanzado. "
                    f"Esperando {tiempo_espera}s (intento {intento + 1}/{self._max_retries})...[/yellow]"
                )
                time.sleep(tiempo_espera)

            except anthropic.APIStatusError as e:
                # Errores de servidor (500, 503, etc.)
                ultimo_error = e
                if e.status_code >= 500:
                    tiempo_espera = 2 ** intento  # 1s, 2s, 4s
                    console.print(
                        f"[yellow]⚠️ Error del servidor ({e.status_code}). "
                        f"Reintentando en {tiempo_espera}s...[/yellow]"
                    )
                    time.sleep(tiempo_espera)
                else:
                    # Errores 4xx (bad request, auth, etc.) no se reintentan
                    raise

            except anthropic.APIConnectionError as e:
                # Error de red
                ultimo_error = e
                tiempo_espera = 2 ** intento
                console.print(
                    f"[yellow]🌐 Error de conexión. "
                    f"Reintentando en {tiempo_espera}s...[/yellow]"
                )
                time.sleep(tiempo_espera)

        # Si llegamos aquí, todos los reintentos fallaron
        raise ultimo_error  # type: ignore[misc]
