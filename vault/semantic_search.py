"""
Local Semantic Vector Search Engine for DevListen (Brick 5).
Uses BAAI/bge-small-en-v1.5 (384-dimensional ONNX embeddings) via fastembed.
Stores normalized vectors in SQLite and executes sub-10ms vectorized cosine search.
"""
import sqlite3
import numpy as np
from typing import List, Dict, Any, Optional
from fastembed import TextEmbedding
from vault.database import VaultDatabase

class SemanticSearchEngine:
    """
    Computes dense vector representations of technical decisions
    and performs real-time semantic retrieval over natural language queries.
    """
    def __init__(self, db: VaultDatabase, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.db = db
        self.model_name = model_name
        self._embedder: Optional[TextEmbedding] = None
        self._ensure_schema()

    def _get_embedder(self) -> TextEmbedding:
        if self._embedder is None:
            self._embedder = TextEmbedding(model_name=self.model_name)
        return self._embedder

    def _ensure_schema(self):
        """Ensures the decisions table has an embedding column."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(decisions)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "embedding" not in columns:
                conn.execute("ALTER TABLE decisions ADD COLUMN embedding BLOB")
                conn.commit()

    def embed_text(self, text: str) -> np.ndarray:
        """Generates a 384-dimensional normalized float32 vector for a text string."""
        embedder = self._get_embedder()
        vec = list(embedder.embed([text]))[0]
        # Ensure L2 normalization for fast dot-product cosine similarity
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.astype(np.float32)

    def index_decision(self, decision_id: str, text_to_embed: str):
        """Computes and stores embedding vector for a decision."""
        try:
            vec = self.embed_text(text_to_embed)
            blob = vec.tobytes()
            with self.db.get_connection() as conn:
                conn.execute(
                    "UPDATE decisions SET embedding = ? WHERE decision_id = ?",
                    (blob, decision_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[DevListen Semantic] Indexing error: {e}")

    def index_all_pending(self):
        """Indexes any decisions in the database missing an embedding."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT decision_id, entity_name, summary FROM decisions WHERE embedding IS NULL"
            ).fetchall()

        if not rows:
            return

        for r in rows:
            content = f"{r['entity_name']}: {r['summary']}"
            self.index_decision(r["decision_id"], content)

    def search(self, query: str, top_k: int = 3, min_similarity: float = 0.45) -> List[Dict[str, Any]]:
        """
        Executes semantic cosine similarity search across all indexed decisions.
        Returns top matching decision dictionaries sorted by relevance score.
        """
        if not query or len(query.strip()) < 2:
            return []

        # 1. Compute query vector
        query_vec = self.embed_text(query)

        # 2. Fetch all candidates with embeddings
        with self.db.get_connection(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT decision_id, entity_name, summary, proposed_by, agreed_by,
                       status, effective_from, embedding
                FROM decisions
                WHERE embedding IS NOT NULL
                """
            ).fetchall()

        if not rows:
            return []

        # 3. Vectorized batch dot-product
        ids = []
        vectors = []
        metadata = []

        for r in rows:
            blob = r["embedding"]
            if blob:
                vec = np.frombuffer(blob, dtype=np.float32)
                vectors.append(vec)
                metadata.append(dict(r))

        if not vectors:
            return []

        matrix = np.vstack(vectors)
        scores = np.dot(matrix, query_vec)

        # 4. Rank by similarity
        results = []
        for idx in np.argsort(-scores):
            score = float(scores[idx])
            if score < min_similarity:
                break
            item = metadata[idx]
            item["similarity_score"] = score
            results.append(item)
            if len(results) >= top_k:
                break

        return results
