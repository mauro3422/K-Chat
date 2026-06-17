import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.tools.extract_text import (
    DEFINITION,
    _extract_image_ocr,
    _extract_pdf_native,
    _extract_single_file,
    _is_scanned,
    _sync_extract_text,
    run,
)


class TestIsScanned:
    def test_empty_text_returns_true(self):
        assert _is_scanned("", 5) is True

    def test_short_text_returns_true(self):
        assert _is_scanned("hello", 1) is True  # 5 chars < 20

    def test_long_enough_text_returns_false(self):
        assert _is_scanned("a" * 50, 2) is False  # 50 chars >= 40

    def test_zero_pages_returns_true(self):
        assert _is_scanned("", 0) is True


class TestExtractPdfNative:
    @patch("fitz.open")
    def test_returns_text_when_native_successful(self, mock_fitz_open):
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Hello World"
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        result = _extract_pdf_native("/fake/test.pdf")

        assert result == "--- Página 1 ---\nHello World"
        mock_doc.close.assert_called_once()

    @patch("fitz.open")
    def test_returns_none_when_scanned_pdf(self, mock_fitz_open):
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 10
        mock_page = MagicMock()
        mock_page.get_text.return_value = "x"
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        result = _extract_pdf_native("/fake/scanned.pdf")

        assert result is None

    @patch("fitz.open")
    def test_returns_none_on_exception(self, mock_fitz_open):
        mock_fitz_open.side_effect = RuntimeError("corrupt PDF")

        result = _extract_pdf_native("/fake/bad.pdf")

        assert result is None


class TestExtractSingleFile:
    def test_file_not_found(self):
        result = _extract_single_file("/nonexistent/file.pdf")
        assert result["status"] == "error"
        assert result["error"] == "Archivo no encontrado"

    def test_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "error"
            assert "Formato no soportado" in result["error"]
        finally:
            os.unlink(path)

    @patch("src.tools.extract_text._extract_pdf_native")
    def test_pdf_native_success(self, mock_native):
        mock_native.return_value = "--- Página 1 ---\nReal text"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "ok"
            assert result["method"] == "pdf_native"
            assert result["text"] == "--- Página 1 ---\nReal text"
        finally:
            os.unlink(path)

    @patch("src.tools.extract_text._extract_pdf_native")
    @patch("src.tools.extract_text._extract_pdf_ocr")
    def test_pdf_fallback_to_ocr(self, mock_ocr, mock_native):
        mock_native.return_value = None
        mock_ocr.return_value = "--- Página 1 (OCR) ---\nOCR text"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "ok"
            assert result["method"] == "pdf_ocr"
            assert "OCR text" in result["text"]
        finally:
            os.unlink(path)

    @patch("src.tools.extract_text._extract_pdf_native")
    @patch("src.tools.extract_text._extract_pdf_ocr")
    def test_pdf_both_fail(self, mock_ocr, mock_native):
        mock_native.return_value = None
        mock_ocr.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "error"
            assert "No se pudo extraer texto" in result["error"]
        finally:
            os.unlink(path)

    @patch("src.tools.extract_text._extract_image_ocr")
    def test_image_success(self, mock_ocr):
        mock_ocr.return_value = "Image text"

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"dummy")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "ok"
            assert result["method"] == "image_ocr"
            assert result["text"] == "Image text"
        finally:
            os.unlink(path)

    @patch("src.tools.extract_text._extract_image_ocr")
    def test_image_failure(self, mock_ocr):
        mock_ocr.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"dummy")
            path = f.name
        try:
            result = _extract_single_file(path)
            assert result["status"] == "error"
            assert "No se pudo extraer texto de la imagen" in result["error"]
        finally:
            os.unlink(path)


class TestSyncExtractText:
    def test_empty_files_list(self):
        result = _sync_extract_text([])
        assert result == "No se especificaron archivos para extraer."

    def test_truncates_over_10_files(self):
        with patch(
            "src.tools.extract_text._extract_single_file",
            return_value={"status": "error", "error": "not found", "file": "", "text": "", "method": ""},
        ):
            files = [f"/tmp/test_{i}.pdf" for i in range(15)]
            result = _sync_extract_text(files)
            assert "### Errores" in result
            assert len(result.split("test_")) - 1 == 10  # only 10 files processed

    def test_internal_exception_caught(self):
        with patch(
            "src.tools.extract_text._extract_single_file",
            side_effect=RuntimeError("boom"),
        ):
            result = _sync_extract_text(["/tmp/test.pdf"])
            assert "Error interno" in result


class TestRun:
    @pytest.mark.anyio
    async def test_no_files(self):
        result = await run(files=[])
        assert result == "No se especificaron archivos para extraer."

    @pytest.mark.anyio
    async def test_truncates_to_10(self):
        with patch(
            "src.tools.extract_text._sync_extract_text",
            return_value="done",
        ) as mock_sync:
            files = [f"/tmp/t_{i}.pdf" for i in range(15)]
            result = await run(files=files)
            assert result == "done"
            passed = mock_sync.call_args[0][0]
            assert len(passed) == 10

    @pytest.mark.anyio
    async def test_exception_caught(self):
        with patch(
            "src.tools.extract_text._sync_extract_text",
            side_effect=ValueError("oops"),
        ):
            result = await run(files=["/tmp/test.pdf"])
            assert "Error interno" in result

    @pytest.mark.anyio
    async def test_proxies_to_sync(self):
        with patch(
            "src.tools.extract_text._sync_extract_text",
            return_value="## test.png — Imagen (OCR)\nsome text",
        ):
            result = await run(files=["/tmp/test.png"])
            assert "test.png" in result
            assert "some text" in result


class TestDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        assert DEFINITION["function"]["name"] == "extract_text"
        assert "files" in DEFINITION["function"]["parameters"]["properties"]
        assert DEFINITION["function"]["parameters"]["required"] == ["files"]
