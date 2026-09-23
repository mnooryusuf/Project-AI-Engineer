// src/components/UploadButton.jsx
import { useRef, useState } from 'react'
import { Paperclip } from 'lucide-react'
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

// `processing` datang dari ChatBox, yang memantau pekerjaan sampai selesai —
// pemantauan tidak ditaruh di sini karena harus tetap berjalan (dan bisa
// dilanjutkan setelah halaman dimuat ulang) terlepas dari tombol ini.
export default function UploadButton({ onJobStarted, onError, processing }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  // Spinner tetap berputar selama server masih memproses, walau transfer
  // berkasnya sendiri sudah selesai sejak tadi.
  const busy = uploading || processing

  const handleFile = async (file) => {
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

    // Preview dibuat dari File object di browser (blob URL) — tidak perlu
    // menunggu upload selesai atau memanggil endpoint tambahan di backend.
    const isImage = file.type.startsWith('image/')
    const previewUrl = isImage ? URL.createObjectURL(file) : null

    setUploading(true)
    try {
      // Transfer berkas selesai cepat; ekstraksi/OCR/embedding berjalan di
      // server. job_id diserahkan ke ChatBox yang memantaunya sampai selesai.
      const { job_id } = await uploadFile(file)
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
