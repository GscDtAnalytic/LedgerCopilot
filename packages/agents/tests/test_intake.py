"""Tests for the Intake agent (Agent 1) — type, language, parse strategy, scope."""

from __future__ import annotations

from packages.agents.intake import (
    classify_document_type,
    detect_language,
    run_intake,
)
from packages.domain.enums import DocumentType


def test_classify_invoice_default():
    dt, reason = classify_document_type("nota_acme.pdf", b"%PDF-1.4", "application/pdf")
    assert dt == DocumentType.INVOICE
    assert reason is None


def test_classify_boleto_and_receipt_by_filename():
    assert classify_document_type("boleto_123.pdf", b"%PDF", "application/pdf")[0] == (
        DocumentType.BOLETO
    )
    assert classify_document_type("comprovante.png", b"\x89PNG", "image/png")[0] == (
        DocumentType.RECEIPT
    )


def test_unsupported_content_is_out_of_scope():
    dt, reason = classify_document_type("clip.mp4", b"\x00\x00\x00\x18", "video/mp4")
    assert dt == DocumentType.OUT_OF_SCOPE
    assert reason is not None and "unsupported_content_type" in reason


def test_pdf_magic_bytes_accepted_even_with_generic_content_type():
    dt, reason = classify_document_type("upload.bin", b"%PDF-1.7 ...", "application/octet-stream")
    assert dt == DocumentType.INVOICE
    assert reason is None


def test_detect_language_portuguese():
    text = "Nota Fiscal Eletrônica. Fornecedor: Aço Forte Ltda. Valor total R$ 1.200,00."
    assert detect_language(text) == "pt"


def test_detect_language_english():
    text = "Invoice. Supplier: ACME Inc. Total amount 1,200.00. Due date 2026-01-01."
    assert detect_language(text) == "en"


def test_detect_language_unknown_when_no_signal():
    assert detect_language("1234 5678 9012") == "unknown"
    assert detect_language("") == "unknown"


def test_run_intake_bundles_everything():
    result = run_intake(
        filename="boleto.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
        text="Boleto bancário. Vencimento 2026-02-01. Valor total R$ 90,00.",
        ocr_confidence=0.55,
        ocr_is_low_quality=True,
    )
    assert result.document_type == DocumentType.BOLETO
    assert result.language == "pt"
    assert result.parse_strategy == "pdf"
    assert result.is_low_quality is True
    assert result.quality_confidence == 0.55
