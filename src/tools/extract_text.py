"""Tool: extract_text — Extrae texto de PDFs e imágenes usando PyMuPDF + Tesseract OCR.

Pipeline:
  1. Si es PDF → intenta extracción nativa con PyMuPDF
  2. Si el PDF no tiene texto (escaneado) → OCR por página con Tesseract
  3. Si es imagen → OCR directo con Tesseract

Dependencias: PyMuPDF, pytesseract, Pillow, tesseract-ocr (sistema)
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# ── Definición para el LLM ────────────────────────────────────────────────

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_text",
        "description": (
            "Extrae el texto de uno o más archivos (PDF, PNG, JPG, JPEG, TIFF, BMP). "
            "Para PDFs con texto nativo lo extrae directamente. "
            "Para PDFs escaneados o imágenes usa OCR (Tesseract). "
            "Devuelve el texto extraído de cada archivo separado por un encabezado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de rutas de archivos a procesar (máx. 10).",
                }
            },
            "required": ["files"],
        },
    }
}

# ── Extensiones soportadas ────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
_PDF_EXTENSION = ".pdf"

_SUPPORTED = _IMAGE_EXTENSIONS | {_PDF_EXTENSION}

# ── Lógica interna ────────────────────────────────────────────────────────


def _is_scanned(pdf_text: str, total_pages: int) -> bool:
    """Un PDF se considera 'escaneado' si tiene muy poco texto por página."""
    if total_pages == 0:
        return True
    text_len = len(pdf_text.strip())
    threshold = total_pages * 20  # menos de ~20 caracteres por página = escaneado
    return text_len < threshold


def _extract_pdf_native(path: str) -> str | None:
    """Extrae texto de un PDF usando PyMuPDF (rápido, sin OCR)."""
    try:
        import fitz
        doc = fitz.open(path)
        num_pages = len(doc)
        pages_text: list[str] = []
        for page_num in range(num_pages):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text and text.strip():
                pages_text.append(f"--- Página {page_num + 1} ---\n{text.strip()}")
        doc.close()

        full_text = "\n\n".join(pages_text)

        if _is_scanned(full_text, num_pages):
            logger.info("PDF parece escaneado (poco texto nativo). Se usará OCR.")
            return None  # señal para fallback OCR

        return full_text if full_text.strip() else None
    except Exception as e:
        logger.warning("Error extrayendo texto nativo de PDF: %s", e)
        return None


def _extract_pdf_ocr(path: str) -> str | None:
    """OCR a un PDF página por página con Tesseract."""
    try:
        import fitz
        from PIL import Image
        import pytesseract

        doc = fitz.open(path)
        pages_text: list[str] = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Renderizar página a imagen (pixmap)
            mat = fitz.Matrix(2, 2)  # 2x para mejor calidad OCR
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            text = pytesseract.image_to_string(img, lang="spa+eng")
            if text and text.strip():
                pages_text.append(f"--- Página {page_num + 1} (OCR) ---\n{text.strip()}")

        doc.close()
        return "\n\n".join(pages_text) if pages_text else None
    except Exception as e:
        logger.error("Error en OCR de PDF: %s", e)
        return None


def _extract_image_ocr(path: str) -> str | None:
    """OCR a una imagen con Tesseract."""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang="spa+eng")
        return text.strip() if text.strip() else None
    except Exception as e:
        logger.error("Error en OCR de imagen: %s", e)
        return None


def _extract_single_file(path: str) -> dict[str, Any]:
    """Procesa un archivo y devuelve resultado con metadata."""
    ext = os.path.splitext(path)[1].lower()
    result: dict[str, Any] = {
        "file": path,
        "status": "error",
        "text": "",
        "method": "",
        "error": "",
    }

    if not os.path.isfile(path):
        result["error"] = "Archivo no encontrado"
        return result

    if ext not in _SUPPORTED:
        result["error"] = f"Formato no soportado: {ext}. Soporta: {', '.join(sorted(_SUPPORTED))}"
        return result

    if ext == _PDF_EXTENSION:
        # Intento 1: extracción nativa
        text = _extract_pdf_native(path)
        if text is not None:
            result["text"] = text
            result["method"] = "pdf_native"
            result["status"] = "ok"
            return result

        # Fallback: OCR
        text = _extract_pdf_ocr(path)
        if text is not None:
            result["text"] = text
            result["method"] = "pdf_ocr"
            result["status"] = "ok"
            return result

        result["error"] = "No se pudo extraer texto (ni nativo ni OCR)"
        return result

    if ext in _IMAGE_EXTENSIONS:
        text = _extract_image_ocr(path)
        if text is not None:
            result["text"] = text
            result["method"] = "image_ocr"
            result["status"] = "ok"
            return result

        result["error"] = "No se pudo extraer texto de la imagen"
        return result

    result["error"] = "Tipo de archivo no procesado"
    return result


# ── Punto de entrada público ──────────────────────────────────────────────


def run(files: list[str], **kwargs: Any) -> str:
    """Extrae texto de archivos PDF/Imagen.

    Args:
        files: Lista de rutas de archivos a procesar (máx. 10).

    Returns:
        Texto formateado con los resultados de cada archivo.
    """
    if not files:
        return "No se especificaron archivos para extraer."

    if len(files) > 10:
        files = files[:10]

    output: list[str] = []
    errors: list[str] = []

    for path in files:
        # Resolver path (~, relative, etc.)
        resolved = os.path.expanduser(os.path.expandvars(path))
        if not os.path.isabs(resolved):
            resolved = os.path.join(os.getcwd(), resolved)

        result = _extract_single_file(resolved)
        filename = os.path.basename(resolved)

        if result["status"] == "ok":
            method_label = {
                "pdf_native": "📄 PDF (texto nativo)",
                "pdf_ocr": "📄 PDF (OCR)",
                "image_ocr": "🖼️ Imagen (OCR)",
            }.get(result["method"], result["method"])

            output.append(f"## {filename} — {method_label}")
            output.append(result["text"])
        else:
            errors.append(f"- {filename}: {result['error']}")

    final: list[str] = []
    if output:
        final.extend(output)
    if errors:
        final.append(f"\n### Errores\n" + "\n".join(errors))

    return "\n\n".join(final) if final else "No se pudo extraer texto de ningún archivo."
