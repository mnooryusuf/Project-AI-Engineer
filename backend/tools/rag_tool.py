"""
tools/rag_tool.py — RAG Search Tool
Similarity search pada pgvector menggunakan cosine distance
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from services.embedding_service import get_embedding


# Ambang minimum relevansi — TERIKAT pada model embedding (config.py) DAN
# pada CHUNK_SIZE (document_service.py). Keduanya menggeser skor, jadi angka
# ini harus diukur ulang setiap kali salah satunya berubah.
#
# Pengukuran berlaku: paraphrase-multilingual, chunk 300 karakter, 80 chunk:
#   pertanyaan relevan     0.547 - 0.832
#   pertanyaan statistik   0.382 - 0.432   <- harus ditolak agar jatuh ke SQL_QUERY
#   pertanyaan luar topik  0.179 - 0.337
# 0.49 berada di tengah celah 0.432-0.547.
#
# Pertanyaan statistik ("berapa jumlah chat hari ini") sengaja diperhitungkan
# sebagai kelompok yang HARUS ditolak: sejak _prepare_answer menjalankan RAG
# lebih dulu untuk semua pertanyaan, ambang inilah satu-satunya yang menjaga
# pertanyaan statistik tetap sampai ke SQL_QUERY. Pada ambang 0.37 hal itu
# TERBUKTI gagal — "Berapa jumlah chat hari ini?" (0.432) tertangkap RAG dan
# dijawab "146.000.000" dari dokumen daftar harga barang.
#
# Riwayat: angka 0.55 untuk all-minilm sudah tidak berlaku. Pada model itu
# pita relevan (0.460-0.715) dan luar topik (0.487-0.599) saling tumpang
# tindih — tidak ada ambang yang memisahkan sama sekali.
SIMILARITY_THRESHOLD = 0.49


async def rag_search(query: str, db: Session, top_k: int = 3) -> dict:
    """
    Cari dokumen yang relevan dengan query menggunakan cosine similarity.
    Mengembalikan context dan sumber dokumen.
    """
    query_embedding = await get_embedding(query)

    # Cosine similarity search via pgvector
    result = db.execute(
        text("""
            SELECT filename, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM documents
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """),
        {
            "embedding": str(query_embedding),
            "top_k": top_k,
        },
    )
    rows = result.fetchall()

    if not rows:
        return {
            "found": False,
            "context": "",
            "sources": [],
        }

    context_parts = []
    sources = []
    for row in rows:
        if row.similarity > SIMILARITY_THRESHOLD:
            context_parts.append(f"[Dari: {row.filename}]\n{row.content}")
            if row.filename not in sources:
                sources.append(row.filename)

    if not context_parts:
        return {"found": False, "context": "", "sources": []}

    return {
        "found": True,
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources,
    }
