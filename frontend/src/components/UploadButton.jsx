// src/components/UploadButton.jsx
import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Paperclip, ShieldCheck } from 'lucide-react'
import { uploadFile } from '../services/api'

const ALLOWED = [
  'application/pdf', 'text/plain', 'image/png', 'image/jpeg', 'image/webp',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',       // .xlsx
]
const ALLOWED_EXT = '.pdf, .txt, .docx, .xlsx, .png, .jpg, .jpeg, .webp'
// Browser/OS kadang salah melaporkan (atau mengosongkan) file.type untuk
// docx/xlsx — TERBUKTI: beberapa kombinasi OS/browser mengirim
// "application/octet-stream" alih-alih MIME OOXML yang benar untuk kedua
// format ini. Ekstensi jadi fallback supaya file valid tidak tertolak cuma
// karena MIME-nya salah terbaca; backend tetap jadi validator sesungguhnya
// (ekstensi + magic bytes) jadi ini tidak melonggarkan keamanan.
const ALLOWED_EXT_LIST = ALLOWED_EXT.split(',').map((e) => e.trim())

// Tingkat akses yang bisa dipilih per role — sama dengan backend/access.py
// (backend tetap yang menegakkan; ini hanya supaya pilihan yang ditolak
// tidak ditawarkan).
const ACCESS_OPTIONS = [
  { value: 'umum', label: 'Umum', desc: 'Bisa dicari semua akun. Hanya untuk dokumen tanpa data pribadi (SOP, katalog layanan, FAQ).' },
  { value: 'internal', label: 'Internal', desc: 'Hanya pegawai yang disetujui admin. Untuk surat, SPT, berita acara.' },
  { value: 'rahasia', label: 'Rahasia', desc: 'Hanya admin.' },
]
const ROLE_ACCESS = { read_only: ['umum'], user: ['umum', 'internal'], admin: ['umum', 'internal', 'rahasia'] }

