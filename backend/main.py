"""
main.py — FastAPI Entry Point
Nanang — Asisten AI Diskominfo SP TIK Kabupaten Hulu Sungai Selatan
"""
import asyncio
import json
import os
import re
import uuid
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from jose import JWTError, jwt
import bcrypt

from config import get_settings
from database import get_db, engine, SessionLocal
from models import Base, ChatHistory, Document, UploadJob, User
from schemas import (
    ChatRequest, UploadResponse, UploadJobStatus, HealthResponse,
    UserCreate, UserResponse, Token, TokenData,
    ChatHistoryItem, ChatSessionItem, DocumentListItem,
)
from agent import run_agent_stream
from services.document_service import process_and_store_document, store_text_as_document
from services.llm_service import check_ollama_status
from services.file_validation import verify_file_signature
from tools.ocr_tool import extract_text_from_image

# ── Init ────────────────────────────────────────────────
settings = get_settings()
Base.metadata.create_all(bind=engine)

# Migrasi ringan: kolom-kolom ini ditambahkan ke ChatHistory belakangan
# (badge tool/sitasi/lampiran di riwayat chat) — create_all() di atas hanya
# membuat tabel yang BELUM ada, tidak meng-ALTER tabel chat_history yang
# sudah ada dari deployment sebelumnya. Idempotent, aman dijalankan tiap start.
with engine.begin() as conn:
    conn.execute(text("""
        ALTER TABLE chat_history
            ADD COLUMN IF NOT EXISTS tool_used VARCHAR(50),
            ADD COLUMN IF NOT EXISTS sources JSON,
            ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(20),
            ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)
    """))

# Pekerjaan yang masih "processing" saat proses ini mulai berarti backend mati
# di tengah pemrosesan sebelumnya — BackgroundTasks hidup di dalam proses, jadi
# pekerjaannya ikut hilang dan tidak akan pernah selesai sendiri. Tanpa ini,
# frontend memantau status yang tidak akan pernah berubah selamanya. Ditandai
# gagal supaya pengguna tahu harus mengunggah ulang.
with engine.begin() as conn:
    conn.execute(text("""
        UPDATE upload_jobs
        SET status = 'failed',
            message = 'Pemrosesan terhenti karena server dimulai ulang. Silakan unggah ulang berkasnya.',
            finished_at = NOW()
        WHERE status = 'processing'
    """))

# Nama file gambar disimpan di disk dengan prefix "{uuid_hex}_" (lihat
# /upload) — untuk ditampilkan di riwayat chat, prefix ini dibuang supaya
# yang terlihat nama file aslinya, bukan nama internal storage.
_UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{32}_")


def _display_filename(stored_name: str) -> str:
    return _UUID_PREFIX_RE.sub("", stored_name, count=1)

app = FastAPI(
    title="Nanang API",
    description="Asisten AI lokal Diskominfo SP TIK HSS — RAG dokumen, OCR gambar, dan query database.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth Setup ───────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".webp"}
# Ekstensi yang teksnya diambil lewat extract_text_from_file(); sisanya
# (gambar) diambil lewat OCR. Keduanya sama-sama berakhir di knowledge base —
# pembedaan di sini hanya soal CARA teksnya diperoleh, bukan apakah diindeks.
DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".docx", ".xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# bcrypt hanya memproses 72 byte pertama; password yang lebih panjang dipotong
# agar tidak melempar error.
BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_password_bytes(plain), hashed.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*roles: str):
    """
    Dependency factory untuk otorisasi berbasis role.

    Sebelumnya kolom `User.role` (admin/user/read_only) ada di skema tapi
    tidak pernah dibaca di endpoint manapun — semua user terautentikasi
    punya akses identik, tanpa pembedaan admin vs read_only sama sekali.
    Dipakai di /upload: role "read_only" boleh chat & baca riwayat, tapi
    tidak boleh menambah dokumen ke knowledge base.
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' tidak diizinkan mengakses endpoint ini.",
            )
        return current_user
    return _check


# ── Auth Endpoints ───────────────────────────────────────

@app.post("/auth/register", response_model=UserResponse, tags=["Auth"])
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Registrasi user baru."""
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username sudah digunakan.")
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login dan dapatkan JWT token."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Username atau password salah.")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


