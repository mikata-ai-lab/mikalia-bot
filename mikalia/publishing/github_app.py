"""
github_app.py — Mikalia se autentica como GitHub App.

¿Por qué GitHub App en vez de Personal Access Token (PAT)?
    1. Permisos granulares: solo lo que Mikalia necesita
    2. No está atada a una cuenta personal
    3. Se puede revocar sin afectar la cuenta de Mikata
    4. Más profesional y seguro para el portafolio
    5. Los commits aparecen como "Mikalia [bot]"

Flujo de autenticación (JWT → Installation Token):
    1. Leer private key (.pem) del .env
    2. Generar JWT firmado con RS256 (válido 10 min)
    3. Intercambiar JWT por Installation Access Token (válido 1 hora)
    4. Usar el token para operaciones Git/API
    5. Renovar automáticamente cuando expire

Permisos necesarios al crear la GitHub App:
    - contents: write (push commits)
    - pull_requests: write (crear PRs en F3)
    - issues: write (comentarios en PRs)
    - metadata: read

Setup detallado en: docs/SETUP_GITHUB_APP.md

Uso:
    from mikalia.publishing.github_app import GitHubApp
    app = GitHubApp(app_id, private_key_path, installation_id)
    token = app.get_token()
    url = app.get_authenticated_url("mikata-ai-lab/mikata-ai-lab.github.io")
"""

from __future__ import annotations

import time
from pathlib import Path

import jwt
import requests

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.github")


class GitHubApp:
    """
    Gestiona la autenticación como GitHub App.

    La autenticación de GitHub Apps tiene dos pasos:
    1. JWT: Token temporal firmado con la private key de la App
    2. Installation Token: Token real que se usa para la API

    El JWT dura 10 minutos (suficiente para obtener el installation token).
    El installation token dura 1 hora (suficiente para operaciones normales).

    Args:
        app_id: ID numérico de la GitHub App
        private_key_path: Ruta al archivo .pem con la private key
        installation_id: ID de la instalación en la organización
    """

    # URL base de la API de GitHub
    API_BASE = "https://api.github.com"

    def __init__(
        self,
        app_id: str,
        private_key_path: str,
        installation_id: str,
    ):
        self._app_id = app_id
        self._private_key_path = Path(private_key_path)
        self._installation_id = installation_id

        # Cache del token para no regenerar en cada llamada
        self._token: str | None = None
        self._token_expires_at: float = 0

        # Cargar la private key
        self._private_key = self._load_private_key()

    def _load_private_key(self) -> str:
        """
        Carga la private key desde el archivo .pem.

        La private key se genera al crear la GitHub App y se
        descarga como archivo .pem. NUNCA debe subirse a Git.

        Returns:
            Contenido de la private key como string.

        Raises:
            FileNotFoundError: Si el archivo .pem no existe.
        """
        # Si la key viene como variable de entorno (GitHub Actions),
        # viene como string directo, no como path
        if not self._private_key_path.exists():
            # Intentar como string directo (para CI/CD)
            key_str = str(self._private_key_path)
            if key_str.startswith("-----BEGIN"):
                return key_str
            raise FileNotFoundError(
                f"No se encontró la private key en: {self._private_key_path}\n"
                "Descárgala desde la configuración de tu GitHub App.\n"
                "Ver: docs/SETUP_GITHUB_APP.md"
            )

        return self._private_key_path.read_text(encoding="utf-8")

    def _generate_jwt(self) -> str:
        """
        Genera un JWT (JSON Web Token) firmado con RS256.

        El JWT es como un "pase temporal" que le dice a GitHub:
        "Soy la app con ID X y puedo demostrarlo porque tengo la private key."

        Campos del JWT:
        - iss: ID de la app (issuer = quién firma)
        - iat: Tiempo actual - 60s (issued at, con margen)
        - exp: Tiempo actual + 10min (expires, tiempo de vida)

        RS256 = RSA con SHA-256. Es un algoritmo de firma asimétrica:
        - Firmamos con la private key (que solo nosotros tenemos)
        - GitHub verifica con la public key (que ellos tienen)

        Returns:
            JWT firmado como string.
        """
        ahora = int(time.time())

        payload = {
            "iss": self._app_id,        # Quién firma (nuestra app)
            "iat": ahora - 60,           # Cuándo se creó (con margen de 60s)
            "exp": ahora + (10 * 60),    # Cuándo expira (10 minutos)
        }

        # Firmar con RS256 usando nuestra private key
        token = jwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
        )

        return token

    def get_token(self) -> str:
        """
        Obtiene un Installation Access Token válido.

        Si ya tenemos un token que no ha expirado, lo reutilizamos.
        Si no, generamos uno nuevo:
        1. Crear JWT
        2. Intercambiar JWT por Installation Token via API
        3. Cachear el token con su tiempo de expiración

        Returns:
            Installation Access Token listo para usar.

        Raises:
            RuntimeError: Si la autenticación falla.
        """
        # Si el token actual es válido, reutilizar
        if self._token and time.time() < self._token_expires_at:
            return self._token

        # Generar nuevo JWT
        jwt_token = self._generate_jwt()

        # Intercambiar JWT por Installation Token
        url = (
            f"{self.API_BASE}/app/installations/"
            f"{self._installation_id}/access_tokens"
        )
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            response = requests.post(url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(
                f"Error al obtener Installation Token: {e}\n"
                "Verifica que GITHUB_APP_ID, INSTALLATION_ID y "
                "la private key sean correctos."
            ) from e

        data = response.json()
        self._token = data["token"]

        # El token dura 1 hora, pero renovamos 5 min antes para margen
        self._token_expires_at = time.time() + (55 * 60)

        logger.success("Autenticación GitHub App exitosa")
        return self._token  # type: ignore[return-value]

    def get_authenticated_url(self, repo: str) -> str:
        """
        Genera una URL de Git autenticada para push/pull.

        En vez de usar SSH o credenciales del usuario, construimos
        una URL HTTPS con el token de la GitHub App embebido.

        Formato: https://x-access-token:{TOKEN}@github.com/{repo}.git

        Args:
            repo: Repo en formato "owner/name" (ej: "mikata-ai-lab/mikata-ai-lab.github.io")

        Returns:
            URL autenticada para git remote.
        """
        token = self.get_token()
        return f"https://x-access-token:{token}@github.com/{repo}.git"

    def is_configured(self) -> bool:
        """
        Verifica si la GitHub App está configurada correctamente.

        Útil para el comando `mikalia health` que verifica
        que todas las conexiones funcionen.

        Returns:
            True si la configuración parece completa.
        """
        return bool(
            self._app_id
            and self._installation_id
            and self._private_key
        )