// `processing` datang dari ChatBox, yang memantau pekerjaan sampai selesai —
// pemantauan tidak ditaruh di sini karena harus tetap berjalan (dan bisa
// dilanjutkan setelah halaman dimuat ulang) terlepas dari tombol ini.
export default function UploadButton({ onJobStarted, onError, processing, role }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  // Spinner tetap berputar selama server masih memproses, walau transfer
  // berkasnya sendiri sudah selesai sejak tadi.
  const busy = uploading || processing

  // Berkas yang sudah lolos validasi, menunggu pengunggah memilih tingkat
  // akses di dialog. Setiap unggahan wajib diklasifikasi — dulu semua
  // unggahan lewat UI otomatis "internal" tanpa ditanya.
  const [pendingFile, setPendingFile] = useState(null)
  const [accessLevel, setAccessLevel] = useState('internal')
  const choices = ACCESS_OPTIONS.filter((o) => (ROLE_ACCESS[role] ?? ['umum', 'internal']).includes(o.value))

  const cancelPending = () => {
    setPendingFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFile = (file) => {
    if (!file) return
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
    if (!ALLOWED.includes(file.type) && !ALLOWED_EXT_LIST.includes(ext)) {
      onError?.(`Format tidak didukung. Gunakan: ${ALLOWED_EXT}`)
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      onError?.('Ukuran file melebihi 10MB.')
      return
    }
    setAccessLevel(choices.some((c) => c.value === 'internal') ? 'internal' : choices[0]?.value ?? 'internal')
    setPendingFile(file)
  }

  const startUpload = async () => {
    const file = pendingFile
    setPendingFile(null)

    // Preview dibuat dari File object di browser (blob URL) — tidak perlu
    // menunggu upload selesai atau memanggil endpoint tambahan di backend.
    const isImage = file.type.startsWith('image/')
    const previewUrl = isImage ? URL.createObjectURL(file) : null

    setUploading(true)
    try {
      // Transfer berkas selesai cepat; ekstraksi/OCR/embedding berjalan di
      // server. job_id diserahkan ke ChatBox yang memantaunya sampai selesai.
      const { job_id } = await uploadFile(file, accessLevel)
      onJobStarted?.({ jobId: job_id, filename: file.name, previewUrl, fileSize: file.size })
    } catch (err) {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      onError?.(err.response?.data?.detail || 'Upload gagal.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }

  return (
    <>
      {/* Portal ke body: composer punya transform (animasi), yang membuat
          position:fixed di dalamnya relatif ke composer — dialog sempat
          terpotong di bawah layar dan tombol Unggah tidak terlihat (uji DOM). */}
      {pendingFile && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} onClick={cancelPending} />
          <div
            role="dialog"
            aria-labelledby="upload-dialog-title"
            className="relative w-full max-w-md rounded-3xl glass slide-up-fade p-6 flex flex-col gap-4"
            style={{ background: 'var(--bg-secondary)' }}
          >
            <h2 id="upload-dialog-title" className="font-bold text-base flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
              <ShieldCheck size={20} className="opacity-80" /> Siapa yang boleh mencari dokumen ini?
            </h2>
            <p className="text-sm truncate" style={{ color: 'var(--text-muted)' }} title={pendingFile.name}>
              {pendingFile.name}
            </p>
            <div className="flex flex-col gap-2">
              {choices.map((o) => (
                <label
                  key={o.value}
                  htmlFor={`access-${o.value}`}
                  className="flex items-start gap-3 px-3 py-2.5 rounded-xl cursor-pointer"
                  style={{
                    background: accessLevel === o.value ? 'var(--overlay-2)' : 'var(--overlay-1)',
                    border: `1px solid ${accessLevel === o.value ? 'var(--accent-blue)' : 'var(--glass-border)'}`,
                  }}
                >
                  <input
                    id={`access-${o.value}`}
                    type="radio"
                    name="access-level"
                    value={o.value}
                    checked={accessLevel === o.value}
                    onChange={() => setAccessLevel(o.value)}
                    className="mt-1"
                  />
                  <span>
                    <span className="text-sm font-semibold block" style={{ color: 'var(--text-primary)' }}>{o.label}</span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{o.desc}</span>
                  </span>
                </label>
              ))}
            </div>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Jangan unggah data pribadi yang tidak perlu (KTP, NIK, nomor rekening, data kesehatan). Dokumen
              "Umum" yang ternyata memuat NIK, NIP, nama bergelar, email, atau nomor HP otomatis disimpan sebagai
              "Internal".
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelPending}
                className="text-sm font-semibold px-4 py-2 rounded-xl hover:bg-[var(--overlay-2)]"
                style={{ color: 'var(--text-muted)' }}
              >
                Batal
              </button>
              <button
                id="upload-confirm-btn"
                type="button"
                onClick={startUpload}
                className="text-sm font-bold px-4 py-2 rounded-xl text-white"
                style={{ background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))' }}
              >
                Unggah
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_EXT}
        className="hidden"
        id="upload-input"
        onChange={(e) => handleFile(e.target.files[0])}
      />
      <label
        htmlFor="upload-input"
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        title="Upload dokumen atau gambar (PDF, TXT, DOCX, XLSX, PNG, JPG)"
        className={`cursor-pointer flex items-center justify-center rounded-xl transition-all duration-200 flex-shrink-0 ${
          busy ? 'px-3 h-10 gap-2' : 'w-10 h-10 hover:scale-105 active:scale-95'
        }`}
        style={{
          background: busy ? 'var(--overlay-3)' : 'var(--overlay-2)',
          border: '1px solid var(--glass-border)',
        }}
      >
        {busy ? (
          <>
            {/* Spinner tanpa angka — persentase transfer byte selesai
                dalam hitungan milidetik di localhost (diukur langsung:
                ~0.3ms), sementara pemrosesan server (extract teks, chunk,
                generate embedding) yang sebenarnya makan waktu 1-10 detik
                sama sekali tidak terukur oleh event upload-progress
                browser. Menampilkan angka % di titik ini cuma berupa
                "100%" seketika lalu diam — terlihat seperti macet,
                padahal justru sedang bekerja. Indikator tak-tentu lebih
                jujur untuk kondisi yang memang tidak bisa diukur presisi. */}
            <svg className="animate-spin w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="var(--overlay-3)" strokeWidth="2"/>
              <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--accent-purple)" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-xs font-medium whitespace-nowrap" style={{ color: 'var(--accent-purple)' }}>
              {processing ? 'Memproses...' : 'Mengunggah...'}
            </span>
          </>
        ) : (
          <Paperclip size={20} className="drop-shadow-sm" style={{ color: 'var(--text-muted)' }} />
        )}
      </label>
    </>
  )
}
