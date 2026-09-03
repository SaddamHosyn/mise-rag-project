CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE forms_directory (
    id SERIAL PRIMARY KEY,
    form_name TEXT NOT NULL,
    category VARCHAR(100),
    file_type VARCHAR(20),
    source_url TEXT NOT NULL,
    description TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    source_url TEXT,
    file_type VARCHAR(20),
    language VARCHAR(10) DEFAULT 'sv',
    scraped_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INT REFERENCES documents(id),
    chunk_text TEXT NOT NULL,
    chunk_index INT,
    embedding VECTOR(768),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE evaluation_logs (
    id SERIAL PRIMARY KEY,
    user_query TEXT,
    generated_sql TEXT,
    raw_result TEXT,
    final_answer TEXT,
    sql_accuracy_score INT,
    faithfulness_score INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_forms_name_trgm ON forms_directory USING gin (form_name gin_trgm_ops);
CREATE INDEX idx_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);