# ── Chat Endpoints ───────────────────────────────────────

@app.post("/chat", tags=["Chat"])
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Kirim pertanyaan ke Agent — jawaban di-stream token demi token sebagai
    NDJSON (satu objek JSON per baris), bukan satu blob JSON di akhir.
    Format tiap baris:
      {"type": "meta", "tool_used": "...", "sources": [...]}   <- sekali, di awal
      {"type": "token", "text": "..."}                          <- berkali-kali
      {"type": "done"}                                          <- sekali, di akhir
      {"type": "error", "detail": "..."}                        <- kalau gagal

    Kenapa buka SessionLocal terpisah di dalam generator, bukan pakai `db`
    dari Depends(get_db): siklus hidup dependency FastAPI terikat ke fungsi
    endpoint ini SELESAI dieksekusi, tapi dengan StreamingResponse, isi
    body (generator di bawah) baru benar-benar jalan SETELAH fungsi ini
    return — `db` bisa saja sudah ditutup oleh Starlette sebelum generator
    sempat memakainya. Sesi terpisah menghindari ambiguitas ini sepenuhnya,
    tidak bergantung pada detail siklus hidup dependency FastAPI versi
    tertentu.
    """
    # Tangkap sebagai int biasa SEKARANG, selagi current_user masih terikat
    # ke sesi Depends(get_db) yang hidup. Kalau current_user.id diakses nanti
    # di dalam generator (setelah StreamingResponse dikembalikan), SQLAlchemy
    # mencoba me-refresh objek User itu dari sesi aslinya yang sudah
    # tertutup -> DetachedInstanceError (terbukti muncul saat diuji; stream
    # terputus tanpa event "done" di baris terakhir).
    user_id = current_user.id

    # Simpan pesan user — ini masih aman pakai `db` dari Depends(get_db)
    # karena terjadi sebelum StreamingResponse dikembalikan (sinkron, bukan
    # bagian dari body generator).
    attachment_type = "image" if request.image_filename else ("document" if request.document_filename else None)
    db.add(ChatHistory(
        user_id=user_id,
        session_id=request.session_id,
        role="user",
        message=request.message,
        attachment_type=attachment_type,
        attachment_filename=(
            _display_filename(request.image_filename or request.document_filename)
            if attachment_type else None
        ),
    ))
    db.commit()

    # Jika pertanyaan merujuk pada gambar yang diunggah sebelumnya, resolve
    # nama file ke path di dalam upload_dir. Nama file datang dari client,
    # jadi ditahan ke basename dan diverifikasi tetap berada di dalam
    # upload_dir sebelum dipakai — mencegah path traversal (mis. "../../etc/passwd").
    image_path = None
    if request.image_filename:
        upload_dir = Path(settings.upload_dir).resolve()
        candidate = (upload_dir / Path(request.image_filename).name).resolve()
        if candidate.is_relative_to(upload_dir) and candidate.is_file():
            image_path = str(candidate)
        else:
            raise HTTPException(status_code=404, detail="Gambar tidak ditemukan.")

    # Sama seperti image_filename, tapi cukup dicocokkan ke kolom filename di
    # tabel documents (bukan path filesystem) — tidak ada risiko path
    # traversal di sini karena tidak pernah dipakai untuk buka file di disk.
    document_filename = None
    if request.document_filename:
        exists = db.query(Document.id).filter(Document.filename == request.document_filename).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan di knowledge base.")
        document_filename = request.document_filename

    async def event_stream():
        stream_db = SessionLocal()
        full_answer = ""
        meta_tool_used = None
        meta_sources = None
        try:
            async for event in run_agent_stream(
                question=request.message, db=stream_db, image_path=image_path,
                document_filename=document_filename,
            ):
                if event["type"] == "meta":
                    meta_tool_used = event.get("tool_used")
                    meta_sources = event.get("sources")
                elif event["type"] == "token":
                    full_answer += event["text"]
                yield json.dumps(event) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
        finally:
            # Simpan apa pun yang sempat terkirim ke user — termasuk kalau
            # error terjadi di tengah jalan, supaya riwayat tetap
            # mencerminkan yang benar-benar dilihat user, bukan hilang begitu
            # saja. tool_used/sources ikut disimpan supaya badge & sitasi
            # tetap tampil konsisten saat riwayat ini dimuat ulang nanti
            # (pindah sesi lalu balik lagi, atau reload halaman).
            if full_answer:
                stream_db.add(ChatHistory(
                    user_id=user_id,
                    session_id=request.session_id,
                    role="assistant",
                    message=full_answer,
                    tool_used=meta_tool_used,
                    sources=meta_sources,
                ))
                stream_db.commit()
            stream_db.close()
            yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/chat/history", response_model=list[ChatHistoryItem], tags=["Chat"])
def get_chat_history(
    session_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ambil riwayat chat berdasarkan session_id.

    Difilter juga dengan user_id — sebelumnya endpoint ini hanya mengecek
    user sudah login (tidak peduli siapa), jadi siapa pun yang tahu/menebak
    session_id user lain bisa membaca isi percakapannya. session_id milik
    user lain sekarang mengembalikan daftar kosong, bukan error, supaya
    tidak membocorkan informasi soal sesi mana yang benar-benar ada.
    """
    return (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_id == session_id,
            ChatHistory.user_id == current_user.id,
        )
        .order_by(ChatHistory.created_at.asc())
        .limit(limit)
        .all()
    )


