"""
Run this AFTER build_index.py has completed, to manually inspect whether
retrieval actually works - especially cross-lingual (the core AR/EN
requirement). This doesn't build anything, just queries the already-persisted
Chroma store and prints results for you to read.

Run with:
    cd app
    python scripts/verify_index.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.vector_store.chroma_store import ChromaStore

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma")


def get_embedding_function():
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3", normalize_embeddings=True)


def print_results(label, results):
    print(f"\n--- {label} ---")
    if not results:
        print("  (no results)")
    for r in results:
        m = r["metadata"]
        if m.get("doc_type") == "product":
            print(f"  [{r['distance']:.3f}] {m['title']} - {m['price']} {m['currency']} "
                  f"(in_stock={m['in_stock']}, lang={m['lang']})")
        else:
            print(f"  [{r['distance']:.3f}] [{m['section_title']}] {r['text'][:80]}...")


def run():
    embedding_fn = get_embedding_function()
    store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR, embedding_function=embedding_fn)

    print(f"Index contains {store.products.count()} products, {store.policies.count()} policy chunks")

    # 1. Basic English product search - sanity check it returns *something* relevant
    print_results("EN: 'baby formula milk'",
                  store.search("baby formula milk", doc_type="product", k=5))

    # 2. Same concept in Arabic - THE cross-lingual test. If this returns similar/related
    # products to the English query above, cross-lingual retrieval is working.
    print_results("AR: 'حليب أطفال' (baby milk)",
                  store.search("حليب أطفال", doc_type="product", k=5))

    # 3. Metadata filtering combined with semantic search
    print_results("EN: 'diapers' + price <= 150 SAR",
                  store.search("diapers", doc_type="product",
                                filters={"price": {"$lte": 150}}, k=5))

    # 4. Policy search - should surface the actual disclaimer/return-policy text
    print_results("EN: 'return policy'",
                  store.search("return policy", doc_type="policy", k=3))
    print_results("AR: 'سياسة الإرجاع' (return policy)",
                  store.search("سياسة الإرجاع", doc_type="policy", k=3))

    print("\n--- What to actually check ---")
    print("1. Do the EN and AR baby-milk searches return the SAME or clearly related")
    print("   products? If AR results look random/unrelated, cross-lingual retrieval")
    print("   isn't working well and it's worth trying the MiniLM fallback model.")
    print("2. Does the price filter actually exclude anything above 150 SAR?")
    print("3. Does the policy search return real return-policy text, not junk?")


if __name__ == "__main__":
    run()