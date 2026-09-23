"""
config.py — Konfigurasi aplikasi dari .env
"""
from pathlib import Path

from pydantic_settings import BaseSettings
from functools import lru_cache

# Root project (satu level di atas folder backend/). Semua path ditambatkan ke
# sini supaya konfigurasi tidak berubah-ubah mengikuti direktori kerja.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    app_env: str = "development"

    # Database
    database_url: str = "postgresql://postgres:mysecretpassword@localhost:5432/agentic_rag"

    # Koneksi terpisah untuk SQL_QUERY tool — role PostgreSQL yang secara
    # fisik hanya punya GRANT SELECT pada chat_history & documents (lihat
    # init.sql). Query yang dihasilkan LLM dieksekusi lewat koneksi ini,
    # bukan lewat `database_url` di atas, supaya proteksinya tidak 100%
    # bergantung pada validasi level-aplikasi di sql_tool.py.
    database_url_readonly: str = (
        "postgresql://agentic_rag_readonly:readonly_agent_pw_2026@localhost:5432/agentic_rag"
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    # 3b, bukan 1b: diuji berdampingan pada analisis dokumen & percakapan
    # lanjutan — 1b meringkas surat undangan jadi 1 kalimat, melewatkan 2 dari
    # 11 penerima, mengarang jawaban saat informasi tidak ada di dokumen, dan
    # salah menyebut harga termahal di berita acara survei harga. 3b benar di
    # keempatnya, dengan harga jawaban 2-4x lebih lambat.
    ollama_llm_model: str = "llama3.2:3b"
    # Jendela konteks LLM (token). 2048 terlalu sempit: dokumen yang
    # dilampirkan hanya muat ~1.800 karakter (6 chunk) sehingga analisis
    # dokumen selalu terpotong, dan tidak tersisa ruang untuk riwayat
    # percakapan. KV-cache 8192 token ~940MB pada llama3.2:3b (~256MB pada
    # 1b) — masih muat di RAM 8GB bersama model embedding, tapi mepet. Harus
    # selaras dengan DOCUMENT_FOCUS_MAX_CHARS dan batas riwayat di agent.py.
    llm_num_ctx: int = 8192
    # paraphrase-multilingual (768 dimensi, ~560MB). Menggantikan all-minilm
    # yang hanya dilatih bahasa Inggris: pada knowledge base berbahasa
    # Indonesia, all-minilm memberi skor pertanyaan DI LUAR topik (0.487-0.599)
    # yang tumpang tindih dengan pertanyaan relevan (0.460-0.715) — tidak ada
    # ambang yang bisa memisahkannya, dan "Apa ibu kota Jepang?" (0.599) dinilai
    # lebih relevan terhadap arsip surat dinas daripada pertanyaan yang
    # jawabannya benar-benar ada di dokumen (0.498). Dengan model ini pita
    # terpisah bersih: relevan 0.433-0.717, di luar topik 0.203-0.302.
    # Dimensi 768 harus cocok dengan Vector() di models.py.
    ollama_embedding_model: str = "paraphrase-multilingual"

    # OCR: "auto" = Apple Vision di macOS (jauh lebih akurat & cepat, lihat
    # tools/ocr_tool.py), EasyOCR di tempat lain. "easyocr" memaksa EasyOCR.
    ocr_engine: str = "auto"

    # Storage
    upload_dir: str = "./storage/uploads"
    processed_dir: str = "./storage/processed"

    # CORS
    cors_origins: str = "http://localhost:5173"

    # JWT Auth
    secret_key: str = "ganti-dengan-secret-key-yang-kuat-minimal-32-karakter"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    class Config:
        # Path absolut, bukan ".env": uvicorn dijalankan dari dalam backend/
        # sehingga path relatif tidak menemukan .env di root project dan
        # seluruh nilai di bawah ini akan diam-diam memakai default.
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()

    # Path penyimpanan ikut ditambatkan ke root project supaya file tidak
    # tersebar ke folder storage/ bayangan di dalam backend/.
    for field in ("upload_dir", "processed_dir"):
        value = Path(getattr(settings, field))
        if not value.is_absolute():
            setattr(settings, field, str((PROJECT_ROOT / value).resolve()))

    return settings
