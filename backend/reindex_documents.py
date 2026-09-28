"""
reindex_documents.py — Bangun ulang seluruh knowledge base dari file asli.

Dipakai saat model embedding diganti. Vektor dari model berbeda TIDAK bisa
dibandingkan satu sama lain, jadi mengganti model berarti seluruh isi tabel
`documents` harus di-embed ulang — bukan sekadar menambah dimensi kolom.

Sumber kebenarannya adalah file di storage/uploads/, bukan isi tabel: teks
di tabel adalah hasil ekstraksi yang ikut berubah kalau CHUNK_SIZE berubah.

Juga dipakai saat mesin OCR diganti (lihat tools/ocr_tool.py): gambar di
knowledge base menyimpan teks hasil OCR saat diunggah, jadi perlu dibaca
ulang supaya ikut membaik. --images membatasi ke gambar saja, tanpa
menyentuh dokumen lain.

Jalankan dari direktori backend/:
    .venv/bin/python3 reindex_documents.py                    # tampilkan rencana saja
    .venv/bin/python3 reindex_documents.py --apply            # jalankan
    .venv/bin/python3 reindex_documents.py --images --apply   # OCR ulang gambar saja
    .venv/bin/python3 reindex_documents.py --pdf --apply      # ekstrak ulang PDF saja

--pdf dipakai saat cara ekstraksi teks PDF berubah (lihat
services/document_service._pdf_text_layer); dokumen lain tidak disentuh.
"""
import asyncio
import os
import re
import sys

from sqlalchemy import text as sqltext

from config import get_settings
from database import SessionLocal, engine
from services.document_service import process_and_store_document, store_text_as_document
from services.embedding_service import get_embedding
from tools.ocr_tool import extract_text_from_image

settings = get_settings()

# Nama file di disk berformat "{uuid_hex}_{nama asli}" (lihat /upload di main.py).
UUID_PREFIX = re.compile(r"^[0-9a-f]{32}_")

# Sama dengan DOCUMENT_EXTENSIONS / IMAGE_EXTENSIONS di main.py. Gambar juga
# masuk knowledge base (teks hasil OCR saat upload), jadi ikut dibangun ulang
# — sebelumnya gambar dianggap "file asli hilang" dan membatalkan reindex.
DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".docx", ".xlsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def is_image(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS


# Tingkat akses & pengunggah tiap dokumen, dibaca SEBELUM baris dihapus
# supaya membangun ulang tidak mengembalikan semua dokumen ke "internal".
_ACCESS: dict[str, tuple[str, int | None]] = {}


async def rebuild_one(name: str, path: str, db) -> int:
    level, owner = _ACCESS.get(name, ("internal", None))
    if is_image(name):
        hasil = await extract_text_from_image(path)
        teks = hasil["text"] if hasil.get("success") else ""
        return await store_text_as_document(
            teks, name, db, {"source": "ocr"}, access_level=level, uploaded_by=owner
        ) if teks.strip() else 0
    return await process_and_store_document(path, name, db, access_level=level, uploaded_by=owner)


def source_files_by_original_name() -> dict[str, str]:
    """Peta nama asli -> path file terbaru di upload_dir."""
    result: dict[str, str] = {}
    for name in os.listdir(settings.upload_dir):
        path = os.path.join(settings.upload_dir, name)
        if not os.path.isfile(path):
            continue
        original = UUID_PREFIX.sub("", name, count=1)
        if os.path.splitext(original)[1].lower() not in DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS:
            continue
        if original not in result or os.path.getmtime(path) > os.path.getmtime(result[original]):
            result[original] = path
    return result


