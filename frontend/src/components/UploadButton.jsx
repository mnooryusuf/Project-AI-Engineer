// src/components/UploadButton.jsx
import { useRef, useState } from 'react'
import { uploadFile } from '../services/api'

const ALLOWED = ['application/pdf', 'text/plain', 'image/png', 'image/jpeg', 'image/webp']
const ALLOWED_EXT = '.pdf, .txt, .png, .jpg, .jpeg, .webp'

export default function UploadButton({ onUploadSuccess, onError }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)

  const handleFile = async (file) => {
    if (!file) return
    if (!ALLOWED.includes(file.type)) {
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
      const result = await uploadFile(file)
      onUploadSuccess?.({ ...result, previewUrl, fileSize: file.size })
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
        title="Upload dokumen atau gambar (PDF, TXT, PNG, JPG)"
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
              Mengunggah...
            </span>
          </>
        ) : (
          <span className="text-lg">📎</span>
        )}
      </label>
    </>
  )
}
