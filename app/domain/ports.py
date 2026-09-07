from abc import ABC, abstractmethod

from domain.entities import ProductChunk, PolicyChunk


class VectorStorePort(ABC):
    @abstractmethod
    def add_product_chunks(self, chunks: list[ProductChunk]) -> None:
        """Embeds and stores product chunks, with their structured fields as metadata."""
        ...

    @abstractmethod
    def add_policy_chunks(self, chunks: list[PolicyChunk]) -> None:
        """Embeds and stores policy chunks."""
        ...

    @abstractmethod
    def search(self, query: str, lang: str | None = None, doc_type: str | None = None,
               filters: dict | None = None, k: int = 5) -> list[dict]:
        """
        Semantic search with optional metadata filtering.
        doc_type: "product" | "policy" | None (both)
        filters: extra metadata conditions, e.g. {"price": {"$lte": 30}, "in_stock": True}
        Returns a list of dicts with at least: text, metadata, distance.
        """
        ...

    @abstractmethod
    def get_product_by_id(self, product_id: str, lang: str) -> dict | None:
        """
        Direct exact-ID lookup, not semantic search - for when the caller already
        knows which product it wants (e.g. following up on an earlier search
        result) and needs its full stored metadata. Returns None if not found.
        """
        ...