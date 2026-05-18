"""
sheaf_cards/embeddings.py — Embedding engine for knowledge cards.

Supports SiliconFlow / OpenAI embedding APIs with local FAISS index.
Pure numpy fallback when FAISS is not installed.

Usage:
    from sheaf_cards.embeddings import EmbeddingEngine

    engine = EmbeddingEngine(Path("data/embeddings"))
    engine.build_index(cards)
    results = engine.search("remote sensing vegetation", top_k=5)
"""
from __future__ import annotations

import json
import os
import hashlib
import numpy as np
from pathlib import Path
from typing import Optional

from sheaf_cards.base import KnowledgeCard


# ============================================================
# Embedding API client
# ============================================================

def _get_api_client():
    """Get OpenAI-compatible client for embeddings (SiliconFlow default)."""
    from openai import OpenAI

    api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key:
        # Try loading from .env (cwd first, then package parent)
        for env_path in [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "SILICONFLOW_API_KEY":
                            api_key = v.strip()
                            break
                if api_key:
                    break

    if not api_key:
        raise ValueError("SILICONFLOW_API_KEY not found. Set it in .env or environment.")

    base_url = os.environ.get("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
EMBEDDING_DIM = 1024  # bge-large-zh dimension


def embed_texts(texts: list[str], model: str = None) -> list[list[float]]:
    """Call embedding API for a batch of texts.

    Returns list of embedding vectors.
    """
    model = model or os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    client = _get_api_client()

    response = client.embeddings.create(
        model=model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_single(text: str, model: str = None) -> list[float]:
    """Embed a single text string."""
    return embed_texts([text], model=model)[0]


# ============================================================
# EmbeddingEngine — index management + search
# ============================================================

class EmbeddingEngine:
    """Manages embedding index for knowledge cards.

    Storage format:
        index.npy      — (N, dim) numpy array of embeddings
        metadata.json  — [{card_id, text_hash}] aligned with index rows

    Uses cosine similarity for search.
    """

    def __init__(self, store_dir: Path, dim: int = EMBEDDING_DIM):
        self.dir = Path(store_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.index_path = self.dir / "index.npy"
        self.meta_path = self.dir / "metadata.json"

        self._vectors: Optional[np.ndarray] = None  # (N, dim)
        self._metadata: list[dict] = []
        self._id_to_row: dict[str, int] = {}  # card_id -> row index

        self._load()

    # --- Internal ---

    def _load(self):
        """Load index from disk if exists."""
        if self.index_path.exists() and self.meta_path.exists():
            self._vectors = np.load(str(self.index_path))
            self._metadata = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self._rebuild_id_map()
        else:
            self._vectors = np.empty((0, self.dim), dtype=np.float32)
            self._metadata = []

    def _rebuild_id_map(self):
        self._id_to_row = {
            m["card_id"]: i for i, m in enumerate(self._metadata) if "card_id" in m
        }

    def _save(self):
        """Persist index and metadata to disk."""
        if self._vectors is not None and len(self._vectors) > 0:
            np.save(str(self.index_path), self._vectors)
        self.meta_path.write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _text_for_card(card: KnowledgeCard) -> str:
        """Build embedding input from card fields."""
        parts = [card.title, card.claim]
        if card.evidence:
            parts.append(card.evidence)
        if card.tags:
            parts.append(" ".join(card.tags))
        return " | ".join(p for p in parts if p)

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between vector a and matrix b."""
        if len(b) == 0:
            return np.array([])
        a_norm = a / (np.linalg.norm(a) + 1e-8)
        b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
        return b_norm @ a_norm

    # --- Public API ---

    def build_index(self, cards: list[KnowledgeCard], model: str = None,
                    batch_size: int = 32):
        """Build embedding index from scratch for a list of cards.

        Processes in batches to avoid API rate limits.
        """
        texts = [self._text_for_card(c) for c in cards]
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = embed_texts(batch, model=model)
            all_embeddings.extend(embeddings)
            print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)} cards")

        self._vectors = np.array(all_embeddings, dtype=np.float32)
        self._metadata = [
            {"card_id": c.card_id, "text_hash": hashlib.md5(t.encode()).hexdigest()[:8]}
            for c, t in zip(cards, texts)
        ]
        self._rebuild_id_map()
        self._save()
        print(f"Index built: {len(self._vectors)} vectors, dim={self.dim}")

    def update_index(self, cards: list[KnowledgeCard], model: str = None):
        """Incrementally add/update cards in the index.

        Skips cards whose text_hash hasn't changed.
        """
        new_vectors = []
        new_meta = []
        changed = False

        for card in cards:
            text = self._text_for_card(card)
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]

            existing_row = self._id_to_row.get(card.card_id)
            if existing_row is not None:
                old_meta = self._metadata[existing_row]
                if old_meta.get("text_hash") == text_hash:
                    continue  # No change

            # Need to (re)embed
            vec = embed_single(text, model=model)
            new_vectors.append(vec)
            new_meta.append({"card_id": card.card_id, "text_hash": text_hash})
            changed = True

        if not changed:
            print("No updates needed.")
            return

        # Append new vectors
        if new_vectors:
            new_arr = np.array(new_vectors, dtype=np.float32)
            if self._vectors is not None and len(self._vectors) > 0:
                # Remove old versions first
                remove_ids = {m["card_id"] for m in new_meta}
                keep_mask = [
                    i for i, m in enumerate(self._metadata)
                    if m.get("card_id") not in remove_ids
                ]
                if keep_mask:
                    self._vectors = self._vectors[keep_mask]
                    self._metadata = [self._metadata[i] for i in keep_mask]
                else:
                    self._vectors = np.empty((0, self.dim), dtype=np.float32)
                    self._metadata = []

            self._vectors = np.vstack([self._vectors, new_arr]) if len(self._vectors) > 0 else new_arr
            self._metadata.extend(new_meta)
            self._rebuild_id_map()
            self._save()
            print(f"Updated: +{len(new_vectors)} cards, total={len(self._vectors)}")

    def search(self, query: str, top_k: int = 10, model: str = None) -> list[tuple[str, float]]:
        """Semantic search. Returns [(card_id, score)] sorted by relevance.

        Uses cosine similarity between query embedding and card embeddings.
        """
        if self._vectors is None or len(self._vectors) == 0:
            return []

        query_vec = np.array(embed_single(query, model=model), dtype=np.float32)
        scores = self._cosine_sim(query_vec, self._vectors)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            meta = self._metadata[idx]
            results.append((meta["card_id"], float(scores[idx])))
        return results

    def count(self) -> int:
        return len(self._vectors) if self._vectors is not None else 0
