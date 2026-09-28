"""
access.py — Hak akses per dokumen knowledge base.

Setiap dokumen punya tingkat akses (kolom documents.access_level):
    umum      bisa dicari semua akun, termasuk read_only hasil pendaftaran mandiri
    internal  hanya pegawai yang disetujui admin (role user) dan admin
    rahasia   hanya admin

Sebelumnya knowledge base dipakai bersama tanpa pembedaan: surat berisi nama,
NIP, dan jabatan pegawai bisa dicari siapa pun yang mendaftar (temuan P1
laporan akhir). Tingkat akses diperiksa di SETIAP jalur baca dokumen — RAG,
pencarian kata kunci, lampiran, dokumen yang disebut namanya, deteksi
lanjutan, daftar dokumen, dan tool SQL — bukan hanya di tampilan.
"""
ACCESS_LEVELS = ("umum", "internal", "rahasia")
DEFAULT_ACCESS_LEVEL = "internal"

ROLE_LEVELS = {
    "read_only": ("umum",),
    "user": ("umum", "internal"),
    "admin": ACCESS_LEVELS,
}


def allowed_levels(role: str | None) -> list[str]:
    """Tingkat akses yang boleh dibaca role ini. Role tidak dikenal hanya
    mendapat dokumen umum (gagal tertutup, bukan terbuka)."""
    return list(ROLE_LEVELS.get(role or "", ("umum",)))


def levels_for_upload(role: str) -> list[str]:
    """Tingkat yang boleh dipilih saat mengunggah: tidak boleh lebih tinggi
    dari yang bisa dibaca pengunggahnya sendiri."""
    return allowed_levels(role)


# ── Deteksi data pribadi saat unggah ──────────────────────────────────
# Klasifikasi dari pengunggah tidak dipercaya begitu saja: dokumen yang
# ditandai "umum" tapi memuat data pribadi dinaikkan ke "internal" sebelum
# disimpan. Pola dibuat untuk format Indonesia yang umum di dokumen dinas.
import re

PERSONAL_DATA_PATTERNS = {
    "NIK": re.compile(r"\bNIK\b\s*[:.]?\s*\d{16}\b|\b\d{16}\b"),
    "NIP": re.compile(r"\bNIP\b\.?\s*[:.]?\s*\d{8}\s?\d{6}\s?\d\s?\d{3}\b|\b\d{18}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "nomor HP": re.compile(r"(?<!\d)(\+62|62|0)8\d{2}[\s-]?\d{3,4}[\s-]?\d{3,5}(?!\d)"),
    # Nama orang dengan gelar ("Drs. HENDRO MARTONO, MT", "Rahmad, S.Kom")
    # — tanda tangan dan daftar pegawai di surat dinas.
    "nama bergelar": re.compile(
        r"\b(Drs|Dra|Dr|Ir|Prof|Hj|H)\.\s+[A-Z][A-Za-z]+"
        r"|\b[A-Z][A-Za-z]+,\s*(S\.\s?[A-Z][a-z]*|M\.\s?[A-Z][A-Za-z]*|MT|MM|SE|ST)\b"
    ),
}
# Alamat email resmi instansi (kop surat) bukan data pribadi.
_OFFICIAL_EMAIL = re.compile(r"@[\w.-]*(go\.id|desa\.id)\b", re.IGNORECASE)


def personal_data_found(text: str) -> list[str]:
    """Jenis data pribadi yang terdeteksi di teks (kosong bila tidak ada)."""
    found = []
    for label, pattern in PERSONAL_DATA_PATTERNS.items():
        matches = pattern.findall(text) if label != "email" else [
            m.group(0) for m in pattern.finditer(text) if not _OFFICIAL_EMAIL.search(m.group(0))
        ]
        if matches:
            found.append(label)
    return found


def classify_for_storage(requested_level: str, text: str) -> tuple[str, list[str]]:
    """(tingkat akses final, jenis data pribadi yang memaksa kenaikan)."""
    if requested_level != "umum":
        return requested_level, []
    found = personal_data_found(text)
    return ("internal", found) if found else ("umum", [])
