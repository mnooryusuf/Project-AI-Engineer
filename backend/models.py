"""
models.py — SQLAlchemy ORM Models
"""
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, JSON
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)
    # all-minilm embedding dimension = 384
    embedding = Column(Vector(384))
    # "metadata" adalah nama yang dipakai Declarative API, jadi atribut
    # Python-nya diberi nama lain sambil tetap memetakan ke kolom "metadata".
    doc_metadata = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin | user | read_only
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
