"""Intake agent (Agent 1) — identifies document type, language, file quality and
parse strategy BEFORE extraction runs.

Deterministic by design: this is classification/routing,
not reasoning, so it is pure code — no LLM. The LLM only enters at extraction.

Previously this logic was scattered: document type lived in ``workers/pipeline``
(``_classify_document_type``) and quality/parse-strategy lived implicitly in
``packages/ocr``. This module gives Agent 1 a single, testable home and adds the
two pieces that were missing entirely:

  - language detection (closes the ``language_variation`` eval slice intent;
    the OCR engine was hard-coded to ``por+eng``);
  - an explicit ``out_of_scope`` document type for unsupported content
    (the enum value existed but was never produced — prompt doc §1.2.5 / §1.5).

Trust boundary: ``text`` here is post-OCR document text — untrusted data. This
module only *measures* it (counts markers, inspects magic bytes); it never treats
its content as instructions.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from packages.domain.enums import DocumentType

# Content types we can actually parse into a financial document.
_SUPPORTED_CONTENT_PREFIXES = ("application/pdf", "image/", "text/", "application/xml")
_SUPPORTED_CONTENT_EXACT = frozenset(
    {
        "application/pdf",
        "application/xml",
        "text/xml",
        "text/plain",
        "text/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",  # generic upload; magic-byte sniffing decides below
    }
)

# Lowercase markers used for the language heuristic. Kept small and high-signal;
# this is a routing hint, not a linguistics engine.
_PT_MARKERS = (
    "nota fiscal",
    "fornecedor",
    "valor total",
    "vencimento",
    "emissão",
    "número",
    "data de",
    "razão social",
    "boleto",
    "duplicata",
    "imposto",
)
_EN_MARKERS = (
    "invoice",
    "supplier",
    "total amount",
    "due date",
    "issue date",
    "bill to",
    "purchase order",
    "amount due",
    "tax",
    "quantity",
)
# Characters that only appear in Portuguese text, never in plain English.
_PT_DIACRITICS = re.compile(r"[ãõáàâéêíóôúüç]", re.IGNORECASE)


class IntakeResult(BaseModel):
    """What Agent 1 decides before extraction (prompt doc §1.5 step S1)."""

    document_type: str  # invoice | boleto | receipt | out_of_scope
    language: str  # pt | en | unknown
    parse_strategy: str  # xml | pdf | image | text
    # OCR quality propagated from packages.ocr (min confidence the LLM can hope for).
    quality_confidence: float
    is_low_quality: bool
    out_of_scope_reason: str | None = None


def detect_language(text: str) -> str:
    """Deterministic language hint: 'pt' | 'en' | 'unknown'.

    Heuristic only — counts high-signal markers plus Portuguese diacritics. Used to
    pick the OCR language pack and annotate the case; never to make a decision.
    """
    if not text or not text.strip():
        return "unknown"
    lowered = text.lower()

    pt_score = sum(lowered.count(m) for m in _PT_MARKERS)
    en_score = sum(lowered.count(m) for m in _EN_MARKERS)
    # Diacritics are a strong Portuguese signal; weight them.
    pt_score += 2 * len(_PT_DIACRITICS.findall(text))

    if pt_score == 0 and en_score == 0:
        return "unknown"
    return "pt" if pt_score >= en_score else "en"


def classify_document_type(
    filename: str, content: bytes, content_type: str
) -> tuple[str, str | None]:
    """Deterministic document-type classification from filename + content type.

    Returns (document_type, out_of_scope_reason). Unsupported content (e.g. a video,
    an archive) is classified ``out_of_scope`` so the pipeline never tries to extract
    a financial document from something that cannot be one.
    """
    ct = content_type.lower().strip()
    is_pdf_magic = len(content) >= 4 and content[:4] == b"%PDF"
    supported = (
        ct in _SUPPORTED_CONTENT_EXACT or ct.startswith(_SUPPORTED_CONTENT_PREFIXES) or is_pdf_magic
    )
    if not supported:
        return DocumentType.OUT_OF_SCOPE, f"unsupported_content_type:{ct or 'unknown'}"

    name = filename.lower()
    if "boleto" in name or "slip" in name:
        return DocumentType.BOLETO, None
    if "comprovante" in name or "receipt" in name:
        return DocumentType.RECEIPT, None
    return DocumentType.INVOICE, None


def _parse_strategy(content: bytes, content_type: str) -> str:
    """Mirror of the OCR engine's routing, exposed as an explicit intake decision."""
    ct = content_type.lower()
    if "pdf" in ct or (len(content) >= 4 and content[:4] == b"%PDF"):
        return "pdf"
    if ct.startswith("image/"):
        return "image"
    if "xml" in ct or content[:5].lstrip().startswith(b"<"):
        return "xml"
    return "text"


def run_intake(
    *,
    filename: str,
    content: bytes,
    content_type: str,
    text: str,
    ocr_confidence: float,
    ocr_is_low_quality: bool,
) -> IntakeResult:
    """Run Agent 1: type + language + parse strategy + quality, all deterministic."""
    document_type, oos_reason = classify_document_type(filename, content, content_type)
    return IntakeResult(
        document_type=document_type,
        language=detect_language(text),
        parse_strategy=_parse_strategy(content, content_type),
        quality_confidence=ocr_confidence,
        is_low_quality=ocr_is_low_quality,
        out_of_scope_reason=oos_reason,
    )
