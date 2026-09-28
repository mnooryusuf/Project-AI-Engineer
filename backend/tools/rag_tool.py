"""
tools/rag_tool.py — RAG Search Tool
Semua pengambilan isi knowledge base untuk agent: similarity search umum
(rag_search), isi satu dokumen tertentu (document_focus_context), dan
pencocokan dokumen yang disebut atau sedang dibahas.
"""
import re
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from access import allowed_levels
from models import Document

# Default setiap fungsi di sini: hanya dokumen umum. Pemanggil yang lupa
# mengoper tingkat akses gagal tertutup, bukan membuka dokumen internal.
_PUBLIC = tuple(allowed_levels(None))
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

# Pelengkap kata kunci (hybrid ringan). Blok tanda tangan "Kepala Dinas,
# Drs. HENDRO MARTONO, MT ... NIP" selalu berada di chunk yang sama dengan
# kalimat penutup surat, sehingga skor embedding-nya terseret ke bawah:
# untuk "Siapa nama kepala dinas kominfo hss?" chunk SPT dan PBJ yang memuat
# nama hanya 0.449 dan 0.335 (di bawah SECONDARY_THRESHOLD), konteks tidak
# memuat nama sama sekali, dan model mengarang "kepala dinas adalah saya
# sendiri, Nanang" (uji e2e laporan v3). Kata kunci menemukan chunk itu
# langsung. Hanya dipakai SETELAH gerbang SIMILARITY_THRESHOLD lolos, jadi
# penolakan pertanyaan di luar topik tidak berubah.
LEXICAL_EXTRA = 2
LEXICAL_MIN_TERMS = 2
_STOPWORDS = {
    "siapa", "apa", "apakah", "nama", "namanya", "yang", "dan", "atau", "dari", "untuk", "dengan",
    "pada", "dalam", "ini", "itu", "berapa", "bagaimana", "cara", "adalah", "saja", "bisa", "tolong",
    "sebutkan", "jelaskan", "kapan", "dimana", "mana", "ada", "tentang", "oleh", "sebagai", "kah",
}


# Pertanyaan "siapa ..." jawabannya nama orang, jadi chunk yang memuat
# penanda nama pejabat (NIP, gelar) didahulukan di antara kandidat kata kunci
# yang sama kuat — daftar jabatan penerima undangan tidak memuat nama.
WHO_QUESTION = re.compile(r"^\s*siapa\b", re.IGNORECASE)
PERSON_SIGNAL = re.compile(
    r"\bNIP\b|\b(Drs|Dra|Dr|Ir|Hj|H|Prof)\.\s|,\s*(S\.\w+|M\.\w+|MT|MM|SE|ST)\b"
)


def _query_terms(query: str) -> list[str]:
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3 and t not in _STOPWORDS]
    return list(dict.fromkeys(terms))


def _lexical_candidates(query: str, db: Session, levels=_PUBLIC, limit: int = 60) -> list:
    """Chunk yang memuat minimal LEXICAL_MIN_TERMS kata penting dari
    pertanyaan. Diurutkan menurut jumlah PASANGAN kata pertanyaan yang muncul
    berurutan ("kepala dinas"), baru ts_rank_cd: tanpa itu daftar penerima
    undangan yang menyebut "Kepala ... Kab. HSS" berkali-kali selalu menang
    atas blok tanda tangan yang memuat nama pejabatnya. Chunk berisi
    placeholder template («isi nama dan NIP») dilewati karena tidak memuat
    fakta apa pun."""
    terms = _query_terms(query)
    if len(terms) < LEXICAL_MIN_TERMS:
        return []
    pairs = [f"{a} {b}" for a, b in zip(terms, terms[1:])]
    wants_person = bool(WHO_QUESTION.search(query))
    rows = db.execute(
        text("""
            SELECT id, filename, content,
                   ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', :q)) AS rank
            FROM documents
            WHERE to_tsvector('simple', content) @@ to_tsquery('simple', :q)
              AND access_level = ANY(:levels)
            ORDER BY rank DESC
            LIMIT :limit
        """),
        {"q": " | ".join(terms), "limit": limit, "levels": list(levels)},
    ).fetchall()
    scored = []
    for r in rows:
        if "«" in r.content:
            continue
        flat = " ".join(re.findall(r"[a-z0-9]+", r.content.lower()))
        if sum(t in flat for t in terms) < LEXICAL_MIN_TERMS:
            continue
        person = wants_person and bool(PERSON_SIGNAL.search(r.content))
        scored.append((sum(f" {p} " in f" {flat} " for p in pairs), person, r.rank, r))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [x[-1] for x in scored]


