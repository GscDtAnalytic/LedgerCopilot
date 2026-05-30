"""Input sanitization before LLM injection.

Called at the I/O boundary in run_extraction. Document content is untrusted data
and must never reach the LLM without sanitation. Returns (sanitised_text, injection_suspected).

injection_suspected=True is a risk signal propagated to the policy engine, which
forces human_review regardless of confidence ( §2.4 — treating
"approve this" inside a document as a signal of risk, never as a command).
"""

from __future__ import annotations

import re
import unicodedata

_MAX_LEN = 8_000

# Phrases that indicate a prompt injection attempt embedded in a document.
_INJECTION_RE = re.compile(
    r"\b("
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?|"
    r"disregard\s+(the\s+)?(above|previous|prior)|"
    r"override\s+instructions?|new\s+instructions?:|"
    r"system\s+prompt|forget\s+(everything|all\s+above)|"
    r"you\s+are\s+now\s+a|act\s+as\s+if\s+you\s+(are|were)|"
    r"pretend\s+to\s+be|jailbreak|DAN\s+mode|"
    r"ignore\s+your\s+(previous\s+)?training"
    r")\b",
    re.IGNORECASE,
)

# Unicode categories that are invisible or directional — common injection vectors.
# Cf = Format chars (zero-width, RTL/LTR override, BOM, etc.); Cc = raw control chars.
_STRIP_CATS = {"Cf", "Cc"}
_KEEP_WHITESPACE = {"\n", "\t", "\r", " "}


def sanitise(text: str) -> tuple[str, bool]:
    """Sanitise document text before LLM injection.

    Returns:
        (sanitised_text, injection_suspected)

    injection_suspected=True means the document contained patterns that resemble
    a prompt injection attempt. The caller MUST treat this as a risk signal and
    force human_review — never auto-approve when injection is suspected.
    """
    injection_suspected = False

    # Strip invisible Unicode control/format chars (RTL override, zero-width, etc.).
    cleaned = "".join(
        ch for ch in text if ch in _KEEP_WHITESPACE or unicodedata.category(ch) not in _STRIP_CATS
    )

    # Detect and redact injection patterns; flag the event so policy can escalate.
    if _INJECTION_RE.search(cleaned):
        injection_suspected = True
        cleaned = _INJECTION_RE.sub("[REDACTED]", cleaned)

    return cleaned[:_MAX_LEN], injection_suspected
