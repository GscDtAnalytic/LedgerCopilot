"""Pydantic entities for AI-layer contracts (pure, validated, no ORM).

LLM output is ALWAYS validated by one of these models before being used anywhere.
Never consume raw JSON from the model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldValue(BaseModel):
    """A single extracted field with its confidence and provenance."""

    value: str | float | None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "ocr"  # ocr | image | both


class ExtractionOutput(BaseModel):
    """Validated output of the Extraction stage (prompt doc §1.11 fields block)."""

    supplier_name: FieldValue | None = None
    tax_id_cnpj: FieldValue | None = None
    total_amount: FieldValue | None = None
    currency: FieldValue | None = None
    issue_date: FieldValue | None = None
    due_date: FieldValue | None = None
    document_number: FieldValue | None = None

    def critical_fields(self) -> list[FieldValue | None]:
        return [self.total_amount, self.tax_id_cnpj, self.document_number]

    def overall_confidence(self) -> float:
        """Min confidence across critical fields; 0.0 if any is missing."""
        values = [f.confidence for f in self.critical_fields() if f is not None]
        return min(values) if values else 0.0


class ValidationRuleResult(BaseModel):
    rule: str
    passed: bool
    severity: str  # block | warn
    detail: str | None = None


class DecisionBranches(BaseModel):
    auto_approve: float = 0.0
    human_review: float = 0.0
    reject: float = 0.0


class AgentDecisionOutput(BaseModel):
    """Validated output of the full orchestration agent (prompt doc §1.11)."""

    document_type: str  # invoice | boleto | receipt | out_of_scope
    fields: ExtractionOutput
    validations: list[ValidationRuleResult] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    decision: str  # auto_approve | human_review | reject
    decision_branches: DecisionBranches = Field(default_factory=DecisionBranches)
    reason_code: str
    justification: str
    prompt_version_id: str = "dev-1.0"
