from domain.ports import VectorStorePort


def build_product_filters(price_min: float | None = None, price_max: float | None = None,
                           brand: str | None = None, category: str | None = None,
                           in_stock_only: bool = False) -> dict:
    """
    Translates named, meaningful filter arguments into Chroma's where-clause
    shape. Kept separate from ChromaStore on purpose - the vector store
    shouldn't need to know what "price_max" *means*, just how to apply a
    generic filters dict.
    """
    conditions = []
    if price_min is not None:
        conditions.append({"price": {"$gte": price_min}})
    if price_max is not None:
        conditions.append({"price": {"$lte": price_max}})
    if brand:
        conditions.append({"brand": brand})
    if category:
        conditions.append({"category_path": category})
    if in_stock_only:
        conditions.append({"in_stock": True})

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]  #same conditions as build_where
    return {"$and": conditions}


def search_products(store: VectorStorePort, query: str, lang: str,
                     price_min: float | None = None, price_max: float | None = None,
                     brand: str | None = None, category: str | None = None,
                     in_stock_only: bool = False, k: int = 5) -> list[dict]:
    """
    Semantic search over the product catalog, combined with structured filters
    in one call - e.g. "allergy medicine" + price_max=30 + in_stock_only=True.
    Returns a list of flat product dicts (metadata + description + a relevance
    distance), ready to hand to the LLM or render in the UI.

    NOTE: includes "description" (the embedded text - title + description +
    classifications) - without this, the agent has no way to answer usage
    questions ("how do I use this", "what is this for"), since that text is
    what search matches against but was previously dropped before reaching
    the LLM, even though it's right there in the vector store's data.
    """
    filters = build_product_filters(price_min, price_max, brand, category, in_stock_only)
    raw_results = store.search(query, lang=lang, doc_type="product", filters=filters, k=k)

    return [
        {**r["metadata"], "description": r["text"], "relevance_distance": r["distance"]}
        for r in raw_results
    ]


def search_policy(store: VectorStorePort, query: str, lang: str, k: int = 3) -> list[dict]:
    """Semantic search over policy/T&C sections - for answering policy questions."""
    raw_results = store.search(query, lang=lang, doc_type="policy", k=k)

    return [
        {
            "section_title": r["metadata"].get("section_title"),
            "source_url": r["metadata"].get("source_url"),
            "text": r["text"],
            "relevance_distance": r["distance"],
        }
        for r in raw_results
    ]


def get_product_details(store: VectorStorePort, product_id: str, lang: str) -> dict | None:
    """
    Direct lookup by ID, not semantic search - for when the agent already has
    a specific product in mind (e.g. from an earlier search result) and needs
    its full details. Returns None if the product/lang combination doesn't exist.
    """
    result = store.get_product_by_id(product_id, lang)
    if result is None:
        return None
    return {**result["metadata"], "description": result["text"]}