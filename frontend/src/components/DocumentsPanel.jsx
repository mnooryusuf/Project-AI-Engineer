// src/components/DocumentsPanel.jsx — Daftar dokumen persisten di
// knowledge base (bukan cuma toast notifikasi sesaat saat upload).
import { useEffect, useState } from 'react'
import { getDocuments, deleteDocument } from '../services/api'

function formatDate(iso) {
  const date = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function DocumentsPanel({ isOpen, onClose }) {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deletingFilename, setDeletingFilename] = useState(null)
  const [confirmingFilename, setConfirmingFilename] = useState(null)

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    setError('')
    getDocuments()
      .then(setDocuments)
      .catch(() => setError('Gagal memuat daftar dokumen.'))
      .finally(() => setLoading(false))
  }, [isOpen])

  if (!isOpen) return null

  const handleDelete = async (filename) => {
    setDeletingFilename(filename)
    try {
      await deleteDocument(filename)
      setDocuments((prev) => prev.filter((d) => d.filename !== filename))
    } catch {
      setError(`Gagal menghapus "${filename}".`)
    } finally {
      setDeletingFilename(null)
      setConfirmingFilename(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0" style={{ background: 'var(--scrim)' }} onClick={onClose} />

      <div
        className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl glass slide-up-fade overflow-hidden"
        style={{ background: 'var(--bg-secondary)' }}
      >
        <div
          className="flex items-center justify-between px-6 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--glass-border)' }}
        >
          <h2 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>
            📄 Dokumen di Knowledge Base
          </h2>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center hover:bg-[var(--overlay-2)] transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && (
            <p className="text-sm text-center py-8" style={{ color: 'var(--text-muted)' }}>
              Memuat...
            </p>
          )}

          {!loading && error && (
            <p className="text-sm text-center py-8" style={{ color: '#fca5a5' }}>
              {error}
            </p>
          )}

          {!loading && !error && documents.length === 0 && (
            <p className="text-sm text-center py-8" style={{ color: 'var(--text-muted)' }}>
              Belum ada dokumen yang diunggah.
            </p>
          )}

          {!loading && !error && documents.length > 0 && (
            <ul className="flex flex-col gap-1">
              {documents.map((doc) => (
                <li
                  key={doc.filename}
                  className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl hover:bg-[var(--overlay-1)] transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }} title={doc.filename}>
                      {doc.filename}
                    </p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {doc.chunk_count} chunk &middot; {formatDate(doc.uploaded_at)}
                    </p>
                  </div>

                  {confirmingFilename === doc.filename ? (
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => handleDelete(doc.filename)}
                        disabled={deletingFilename === doc.filename}
                        className="text-xs font-semibold px-2.5 py-1.5 rounded-lg"
                        style={{ background: 'rgba(239,68,68,0.2)', color: '#fca5a5' }}
                      >
                        {deletingFilename === doc.filename ? '...' : 'Hapus?'}
                      </button>
                      <button
                        onClick={() => setConfirmingFilename(null)}
                        className="text-xs font-semibold px-2.5 py-1.5 rounded-lg hover:bg-[var(--overlay-2)]"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        Batal
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmingFilename(doc.filename)}
                      className="w-8 h-8 flex-shrink-0 rounded-lg flex items-center justify-center hover:bg-red-500/10 transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                      title="Hapus dari knowledge base"
                    >
                      🗑
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