async def main(apply: bool, images_only: bool, pdf_only: bool = False) -> int:
    db = SessionLocal()
    indexed = [r[0] for r in db.execute(
        sqltext("SELECT DISTINCT filename FROM documents ORDER BY 1")
    ).fetchall()]
    if images_only:
        indexed = [f for f in indexed if is_image(f)]
    if pdf_only:
        indexed = [f for f in indexed if f.lower().endswith(".pdf")]
    available = source_files_by_original_name()
    _ACCESS.update({
        r.filename: (r.access_level, r.uploaded_by)
        for r in db.execute(sqltext(
            "SELECT DISTINCT ON (filename) filename, access_level, uploaded_by FROM documents ORDER BY filename, id"
        )).fetchall()
    })

    rebuildable = [f for f in indexed if f in available]
    missing = [f for f in indexed if f not in available]

    print(f"Model embedding : {settings.ollama_embedding_model}")
    print(f"Terindeks saat ini: {len(indexed)} dokumen")
    print(f"Bisa dibangun ulang: {len(rebuildable)}")
    for f in rebuildable:
        print(f"   + {f}")
    if missing:
        print(f"File asli HILANG (akan lenyap dari knowledge base): {len(missing)}")
        for f in missing:
            print(f"   ! {f}")

    if not apply:
        print("\nIni baru rencana. Tambahkan --apply untuk menjalankan.")
        db.close()
        return 0

    if missing:
        print("\nDIBATALKAN: ada dokumen yang file aslinya tidak ditemukan.")
        print("Hapus dulu dokumen itu lewat panel Dokumen kalau memang direlakan,")
        print("atau kembalikan filenya ke storage/uploads/.")
        db.close()
        return 1

    if pdf_only:
        # Versi baru disimpan dulu, baru chunk lama dihapus — kalau ekstraksi
        # gagal di tengah jalan, dokumen lama tetap utuh.
        total = 0
        for name in rebuildable:
            old_max = db.execute(sqltext("SELECT MAX(id) FROM documents WHERE filename = :f"), {"f": name}).scalar()
            chunks = await rebuild_one(name, available[name], db)
            if chunks > 0:
                db.execute(sqltext("DELETE FROM documents WHERE filename = :f AND id <= :m"), {"f": name, "m": old_max})
                db.commit()
            total += chunks
            print(f"   {name}: {chunks} chunk" + ("" if chunks else "  (GAGAL — versi lama dipertahankan)"))
        db.close()
        print(f"\nSelesai. {len(rebuildable)} PDF, {total} chunk.")
        return 0

    if images_only:
        # Dimensi embedding tidak berubah, jadi cukup ganti baris milik
        # gambar-gambar ini saja.
        total = 0
        for name in rebuildable:
            db.execute(sqltext("DELETE FROM documents WHERE filename = :f"), {"f": name})
            db.commit()
            chunks = await rebuild_one(name, available[name], db)
            total += chunks
            print(f"   {name}: {chunks} chunk")
        db.close()
        print(f"\nSelesai. {len(rebuildable)} gambar, {total} chunk.")
        return 0

    print("\nMengosongkan tabel documents...")
    db.execute(sqltext("DELETE FROM documents"))
    db.commit()

    # Dimensi ditanyakan ke model yang sedang aktif, bukan ditulis tetap di
    # sini — supaya skrip ini tetap benar untuk model apa pun berikutnya.
    # Kolom hanya bisa diubah tipenya saat tabel sudah kosong.
    dim = len(await get_embedding("uji dimensi"))
    print(f"Menyesuaikan dimensi kolom embedding -> vector({dim})...")
    with engine.begin() as conn:
        conn.execute(sqltext(f"ALTER TABLE documents ALTER COLUMN embedding TYPE vector({dim})"))

    total = 0
    for name in rebuildable:
        chunks = await rebuild_one(name, available[name], db)
        total += chunks
        print(f"   {name}: {chunks} chunk")

    db.close()
    print(f"\nSelesai. {len(rebuildable)} dokumen, {total} chunk, dimensi {dim}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--apply" in sys.argv, "--images" in sys.argv, "--pdf" in sys.argv)))
