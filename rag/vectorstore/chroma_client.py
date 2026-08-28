"""ChromaDB Vector Store Client for SOP/Policy Handbook RAG retrieval.

Stores embedded SOP clauses for similarity search during policy weight extraction.
"""

from __future__ import annotations

from typing import Optional

import chromadb
import structlog
from chromadb.config import Settings

from schemas import CitedClause

logger = structlog.get_logger(__name__)

# Default collection name
CCRO_SOP_COLLECTION = "ccro_sop_handbook"


class ChromaVectorStore:
    """Wrapper around ChromaDB for SOP clause retrieval."""

    def __init__(
        self,
        collection_name: str = CCRO_SOP_COLLECTION,
        persist_directory: str = "./data/chromadb",
    ):
        self.collection_name = collection_name
        self.client = chromadb.Client(
            Settings(chroma_db_impl="duckdb+parquet", persist_directory=persist_directory)
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_sop_clause(
        self,
        clause_id: str,
        text: str,
        source_doc: str,
        doc_version: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a single SOP clause to the vector store."""
        meta = {
            "source_doc": source_doc,
            "doc_version": doc_version,
            **(metadata or {}),
        }
        self.collection.add(
            documents=[text],
            metadatas=[meta],
            ids=[clause_id],
        )
        logger.debug("rag.clause_added", clause_id=clause_id, source_doc=source_doc)

    def search_similar_clauses(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[CitedClause]:
        """RAG similarity search for relevant SOP clauses."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
        except Exception as e:
            logger.error("rag.search_failed", error=str(e))
            return []

        clauses: list[CitedClause] = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = (
                    results["distances"][0][i] if results.get("distances") else 0.0
                )
                # Convert cosine distance to similarity score
                similarity = 1.0 - distance

                clauses.append(
                    CitedClause(
                        clause_id=results["ids"][0][i],
                        source_doc=meta.get("source_doc", ""),
                        doc_version=meta.get("doc_version", ""),
                        similarity_score=similarity,
                        text_excerpt=doc,
                    )
                )

        logger.info("rag.search_completed", n_results=len(clauses))
        return clauses

    def get_clause_count(self) -> int:
        """Return the number of clauses in the collection."""
        return self.collection.count()
