"""
validators.py -- Validacion de contenido y metadata para posts de Mikalia.

Este modulo contiene funciones para validar que el contenido generado
por Mikalia cumple con los requisitos del blog antes de publicar.

Hay tres tipos de validacion:
1. Front matter YAML: que la metadata de Hugo sea valida y completa
2. Contenido del post: que no este vacio, tenga firma, longitud razonable
3. Slug: que sea un slug URL-friendly valido

Cada funcion retorna una tupla (es_valido, mensaje_de_error).
Si es_valido es True, el mensaje sera una cadena vacia.
Si es_valido es False, el mensaje explica que salio mal.

Por que tuplas y no excepciones?
    Las validaciones no son errores fatales. Un post puede fallar
    validacion y el flujo debe decidir que hacer (corregir, advertir,
    o rechazar). Excepciones forzarian try/except en todos lados.

Uso:
    from mikalia.utils.validators import (
        validate_front_matter,
        validate_post_content,
        validate_slug,
    )

    valido, error = validate_front_matter(datos)
    if not valido:
        print(f"Front matter invalido: {error}")

    valido, error = validate_post_content(contenido)
    if not valido:
        print(f"Contenido invalido: {error}")
"""

from __future__ import annotations

import re
from typing import Any


# =====================================================================
# Constantes de validacion
# =====================================================================

# Campos obligatorios en el front matter de Hugo.
# Sin estos campos, Hugo no puede renderizar el post correctamente.
REQUIRED_FRONT_MATTER_FIELDS: list[str] = [
    "title",
    "date",
    "description",
    "tags",
    "categories",
]

# Categorias validas del blog (deben coincidir con config.yaml).
# Si alguien agrega una categoria nueva, debe actualizar ambos lugares.
VALID_CATEGORIES: list[str] = [
    "ai",
    "dev-journal",
    "tutorials",
    "project-updates",
    "thoughts",
    "technical",
    "stories",
]

# Firma oficial de Mikalia que debe aparecer al final de cada post.
# Se busca de forma flexible: con o sin negritas markdown.
MIKALIA_SIGNATURE: str = "Mikalia"

# Limites de longitud del contenido en palabras.
# Estos limites son amplios para cubrir tanto posts cortos como deep dives.
MIN_WORD_COUNT: int = 300
MAX_WORD_COUNT: int = 3000

# Patron para slugs validos: solo letras minusculas, numeros y guiones.
# Ejemplos validos: "building-ai-agents", "post-1", "como-usar-claude"
# Ejemplos invalidos: "Building AI", "post_1", "hola--mundo"
SLUG_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Longitud maxima de un slug (para URLs amigables y nombres de directorio).
MAX_SLUG_LENGTH: int = 50


# =====================================================================
# Validacion de front matter YAML
# =====================================================================