@app.get("/chat/sessions", response_model=list[ChatSessionItem], tags=["Chat"])
def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Daftar sesi percakapan milik user ini, untuk sidebar riwayat — judul
    diambil dari pesan pertama tiap sesi, diurutkan dari yang paling baru
    aktif.
    """
    result = db.execute(
        text("""
            SELECT session_id, message AS title, last_activity
            FROM (
                SELECT session_id, message, created_at,
                       ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY created_at ASC) AS rn,
                       MAX(created_at) OVER (PARTITION BY session_id) AS last_activity
                FROM chat_history
                WHERE user_id = :user_id
            ) t
            WHERE rn = 1
            ORDER BY last_activity DESC
            LIMIT 100
        """),
        {"user_id": current_user.id},
    )
    return [
        {"session_id": row.session_id, "title": row.title, "last_activity": row.last_activity}
        for row in result.fetchall()
    ]


@app.delete("/chat/sessions/{session_id}", tags=["Chat"])
def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Hapus satu percakapan (semua pesan di session_id ini) milik user yang
    sedang login. Difilter dengan user_id — sama seperti /chat/history,
    supaya user tidak bisa menghapus percakapan user lain walau tahu/
    menebak session_id-nya. Ini data personal (bukan knowledge base
    bersama seperti /documents), jadi tidak ada pembatasan role — siapa
    pun yang login boleh hapus percakapannya sendiri.
    """
    deleted = (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id, ChatHistory.user_id == current_user.id)
        .delete()
    )
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan.")
    return {"session_id": session_id, "messages_deleted": deleted}


# ── Upload Endpoints ─────────────────────────────────────

# Hanya satu berkas diproses pada satu waktu. OCR memuat model EasyOCR dan
# merender halaman PDF ke bitmap beresolusi penuh — dua unggahan bersamaan di
# mesin 8GB (yang sudah menjalankan Ollama, Postgres, dan Vite) berisiko
# kehabisan memori. Antre lebih baik daripada keduanya gagal.
_upload_semaphore = asyncio.Semaphore(1)


