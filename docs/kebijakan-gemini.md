# Kebijakan Pemakaian Gemini pada Aplikasi Nanang

> **Status: DRAF** — disusun dari konfigurasi aplikasi per 27 September 2026.
> Perlu ditinjau dan disahkan oleh Kepala Dinas Diskominfo SP TIK HSS bersama
> pejabat yang menangani pelindungan data pribadi. Rujukan pasal UU PDP perlu
> diverifikasi bagian hukum sebelum disahkan.

## 1. Tujuan

Mengatur kapan model Gemini (Google) boleh dipakai sebagai penulis jawaban di
aplikasi Nanang, karena memakai Gemini berarti data dikirim ke layanan di luar
server dinas dan kemungkinan di luar wilayah hukum Indonesia (transfer data
pribadi ke luar negeri, UU No. 27 Tahun 2022 Pasal 56).

## 2. Status saat ini

- Gemini **dinonaktifkan** di server dinas: `GEMINI_API_KEY` di `.env` kosong,
  sehingga `GET /models` hanya mengembalikan model lokal (`llama3.2:3b`) dan
  pilihan Gemini tidak tampil di antarmuka.
- Model lokal (Ollama) adalah model utama dan satu-satunya model yang aktif.

## 3. Data yang dikirim bila Gemini diaktifkan

Saat pengguna memilih Gemini untuk satu pertanyaan, yang dikirim ke Google:

| Data | Dikirim? |
|---|---|
| Pertanyaan pengguna | Ya |
| Riwayat percakapan sesi itu (maks. 6 pesan terakhir) | Ya |
| Kutipan dokumen knowledge base | **Hanya dokumen bertingkat `umum`** |
| Isi dokumen `internal` / `rahasia` | Tidak — ditegakkan oleh kode |
| Identitas akun, password, token | Tidak |
| Pemilihan tool, deteksi lanjutan, query SQL | Tidak — tetap diproses model lokal |

Pembatasan kutipan ke dokumen `umum` ditegakkan di `backend/main.py` (`/chat`):
bila `model == "gemini"`, tingkat akses pencarian dipersempit ke `umum` untuk
semua role, termasuk admin.

## 4. Ketentuan

1. Gemini **tidak diaktifkan di server produksi** yang melayani pegawai,
   kecuali Kepala Dinas menyetujui secara tertulis setelah penilaian dampak
   (lihat `docs/dpia.md` bagian Gemini).
2. Bila diaktifkan, hanya untuk pertanyaan yang **tidak memuat data pribadi**
   (nama, NIK, NIP, alamat, data kesehatan, nomor rekening). Pengguna
   diingatkan lewat pemberitahuan privasi saat mendaftar dan peringatan di UI
   setiap kali memilih Gemini.
3. Dokumen yang berisi data pribadi **wajib** bertingkat `internal` atau
   `rahasia`, sehingga tidak pernah ikut dikirim ke Gemini.
4. Setiap jawaban Gemini tercatat di `chat_history.model = 'gemini'` sebagai
   jejak audit; admin meninjaunya bulanan.
5. API key disimpan hanya di `.env` server, tidak pernah dikirim ke frontend
   dan tidak masuk Git.

## 5. Cara mengaktifkan / menonaktifkan

```bash
# Nonaktifkan (kondisi saat ini)
GEMINI_API_KEY=            # di .env, lalu restart backend

# Aktifkan (hanya setelah persetujuan tertulis)
GEMINI_API_KEY=<kunci>     # di .env, lalu restart backend
```

## 6. Peninjauan

Kebijakan ini ditinjau setiap triwulan atau saat ketentuan layanan Google,
nama model (`GEMINI_MODEL`), atau regulasi PDP berubah.
