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
    refs = _TABLE_REF.findall(query_lower)
    # Nama ber-skema (public.chat_history) ditolak: nama tabel polos wajib
    # dipakai supaya CTE pembatas di run_sql_query (riwayat chat hanya milik
    # pengguna ini) tidak bisa dilewati dengan menyebut tabel aslinya.
    if any("." in t for t in refs):
        return False, "Nama tabel tidak boleh memakai skema (mis. public.)."
    referenced = set(refs)
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


# Pembungkus yang dijalankan di depan SETIAP query. CTE bernama sama dengan
# tabel aslinya "membayangi" tabel itu untuk seluruh query di dalamnya,
# termasuk subquery:
#   - chat_history hanya berisi baris milik pengguna yang bertanya. Role
#     readonly punya SELECT ke SELURUH chat_history, jadi tanpa ini
#     "tampilkan pesan terakhir" bisa membocorkan percakapan pengguna lain.
#   - documents tanpa kolom embedding (vektor 768 angka per baris tidak
#     berguna bagi LLM dan cuma memenuhi jendela konteks).
_SCOPED_QUERY = """WITH chat_history AS (
    SELECT id, session_id, role, message, tool_used, created_at
    FROM public.chat_history WHERE user_id = :scope_user_id
), documents AS (
    SELECT id, filename, content, created_at FROM public.documents
)
SELECT * FROM ({query}) AS hasil LIMIT {limit}"""

# ── Template statistik ────────────────────────────────────────────────
# Query untuk pertanyaan statistik yang umum disusun dari template, bukan
# ditulis LLM. Diuji pada 10 pertanyaan statistik: SQL tulisan llama3.2:3b
# 2x gagal sintaks (tanda kurung AT TIME ZONE), menghitung sesi padahal
# ditanya jumlah pesan, dan mengartikan "minggu ini" sebagai hari ini.
# Query bebas dari LLM tetap dipakai sebagai cadangan untuk pertanyaan yang
# tidak cocok template mana pun.
# created_at bertipe `timestamp WITHOUT time zone` berisi waktu UTC (lihat
# init.sql; server DB berzona Etc/UTC). Harus ditandai UTC dulu baru diubah
# ke WITA — langsung "AT TIME ZONE 'Asia/Makassar'" justru menganggapnya
# waktu WITA dan menggesernya 8 jam ke belakang, sehingga "chat hari ini"
# terhitung 0 padahal ada (diuji).
_LOCAL_TIME = "(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Makassar')"
_NOW_LOCAL = "(now() AT TIME ZONE 'Asia/Makassar')"
_PERIODS = [
    (r"\bhari ini\b", f"{_LOCAL_TIME}::date = {_NOW_LOCAL}::date", "hari ini"),
    (r"\bkemarin\b", f"{_LOCAL_TIME}::date = {_NOW_LOCAL}::date - 1", "kemarin"),
    (r"\bminggu ini\b|\bpekan ini\b", f"date_trunc('week', {_LOCAL_TIME}) = date_trunc('week', {_NOW_LOCAL})", "minggu ini"),
    (r"\bbulan ini\b", f"date_trunc('month', {_LOCAL_TIME}) = date_trunc('month', {_NOW_LOCAL})", "bulan ini"),
    (r"\btahun ini\b", f"date_trunc('year', {_LOCAL_TIME}) = date_trunc('year', {_NOW_LOCAL})", "tahun ini"),
]

# Penanda pertanyaan statistik: kata hitung + objek yang memang ada di
# database. Objek dokumen WAJIB disertai kata penyimpanan ("tersimpan",
# "diunggah", "di database") — tanpa itu "Berapa jumlah dokumen yang harus
# dilampirkan untuk permohonan email?" ikut dianggap statistik padahal
# jawabannya ada di SOP. Diuji: 19 pertanyaan, 19 benar.
_COUNT_WORDS = re.compile(r"\b(berapa|jumlah|total|banyak\w*|rata.rata|statistik|paling (sering|banyak)|terbanyak)\b", re.I)
_CHAT_WORDS = re.compile(r"\b(chat|pesan|percakapan|obrolan|sesi|riwayat|pertanyaan (saya|yang (saya|sudah)))\b", re.I)
_TOOL_WORDS = re.compile(r"\b(tool|fitur)\b", re.I)
_DOC_WORDS = re.compile(
    r"\bchunk|\b(dokumen|file|berkas|gambar)\b.*\b(tersimpan|disimpan|diunggah|diupload|terunggah|di ?database|di knowledge base|di sistem|masuk)\b"
    r"|\b(diunggah|diupload)\b",
    re.I,
)