async def _process_upload_job(job_id: str, file_path: str, original_filename: str, ext: str) -> None:
    """
    Kerjakan ekstraksi + embedding satu unggahan di latar belakang.

    Membuka sesi database sendiri: sesi dari Depends(get_db) milik permintaan
    /upload sudah ditutup Starlette saat fungsi ini berjalan (pola yang sama
    dipakai generator streaming di /chat).
    """
    async with _upload_semaphore:
        db = SessionLocal()
        try:
            if ext in DOCUMENT_EXTENSIONS:
                chunks = await process_and_store_document(file_path, original_filename, db)
                gagal_pesan = (
                    f"Tidak ada teks yang bisa dibaca dari {original_filename}. "
                    "Dokumen TIDAK masuk knowledge base."
                )
                sukses_pesan = f"Dokumen diproses: {chunks} chunk disimpan ke knowledge base."
            else:
                hasil = await extract_text_from_image(file_path)
                teks = hasil["text"] if hasil.get("success") else ""
                chunks = await store_text_as_document(
                    teks, original_filename, db, {"source": "ocr"}
                ) if teks.strip() else 0
                gagal_pesan = (
                    f"Tidak ada teks yang terbaca pada {original_filename}. "
                    "Gambar TIDAK masuk knowledge base — pastikan tulisannya jelas dan tidak terpotong."
                )
                sukses_pesan = f"Gambar dibaca lewat OCR: {chunks} chunk disimpan ke knowledge base."

            # Nol chunk TIDAK boleh dilaporkan sebagai sukses — pengguna akan
            # mengira dokumennya masuk knowledge base padahal kosong, lalu
            # pertanyaan berikutnya dijawab mengarang. stored_filename
            # dibiarkan kosong supaya tidak ada lampiran yang menunjuk ke
            # dokumen tanpa isi.
            job_status = "done" if chunks > 0 else "warning"
            _finish_job(
                db, job_id, job_status,
                sukses_pesan if chunks > 0 else gagal_pesan,
                chunks,
                original_filename if chunks > 0 else None,
            )
        except Exception as e:
            # Kegagalan tak terduga (berkas rusak, Ollama mati di tengah jalan)
            # harus tetap sampai ke pengguna — tanpa ini pekerjaan menggantung
            # di status "processing" selamanya.
            _finish_job(db, job_id, "failed", f"Gagal memproses {original_filename}: {e}", 0, None)
        finally:
            db.close()


def _finish_job(db: Session, job_id: str, status: str, message: str,
                chunks: int, stored_filename: str | None) -> None:
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if job is None:
        return
    job.status = status
    job.message = message
    job.chunks_saved = chunks
    job.stored_filename = stored_filename
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


@app.post("/upload", response_model=UploadResponse, tags=["Upload"])
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    # read_only sengaja tidak termasuk: menambah dokumen mengubah knowledge
    # base bersama, bukan operasi "baca saja".
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    """Upload dokumen (PDF/TXT/DOCX/XLSX) atau gambar untuk OCR."""
    # `file.filename` datang mentah dari client (header Content-Disposition
    # multipart) — bisa diisi string apa pun oleh client non-browser, bukan
    # cuma nama file polos. TERBUKTI saat diuji: filename seperti
    # "foo/../../../../tmp/evil.txt" membuat os.path.join(upload_dir, ...)
    # menghasilkan path yang keluar dari upload_dir sepenuhnya saat dibuka —
    # arbitrary file write oleh user terautentikasi mana pun (bukan cuma
    # admin). `.name` mengambil HANYA komponen nama file terakhir, membuang
    # semua "/" dan "..".
    original_filename = Path(file.filename).name
    if not original_filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid.")

    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Format tidak didukung: {ext}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Ukuran file melebihi 10MB.")

    # Validasi isi file (magic bytes), bukan cuma ekstensi nama file — nama
    # dan Content-Type dari client sama-sama bisa dipalsukan; ini memastikan
    # byte awal file benar-benar cocok dengan tipe yang diklaim.
    if not verify_file_signature(content, ext):
        raise HTTPException(
            status_code=400,
            detail=f"Isi file tidak sesuai dengan format {ext} yang diklaim.",
        )

    # Simpan file
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{original_filename}"
    file_path = os.path.join(settings.upload_dir, safe_name)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Pemrosesan (ekstraksi/OCR/embedding) dipindah ke latar belakang. OCR
    # berjalan ~33 detik per halaman, jadi kalau dikerjakan di dalam permintaan
    # ini pengguna menatap spinner sampai beberapa menit dan koneksi berisiko
    # putus di tengah jalan. Di sini berkas hanya divalidasi dan disimpan,
    # lalu balasan langsung dikirim; kemajuannya dipantau lewat
    # GET /upload/jobs/{job_id}.
    job_id = str(uuid.uuid4())
    db.add(UploadJob(
        id=job_id,
        user_id=current_user.id,
        filename=original_filename,
        status="processing",
        message="Berkas diterima, sedang diproses.",
    ))
    db.commit()

    background_tasks.add_task(_process_upload_job, job_id, file_path, original_filename, ext)

    return UploadResponse(
        job_id=job_id,
        filename=original_filename,
        status="processing",
        message="Berkas diterima, sedang diproses.",
    )


