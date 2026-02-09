"""Semantic embedding engine for Megregore. ChromaDB + sentence-transformers."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("megregore.embeddings")

# Lazy-loaded state
_model = None
_model_lock = asyncio.Lock()
_collection = None
_collection_lock = asyncio.Lock()
_chroma_client = None
_available = None  # None = not yet checked, True/False after first attempt

MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "megregore_memories"
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"


def _load_model():
    """Synchronous model load — runs in executor."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


async def _ensure_model() -> bool:
    """Lazy-load sentence-transformers model. Returns True if available."""
    global _model, _available

    if _available is False:
        return False
    if _model is not None:
        return True

    async with _model_lock:
        if _model is not None:
            return True
        try:
            loop = asyncio.get_running_loop()
            _model = await loop.run_in_executor(None, _load_model)
            _available = True
            logger.info("Embedding model loaded: %s", MODEL_NAME)
            return True
        except Exception as e:
            _available = False
            logger.warning("Embeddings unavailable (falling back to FTS5): %s", e)
            return False


async def _ensure_collection():
    """Lazy-init ChromaDB persistent client and collection."""
    global _chroma_client, _collection, _available

    if _collection is not None:
        return _collection

    async with _collection_lock:
        if _collection is not None:
            return _collection
        try:
            import chromadb
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)

            loop = asyncio.get_running_loop()
            _chroma_client = await loop.run_in_executor(
                None,
                lambda: chromadb.PersistentClient(path=str(CHROMA_DIR)),
            )
            _collection = await loop.run_in_executor(
                None,
                lambda: _chroma_client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                ),
            )
            logger.info("ChromaDB collection ready: %s", COLLECTION_NAME)
            return _collection
        except Exception as e:
            _available = False
            logger.warning("ChromaDB unavailable (falling back to FTS5): %s", e)
            return None


def _build_embed_text(content: str, context: Optional[str] = None) -> str:
    """Combine content + context into a single string for embedding.

    Context provides situational meaning that enriches the semantic representation.
    Example: content="That was a breakthrough" alone is vague.
    With context="discussing consciousness and qualia", the embedding captures the domain.
    """
    parts = [content]
    if context:
        parts.append(context)
    return " ".join(parts)


async def warmup() -> dict:
    """Pre-warm the embedding model and ChromaDB collection at server startup.

    Returns status dict with model_loaded and collection_ready booleans.
    """
    model_ok = await _ensure_model()
    collection = None
    if model_ok:
        collection = await _ensure_collection()
    return {
        "model_loaded": model_ok,
        "collection_ready": collection is not None,
    }


async def embed_and_store(
    memory_id: int,
    content: str,
    context: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """Generate embedding for a memory and store it in ChromaDB.

    Returns True if successful, False if embeddings are unavailable.
    Caller should proceed normally either way — this is fire-and-forget
    from the memory storage perspective.
    """
    if not await _ensure_model():
        return False

    collection = await _ensure_collection()
    if collection is None:
        return False

    try:
        text = _build_embed_text(content, context)
        loop = asyncio.get_running_loop()

        embedding = await loop.run_in_executor(
            None,
            lambda: _model.encode(text).tolist(),
        )

        await loop.run_in_executor(
            None,
            lambda: collection.upsert(
                ids=[str(memory_id)],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata or {}],
            ),
        )
        return True
    except Exception as e:
        logger.error("Failed to embed memory %d: %s", memory_id, e)
        return False


async def semantic_search(
    query: str,
    limit: int = 20,
) -> list[tuple[int, float]]:
    """Search ChromaDB for semantically similar memories.

    Returns list of (memory_id, similarity_score) tuples.
    Similarity score is 0.0 to 1.0 (cosine similarity, higher = more similar).

    Returns empty list if embeddings are unavailable.
    """
    if not await _ensure_model():
        return []

    collection = await _ensure_collection()
    if collection is None:
        return []

    try:
        loop = asyncio.get_running_loop()

        query_embedding = await loop.run_in_executor(
            None,
            lambda: _model.encode(query).tolist(),
        )

        results = await loop.run_in_executor(
            None,
            lambda: collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["distances"],
            ),
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity: similarity = 1 - (distance / 2)
        pairs = []
        for id_str, distance in zip(results["ids"][0], results["distances"][0]):
            similarity = 1.0 - (distance / 2.0)
            pairs.append((int(id_str), similarity))

        return pairs
    except Exception as e:
        logger.error("Semantic search failed: %s", e)
        return []


async def is_available() -> bool:
    """Check if the embedding subsystem is operational.

    Does NOT trigger lazy loading — just reports current state.
    """
    return _available is True


async def backfill_all() -> dict:
    """Embed all existing memories that aren't yet in ChromaDB.

    Uses upsert so re-running is safe (idempotent).
    Returns stats about what was processed.
    """
    from . import database

    if not await _ensure_model():
        return {"status": "error", "message": "Embedding model unavailable"}

    collection = await _ensure_collection()
    if collection is None:
        return {"status": "error", "message": "ChromaDB unavailable"}

    db = await database.get_connection()
    try:
        cursor = await db.execute(
            "SELECT id, content, context, memory_type, importance FROM memories"
        )
        rows = await cursor.fetchall()

        total = len(rows)
        succeeded = 0
        failed = 0

        for row in rows:
            metadata = {
                "memory_type": row["memory_type"],
                "importance": row["importance"],
            }
            ok = await embed_and_store(
                memory_id=row["id"],
                content=row["content"],
                context=row["context"],
                metadata=metadata,
            )
            if ok:
                succeeded += 1
            else:
                failed += 1

        return {
            "status": "completed",
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
        }
    finally:
        await db.close()
