"""
services/gemini_service.py — Model kedua: Gemini Flash (Google AI Studio)

Antarmukanya sama dengan services/llm_service.py (ask/stream + system prompt
+ riwayat) supaya agent.py bisa memilih salah satu tanpa cabang khusus.

PERHATIAN: berbeda dengan Ollama, semua yang dikirim ke fungsi di sini
keluar dari server dinas ke Google — termasuk kutipan dokumen yang ada di
prompt. Karena itu Gemini hanya dipakai kalau pengguna memilihnya sendiri
di UI, dan default aplikasi tetap model lokal.
"""
import asyncio
import json

import httpx
from config import get_settings

settings = get_settings()

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Google sesekali membalas 503 "This model is currently experiencing high
# demand" (teramati beberapa kali saat pengujian pada gemini-flash-latest,
# selang beberapa detik sudah normal lagi) atau 429 saat kuota per menit
# habis. Keduanya dicoba ulang dengan jeda; kalau tetap gagal, dicoba dengan
# model cadangan (config.gemini_fallback_model) sebelum menyerah.
_RETRY_STATUS = {429, 500, 503}
_RETRY_DELAYS = [1.0, 3.0]

# Batas tunggu per percobaan. Streaming sempat menggantung tanpa respons
# sampai batas lama 120 detik habis (sekali, saat pengujian; percobaan
# berikutnya normal dalam 3-5 detik). Timeout diperlakukan seperti 503:
# dicoba ulang lalu pindah ke model cadangan, bukan membuat pengguna
# menunggu dua menit.
_TIMEOUT = httpx.Timeout(45.0, connect=10.0)


def _models() -> list[str]:
    models = [settings.gemini_model]
    if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
        models.append(settings.gemini_fallback_model)
    return models


def _error_message(status: int, body: bytes) -> str:
    try:
        message = json.loads(body)["error"]["message"]
    except Exception:
        message = body[:200].decode(errors="ignore")
    return f"Gemini menolak permintaan ({status}): {message}"


def gemini_available() -> bool:
    return bool(settings.gemini_api_key)


def _payload(prompt: str, system_prompt: str, history: list[dict] | None) -> dict:
    # Gemini memakai role "model" untuk giliran asisten, bukan "assistant".
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in (history or [])
    ]
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    payload = {"contents": contents, "generationConfig": {"temperature": 0.2}}
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    return payload


def _text_of(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    # Bagian "thought" (ringkasan penalaran) tidak ditampilkan ke pengguna.
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


async def ask_gemini(prompt: str, system_prompt: str = "", history: list[dict] | None = None) -> str:
    payload = _payload(prompt, system_prompt, history)
    last_error = ""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for model in _models():
            for delay in _RETRY_DELAYS + [None]:
                try:
                    response = await client.post(
                        f"{_BASE_URL}/{model}:generateContent",
                        headers={"x-goog-api-key": settings.gemini_api_key},
                        json=payload,
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_error = f"Gemini tidak merespons ({type(e).__name__})."
                    if delay is not None:
                        await asyncio.sleep(delay)
                    continue
                if response.status_code < 400:
                    return _text_of(response.json())
                last_error = _error_message(response.status_code, response.content)
                if response.status_code not in _RETRY_STATUS:
                    raise RuntimeError(last_error)
                if delay is not None:
                    await asyncio.sleep(delay)
    raise RuntimeError(last_error)


async def stream_gemini(prompt: str, system_prompt: str = "", history: list[dict] | None = None):
    """Versi streaming (Server-Sent Events) — yield potongan teks jawaban.

    Coba ulang hanya dilakukan SEBELUM token pertama terkirim: setelah itu
    pengguna sudah melihat sebagian jawaban, dan mengulang dari awal akan
    menggandakan teks di layar."""
    payload = _payload(prompt, system_prompt, history)
    last_error = ""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for model in _models():
            for delay in _RETRY_DELAYS + [None]:
                sent_any = False
                try:
                    async with client.stream(
                        "POST",
                        f"{_BASE_URL}/{model}:streamGenerateContent",
                        params={"alt": "sse"},
                        headers={"x-goog-api-key": settings.gemini_api_key},
                        json=payload,
                    ) as response:
                        if response.status_code < 400:
                            async for line in response.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                text = _text_of(json.loads(line[5:]))
                                if text:
                                    sent_any = True
                                    yield text
                            return
                        last_error = _error_message(response.status_code, await response.aread())
                        if response.status_code not in _RETRY_STATUS:
                            raise RuntimeError(last_error)
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    if sent_any:
                        raise RuntimeError(f"Koneksi ke Gemini terputus di tengah jawaban ({type(e).__name__}).")
                    last_error = f"Gemini tidak merespons ({type(e).__name__})."
                if delay is not None:
                    await asyncio.sleep(delay)
    raise RuntimeError(last_error)
