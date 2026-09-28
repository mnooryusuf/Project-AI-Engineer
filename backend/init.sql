-- Init Database Script
-- Dijalankan otomatis saat container PostgreSQL pertama kali dibuat

-- Aktifkan extension pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabel chat_history
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    -- Pemilik sesi — dipakai untuk sidebar riwayat & memastikan satu user
    -- tidak bisa membaca riwayat chat user lain lewat /chat/history.
    user_id BIGINT,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_history(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);

-- Tabel documents (dengan embedding vector)
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    -- paraphrase-multilingual menghasilkan 768 dimensi — harus sama dengan
    -- Vector(768) di models.py. Ganti model embedding = ubah angka ini dan
    -- jalankan reindex_documents.py (lihat README).
    embedding VECTOR(768),
    metadata JSONB,
    -- Tingkat akses: umum (semua akun) | internal (user & admin) | rahasia (admin).
    access_level VARCHAR(20) NOT NULL DEFAULT 'internal' CHECK (access_level IN ('umum', 'internal', 'rahasia')),
    uploaded_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);
CREATE INDEX IF NOT EXISTS idx_documents_access_level ON documents(access_level);
-- Index untuk similarity search.
-- HNSW, bukan ivfflat: ivfflat membagi data ke sejumlah list dan secara default
-- hanya memindai satu list per query, sehingga pada knowledge base kecil
-- (puluhan chunk) sebagian besar baris tidak pernah ikut terpindai.
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents
    USING hnsw (embedding vector_cosine_ops);

-- Tabel users (JWT auth)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'read_only' CHECK (role IN ('admin', 'user', 'read_only')),
    is_active BOOLEAN DEFAULT TRUE,
    privacy_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tidak ada akun admin bawaan. Buat admin pertama dari backend/:
--   .venv/bin/python3 manage_users.py create-admin <username> <email>

-- ── User read-only khusus SQL Agent ──────────────────────
-- SQL_QUERY tool sebelumnya memakai koneksi "postgres" (superuser) yang
-- sama dengan seluruh aplikasi — perlindungannya 100% bergantung pada
-- validasi di level aplikasi (whitelist tabel, blocklist kata kunci).
-- Role ini jadi lapisan pertahanan kedua: walau ada celah yang belum
-- ditemukan di validator, role ini secara fisik TIDAK PUNYA izin menulis
-- atau mengakses tabel users sama sekali — dipaksakan oleh PostgreSQL
-- sendiri, bukan oleh kode Python.
-- GANTI PASSWORD INI untuk deployment sungguhan.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agentic_rag_readonly') THEN
        CREATE ROLE agentic_rag_readonly WITH LOGIN PASSWORD 'readonly_agent_pw_2026';
    END IF;
END
$$;

-- Query timeout 5 detik — mencegah SQL hasil generate LLM (yang kadang
-- salah bentuk, mis. JOIN tak sengaja) menahan koneksi tanpa batas waktu.
ALTER ROLE agentic_rag_readonly SET statement_timeout = '5000';

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM agentic_rag_readonly;
GRANT CONNECT ON DATABASE agentic_rag TO agentic_rag_readonly;
GRANT USAGE ON SCHEMA public TO agentic_rag_readonly;
GRANT SELECT ON chat_history, documents TO agentic_rag_readonly;
-- users TIDAK diberi GRANT sama sekali — SELECT ke tabel itu akan gagal
-- dengan "permission denied" di level database, bukan cuma ditolak validator.

SELECT 'Database initialized successfully' AS status;