def validate_front_matter(data: dict[str, Any]) -> tuple[bool, str]:
    """
    Valida que un diccionario de front matter tenga todos los campos
    requeridos por Hugo y que sus valores sean correctos.

    El front matter es el bloque YAML al inicio de cada archivo .md
    que Hugo usa para metadata (titulo, fecha, tags, etc.).
    Esta funcion verifica:
    - Que existan todos los campos obligatorios
    - Que el titulo no este vacio ni sea demasiado largo
    - Que la fecha tenga formato ISO 8601
    - Que los tags sean una lista no vacia
    - Que la categoria sea una de las permitidas

    Args:
        data: Diccionario con los campos del front matter.
              Normalmente viene de parsear el YAML con PyYAML.

    Returns:
        Tupla (es_valido, mensaje_de_error).
        Si es_valido es True, mensaje sera "".
        Si es_valido es False, mensaje explica el problema.

    Ejemplo:
        datos = {
            "title": "Building AI Agents",
            "date": "2026-02-15T10:00:00-06:00",
            "description": "A guide to autonomous agents",
            "tags": ["ai", "agents"],
            "categories": ["ai"],
        }
        valido, error = validate_front_matter(datos)
        assert valido is True
    """
    # --- Verificar que data sea un diccionario ---
    if not isinstance(data, dict):
        return False, "El front matter debe ser un diccionario, no " + type(data).__name__

    # --- Verificar campos obligatorios ---
    # Iteramos sobre la lista de campos requeridos y reportamos
    # el primero que falte. Esto da mensajes de error claros.
    for campo in REQUIRED_FRONT_MATTER_FIELDS:
        if campo not in data:
            return False, f"Falta el campo obligatorio: '{campo}'"

    # --- Validar titulo ---
    # El titulo es lo primero que ve el lector y aparece en SEO.
    # Debe ser una cadena no vacia y de longitud razonable.
    titulo = data["title"]
    if not isinstance(titulo, str) or not titulo.strip():
        return False, "El titulo no puede estar vacio"
    if len(titulo) > 100:
        return False, f"El titulo es demasiado largo ({len(titulo)} chars, max 100)"

    # --- Validar fecha ---
    # Hugo espera formato ISO 8601 con timezone.
    # Ejemplo valido: 2026-02-15T10:00:00-06:00
    # Usamos regex porque datetime.fromisoformat no maneja todos los
    # formatos de timezone que Hugo acepta.
    fecha = data["date"]
    if not isinstance(fecha, str):
        return False, "La fecha debe ser una cadena en formato ISO 8601"

    fecha_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"
    )
    if not fecha_pattern.match(fecha):
        return False, (
            f"Formato de fecha invalido: '{fecha}'. "
            "Se espera: YYYY-MM-DDTHH:MM:SS+HH:MM (ISO 8601 con timezone)"
        )

    # --- Validar description ---
    # La descripcion se usa para SEO y previews. Debe existir y no ser
    # absurdamente larga. Hugo no la requiere pero nuestro blog si.
    descripcion = data.get("description", "")
    if isinstance(descripcion, str) and len(descripcion) > 200:
        return False, f"La descripcion es demasiado larga ({len(descripcion)} chars, max 200)"

    # --- Validar tags ---
    # Los tags deben ser una lista con al menos un elemento.
    # Cada tag debe ser una cadena no vacia.
    tags = data["tags"]
    if not isinstance(tags, list) or len(tags) == 0:
        return False, "Los tags deben ser una lista con al menos un elemento"
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            return False, f"Tag invalido encontrado: '{tag}'. Cada tag debe ser texto no vacio"

    # --- Validar categories ---
    # Las categorias deben ser una lista. Verificamos que cada una
    # este en la lista de categorias validas del blog.
    categorias = data["categories"]
    if not isinstance(categorias, list) or len(categorias) == 0:
        return False, "Las categorias deben ser una lista con al menos un elemento"
    for cat in categorias:
        if cat not in VALID_CATEGORIES:
            cats_validas = ", ".join(VALID_CATEGORIES)
            return False, (
                f"Categoria invalida: '{cat}'. "
                f"Las categorias validas son: {cats_validas}"
            )

    # Si llegamos aqui, todo esta bien
    return True, ""


# =====================================================================
# Validacion de contenido del post
# =====================================================================

def validate_post_content(content: str) -> tuple[bool, str]:
    """
    Valida que el contenido de un post cumpla con los requisitos minimos
    de calidad antes de ser publicado.

    Esta funcion verifica tres cosas fundamentales:
    1. Que el contenido no este vacio (un post sin contenido no sirve)
    2. Que contenga la firma de Mikalia (identidad de marca)
    3. Que la longitud sea razonable (ni muy corto ni excesivamente largo)

    El conteo de palabras es aproximado (split por espacios) pero
    suficiente para detectar posts demasiado cortos o largos.

    Args:
        content: Contenido markdown del post (sin front matter).
                 Puede ser la version EN o ES.

    Returns:
        Tupla (es_valido, mensaje_de_error).
        Si es_valido es True, mensaje sera "".
        Si es_valido es False, mensaje explica el problema.

    Ejemplo:
        contenido = "## Intro\\nEste es un post...\\n\\n--- **Mikalia**"
        valido, error = validate_post_content(contenido)
    """
    # --- Verificar que sea un string ---
    if not isinstance(content, str):
        return False, "El contenido debe ser una cadena de texto"

    # --- Verificar que no este vacio ---
    # strip() elimina espacios y newlines al inicio/final.
    # Un post vacio o solo con espacios no tiene sentido publicar.
    texto_limpio = content.strip()
    if not texto_limpio:
        return False, "El contenido del post esta vacio"

    # --- Verificar firma de Mikalia ---
    # Buscamos "Mikalia" en el contenido de forma flexible.
    # La firma puede aparecer como:
    #   *Stay curious~ * -- **Mikalia**
    #   -- Mikalia
    #   --- **Mikalia**
    # Lo importante es que aparezca el nombre cerca del final.
    # Buscamos en los ultimos 200 caracteres para no dar falso positivo
    # si el nombre aparece en el cuerpo del texto.
    ultimos_chars = texto_limpio[-200:]
    if MIKALIA_SIGNATURE not in ultimos_chars:
        return False, (
            "No se encontro la firma de Mikalia al final del post. "
            "El post debe terminar con la firma oficial."
        )

    # --- Verificar longitud ---
    # Contamos palabras de forma simple: dividimos por espacios.
    # No es perfecto (cuenta markdown como "##" como palabras)
    # pero es suficiente para detectar extremos.
    palabras = texto_limpio.split()
    num_palabras = len(palabras)

    if num_palabras < MIN_WORD_COUNT:
        return False, (
            f"El post es demasiado corto ({num_palabras} palabras, "
            f"minimo {MIN_WORD_COUNT}). "
            "Considera expandir el contenido con mas ejemplos o explicaciones."
        )

    if num_palabras > MAX_WORD_COUNT:
        return False, (
            f"El post es demasiado largo ({num_palabras} palabras, "
            f"maximo {MAX_WORD_COUNT}). "
            "Considera dividirlo en una serie de posts o recortar secciones."
        )

    # Todo bien
    return True, ""


