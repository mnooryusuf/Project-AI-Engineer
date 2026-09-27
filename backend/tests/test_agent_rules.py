import asyncio

import pytest

import agent
from agent import FixedAnswer, IDENTITY_ANSWER, NOT_IN_DOCUMENTS_ANSWER, _asks_internal_data, _extract_sql, _looks_not_found
from tools.sql_tool import build_stats_query, is_stats_question


# Contoh diambil dari komentar kode dan uji laporan akhir.
@pytest.mark.parametrize("question", [
    "Berapa hari cuti tahunan pegawai?",
    "Siapa kepala dinas kominfo HSS?",
    "Berapa biaya layanan hosting di Diskominfo?",
    "Jam pelayanan kantor jam berapa?",
    "Berapa anggaran kegiatan ini di dinas?",
])
def test_internal_data_questions_are_guarded(question):
    assert _asks_internal_data(question)


@pytest.mark.parametrize("question", [
    "Apa ibu kota Jepang?",
    "Buatkan pantun tentang kopi",
    "Bagaimana cara install Zoom?",
    "Apa syarat membuat SIM?",
    "Berapa biaya kuliah di UI?",
    "Apa itu SOP?",
    "Apa arti pagu anggaran?",
    "apa wisata yang ada di kabupaten HSS",
])
def test_general_questions_are_not_guarded(question):
    assert not _asks_internal_data(question)


@pytest.mark.parametrize("question", ["Berapa jumlah chat hari ini?", "Ada berapa dokumen yang tersimpan?"])
def test_stats_questions_are_recognised(question):
    assert is_stats_question(question)
    assert build_stats_query(question) is not None


@pytest.mark.parametrize("question", ["Bagaimana cara meminjam ruang Media Center?", "Apa itu SPBE?"])
def test_document_questions_are_not_stats(question):
    assert not is_stats_question(question)


def test_extract_sql_ignores_surrounding_prose():
    reply = "Untuk menjawab ini, gunakan query berikut:\n```sql\nSELECT COUNT(*) FROM documents;\n```\nSemoga membantu."
    assert _extract_sql(reply) == "SELECT COUNT(*) FROM documents"


def test_not_found_only_for_short_answers():
    assert _looks_not_found("Tidak ada informasi tentang anggaran kegiatan ini dalam dokumen.")
    assert not _looks_not_found("Ringkasan: " + "poin penting. " * 40 + "Tidak ada informasi tanggal.")


def _prepare(question, monkeypatch, rag_found=False):
    """Jalankan _prepare_answer tanpa DB/Ollama: RAG dan router LLM dipalsukan."""
    async def fake_rag(query, db):
        return {"found": rag_found, "context": "isi dokumen" if rag_found else "", "sources": ["dok.txt"] if rag_found else []}

    async def fake_router(q):
        return "DIRECT_ANSWER"

    monkeypatch.setattr(agent, "rag_search", fake_rag)
    monkeypatch.setattr(agent, "_determine_tool", fake_router)
    return asyncio.run(agent._prepare_answer(question, None))


def test_internal_question_without_documents_gets_fixed_refusal(monkeypatch):
    tool, sources, prompt = _prepare("Berapa hari cuti tahunan pegawai?", monkeypatch)
    assert tool == "direct_answer" and sources == []
    assert isinstance(prompt, FixedAnswer) and prompt == NOT_IN_DOCUMENTS_ANSWER


def test_internal_question_with_documents_goes_to_model(monkeypatch):
    tool, sources, prompt = _prepare("Siapa kepala dinas kominfo HSS?", monkeypatch, rag_found=True)
    assert tool == "rag_search" and sources == [{"filename": "dok.txt"}]
    assert not isinstance(prompt, FixedAnswer) and "isi dokumen" in prompt


@pytest.mark.parametrize("question", ["Siapa kamu?", "halo kamu siapa", "siapa namamu"])
def test_identity_question_names_nanang(question, monkeypatch):
    _, _, prompt = _prepare(question, monkeypatch)
    assert isinstance(prompt, FixedAnswer) and prompt == IDENTITY_ANSWER
    assert "Nanang" in IDENTITY_ANSWER


def test_general_question_uses_model(monkeypatch):
    _, _, prompt = _prepare("Apa ibu kota Jepang?", monkeypatch)
    assert not isinstance(prompt, FixedAnswer) and "Apa ibu kota Jepang?" in prompt