async def rag_search(query: str, db: Session, top_k: int = MAX_CHUNKS, levels=_PUBLIC) -> dict:
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
            WHERE access_level = ANY(:levels)
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :candidates
        """),
        {"embedding": str(query_embedding), "candidates": CANDIDATES, "levels": list(levels)},
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

    picked_ids = {r.id for r in picked}
    extra = 0
    for row in _lexical_candidates(query, db, levels):
        if extra >= LEXICAL_EXTRA:
            break
        if row.id in picked_ids or per_doc.get(row.filename, 0) >= MAX_PER_DOCUMENT:
            continue
        per_doc[row.filename] = per_doc.get(row.filename, 0) + 1
        picked.append(row)
        picked_ids.add(row.id)
        extra += 1

    # Tetangga (id +-NEIGHBORS dengan filename sama — chunk satu dokumen
    # disimpan berurutan) diambil sekaligus dalam satu query.
    wanted = {(r.filename, r.id + d) for r in picked for d in range(-NEIGHBORS, NEIGHBORS + 1)}
    chunks = db.execute(
        text("SELECT id, filename, content FROM documents WHERE id = ANY(:ids) AND access_level = ANY(:levels)"),
        {"ids": sorted({i for _, i in wanted}), "levels": list(levels)},
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


# Anggaran karakter isi dokumen untuk DOCUMENT_FOCUS (lihat
# document_focus_context). Dulu dibatasi 6 chunk pertama — dengan CHUNK_SIZE
# 300 itu cuma ~1.800 karakter, jadi ringkasan/analisis dokumen hampir selalu
# hanya membahas halaman awal. 12.000 karakter (~3.500-4.000 token teks
# Indonesia) muat di num_ctx=8192 (config.py) bersama system prompt, riwayat
# percakapan (HISTORY_* di agent.py) dan ruang untuk jawaban. Dokumen yang lebih panjang
# dipilih bagian-bagian paling relevan terhadap pertanyaan, bukan dipotong
# begitu saja di awal.
DOCUMENT_FOCUS_MAX_CHARS = 12000


# Kelonggaran untuk active_document_wins. Glosarium istilah menarik skor
# tinggi untuk hampir semua pertanyaan umum: "siapa saja yang ditugaskan?"
# -> glosarium 0.522 vs SPT (dokumen aktif, jawabannya memang di sana) 0.506.
ACTIVE_DOCUMENT_MARGIN = 0.05


async def active_document_wins(db: Session, active_document: str, question: str, levels=_PUBLIC) -> bool:
    """True kalau chunk terbaik dokumen aktif lebih mirip dengan pertanyaan
    daripada chunk terbaik dokumen LAIN mana pun. Membandingkan, bukan
    memakai ambang: skor mutlak lanjutan dan pindah topik saling tumpang
    tindih, tapi pada pindah topik asli dokumen lain selalu menang jauh
    (Media Center +0.50, SPBE +0.33)."""
    own, other = await active_document_scores(db, active_document, question, levels)
    return own is not None and (other is None or own >= other - ACTIVE_DOCUMENT_MARGIN)


def document_visible(db: Session, filename: str, levels=_PUBLIC) -> bool:
    """Apakah dokumen ini ada di knowledge base DAN boleh dibaca dengan
    tingkat akses ini."""
    return db.execute(
        text("SELECT 1 FROM documents WHERE filename = :f AND access_level = ANY(:levels) LIMIT 1"),
        {"f": filename, "levels": list(levels)},
    ).first() is not None


def document_contains_any(db: Session, filename: str, words: list[str], levels=_PUBLIC) -> bool:
    """Apakah isi dokumen `filename` memuat salah satu kata ini (tanpa
    membedakan huruf besar/kecil)."""
    if not words:
        return False
    clauses = " OR ".join(f"content ILIKE :w{i}" for i in range(len(words)))
    params = {"f": filename, "levels": list(levels), **{f"w{i}": f"%{w}%" for i, w in enumerate(words)}}
    return db.execute(
        text(f"SELECT 1 FROM documents WHERE filename = :f AND access_level = ANY(:levels) AND ({clauses}) LIMIT 1"),
        params
    ).first() is not None


async def active_document_scores(db: Session, active_document: str, question: str, levels=_PUBLIC) -> tuple:
    """(skor chunk terbaik dokumen aktif, skor chunk terbaik dokumen lain)."""
    embedding = str(await get_embedding(question))
    row = db.execute(
        text("""
            SELECT
                MAX(1 - (embedding <=> CAST(:e AS vector))) FILTER (WHERE filename = :f) AS own,
                MAX(1 - (embedding <=> CAST(:e AS vector))) FILTER (WHERE filename <> :f) AS other
            FROM documents
            WHERE access_level = ANY(:levels)
        """),
        {"e": embedding, "f": active_document, "levels": list(levels)},
    ).first()
    return row.own, row.other


async def _select_relevant_chunks(db: Session, document_filename: str, question: str, levels=_PUBLIC) -> str:
    """Untuk dokumen yang melebihi anggaran: chunk pertama selalu ikut
    (biasanya judul/kop/identitas dokumen), sisanya dipilih berdasarkan
    kemiripan dengan pertanyaan DI DALAM dokumen ini saja, lalu diurutkan
    kembali sesuai posisi aslinya supaya alurnya tetap terbaca."""
    query_embedding = await get_embedding(question)
    ranked = db.execute(
        text("""
            SELECT id, content
            FROM documents
            WHERE filename = :filename AND access_level = ANY(:levels)
            ORDER BY embedding <=> CAST(:embedding AS vector)
        """),
        {"filename": document_filename, "embedding": str(query_embedding), "levels": list(levels)},
    ).fetchall()
    first = min(ranked, key=lambda r: r.id)

    chosen = {first.id: first.content}
    budget = DOCUMENT_FOCUS_MAX_CHARS - len(first.content)
    for row in ranked:
        if row.id in chosen:
            continue
        if len(row.content) > budget:
            break
        chosen[row.id] = row.content
        budget -= len(row.content)

    # Chunk yang bersebelahan disambung (overlap dibuang); celah antar-bagian
    # ditandai "[...]" supaya model tahu ada bagian dokumen yang dilewati.
    ids = sorted(chosen)
    out = [chosen[ids[0]]]
    for prev_id, cur_id in zip(ids, ids[1:]):
        if cur_id == prev_id + 1:
            out.append(chosen[cur_id][CHUNK_OVERLAP:])
        else:
            out.append("\n[...]\n" + chosen[cur_id])
    return "".join(out)


async def document_focus_context(db: Session, document_filename: str, question: str, levels=_PUBLIC) -> str:
    """Ambil isi dokumen untuk DOCUMENT_FOCUS.

    Dokumen yang muat DOCUMENT_FOCUS_MAX_CHARS dikirim UTUH (overlap
    antar-chunk dibuang supaya teks tidak berulang). Yang lebih panjang
    diserahkan ke _select_relevant_chunks.
    """
    rows = (
        db.query(Document.content)
        .filter(Document.filename == document_filename, Document.access_level.in_(list(levels)))
        .order_by(Document.id)
        .all()
    )
    if not rows:
        return ""

    total = sum(len(r.content) for r in rows) - CHUNK_OVERLAP * (len(rows) - 1)
    if total > DOCUMENT_FOCUS_MAX_CHARS:
        return await _select_relevant_chunks(db, document_filename, question, levels)
    return rows[0].content + "".join(r.content[CHUNK_OVERLAP:] for r in rows[1:])


def _normalize_name(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())


def find_mentioned_document(question: str, db: Session, levels=_PUBLIC) -> str | None:
    """Dokumen di knowledge base yang namanya disebut di pertanyaan.

    Tanpa ini, menyebut nama dokumen di percakapan baru tidak ada gunanya:
    "SPT SINAU JOGJA AI ENGINEER.docx ambil nama kepala dinas dari dokumen
    ini" tetap dijawab dari surat undangan, karena pencarian umum menaruh
    tiga chunk surat itu di atas SPT (diuji). Cocok kalau nama lengkap tanpa
    ekstensi, atau tiga kata pertamanya, muncul utuh di pertanyaan. Nama
    pendek (< 5 huruf, mis. "6.jpeg") hanya cocok lewat nama file lengkap
    beserta ekstensinya, supaya angka biasa di pertanyaan tidak ikut cocok.
    Kalau beberapa cocok, yang paling panjang (paling spesifik) menang.
    """
    q = f" {_normalize_name(question)} "
    best, best_len = None, 0
    for (filename,) in db.query(Document.filename).filter(Document.access_level.in_(list(levels))).distinct():
        stem = _normalize_name(Path(filename).stem)
        candidates = [_normalize_name(filename)]
        if len(stem) >= 5:
            candidates.append(stem)
            words = stem.split()
            if len(words) > 3:
                candidates.append(" ".join(words[:3]))
        for cand in candidates:
            if cand and f" {cand} " in q and len(cand) > best_len:
                best, best_len = filename, len(cand)
    return best
