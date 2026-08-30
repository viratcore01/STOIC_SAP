"""SOP Ingestion Script — Chunks, embeds, and loads SOP documents into ChromaDB.

Usage:
    python scripts/ingest_sops.py

This script:
1. Reads SOP markdown files from data/sops/
2. Chunks them into clause-sized paragraphs
3. Embeds them using ChromaDB's default embedding function
4. Loads them into the ccro_sop_handbook collection

The policy_agent retriever then queries this collection for relevant clauses.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import chromadb
import structlog

logger = structlog.get_logger(__name__)

SOP_DIR = project_root / "data" / "sops"
CHROMA_DIR = project_root / "data" / "chromadb"
COLLECTION_NAME = "ccro_sop_handbook"


def chunk_markdown(text: str, source_doc: str, max_chunk_chars: int = 800) -> list[dict]:
    """Chunk a markdown document into clause-sized paragraphs.

    Splits on:
    - Section headers (##, ###)
    - Numbered items (1., 2., etc.)
    - Bullet points (-, *)
    - Blank line separators

    Returns list of {id, text, metadata} dicts.
    """
    chunks = []
    current_section = ""
    current_text = []
    chunk_index = 0

    for line in text.split("\n"):
        stripped = line.strip()

        # Detect section headers
        if stripped.startswith("#"):
            # Save previous chunk if non-empty
            if current_text:
                chunk_text = "\n".join(current_text).strip()
                if chunk_text and len(chunk_text) > 20:
                    chunk_index += 1
                    chunks.append({
                        "id": f"{source_doc}-clause-{chunk_index:03d}",
                        "text": f"[{current_section}] {chunk_text}" if current_section else chunk_text,
                        "metadata": {
                            "source_doc": source_doc,
                            "section": current_section,
                            "clause_index": chunk_index,
                        },
                    })
                current_text = []

            # Extract header text
            header_text = stripped.lstrip("#").strip()
            if header_text:
                current_section = header_text
            continue

        # Detect list items (natural clause boundaries)
        if stripped and (stripped[0].isdigit() and ". " in stripped[:5]) or stripped.startswith(("- ", "* ")):
            # Save previous chunk
            chunk_text = "\n".join(current_text).strip()
            if chunk_text and len(chunk_text) > 20:
                chunk_index += 1
                chunks.append({
                    "id": f"{source_doc}-clause-{chunk_index:03d}",
                    "text": f"[{current_section}] {chunk_text}" if current_section else chunk_text,
                    "metadata": {
                        "source_doc": source_doc,
                        "section": current_section,
                        "clause_index": chunk_index,
                    },
                })
                current_text = []

        current_text.append(line)

        # Split if chunk gets too long
        combined = "\n".join(current_text)
        if len(combined) > max_chunk_chars:
            chunk_text = combined.strip()
            if chunk_text and len(chunk_text) > 20:
                chunk_index += 1
                chunks.append({
                    "id": f"{source_doc}-clause-{chunk_index:03d}",
                    "text": f"[{current_section}] {chunk_text}" if current_section else chunk_text,
                    "metadata": {
                        "source_doc": source_doc,
                        "section": current_section,
                        "clause_index": chunk_index,
                    },
                })
            current_text = []

    # Save final chunk
    if current_text:
        chunk_text = "\n".join(current_text).strip()
        if chunk_text and len(chunk_text) > 20:
            chunk_index += 1
            chunks.append({
                "id": f"{source_doc}-clause-{chunk_index:03d}",
                "text": f"[{current_section}] {chunk_text}" if current_section else chunk_text,
                "metadata": {
                    "source_doc": source_doc,
                    "section": current_section,
                    "clause_index": chunk_index,
                },
            })

    return chunks


def ingest_sops():
    """Main ingestion pipeline."""
    if not SOP_DIR.exists():
        logger.error("ingest.sop_dir_not_found", path=str(SOP_DIR))
        print(f"ERROR: SOP directory not found at {SOP_DIR}")
        sys.exit(1)

    md_files = list(SOP_DIR.glob("*.md"))
    if not md_files:
        logger.error("ingest.no_sop_files", path=str(SOP_DIR))
        print(f"ERROR: No .md files found in {SOP_DIR}")
        sys.exit(1)

    print(f"Found {len(md_files)} SOP file(s):")
    for f in md_files:
        print(f"  - {f.name}")

    # Initialize ChromaDB
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Delete existing collection if present (clean re-ingestion)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    total_chunks = 0

    for md_file in md_files:
        source_doc = md_file.stem
        print(f"\nProcessing: {md_file.name}")

        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, source_doc)
        print(f"  Chunked into {len(chunks)} clauses")

        if not chunks:
            print(f"  WARNING: No chunks generated from {md_file.name}")
            continue

        # Batch add to ChromaDB
        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        total_chunks += len(chunks)
        print(f"  Ingested {len(chunks)} clauses into ChromaDB")

    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"  Documents processed: {len(md_files)}")
    print(f"  Total clauses ingested: {total_chunks}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  ChromaDB path: {CHROMA_DIR}")
    print(f"{'='*60}")

    # Verify by running a test query
    print("\nVerification query: 'cold chain temperature requirements'")
    results = collection.query(
        query_texts=["cold chain temperature requirements"],
        n_results=3,
    )
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            similarity = 1.0 - distance
            print(f"  Result {i+1} (similarity={similarity:.3f}):")
            print(f"    Source: {meta.get('source_doc', 'unknown')}")
            print(f"    Text: {doc[:120]}...")

    return collection


if __name__ == "__main__":
    ingest_sops()
