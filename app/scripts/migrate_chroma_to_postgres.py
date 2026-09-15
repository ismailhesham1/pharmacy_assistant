"""
One-time migration: pulls existing vectors, text, and metadata directly out
of Chroma and inserts them into Postgres. No re-embedding, no re-scraping -
the embeddings themselves are just numbers, portable between any store.

Run once, after the new Postgres schema exists (see schema.sql) and BEFORE
switching agent/tools.py and scripts/build_index.py over to PostgresStore.
Your existing Chroma data and working app are untouched by this script.

Usage:
    cd app
    python scripts/migrate_chroma_to_postgres.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from pgvector.psycopg2 import register_vector
from pgvector import Vector

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma")

# Match your actual Postgres setup from earlier steps.
PG_CONFIG = dict(host="localhost", dbname="pharmacy", user="pharmacy_user", password="zim100100")


def migrate_collection(chroma_collection, pg_conn, table: str, id_field_map):
    """
    id_field_map: which Chroma metadata field(s) become which Postgres columns
    - products and policies have different shapes, so this is passed in per call.
    """
    print(f"Reading all records from Chroma collection '{chroma_collection.name}' ...")
    result = chroma_collection.get(include=["embeddings", "documents", "metadatas"])

    ids = result["ids"]
    embeddings = result["embeddings"]
    documents = result["documents"]
    metadatas = result["metadatas"]

    print(f"  {len(ids)} records found. Inserting into Postgres table '{table}' ...")

    with pg_conn.cursor() as cur:
        for i, chroma_id in enumerate(ids):
            metadata = metadatas[i]
            row_values = id_field_map(chroma_id, documents[i], metadata)
            columns = ", ".join(row_values.keys())
            placeholders = ", ".join(["%s"] * len(row_values))
            values = list(row_values.values())
            values.append(Vector(embeddings[i]))

            cur.execute(
                f"""
                INSERT INTO {table} ({columns}, embedding)
                VALUES ({placeholders}, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                values,
            )

            if (i + 1) % 500 == 0:
                print(f"    ...{i + 1}/{len(ids)} inserted")

    pg_conn.commit()
    print(f"  Done. {table} now has data migrated from Chroma.")


def run():
    from chromadb import PersistentClient

    chroma_client = PersistentClient(path=CHROMA_PERSIST_DIR)
    products_collection = chroma_client.get_collection("pharmacy_products")
    policies_collection = chroma_client.get_collection("pharmacy_policies")

    pg_conn = psycopg2.connect(**PG_CONFIG)
    register_vector(pg_conn)

    migrate_collection(
        products_collection, pg_conn, "products",
        id_field_map=lambda chroma_id, doc, m: {
            "id": chroma_id,
            "product_id": m.get("product_id"),
            "lang": m.get("lang"),
            "embed_text": doc,
            "title": m.get("title") or None,
            "price": None if m.get("price") == -1.0 else m.get("price"),  # undo Chroma's None sentinel
            "currency": m.get("currency") or None,
            "in_stock": m.get("in_stock"),
            "brand": m.get("brand") or None,
            "category_path": m.get("category_path") or None,
            "product_url": m.get("product_url") or None,
            "image_url": m.get("image_url") or None,
        },
    )

    migrate_collection(
        policies_collection, pg_conn, "policies",
        id_field_map=lambda chroma_id, doc, m: {
            "id": chroma_id,
            "lang": m.get("lang"),
            "section_title": m.get("section_title") or None,
            "source_url": m.get("source_url") or None,
            "text": doc,
        },
    )

    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM products;")
        product_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM policies;")
        policy_count = cur.fetchone()[0]

    print(f"\nMigration complete: {product_count} products, {policy_count} policy chunks in Postgres.")
    pg_conn.close()


if __name__ == "__main__":
    run()