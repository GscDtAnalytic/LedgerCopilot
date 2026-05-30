"""Tests for OCR engine routing and confidence semantics."""

from __future__ import annotations

import pytest

from packages.ocr.engine import OcrResult, extract_text


def test_plain_text_route():
    content = b"NOTA FISCAL\nCNPJ: 12.345.678/0001-99\nValor: R$ 1.000,00"
    result = extract_text(content, "text/plain")
    assert result.source == "text"
    assert result.confidence == 1.0
    assert "NOTA FISCAL" in result.text
    assert not result.is_low_quality


def test_xml_route():
    content = b"<?xml version='1.0'?><nfeProc></nfeProc>"
    result = extract_text(content, "application/xml")
    assert result.source == "text"
    assert result.confidence == 1.0


def test_pdf_magic_bytes_routes_to_pdf(monkeypatch):
    """PDF magic bytes trigger PDF route even with wrong content-type."""
    called = []

    def fake_pdf(content):
        called.append(True)
        return OcrResult(text="pdf text", confidence=0.95, source="pdf-text")

    monkeypatch.setattr("packages.ocr.engine._extract_pdf", fake_pdf)
    result = extract_text(b"%PDF-1.4 fake", "application/octet-stream")
    assert called
    assert result.source == "pdf-text"


def test_image_content_type_routes_to_image(monkeypatch):
    def fake_image(content):
        return OcrResult(text="ocr text", confidence=0.75, source="ocr-image")

    monkeypatch.setattr("packages.ocr.engine._extract_image", fake_image)
    result = extract_text(b"\xff\xd8\xff", "image/jpeg")
    assert result.source == "ocr-image"


def test_low_quality_flag():
    result = OcrResult(text="blurry", confidence=0.50, source="ocr-tesseract")
    assert result.is_low_quality

    result_ok = OcrResult(text="clear", confidence=0.80, source="pdf-text")
    assert not result_ok.is_low_quality


def test_pdfplumber_text_pdf(tmp_path):
    """Integration: pdfplumber extracts text from a text-based PDF."""
    try:
        import io

        import pdfplumber  # noqa: F401

        # Build a minimal PDF with embedded text using reportlab if available.
        try:
            from reportlab.pdfgen import canvas as rl_canvas

            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf)
            c.drawString(72, 720, "CNPJ: 12.345.678/0001-99 Valor: 1000.00")
            c.save()
            pdf_bytes = buf.getvalue()
        except ImportError:
            # reportlab not installed — skip the actual PDF content test.
            return

        result = extract_text(pdf_bytes, "application/pdf")
        assert result.source == "pdf-text"
        assert result.confidence >= 0.90
        assert "CNPJ" in result.text or len(result.text) > 10
    except ImportError:
        pytest.skip("pdfplumber not installed")
