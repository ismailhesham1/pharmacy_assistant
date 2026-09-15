"""
Postgres + pgvector implementation of VectorStorePort - same contract as
ChromaStore, so nothing in application/ or agent/ needs to change to use
this instead. The main practical differences from ChromaStore, worth
knowing:
  - Filtering is plain SQL WHERE clauses (parameterized - never raw string
    formatting into SQL, to avoid injection), rather than Chroma's custom
    $and/$gte dictionary syntax and its one-top-level-operator limitation.
  - price can be a real SQL NULL here, instead of Chroma's -1.0 sentinel
    (Chroma's metadata simply cannot store None at all).
  - The HNSW index has to be created explicitly (see schema.sql) - Chroma
    does this automatically with zero configuration.
"""
from pgvector import Vector

from domain.entities import ProductChunk, PolicyChunk
from domain.ports import VectorStorePort


class PostgresStore(VectorStorePort):
    def __init__(self, conn, embedding_function):
        """
        conn: an open psycopg2 connection.
        embedding_function: any callable(list[str]) -> list[list[float]],
        e.g. a thin wrapper around SentenceTransformer.encode(...) - kept
        as a plain injected function rather than Chroma's embedding_functions
        class, since pgvector has no equivalent "embedding function" concept
        of its own; we call it ourselves before every insert/search.
        """
        self.conn = conn
        self.embed = embedding_function

        # pgvector's HNSW index defaults to hnsw.ef_search=40 - it only ever
        # considers the 40 nearest raw-embedding candidates before our WHERE
        # filters (brand/category/price/in_stock) are applied. For a selective
        # filter (e.g. one brand out of thousands of products) the matching
        # rows are frequently outside that window, so a real, exact match
        # silently comes back as "no results" - independent of anything else
        # about the query. Raising it trades a bit of per-query index-scan
        # cost (still far cheaper than a full table scan) for actually
        # finding filtered matches that exist. Session-level GUC, so this is
        # set once here rather than per-query.
        with self.conn.cursor() as cur:
            cur.execute("LOAD 'vector'")
            cur.execute("SET hnsw.ef_search = 200")

    def add_product_chunks(self, chunks: list[ProductChunk]) -> None:
        if not chunks:
            return
        texts = [c.embed_text for c in chunks]
        vectors = self.embed(texts)

        with self.conn.cursor() as cur:
            for c, vector in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO products
                        (id, product_id, lang, embed_text, embedding, title, price,
                         currency, in_stock, brand, category_path, product_url, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        f"{c.product_id}:{c.lang}", c.product_id, c.lang, c.embed_text, Vector(vector),
                        c.title, c.price, c.currency, c.in_stock, c.brand,
                        " > ".join(c.category_path) if c.category_path else None,
                        c.product_url, c.image_url,
                    ),
                )
        self.conn.commit()

    def add_policy_chunks(self, chunks: list[PolicyChunk]) -> None:
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = self.embed(texts)

        with self.conn.cursor() as cur:
            for i, (c, vector) in enumerate(zip(chunks, vectors)):
                cur.execute(
                    """
                    INSERT INTO policies (id, lang, section_title, source_url, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (f"{c.source_url}:{c.lang}:{i}", c.lang, c.section_title, c.source_url, c.text, Vector(vector)),
                )
        self.conn.commit()

    def _search_table(self, table: str, text_col: str, query_vector, lang, filters, k) -> list[dict]:
        where_clauses = []
        params = []

        if lang:
            where_clauses.append("lang = %s")
            params.append(lang)

        # filters is the same shape build_product_filters() already produces
        # for the Chroma path - {"price": {"$gte": 5}}, {"brand": "Panadol"},
        # or {"$and": [...]} for multiple conditions - translated here into
        # plain, parameterized SQL instead of Chroma's operator dictionaries.
        if filters:
            conditions = filters.get("$and", [filters]) if "$and" in filters else [filters] if filters else []
            for cond in conditions:
                for field, value in cond.items():
                    if isinstance(value, dict):
                        op_map = {"$gte": ">=", "$lte": "<=", "$gt": ">", "$lt": "<"}
                        for op_key, sql_op in op_map.items():
                            if op_key in value:
                                where_clauses.append(f"{field} {sql_op} %s")
                                params.append(value[op_key])
                    elif field in ("brand", "category_path"):
                        # Case-insensitive match for free-text catalog fields - the LLM
                        # (or a user-supplied filter) may not match the DB's exact casing
                        # (e.g. "dove" vs stored "Dove"). Only for text fields - LOWER()
                        # has no boolean overload, so in_stock and any other non-text
                        # field must stay on exact equality below.
                        where_clauses.append(f"LOWER({field}) = LOWER(%s)")
                        params.append(value)
                    else:
                        where_clauses.append(f"{field} = %s")
                        params.append(value)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT {text_col}, embedding <=> %s AS distance, *
            FROM {table}
            {where_sql}
            ORDER BY distance
            LIMIT %s
        """
        params = [Vector(query_vector)] + params + [k]

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

        results = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            results.append({
                "text": row_dict[text_col],
                "distance": row_dict["distance"],
                "metadata": {k: v for k, v in row_dict.items() if k not in (text_col, "distance", "embedding")},
            })
        return results

    def search(self, query: str, lang: str | None = None, doc_type: str | None = None,
               filters: dict | None = None, k: int = 5) -> list[dict]:
        query_vector = self.embed([query])[0]

        results = []
        if doc_type in (None, "product"):
            for r in self._search_table("products", "embed_text", query_vector, lang, filters, k):
                r["metadata"]["doc_type"] = "product"
                results.append(r)
        if doc_type in (None, "policy"):
            for r in self._search_table("policies", "text", query_vector, lang, filters, k):
                r["metadata"]["doc_type"] = "policy"
                results.append(r)

        results.sort(key=lambda r: r["distance"])
        return results[:k]

    def get_product_by_id(self, product_id: str, lang: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id = %s", (f"{product_id}:{lang}",))
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()

        if row is None:
            return None
        row_dict = dict(zip(columns, row))
        return {
            "text": row_dict["embed_text"],
            "metadata": {k: v for k, v in row_dict.items() if k not in ("embed_text", "embedding")},
        }