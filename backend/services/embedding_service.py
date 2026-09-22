"""
services/embedding_service.py — Layanan embedding via Ollama
Model: all-minilm (384 dimensi, ~45MB, sangat ringan untuk RAM 8GB)
"""
import httpx
from config import get_settings

settings = get_settings()


async def get_embedding(text: str) -> list[float]:
    """
    Menghasilkan vector embedding dari teks menggunakan Ollama.
    Model: all-minilm → 384 dimensi.
    """
    # Timeout longgar: pemanggilan pertama harus memuat model ke RAM, yang di
    # mesin 8GB bisa memakan lebih dari 30 detik.
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={
                "model": settings.ollama_embedding_model,
                "prompt": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]
