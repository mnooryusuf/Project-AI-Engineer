"""
tools/ocr_tool.py — OCR Tool menggunakan EasyOCR
Lazy loading: model hanya dimuat saat pertama kali dipanggil (hemat RAM)
"""
import asyncio
from functools import lru_cache
from typing import Optional

# Lazy import — EasyOCR hanya dimuat saat dibutuhkan
_ocr_reader = None


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
    reader = await loop.run_in_executor(None, _get_ocr_reader)

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
                baris = reader.readtext(np.array(image), detail=0, paragraph=True)
                hasil[i] = "\n".join(baris)
        finally:
            pdf.close()
        return hasil

    # Render + OCR keduanya sinkron dan berat; jalankan di thread pool supaya
    # event loop tidak terblokir selama puluhan detik per halaman.
    return await loop.run_in_executor(None, _render_and_read)


async def extract_text_from_image(image_path: str) -> dict:
    """
    Ekstrak teks dari gambar menggunakan EasyOCR.
    Lazy loading: model dimuat saat pertama kali dipanggil.
    """
    try:
        # Jalankan OCR di thread pool agar tidak block event loop
        loop = asyncio.get_event_loop()
        reader = await loop.run_in_executor(None, _get_ocr_reader)

        results = await loop.run_in_executor(
            None,
            lambda: reader.readtext(image_path, detail=0, paragraph=True),
        )

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
