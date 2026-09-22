import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import UploadButton from './UploadButton'
import { sendMessageStream, getChatHistory } from '../services/api'
import { Bot, FileText, Image as ImageIcon, Database } from 'lucide-react'

// Prompt bawaan saat user melampirkan file lalu langsung menekan kirim
// tanpa mengetik apa pun — pola yang sama dipakai ChatGPT/Gemini: lampirkan
// file, kirim kosong, AI otomatis meringkas/menganalisis.
const DEFAULT_PROMPT = {
  image: 'Apa isi teks pada gambar ini?',
  document: 'Ringkas isi dokumen ini.',
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

  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const abortControllerRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Muat riwayat setiap kali sessionId berganti (klik sesi lain di sidebar,
  // atau "Percakapan Baru"). Riwayat lama tidak menyimpan tool_used/sources
  // (kolomnya tidak ada di tabel chat_history) — badge & sitasi cuma
  // tersedia untuk pesan yang baru dikirim di sesi berjalan ini.
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
          rows.map((r) => ({ id: r.id, role: r.role, message: r.message }))
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

    const userMsg = { role: 'user', message: text, id: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError('')

    const imageFilename = attachment?.type === 'image' ? attachment.stored_filename : null
    const documentFilename = attachment?.type === 'document' ? attachment.stored_filename : null
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
      await sendMessageStream(sessionId, text, imageFilename, documentFilename, {
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

  const handleUploadSuccess = (result) => {
    notify(`✅ ${result.message}`)
    // Sama seperti ChatGPT/Gemini: upload TIDAK membuat giliran chat
    // tersendiri — file jadi lampiran di composer (banner di bawah),
    // baru "masuk" ke percakapan saat user benar-benar menekan kirim.
    if (result.stored_filename) {
      const type = result.status === 'uploaded' ? 'image' : 'document'
      setPendingAttachment({
        type,
        filename: result.filename,
        stored_filename: result.stored_filename,
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
            <h1 className="font-bold text-base gradient-text tracking-wide">Agentic RAG</h1>
            <p className="text-xs font-medium opacity-80" style={{ color: 'var(--text-muted)' }}>
              Local AI &middot; llama3.2:1b
            </p>
          </div>
        </div>

        {/* Status Dots */}
        <div className="flex items-center gap-3 sm:gap-5">
          <div className="hidden sm:flex items-center gap-2 bg-green-950/30 px-3 py-1.5 rounded-full border border-green-500/20">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs font-semibold text-green-400">Ollama</span>
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
          <div className="flex flex-col items-center justify-center h-full gap-5 text-center slide-up-fade">
            <div
              className="w-16 h-16 rounded-[1.5rem] flex items-center justify-center text-3xl"
              style={{ background: 'linear-gradient(135deg, rgba(6,182,212,0.1), rgba(168,85,247,0.1))', border: '1px solid rgba(168,85,247,0.2)' }}
            >
              🤖
            </div>
            <div>
              <p className="font-bold text-xl mb-2 tracking-tight" style={{ color: 'var(--text-primary)' }}>Siap Membantu Anda</p>
              <p className="text-sm max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
                Ajukan pertanyaan, minta ringkasan, atau upload dokumen/gambar untuk dianalisis oleh AI.
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
                  className="flex items-center gap-2 text-xs font-medium px-4 py-2.5 rounded-full transition-colors duration-200 hover:text-white"
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
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Notifications ───────────────────────── */}
      {(error || notification) && (
        <div
          className="mx-4 sm:mx-8 mb-3 px-5 py-3 rounded-2xl text-sm font-medium slide-up-fade shadow-lg"
          style={{
            background: error ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
            border: `1px solid ${error ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)'}`,
            color: error ? '#fca5a5' : '#6ee7b7',
            backdropFilter: 'blur(12px)'
          }}
        >
          {error || notification}
        </div>
      )}

      {/* ── Lampiran (gambar/dokumen) ───────────── */}
      {pendingAttachment && (
        <div
          className="mx-4 sm:mx-8 mb-3 flex items-center justify-between gap-3 px-4 py-3 rounded-2xl text-xs slide-up-fade shadow-lg backdrop-blur-md"
          style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)', color: '#93c5fd' }}
        >
          <div className="flex items-center gap-2">
            {pendingAttachment.type === 'image' ? <ImageIcon size={16} /> : <FileText size={16} />}
            <span>
              <code className="bg-blue-900/30 px-1.5 py-0.5 rounded text-blue-200">{pendingAttachment.filename}</code>{' '}
              siap dianalisis — ketik pertanyaan atau langsung tekan kirim untuk{' '}
              {pendingAttachment.type === 'image' ? 'baca teksnya' : 'ringkasan otomatis'}
            </span>
          </div>
          <button
            onClick={() => setPendingAttachment(null)}
            className="w-6 h-6 rounded-full flex items-center justify-center bg-blue-500/20 hover:bg-blue-500/40 transition-colors flex-shrink-0"
            title="Batalkan lampiran"
          >
            ✕
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
              onUploadSuccess={handleUploadSuccess}
              onError={(msg) => notify(msg, true)}
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
            className="w-12 h-12 mb-0.5 mr-0.5 rounded-[1.5rem] flex items-center justify-center transition-all duration-200 hover:brightness-110 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))' }}
            title={loading ? 'Hentikan jawaban' : 'Kirim'}
          >
            {loading ? (
              <span className="w-3.5 h-3.5 rounded-[3px] bg-white" />
            ) : (
              <svg className="w-5 h-5 text-white transform translate-x-px" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
