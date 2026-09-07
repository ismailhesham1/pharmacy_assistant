"""
Composition root: the ONE place where every piece actually gets wired together
and the real embedding model gets instantiated. Run with:

    cd app
    python scripts/build_index.py

Everything before this point (domain/, application/, infrastructure/) was just
definitions - this is the file that makes it actually run.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # add app/ to path

from infrastructure.data_loaders.jsonl_loader import load_scraper_output
from infrastructure.vector_store.chroma_store import ChromaStore
from application.use_cases.build_index import build_index

SCRAPER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraper", "data")
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma")


def get_embedding_function():
    """
    The actual model gets loaded HERE, and nowhere else. bge-m3: strong native
    Arabic + English support, no query/passage prefix convention needed.
    First run downloads the model (~2.2GB) - needs normal internet access,
    cached locally after that.
    """
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3", normalize_embeddings=True)


def run():
    print(f"Loading scraped data from {SCRAPER_DATA_DIR} ...")
    structured, full, content_pages = load_scraper_output(SCRAPER_DATA_DIR)
    print(f"  {len(structured)} structured records, {len(full)} full records, "
          f"{len(content_pages)} content pages")

    print("\nBuilding chunks (merge, embed-text, policy splitting)...")
    result = build_index(structured, full, content_pages)
    print(f"  {len(result.product_chunks)} product chunks")
    print(f"  {len(result.policy_chunks)} policy chunks")
    print(f"  {result.products_missing_description} products used fallback text (no description)")

    print("\nLoading embedding model (bge-m3 - first run downloads ~2.2GB)...")
    embedding_fn = get_embedding_function()

    print(f"\nWriting to Chroma at {CHROMA_PERSIST_DIR} ...")
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    store = ChromaStore(persist_dir=CHROMA_PERSIST_DIR, embedding_function=embedding_fn)

    store.add_product_chunks(result.product_chunks)
    store.add_policy_chunks(result.policy_chunks)

    print(f"\nDone. {store.products.count()} products indexed, {store.policies.count()} policy chunks indexed.")


if __name__ == "__main__":
    run()