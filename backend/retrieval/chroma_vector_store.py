from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models import Product, Review
from backend.retrieval.embeddings import EmbeddingProvider, create_embedding_provider
from backend.retrieval.product_vector_store import _product_document
from backend.retrieval.review_vector_store import _aspect_bonus, _review_document


class ChromaUnavailableError(RuntimeError):
    pass


class ChromaProductVectorStore:
    """Persistent Chroma-backed product vector index."""

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = "cartpilot_products",
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        chromadb = _load_chromadb()
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self._get_collection()

    @classmethod
    def from_products(
        cls,
        products: list[Product],
        persist_dir: Path,
        rebuild: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "ChromaProductVectorStore":
        store = cls(persist_dir=persist_dir, embedding_provider=embedding_provider)
        if rebuild or store.count() != len(products):
            store.rebuild(products)
        return store

    def rebuild(self, products: list[Product]) -> None:
        self._reset_collection()
        if not products:
            return
        documents = [_product_document(product) for product in products]
        embeddings = self.embedding_provider.embed_texts(documents)
        self.collection.add(
            ids=[product.product_id for product in products],
            documents=documents,
            embeddings=embeddings,
            metadatas=[
                {
                    "product_id": product.product_id,
                    "category": product.category,
                    "title": product.title,
                    "brand": product.brand,
                    "price": product.price,
                    "tags_json": json.dumps(product.tags, ensure_ascii=False),
                    "specs_json": json.dumps(product.specs, ensure_ascii=False),
                    "provider_name": self.embedding_provider.name,
                }
                for product in products
            ],
        )

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        query_vector = self.embedding_provider.embed_text(query)
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=max(1, top_k),
            where={"category": category} if category else None,
            include=["metadatas", "distances"],
        )
        hits: list[dict[str, Any]] = []
        for product_id, metadata, distance in zip(
            result.get("ids", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            hits.append(
                {
                    "product_id": product_id,
                    "title": metadata.get("title", product_id),
                    "category": metadata.get("category", ""),
                    "vector_score": _distance_to_score(float(distance)),
                    "retrieval_source": "chroma_product_vector_store",
                    "embedding_provider": metadata.get("provider_name", self.embedding_provider.name),
                }
            )
        return hits

    def count(self) -> int:
        return int(self.collection.count())

    def _reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self._get_collection()

    def _get_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_provider": self.embedding_provider.name,
            },
        )


class ChromaReviewVectorStore:
    """Persistent Chroma-backed review evidence vector index."""

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = "cartpilot_reviews",
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        chromadb = _load_chromadb()
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self._get_collection()

    @classmethod
    def from_reviews(
        cls,
        reviews: list[Review],
        persist_dir: Path,
        rebuild: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "ChromaReviewVectorStore":
        store = cls(persist_dir=persist_dir, embedding_provider=embedding_provider)
        if rebuild or store.count() != len(reviews):
            store.rebuild(reviews)
        return store

    def rebuild(self, reviews: list[Review]) -> None:
        self._reset_collection()
        if not reviews:
            return
        documents = [_review_document(review) for review in reviews]
        embeddings = self.embedding_provider.embed_texts(documents)
        self.collection.add(
            ids=[review.review_id for review in reviews],
            documents=[review.content for review in reviews],
            embeddings=embeddings,
            metadatas=[
                {
                    "review_id": review.review_id,
                    "product_id": review.product_id,
                    "rating": review.rating,
                    "aspects_json": json.dumps(review.aspects, ensure_ascii=False),
                    "provider_name": self.embedding_provider.name,
                }
                for review in reviews
            ],
        )

    def count(self) -> int:
        return int(self.collection.count())

    def search(
        self,
        query: str,
        product_id: str | None = None,
        aspects: list[str] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        if self.count() == 0:
            return []
        query_text = " ".join([query, *(aspects or [])])
        query_vector = self.embedding_provider.embed_text(query_text)
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=max(1, top_k * 4),
            where={"product_id": product_id} if product_id else None,
            include=["documents", "metadatas", "distances"],
        )
        scored = []
        for review_id, content, metadata, distance in zip(
            result.get("ids", [[]])[0],
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            aspects_dict = json.loads(metadata.get("aspects_json", "{}"))
            score = _distance_to_score(float(distance))
            if aspects:
                score += _aspect_bonus(aspects_dict, aspects)
            scored.append((score, review_id, content, metadata, aspects_dict))

        scored.sort(key=lambda item: (-item[0], -int(item[3].get("rating", 0))))
        evidence = []
        for score, review_id, content, metadata, aspects_dict in scored[:top_k]:
            evidence.append(
                {
                    "review_id": review_id,
                    "rating": int(metadata.get("rating", 0)),
                    "content": content,
                    "matched_aspects": {
                        aspect: sentiment
                        for aspect, sentiment in aspects_dict.items()
                        if not aspects or aspect in aspects
                    },
                    "retrieval_score": round(score, 4),
                    "retrieval_source": "chroma_vector_store",
                    "embedding_provider": metadata.get("provider_name", self.embedding_provider.name),
                }
            )
        return evidence

    def _reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self._get_collection()

    def _get_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_provider": self.embedding_provider.name,
            },
        )


def _load_chromadb():
    try:
        import chromadb
    except ModuleNotFoundError as error:
        raise ChromaUnavailableError("chromadb_not_installed") from error
    return chromadb


def _distance_to_score(distance: float) -> float:
    return round(max(0.0, 1.0 - distance), 4)
