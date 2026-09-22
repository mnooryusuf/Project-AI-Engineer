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
