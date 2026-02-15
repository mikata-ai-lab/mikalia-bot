"""
doc_analyzer.py — Mikalia lee documentos y extrae conocimiento.

Soporta múltiples formatos:
    - .md / .txt → lectura directa
    - .pdf → extracción con pdfplumber
    - .docx → extracción con python-docx
    - .yaml / .yml → parseo estructurado
    - .json → parseo estructurado

El objetivo es extraer contenido relevante y pasarlo como
contexto al generador de posts para crear contenido más
informado y preciso.

¿Por qué no pasar el archivo completo?
    Algunos documentos son enormes (PDFs de 100+ páginas).
    Necesitamos extraer lo relevante y respetar el límite
    de tokens del modelo.

¿Por qué soportar tantos formatos?
    Porque la documentación técnica viene en todos los formatos.
    Mikata-kun podría querer que Mikalia escriba un post basado
    en un PDF de una conferencia, un README de un proyecto,
    o un documento de arquitectura en YAML.

Uso:
    from mikalia.generation.doc_analyzer import DocAnalyzer
    analyzer = DocAnalyzer()
    context = analyzer.analyze("docs/architecture.md")
    # Luego pasas context.to_prompt() al post_generator
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.doc_analyzer")

# Formatos soportados y sus handlers
SUPPORTED_FORMATS = {
    ".md": "markdown",
    ".txt": "text",
    ".pdf": "pdf",
    ".docx": "docx",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".rst": "text",
    ".csv": "text",
}


@dataclass
class DocContext:
    """
    Contexto extraído de un documento.

    Contiene el contenido procesado del documento listo para
    ser usado como contexto en la generación de posts.

    Campos:
        doc_name: Nombre del archivo
        doc_format: Formato del documento (md, pdf, docx, etc.)
        content: Contenido completo extraído
        summary: Resumen corto (primeros ~500 chars)
        key_sections: Secciones principales identificadas
        total_chars: Longitud total del contenido
    """
    doc_name: str
    doc_format: str = ""
    content: str = ""
    summary: str = ""
    key_sections: list[str] = field(default_factory=list)
    total_chars: int = 0

    def to_prompt(self, max_tokens: int = 8000) -> str:
        """
        Convierte el contexto del documento a texto para el prompt.

        Incluye el contenido del documento con metadata,
        truncado al límite de tokens especificado.

        Args:
            max_tokens: Límite aproximado de caracteres (~4 chars/token)

        Returns:
            String formateado para incluir en el prompt de generación.
        """
        partes = []

        partes.append(f"=== Document: {self.doc_name} ===")
        partes.append(f"Format: {self.doc_format}")
        partes.append(f"Length: {self.total_chars} characters")

        if self.key_sections:
            partes.append(f"Sections: {', '.join(self.key_sections)}")

        max_chars = max_tokens * 4
        contenido = self.content[:max_chars]
        if len(self.content) > max_chars:
            contenido += "\n... (document truncated for brevity)"

        partes.append(f"\n--- Content ---\n{contenido}")

        return "\n".join(partes)


class DocAnalyzer:
    """
    Analiza documentos en varios formatos y extrae contexto.

    Detecta automáticamente el formato del archivo por su
    extensión y usa el handler apropiado para extraer texto.
    """

    def analyze(
        self,
        doc_path: str,
        focus_topic: str | None = None,
    ) -> DocContext:
        """
        Analiza un documento y extrae su contenido como contexto.

        Detecta el formato automáticamente y usa el lector apropiado.

        Args:
            doc_path: Ruta al documento (absoluta o relativa).
            focus_topic: Tema de enfoque (no usado aún, reservado para F3).

        Returns:
            DocContext con el contenido extraído.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            ValueError: Si el formato no es soportado.
        """
        ruta = Path(doc_path).resolve()

        if not ruta.exists():
            raise FileNotFoundError(f"Documento no encontrado: {doc_path}")

        extension = ruta.suffix.lower()
        if extension not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato no soportado: {extension}. "
                f"Formatos válidos: {', '.join(SUPPORTED_FORMATS.keys())}"
            )

        formato = SUPPORTED_FORMATS[extension]
        logger.info(f"Analizando documento: {ruta.name} ({formato})")

        # Leer contenido según el formato
        contenido = self._read_by_format(ruta, formato)

        # Extraer secciones (para markdown y texto)
        secciones = self._extract_sections(contenido, formato)

        # Generar resumen (primeros ~500 chars significativos)
        resumen = self._generate_summary(contenido)

        contexto = DocContext(
            doc_name=ruta.name,
            doc_format=formato,
            content=contenido,
            summary=resumen,
            key_sections=secciones,
            total_chars=len(contenido),
        )

        logger.success(
            f"Documento analizado: {len(contenido)} chars, "
            f"{len(secciones)} secciones"
        )

        return contexto

    def _read_by_format(self, ruta: Path, formato: str) -> str:
        """
        Lee un documento según su formato.

        Cada formato tiene su propio handler porque la extracción
        de texto funciona diferente en cada uno.

        Args:
            ruta: Ruta al archivo.
            formato: Tipo de formato detectado.

        Returns:
            Texto extraído del documento.
        """
        handlers = {
            "markdown": self._read_text,
            "text": self._read_text,
            "pdf": self._read_pdf,
            "docx": self._read_docx,
            "yaml": self._read_yaml,
            "json": self._read_json,
            "toml": self._read_toml,
        }

        handler = handlers.get(formato, self._read_text)
        return handler(ruta)

    def _read_text(self, ruta: Path) -> str:
        """
        Lee archivos de texto plano (md, txt, rst, csv).

        El caso más simple: leer y retornar el contenido.
        Maneja errores de encoding con replace.

        Args:
            ruta: Ruta al archivo.

        Returns:
            Contenido del archivo como string.
        """
        try:
            return ruta.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Error leyendo texto {ruta.name}: {e}")
            return ""

    def _read_pdf(self, ruta: Path) -> str:
        """
        Extrae texto de un archivo PDF usando pdfplumber.

        pdfplumber es mejor que PyPDF2 para extraer texto porque
        maneja mejor layouts complejos, tablas, y columnas.

        Si pdfplumber no está instalado, da un mensaje claro.

        Args:
            ruta: Ruta al archivo PDF.

        Returns:
            Texto extraído del PDF.
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning(
                "pdfplumber no instalado. Instálalo con: pip install pdfplumber"
            )
            return f"[PDF file: {ruta.name} — install pdfplumber to extract text]"

        try:
            paginas_texto = []
            with pdfplumber.open(ruta) as pdf:
                for i, pagina in enumerate(pdf.pages):
                    texto = pagina.extract_text()
                    if texto:
                        paginas_texto.append(f"--- Page {i + 1} ---\n{texto}")

            return "\n\n".join(paginas_texto)
        except Exception as e:
            logger.error(f"Error leyendo PDF {ruta.name}: {e}")
            return f"[Error reading PDF: {e}]"

    def _read_docx(self, ruta: Path) -> str:
        """
        Extrae texto de un archivo .docx usando python-docx.

        python-docx lee el formato Open XML de Word y extrae
        los párrafos de texto. No extrae imágenes ni estilos,
        solo el texto plano.

        Args:
            ruta: Ruta al archivo .docx.

        Returns:
            Texto extraído del documento Word.
        """
        try:
            from docx import Document
        except ImportError:
            logger.warning(
                "python-docx no instalado. Instálalo con: pip install python-docx"
            )
            return f"[DOCX file: {ruta.name} — install python-docx to extract text]"

        try:
            doc = Document(str(ruta))
            parrafos = []
            for parrafo in doc.paragraphs:
                if parrafo.text.strip():
                    parrafos.append(parrafo.text)
            return "\n\n".join(parrafos)
        except Exception as e:
            logger.error(f"Error leyendo DOCX {ruta.name}: {e}")
            return f"[Error reading DOCX: {e}]"

    def _read_yaml(self, ruta: Path) -> str:
        """
        Lee y formatea un archivo YAML de forma legible.

        En vez de retornar el YAML crudo, lo parseamos y re-formateamos
        para que sea más fácil de leer como contexto.

        Args:
            ruta: Ruta al archivo YAML.

        Returns:
            Contenido YAML formateado.
        """
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            # Parsear y re-formatear para limpieza
            datos = yaml.safe_load(texto)
            if datos:
                return yaml.dump(
                    datos, default_flow_style=False,
                    allow_unicode=True, sort_keys=False,
                )
            return texto
        except Exception as e:
            logger.error(f"Error leyendo YAML {ruta.name}: {e}")
            # Si falla el parseo, retornar el texto crudo
            try:
                return ruta.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""

    def _read_json(self, ruta: Path) -> str:
        """
        Lee y formatea un archivo JSON de forma legible.

        Similar al handler de YAML: parseamos y re-formateamos
        con indentación para legibilidad.

        Args:
            ruta: Ruta al archivo JSON.

        Returns:
            Contenido JSON formateado con indentación.
        """
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            datos = json.loads(texto)
            return json.dumps(datos, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error leyendo JSON {ruta.name}: {e}")
            try:
                return ruta.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""

    def _read_toml(self, ruta: Path) -> str:
        """
        Lee un archivo TOML.

        Python 3.11+ tiene tomllib en la stdlib, pero para
        compatibilidad usamos lectura de texto simple.

        Args:
            ruta: Ruta al archivo TOML.

        Returns:
            Contenido TOML como texto.
        """
        try:
            return ruta.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Error leyendo TOML {ruta.name}: {e}")
            return ""

    def _extract_sections(self, contenido: str, formato: str) -> list[str]:
        """
        Extrae nombres de secciones del documento.

        Para markdown, busca headings (##). Para otros formatos,
        busca patrones similares a secciones.

        Args:
            contenido: Texto del documento.
            formato: Formato del documento.

        Returns:
            Lista de nombres de secciones encontradas.
        """
        secciones = []

        if formato in ("markdown", "text"):
            # Buscar headings de markdown (## Sección)
            for linea in contenido.splitlines():
                linea = linea.strip()
                if linea.startswith("#"):
                    # Remover los # y espacios
                    titulo = linea.lstrip("#").strip()
                    if titulo:
                        secciones.append(titulo)
        elif formato == "yaml":
            # Las keys de primer nivel son como secciones
            try:
                datos = yaml.safe_load(contenido)
                if isinstance(datos, dict):
                    secciones = list(datos.keys())[:20]
            except Exception:
                pass
        elif formato == "json":
            # Similar al YAML
            try:
                datos = json.loads(contenido)
                if isinstance(datos, dict):
                    secciones = list(datos.keys())[:20]
            except Exception:
                pass

        return secciones[:30]  # Máximo 30 secciones

    def _generate_summary(self, contenido: str) -> str:
        """
        Genera un resumen corto del documento.

        Toma las primeras líneas significativas (no vacías,
        no headings) como resumen.

        Args:
            contenido: Texto completo del documento.

        Returns:
            Resumen de ~500 caracteres.
        """
        lineas_significativas = []
        for linea in contenido.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            if linea.startswith("#"):
                continue
            if linea.startswith("---"):
                continue
            lineas_significativas.append(linea)
            if sum(len(l) for l in lineas_significativas) > 500:
                break

        return " ".join(lineas_significativas)[:500]
