"""
cleanup_uploads.py — Hapus file di storage/uploads yang tidak lagi dipakai.

Sebelum DELETE /documents ikut menghapus file aslinya, file tetap tertinggal
setiap kali dokumen dihapus, diunggah ulang, atau gagal diproses. Skrip ini
membersihkan sisa itu sekali jalan:
  - file milik dokumen yang sudah tidak ada di tabel documents dihapus;
  - untuk dokumen yang masih ada, hanya file versi TERBARU yang disimpan —
    sama dengan file yang dipakai reindex_documents.py sebagai sumber.
File yang namanya tidak berformat "{uuid}_{nama}" tidak disentuh.

Jalankan dari direktori backend/:
    .venv/bin/python3 cleanup_uploads.py           # tampilkan rencana saja
    .venv/bin/python3 cleanup_uploads.py --apply   # hapus
"""
import sys
from pathlib import Path

from sqlalchemy import text

from config import get_settings
from database import SessionLocal
from services.document_service import UUID_PREFIX


def plan() -> tuple[list[Path], list[Path], list[Path]]:
    """-> (dipertahankan, dihapus, tidak dikenali)."""
    db = SessionLocal()
    try:
        indexed = {r[0] for r in db.execute(text("SELECT DISTINCT filename FROM documents")).fetchall()}
    finally:
        db.close()

    by_name: dict[str, list[Path]] = {}
    unknown = []
    for f in Path(get_settings().upload_dir).iterdir():
        if not f.is_file():
            continue
        if not UUID_PREFIX.match(f.name):
            unknown.append(f)
            continue
        by_name.setdefault(UUID_PREFIX.sub("", f.name, count=1), []).append(f)

    keep, remove = [], []
    for name, files in by_name.items():
        files.sort(key=lambda f: f.stat().st_mtime)
        if name in indexed:
            keep.append(files[-1])
            remove.extend(files[:-1])
        else:
            remove.extend(files)
    return keep, remove, unknown


def main(apply: bool) -> int:
    keep, remove, unknown = plan()
    for f in sorted(remove, key=lambda f: f.name):
        print(f"hapus    {f.name}")
    for f in sorted(unknown, key=lambda f: f.name):
        print(f"lewati   {f.name}  (nama tidak berformat uuid_nama)")
    size = sum(f.stat().st_size for f in remove)
    print(f"\n{len(keep)} file dipertahankan, {len(remove)} file dihapus ({size / 1024 / 1024:.1f} MB), "
          f"{len(unknown)} dilewati.")
    if not apply:
        print("Belum ada yang dihapus. Jalankan dengan --apply untuk menghapus.")
        return 0
    for f in remove:
        f.unlink(missing_ok=True)
    print("Selesai.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv[1:]))
