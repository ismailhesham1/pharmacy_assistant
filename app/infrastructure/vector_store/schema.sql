CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    lang TEXT NOT NULL,
    embed_text TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    title TEXT,
    price FLOAT,
    currency TEXT,
    in_stock BOOLEAN,
    brand TEXT,
    category_path TEXT,
    product_url TEXT,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY,
    lang TEXT NOT NULL,
    section_title TEXT,
    source_url TEXT,
    text TEXT NOT NULL,
    embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS products_embedding_idx
    ON products USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS policies_embedding_idx
    ON policies USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS products_lang_idx ON products (lang);
CREATE INDEX IF NOT EXISTS products_price_idx ON products (price);
CREATE INDEX IF NOT EXISTS products_in_stock_idx ON products (in_stock);
CREATE INDEX IF NOT EXISTS policies_lang_idx ON policies (lang);