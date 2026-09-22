// src/components/MessageBubble.jsx
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Bot, FileText, Image, Database, MessageSquare, Paperclip } from 'lucide-react'

const TOOL_LABELS = {
  rag_search:    { label: 'RAG Dokumen', icon: <FileText size={14} />, color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  image_ocr:     { label: 'OCR Gambar',  icon: <Image size={14} />, color: '#a855f7', bg: 'rgba(168,85,247,0.1)' },
  sql_query:     { label: 'SQL Query',   icon: <Database size={14} />, color: '#06b6d4', bg: 'rgba(6,182,212,0.1)' },
  direct_answer: { label: 'Jawaban Langsung', icon: <MessageSquare size={14} />, color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
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
        {copied ? '✓ Disalin' : 'Salin'}
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
        <>✓ Disalin</>
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

export default function MessageBubble({ role, message, toolUsed, sources, isStreaming }) {
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
        <div
          className="max-w-[85%] sm:max-w-[70%] px-4 py-2.5 rounded-[20px] rounded-tr-[4px] text-[14.5px] leading-relaxed shadow-sm"
          style={{ background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))' }}
        >
          <p className="text-white font-medium whitespace-pre-wrap">{message}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="slide-up-fade group/msg flex gap-3.5 mb-6 max-w-[720px]">
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm shadow-sm mt-1"
        style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))' }}
      >
        <Bot size={18} className="text-white drop-shadow-md" />
      </div>

      <div className="flex-1 min-w-0 flex flex-col gap-2 bg-[var(--overlay-1)] px-5 py-4 rounded-[20px] rounded-tl-[4px] border border-[var(--glass-border)] shadow-sm">
        {tool && (
          <span
            className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md self-start"
            style={{ background: tool.bg, color: tool.color, border: `1px solid ${tool.color}33` }}
          >
            <span className="text-sm">{tool.icon}</span> {tool.label}
          </span>
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
                style={{ background: 'rgba(59,130,246,0.1)', color: '#93c5fd', border: '1px solid rgba(59,130,246,0.2)' }}
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
