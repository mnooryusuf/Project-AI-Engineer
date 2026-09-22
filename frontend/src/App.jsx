// src/App.jsx — Root Application dengan Auth flow (Premium UI)
import { useState, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ChatBox from './components/ChatBox'
import Sidebar from './components/Sidebar'
import DocumentsPanel from './components/DocumentsPanel'
import { login, register, getChatSessions } from './services/api'

function LoginPage({ onLogin }) {
  const [mode, setMode]       = useState('login') // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [email, setEmail]     = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        await register(username, email, password)
        setMode('login')
        setError('') 
        alert('Registrasi berhasil! Silakan login.')
      } else {
        const data = await login(username, password)
        localStorage.setItem('access_token', data.access_token)
        onLogin()
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Terjadi kesalahan.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{
        background: 'radial-gradient(circle at 15% 50%, rgba(6, 182, 212, 0.15) 0%, transparent 40%), radial-gradient(circle at 85% 30%, rgba(168, 85, 247, 0.15) 0%, transparent 40%), var(--bg-primary)',
      }}
    >
      <div className="w-full max-w-sm slide-up-fade">
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="w-20 h-20 rounded-[1.25rem] flex items-center justify-center text-5xl mx-auto mb-5 shadow-xl"
            style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-blue), var(--accent-purple))' }}
          >
            🤖
          </div>
          <h1 className="text-3xl font-bold gradient-text tracking-tight mb-2">Agentic RAG</h1>
          <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
            Premium Local AI Assistant
          </p>
        </div>

        {/* Form Card */}
        <div className="glass rounded-3xl p-8 relative overflow-hidden">
          {/* Subtle accent line on top of card */}
          <div className="absolute top-0 left-0 right-0 h-1" style={{ background: 'linear-gradient(90deg, var(--accent-cyan), var(--accent-purple))' }} />
          
          {/* Tab Switch */}
          <div className="flex mb-8 p-1 rounded-2xl" style={{ background: 'rgba(0,0,0,0.2)', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.1)' }}>
            {['login', 'register'].map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError('') }}
                className="flex-1 py-2.5 text-sm font-semibold transition-all duration-300 capitalize rounded-xl"
                style={{
                  background: mode === m ? 'var(--overlay-3)' : 'transparent',
                  color: mode === m ? '#fff' : 'var(--text-muted)',
                  boxShadow: mode === m ? '0 4px 12px rgba(0,0,0,0.1)' : 'none'
                }}
              >
                {m === 'login' ? 'Masuk' : 'Daftar'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Username */}
            <div>
              <label className="text-xs font-medium mb-1.5 ml-1 block" style={{ color: 'var(--text-muted)' }}>Username</label>
              <input
                id="username-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-2xl text-sm outline-none interactive-ring bg-transparent"
                style={{
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-primary)',
                  backgroundColor: 'var(--overlay-1)'
                }}
                placeholder="masukkan username"
              />
            </div>

            {/* Email (register only) */}
            {mode === 'register' && (
              <div className="slide-up-fade">
                <label className="text-xs font-medium mb-1.5 ml-1 block" style={{ color: 'var(--text-muted)' }}>Email</label>
                <input
                  id="email-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 rounded-2xl text-sm outline-none interactive-ring bg-transparent"
                  style={{
                    border: '1px solid var(--glass-border)',
                    color: 'var(--text-primary)',
                    backgroundColor: 'var(--overlay-1)'
                  }}
                  placeholder="email@example.com"
                />
              </div>
            )}

            {/* Password */}
            <div>
              <label className="text-xs font-medium mb-1.5 ml-1 block" style={{ color: 'var(--text-muted)' }}>Password</label>
              <input
                id="password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-2xl text-sm outline-none interactive-ring bg-transparent"
                style={{
                  border: '1px solid var(--glass-border)',
                  color: 'var(--text-primary)',
                  backgroundColor: 'var(--overlay-1)'
                }}
                placeholder="••••••••"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="text-xs px-4 py-3 rounded-xl slide-up-fade flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.1)', color: '#fca5a5', border: '1px solid rgba(239,68,68,0.2)' }}>
                <span className="text-lg">⚠️</span> {error}
              </div>
            )}

            {/* Submit */}
            <button
              id="auth-submit-btn"
              type="submit"
              disabled={loading}
              className="w-full mt-4 py-3.5 rounded-2xl text-sm font-bold text-white transition-all duration-200 hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))' }}
            >
              {loading ? '⏳ Memproses...' : mode === 'login' ? 'Masuk ke Sistem' : 'Buat Akun Sekarang'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-6 font-medium tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Agentic RAG &middot; Local AI &middot; Powered by Ollama
        </p>
      </div>
    </div>
  )
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(() => uuidv4())
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [documentsOpen, setDocumentsOpen] = useState(false)
  // Default 'dark' — tema asli aplikasi. index.html sudah menerapkan nilai
  // tersimpan ke <html> lebih dulu (hindari flash tema salah saat load);
  // state di sini cuma menyusul supaya React tahu nilainya untuk re-render
  // (mis. label tombol toggle, className prose-invert vs bukan).
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) setIsAuthenticated(true)
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const data = await getChatSessions()
      setSessions(data)
      // Buka percakapan terakhir yang aktif (bukan langsung mulai kosong)
      // kalau memang ada riwayat — mirip perilaku ChatGPT/Gemini saat dibuka.
      const savedId = localStorage.getItem('last_session_id')
      if (savedId && data.some((s) => s.session_id === savedId)) {
        setSessionId(savedId)
      } else if (data.length > 0) {
        setSessionId(data[0].session_id)
      }
    } catch {
      // Diam saja — sidebar cukup tampil kosong kalau gagal memuat.
    }
  }, [])

  useEffect(() => {
    if (isAuthenticated) loadSessions()
  }, [isAuthenticated, loadSessions])

  useEffect(() => {
    localStorage.setItem('last_session_id', sessionId)
  }, [sessionId])

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('last_session_id')
    setIsAuthenticated(false)
    setSessions([])
  }

  const handleNewChat = () => {
    setSessionId(uuidv4())
    setSidebarOpen(false)
  }

  const handleSelectSession = (id) => {
    setSessionId(id)
    setSidebarOpen(false)
  }

  if (!isAuthenticated) {
    return <LoginPage onLogin={() => setIsAuthenticated(true)} />
  }

  return (
    <div
      className="h-screen flex relative overflow-hidden"
      style={{
        background: 'radial-gradient(circle at top right, rgba(6,182,212,0.06) 0%, transparent 60%), radial-gradient(circle at bottom left, rgba(168,85,247,0.06) 0%, transparent 60%), var(--bg-primary)',
      }}
    >
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenDocuments={() => { setDocumentsOpen(true); setSidebarOpen(false) }}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <ChatBox
          sessionId={sessionId}
          onMessageSent={loadSessions}
          onLogout={handleLogout}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />
      </div>
      <DocumentsPanel isOpen={documentsOpen} onClose={() => setDocumentsOpen(false)} />
    </div>
  )
}
