"""
One-off fix: deletes ONLY the policy collection (not products) so it can be
rebuilt with the corrected split_policy_text() logic. Products are unaffected
and untouched - this saves you from re-embedding all 47,920 product chunks
again, which is the part that took hours.

Run with:
    cd app
    python scripts/rebuild_policy_only.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.data_loaders.jsonl_loader import load_scraper_output
from infrastructure.vector_store.chroma_store import ChromaStore, POLICY_COLLECTION
from application.use_cases.build_index import build_index

SCRAPER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraper", "data")
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma")


def get_embedding_function():
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3", normalize_embeddings=True)


def run():
    print("Loading content pages...")
    _, _, content_pages = load_scraper_output(SCRAPER_DATA_DIR)
    print(f"  {len(content_pages)} content pages")

    print("\nRe-chunking with the fixed split_policy_text()...")
    result = build_index(structured=[], full=[], content_pages=content_pages)  # empty products - policy only
    print(f"  {len(result.policy_chunks)} policy chunks (was 575 before the fix - "
          f"compare this number, a big drop means the word-per-line bug was "
          f"badly over-fragmenting before)")

    print("\nLoading embedding model (should be fast - already cached from before)...")
    embedding_fn = get_embedding_function()

    print(f"\nConnecting to Chroma at {CHROMA_PERSIST_DIR} ...")
    store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR, embedding_function=embedding_fn)

    print(f"Products collection untouched: {store.products.count()} chunks (should still be 47920)")

    print("\nDeleting old (buggy) policy collection...")
    store.client.delete_collection(POLICY_COLLECTION)

    print("Recreating policy collection and re-indexing with fixed chunking...")
    store.policies = store.client.get_or_create_collection(POLICY_COLLECTION, embedding_function=embedding_fn)
    store.add_policy_chunks(result.policy_chunks)

    print(f"\nDone. Policy collection now has {store.policies.count()} chunks "
          f"(products still at {store.products.count()}, untouched).")


if __name__ == "__main__":
    run()