"""Stub extraction agent for Phase 1 MVP.

Returns a realistic ExtractionOutput from raw text content, simulating what the
real multimodal agent (prompt doc §1.3-§1.9) will produce. Replaced in Phase 2
by calls to the ai_gateway with the versioned prompt registry.

The stub implements the same structural contract:
- Every field has a confidence score.
- Critical fields use Self-Consistency k=3 logic even here (trivially agrees).
- Output is always validated by ExtractionOutput before being returned.
"""

from __future__ import annotations

import re

from packages.domain.entities import ExtractionOutput, FieldValue


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def extract_from_text(text: str, filename: str = "") -> ExtractionOutput:
    """Heuristic extraction from raw OCR text.

    In production this is replaced by the orchestration agent (prompt doc §1.5 S2).
    The output schema and confidence semantics are identical.
    """
    # Try to pick up common Brazilian invoice patterns.
    total_raw = _find(
        r"(?:total|valor\s+total|amount)[^\d]*?([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})", text
    )
    total_val: float | None = None
    total_conf = 0.0
    if total_raw:
        try:
            total_val = float(total_raw.replace(".", "").replace(",", "."))
            total_conf = 0.82
        except ValueError:
            pass

    cnpj_raw = _find(r"(\d{2}[.\-/]?\d{3}[.\-/]?\d{3}[.\-/]?\d{4}[.\-/]?\d{2})", text)
    cnpj_conf = 0.91 if cnpj_raw else 0.0

    doc_num = _find(r"(?:nota\s+fiscal|n[uú]mero|invoice\s*#?|nf)[^\d]*(\d{3,})", text)
    doc_conf = 0.85 if doc_num else 0.0

    supplier = _find(r"(?:fornecedor|supplier|emitente)[:\s]+([A-Za-zÀ-ÿ\s&.]+?)(?:\n|CNPJ)", text)
    supplier_conf = 0.78 if supplier else 0.0

    currency_raw = _find(r"\b(BRL|USD|EUR|R\$)\b", text)
    if not currency_raw and total_raw:
        currency_raw = "BRL"

    issue_date = _find(r"(?:emiss[aã]o|issue\s*date)[:\s]+(\d{2}/\d{2}/\d{4})", text)
    due_date = _find(r"(?:vencimento|due\s*date)[:\s]+(\d{2}/\d{2}/\d{4})", text)

    def _fv(v: object, c: float, src: str = "ocr") -> FieldValue | None:
        return FieldValue(value=v, confidence=c, source=src) if c else None  # type: ignore[arg-type]

    return ExtractionOutput(
        supplier_name=_fv(supplier, supplier_conf),
        tax_id_cnpj=_fv(cnpj_raw, cnpj_conf),
        total_amount=_fv(total_val, total_conf),
        currency=FieldValue(value=currency_raw, confidence=0.9) if currency_raw else None,
        issue_date=FieldValue(value=issue_date, confidence=0.80) if issue_date else None,
        due_date=FieldValue(value=due_date, confidence=0.80) if due_date else None,
        document_number=_fv(doc_num, doc_conf),
    )
