# 🤖 Agentic RAG — Local AI System

AI Assistant lokal berbasis **Agentic RAG** dengan kemampuan membaca dokumen, gambar, dan database. Berjalan 100% offline menggunakan Ollama.

## 🛠️ Tech Stack

| Layer | Teknologi |
|---|---|
| Frontend | ViteJS + React + TailwindCSS |
| Backend | FastAPI + Python 3.12 |
| Agent | Orkestrasi sendiri di `agent.py` (panggil Ollama via `httpx`) |
| LLM | Ollama `llama3.2:3b` |
| Embedding | Ollama `paraphrase-multilingual` (768 dimensi) |
| OCR | EasyOCR |
| Database | PostgreSQL + pgvector |

## 🚀 Cara Menjalankan

### Prasyarat
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (untuk PostgreSQL)
- [Ollama](https://ollama.com) sudah terinstall dan berjalan
- Python 3.12 (via pyenv)
- Node.js 18+

### 1. Setup Pertama Kali

```bash
# Clone / masuk ke folder project
cd Project-AI-Engineer

# Salin .env
cp .env.example .env

# Jalankan PostgreSQL via Docker
docker compose up -d

# Pull model Ollama (jika belum)
ollama pull llama3.2:3b
ollama pull paraphrase-multilingual

# Setup backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..

# Setup frontend
cd frontend
npm install
cd ..
```

### Ganti password bawaan

`.env.example`, `docker-compose.yml`, dan `init.sql` memakai password contoh.
Setelah database pertama kali dibuat, ganti keduanya lalu samakan `.env`
(`POSTGRES_PASSWORD`, `DATABASE_URL`, `DATABASE_URL_READONLY`):

```bash
docker exec -i agentic-rag-db psql -U postgres -d agentic_rag <<'SQL'
ALTER ROLE postgres WITH PASSWORD '<password-baru>';
ALTER ROLE agentic_rag_readonly WITH PASSWORD '<password-baru-lain>';
SQL
```

Ganti juga `SECRET_KEY` (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`).
Di luar `APP_ENV=development` backend menolak start kalau salah satunya masih nilai contoh.

### Akun admin pertama

Pendaftaran lewat aplikasi selalu menghasilkan akun `read_only` (bisa
bertanya, belum bisa mengunggah). Setelah backend pernah dijalankan sekali
(tabel sudah dibuat), buat admin dan setujui akun lain dari terminal:

```bash
cd backend
.venv/bin/python3 manage_users.py create-admin <username> <email>   # password ditanya
.venv/bin/python3 manage_users.py set-role <username> user          # izinkan unggah
.venv/bin/python3 manage_users.py list
```

| Role | Bertanya | Unggah dokumen | Hapus dokumen |
|---|---|---|---|
| `read_only` | ✅ | — | — |
| `user` | ✅ | ✅ | — |
| `admin` | ✅ | ✅ | ✅ (chunk + file asli) |

### Hak akses per dokumen

Setiap dokumen punya tingkat akses (`backend/access.py`), ditegakkan di semua
jalur baca — RAG, kata kunci, lampiran, dokumen yang disebut namanya, deteksi
lanjutan, daftar dokumen, dan tool SQL:

| Tingkat | Bisa dicari oleh | Contoh |
|---|---|---|
| `umum` | semua akun, termasuk `read_only` | profil, katalog layanan, SOP, FAQ, glosarium |
| `internal` | `user` dan `admin` (bawaan unggahan) | surat, SPT, berita acara berisi nama/NIP |
| `rahasia` | `admin` | dokumen sensitif |

Setiap unggahan lewat UI membuka dialog pemilihan tingkat akses (bawaan
Internal; pilihan dibatasi sesuai role). Dokumen yang diminta **Umum** tapi
memuat data pribadi — NIK, NIP, nama bergelar, email pribadi, nomor HP —
otomatis disimpan sebagai **Internal** dan pengunggah diberi tahu
(`access.classify_for_storage`). Admin mengubah tingkat akses di panel Dokumen
(atau `PATCH /documents/{filename}`). Unggah ulang tanpa `access_level`
mempertahankan tingkat lama.
Jawaban dengan Gemini hanya memakai dokumen `umum` (`docs/kebijakan-gemini.md`).

Dokumen kebijakan (draf, perlu disahkan): `docs/kebijakan-gemini.md`,
`docs/prosedur-insiden-pdp.md`, `docs/dpia.md`.

### 2. Menjalankan (setiap kali)

```bash
# Opsi 1: Pakai script otomatis
./start.sh all

# Opsi 2: Manual
# Terminal 1 - Backend
cd backend && .venv/bin/uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend && npm run dev
```

### 3. Akses Aplikasi

| Service | URL |
|---|---|
| Frontend (Chat UI) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

## 📁 Struktur Project

```
Project-AI-Engineer/
├── backend/
│   ├── main.py          # FastAPI entry point
│   ├── agent.py         # Agentic orchestrator
│   ├── database.py      # PostgreSQL connection
│   ├── models.py        # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── config.py        # Environment config
│   ├── tools/
│   │   ├── rag_tool.py  # RAG similarity search
│   │   ├── ocr_tool.py  # EasyOCR (Bahasa Indonesia)
│   │   └── sql_tool.py  # Read-only SQL tool
│   └── services/
│       ├── embedding_service.py
│       ├── document_service.py
│       └── llm_service.py
├── frontend/
│   └── src/
│       ├── App.jsx              # Auth + routing
│       ├── components/
│       │   ├── ChatBox.jsx      # Main chat interface
│       │   ├── MessageBubble.jsx
│       │   └── UploadButton.jsx
│       └── services/api.js
├── storage/
│   ├── uploads/    # File upload sementara
│   └── processed/
├── docker-compose.yml
├── start.sh        # Script startup otomatis
└── .env.example
```

## 📎 Attach-and-Analyze

Upload dokumen (PDF/TXT) atau gambar jadi **lampiran di composer** (pola
ChatGPT/Gemini) — belum masuk percakapan sampai ditekan kirim. Kirim boleh
kosong (prompt bawaan otomatis: "Ringkas isi dokumen ini." / "Apa isi teks
pada gambar ini?"). Jawaban dibangun **langsung dari dokumen yang baru
diunggah** (`agent.py` mode `DOCUMENT_FOCUS`), bukan lewat similarity
search — ini sengaja menghindari ambang similarity 0.55 yang terbukti bisa
meleset (lihat § Catatan Teknis Penting). Badge "Analisis Dokumen" di
jawaban menandai mode ini, beda dari "RAG Dokumen" (similarity search
biasa, tetap dipakai untuk pertanyaan susulan lintas-dokumen).

## 🔒 Keamanan

- **Authentication**: JWT untuk semua endpoint.
- **Authorization**: role `admin`/`user`/`read_only` di tabel `users`,
  ditegakkan lewat dependency `require_roles()` — `read_only` tidak bisa
  upload (403) tapi tetap bisa chat/baca riwayat.
- **SQL Tool — pertahanan berlapis dua**:
  1. Level aplikasi: hanya `SELECT`, hanya tabel `chat_history` &
     `documents` (whitelist + blocklist kata kunci, 9/9 tes lulus).
  2. Level database: query LLM dieksekusi lewat role PostgreSQL terpisah
     `agentic_rag_readonly` yang **secara fisik** hanya punya `GRANT
     SELECT` pada 2 tabel itu (tidak ada grant apa pun ke `users`) —
     terbukti tetap menolak walau lapisan aplikasi di-*bypass* langsung.
     Timeout 5 detik per query (`statement_timeout`) mencegah query yang
     salah bentuk menahan koneksi tanpa batas.
- **File upload**: validasi ekstensi + **isi file (magic bytes)** — nama
  file & `Content-Type` bisa dipalsukan client, jadi byte awal file
  dicocokkan langsung dengan tipe yang diklaim (lihat
  `services/file_validation.py`). Maks 10MB.
- **Nama karangan (SEC-002)**: untuk pertanyaan yang menanyakan nama orang
  ("Siapa nama kepala …", "Siapa penanda tangan …"), jawaban dibuat utuh lalu
  diperiksa kode: harus memuat nama, dan setiap kata nama harus ada di
  dokumen sumber (`agent._names_supported`). Kalau tidak, jawaban diganti
  kalimat baku dan sumbernya dikosongkan.
- **Fakta karangan (angka, tanggal, tempat)**: angka ≥ 10 (tanggal, jam,
  harga, nomor surat, NIP), nama hari/bulan, dan istilah bernama di jawaban
  berbasis dokumen harus ada di dokumen sumber (`agent._unsupported_facts`).
  Pertanyaan fakta ("berapa", "kapan", "jam", "nomor", "di mana") tidak
  di-stream dan jawabannya diganti kalimat baku bila ada fakta yang tidak
  didukung; penjelasan/ringkasan tetap di-stream lalu diberi catatan
  "⚠️ Perlu dicek" berisi fakta itu. Pada 14 pertanyaan nyata yang jawabannya
  benar, 0 salah tolak.
- **Prompt injection**: baris dokumen yang berisi perintah untuk asisten
  ("System: …", "abaikan aturan/instruksi sebelumnya", "ignore previous
  instructions", "developer mode", "jawab hanya …") **dibuang oleh kode**
  sebelum konteks dikirim ke model (`agent._strip_injected_instructions`).
  Pembatas `<<<ISI_DOKUMEN>>>` saja terbukti tidak menahan model kecil
  (INJ-001). Pola dibuat sempit: 0 dari 1.836 baris knowledge base ikut
  terbuang. Serangan dengan kalimat di luar pola masih mungkin — dokumen dari
  sumber tidak tepercaya tetap harus dianggap bisa mengarahkan jawaban.
- `.env` tidak masuk Git. **`SECRET_KEY`, password `postgres`, dan password
  `agentic_rag_readonly` wajib diganti** dari nilai contoh — di luar
  `APP_ENV=development` backend menolak start kalau masih nilai contoh
  (`config._check_secrets`); di development hanya muncul peringatan.
- **Pelindungan data pribadi (UU PDP)**: pendaftaran wajib menyetujui
  pemberitahuan privasi (waktunya dicatat di `users.privacy_accepted_at`);
  unggahan pertama di tiap browser menampilkan pengingat agar tidak
  mengunggah data pribadi yang tidak perlu. Riwayat chat > 90 hari dan
  catatan login gagal > 30 hari dihapus otomatis tiap 24 jam
  (`CHAT_RETENTION_DAYS`, `LOGIN_ATTEMPT_RETENTION_DAYS`; 0 = nonaktif).
  Akun uji/lama dinonaktifkan dengan `manage_users.py set-active <username> no`.

## 🧪 Test

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Test di `backend/tests/` menguji aturan yang sengaja ditangani kode, bukan
prompt: pagar data internal dinas, jawaban identitas, pengenal pertanyaan
statistik, validasi SQL dan file, pemeriksaan rahasia, dan pencocokan file
unggahan, penyaring prompt injection, sumber dikosongkan untuk jawaban
"tidak ada", pelengkap kata kunci pencarian. Tidak butuh Ollama maupun
database, dan dijalankan otomatis oleh GitHub Actions
(`.github/workflows/tests.yml`) di setiap push.

**Uji end-to-end** (`backend/tests/e2e/`, skenario Bab 6.4 laporan akhir) berjalan
terhadap aplikasi yang sedang hidup dan dilewati kalau `E2E_BASE_URL` kosong:

```bash
E2E_BASE_URL=http://localhost:8000 E2E_ADMIN_USER=<admin> E2E_ADMIN_PASSWORD=<password> \
  .venv/bin/python -m pytest tests/e2e -v
```

Isinya: persetujuan privasi, akun `read_only` tidak bisa unggah, identitas
Nanang, RAG Media Center, cuti tidak dikarang dan tanpa sumber, ejaan nama
kepala dinas, tidak ada data KTP, tabel `users` tidak bocor lewat SQL, dan
dokumen berisi perintah tersembunyi tidak bisa membajak jawaban.

**Observability**: setiap jawaban mencatat satu baris `chat_metrics` di log
backend (tool, `ttft_s`, `total_s`, dan `outcome`: `answered`,
`not_found_in_documents`, `outside_documents`, `refused_internal`,
`identity`) tanpa isi pertanyaan/jawaban. Contoh: `grep chat_metrics <log>`.

## ⚠️ Catatan Teknis Penting

Hal-hal berikut ditemukan saat pengujian dan sudah diperbaiki — jangan
dikembalikan ke kondisi semula:

| Hal | Alasan |
|---|---|
| **Python 3.12, bukan 3.13+** | `pydantic-core` dan `psycopg` belum punya wheel untuk Python 3.13/3.14. `start.sh` sengaja gagal cepat jika `python3.12` tidak ada. |
| **Index HNSW, bukan ivfflat** | `ivfflat` membagi data ke beberapa list dan default hanya memindai satu list per query. Pada knowledge base kecil, sebagian besar chunk tidak pernah terpindai — pencarian mengembalikan 0 baris meski datanya ada. |
| **Embedding `paraphrase-multilingual` + ambang similarity 0.49** | `all-minilm` (dipakai sebelumnya, ambang 0.55) dilatih untuk bahasa Inggris: pada teks Indonesia pita skor relevan (0.460–0.715) dan luar topik (0.487–0.599) tumpang tindih, jadi tidak ada ambang yang bisa memisahkan. `paraphrase-multilingual` memisahkan keduanya dengan bersih (relevan 0.547–0.832, luar topik 0.179–0.337); 0.49 diukur untuk model ini — lihat `tools/rag_tool.py`. Ganti model = ubah `VECTOR()` di `init.sql` dan `models.py`, jalankan `reindex_documents.py --apply`, lalu ukur ulang ambangnya. |
| **`env_file` pakai path absolut** | `uvicorn` dijalankan dari dalam `backend/`, sehingga `.env` relatif tidak ketemu dan semua konfigurasi diam-diam memakai default — termasuk `SECRET_KEY`. |
| **`bcrypt` langsung, bukan `passlib`** | `passlib` 1.7.4 tidak kompatibel dengan `bcrypt` 5.x. |
| **Gambar di-OCR saat upload, bukan saat ditanya** | `ChatRequest.image_filename` dan cabang `image_path` di `agent.py` sudah dihapus. Teks gambar dibaca sekali di `/upload` lalu disimpan ke knowledge base, dan pertanyaan soal gambar dikirim lewat `document_filename` seperti dokumen lain. Jalur lama meng-OCR ulang gambar di setiap pertanyaan (5–30 detik) dan sudah tidak dipakai frontend. Jangan dikembalikan. |
| **Instruksi fallback "balas persis: ..." dihapus dari prompt jawaban akhir** | Pada `llama3.2:1b`, instruksi larangan multi-baris ini justru membuat model salah menolak menjawab meski konteksnya sudah lengkap (terbukti pada pertanyaan OCR terbuka). Karena ambang similarity 0.55 sudah menyaring pertanyaan tak relevan sebelum LLM dipanggil, instruksi ini lebih banyak menimbulkan regresi daripada manfaat. |
| **Ekstraksi SQL pakai regex, bukan `.strip("```sql")`** | `.strip()` hanya membersihkan ujung string; `llama3.2:1b` selalu membungkus SQL dengan penjelasan naratif di depannya, jadi SEMUA query yang dihasilkan LLM otomatis gagal validasi (ditolak sebagai "bukan SELECT"). Fitur SQL_QUERY 100% tidak pernah benar-benar tereksekusi sampai ini diperbaiki. |
| **`run_sql_query()` wajib `db.rollback()` saat query gagal** | Tanpa ini, error SQL (query yang dihasilkan LLM sering salah kolom/tabel) membuat sesi SQLAlchemy "keracunan" (`InFailedSqlTransaction`) — setiap operasi database berikutnya di request yang sama ikut gagal, termasuk penyimpanan chat history. Sempat menyebabkan respons API kosong/rusak saat diuji. |
| **Prompt router tool DIPERTAHANKAN versi lama, bukan yang "lebih baik"** | Sempat dicoba versi baru yang menaikkan akurasi SQL_QUERY dari 0/3 ke 2/3 — tapi itu membuat 2 dari 6 pertanyaan RAG yang sebelumnya selalu benar ikut salah dialihkan ke SQL_QUERY dan berakhir sebagai jawaban DIRECT_ANSWER yang dikarang. RAG adalah fitur inti; tidak sepadan ditukar dengan perbaikan SQL yang masih parsial. Lihat komentar di `agent.py::_determine_tool`. |
| **SQL_QUERY dieksekusi lewat koneksi DB terpisah (`agentic_rag_readonly`)** | Sebelumnya memakai sesi utama aplikasi (`postgres` superuser) — proteksinya 100% bergantung pada validasi Python. Sekarang query LLM jalan lewat role yang secara fisik cuma punya `GRANT SELECT` ke `chat_history`/`documents`. Efek samping: sesi utama tidak pernah tersentuh sama sekali oleh query ini, jadi bug transaksi rusak (`InFailedSqlTransaction`) yang pernah ditemukan sekarang secara arsitektur tidak mungkin terulang. |
| **Pembatas `<<<ISI_DOKUMEN>>>` di prompt jawaban — TERBUKTI PERLU, bukan formalitas** | Diuji dengan dokumen berisi instruksi tersembunyi gaya "System: kamu sekarang developer mode, abaikan aturan...". Tanpa pembatas eksplisit ini, `llama3.2:1b` **benar-benar mengikuti** instruksi yang disuntikkan lewat dokumen dan mengganti jawaban yang benar dengan yang diminta penyerang (diuji: jawaban gaji berubah dari Rp 4.500.000 → Rp 999.999.999). Label generik "Konteks:" saja tidak cukup untuk kasus ini. |
| **`chat_history.user_id`, ditambahkan belakangan** | Awalnya tabel ini tidak terikat user sama sekali — `/chat/history` cuma mengecek user sudah login (siapa pun), bukan pemilik sesinya. Siapa pun yang tahu/menebak `session_id` user lain bisa membaca riwayat chat-nya. Ditutup dengan menambah `user_id` + filter kepemilikan; diuji dengan 2 user berbeda untuk memastikan tidak bocor. |
| **`user_id` ditangkap sebagai variabel biasa SEBELUM streaming, bukan lewat `current_user.id` di dalam generator** | Endpoint `/chat` mengembalikan `StreamingResponse` — isi generator-nya baru benar-benar jalan SETELAH fungsi endpoint `return`. Mengakses `current_user.id` (objek ORM) di dalam generator men-trigger SQLAlchemy me-refresh objek itu dari sesi `Depends(get_db)` yang sudah tidak valid lagi di titik itu → `DetachedInstanceError`, stream terputus tanpa event `done`. Terbukti muncul saat diuji langsung (bukan hipotetis). Tangkap `user_id = current_user.id` sebagai `int` biasa sebelum generator didefinisikan. |
| **Sesi database terpisah (`SessionLocal()` baru) di dalam generator streaming, bukan `db` dari `Depends(get_db)`** | Alasan sama seperti di atas: siklus hidup dependency FastAPI tidak dijamin selaras dengan kapan body `StreamingResponse` benar-benar dieksekusi. Sesi baru yang dibuka & ditutup sendiri di dalam generator menghindari ambiguitas ini sepenuhnya, tidak bergantung pada detail versi FastAPI. |
| **`file.filename` di-sanitasi ke basename (`Path(file.filename).name`) sebelum dipakai di mana pun** | **Celah arbitrary file write terkonfirmasi & dieksploitasi saat diuji**: `safe_name = f"{uuid}_{file.filename}"` lalu `os.path.join(upload_dir, safe_name)` — kalau `file.filename` berisi `"foo/../../../../tmp/evil.txt"`, path hasil join benar-benar keluar dari `upload_dir` saat file ditulis ke disk (dibuktikan langsung: file mendarat di `/tmp/...` bukan di `storage/uploads/`). User terautentikasi mana pun (bukan cuma admin) bisa menulis file ke lokasi sembarang di server. `file.filename` datang mentah dari header multipart, bisa diisi string apa pun oleh client non-browser. |

### ⚠️ Risiko terkonfirmasi: sitasi palsu pada pertanyaan tentang nama/jabatan

Diuji dan direproduksi secara konsisten: jika pengguna bertanya tentang
**nama orang atau pejabat spesifik** yang topiknya mirip dokumen tapi
faktanya tidak ada di dalamnya (mis. "Siapa nama kepala dinas Diskominfo
saat ini?" terhadap dokumen kebijakan cuti yang hanya menyebut kata
"Diskominfo"), `llama3.2:1b` akan **mengarang nama** dan sistem tetap
menyitasi dokumen asli sebagai sumbernya — padahal dokumen itu sama sekali
tidak menyebut nama tersebut.

**Root cause:** skor similarity chunk yang salah pada kasus ini (0.58) lebih
tinggi dari skor chunk yang benar pada kasus lain yang terbukti berfungsi
(0.57, pertanyaan cuti melahirkan). Karena itu, tidak ada satu pun nilai
ambang similarity yang bisa memisahkan keduanya — menaikkan ambang untuk
memblokir kasus ini otomatis akan merusak kasus RAG yang sudah benar.

**Sudah dicoba dan terbukti tidak menyelesaikan masalah ini secara spesifik**
(meski beberapa berguna untuk hal lain):
- Instruksi fallback "balas: Informasi tidak ditemukan" di berbagai
  formulasi — model tetap mengarang nama pada kasus ini, dan pada kasus lain
  malah salah menolak menjawab pertanyaan yang jawabannya sebenarnya ada.
- Verifikasi dua-tahap (LLM mengecek ulang jawabannya sendiri) — model 1B
  punya bias negatif sistematis pada tugas ya/tidak, selalu condong menjawab
  "tidak cocok" bahkan untuk jawaban yang benar.
- Instruksi khusus di system prompt melarang mengarang nama orang — tetap
  diabaikan model pada kasus ini.

**Mitigasi yang berlaku saat ini:** ambang similarity 0.49 tetap menyaring
mayoritas pertanyaan yang benar-benar tidak relevan secara topik (terbukti
efektif). Risiko residual hanya pada zona sempit "topik mirip, fakta spesifik
tidak ada" — terutama pertanyaan tentang nama orang/pejabat. **Rekomendasi:
jangan andalkan jawaban sistem ini untuk pertanyaan semacam itu tanpa
verifikasi manual terhadap dokumen aslinya.** Perbaikan yang lebih permanen
memerlukan salah satu dari: model LLM yang jauh lebih besar, reranker
cross-encoder terpisah, atau hybrid search (BM25 + vector) — di luar
anggaran RAM 8GB & waktu pengembangan project pelatihan ini.

### Keterbatasan yang diketahui

- **Routing tool masih lemah.** `llama3.2:1b` cenderung memilih `RAG_SEARCH`
  untuk hampir semua pertanyaan dan jarang memilih `SQL_QUERY`. Jawaban tetap
  benar karena agent jatuh ke `direct_answer` saat RAG tidak menemukan konteks,
  tetapi pertanyaan statistik belum tentu benar-benar menjalankan SQL. Model
  yang lebih besar (`llama3.2:3b` ke atas) akan jauh lebih akurat memilih tool.
- **Akurasi OCR EasyOCR bervariasi** pada teks kecil/renggang — pada uji coba,
  spasi dan tanda baca (`/`, `-`) kadang hilang atau berubah simbol. Untuk
  dokumen resmi hasil scan/foto, cek ulang hasil OCR sebelum dipakai sebagai
  rujukan.

## ⏱️ Performa (Terukur)

Diukur pada mesin pengembangan (Apple Silicon, 8GB RAM), model sudah termuat:

| Jenis pertanyaan | Latensi | Keterangan |
|---|---|---|
| RAG (dokumen) | ~1.5 detik sampai token pertama tampil | embedding + panggilan router, lalu jawaban di-stream |
| Jawaban langsung | ~0.7 detik sampai token pertama tampil | panggilan router, lalu jawaban di-stream |
| SQL | ~10 detik total | 3 panggilan LLM (router + generate SQL + jawaban); model cenderung menulis penjelasan panjang di sekitar query SQL-nya |

> [!NOTE]
> **Jawaban akhir di-stream token demi token** (`POST /chat` membalas NDJSON,
> bukan satu blob JSON — lihat `agent.py::run_agent_stream` &
> `services/llm_service.py::stream_llm`). Angka di atas adalah waktu sampai
> *token pertama* tampil (tool selection + retrieval), bukan waktu sampai
> jawaban selesai total — sejak streaming aktif, pengguna mulai melihat
> jawaban jauh sebelum itu, yang terasa jauh lebih responsif meski total
> waktu keseluruhan sama. Panggilan LLM internal (router pemilih tool,
> generate query SQL) TETAP non-streaming — hanya jawaban akhir yang
> ditampilkan ke user yang di-stream.

> [!WARNING]
> **RAM 8GB benar-benar mepet, bukan sekadar peringatan teoretis.** Saat
> Docker Desktop + PostgreSQL + Ollama (2 model termuat) + backend + frontend
> berjalan bersamaan dalam sesi pengembangan yang panjang, **swap terpakai
> hingga 19.7GB dari 20GB** yang tersedia di sistem uji. Ikuti anjuran di
> bagian "Manajemen RAM 8GB" di atas — jangan jalankan semua service terus-
> menerus tanpa perlu, terutama Docker Desktop saat hanya melakukan chat
> tanpa RAG/upload.

## 📊 Optimasi RAM 8GB

- Model `llama3.2:3b` (~2GB di disk, ~2,6GB saat dimuat). Dipilih setelah diuji berdampingan dengan `llama3.2:1b`: 3b menjawab lengkap dan jujur saat informasi tidak ada di dokumen, sementara 1b sering meringkas terlalu pendek dan salah membaca tabel harga. Kekurangannya, jawaban 2-4x lebih lambat (5-32 detik). Kembali ke 1b cukup dengan `OLLAMA_LLM_MODEL=llama3.2:1b` di `.env`
- Embedding `paraphrase-multilingual` (~560MB)
- EasyOCR lazy loading (dimuat saat dibutuhkan)
- PostgreSQL dibatasi 512MB via docker-compose
- `num_ctx=8192` (`LLM_NUM_CTX` di config.py) — cukup untuk dokumen lampiran ~12.000 karakter + riwayat percakapan; KV-cache ~940MB pada llama3.2:3b (~256MB pada 1b)
