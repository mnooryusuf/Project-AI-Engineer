// src/components/UploadButton.jsx
import { useRef, useState } from 'react'
import { uploadFile } from '../services/api'

const ALLOWED = ['application/pdf', 'text/plain', 'image/png', 'image/jpeg', 'image/webp']
const ALLOWED_EXT = '.pdf, .txt, .png, .jpg, .jpeg, .webp'

export default function UploadButton({ onUploadSuccess, onError }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

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

    setUploading(true)
    setProgress(0)
    try {
      const result = await uploadFile(file, setProgress)
      onUploadSuccess?.(result)
    } catch (err) {
      onError?.(err.response?.data?.detail || 'Upload gagal.')
    } finally {
      setUploading(false)
      setProgress(0)
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
        className="cursor-pointer flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 hover:scale-105 active:scale-95"
        style={{
          background: uploading ? 'rgba(139,92,246,0.3)' : 'var(--overlay-2)',
          border: '1px solid var(--glass-border)',
        }}
      >
        {uploading ? (
          <div className="relative w-5 h-5">
            <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="var(--overlay-3)" strokeWidth="2"/>
              <path d="M12 2a10 10 0 0 1 10 10" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-purple-300">
              {progress}%
            </span>
          </div>
        ) : (
          <span className="text-lg">📎</span>
        )}
      </label>
    </>
  )
}
