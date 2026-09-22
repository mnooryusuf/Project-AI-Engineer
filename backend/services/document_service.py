"""
services/document_service.py — Memproses dokumen untuk RAG pipeline
Mendukung: PDF, TXT
"""
import os
import aiofiles
from pathlib import Path
from typing import List
from sqlalchemy.orm import Session
from models import Document
from services.embedding_service import get_embedding
from config import get_settings

settings = get_settings()

# Ukuran chunk (kecilkan untuk hemat RAM)
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Membagi teks menjadi chunk-chunk kecil dengan overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


async def extract_text_from_file(file_path: str) -> str:
    """Ekstrak teks dari file PDF atau TXT."""
    ext = Path(file_path).suffix.lower()

    if ext == ".txt":
        async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return await f.read()

    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    else:
        raise ValueError(f"Format file tidak didukung: {ext}")


async def process_and_store_document(
    file_path: str,
    filename: str,
    db: Session
) -> int:
    """
    Pipeline lengkap:
    1. Ekstrak teks
    2. Chunk
    3. Embedding
    4. Simpan ke PostgreSQL
    Mengembalikan jumlah chunk yang disimpan.
    """
    text = await extract_text_from_file(file_path)
    chunks = chunk_text(text)
    saved = 0

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        embedding = await get_embedding(chunk)
        doc = Document(
            filename=filename,
            content=chunk,
            embedding=embedding,
            doc_metadata={"chunk_index": i, "total_chunks": len(chunks)},
        )
        db.add(doc)
        saved += 1

    db.commit()
    return saved
