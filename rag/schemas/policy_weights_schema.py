"""Policy weights schema with Pydantic validation.

Enforces:
  - w1, w2, w3 ∈ [0, 1]
  - w1 + w2 + w3 = 1.0 (within floating-point tolerance)
  - cited_clauses are properly formatted SOP references
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from schemas import CitedClause, PolicyWeights


class PolicyWeightsRequest(BaseModel):
    """Request schema for LLM structured output extraction."""

    raw_llm_response: str


class PolicyWeightsExtraction(BaseModel):
    """Structured output from LLM extraction of policy weights."""

    w1: float = Field(
        ge=0.0,
        le=1.0,
        description="Clinical Urgency weight",
        default=0.4,
    )
    w2: float = Field(
        ge=0.0,
        le=1.0,
        description="Operational Simplicity weight",
        default=0.3,
    )
    w3: float = Field(
        ge=0.0,
        le=1.0,
        description="Value Preservation Index weight",
        default=0.3,
    )
    cited_clauses: list[CitedClause] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "PolicyWeightsExtraction":
        total = self.w1 + self.w2 + self.w3
        if abs(total - 1.0) > 1e-6:
            # Auto-normalize if close, reject if wildly off
            if 0.5 < total < 2.0:
                self.w1 /= total
                self.w2 /= total
                self.w3 /= total
            else:
                raise ValueError(
                    f"Weights must sum to ~1.0, got {total}. "
                    "Cannot auto-normalize — please provide valid weights."
                )
        return self

    def to_policy_weights(self) -> PolicyWeights:
        """Convert to the canonical PolicyWeights schema."""
        return PolicyWeights(
            w1=self.w1,
            w2=self.w2,
            w3=self.w3,
            cited_clauses=self.cited_clauses,
            confidence_score=self.confidence_score,
        )
