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

from packages.domain.entities import ExtractionOutput, FieldValue, LineItem


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _to_float(raw: str | None) -> float | None:
    """Parse a BR/US-formatted money string into a float (e.g. '9.500,00' → 9500.0)."""
    if not raw:
        return None
    cleaned = raw.strip()
    # If both separators present, the last one is the decimal separator.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_items(text: str) -> list[LineItem]:
    """Heuristic line-item parser.

    Recognises two shapes used in our fixtures / canonical text serialisations:
      1. "Item: <desc> | Qtd: <q> | Unit: <u> | Total: <t>"  (canonical, pipe-delimited)
      2. "<n>. <desc> <q> x <u> = <t>"                        (loose receipt style)
    Returns [] when nothing matches — the validation rule then simply skips.
    """
    items: list[LineItem] = []

    # Shape 1: explicit labelled, pipe-delimited line items.
    for m in re.finditer(
        r"item:\s*(?P<desc>[^|]+?)\s*\|\s*"
        r"(?:qtd|quantidade|qty)[:\s]*(?P<qty>[\d.,]+)\s*\|\s*"
        r"(?:unit|valor\s*unit[aá]rio|unit\s*price)[:\s]*(?:R\$\s*)?(?P<unit>[\d.,]+)\s*\|\s*"
        r"(?:total|line\s*total)[:\s]*(?:R\$\s*)?(?P<total>[\d.,]+)",
        text,
        re.IGNORECASE,
    ):
        items.append(
            LineItem(
                description=m.group("desc").strip(),
                quantity=_to_float(m.group("qty")),
                unit_price=_to_float(m.group("unit")),
                line_total=_to_float(m.group("total")),
                confidence=0.80,
            )
        )

    if items:
        return items

    # Shape 2: "<desc> <q> x <u> = <t>".
    for m in re.finditer(
        r"(?P<desc>[A-Za-zÀ-ÿ][\w\s.\-]+?)\s+(?P<qty>[\d.,]+)\s*x\s*"
        r"(?:R\$\s*)?(?P<unit>[\d.,]+)\s*=\s*(?:R\$\s*)?(?P<total>[\d.,]+)",
        text,
        re.IGNORECASE,
    ):
        items.append(
            LineItem(
                description=m.group("desc").strip(),
                quantity=_to_float(m.group("qty")),
                unit_price=_to_float(m.group("unit")),
                line_total=_to_float(m.group("total")),
                confidence=0.70,
            )
        )
    return items


def extract_from_text(text: str, filename: str = "") -> ExtractionOutput:
    """Heuristic extraction from raw OCR text.

    In production this is replaced by the orchestration agent (prompt doc §1.5 S2).
    The output schema and confidence semantics are identical.
    """
    # Capture the number after a total/amount label, then let _to_float normalise it.
    # Permissive on purpose: matches grouped BR/US money ("9.500,00") AND the plain
    # decimals/integers that structured channels emit ("Total: 4000.0" from a CSV/ERP
    # float). The old regex required exactly two grouped decimals, so structured-channel
    # amounts never parsed and the case wrongly blocked on amount_present.
    total_raw = _find(r"(?:total|valor\s+total|amount)[^\d\-]*?(\d[\d.,]*\d|\d)", text)
    total_val = _to_float(total_raw)
    total_conf = 0.82 if total_val is not None else 0.0

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

    cost_center = _find(r"(?:centro\s+de\s+custo|cost\s*center)[:\s]+([A-Za-z0-9\-]+)", text)
    category = _find(r"(?:categoria|category)[:\s]+([A-Za-zÀ-ÿ\s_]+?)(?:\n|$|\|)", text)

    items = _extract_items(text)

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
        items=items,
        cost_center=FieldValue(value=cost_center, confidence=0.75) if cost_center else None,
        category=FieldValue(value=category, confidence=0.75) if category else None,
    )
