// src/components/MessageBubble.jsx
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Bot, FileText, Image, Database, MessageSquare, Paperclip, Check, CornerDownRight, Sparkles } from 'lucide-react'
import Mascot from './Mascot'

const TOOL_LABELS = {
  rag_search:      { label: 'RAG Dokumen', icon: <FileText size={14} />, color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  // Dokumen yang baru diunggah & langsung ditanyakan — dianalisis langsung
  // by filename, BUKAN lewat similarity search seperti rag_search (lihat
  // agent.py::_prepare_answer). Badge beda supaya user bisa membedakan.
  document_focus:  { label: 'Analisis Dokumen', icon: <FileText size={14} />, color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  image_ocr:       { label: 'OCR Gambar',  icon: <Image size={14} />, color: '#a855f7', bg: 'rgba(168,85,247,0.1)' },
  sql_query:       { label: 'SQL Query',   icon: <Database size={14} />, color: '#06b6d4', bg: 'rgba(6,182,212,0.1)' },
  direct_answer:   { label: 'Jawaban Langsung', icon: <MessageSquare size={14} />, color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
}

// Overlay tombol "Salin" pada blok kode — hanya muncul saat hover, mengikuti
// pola ChatGPT/Gemini untuk code block.
function CodeBlock({ children, ...props }) {
  const [copied, setCopied] = useState(false)
  const text = children?.props?.children ? String(children.props.children).replace(/\n$/, '') : ''

  const handleCopy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="relative group/code my-2">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 text-[11px] font-medium px-2 py-1 rounded-md opacity-0 group-hover/code:opacity-100 transition-opacity duration-150"
        style={{ background: 'var(--overlay-3)', color: 'var(--text-muted)' }}
      >
        {copied ? <><Check size={12} className="inline mr-1" /> Disalin</> : 'Salin'}
      </button>
      <pre {...props}>{children}</pre>
    </div>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-1 rounded-md opacity-0 group-hover/msg:opacity-100 transition-opacity duration-150 hover:bg-[var(--overlay-2)]"
      style={{ color: 'var(--text-muted)' }}
      title="Salin jawaban"
    >
      {copied ? (
        <><Check size={14} className="inline mr-1" /> Disalin</>
      ) : (
        <>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          Salin
        </>
      )}
    </button>
  )
}

export default function MessageBubble({ role, message, toolUsed, sources, isStreaming, attachment, followUp, model }) {
  const isUser = role === 'user'
  const tool = TOOL_LABELS[toolUsed] || null

  // Pesan user: bubble kompak rata kanan (khas semua chat app, termasuk
  // ChatGPT/Gemini). Pesan AI: TIDAK dibungkus bubble — teks polos lebar
  // penuh, hanya avatar kecil sebagai penanda pengirim. Ini pola yang sama
  // persis dipakai ChatGPT & Gemini: bubble simetris di kedua sisi terasa
  // seperti aplikasi pesan instan, bukan transkrip asisten.
  if (isUser) {
    return (
      <div className="slide-up-fade flex justify-end mb-6">
        <div className="max-w-[85%] sm:max-w-[70%] flex flex-col items-end gap-1.5">
          {attachment?.previewUrl && (
            <img
              src={attachment.previewUrl}
              alt={attachment.filename}
              onClick={() => window.open(attachment.previewUrl, '_blank')}
              title="Klik untuk memperbesar"
              className="max-w-[200px] max-h-[200px] rounded-2xl object-cover border border-white/10 shadow-sm cursor-zoom-in"
            />
          )}
          {attachment && !attachment.previewUrl && (
            <span
              className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg"
              style={{ background: 'var(--overlay-2)', color: 'var(--text-muted)' }}
            >
              {attachment.type === 'image' ? <Image size={13} /> : <FileText size={13} />} {attachment.filename}
            </span>
          )}
          <div
            className="px-4 py-2.5 rounded-[20px] rounded-tr-[4px] text-[14.5px] leading-relaxed shadow-sm"
            style={{ background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))' }}
          >
            <p className="text-white font-medium whitespace-pre-wrap">{message}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="slide-up-fade group/msg flex gap-3.5 mb-6 max-w-[720px]">
      <Mascot size={34} className="flex-shrink-0 mt-0.5 drop-shadow-sm" />
      
      <div className="flex-1 min-w-0 flex flex-col gap-2 bg-[var(--overlay-1)] px-5 py-4 rounded-[20px] rounded-tl-[4px] border border-[var(--glass-border)] shadow-sm">
        {(tool || followUp || model === 'gemini') && (
          <div className="flex flex-wrap items-center gap-2">
            {tool && (
              <span
                className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md"
                style={{ background: tool.bg, color: tool.color, border: `1px solid ${tool.color}33` }}
              >
                <span className="text-sm">{tool.icon}</span> {tool.label}
              </span>
            )}
            {/* Penanda jawaban yang memakai riwayat percakapan (lihat
                agent._is_follow_up) — supaya pengguna tahu kenapa jawabannya
                merujuk ke dokumen/topik sebelumnya, atau justru tidak. */}
            {followUp && (
              <span
                className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md"
                style={{ background: 'var(--overlay-2)', color: 'var(--text-muted)' }}
                title="Jawaban ini melanjutkan percakapan sebelumnya"
              >
                <CornerDownRight size={12} /> Lanjutan
              </span>
            )}
            {/* Jawaban yang ditulis model eksternal ditandai, supaya jelas
                mana yang isinya pernah dikirim ke Google. */}
            {model === 'gemini' && (
              <span
                className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md"
                style={{ background: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.25)' }}
                title="Jawaban ditulis Gemini Flash (Google)"
              >
                <Sparkles size={12} /> Gemini
              </span>
            )}
          </div>
        )}

        <div
          className="prose prose-invert prose-sm max-w-none font-medium text-[14.5px] leading-relaxed prose-p:leading-relaxed prose-pre:bg-[var(--code-bg)] prose-pre:border prose-pre:border-[var(--code-border)] prose-pre:rounded-xl"
          style={{ color: 'var(--text-primary)' }}
        >
          <ReactMarkdown components={{ pre: CodeBlock }}>{message}</ReactMarkdown>
          {isStreaming && (
            <span
              className="inline-block w-[2px] h-[1em] align-middle ml-0.5 animate-pulse"
              style={{ background: 'var(--accent-cyan)' }}
            />
          )}
        </div>

        {/* Tombol copy hanya berguna kalau jawabannya sudah selesai —
            selagi masih streaming, teksnya belum lengkap untuk disalin. */}
        {!isStreaming && (
          <div className="flex items-center gap-2 -ml-1">
            <CopyButton text={message} />
          </div>
        )}

        {sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-0.5">
            {sources.map((src, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors hover:bg-blue-500/20 cursor-default"
                style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--accent-blue)', border: '1px solid rgba(59,130,246,0.2)' }}
              >
                <Paperclip size={12} /> <span className="opacity-90">{src.filename}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
