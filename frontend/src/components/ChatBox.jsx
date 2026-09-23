import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import UploadButton from './UploadButton'
import { sendMessageStream, getChatHistory, waitForUploadJob } from '../services/api'
import { Bot, FileText, Image as ImageIcon, Database, X, CheckCircle, AlertTriangle } from 'lucide-react'
import Mascot from './Mascot'

// Prompt bawaan saat user melampirkan file lalu langsung menekan kirim
// tanpa mengetik apa pun — pola yang sama dipakai ChatGPT/Gemini: lampirkan
// file, kirim kosong, AI otomatis meringkas/menganalisis.
const DEFAULT_PROMPT = {
  image: 'Jelaskan isi gambar ini secara lengkap.',
  document: 'Ringkas isi dokumen ini.',
}

// Kunci localStorage tempat job_id unggahan yang belum selesai disimpan,
// supaya pemrosesan yang masih berjalan bisa dilanjutkan setelah halaman
// ditutup atau dimuat ulang.
const PENDING_UPLOAD_KEY = 'nanang_pending_upload'

const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp']

const formatBytes = (bytes) => {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ChatBox({ sessionId, onMessageSent, onLogout, onToggleSidebar }) {
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [notification, setNotify] = useState('')
  // Lampiran yang menunggu dikirim bersama pesan berikutnya — gambar (OCR)
  // ATAU dokumen yang baru diunggah (DOCUMENT_FOCUS, lihat agent.py).
  // { type: 'image' | 'document', filename, stored_filename }
  const [pendingAttachment, setPendingAttachment] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  // Server masih mengekstrak/OCR berkas yang diunggah — dipakai tombol upload
  // untuk menahan spinner dengan label "Memproses...".
  const [uploadProcessing, setUploadProcessing] = useState(false)

  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const abortControllerRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Muat riwayat setiap kali sessionId berganti (klik sesi lain di sidebar,
  // atau "Percakapan Baru"). Badge tool/sitasi & info lampiran ikut tersimpan
  // di backend jadi tetap tampil konsisten setelah pindah sesi — hanya
  // thumbnail gambar asli yang tidak bisa dipulihkan (blob URL sisi-klien,
  // bukan file yang disimpan), jadi lampiran lama tampil sebagai chip
  // ikon+nama, bukan pratinjau gambar penuh.
  useEffect(() => {
    let cancelled = false
    setHistoryLoading(true)
    setError('')
    setPendingAttachment(null)
    setInput('')

    getChatHistory(sessionId)
      .then((rows) => {
        if (cancelled) return
        setMessages(
          rows.map((r) => ({
            id: r.id,
            role: r.role,
            message: r.message,
            toolUsed: r.tool_used,
            sources: r.sources,
            followUp: r.follow_up,
            attachment: r.attachment_type
              ? { type: r.attachment_type, filename: r.attachment_filename, previewUrl: null }
              : null,
          }))
        )
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false)
      })

    return () => { cancelled = true }
  }, [sessionId])

  const notify = (msg, isError = false) => {
    if (isError) setError(msg)
    else setNotify(msg)
    setTimeout(() => { setError(''); setNotify('') }, 4000)
  }

  const handleSend = async () => {
    const attachment = pendingAttachment
    // Kalau ada lampiran dan input kosong, pakai prompt bawaan (mis. "kirim
    // langsung" setelah upload tanpa mengetik apa-apa) — bukan diblokir
    // seperti sebelumnya (submit selalu butuh teks non-kosong).
    const text = input.trim() || (attachment ? DEFAULT_PROMPT[attachment.type] : '')
    if (!text || loading) return

    const userMsg = {
      role: 'user',
      message: text,
      id: Date.now(),
      // Preview ikut dibawa ke bubble pesan supaya lampiran tetap terlihat
      // di riwayat chat sesi berjalan (blob URL, hilang setelah reload).
      attachment: attachment
        ? { type: attachment.type, filename: attachment.filename, previewUrl: attachment.previewUrl }
        : null,
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError('')

    // Semua lampiran — gambar sekalian — sudah masuk knowledge base saat
    // diunggah, jadi cukup dirujuk lewat document_filename. Gambar TIDAK lagi
    // dikirim lewat image_filename: jalur itu meng-OCR ulang tiap pertanyaan
    // (5-30 detik), padahal teksnya sudah tersimpan sejak upload.
    const documentFilename = attachment?.stored_filename ?? null
    setPendingAttachment(null)

    // Sampai event "meta" pertama datang (LLM masih memilih tool & menyusun
    // konteks — bisa 1-10 detik tergantung tool), belum ada pesan asisten
    // untuk ditampilkan sama sekali, jadi indikator titik-titik dulu yang
    // tampil (lihat kondisi render "loading && !assistantMsgId" di bawah).
    // Begitu token pertama datang, bubble jawaban muncul dan terisi
    // progresif — bukan menunggu jawaban penuh baru ditampilkan sekaligus.
    let assistantMsgId = null
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      await sendMessageStream(sessionId, text, null, documentFilename, {
        onMeta: (meta) => {
          assistantMsgId = Date.now() + 1
          setMessages((prev) => [
            ...prev,
            {
              id: assistantMsgId,
              role: 'assistant',
              message: '',
              toolUsed: meta.tool_used,
              sources: meta.sources,
              followUp: meta.follow_up,
              streaming: true,
            },
          ])
        },
        onToken: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, message: m.message + chunk } : m
            )
          )
        },
        onDone: () => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMsgId ? { ...m, streaming: false } : m))
          )
          // Sidebar perlu tahu ada sesi baru/berubah — supaya judul & urutan
          // "terakhir aktif" ikut ter-update tanpa harus refresh halaman.
          onMessageSent?.()
        },
      }, controller.signal)
    } catch (err) {
      if (err.name === 'AbortError') {
        // Dihentikan lewat tombol Stop — bukan kegagalan, jangan tampilkan
        // sebagai error. Backend tetap menyimpan jawaban parsial yang
        // sempat ter-generate (diuji: finally block di /chat tetap jalan
        // walau koneksi diputus paksa), jadi cukup tandai bubble ini
        // berhenti streaming dan biarkan teks yang sudah ada tetap tampil.
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsgId ? { ...m, streaming: false } : m))
        )
        onMessageSent?.()
      } else {
        notify(err.message || 'Gagal menghubungi server.', true)
      }
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleStop = () => {
    abortControllerRef.current?.abort()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Mulai memantau satu pekerjaan unggahan sampai selesai. Dipakai dua kali:
  // tepat setelah berkas diunggah, dan saat halaman dibuka ulang untuk
  // melanjutkan pekerjaan yang ditinggal (lihat useEffect di bawah).
  const trackUploadJob = async (jobId, previewUrl, fileSize, signal) => {
    setUploadProcessing(true)
    try {
      const job = await waitForUploadJob(jobId, { signal })
      if (job) applyUploadResult({ ...job, previewUrl, fileSize })
    } catch {
      notify('Gagal memeriksa status pemrosesan berkas.', true)
    } finally {
      localStorage.removeItem(PENDING_UPLOAD_KEY)
      setUploadProcessing(false)
    }
  }

  const handleJobStarted = ({ jobId, filename, previewUrl, fileSize }) => {
    // Disimpan supaya pekerjaan tetap bisa dilanjutkan kalau halaman ditutup
    // atau dimuat ulang saat OCR masih berjalan — tanpa ini job_id hilang dan
    // dokumen yang sudah selesai diproses tidak pernah terpasang sebagai
    // lampiran. previewUrl (blob) sengaja TIDAK disimpan: URL blob hanya
    // berlaku selama halaman itu hidup, jadi setelah dimuat ulang lampiran
    // tampil sebagai chip ikon+nama, bukan thumbnail.
    try {
      localStorage.setItem(PENDING_UPLOAD_KEY, JSON.stringify({ jobId, filename }))
    } catch {
      // Mode privat / penyimpanan penuh — pemantauan tetap jalan di sesi ini,
      // hanya kemampuan melanjutkan setelah reload yang hilang.
    }
    trackUploadJob(jobId, previewUrl, fileSize)
  }

  // Lanjutkan pekerjaan yang ditinggal saat halaman ditutup/dimuat ulang.
  useEffect(() => {
    let simpanan
    try {
      simpanan = JSON.parse(localStorage.getItem(PENDING_UPLOAD_KEY) || 'null')
    } catch {
      simpanan = null
    }
    if (!simpanan?.jobId) return

    const controller = new AbortController()
    trackUploadJob(simpanan.jobId, null, null, controller.signal)
    return () => controller.abort()
    // Sengaja hanya saat mount: pekerjaan yang tertinggal cuma perlu
    // dilanjutkan sekali, bukan tiap kali pindah sesi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const applyUploadResult = (result) => {
    // Hanya status "done" yang berarti teksnya benar-benar masuk knowledge
    // base. "warning" (tidak ada teks terbaca — mis. gambar buram) dan
    // "failed" (berkas rusak, Ollama mati di tengah jalan) ditampilkan merah
    // seperti error; dulu keduanya tampil hijau bertanda centang sehingga
    // pengguna mengira dokumennya sudah masuk padahal kosong.
    // stored_filename juga kosong untuk kedua status itu, jadi tidak ada
    // lampiran yang dibuat.
    notify(result.message, result.status !== 'done')
    // Lampiran sebelumnya dibatalkan tanpa pernah terkirim (mis. ganti file
    // sebelum menekan kirim) — blob URL-nya tidak dipakai lagi, lepaskan.
    if (pendingAttachment?.previewUrl) URL.revokeObjectURL(pendingAttachment.previewUrl)
    // Sama seperti ChatGPT/Gemini: upload TIDAK membuat giliran chat
    // tersendiri — file jadi lampiran di composer (banner di bawah),
    // baru "masuk" ke percakapan saat user benar-benar menekan kirim.
    if (result.stored_filename) {
      // Ditentukan dari ekstensi nama berkas, BUKAN dari ada/tidaknya
      // pratinjau: pratinjau (blob URL) hilang setelah halaman dimuat ulang,
      // sehingga gambar yang pemrosesannya dilanjutkan setelah reload akan
      // salah dikenali sebagai dokumen — ikonnya keliru dan prompt bawaannya
      // menawarkan "ringkasan" alih-alih "baca teksnya". Tipe ini hanya
      // menentukan tampilan, bukan cara lampiran dirujuk ke backend.
      const type = IMAGE_EXTENSIONS.some((e) => result.filename?.toLowerCase().endsWith(e))
        ? 'image'
        : 'document'
      setPendingAttachment({
        type,
        filename: result.filename,
        stored_filename: result.stored_filename,
        previewUrl: result.previewUrl || null,
        fileSize: result.fileSize,
      })
    }
  }

  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* ── Header ──────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 sm:px-6 py-4 flex-shrink-0 relative z-20 backdrop-blur-md"
        style={{ borderBottom: '1px solid var(--glass-border)', background: 'var(--surface-translucent)' }}
      >
        <div className="flex items-center gap-3">
          {/* Tombol sidebar — hanya tampil di layar sempit (sidebar sudah
              selalu terbuka di desktop) */}
          <button
            onClick={onToggleSidebar}
            className="md:hidden w-9 h-9 rounded-xl flex items-center justify-center hover:bg-[var(--overlay-2)] transition-colors"
            style={{ color: 'var(--text-muted)' }}
            title="Buka daftar percakapan"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
          <div
            className="w-9 h-9 rounded-2xl flex items-center justify-center shadow-lg"
            style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))' }}
          >
            <Bot size={22} className="text-white drop-shadow-md" />
          </div>
          <div>
            <h1 className="font-bold text-base gradient-text tracking-wide">Nanang</h1>
            <p className="text-xs font-medium opacity-80" style={{ color: 'var(--text-muted)' }}>
              Asisten AI Diskominfo HSS
            </p>
          </div>
        </div>

        {/* Status Dots */}
        <div className="flex items-center gap-3 sm:gap-5">
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full border" style={{ background: 'rgba(16,185,129,0.1)', borderColor: 'rgba(16,185,129,0.2)' }}>
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent-green, #10b981)' }} />
            <span className="text-xs font-semibold" style={{ color: 'var(--accent-green, #10b981)' }}>Ollama</span>
          </div>
          <button
            onClick={onLogout}
            className="text-xs font-semibold px-4 py-2 rounded-xl transition-all duration-300 hover:bg-[var(--overlay-2)] hover:text-[var(--text-primary)]"
            style={{ color: 'var(--text-muted)', border: '1px solid var(--glass-border)' }}
          >
            Keluar
          </button>
        </div>
      </div>

      {/* ── Messages ────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 relative z-10 scroll-smooth">
        {!historyLoading && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center slide-up-fade px-4 sm:px-8 mt-4 sm:mt-0">
            <Mascot size={72} className="mb-4 drop-shadow-lg" />
            <div>
              <p className="font-bold text-xl mb-1 tracking-tight" style={{ color: 'var(--text-primary)' }}>Halo, saya Nanang</p>
              <p className="text-[11px] italic mb-3 max-w-md mx-auto" style={{ color: 'var(--text-muted)', opacity: 0.8 }}>
                Naskah, Arsip, dan Navigasi Analitik nan Gesit
              </p>
              <p className="text-sm max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
                Ajukan pertanyaan, minta ringkasan, atau unggah dokumen/gambar untuk saya analisis.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 justify-center mt-4">
              {[
                { text: 'Apa isi dokumen ini?', icon: <FileText size={14} /> },
                { text: 'Baca teks dari gambar', icon: <ImageIcon size={14} /> },
                { text: 'Berapa jumlah chat hari ini?', icon: <Database size={14} /> },
              ].map((item, i) => (
                <button
                  key={i}
                  onClick={() => setInput(item.text)}
                  className="flex items-center gap-2 text-xs font-medium px-4 py-2.5 rounded-full transition-colors duration-200 hover:text-[var(--text-primary)] hover:bg-[var(--overlay-2)]"
                  style={{
                    background: 'var(--overlay-1)',
                    border: '1px solid var(--glass-border)',
                    color: 'var(--text-muted)',
                  }}
                >
                  {item.icon} {item.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            message={msg.message}
            toolUsed={msg.toolUsed}
            sources={msg.sources}
            isStreaming={msg.streaming}
            attachment={msg.attachment}
            followUp={msg.followUp}
          />
        ))}

        {/* Titik-titik loading — hanya sebelum event "meta" pertama datang
            (LLM masih memilih tool/menyusun konteks). Begitu bubble
            streaming muncul (token pertama tiba), titik-titik ini
            disembunyikan karena bubble yang tumbuh progresif sudah jadi
            indikator "sedang menjawab" yang lebih informatif. */}
        {loading && !messages[messages.length - 1]?.streaming && (
          <div className="slide-up-fade flex gap-3.5 mb-6">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm shadow-sm flex-shrink-0 mt-1"
              style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))' }}
            >
              <Bot size={18} className="text-white drop-shadow-md" />
            </div>
            <div className="flex items-center gap-2 bg-[var(--overlay-1)] px-5 py-4 rounded-[20px] rounded-tl-[4px] border border-[var(--glass-border)] shadow-sm">
              {(() => {
                const lastMsg = messages[messages.length - 1]
                const isAnalyzing = lastMsg?.role === 'user' && lastMsg?.attachment
                if (isAnalyzing) {
                  return (
                    <div className="flex items-center gap-2.5 px-1 py-0.5">
                      <svg className="animate-spin w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="var(--overlay-3)" strokeWidth="3"/>
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--accent-purple)" strokeWidth="3" strokeLinecap="round"/>
                      </svg>
                      <span className="text-[13px] font-medium" style={{ color: 'var(--text-muted)' }}>
                        Menganalisis {lastMsg.attachment.type === 'image' ? 'gambar' : 'dokumen'}...
                      </span>
                    </div>
                  )
                }
                return (
                  <div className="flex items-center gap-2.5 px-1 py-0.5">
                    <div className="flex items-center gap-1">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </div>
                    <span className="text-[13px] font-medium animate-pulse" style={{ color: 'var(--text-muted)' }}>
                      Sedang berpikir...
                    </span>
                  </div>
                )
              })()}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Notifications ───────────────────────── */}
      {(error || notification) && (
        <div
          className="mx-4 sm:mx-8 mb-3 px-5 py-3 rounded-2xl text-sm font-medium slide-up-fade shadow-lg flex items-center gap-2"
          style={{
            background: error ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
            border: `1px solid ${error ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)'}`,
            color: error ? '#fca5a5' : '#6ee7b7',
            backdropFilter: 'blur(12px)'
          }}
        >
          {error ? <AlertTriangle size={18} /> : <CheckCircle size={18} />}
          <span>{error || notification}</span>
        </div>
      )}

      {/* ── Lampiran (gambar/dokumen) ───────────── */}
      {pendingAttachment && (
        <div
          className="mx-4 sm:mx-8 mb-3 flex items-center justify-between gap-3 px-4 py-3 rounded-2xl text-xs slide-up-fade shadow-lg backdrop-blur-md"
          style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: 'var(--accent-blue)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            {pendingAttachment.type === 'image' && pendingAttachment.previewUrl ? (
              <img
                src={pendingAttachment.previewUrl}
                alt={pendingAttachment.filename}
                onClick={() => window.open(pendingAttachment.previewUrl, '_blank')}
                title="Klik untuk memperbesar"
                className="w-11 h-11 rounded-lg object-cover flex-shrink-0 border border-blue-400/30 cursor-zoom-in"
              />
            ) : (
              <div className="w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(59,130,246,0.15)' }}>
                {pendingAttachment.type === 'image' ? <ImageIcon size={18} /> : <FileText size={18} />}
              </div>
            )}
            <span className="min-w-0 truncate">
              <code className="bg-[var(--overlay-3)] px-1.5 py-0.5 rounded text-[var(--accent-blue)]">{pendingAttachment.filename}</code>
              {pendingAttachment.fileSize != null && (
                <span className="opacity-70"> &middot; {formatBytes(pendingAttachment.fileSize)}</span>
              )}
              {' '}siap dianalisis — ketik pertanyaan atau langsung tekan kirim untuk{' '}
              {pendingAttachment.type === 'image' ? 'baca teksnya' : 'ringkasan otomatis'}
            </span>
          </div>
          <button
            onClick={() => {
              if (pendingAttachment.previewUrl) URL.revokeObjectURL(pendingAttachment.previewUrl)
              setPendingAttachment(null)
            }}
            className="w-6 h-6 rounded-full flex items-center justify-center bg-blue-500/20 hover:bg-blue-500/40 transition-colors flex-shrink-0"
            title="Batalkan lampiran"
          >
            <X size={12} strokeWidth={3} />
          </button>
        </div>
      )}

      {/* ── Input Bar ───────────────────────────── */}
      <div className="px-4 sm:px-8 pb-6 pt-2 relative z-20 flex-shrink-0 bg-transparent">
        <div
          className="flex items-end gap-3 p-2 rounded-[2rem] glass transition-all duration-300 focus-within:shadow-[0_0_20px_rgba(59,130,246,0.15)] focus-within:border-blue-500/40"
        >
          <div className="ml-1 mb-1">
            <UploadButton
              onJobStarted={handleJobStarted}
              onError={(msg) => notify(msg, true)}
              processing={uploadProcessing}
            />
          </div>

          <div className="flex-1 flex items-center min-h-[44px]">
            <textarea
              ref={textareaRef}
              id="chat-input"
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
              }}
              onKeyDown={handleKeyDown}
              placeholder="Tulis pertanyaan..."
              rows={1}
              disabled={loading}
              className="w-full bg-transparent resize-none outline-none text-sm font-medium text-[var(--text-primary)] placeholder-[var(--text-muted)] leading-relaxed py-3 pr-2 scroll-smooth"
              style={{ maxHeight: '120px' }}
            />
          </div>

          <button
            id="send-btn"
            onClick={loading ? handleStop : handleSend}
            disabled={!loading && !input.trim() && !pendingAttachment}
            className="w-12 h-12 mb-0.5 mr-0.5 rounded-[1.5rem] flex items-center justify-center transition-all duration-200 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed"
            style={{ 
              background: (!loading && !input.trim() && !pendingAttachment) ? 'var(--overlay-3)' : 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
              color: (!loading && !input.trim() && !pendingAttachment) ? 'var(--text-muted)' : '#ffffff'
            }}
            title={loading ? 'Hentikan jawaban' : 'Kirim'}
          >
            {loading ? (
              <span className="w-3.5 h-3.5 rounded-[3px] bg-current" />
            ) : (
              <svg className="w-5 h-5 transform translate-x-px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        <div className="text-center mt-3">
          <p className="text-[10px] uppercase tracking-wider font-semibold opacity-40">Tekan Enter untuk mengirim &middot; Shift+Enter untuk baris baru</p>
        </div>
      </div>
    </div>
  )
}
