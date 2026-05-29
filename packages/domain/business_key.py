"""Business-key dedup for financial documents.

Computes a deterministic, normalized key from extracted fields so that the same
invoice submitted as different file formats (PDF, scan, re-upload) is still
detected as a duplicate.

Key format:
  cnpj:{14-digit-cnpj}|doc:{normalized-doc-number}|total:{2dp-total}|date:{date}

Returns None when any of the three mandatory fields (CNPJ, doc number, total) is
missing — it is safer to skip dedup than to raise a false-positive collision.

Wiki: (chave natural determinística; anti-padrão de
dedup só por hash de bytes);
(idempotência por chave de acesso).
"""

from __future__ import annotations

import re

from packages.domain.entities import ExtractionOutput

_NON_DIGIT = re.compile(r"\D")


def _normalise_cnpj(raw: str | float | None) -> str | None:
    if raw is None:
        return None
    digits = _NON_DIGIT.sub("", str(raw))
    return digits if len(digits) == 14 else None  # CNPJ must be exactly 14 digits


def _normalise_doc_number(raw: str | float | None) -> str | None:
    if raw is None:
        return None
    return str(raw).strip().lower()


def _normalise_total(raw: str | float | None) -> str | None:
    if raw is None:
        return None
    try:
        return f"{float(raw):.2f}"
    except (ValueError, TypeError):
        return None


def compute_business_key(fields: ExtractionOutput) -> str | None:
    """Return a stable business-key string or None if mandatory fields are absent.

    The key is deterministic: same CNPJ + document_number + total_amount always
    produces the same string, regardless of file encoding or channel.
    issue_date is included when present (optional — some docs omit it).
    """
    cnpj = _normalise_cnpj(fields.tax_id_cnpj.value if fields.tax_id_cnpj else None)
    doc = _normalise_doc_number(fields.document_number.value if fields.document_number else None)
    total = _normalise_total(fields.total_amount.value if fields.total_amount else None)

    # All three mandatory components required; missing any → can't dedup.
    if not cnpj or not doc or total is None:
        return None

    date_part = ""
    if fields.issue_date and fields.issue_date.value is not None:
        date_part = f"|date:{str(fields.issue_date.value).strip()}"

    return f"cnpj:{cnpj}|doc:{doc}|total:{total}{date_part}"
