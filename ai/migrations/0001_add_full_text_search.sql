-- Apply after langchain-postgres has created langchain_pg_embedding in Neon.
-- The generated column is populated for existing rows and stays synchronized
-- with future inserts and updates to document text.
ALTER TABLE langchain_pg_embedding
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(document, ''))) STORED;

CREATE INDEX IF NOT EXISTS langchain_pg_embedding_search_vector_gin
    ON langchain_pg_embedding USING GIN (search_vector);
