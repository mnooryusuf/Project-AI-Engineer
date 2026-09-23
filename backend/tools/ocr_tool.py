"""
tools/ocr_tool.py — OCR Tool: Apple Vision (macOS) dengan fallback EasyOCR
Lazy loading: model hanya dimuat saat pertama kali dipanggil (hemat RAM)
"""
import asyncio
import sys

from config import get_settings

settings = get_settings()

# Lazy import — EasyOCR hanya dimuat saat dibutuhkan
_ocr_reader = None

# Ambang keyakinan EasyOCR. Tanpa penyaring, teks miring/kecil (mis. layar
# HP di dalam poster) terbaca sebagai puluhan potongan sampah ("Kxx Qisia",
# "pemefirkzh teren") yang ikut masuk konteks LLM dan embedding. Diukur pada
# poster Ombudsman: semua potongan sampah <= 0.33, teks yang benar >= 0.40.
EASYOCR_MIN_CONFIDENCE = 0.35


def _use_apple_vision() -> bool:
    """Apple Vision dipakai kalau engine "auto"/"vision" dan tersedia.

    Diukur pada mesin target (Mac 8GB) — Apple Vision vs EasyOCR:
      poster Ombudsman 1080x1350: 3,3 dtk vs 70 dtk; teks di layar HP dalam
        poster terbaca utuh, URL persis "https://bit.ly/kepercayaan_masyarakat"
        (EasyOCR: "https:llbit ly/..." + puluhan potongan sampah)
      foto produk 1254x1254: 0,3 dtk; "RP100 PRO", "360° Coverage"
        (EasyOCR: "RPIOO pRo", "3600 3600 Coverage")
    Hanya ada di macOS — di server Linux otomatis kembali ke EasyOCR.
    """
    if settings.ocr_engine == "easyocr" or sys.platform != "darwin":
        return False
    try:
        import ocrmac  # noqa: F401
        return True
    except ImportError:
        return False


def uses_fast_ocr() -> bool:
    """Apple Vision aktif — dipakai document_service untuk memutuskan apakah
    gambar di dalam halaman PDF yang sudah berteks ikut dibaca (~1 dtk/hal),
    yang terlalu lambat kalau memakai EasyOCR (~33 dtk/hal)."""
    return _use_apple_vision()


def _vision_lines(image) -> list[tuple[float, float, float, float, str]]:
    """OCR satu gambar PIL lewat Apple Vision -> [(x0, y0, x1, y1, teks)]
    dalam piksel, asal kiri ATAS (Vision memakai koordinat ternormalisasi
    dengan asal kiri BAWAH)."""
    from ocrmac import ocrmac
    results = ocrmac.OCR(
        image, language_preference=["id-ID", "en-US"], recognition_level="accurate"
    ).recognize()
    w, h = image.size
    return [
        (bx * w, (1 - by - bh) * h, (bx + bw) * w, (1 - by) * h, text)
        for text, _conf, (bx, by, bw, bh) in results
    ]