@app.get("/upload/jobs/{job_id}", response_model=UploadJobStatus, tags=["Upload"])
def get_upload_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Status pemrosesan satu unggahan. Difilter dengan user_id supaya pengguna
    tidak bisa mengintip status unggahan orang lain dengan menebak job_id.
    """
    job = (
        db.query(UploadJob)
        .filter(UploadJob.id == job_id, UploadJob.user_id == current_user.id)
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Proses unggahan tidak ditemukan.")
    return UploadJobStatus(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        message=job.message or "",
        chunks_saved=job.chunks_saved or 0,
        stored_filename=job.stored_filename,
    )


# ── Documents (Knowledge Base) ───────────────────────────

@app.get("/documents", response_model=list[DocumentListItem], tags=["Documents"])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Daftar dokumen di knowledge base — dikelompokkan per filename (satu
    dokumen tersimpan sebagai banyak baris/chunk di tabel documents).

    Knowledge base bersifat SHARED, bukan per-user — sama seperti RAG_SEARCH
    yang mencari ke semua dokumen tanpa memandang siapa yang mengunggahnya,
    daftar ini juga menampilkan semua dokumen untuk siapa pun yang login.
    """
    result = db.execute(
        text("""
            SELECT filename, count(*) AS chunk_count, min(created_at) AS uploaded_at
            FROM documents
            GROUP BY filename
            ORDER BY uploaded_at DESC
        """)
    )
    return [
        {"filename": row.filename, "chunk_count": row.chunk_count, "uploaded_at": row.uploaded_at}
        for row in result.fetchall()
    ]


@app.delete("/documents/{filename}", tags=["Documents"])
def delete_document(
    filename: str,
    # read_only sengaja tidak termasuk — sama seperti /upload, menghapus
    # dokumen mengubah knowledge base bersama, bukan operasi "baca saja".
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    """
    Hapus semua chunk milik satu dokumen dari knowledge base (jadi tidak
    ikut muncul lagi di hasil RAG_SEARCH).

    CATATAN: ini hanya menghapus baris di tabel documents, BUKAN file fisik
    di storage/uploads/ — nama file yang tersimpan di disk punya prefix uuid
    (lihat safe_name di /upload) yang tidak direkam di tabel documents,
    jadi tidak ada cara aman merekonstruksi path aslinya dari sini tanpa
    perubahan skema lebih lanjut. File fisik jadi sekadar arsip tak
    terpakai — tidak memengaruhi RAG karena itu murni baca dari tabel ini.
    """
    deleted = db.query(Document).filter(Document.filename == filename).delete()
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan di knowledge base.")
    return {"filename": filename, "chunks_deleted": deleted}


# ── Health Check ─────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(db: Session = Depends(get_db)):
    """Cek status semua service."""
    # Cek database
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"

    ollama_status = await check_ollama_status()

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        ollama=ollama_status,
        database=db_status,
    )