def is_stats_question(question: str) -> bool:
    return bool(_COUNT_WORDS.search(question)) and bool(
        _CHAT_WORDS.search(question) or _DOC_WORDS.search(question) or _TOOL_WORDS.search(question)
    )


def build_stats_query(question: str) -> tuple[str, str] | None:
    """Susun query dari template -> (sql, keterangan) atau None kalau tidak
    ada template yang cocok. `keterangan` menjelaskan apa yang dihitung,
    supaya jawaban akhir tidak salah menyebut satuannya."""
    q = question.lower()
    where, period = "TRUE", "sepanjang waktu"
    for pattern, cond, label in _PERIODS:
        if re.search(pattern, q):
            where, period = cond, label
            break

    if re.search(r"\btool\b|\balat\b|\bfitur\b", q):
        return (
            f"SELECT tool_used, COUNT(*) AS jumlah FROM chat_history "
            f"WHERE role = 'assistant' AND tool_used IS NOT NULL AND {where} "
            f"GROUP BY tool_used ORDER BY jumlah DESC",
            f"jumlah pemakaian tiap tool dalam jawaban untuk pengguna ini, {period}",
        )
    if re.search(r"\bchunk", q) and re.search(r"paling|terbanyak|terbesar", q):
        return (
            f"SELECT filename, COUNT(*) AS jumlah_chunk FROM documents WHERE {where} "
            f"GROUP BY filename ORDER BY jumlah_chunk DESC",
            f"jumlah chunk per dokumen di knowledge base, {period}",
        )
    if re.search(r"\bchunk", q):
        return (
            f"SELECT COUNT(*) AS jumlah_chunk FROM documents WHERE {where}",
            f"jumlah chunk di knowledge base, {period}",
        )
    if re.search(r"\b(dokumen|file|berkas|gambar)\b", q) and not _CHAT_WORDS.search(q):
        return (
            f"SELECT COUNT(DISTINCT filename) AS jumlah_dokumen FROM documents WHERE {where}",
            f"jumlah dokumen berbeda di knowledge base (milik bersama semua pengguna), {period}",
        )
    if re.search(r"\b(percakapan|obrolan|sesi)\b", q):
        return (
            f"SELECT COUNT(DISTINCT session_id) AS jumlah_percakapan FROM chat_history WHERE {where}",
            f"jumlah percakapan (sesi) milik pengguna ini, {period}",
        )
    if re.search(r"\bjawaban\b", q):
        return (
            f"SELECT COUNT(*) AS jumlah_jawaban FROM chat_history WHERE role = 'assistant' AND {where}",
            f"jumlah jawaban asisten untuk pengguna ini, {period}",
        )
    if re.search(r"\b(chat|pesan|pertanyaan|riwayat)\b", q):
        return (
            f"SELECT COUNT(*) AS jumlah_pesan FROM chat_history WHERE role = 'user' AND {where}",
            f"jumlah pesan/pertanyaan yang dikirim pengguna ini, {period}",
        )
    return None


async def run_sql_query(query: str, db: Session = None, limit: int = 20, user_id: int | None = None) -> dict:
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

    # user_id None -> CTE chat_history kosong (tidak ada user_id = NULL),
    # jadi pemanggil yang lupa mengirim user_id gagal aman, bukan bocor.
    scoped = _SCOPED_QUERY.format(query=query.strip().rstrip(";"), limit=int(limit))

    session = _get_readonly_sessionmaker()()
    try:
        result = session.execute(text(scoped), {"scope_user_id": user_id})
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
