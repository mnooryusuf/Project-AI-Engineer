"""
services/file_validation.py — Validasi konten file di level server.

Spesifikasi asli project meminta validasi File Extension, MIME Type, dan
File Signature untuk upload. Sebelumnya hanya ekstensi nama file yang
dicek — file apa pun (termasuk executable yang diberi nama ulang) bisa
lolos selama namanya diakhiri ".pdf"/".png"/dst. Modul ini memverifikasi
byte awal (magic number) file benar-benar cocok dengan tipe yang diklaim
oleh ekstensinya, independen dari nama file atau header Content-Type yang
dikirim client (keduanya bisa dipalsukan).
"""

# Magic bytes untuk tiap ekstensi yang didukung.
# .docx/.xlsx (format OOXML) sebenarnya adalah arsip ZIP — magic number-nya
# sama persis dengan ZIP biasa ("PK\x03\x04"), jadi pengecekan ini hanya
# memverifikasi "ini benar-benar arsip ZIP", bukan spesifik docx vs xlsx.
# Itu cukup untuk tujuan validasi ini (menolak file yang jelas BUKAN ZIP
# tapi diberi ekstensi .docx/.xlsx) — pembeda docx/xlsx yang sebenarnya
# baru diketahui saat python-docx/openpyxl membuka struktur internalnya.
_SIGNATURES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
}


def verify_file_signature(content: bytes, ext: str) -> bool:
    """
    True jika byte awal `content` cocok dengan magic number yang diharapkan
    untuk ekstensi `ext`.

    ".txt" dan ".webp" tidak punya magic number sesederhana itu, jadi
    ditangani lewat aturan khusus:
    - .webp: RIFF container, "WEBP" muncul di byte offset 8-12.
    - .txt: tidak punya signature baku sama sekali — divalidasi lewat
      heuristik "isinya benar-benar teks" (bisa didekode UTF-8, tidak
      mengandung byte null yang jadi ciri khas file biner).
    """
    if ext == ".txt":
        return _looks_like_text(content)

    if ext == ".webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"

    signatures = _SIGNATURES.get(ext)
    if not signatures:
        return False
    return any(content.startswith(sig) for sig in signatures)


def _looks_like_text(content: bytes, sample_size: int = 8192) -> bool:
    sample = content[:sample_size]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
