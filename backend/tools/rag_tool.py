"""
tools/rag_tool.py — RAG Search Tool
Similarity search pada pgvector menggunakan cosine distance
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from services.embedding_service import get_embedding
from services.document_service import CHUNK_OVERLAP


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


# Pemilihan konteks. Diukur pada pertanyaan "siapa nama kepala dinas kominfo
# hss" (137 chunk, 11 dokumen). Versi lama (top_k=3, tanpa aturan lain)
# menjawab "nama tidak disebutkan", padahal namanya ada di 3 dokumen:
#   - chunk yang memuat nama ("Drs. HENDRO MARTONO, MT", surat PBJ) ada di
#     peringkat #4 (0.509, di atas ambang) — terpotong top_k=3;
#   - ketiga slot diambil SATU dokumen: daftar penerima surat undangan
#     ("... Kepala Dinas Komunikasi, Informatika ...", jabatan tanpa nama)
#     paling mirip dengan kalimat pertanyaannya;
#   - jabatan dan nama sering terbelah di dua chunk (CHUNK_SIZE 300): chunk
#     nama tidak memuat kata "Kepala Dinas", jabatannya ada di chunk
#     sebelumnya.
# Jadi: kandidat lebih banyak, paling banyak MAX_PER_DOCUMENT chunk per
# dokumen, dan setiap chunk terpilih dibawa bersama chunk tetangganya.
CANDIDATES = 20
MAX_CHUNKS = 6
# Ambang dua tingkat: chunk TERBAIK tetap harus lolos SIMILARITY_THRESHOLD
# (gerbang "pertanyaan ini memang soal dokumen"), tapi setelah lolos, chunk
# pendamping cukup di atas angka ini. "siapa kepala dinas": chunk SPT yang
# memuat nama kepala dinas skornya 0.487 — tersaring ambang tunggal 0.49,
# padahal pertanyaan itu sendiri (0.537) jelas soal dokumen. Menurunkan
# ambang gerbang tidak aman: pertanyaan di luar topik sudah mencapai 0.455
# ("Buatkan pantun tentang kopi") sampai 0.566 ("Siapa presiden pertama
# Indonesia?") seiring knowledge base bertambah.
SECONDARY_THRESHOLD = 0.45
MAX_PER_DOCUMENT = 2
NEIGHBORS = 1


async def rag_search(query: str, db: Session, top_k: int = MAX_CHUNKS) -> dict:
    """
    Cari dokumen yang relevan dengan query menggunakan cosine similarity.
    Mengembalikan context dan sumber dokumen.
    """
    query_embedding = await get_embedding(query)

    rows = db.execute(
        text("""
            SELECT id, filename,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM documents
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :candidates
        """),
        {"embedding": str(query_embedding), "candidates": CANDIDATES},
    ).fetchall()

    # Urutan skor dipertahankan; tiap dokumen dibatasi supaya satu dokumen
    # yang kebetulan mirip kalimatnya tidak menutup dokumen lain.
    if not rows or rows[0].similarity <= SIMILARITY_THRESHOLD:
        return {"found": False, "context": "", "sources": []}

    picked, per_doc = [], {}
    for row in rows:
        if row.similarity <= SECONDARY_THRESHOLD or len(picked) >= top_k:
            break
        if per_doc.get(row.filename, 0) >= MAX_PER_DOCUMENT:
            continue
        per_doc[row.filename] = per_doc.get(row.filename, 0) + 1
        picked.append(row)

    # Tetangga (id +-NEIGHBORS dengan filename sama — chunk satu dokumen
    # disimpan berurutan) diambil sekaligus dalam satu query.
    wanted = {(r.filename, r.id + d) for r in picked for d in range(-NEIGHBORS, NEIGHBORS + 1)}
    chunks = db.execute(
        text("SELECT id, filename, content FROM documents WHERE id = ANY(:ids)"),
        {"ids": sorted({i for _, i in wanted})},
    ).fetchall()
    chunks = [c for c in chunks if (c.filename, c.id) in wanted]

    # Dokumen diurutkan menurut chunk terbaiknya; di dalam satu dokumen,
    # chunk diurutkan menurut posisi dan yang bersebelahan disambung
    # (overlap dibuang) supaya terbaca sebagai teks utuh.
    doc_order = list(dict.fromkeys(r.filename for r in picked))
    context_parts = []
    for filename in doc_order:
        own = sorted((c for c in chunks if c.filename == filename), key=lambda c: c.id)
        text_parts, prev_id = [], None
        for c in own:
            if prev_id is not None and c.id == prev_id + 1:
                text_parts.append(c.content[CHUNK_OVERLAP:])
            else:
                text_parts.append(("\n[...]\n" if text_parts else "") + c.content)
            prev_id = c.id
        context_parts.append(f"[Dari: {filename}]\n{''.join(text_parts)}")

    return {
        "found": True,
        "context": "\n\n---\n\n".join(context_parts),
        "sources": doc_order,
    }
