# Penilaian Dampak Pelindungan Data Pribadi (DPIA) — Aplikasi Nanang

> **Status: DRAF** — disusun dari kondisi aplikasi per 27 September 2026.
> Perlu ditinjau dan disahkan Kepala Dinas Diskominfo SP TIK HSS. Rujukan
> pasal UU No. 27 Tahun 2022 perlu diverifikasi bagian hukum.

## 1. Mengapa DPIA diperlukan

UU PDP mewajibkan penilaian dampak bila pemrosesan berpotensi berisiko tinggi
bagi subjek data (Pasal 34), antara lain pemrosesan data dalam skala besar,
penggunaan teknologi baru, dan pencocokan/penggabungan data. Nanang memakai
teknologi baru (model bahasa dan pencarian vektor) untuk memproses dokumen
dinas yang memuat data pribadi pegawai.

## 2. Deskripsi pemrosesan

| Aspek | Keterangan |
|---|---|
| Pengendali data | Diskominfo SP TIK Kabupaten Hulu Sungai Selatan |
| Tujuan | Menjawab pertanyaan pegawai dari dokumen dinas, meringkas lampiran, statistik pemakaian |
| Dasar pemrosesan | Pelaksanaan tugas/kewenangan instansi (Pasal 20) dan persetujuan pengguna saat mendaftar (dicatat di `users.privacy_accepted_at`) |
| Subjek data | Pegawai pengguna aplikasi; pegawai/pejabat yang namanya tercantum di dokumen |
| Lokasi pemrosesan | Server dinas (Ollama, PostgreSQL lokal). Gemini dinonaktifkan |
| Penerima di luar dinas | Tidak ada selama Gemini nonaktif (lihat `docs/kebijakan-gemini.md`) |

## 3. Inventaris data

| Lokasi | Data pribadi | Siapa yang bisa mengakses | Retensi |
|---|---|---|---|
| `users` | username, email, hash password (bcrypt), role, status, waktu persetujuan | Backend; tidak bisa dibaca tool SQL | Selama akun ada |
| `chat_history` | isi pertanyaan & jawaban, lampiran, waktu | Pemilik sesi; tool SQL dibatasi ke baris penanya | 90 hari (otomatis) |
| `documents` + `storage/uploads` | isi dokumen: nama, NIP, jabatan pegawai | Sesuai tingkat akses dokumen (tabel 4) | Sampai dihapus admin (chunk + file ikut terhapus) |
| `login_attempts` | username, IP percobaan gagal | Backend/admin | 30 hari (otomatis) |
| Log backend (`chat_metrics`) | tool, waktu, jenis jawaban — **tanpa** isi pesan | Admin server | Mengikuti rotasi log server |

## 4. Kontrol akses dokumen

| Tingkat | Bisa dicari oleh | Dipakai untuk |
|---|---|---|
| `umum` | Semua akun, termasuk `read_only` | Profil, katalog layanan, SOP, FAQ, glosarium |
| `internal` | `user` dan `admin` | Surat, SPT, berita acara (memuat nama/NIP) — **bawaan unggahan** |
| `rahasia` | `admin` | Dokumen sensitif |

Ditegakkan di semua jalur baca (RAG, kata kunci, lampiran, dokumen yang
disebut namanya, deteksi lanjutan, daftar dokumen, tool SQL) dan diuji di
`backend/tests/e2e/test_live.py`. Akun hasil pendaftaran mandiri selalu
`read_only`; hanya admin yang menaikkan role dan mengubah tingkat akses.

## 5. Penilaian risiko

Skala: Kemungkinan (K) dan Dampak (D) 1–3; Risiko = K × D.

| # | Risiko | K | D | Awal | Kontrol yang diterapkan | Sisa |
|---|---|---|---|---|---|---|
| R1 | Dokumen berdata pribadi dibaca akun yang tidak berhak | 3 | 3 | 9 | Tingkat akses per dokumen, bawaan `internal`, akun baru `read_only`, pengingat sebelum unggah | 2 (salah klasifikasi oleh pengunggah) |
| R2 | Model mengarang nama/jabatan dan menyitasi dokumen | 3 | 2 | 6 | Pemeriksaan nama oleh kode (nama di jawaban harus ada di dokumen), pagar data internal, sumber dikosongkan untuk jawaban "tidak ada" | 2 |
| R3 | Dokumen berisi perintah tersembunyi membajak jawaban | 2 | 2 | 4 | Baris perintah untuk asisten dibuang sebelum ke model; unggah hanya `user`/`admin` | 2 (pola di luar daftar) |
| R4 | Tool SQL membocorkan akun atau data pengguna lain | 2 | 3 | 6 | Role database read-only tanpa akses `users`, CTE per pengguna dan per tingkat akses, timeout 5 dtk | 1 |
| R5 | Token dipalsukan karena SECRET_KEY bocor/default | 2 | 3 | 6 | SECRET_KEY acak; backend menolak start dengan nilai contoh di produksi | 1 |
| R6 | Data terkirim ke luar negeri lewat Gemini | 2 | 3 | 6 | Gemini nonaktif; bila aktif hanya kutipan dokumen `umum` | 1 |
| R7 | Penyimpanan data melebihi keperluan | 3 | 1 | 3 | Retensi otomatis; hapus dokumen ikut hapus file; pembersihan file lama | 1 |
| R8 | Pengambilalihan akun lewat tebak password | 2 | 2 | 4 | bcrypt, kunci 15 menit setelah 5 gagal, akun uji dinonaktifkan | 1 |

## 6. Risiko sisa dan tindak lanjut

1. **Salah klasifikasi dokumen (R1).** Pengunggah bisa memberi tingkat yang
   terlalu rendah. Tindak lanjut: admin meninjau daftar dokumen `umum` setiap
   bulan (`docs/prosedur-insiden-pdp.md` § 3.1).
2. **Model kecil (R2, R3).** Pemeriksaan kode mengurangi, tetapi tidak
   menghilangkan, jawaban keliru. Tindak lanjut: pindah ke server dengan RAM
   ≥ 16 GB untuk model 7–8B; jalankan `tests/e2e` setiap perubahan.
3. **Cadangan database dan log** belum terenkripsi. Tindak lanjut: simpan
   `pg_dump` di media terenkripsi dengan akses terbatas.

## 7. Kesimpulan

Dengan kontrol di atas, risiko sisa berada pada tingkat rendah (≤ 2) dan
pemrosesan dapat dilanjutkan untuk pengguna internal dinas, dengan syarat
tindak lanjut di bagian 6 dijadwalkan dan Gemini tetap nonaktif di produksi.

## 8. Persetujuan

| Peran | Nama | Tanggal | Tanda tangan |
|---|---|---|---|
| Penyusun | Muhammad Noor Yusuf | 27 September 2026 | |
| Pejabat PDP | «isi» | | |
| Kepala Dinas | «isi» | | |
