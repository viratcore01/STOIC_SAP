"""Policy Agent Retriever — LangChain retriever configuration for SOP corpus.

Retrieves relevant SOP clauses via similarity search, then extracts
policy weights via structured-output LLM call.
"""

from __future__ import annotations

from typing import Optional

import structlog

from rag.vectorstore.chroma_client import ChromaVectorStore
from schemas import CitedClause, PolicyWeights

logger = structlog.get_logger(__name__)


class PolicyRetriever:
    """Retrieves policy context from the RAG knowledge base.

    Uses ChromaDB vector store for similarity search, returning
    cited SOP clauses with similarity scores.
    """

    def __init__(self, vector_store: ChromaVectorStore, top_k: int = 5):
        self.vector_store = vector_store
        self.top_k = top_k

    def retrieve_policy_clauses(
        self,
        disruption_type: str,
        severity: str,
        geography: str = "",
    ) -> list[CitedClause]:
        """Retrieve relevant SOP clauses for the given disruption context.

        Args:
            disruption_type: Type of disruption (thermal_drift, weather, etc.)
            severity: Severity level (low, medium, high, critical)
            geography: Optional geographic context.

        Returns:
            List of cited SOP clauses ranked by similarity.
        """
        # Build query from disruption context
        query = (
            f"Cold chain disruption: {disruption_type}, "
            f"severity: {severity}"
        )
        if geography:
            query += f", geography: {geography}"

        clauses = self.vector_store.search_similar_clauses(
            query=query,
            n_results=self.top_k,
        )

        logger.info(
            "policy.clauses_retrieved",
            n_clauses=len(clauses),
            disruption_type=disruption_type,
        )

        return clauses
