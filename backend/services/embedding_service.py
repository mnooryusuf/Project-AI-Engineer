"""
services/embedding_service.py — Layanan embedding via Ollama
Model: paraphrase-multilingual (768 dimensi, ~560MB, multilingual termasuk
Bahasa Indonesia). Lihat catatan pemilihan model di config.py.
"""
import httpx
from config import get_settings

settings = get_settings()

# Batas percobaan pemotongan sebelum menyerah (0.8^6 ≈ 26% panjang asli).
_MAX_SHRINK_ATTEMPTS = 6
_MIN_CHARS = 40


async def get_embedding(text: str) -> list[float]:
    """
    Menghasilkan vector embedding dari teks menggunakan Ollama.

    Input yang melewati batas token model ditolak Ollama dengan HTTP 500
    (bukan dipotong diam-diam), dan itu menggagalkan SELURUH upload dokumen.
    Terjadi nyata pada chunk dari PDF hasil scan: ekstraksi pypdf menyisipkan
    spasi di antara hampir tiap huruf, sehingga 300-500 karakter bisa menjadi
    jauh lebih banyak token daripada teks normal dengan panjang sama. Di sini
    teks dipendekkan bertahap sampai diterima — lebih baik meng-embed sebagian
    chunk daripada kehilangan dokumennya sama sekali.
    """
    # Timeout longgar: pemanggilan pertama harus memuat model ke RAM, yang di
    # mesin 8GB bisa memakan lebih dari 30 detik.
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload_text = text
        for _ in range(_MAX_SHRINK_ATTEMPTS):
            response = await client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={
                    "model": settings.ollama_embedding_model,
                    "prompt": payload_text,
                },
            )
            if response.status_code != 500 or len(payload_text) <= _MIN_CHARS:
                response.raise_for_status()
                return response.json()["embedding"]
            payload_text = payload_text[: int(len(payload_text) * 0.8)]

        response.raise_for_status()
        return response.json()["embedding"]
