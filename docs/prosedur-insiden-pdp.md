# Prosedur Penanganan Insiden Pelindungan Data Pribadi — Aplikasi Nanang

> **Status: DRAF** — perlu ditinjau dan disahkan Kepala Dinas Diskominfo SP TIK
> HSS. Rujukan pasal UU No. 27 Tahun 2022 (UU PDP) perlu diverifikasi bagian
> hukum. Perintah deteksi, `manage_users.py`, hapus dokumen, rotasi kunci, dan
> `pg_dump` di bawah sudah dijalankan pada aplikasi per 27 September 2026.

## 1. Ruang lingkup

Berlaku untuk kegagalan pelindungan data pribadi pada aplikasi Nanang:
database PostgreSQL (`users`, `chat_history`, `documents`, `login_attempts`,
`upload_jobs`), folder `storage/uploads`, file `.env`, dan log backend.

Contoh insiden:
- akun diambil alih atau dipakai orang yang tidak berhak;
- dokumen berisi data pribadi terunggah dengan tingkat akses `umum`;
- `.env` (SECRET_KEY, password database) bocor;
- data dikirim ke Gemini padahal tidak diizinkan;
- server atau cadangan database diakses pihak luar.

## 2. Peran

| Peran | Tugas |
|---|---|
| Pelapor (siapa pun) | Melaporkan dugaan insiden ke admin aplikasi secepatnya |
| Admin aplikasi | Penahanan teknis, pengumpulan bukti, pemulihan |
| Pejabat PDP / Kepala Dinas | Keputusan pemberitahuan, komunikasi ke subjek data dan lembaga |
| Bagian hukum | Penilaian kewajiban hukum dan isi pemberitahuan |

## 3. Tahapan

### 3.1 Deteksi (jam ke-0)

Sumber tanda insiden yang sudah ada di aplikasi:

```bash
# Percobaan login gagal beruntun (akun ditebak-tebak)
docker exec agentic-rag-db psql -U postgres -d agentic_rag \
  -c "SELECT username, ip_address, count(*) FROM login_attempts
      WHERE created_at > now() - interval '1 day' GROUP BY 1,2 ORDER BY 3 DESC;"

# Pola pemakaian per jawaban (tool, jenis jawaban, waktu) — tanpa isi pesan
grep chat_metrics /tmp/agentic-rag-smoke/backend.log | tail -50

# Dokumen per tingkat akses (cek dokumen berdata pribadi yang terbuka "umum")
docker exec agentic-rag-db psql -U postgres -d agentic_rag \
  -c "SELECT access_level, filename, uploaded_by FROM documents GROUP BY 1,2,3 ORDER BY 1,2;"

# Jawaban yang dikirim ke Gemini
docker exec agentic-rag-db psql -U postgres -d agentic_rag \
  -c "SELECT count(*), max(created_at) FROM chat_history WHERE model = 'gemini';"
```

Catat: waktu diketahui, pelapor, gejala, data dan akun yang diduga terdampak.

### 3.2 Penahanan (target ≤ 4 jam)

Pilih sesuai jenis insiden (dijalankan dari `backend/`):

```bash
# Nonaktifkan akun yang disalahgunakan (login langsung ditolak)
.venv/bin/python3 manage_users.py set-active <username> no

# Turunkan hak akses akun
.venv/bin/python3 manage_users.py set-role <username> read_only

# Dokumen berdata pribadi terlanjur "umum": ubah tingkat akses lewat panel
# Dokumen (admin), atau hapus dokumen beserta semua file aslinya
curl -X DELETE -H "Authorization: Bearer <token-admin>" \
  "http://localhost:8000/documents/<nama-file>"

# SECRET_KEY bocor: buat kunci baru di .env lalu restart backend —
# SEMUA token login lama langsung tidak berlaku
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Password database bocor: ganti lalu samakan .env (lihat README
# § "Ganti password bawaan")

# Gemini disalahgunakan: kosongkan GEMINI_API_KEY di .env, restart backend
```

Jangan menghapus log, `login_attempts`, atau `chat_history` yang menjadi bukti
sebelum disalin (lihat 3.3). Retensi otomatis (chat 90 hari, login gagal 30
hari) bisa dimatikan sementara dengan `CHAT_RETENTION_DAYS=0` dan
`LOGIN_ATTEMPT_RETENTION_DAYS=0` selama investigasi.

### 3.3 Pengumpulan bukti dan penilaian (target ≤ 24 jam)

```bash
docker exec agentic-rag-db pg_dump -U postgres agentic_rag > insiden-$(date +%F).sql
cp /tmp/agentic-rag-smoke/backend.log insiden-$(date +%F)-backend.log
```

Simpan salinan di media yang aksesnya terbatas. Tentukan:
- data pribadi apa yang terdampak (nama, NIP, NIK, isi percakapan, dll.);
- jumlah subjek data dan siapa saja;
- apakah data sudah diakses/disalin pihak yang tidak berhak;
- risiko bagi subjek data.

### 3.4 Pemberitahuan (paling lambat 3 × 24 jam)

Bila terjadi kegagalan pelindungan data pribadi, pengendali data wajib
menyampaikan pemberitahuan tertulis kepada subjek data dan lembaga paling
lambat 3 × 24 jam (UU PDP Pasal 46). Isi pemberitahuan minimal:

1. data pribadi yang terungkap;
2. kapan dan bagaimana data terungkap;
3. upaya penanganan dan pemulihan yang dilakukan.

Keputusan dan isi pemberitahuan ditetapkan Kepala Dinas bersama bagian hukum.

### 3.5 Pemulihan

- Aktifkan kembali akun yang tidak bersalah (`set-active <username> yes`).
- Unggah ulang dokumen dengan tingkat akses yang benar bila perlu.
- Jalankan uji regresi sebelum layanan dibuka kembali:

```bash
cd backend && .venv/bin/python -m pytest
E2E_BASE_URL=http://localhost:8000 E2E_ADMIN_USER=<admin> E2E_ADMIN_PASSWORD=<pw> \
  .venv/bin/python -m pytest tests/e2e
```

### 3.6 Evaluasi (≤ 14 hari)

Tulis laporan pasca-insiden: kronologi, penyebab, dampak, tindakan, dan
perbaikan permanen. Perbarui `docs/dpia.md` bila risiko baru ditemukan.

## 4. Kontak

| Peran | Nama | Kontak |
|---|---|---|
| Admin aplikasi | «isi» | «isi» |
| Pejabat PDP | «isi» | «isi» |
| Kepala Dinas | «isi» | «isi» |
