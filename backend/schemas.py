"""
schemas.py — Pydantic Schemas untuk request/response validation
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ──────────────────────────────────────────
# Auth
# ──────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None


# ──────────────────────────────────────────
# Chat
# ──────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    # Nama file (bukan path lengkap) dari gambar yang sebelumnya diunggah lewat
    # /upload, jika pertanyaan ini merujuk pada gambar tersebut.
    image_filename: Optional[str] = None
    # Sama seperti image_filename, tapi untuk dokumen PDF/TXT — kalau diisi,
    # jawaban langsung dibangun dari isi dokumen ini (dicari by filename di
    # tabel documents), BUKAN lewat similarity search umum. Dipakai saat user
    # baru saja upload dokumen dan langsung bertanya, mirip pola lampiran
    # file di ChatGPT/Gemini.
    document_filename: Optional[str] = None

class SourceInfo(BaseModel):
    filename: str

class ChatResponse(BaseModel):
    answer: str
    tool_used: Optional[str] = None
    sources: Optional[List[SourceInfo]] = []

class ChatHistoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    message: str
    created_at: datetime
    tool_used: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    attachment_type: Optional[str] = None
    attachment_filename: Optional[str] = None

    class Config:
        from_attributes = True

class ChatSessionItem(BaseModel):
    session_id: str
    # Pesan pertama user di sesi ini, dipakai sebagai judul di sidebar —
    # tabel chat_history tidak menyimpan judul terpisah.
    title: str
    last_activity: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# Documents
# ──────────────────────────────────────────

class DocumentListItem(BaseModel):
    filename: str
    chunk_count: int
    uploaded_at: datetime

class UploadResponse(BaseModel):
    filename: str
    status: str
    message: str
    # Nama file tersimpan (bukan path lengkap) — kirim balik lewat
    # ChatRequest.image_filename untuk menanyakan isi gambar ini.
    stored_filename: Optional[str] = None


# ──────────────────────────────────────────
# Health
# ──────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    ollama: str
    database: str
