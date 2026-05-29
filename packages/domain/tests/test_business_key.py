"""Tests for business-key computation."""

from __future__ import annotations

from packages.domain.business_key import compute_business_key
from packages.domain.entities import ExtractionOutput, FieldValue


def _fields(
    cnpj: str | None = "12.345.678/0001-90",
    doc: str | None = "NF-001",
    total: float | None = 1000.0,
    date: str | None = "2026-05-01",
) -> ExtractionOutput:
    return ExtractionOutput(
        tax_id_cnpj=FieldValue(value=cnpj, confidence=0.95) if cnpj else None,
        document_number=FieldValue(value=doc, confidence=0.95) if doc else None,
        total_amount=FieldValue(value=total, confidence=0.95) if total is not None else None,
        issue_date=FieldValue(value=date, confidence=0.95) if date else None,
    )


def test_full_fields_produces_key() -> None:
    key = compute_business_key(_fields())
    assert key is not None
    assert "cnpj:" in key
    assert "doc:" in key
    assert "total:" in key
    assert "date:" in key


def test_cnpj_punctuation_stripped() -> None:
    key = compute_business_key(_fields(cnpj="12.345.678/0001-90"))
    assert key is not None
    assert "cnpj:12345678000190" in key

def test_deterministic_same_fields_same_key() -> None:
    key1 = compute_business_key(_fields())
    key2 = compute_business_key(_fields())
    assert key1 == key2


def test_different_cnpj_different_key() -> None:
    key1 = compute_business_key(_fields(cnpj="12.345.678/0001-90"))
    key2 = compute_business_key(_fields(cnpj="99.999.999/0001-99"))
    assert key1 != key2


def test_missing_cnpj_returns_none() -> None:
    assert compute_business_key(_fields(cnpj=None)) is None


def test_missing_document_number_returns_none() -> None:
    assert compute_business_key(_fields(doc=None)) is None


def test_missing_total_returns_none() -> None:
    assert compute_business_key(_fields(total=None)) is None


def test_missing_date_still_produces_key() -> None:
    # issue_date is optional — key without |date: part is still valid.
    key = compute_business_key(_fields(date=None))
    assert key is not None
    assert "date:" not in key

def test_total_normalised_to_two_decimal_places() -> None:
    key1 = compute_business_key(_fields(total=1000.0))
    key2 = compute_business_key(_fields(total=1000))
    assert key1 is not None
    assert key1 == key2
    assert "total:1000.00" in key1

def test_invalid_cnpj_length_returns_none() -> None:
    # 13-digit CNPJ is invalid — should return None.
    assert compute_business_key(_fields(cnpj="1234567800019")) is None


def test_doc_number_case_insensitive() -> None:
    key1 = compute_business_key(_fields(doc="NF-001"))
    key2 = compute_business_key(_fields(doc="nf-001"))
    assert key1 == key2
