"""
services/llm_service.py — Layanan LLM via Ollama
Model: llama3.2:1b (ringan ~700MB, untuk RAM 8GB)
"""
import json

import httpx
from config import get_settings

settings = get_settings()


async def ask_llm(prompt: str, system_prompt: str = "") -> str:
    """
    Kirim prompt ke Ollama dan dapatkan jawaban.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": messages,
                "stream": False,
                "options": {
                    # Batasi konteks untuk hemat RAM
                    "num_ctx": 2048,
                    "temperature": 0.1,
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def stream_llm(prompt: str, system_prompt: str = ""):
    """
    Versi streaming dari ask_llm() — yield potongan teks jawaban segera
    setelah Ollama menghasilkannya, alih-alih menunggu jawaban lengkap.

    HANYA dipakai untuk jawaban akhir yang ditampilkan ke user (di
    agent.py). Panggilan LLM internal (router pemilih tool, generate SQL)
    tetap pakai ask_llm() non-streaming — user tidak perlu melihat token
    demi token untuk keputusan internal yang tidak pernah ditampilkan
    langsung.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_ctx": 2048,
                    "temperature": 0.1,
                },
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
                if data.get("done"):
                    break


async def check_ollama_status() -> str:
    """Cek apakah Ollama berjalan."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            if response.status_code == 200:
                return "ok"
    except Exception:
        pass
    return "unavailable"
