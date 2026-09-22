"""
tools/sql_tool.py — SQL Tool (READ-ONLY)
Hanya memperbolehkan SELECT pada tabel yang di-whitelist.
Agent tidak dapat melakukan DROP, DELETE, UPDATE, INSERT.

Pertahanan berlapis dua:
1. Level aplikasi — validate_sql_query() di bawah (whitelist tabel,
   blocklist kata kunci, larangan multi-statement).
2. Level database — query dieksekusi lewat `agentic_rag_readonly`, role
   PostgreSQL terpisah yang secara fisik hanya diberi GRANT SELECT pada
   chat_history & documents (lihat init.sql). Kalau lapisan 1 di atas
   pernah punya celah yang belum ditemukan, lapisan 2 tetap menahan —
   PostgreSQL sendiri yang menolak, bukan kode Python.
"""
import re
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

# Tabel yang boleh diakses Agent.
# Tabel "users" sengaja tidak masuk daftar: berisi hashed_password.
ALLOWED_TABLES = {"chat_history", "documents"}

# Kata kunci berbahaya yang harus diblokir
FORBIDDEN_KEYWORDS = {
    "drop", "delete", "update", "insert", "truncate",
    "alter", "create", "grant", "revoke", "exec",
}

# Nama tabel yang mengikuti FROM / JOIN, termasuk bentuk ber-skema (public.users).
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", re.IGNORECASE)


def validate_sql_query(query: str) -> tuple[bool, str]:
    """
    Validasi query sebelum dieksekusi.
    Mengembalikan (is_valid, pesan_error).
    """
    query_lower = query.lower().strip()

    # Harus dimulai dengan SELECT
    if not query_lower.startswith("select"):
        return False, "Hanya query SELECT yang diperbolehkan."

    # Tolak statement bertumpuk (mis. "SELECT 1; DROP TABLE users").
    if ";" in query_lower.rstrip().rstrip(";"):
        return False, "Query tidak boleh berisi lebih dari satu statement."

    # Cek kata kunci berbahaya. Pencocokan harus per kata utuh — tanpa batas
    # kata, kolom sah seperti "created_at" akan terbaca sebagai "CREATE".
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", query_lower):
            return False, f"Query mengandung operasi yang tidak diperbolehkan: {keyword.upper()}"

    # Tegakkan whitelist tabel. Tanpa ini, agent bisa diarahkan membaca tabel
    # users dan membocorkan hash password.
    referenced = {t.split(".")[-1] for t in _TABLE_REF.findall(query_lower)}
    if not referenced:
        return False, "Query harus menyebut tabel yang diizinkan."

    forbidden = referenced - ALLOWED_TABLES
    if forbidden:
        return False, (
            f"Tabel tidak diizinkan: {', '.join(sorted(forbidden))}. "
            f"Hanya boleh: {', '.join(sorted(ALLOWED_TABLES))}."
        )

    return True, ""


@lru_cache()
def _get_readonly_sessionmaker() -> sessionmaker:
    """
    Engine terpisah dari koneksi utama aplikasi (lihat database.py), memakai
    role `agentic_rag_readonly`. Dibuat lazy + di-cache supaya hanya satu
    connection pool yang dibuat sepanjang umur proses, dan supaya import
    modul ini tidak langsung mencoba konek ke DB (mis. saat testing).
    """
    engine = create_engine(
        get_settings().database_url_readonly.replace("postgresql://", "postgresql+psycopg://"),
        pool_pre_ping=True,
        pool_size=2,
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def run_sql_query(query: str, db: Session = None, limit: int = 20) -> dict:
    """
    Jalankan query SQL read-only dengan batas hasil.

    Parameter `db` (sesi utama aplikasi) TIDAK dipakai untuk eksekusi lagi —
    dipertahankan hanya demi kompatibilitas pemanggil lama. Query yang
    dihasilkan LLM dijalankan lewat koneksi `agentic_rag_readonly` yang
    terpisah total, supaya kalaupun query itu entah bagaimana lolos validasi
    di atas (mis. celah yang belum ditemukan) dan mencoba menulis atau
    membaca tabel users, PostgreSQL sendiri yang menolaknya di level
    permission — bukan cuma diasumsikan aman karena sudah lolos regex. Ini
    juga sekaligus menghapus risiko transaksi sesi utama ikut rusak
    (`InFailedSqlTransaction`) kalau query yang di-generate LLM error,
    karena sesi utama tidak pernah tersentuh sama sekali oleh query ini.
    """
    is_valid, error_msg = validate_sql_query(query)
    if not is_valid:
        return {
            "success": False,
            "error": error_msg,
            "rows": [],
            "count": 0,
        }

    if "limit" not in query.lower():
        query = f"{query.rstrip(';')} LIMIT {limit}"

    session = _get_readonly_sessionmaker()()
    try:
        result = session.execute(text(query))
        rows = [dict(row._mapping) for row in result.fetchall()]

        return {
            "success": True,
            "rows": rows,
            "count": len(rows),
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Query gagal: {str(e)}",
            "rows": [],
            "count": 0,
        }
    finally:
        session.close()
