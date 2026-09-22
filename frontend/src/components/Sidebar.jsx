// src/components/Sidebar.jsx — Daftar riwayat percakapan, gaya restrained
// (bukan neon) seperti sidebar ChatGPT/Gemini.
import { FileText, Sun, Moon } from 'lucide-react'
function formatRelativeTime(iso) {
  const date = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.round(diffMs / 60000)
  if (diffMin < 1) return 'Baru saja'
  if (diffMin < 60) return `${diffMin} menit lalu`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour} jam lalu`
  const diffDay = Math.round(diffHour / 24)
  if (diffDay === 1) return 'Kemarin'
  if (diffDay < 7) return `${diffDay} hari lalu`
  return date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  isOpen,
  onClose,
  onOpenDocuments,
  theme,
  onToggleTheme,
}) {
  return (
    <>
      {/* Overlay mobile — tutup sidebar saat area luar ditekan */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 md:hidden"
          style={{ background: 'var(--scrim)' }}
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed md:static inset-y-0 left-0 z-40 w-[260px] flex-shrink-0 flex flex-col
          transition-transform duration-300 md:translate-x-0
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}
        style={{
          background: 'var(--bg-secondary)',
          borderRight: '1px solid var(--glass-border)',
        }}
      >
        <div className="p-3">
          <button
            id="new-chat-btn"
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[15px] font-semibold transition-all duration-200 shadow-sm hover:shadow-md hover:-translate-y-0.5"
            style={{ 
              background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))', 
              color: '#ffffff',
              border: 'none'
            }}
          >
            <span className="text-lg leading-none">+</span>
            Percakapan Baru
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 ? (
            <p className="text-xs px-3 py-4 text-center" style={{ color: 'var(--text-muted)' }}>
              Belum ada percakapan.
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {sessions.map((s) => {
                const active = s.session_id === activeSessionId
                return (
                  <li key={s.session_id}>
                    <button
                      onClick={() => onSelectSession(s.session_id)}
                      className="w-full text-left px-3 py-3 rounded-xl text-sm truncate transition-all duration-200 border-l-2"
                      style={{
                        background: active ? 'var(--overlay-2)' : 'transparent',
                        borderColor: active ? 'var(--accent-blue)' : 'transparent',
                        color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                      }}
                      title={s.title}
                    >
                      <span className="block truncate font-medium">{s.title || '(percakapan kosong)'}</span>
                      <span className="block text-[11px] opacity-70 mt-1">
                        {formatRelativeTime(s.last_activity)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="p-3 flex flex-col gap-1" style={{ borderTop: '1px solid var(--glass-border)' }}>
          <button
            id="open-documents-btn"
            onClick={onOpenDocuments}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors duration-150 hover:bg-[var(--overlay-2)]"
            style={{ color: 'var(--text-muted)' }}
          >
            <FileText size={16} /> Dokumen
          </button>
          <button
            id="toggle-theme-btn"
            onClick={onToggleTheme}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors duration-150 hover:bg-[var(--overlay-2)]"
            style={{ color: 'var(--text-muted)' }}
          >
            {theme === 'dark' ? <><Sun size={16} /> Mode Terang</> : <><Moon size={16} /> Mode Gelap</>}
          </button>
        </div>
      </aside>
    </>
  )
}
