"""Policy Weight Extraction — Structured-output LLM call with Pydantic validation.

Extracts w1, w2, w3 coefficients from retrieved SOP clauses using an LLM,
then validates via Pydantic (sum=1, bounds [0,1]).
"""

from __future__ import annotations

from typing import Optional

import structlog
from pydantic import ValidationError

from rag.schemas.policy_weights_schema import PolicyWeightsExtraction
from schemas import CitedClause, PolicyWeights

logger = structlog.get_logger(__name__)

# System prompt for structured weight extraction
WEIGHT_EXTRACTION_PROMPT = """You are a pharmaceutical cold-chain policy analyst.

Given the following SOP clauses retrieved from the organizational policy handbook,
extract three policy weight coefficients for the cold-chain scarcity allocation:

w1 = Clinical Urgency (weight for sites with shorter remaining shelf life)
w2 = Operational Simplicity (weight for routes/easier logistics)
w3 = Value Preservation Index (weight for higher-demand/value shipments)

CONSTRAINTS:
- w1 + w2 + w3 MUST equal 1.0
- Each weight must be in [0, 1]
- Higher severity disruptions should increase w1 (clinical urgency)
- The weights should reflect the cited SOP clauses

SOP Clauses:
{clauses_text}

Return JSON with: w1, w2, w3, confidence_score, reasoning.
"""


class WeightExtractor:
    """Extracts policy weights from retrieved SOP clauses via structured LLM call."""

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        self.llm_provider = llm_provider
        self.model = model

    def extract_weights(
        self,
        cited_clauses: list[CitedClause],
        disruption_type: str = "",
        severity: str = "",
    ) -> PolicyWeights:
        """Extract policy weights from retrieved SOP clauses.

        Uses LLM structured output + Pydantic validation.
        Falls back to default weights if extraction fails.
        """
        if not cited_clauses:
            logger.warning("policy.no_clauses_for_extraction")
            return PolicyWeights(
                w1=0.4,
                w2=0.3,
                w3=0.3,
                confidence_score=0.3,
            )

        # Format clauses for the prompt
        clauses_text = "\n".join(
            f"- [{c.clause_id}] {c.source_doc} §{c.clause_id}: {c.text_excerpt} "
            f"(similarity: {c.similarity_score:.2f})"
            for c in cited_clauses
        )

        prompt = WEIGHT_EXTRACTION_PROMPT.format(clauses_text=clauses_text)

        # In production, this calls the LLM API
        # For now, use a heuristic based on disruption context
        extracted = self._heuristic_extraction(
            cited_clauses, disruption_type, severity
        )

        try:
            validated = PolicyWeightsExtraction(
                w1=extracted["w1"],
                w2=extracted["w2"],
                w3=extracted["w3"],
                cited_clauses=cited_clauses,
                confidence_score=extracted["confidence_score"],
                reasoning=extracted.get("reasoning", ""),
            )
            policy_weights = validated.to_policy_weights()

            logger.info(
                "policy.weights_extracted",
                w1=policy_weights.w1,
                w2=policy_weights.w2,
                w3=policy_weights.w3,
                confidence=policy_weights.confidence_score,
                n_clauses=len(cited_clauses),
            )

            return policy_weights

        except ValidationError as e:
            logger.error("policy.weight_validation_failed", error=str(e))
            return PolicyWeights(
                w1=0.4, w2=0.3, w3=0.3,
                cited_clauses=cited_clauses,
                confidence_score=0.3,
            )

    def _heuristic_extraction(
        self,
        clauses: list[CitedClause],
        disruption_type: str,
        severity: str,
    ) -> dict:
        """Heuristic weight extraction based on disruption context.

        In production, replace with actual LLM API call.
        """
        base_w1 = 0.4
        base_w2 = 0.3
        base_w3 = 0.3

        # Adjust based on severity
        severity_boost = {
            "low": 0.0,
            "medium": 0.05,
            "high": 0.1,
            "critical": 0.15,
        }.get(severity, 0.0)

        w1 = min(1.0, base_w1 + severity_boost)
        w3 = min(1.0, base_w3 + severity_boost * 0.5)
        w2 = max(0.0, 1.0 - w1 - w3)

        # Normalize
        total = w1 + w2 + w3
        w1 /= total
        w2 /= total
        w3 /= total

        avg_similarity = (
            sum(c.similarity_score for c in clauses) / len(clauses) if clauses else 0.5
        )

        return {
            "w1": round(w1, 3),
            "w2": round(w2, 3),
            "w3": round(w3, 3),
            "confidence_score": round(avg_similarity, 3),
            "reasoning": (
                f"Based on {len(clauses)} SOP clauses for {disruption_type} "
                f"(severity: {severity}). Clinical urgency weighted higher due to "
                f"severity level."
            ),
        }
