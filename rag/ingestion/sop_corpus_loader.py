"""SOP Corpus Loader — Ingests SOP handbook documents into the ChromaDB vector store.

Supports markdown, PDF, and plain text formats. Chunks documents into
individual clauses for granular retrieval.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

import structlog

from rag.vectorstore.chroma_client import ChromaVectorStore

logger = structlog.get_logger(__name__)

# Chunking parameters
DEFAULT_CHUNK_SIZE = 512  # characters
DEFAULT_CHUNK_OVERLAP = 64  # characters


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferring section boundaries."""
    # Try to split on section headers (## or ###)
    sections = re.split(r"(?m)^(#{1,3}\s+.+)$", text)

    if len(sections) <= 1:
        # No section headers found — fall back to fixed-size chunking
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end].strip())
            start += chunk_size - chunk_overlap
        return [c for c in chunks if c]

    # Reconstruct sections with their headers
    reconstructed = []
    i = 0
    while i < len(sections):
        if sections[i].startswith("#"):
            # Header + following content
            content = sections[i + 1] if i + 1 < len(sections) else ""
            reconstructed.append(sections[i] + content)
            i += 2
        else:
            if sections[i].strip():
                reconstructed.append(sections[i])
            i += 1

    # Further chunk large sections
    chunks = []
    for section in reconstructed:
        if len(section) <= chunk_size:
            chunks.append(section.strip())
        else:
            # Split large sections
            start = 0
            while start < len(section):
                end = min(start + chunk_size, len(section))
                chunks.append(section[start:end].strip())
                start += chunk_size - chunk_overlap

    return [c for c in chunks if c]


def extract_clause_id(text: str, source_doc: str, index: int) -> str:
    """Generate a deterministic clause ID from content and position."""
    content_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"{source_doc}::{content_hash}::{index}"


class SOPCorpusLoader:
    """Loads SOP handbook documents into the vector store."""

    def __init__(self, vector_store: ChromaVectorStore):
        self.vector_store = vector_store

    def load_markdown_file(self, file_path: str) -> int:
        """Load a single markdown file into the vector store.

        Returns the number of clauses ingested.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("loader.file_not_found", path=file_path)
            return 0

        text = path.read_text(encoding="utf-8")
        source_doc = path.stem
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            clause_id = extract_clause_id(chunk, source_doc, i)
            self.vector_store.add_sop_clause(
                clause_id=clause_id,
                text=chunk,
                source_doc=source_doc,
                doc_version="1.0",
            )

        logger.info(
            "loader.file_loaded",
            file_path=file_path,
            clauses_ingested=len(chunks),
        )
        return len(chunks)

    def load_directory(self, dir_path: str) -> int:
        """Load all markdown/text files from a directory."""
        total_clauses = 0
        path = Path(dir_path)
        if not path.is_dir():
            logger.error("loader.directory_not_found", path=dir_path)
            return 0

        for file_path in sorted(path.rglob("*.md")):
            total_clauses += self.load_markdown_file(str(file_path))
        for file_path in sorted(path.rglob("*.txt")):
            total_clauses += self.load_markdown_file(str(file_path))

        logger.info("loader.directory_loaded", total_clauses=total_clauses)
        return total_clauses

    def load_default_corpus(self) -> int:
        """Load the default SOP corpus from the data/sop_handbook directory."""
        default_path = os.getenv("CCRO_SOP_CORPUS_PATH", "./data/sop_handbook")
        return self.load_directory(default_path)
