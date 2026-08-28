"""Policy Agent Service — Phase 5 GOVERN.

Retrieves relevant SOP clauses via RAG similarity search and extracts
policy weight coefficients via structured-output LLM call.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from agents.policy_agent.retriever import PolicyRetriever
from agents.policy_agent.weight_extraction import WeightExtractor
from rag.vectorstore.chroma_client import ChromaVectorStore
from schemas import PolicyWeights

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Policy Agent", version="0.1.0")

# Initialize components
vector_store = ChromaVectorStore()
retriever = PolicyRetriever(vector_store)
weight_extractor = WeightExtractor()

# Cache for TTL-validated prefetch
_prefetch_cache: dict[str, PolicyWeights] = {}


@app.post("/retrieve-weights", response_model=PolicyWeights)
async def retrieve_policy_weights(
    disruption_type: str,
    severity: str,
    geography: str = "",
    use_cache: bool = True,
) -> PolicyWeights:
    """Retrieve policy weights for a disruption context.

    If a cached prefetch exists and is valid, returns the cached weights.
    Otherwise, performs full RAG retrieval + LLM extraction.
    """
    cache_key = f"{disruption_type}:{severity}:{geography}"

    # Check cache (TTL validation)
    if use_cache and cache_key in _prefetch_cache:
        logger.info("policy.cache_hit", key=cache_key)
        return _prefetch_cache[cache_key]

    # Full retrieval pipeline
    clauses = retriever.retrieve_policy_clauses(
        disruption_type=disruption_type,
        severity=severity,
        geography=geography,
    )

    weights = weight_extractor.extract_weights(
        cited_clauses=clauses,
        disruption_type=disruption_type,
        severity=severity,
    )

    # Cache for future use
    _prefetch_cache[cache_key] = weights

    return weights


@app.post("/prefetch")
async def prefetch_weights(
    disruption_type: str,
    severity: str,
    geography: str = "",
) -> dict:
    """Speculatively prefetch policy weights (called during S3).

    The result is cached and served with TTL validation when S4 activates.
    """
    weights = await retrieve_policy_weights(
        disruption_type=disruption_type,
        severity=severity,
        geography=geography,
        use_cache=False,
    )

    cache_key = f"{disruption_type}:{severity}:{geography}"
    _prefetch_cache[cache_key] = weights

    logger.info("policy.prefetched", key=cache_key, confidence=weights.confidence_score)

    return {"status": "prefetched", "confidence": weights.confidence_score}


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "corpus_size": str(vector_store.get_clause_count()),
        "cached_entries": str(len(_prefetch_cache)),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
