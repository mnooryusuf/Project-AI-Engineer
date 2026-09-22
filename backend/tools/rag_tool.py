"""
tools/rag_tool.py — RAG Search Tool
Similarity search pada pgvector menggunakan cosine distance
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from services.embedding_service import get_embedding


# Ambang minimum relevansi.
# all-minilm dilatih untuk bahasa Inggris, sehingga teks Indonesia menempati
# pita similarity yang sempit. Hasil pengukuran pada knowledge base contoh:
# pertanyaan relevan 0.63-0.69, pertanyaan di luar topik 0.27-0.51. Ambang 0.55
# memisahkan keduanya; nilai yang lebih rendah membuat dokumen acak ikut lolos
# dan dikutip sebagai sumber.
SIMILARITY_THRESHOLD = 0.55


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
