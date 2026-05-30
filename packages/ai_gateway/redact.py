"""PII redaction for gateway traces.

Called before storing prompt/completion in model_runs so no raw PII lands
in the trace table. Redaction is best-effort: structured patterns only.
Named entities (person names, addresses) require NLP and are out of scope here.
"""

from __future__ import annotations

import re

# Brazilian CPF: 000.000.000-00 or 11 contiguous digits
_CPF_RE = re.compile(r"\b\d{3}[.\-]?\d{3}[.\-]?\d{3}[.\-]?\d{2}\b")

# Email addresses
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def redact_pii(text: str) -> str:
    """Replace CPF and e-mail patterns with placeholder tokens."""
    text = _CPF_RE.sub("[CPF]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text
