// src/components/UploadButton.jsx
import { useRef, useState } from 'react'
import { Paperclip } from 'lucide-react'
import { uploadFile, getUploadJob } from '../services/api'

// Jeda antar pengecekan status. Cukup rapat supaya berkas kecil (.txt selesai
// ~1 detik) tidak terasa tertahan, tapi tidak membanjiri server selama OCR
// yang bisa berjalan beberapa menit.
const POLL_INTERVAL_MS = 1000

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

export default function UploadButton({ onUploadSuccess, onError }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  // null selama transfer berkas, "memproses" selama server mengekstrak/OCR —
  // dibedakan karena keduanya berbeda jauh lamanya (detik vs menit) dan label
  // "Mengunggah..." selama dua menit terlihat seperti macet.
  const [phase, setPhase] = useState(null)

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
      // Unggahan selesai cepat; pemrosesan (ekstraksi/OCR/embedding) berjalan
      // di server dan dipantau lewat job_id sampai statusnya bukan
      // "processing". OCR bisa memakan menit, jadi tidak ada batas percobaan
      // di sini — pengguna bisa membatalkan dengan menutup halaman, dan
      // server tetap menyelesaikan pekerjaannya.
      const { job_id } = await uploadFile(file)
      let job
      do {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
        job = await getUploadJob(job_id)
        setPhase(job.status === 'processing' ? 'memproses' : null)
      } while (job.status === 'processing')

      onUploadSuccess?.({ ...job, previewUrl, fileSize: file.size })
    } catch (err) {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      onError?.(err.response?.data?.detail || 'Upload gagal.')
    } finally {
      setUploading(false)
      setPhase(null)
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
          uploading ? 'px-3 h-10 gap-2' : 'w-10 h-10 hover:scale-105 active:scale-95'
        }`}
        style={{
          background: uploading ? 'rgba(139,92,246,0.3)' : 'var(--overlay-2)',
          border: '1px solid var(--glass-border)',
        }}
      >
        {uploading ? (
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
              <path d="M12 2a10 10 0 0 1 10 10" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="text-xs font-medium whitespace-nowrap" style={{ color: '#c4b5fd' }}>
              {phase === 'memproses' ? 'Memproses...' : 'Mengunggah...'}
            </span>
          </>
        ) : (
          <Paperclip size={20} className="text-white drop-shadow-sm" />
        )}
      </label>
    </>
  )
}