# =====================================================================
# Validacion de slug
# =====================================================================

def validate_slug(slug: str) -> tuple[bool, str]:
    """
    Valida que un slug sea apto para usarse como URL y nombre de directorio.

    El slug es la parte de la URL que identifica al post:
        https://mikata-ai-lab.github.io/blog/{slug}/

    Tambien se usa como nombre del directorio del page bundle de Hugo:
        content/blog/{slug}/index.md

    Por eso debe cumplir reglas estrictas:
    - Solo letras minusculas (a-z), numeros (0-9) y guiones (-)
    - No puede empezar ni terminar con guion
    - No puede tener guiones consecutivos (--)
    - Maximo 50 caracteres
    - No puede estar vacio

    Args:
        slug: El slug a validar (ej: "building-ai-agents").

    Returns:
        Tupla (es_valido, mensaje_de_error).
        Si es_valido es True, mensaje sera "".
        Si es_valido es False, mensaje explica el problema.

    Ejemplo:
        valido, error = validate_slug("building-ai-agents")
        assert valido is True

        valido, error = validate_slug("Building AI Agents!")
        assert valido is False
    """
    # --- Verificar que sea un string ---
    if not isinstance(slug, str):
        return False, "El slug debe ser una cadena de texto"

    # --- Verificar que no este vacio ---
    if not slug:
        return False, "El slug no puede estar vacio"

    # --- Verificar longitud maxima ---
    # URLs muy largas son feas, dificiles de compartir, y algunos
    # sistemas de archivos tienen limites de longitud de ruta.
    if len(slug) > MAX_SLUG_LENGTH:
        return False, (
            f"El slug es demasiado largo ({len(slug)} chars, "
            f"maximo {MAX_SLUG_LENGTH})"
        )

    # --- Verificar formato con regex ---
    # El patron exige: empieza con alfanumerico, puede tener segmentos
    # separados por UN guion, termina con alfanumerico.
    # Esto automaticamente rechaza: guiones dobles, guiones al
    # inicio/final, mayusculas, caracteres especiales.
    if not SLUG_PATTERN.match(slug):
        # Dar un mensaje de error mas especifico segun el problema
        if slug != slug.lower():
            return False, (
                f"El slug contiene mayusculas: '{slug}'. "
                "Los slugs deben ser completamente en minusculas."
            )
        if "--" in slug:
            return False, (
                f"El slug contiene guiones consecutivos: '{slug}'. "
                "Usa solo un guion entre palabras."
            )
        if slug.startswith("-") or slug.endswith("-"):
            return False, (
                f"El slug empieza o termina con guion: '{slug}'. "
                "Los guiones solo van entre palabras."
            )
        # Caso general: caracteres no permitidos
        chars_invalidos = set(re.findall(r"[^a-z0-9-]", slug))
        return False, (
            f"El slug contiene caracteres invalidos: {chars_invalidos}. "
            "Solo se permiten letras minusculas (a-z), numeros (0-9) y guiones (-)."
        )

    # Slug valido
    return True, ""
