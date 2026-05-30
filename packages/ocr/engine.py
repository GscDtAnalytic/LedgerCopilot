"""OCR / text-extraction engine.

Implements the IDP pipeline from:
  1. Detect document format (text/PDF/image)
  2. Extract text with the appropriate engine
  3. Attach a confidence score (0.0-1.0) and provenance label

Confidence semantics
--------------------
- 1.0  → exact UTF-8 text or structured XML (no OCR needed)
- 0.95 → PDF with embedded text layer (pdfplumber)
- 0.70-0.95 -> scanned PDF or image via Tesseract (from tesseract word-conf)
- < 0.60 → OCR quality is too low; pipeline will cap field confidences and
           add "ocr_quality" to low_agreement → forces HITL review

Anti-patterns avoided (wiki):
- Never discard the original bytes (callers are responsible for bronze storage).
- Never accept low-confidence output without flagging it for human review.

Optional dependencies (graceful degradation):
- pdfplumber  → text PDFs (required; add to pyproject.toml)
- pytesseract + Pillow → images and scanned PDFs (optional; needs Tesseract binary)
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Fields whose OCR confidence falls below this threshold are flagged for HITL.
LOW_OCR_CONFIDENCE = 0.60

# Minimum chars extracted from a PDF page before we consider the text layer usable.
_MIN_PDF_TEXT_CHARS = 50


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0.0-1.0
    source: str  # "text" | "pdf-text" | "ocr-tesseract" | "ocr-image" | "ocr-failed"
    pages: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def is_low_quality(self) -> bool:
        return self.confidence < LOW_OCR_CONFIDENCE


def extract_text(content: bytes, content_type: str) -> OcrResult:
    """Detect document format and extract text with confidence.

    Routing logic (wiki: prefer structured source over OCR):
    - PDF magic bytes OR content_type contains "pdf" → pdfplumber (text PDF)
      └ if text is too sparse (scanned) → Tesseract fallback
    - image/* content_type → Tesseract
    - Everything else → UTF-8 decode (XML, plain text); confidence=1.0
    """
    ct = content_type.lower()

    if "pdf" in ct or (len(content) >= 4 and content[:4] == b"%PDF"):
        return _extract_pdf(content)

    if ct.startswith("image/"):
        return _extract_image(content)

    # Plain text / XML / unknown — direct decode, zero OCR uncertainty.
    text = content.decode("utf-8", errors="replace")
    return OcrResult(text=text, confidence=1.0, source="text")


# ── PDF ───────────────────────────────────────────────────────────────────────


def _extract_pdf(content: bytes) -> OcrResult:
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed — falling back to UTF-8 decode for PDF")
        return OcrResult(
            text=content.decode("utf-8", errors="replace"),
            confidence=0.50,
            source="pdf-fallback",
            warnings=["pdfplumber not installed; install it with: uv add pdfplumber"],
        )

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            page_texts: list[str] = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                page_texts.append(t)

            full_text = "\n".join(page_texts).strip()
            n_pages = len(pdf.pages)

        if len(full_text) >= _MIN_PDF_TEXT_CHARS:
            return OcrResult(
                text=full_text,
                confidence=0.95,
                source="pdf-text",
                pages=n_pages,
            )

        # Very little text extracted → likely a scanned PDF.
        logger.info("PDF has sparse text (%d chars) — attempting Tesseract OCR", len(full_text))
        return _extract_pdf_with_tesseract(content, n_pages)

    except Exception as exc:
        logger.warning("pdfplumber failed (%s) — falling back to UTF-8", exc)
        return OcrResult(
            text=content.decode("utf-8", errors="replace"),
            confidence=0.40,
            source="pdf-fallback",
            warnings=[f"pdfplumber error: {exc}"],
        )


def _extract_pdf_with_tesseract(content: bytes, n_pages: int) -> OcrResult:
    """Render PDF pages as images and run Tesseract (requires pytesseract + Pillow + poppler)."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return OcrResult(
            text="",
            confidence=0.0,
            source="ocr-failed",
            pages=n_pages,
            warnings=[
                "Scanned PDF detected but pytesseract/pdf2image not installed. "
                "Install: uv add pytesseract pdf2image Pillow (needs poppler system pkg)."
            ],
        )

    try:
        images = convert_from_bytes(content, dpi=200)
        texts: list[str] = []
        confidences: list[float] = []

        for img in images:
            data = pytesseract.image_to_data(
                img, output_type=pytesseract.Output.DICT, lang="por+eng"
            )
            texts.append(pytesseract.image_to_string(img, lang="por+eng"))
            word_confs = [c for c in data["conf"] if isinstance(c, int) and c >= 0]
            if word_confs:
                confidences.append(sum(word_confs) / len(word_confs) / 100.0)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.50
        return OcrResult(
            text="\n".join(texts),
            confidence=avg_conf,
            source="ocr-tesseract",
            pages=len(images),
        )
    except Exception as exc:
        logger.warning("Tesseract PDF OCR failed: %s", exc)
        return OcrResult(
            text="",
            confidence=0.0,
            source="ocr-failed",
            pages=n_pages,
            warnings=[f"Tesseract PDF error: {exc}"],
        )


# ── Images ────────────────────────────────────────────────────────────────────


def _extract_image(content: bytes) -> OcrResult:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return OcrResult(
            text="",
            confidence=0.0,
            source="ocr-image-unavailable",
            warnings=[
                "Image document detected but pytesseract/Pillow not installed. "
                "Install with: uv add pytesseract Pillow (also needs Tesseract binary)."
            ],
        )

    try:
        img = Image.open(io.BytesIO(content))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang="por+eng")
        text = pytesseract.image_to_string(img, lang="por+eng")
        word_confs = [c for c in data["conf"] if isinstance(c, int) and c >= 0]
        avg_conf = sum(word_confs) / len(word_confs) / 100.0 if word_confs else 0.50
        return OcrResult(text=text, confidence=avg_conf, source="ocr-image")
    except Exception as exc:
        logger.warning("Tesseract image OCR failed: %s", exc)
        return OcrResult(
            text="",
            confidence=0.0,
            source="ocr-failed",
            warnings=[f"Tesseract image error: {exc}"],
        )
