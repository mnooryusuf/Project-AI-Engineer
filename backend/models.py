"""
models.py — SQLAlchemy ORM Models
"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(BigInteger, primary_key=True, index=True)
    # Nullable karena baris lama (sebelum kolom ini ada) tidak punya nilai.
    # Baris tanpa user_id tidak akan muncul di sidebar riwayat siapa pun —
    # itu perilaku yang diinginkan untuk data lama/uji, bukan bug.
    user_id = Column(BigInteger, nullable=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant | system | tool
    message = Column(Text, nullable=False)
    # Badge tool (rag_search/image_ocr/sql_query/dst) & sitasi jawaban asisten,
    # ditambahkan lewat migrasi ringan di main.py — baris lama tetap NULL.
    tool_used = Column(String(50), nullable=True)
    sources = Column(JSON, nullable=True)
    # Lampiran (gambar/dokumen) yang disertakan pesan user ini, kalau ada.
    attachment_type = Column(String(20), nullable=True)  # image | document
    attachment_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)
    # paraphrase-multilingual embedding dimension = 768.
    # Harus cocok dengan ollama_embedding_model di config.py — mengganti model
    # embedding berarti mengganti angka ini DAN meng-embed ulang seluruh isi
    # tabel (vektor lama tidak kompatibel, bukan sekadar beda panjang).
    embedding = Column(Vector(768))
    # "metadata" adalah nama yang dipakai Declarative API, jadi atribut
    # Python-nya diberi nama lain sambil tetap memetakan ke kolom "metadata".
    doc_metadata = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UploadJob(Base):
    """
    Status pemrosesan satu berkas yang diunggah.

    Disimpan di database, bukan di memori proses: OCR bisa berjalan beberapa
    menit, dan kalau backend di-restart di tengah jalan status yang hanya ada
    di memori akan hilang tanpa jejak — pengguna melihat "sedang diproses"
    selamanya tanpa cara mengetahui apa yang terjadi.
    """
    __tablename__ = "upload_jobs"

    id = Column(String(36), primary_key=True, index=True)  # uuid4
    user_id = Column(BigInteger, nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    # Nama rujukan untuk lampiran chat setelah selesai (kolom `filename` di
    # tabel documents). Kosong selama pemrosesan belum berhasil.
    stored_filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False)  # processing | done | warning | failed
    chunks_saved = Column(Integer, default=0)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin | user | read_only
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
