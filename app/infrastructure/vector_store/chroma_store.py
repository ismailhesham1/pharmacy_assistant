"""
Concrete VectorStorePort implementation using Chroma. This is the ONLY file in
the whole app that should ever import chromadb
"""
import chromadb

from domain.entities import ProductChunk, PolicyChunk
from domain.ports import VectorStorePort

PRODUCTS_COLLECTION = "pharmacy_products"
POLICY_COLLECTION = "pharmacy_policies"


class ChromaStore(VectorStorePort):
    def __init__(self, persist_dir: str, embedding_function=None):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_function = embedding_function

        self.products = self.client.get_or_create_collection(
            PRODUCTS_COLLECTION, embedding_function=embedding_function
        )
        self.policies = self.client.get_or_create_collection(
            POLICY_COLLECTION, embedding_function=embedding_function
        )

    def add_product_chunks(self, chunks: list[ProductChunk]) -> None:
        if not chunks:
            return

        ids = [f"{c.product_id}:{c.lang}" for c in chunks]
        documents = [c.embed_text for c in chunks]
        metadatas = [
            {
                "doc_type": "product",
                "product_id": c.product_id,
                "lang": c.lang,
                "title": c.title or "",
                "price": c.price if c.price is not None else -1.0,
                "currency": c.currency or "",
                "in_stock": c.in_stock if c.in_stock is not None else False,
                "brand": c.brand or "",
                "category_path": " > ".join(c.category_path) if c.category_path else "",
                "product_url": c.product_url or "",
                "image_url": c.image_url or "",
            }
            for c in chunks
        ]

        batch_size = 500
        total_batches = (len(ids) + batch_size - 1) // batch_size
        for i in range(0, len(ids), batch_size):
            batch_num = i // batch_size + 1
            batch_ids = ids[i:i + batch_size]
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]

            already_present = set(self.products.get(ids=batch_ids)["ids"])
            new_indices = [j for j, bid in enumerate(batch_ids) if bid not in already_present]

            if not new_indices:
                print(f"  product batch {batch_num}/{total_batches} already indexed - skipping")
                continue

            self.products.add(
                ids=[batch_ids[j] for j in new_indices],
                documents=[batch_docs[j] for j in new_indices],
                metadatas=[batch_meta[j] for j in new_indices],
            )
            skipped = len(batch_ids) - len(new_indices) #progressReporting
            skip_note = f" ({skipped} already indexed, skipped)" if skipped else ""
            print(f"  product batch {batch_num}/{total_batches} embedded and stored "
                  f"({min(i + batch_size, len(ids))}/{len(ids)} chunks){skip_note}")

    def add_policy_chunks(self, chunks: list[PolicyChunk]) -> None:
        if not chunks:
            return

        ids = [f"{c.source_url}:{c.lang}:{i}" for i, c in enumerate(chunks)]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "doc_type": "policy",
                "lang": c.lang,
                "source_url": c.source_url,
                "section_title": c.section_title,
            }
            for c in chunks
        ]

        batch_size = 500
        total_batches = (len(ids) + batch_size - 1) // batch_size
        for i in range(0, len(ids), batch_size):
            batch_num = i // batch_size + 1
            batch_ids = ids[i:i + batch_size]
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]

            already_present = set(self.policies.get(ids=batch_ids)["ids"])
            new_indices = [j for j, bid in enumerate(batch_ids) if bid not in already_present]

            if not new_indices:
                print(f"  policy batch {batch_num}/{total_batches} already indexed - skipping")
                continue

            self.policies.add(
                ids=[batch_ids[j] for j in new_indices],
                documents=[batch_docs[j] for j in new_indices],
                metadatas=[batch_meta[j] for j in new_indices],
            )
            skipped = len(batch_ids) - len(new_indices)
            skip_note = f" ({skipped} already indexed, skipped)" if skipped else ""
            print(f"  policy batch {batch_num}/{total_batches} embedded and stored "
                  f"({min(i + batch_size, len(ids))}/{len(ids)} chunks){skip_note}")

    def search(self, query: str, lang: str | None = None, doc_type: str | None = None,
               filters: dict | None = None, k: int = 5) -> list[dict]:
        where = self._build_where(lang, filters)

        results = []
        collections = []
        if doc_type in (None, "product"):
            collections.append(self.products)
        if doc_type in (None, "policy"):
            collections.append(self.policies)

        for collection in collections:
            res = collection.query(
                query_texts=[query],
                n_results=k,
                where=where,
            )
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                results.append({"text": doc, "metadata": meta, "distance": dist})

        results.sort(key=lambda r: r["distance"])
        return results[:k] #combines sseperate chroma lists into one result

    @staticmethod
    def _build_where(lang: str | None, filters: dict | None) -> dict | None:
        """
        Chroma requires a where clause to have exactly ONE top-level operator -
        so 'lang' can't just be added as a sibling key next to an existing
        '$and' from filters. Collect every condition into one list and wrap
        in a single $and if there's more than one; return the bare condition
        if there's only one; return None if there are none.
        """
        conditions = []

        if filters:
            if "$and" in filters:
                conditions.extend(filters["$and"])
            elif filters:
                conditions.append(filters)

        if lang:
            conditions.append({"lang": lang})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def get_product_by_id(self, product_id: str, lang: str) -> dict | None:
        res = self.products.get(ids=[f"{product_id}:{lang}"])
        if not res["ids"]:
            return None
        return {"text": res["documents"][0], "metadata": res["metadatas"][0]}