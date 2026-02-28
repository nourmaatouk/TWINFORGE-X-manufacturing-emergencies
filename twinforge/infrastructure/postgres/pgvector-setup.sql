-- Enable pgvector extension and create embeddings table
\c twinforge;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embedding ON document_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