def _overlaps(a, b) -> bool:
    """True kalau irisan dua kotak menutupi >= 30% kotak yang lebih kecil."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return False
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return smaller > 0 and ix * iy >= 0.3 * smaller


# Pembagian ubin untuk gambar. Vision melewatkan teks yang kecil RELATIF
# terhadap seluruh gambar: pada poster Ombudsman, tulisan pojok kanan atas
# ("AWASI TEGUR LAPORKAN", "Pengawasan Berdampak ...") tidak terbaca sama
# sekali di gambar utuh, tapi terbaca lengkap begitu area itu dipotong.
# Jadi gambar dibaca utuh DAN per kuadran (tumpang tindih supaya teks di
# garis potong tetap utuh di salah satu ubin), lalu digabung.
#
# Penggabungan berdasarkan POSISI, bukan isi teks: ubin sering membaca baris
# yang sama dengan salah eja berbeda ("OPINI" vs "OPNI"/"OPEL"), jadi
# pencocokan teks meloloskan duplikat. Baris dari gambar utuh selalu
# diutamakan; baris ubin hanya ditambahkan di area yang kosong.
TILE_GRID = 2
TILE_OVERLAP = 0.15


def _read_apple_vision(image, tiled: bool = True) -> list[str]:
    """OCR lewat Apple Vision. `image` boleh path berkas atau PIL.Image."""
    from PIL import Image

    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.convert("RGB")
    w, h = image.size

    kept = _vision_lines(image)
    if tiled:
        step_x, step_y = w / TILE_GRID, h / TILE_GRID
        pad_x, pad_y = step_x * TILE_OVERLAP, step_y * TILE_OVERLAP
        for row in range(TILE_GRID):
            for col in range(TILE_GRID):
                box = (
                    int(max(0, col * step_x - pad_x)), int(max(0, row * step_y - pad_y)),
                    int(min(w, (col + 1) * step_x + pad_x)), int(min(h, (row + 1) * step_y + pad_y)),
                )
                for x0, y0, x1, y1, text in _vision_lines(image.crop(box)):
                    line = (x0 + box[0], y0 + box[1], x1 + box[0], y1 + box[1], text)
                    if not any(_overlaps(line, k) for k in kept):
                        kept.append(line)

    # Urutan baca: atas ke bawah, lalu kiri ke kanan untuk baris yang
    # sejajar (toleransi 1% tinggi gambar).
    band = max(1.0, h * 0.01)
    kept.sort(key=lambda k: (round(k[1] / band), k[0]))
    return [k[4] for k in kept]


def _read_easyocr(reader, image) -> list[str]:
    """OCR lewat EasyOCR per baris, membuang hasil berkeyakinan rendah.

    paragraph=True tidak dipakai lagi: mode itu menggabungkan baris sebelum
    skor keyakinan bisa dilihat, sehingga sampah tidak bisa disaring.
    """
    return [
        text for _box, text, conf in reader.readtext(image, detail=1, paragraph=False)
        if conf >= EASYOCR_MIN_CONFIDENCE
    ]


def _get_ocr_reader():
    """Singleton OCR reader — dimuat sekali, digunakan berkali-kali."""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        # Dukung Bahasa Indonesia + Inggris
        _ocr_reader = easyocr.Reader(["id", "en"], gpu=False, verbose=False)
    return _ocr_reader


# Resolusi render halaman PDF sebelum di-OCR. Diukur langsung pada mesin
# target (8GB, CPU) dengan surat dinas 1 halaman A4:
#   200 dpi -> 56.1 detik, 927 karakter terbaca
#   150 dpi -> 32.7 detik, 924 karakter terbaca
#   110 dpi -> 18.6 detik, 921 karakter terbaca
# Kualitasnya praktis sama (selisih < 1%), jadi resolusi tinggi hanya
# membuang waktu. 150 dipilih sebagai kompromi: setengah waktu 200 dpi
# dengan margin aman untuk dokumen yang tulisannya lebih kecil.
PDF_OCR_DPI = 150


async def extract_text_from_pdf_pages(pdf_path: str, page_indices: list[int]) -> dict[int, str]:
    """
    OCR halaman PDF tertentu — halaman dirender jadi gambar lebih dulu karena
    EasyOCR hanya menerima gambar, bukan PDF.

    Dipakai sebagai fallback untuk PDF hasil pindaian, yang isinya gambar
    sehingga pypdf tidak menemukan teks sama sekali (lihat document_service).
    Mengembalikan peta {nomor_halaman: teks}.
    """
    loop = asyncio.get_event_loop()
    use_vision = _use_apple_vision()
    reader = None if use_vision else await loop.run_in_executor(None, _get_ocr_reader)

    def _render_and_read() -> dict[int, str]:
        import numpy as np
        import pypdfium2 as pdfium

        hasil: dict[int, str] = {}
        pdf = pdfium.PdfDocument(pdf_path)
        try:
            for i in page_indices:
                if i >= len(pdf):
                    continue
                image = pdf[i].render(scale=PDF_OCR_DPI / 72).to_pil()
                baris = _read_apple_vision(image, tiled=False) if use_vision else _read_easyocr(reader, np.array(image))
                hasil[i] = "\n".join(baris)
        finally:
            pdf.close()
        return hasil

    # Render + OCR keduanya sinkron dan berat; jalankan di thread pool supaya
    # event loop tidak terblokir selama puluhan detik per halaman.
    return await loop.run_in_executor(None, _render_and_read)


async def extract_text_from_image(image_path: str) -> dict:
    """
    Ekstrak teks dari gambar — Apple Vision kalau tersedia, selain itu
    EasyOCR (lazy loading: model dimuat saat pertama kali dipanggil).
    """
    try:
        # Jalankan OCR di thread pool agar tidak block event loop
        loop = asyncio.get_event_loop()
        if _use_apple_vision():
            results = await loop.run_in_executor(None, _read_apple_vision, image_path)
        else:
            reader = await loop.run_in_executor(None, _get_ocr_reader)
            results = await loop.run_in_executor(None, _read_easyocr, reader, image_path)

        extracted_text = "\n".join(results)

        if not extracted_text.strip():
            return {
                "success": False,
                "text": "",
                "message": "Tidak ada teks yang terdeteksi pada gambar.",
            }

        return {
            "success": True,
            "text": extracted_text,
            "message": f"Berhasil membaca {len(results)} baris teks.",
        }

    except Exception as e:
        return {
            "success": False,
            "text": "",
            "message": f"Error OCR: {str(e)}",
        }
